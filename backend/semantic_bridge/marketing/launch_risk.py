"""M16 lansman risk bayrağı (AI fırsatları öneri 17a): kural eşikli bayrak + tek cümle gerekçe. Karar insanda.

**Bayrak kuraldır** (model rakam da karar da üretmez); girdisi lansman özetindeki mevcut sinyallerdir (`launch.evaluate`
ve emsal eğrisi, `launch_track.emsal_days`):

- `stok` — açık sipariş depo stokunun üstünde (stok–talep çatışması).
- `dagilim` — yayın günü geçti, dağılım siparişi yok.
- `hedef` — yayından bu yana faturalı satış (Logo verisi yoksa sipariş) hedef payının eşiğin altında
  (`MARKETING_LAUNCH_ALERT_RATIO`, M46 kuralı).
- `emsal` — aynı gün sayısında birikmiş satış (esas: fatura; yoksa sipariş, etiketiyle) emsallerin ortalama eğrisinin
  `MARKETING_LAUNCH_EMSAL_RATIO` (varsayılan %70) altında. Eğri yoksa bu kural sessizce geçmez: «emsal yok» notu düşer.
- `siparis` — yayından en az `MARKETING_LAUNCH_ORDER_DAYS` (varsayılan 3) gün sonra hâlâ hiç CRM siparişi yok.

Düzey: `yuksek` (stok ya da dağılım kuralı, ya da iki ve üstü neden), `orta` (tek neden), `yok`.

**Gerekçe cümlesi:** önce kural cümlesi (nedenlerin rakamlı metni). Zeki AI yalnız gece turunda (BATCH), bayrağı olan ve
girdisi değişen lansman için tek cümle yazar; cümle `marketing.guard` denetiminden geçmezse (kaynaksız rakam, kanıtsız
iddia, teknoloji adı) kural cümlesi kalır. Cümle `semantic_mkt_meta` içinde `launch-risk:<id>` anahtarında saklanır.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Optional

from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import guard as G

LEVELS = {"yuksek": "Yüksek risk", "orta": "Dikkat", "yok": "Risk görünmüyor"}
REASONS = {"stok": "Stok–talep", "dagilim": "Dağılım", "hedef": "Hedef payı", "emsal": "Emsal sapması", "siparis": "Sipariş yok"}
SYSTEM = ("Sen TİMAŞ Yayınları pazarlama ekibine lansman riskini tek cümleyle anlatan Zeki AI'sın. Türkçe yaz. Yalnız "
          "verilen olguları kullan; olgularda olmayan hiçbir sayı yazma, yeni yüzde ya da hesap üretme. Karar verme, "
          "öneri buyurma; yalnız durumu söyle. Teknoloji ya da model adı yazma.")


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    def num(key: str, default: float, lo: float, hi: float) -> float:
        raw = (conf(key) or "").strip().replace(",", ".")
        try:
            return max(lo, min(hi, float(raw))) if raw else default
        except ValueError:
            return default

    return {"emsalRatio": num("MARKETING_LAUNCH_EMSAL_RATIO", 70, 1, 100) / 100.0,
            "orderDays": int(num("MARKETING_LAUNCH_ORDER_DAYS", 3, 0, 60))}


def _tr(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}".replace(",", ".")


def flag(head: dict[str, Any], alert_ratio: float, rs: dict[str, Any]) -> dict[str, Any]:
    """Lansman başlığından (`launch.head`) bayrak: düzey, nedenler (kod + rakamlı metin), kural cümlesi, olgular."""
    sig = head.get("sinyal") or {}
    g = sig.get("gun") if sig.get("gun") is not None else head.get("gun")
    reasons: list[dict[str, str]] = []
    notes: list[str] = []
    if head.get("durum") == "kapandi" or not sig:
        return {"duzey": "yok", "duzeyAdi": LEVELS["yok"], "nedenler": [], "notlar": ["Lansman kapandı ya da henüz okunmadı."],
                "kuralCumlesi": None, "olgular": []}
    dep = (sig.get("depo") or {}).get("deger")
    if sig.get("stokCatismasi"):
        reasons.append({"kod": "stok", "metin": f"açık sipariş {_tr(sig.get('bekleyen'))} adet, depo stoku {_tr(dep)} adet"})
    if sig.get("dagilimYok"):
        reasons.append({"kod": "dagilim", "metin": "yayın günü geçti, dağılım siparişi görünmüyor"})
    if sig.get("hedefAltinda") and sig.get("oran") is not None:
        esas = "faturalı satış" if sig.get("oranEsas") == "fatura" else "sipariş"
        reasons.append({"kod": "hedef", "metin": f"{esas} hedef payının %{sig['oran'] * 100:.0f}'inde (eşik %{alert_ratio * 100:.0f})"})
    curve = ((head.get("emsal") or {}).get("egri")) or []
    if g is not None and g >= 1:
        n = min(int(g), len(curve))
        expected = sum(curve[:n]) if n else 0.0
        esas = "fatura" if sig.get("oranEsas") == "fatura" and sig.get("fatura") is not None else "siparis"
        actual = sig.get("fatura") if esas == "fatura" else sig.get("siparis")
        if not curve:
            notes.append("Emsal eğrisi yok; emsal kuralı uygulanamadı.")
        elif expected > 0 and actual is not None:
            ratio = actual / expected
            if ratio < rs["emsalRatio"]:
                what = "faturalı satış" if esas == "fatura" else "sipariş"
                reasons.append({"kod": "emsal", "metin": f"ilk {n} günde {what} {_tr(actual)} adet, emsal ortalaması {_tr(expected)} adet "
                                                         f"(%{ratio * 100:.0f}, eşik %{rs['emsalRatio'] * 100:.0f})"})
        if g >= rs["orderDays"] and (sig.get("siparis") or 0) <= 0:
            reasons.append({"kod": "siparis", "metin": f"yayından {int(g)} gün sonra CRM'de sipariş görünmüyor"})
    codes = {r["kod"] for r in reasons}
    level = "yuksek" if (codes & {"stok", "dagilim"} or len(reasons) >= 2) else ("orta" if reasons else "yok")
    rule = None
    if reasons:
        rule = "Kurala göre " + ("yüksek risk" if level == "yuksek" else "dikkat") + ": " + "; ".join(r["metin"] for r in reasons) + "."
    facts = [f"Kitap: {head.get('baslik')}", f"Yayından bu yana gün: {g}"] + [r["metin"] for r in reasons]
    return {"duzey": level, "duzeyAdi": LEVELS[level], "nedenler": [{**r, "ad": REASONS[r["kod"]]} for r in reasons],
            "notlar": notes, "kuralCumlesi": rule, "olgular": facts}


def input_hash(f: dict[str, Any]) -> str:
    return hashlib.sha1("\n".join(f["olgular"]).encode("utf-8")).hexdigest()


def attach(engine: Any, tenant: str, heads: list[dict[str, Any]], alert_ratio: float, rs: dict[str, Any]) -> list[dict[str, Any]]:
    """Liste satırlarına `risk` ekler: bayrak + saklı Zeki AI cümlesi (girdisi aynıysa) ya da kural cümlesi."""
    em = emsal_map(engine, tenant, [h["id"] for h in heads])
    out = []
    for h in heads:
        f = flag({**h, "emsal": em.get(h["id"]) or {}}, alert_ratio, rs)
        saved = C.meta_get(engine, tenant, f"launch-risk:{h['id']}") if f["duzey"] != "yok" else {}
        use_model = bool(saved.get("cumle")) and saved.get("girdi") == input_hash(f)
        out.append({**h, "risk": {k: f[k] for k in ("duzey", "duzeyAdi", "nedenler", "notlar")}
                    | {"cumle": saved["cumle"] if use_model else f["kuralCumlesi"], "cumleKaynak": "zeki" if use_model else "kural",
                       "kuralCumlesi": f["kuralCumlesi"]}})
    return out


def write_sentence(engine: Any, tenant: str, head: dict[str, Any], f: dict[str, Any], llm: Any, claims: list[str]) -> dict[str, Any]:
    """Bayraklı lansmana Zeki AI tek cümle (gece, BATCH). Girdi değişmediyse çağrılmaz. Denetimden geçen ilk cümle
    saklanır; hiçbiri geçmezse saklı cümle silinir (ekranda kural cümlesi kalır)."""
    key = f"launch-risk:{head['id']}"
    h = input_hash(f)
    saved = C.meta_get(engine, tenant, key)
    if saved.get("girdi") == h:
        return {"durum": "degismedi"}
    prompt = ("Olgular (yazabileceğin sayılar yalnız bunlar):\n" + "\n".join(f"- {x}" for x in f["olgular"])
              + "\n\nBu lansmanın neden riskli göründüğünü pazarlama müdürüne tek cümleyle yaz.")
    raw = str(llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], max_tokens=160) or "")
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    res = G.check(raw, [str(head.get("baslik") or "")], f["olgular"], claims)
    first = next((s for s in re.split(r"(?<=[.!?…])\s+", res["metin"].replace("\n", " ")) if s.strip()), None)
    C.meta_set(engine, tenant, key, {"girdi": h, "cumle": first, "dusen": res["dusenSayisi"]})
    return {"durum": "yazildi" if first else "dustu", "dusen": res["dusenSayisi"]}


def emsal_map(engine: Any, tenant: str, ids: list[str]) -> dict[str, dict[str, Any]]:
    """Lansman → özetindeki emsal (eğri dahil). Liste ucu `head`'de eğri taşımaz; tek sorguyla okunur."""
    import sqlalchemy as sa

    from semantic_bridge.marketing import launch as L

    if not ids:
        return {}
    with engine.connect() as c:
        rows = c.execute(sa.select(L.LAUNCHES.c.id, L.LAUNCHES.c.ozet_json).where(
            L.LAUNCHES.c.tenant_id == tenant, L.LAUNCHES.c.id.in_(ids))).all()
    return {r.id: (C.loads(r.ozet_json, {}).get("emsal") or {}) for r in rows}


def run(engine: Any, tenant: str, heads: list[dict[str, Any]], alert_ratio: float, rs: dict[str, Any], llm: Any,
        claims: list[str]) -> dict[str, Any]:
    """Gece turu adımı: bayrağı olan açık lansmanlara Zeki AI cümlesi. Model yoksa kural cümlesi yeter."""
    em = emsal_map(engine, tenant, [h["id"] for h in heads])
    out = {"bayrakli": 0, "yazildi": 0, "dustu": 0, "degismedi": 0, "hata": 0, "model": llm is not None}
    for h in heads:
        f = flag({**h, "emsal": em.get(h["id"]) or {}}, alert_ratio, rs)
        if f["duzey"] == "yok":
            continue
        out["bayrakli"] += 1
        if llm is None:
            continue
        try:
            r = write_sentence(engine, tenant, h, f, llm, claims)
            out[r["durum"]] = out.get(r["durum"], 0) + 1
        except Exception:  # noqa: BLE001 — model düştüyse kural cümlesi kalır, sonraki koşu yeniden dener
            out["hata"] += 1
    return out
