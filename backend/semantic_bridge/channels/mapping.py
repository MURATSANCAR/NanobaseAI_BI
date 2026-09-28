"""M42 cari ↔ platform eşlemesi (M40/M41 de kullanır) ve paketin ayarları.

Eşleme üç katmandır; hepsi kullanıcı onayıyla kesinleşir, hiçbiri CRM'e ya da Logo'ya yazılmaz:

1. **Cari** (`semantic_channel_accounts`): e-ticaret kanal kodlu (Logo `CLCARD.SPECODE2`, varsayılan `E-TICARET`) her
   cari için aday platform. Aday iki yoldan gelir: (a) unvan ya da CRM adı platformun adını veya işletmecisinin ticari
   unvanını içeriyorsa «ad» adayı; (b) değilse Zeki AI kapalı kümeden seçer (platform listesi + «platform değil»),
   seçimin olasılığı kaydedilir, eşik altı aday gösterilmez. Onay «onayli» yapar; kullanıcı başka platform ya da
   «platform değil» seçebilir (yöntem «elle»).
2. **Kanal kodu** (ayar `kanal-platform:<kod>`): tek tek eşlenemeyecek kadar çok carisi olan kanal (ör. sitenin bireysel
   müşterileri) bütünüyle bir platforma bağlanır; o kanaldaki cariler tek satırda ('#K:<kod>') toplanır.
3. **Hedef bölgesi** (ayar `hedef-bolge:<kod>`): CRM satış hedefi bölgesi (new_bolge) → platform (Soru 4 kararı: kanal
   hedefi CRM bölge hedefidir; M46 hedefinden türetilen kanal hedefi ayrıca gösterilir).

Platform listesi kapalıdır (`PLATFORMS`); işletmeci unvanları Yönetim ayarından (`CHANNEL_PLATFORM_HINTS`) değişir.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge.channels import store as S

log = logging.getLogger("semantic.channels.mapping")

#: Kapalı platform listesi. `degil` = e-ticaret kodlu ama platform kanalı değil (karnede sayılmaz, ayrıca gösterilir).
PLATFORMS: dict[str, str] = {
    "hepsiburada": "Hepsiburada",
    "trendyol": "Trendyol",
    "amazon": "Amazon",
    "kitapyurdu": "Kitapyurdu",
    "dr": "D&R",
    "idefix": "idefix",
    "timas.com.tr": "timas.com.tr",
    "diger": "Diğer e-ticaret",
    "degil": "Platform değil",
}
D2C = "timas.com.tr"
UNMAPPED = "eslenmemis"
#: Karnede sütun olan platformlar (sıra ekranda korunur).
CARD_PLATFORMS = [k for k in PLATFORMS if k != "degil"]

#: İşletmeci ticari unvanlarının varsayılanı (genel bilgi; Yönetim → Platform ve kanallar'dan değişir).
DEFAULT_HINTS: dict[str, list[str]] = {
    "hepsiburada": ["D-MARKET", "D MARKET"],
    "trendyol": ["DSM GRUP"],
    "dr": ["TURKUVAZ"],
    "amazon": ["AMAZON TURKEY"],
}

MAP_PROMPT = (
    "Bir yayınevinin muhasebe sistemindeki cari kartı aşağıda. Bu cari hangi e-ticaret platformunun ya da satış "
    "sitesinin carisidir? Platformun kendisi değil de başka bir işletmeyse (kitapçı, dağıtıcı, kurum, kişi) "
    "«Platform değil» seç. Emin değilsen «Diğer e-ticaret» seç.\n\n"
    "Platformlar ve işletmecileri:\n{platforms}\n\n"
    "Cari kodu: {code}\nLogo unvanı: {unvan}\nLogo kanal kodu: {kanal}\nCRM firma adı: {crm}"
)


def fold(s: Any) -> str:
    t = str(s or "").replace("İ", "i").replace("I", "ı").lower()
    for a, b in (("ı", "i"), ("ş", "s"), ("ğ", "g"), ("ü", "u"), ("ö", "o"), ("ç", "c"), ("â", "a"), ("î", "i"), ("û", "u")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------ ayarlar


def _num(v: Any, default: float) -> float:
    try:
        x = float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return default
    return x if x == x else default


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    """Yönetim → Platform ve kanallar ayarları (ekran > ortam > varsayılan)."""
    hints = dict(DEFAULT_HINTS)
    raw = (conf("CHANNEL_PLATFORM_HINTS") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                hints = {k: [str(x) for x in (v if isinstance(v, list) else [v]) if str(x).strip()]
                         for k, v in parsed.items() if k in PLATFORMS}
        except ValueError:
            log.warning("CHANNEL_PLATFORM_HINTS JSON değil; varsayılan kullanılıyor")
    specodes = [s.strip() for s in (conf("CHANNEL_SPECODES") or "E-TICARET").split(",") if s.strip()]
    return {
        "specodes": specodes,
        "years": max(1, int(_num(conf("CHANNEL_YEARS"), 2))),
        "hints": hints,
        "minProb": _num(conf("CHANNEL_MAP_MIN_PROB"), 0.70),
        "minMargin": _num(conf("CHANNEL_MAP_MIN_MARGIN"), 0.30),
        "modelBudgetSec": int(_num(conf("CHANNEL_MODEL_BUDGET_SEC"), 600)),
        "returnThreshold": _num(conf("CHANNEL_RETURN_THRESHOLD"), 0.10),
        "discountRise": _num(conf("CHANNEL_DISCOUNT_RISE_PTS"), 2.0),
        "orderDays": int(_num(conf("CHANNEL_ORDER_DAYS"), 180)),
        "recipients": [x.strip() for x in (conf("CHANNEL_REPORT_RECIPIENTS") or "").replace(";", ",").split(",") if "@" in x],
        "d2cMinAdet": _num(conf("CHANNEL_D2C_MIN_ADET"), 20),
        "d2cIndex": _num(conf("CHANNEL_D2C_INDEX"), 1.5),
        "yearCodes": _year_codes(conf("CHANNEL_TARGET_YEAR_CODES")),
    }


def _year_codes(raw: Optional[str]) -> dict[int, int]:
    """«2025:3,2026:100000000» → {2025: 3, 2026: 100000000}. Boşsa CRM etiketinden okunur."""
    out: dict[int, int] = {}
    for part in (raw or "").split(","):
        if ":" in part:
            y, c = part.split(":", 1)
            if y.strip().isdigit() and c.strip().isdigit():
                out[int(y)] = int(c)
    return out


def kanal_map(engine: sa.engine.Engine, tenant: str) -> dict[str, str]:
    """Kanal kodu (özel kod 2) → platform."""
    return {k.split(":", 1)[1]: v for k, v in S.settings_all(engine, tenant).items() if k.startswith("kanal-platform:") and v in PLATFORMS}


def region_map(engine: sa.engine.Engine, tenant: str) -> dict[str, str]:
    """CRM hedef bölgesi kodu → platform."""
    return {k.split(":", 1)[1]: v for k, v in S.settings_all(engine, tenant).items() if k.startswith("hedef-bolge:") and v in PLATFORMS}


def extra_costs(engine: sa.engine.Engine, tenant: str) -> dict[str, float]:
    """Platform → ek kanal maliyeti oranı (net cironun payı; finans girer, komisyon/kargo/reklam için). Yoksa boş."""
    out = {}
    for k, v in S.settings_all(engine, tenant).items():
        if k.startswith("ek-maliyet:"):
            x = _num(v, -1)
            if 0 <= x < 1:
                out[k.split(":", 1)[1]] = x
    return out


# ------------------------------------------------------------------ aday


def name_candidate(card: dict[str, Any], hints: dict[str, list[str]]) -> Optional[str]:
    """Unvan ya da CRM adı tek bir platformun adını/işletmecisini içeriyorsa o platform; birden çoksa ya da hiçse None."""
    text = " ".join(fold(x) for x in (card.get("unvan"), card.get("crmAd")) if x)
    if not text:
        return None
    hits = set()
    for key, label in PLATFORMS.items():
        if key in ("diger", "degil"):
            continue
        names = [label, key] + list(hints.get(key, []))
        for n in names:
            f = fold(n)
            if len(f) >= 3 and re.search(r"(^|[^a-z0-9])" + re.escape(f) + r"($|[^a-z0-9])", text):
                hits.add(key)
                break
    return next(iter(hits)) if len(hits) == 1 else None


def _platform_lines(hints: dict[str, list[str]]) -> str:
    lines = []
    for key, label in PLATFORMS.items():
        if key in ("diger", "degil"):
            continue
        ops = ", ".join(hints.get(key, []))
        lines.append(f"- {label}" + (f" (işletmeci: {ops})" if ops else ""))
    return "\n".join(lines)


def model_candidate(llm: Any, card: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    """Zeki AI kapalı küme seçimi. {"platform", "olasilik", "marj", "yontem", "emin", "olasiliklar"}. Model hiç cevap
    veremezse istisna yükselir (çağıran sonraki tura bırakır)."""
    labels = [v for k, v in PLATFORMS.items()]
    prompt = MAP_PROMPT.format(platforms=_platform_lines(st["hints"]), code=card.get("cariKodu") or "-",
                               unvan=card.get("unvan") or "-", kanal=card.get("kanal") or "-", crm=card.get("crmAd") or "-")
    key_of = {v: k for k, v in PLATFORMS.items()}
    if hasattr(llm, "choose"):
        r = llm.choose(prompt, labels)
        conf = bool(r.choice is not None and r.confident(st["minProb"], min_margin=st["minMargin"]))
        probs = {key_of[k]: round(v, 4) for k, v in (r.probs or {}).items() if k in key_of}
        return {"platform": key_of.get(r.choice) if r.choice else None, "olasilik": r.probability, "marj": r.margin,
                "yontem": r.method, "emin": conf, "olasiliklar": probs}
    ans = (llm.chat([{"role": "user", "content": prompt + "\nSeçenekler: " + "; ".join(labels) + "\nYalnız seçeneği aynen yaz.\nCevap:"}],
                    max_tokens=16, temperature=0.0) or "").strip(" .:-*«»\"'\n")
    pick = next((k for k, v in PLATFORMS.items() if fold(v) == fold(ans)), None)
    return {"platform": pick, "olasilik": None, "marj": None, "yontem": "text" if pick else "none", "emin": False, "olasiliklar": {}}


def propose(engine: sa.engine.Engine, tenant: str, llm: Any, st: dict[str, Any], *, budget_sec: Optional[int] = None,
            only: Optional[list[str]] = None, force: bool = False) -> dict[str, Any]:
    """Bekleyen carilere aday bulur: önce ad eşleşmesi, sonra Zeki AI. Onaylı satıra dokunmaz. Süre dolunca kalan
    sonraki tura kalır (kayıp yok)."""
    out = {"ad": 0, "zeki": 0, "eminDegil": 0, "kalan": 0, "atlandi": None}
    budget = st["modelBudgetSec"] if budget_sec is None else budget_sec
    t0 = time.monotonic()
    with engine.connect() as c:
        stmt = sa.select(S.ACCOUNTS).where(S.ACCOUNTS.c.tenant_id == tenant, S.ACCOUNTS.c.durum != "onayli")
        if only:
            stmt = stmt.where(S.ACCOUNTS.c.logo_cari_kodu.in_(only))
        rows = [S.account_view(r) for r in c.execute(stmt.order_by(S.ACCOUNTS.c.logo_cari_kodu)).all()]
    todo = [r for r in rows if force or (r["durum"] == "bekliyor" and not r["adayZamani"])]
    for card in todo:
        cand = name_candidate(card, st["hints"])
        if cand:
            _save_candidate(engine, tenant, card["cariKodu"], cand, "ad", None, {"kaynak": "ad", "platform": cand})
            out["ad"] += 1
            continue
        if llm is None:
            out["atlandi"] = "model tanımlı değil"
            out["kalan"] += 1
            continue
        if time.monotonic() - t0 > budget:
            out["kalan"] += 1
            continue
        try:
            r = model_candidate(llm, card, st)
        except Exception as e:  # noqa: BLE001 — model düşerse kalan sonraki tura
            log.warning("channels: eşleme adayı alınamadı: %s", e)
            out["atlandi"] = "model cevap vermedi"
            out["kalan"] += 1
            continue
        if r["emin"] and r["platform"]:
            _save_candidate(engine, tenant, card["cariKodu"], r["platform"], "zeki", r["olasilik"], r)
            out["zeki"] += 1
        else:
            _save_candidate(engine, tenant, card["cariKodu"], None, "zeki", r["olasilik"], r)
            out["eminDegil"] += 1
    return out


def _save_candidate(engine: sa.engine.Engine, tenant: str, code: str, platform: Optional[str], yontem: str,
                    olasilik: Optional[float], evidence: dict[str, Any]) -> None:
    with engine.begin() as c:
        c.execute(S.ACCOUNTS.update().where(S.ACCOUNTS.c.tenant_id == tenant, S.ACCOUNTS.c.logo_cari_kodu == code,
                                            S.ACCOUNTS.c.durum != "onayli")
                  .values(platform=platform, durum="aday" if platform else "bekliyor", yontem=yontem, olasilik=olasilik,
                          aday_json=json.dumps(evidence, ensure_ascii=False, default=str), aday_zamani=S.now(), guncellendi=S.now()))


class MappingError(ValueError):
    pass


def decide(engine: sa.engine.Engine, tenant: str, user: str, code: str, body: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Cari eşlemesini onaylar ya da değiştirir. body: {"platform": <anahtar> | null, "onay": bool, "not": str}.
    `platform` verilmezse adayın platformu onaylanır; null + onay=false eşlemeyi kaldırır (satır «bekliyor»a döner)."""
    cur = S.account_get(engine, tenant, code)
    if cur is None:
        raise MappingError("Cari eşleme listesinde yok.")
    has_platform = "platform" in body
    platform = body.get("platform") if has_platform else cur["platform"]
    approve = bool(body.get("onay", True))
    note = (str(body.get("not") or "").strip() or None)
    if platform is not None and platform not in PLATFORMS:
        raise MappingError("Bilinmeyen platform.")
    if approve and not platform:
        raise MappingError("Onay için platform seçilmeli.")
    before = {"platform": cur["platform"], "durum": cur["durum"]}
    if approve:
        yontem = cur["yontem"] if (not has_platform or platform == cur["platform"]) and cur["yontem"] else "elle"
        vals = dict(platform=platform, durum="onayli", yontem=yontem, onaylayan=user, onay_tarihi=S.now(), notu=note, guncellendi=S.now())
    else:
        vals = dict(platform=None, durum="bekliyor", yontem=None, olasilik=None, onaylayan=None, onay_tarihi=None, notu=note,
                    guncellendi=S.now())
    with engine.begin() as c:
        c.execute(S.ACCOUNTS.update().where(S.ACCOUNTS.c.tenant_id == tenant, S.ACCOUNTS.c.logo_cari_kodu == code).values(**vals))
    after = S.account_get(engine, tenant, code)
    return after, {"once": before, "sonra": {"platform": after["platform"], "durum": after["durum"]}, "not": note}


def set_kanal(engine: sa.engine.Engine, tenant: str, user: str, kod: str, platform: Optional[str]) -> None:
    if platform is not None and platform not in PLATFORMS:
        raise MappingError("Bilinmeyen platform.")
    S.setting_set(engine, tenant, f"kanal-platform:{kod}", platform, user)


def set_region(engine: sa.engine.Engine, tenant: str, user: str, kod: str, platform: Optional[str]) -> None:
    if platform is not None and platform not in PLATFORMS:
        raise MappingError("Bilinmeyen platform.")
    S.setting_set(engine, tenant, f"hedef-bolge:{kod}", platform, user)


def region_candidate(name: str, hints: dict[str, list[str]]) -> Optional[str]:
    """Bölge adı bir platformun adını içeriyorsa o (ör. «HEPSİBURADA», «KİTAPYURDU», «D&R»). Onaysız öneridir."""
    return name_candidate({"unvan": name}, hints)
