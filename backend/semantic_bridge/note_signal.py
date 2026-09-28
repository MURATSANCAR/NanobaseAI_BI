"""Serbest not sinyali (AI fırsatları öneri 16): cari başına ziyaret ve görüşme notlarından kapalı küme etiketi ve son
notların iki cümlelik özeti. **Yalnız bilgi**: hiçbir skora (M30 öncelik, M59 bayi skoru, M38 kayıp riski) bileşen
olarak girmez; kural sürümüne girmesi ayrı karardır.

**Kaynaklar (yalnız okuma):**
- Portal: M30/M31 ortak ziyaret tablosu `semantic_saha_ziyaret` (`tur='cari'`; M59 bayi kartındaki notlar da buraya
  yazılır), M59 aksiyon notu `semantic_dealer_actions.notu`, M38 aksiyon açıklaması ve sonuç notu
  `semantic_musteri_actions`. **Gizli işaretli ziyaret notu hiçbir yerde kullanılmaz** (modele de gitmez).
- CRM (seçenekli): `new_etkinlikBase` «Cari Ziyareti» (`new_ziyarettipi` 4) `new_info` + `new_Tahsilatinfo`. Etkinliği
  cariye bağlayan kolon ölçülmedi; M30'un ayarı `FIELD_CRM_VISIT_ACCOUNT_COLUMN` boşsa CRM kaynağı hiç okunmaz.

**Etiket (gece, BATCH):** tahsilat sözü · şikâyet · sipariş niyeti · iade talebi · kapanış sinyali · yok (`LABELS`).
Portal ziyaretinde «ödeme sözü» alanı doluysa etiket kuraldır (tahsilat sözü); kalan not `QueuedLlm.choose` + olasılık
eşiği (`NOT_SINYALI_MIN_OLASILIK`, `NOT_SINYALI_MIN_FARK`); eşik altı «emin-degil».

**Özet:** carinin son 5 (gizli olmayan) notundan iki cümle; her sayı notlarda ya da olgu listesinde geçmek zorunda
(`marketing.guard.check`), geçmeyen cümle düşer; hiç cümle kalmazsa kural özeti (etiket sayıları). Notlar değişmedikçe
model yeniden çağrılmaz (girdi özeti).

**Maske:** M51'in `support.mask_personal` (e-posta, telefon, IBAN, kart, kimlik no) + İK'nın `mask_names` (temsilci
adları) + «Ad Bey/Hanım» kalıbı. Model yalnız LLM kapısından (`rt.llm_for("not-sinyali", …)`).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge.marketing import guard as G

log = logging.getLogger("semantic.note_signal")

_md = sa.MetaData()

SIGNALS = sa.Table(
    "semantic_note_signals", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kaynak", sa.String(16), primary_key=True),              # saha-ziyaret | bayi-aksiyon | musteri-aksiyon | crm-etkinlik
    sa.Column("not_id", sa.String(80), primary_key=True),
    sa.Column("cari_kodu", sa.String(40), nullable=False, index=True),
    sa.Column("tarih", sa.String(10)),
    sa.Column("etiket", sa.String(12)),                                 # LABELS anahtarı; emin-degil ise boş
    sa.Column("olasilik", sa.Float),
    sa.Column("yontem", sa.String(12), nullable=False),                 # kural | zeki | emin-degil
    sa.Column("parmak", sa.String(40), nullable=False),
    sa.Column("siniflama", sa.DateTime(timezone=True), nullable=False),
)
SUMMARIES = sa.Table(
    "semantic_note_signal_summaries", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("cari_kodu", sa.String(40), primary_key=True),
    sa.Column("girdi", sa.String(40), nullable=False),                  # son notların özeti (değişince yeniden yazılır)
    sa.Column("metin", sa.Text),
    sa.Column("kaynak", sa.String(8), nullable=False),                  # zeki | kural
    sa.Column("dusen", sa.Integer, nullable=False, default=0),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)

LABELS: dict[str, str] = {
    "tahsilat": "Tahsilat sözü", "sikayet": "Şikâyet", "siparis": "Sipariş niyeti", "iade": "İade talebi",
    "kapanis": "Kapanış sinyali", "yok": "Yok",
}
SOURCES: dict[str, str] = {
    "saha-ziyaret": "Ziyaret notu", "bayi-aksiyon": "Bayi aksiyonu", "musteri-aksiyon": "Müşteri aksiyonu",
    "crm-etkinlik": "CRM ziyaret kaydı",
}
LAST_N = 5
PROMPT = ("Bir yayınevinin satış temsilcisinin kitapçı/bayi ziyaretinden sonra yazdığı not aşağıda. Not hangi sinyali "
          "taşıyor? «Tahsilat sözü»: ödeme sözü ya da ödeme tarihi. «Şikâyet»: müşterinin memnuniyetsizliği. «Sipariş "
          "niyeti»: sipariş verecek ya da kitap istiyor. «İade talebi»: kitap iade etmek istiyor. «Kapanış sinyali»: dükkânı "
          "kapatma, devir, işi bırakma. Hiçbiri yoksa «Yok».\n\nNot (kişisel bilgi maskelendi): {metin}")
SUMMARY_SYSTEM = ("Sen TİMAŞ Yayınları satış ekibi için not özeti yazan Zeki AI'sın. Türkçe yaz. Yalnız verilen notları "
                  "kullan; notlarda olmayan hiçbir sayı, tarih ya da tutar yazma, yeni hesap yapma. Kişi adı yazma. "
                  "Teknoloji ya da model adı yazma.")
SUMMARY_PROMPT = ("Bir carinin son ziyaret/görüşme notları aşağıda (yeniden eskiye). Satış temsilcisi için tam iki cümlelik "
                  "özet yaz: son durum ve dikkat edilecek konu. Başlık ya da madde işareti kullanma.\n\n{notlar}")

_ready: set[int] = set()
_lock = threading.Lock()
_TITLE = re.compile(r"\b[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)?\s+(Bey|Hanım|Hanim|Bay|Bayan)\b")


class NoteError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def now() -> datetime:
    return datetime.now(timezone.utc)


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    def num(key: str, default: float, lo: float, hi: float) -> float:
        raw = (conf(key) or "").strip().replace(",", ".")
        try:
            return max(lo, min(hi, float(raw))) if raw else default
        except ValueError:
            return default

    return {
        "minProb": num("NOT_SINYALI_MIN_OLASILIK", 0.60, 0.0, 1.0),
        "minMargin": num("NOT_SINYALI_MIN_FARK", 0.20, 0.0, 1.0),
        "windowDays": int(num("NOT_SINYALI_GUN", 90, 1, 3650)),
        "crmDays": int(num("NOT_SINYALI_CRM_GUN", 365, 1, 3650)),
        "budgetSec": int(num("NOT_SINYALI_MODEL_SURE_SN", 1200, 10, 86_400)),
        "crmColumn": (conf("FIELD_CRM_VISIT_ACCOUNT_COLUMN") or "").strip(),
        "schema": (conf("CRM_SCHEMA") or "Timas_MSCRM.dbo").strip(),
    }


def mask(text: Any, names: Iterable[str] = ()) -> str:
    """Mevcut maskeler: M51 `mask_personal` + İK `mask_names` (bilinen kişi adları) + «Ad Bey/Hanım» kalıbı."""
    from semantic_bridge.hr_engagement_text import MASK_PERSON, mask_names
    from semantic_bridge.support import mask_personal

    t = mask_personal(str(text or ""))
    t = _TITLE.sub(lambda m: f"{MASK_PERSON} {m.group(2)}", t)
    t, _n = mask_names(t, [n for n in names if n])
    return re.sub(r"\s+", " ", t).strip()


def fingerprint(*parts: Any) -> str:
    return hashlib.sha1("\n".join(G.fold(p) for p in parts).encode("utf-8")).hexdigest()


def _day(v: Any) -> Optional[str]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else None


# ------------------------------------------------------------------ notlar (yalnız okuma)


def portal_notes(engine: sa.engine.Engine, tenant: str, codes: Optional[set[str]] = None) -> list[dict[str, Any]]:
    """Portal notları: {kaynak, id, cari, tarih, metin, sozOdeme}. Gizli ziyaret notu ve iptal edilen kayıt hariç."""
    out: list[dict[str, Any]] = []
    insp = sa.inspect(engine)
    if insp.has_table("semantic_saha_ziyaret"):
        from semantic_bridge import field_sales as F

        q = sa.select(F.VISITS).where(F.VISITS.c.tenant_id == tenant, F.VISITS.c.tur == "cari", F.VISITS.c.durum != "iptal",
                                      sa.or_(F.VISITS.c.gizli.is_(None), F.VISITS.c.gizli == sa.false()))
        with engine.connect() as c:
            for r in c.execute(q):
                if codes is not None and r.hedef_kimlik not in codes:
                    continue
                txt = " ".join(x for x in (r.notu, r.sonraki_adim) if x and str(x).strip())
                if not txt and not r.soz_odeme_tarihi:
                    continue
                out.append({"kaynak": "saha-ziyaret", "id": r.id, "cari": r.hedef_kimlik,
                            "tarih": (r.gerceklesen or r.planlanan or _day(r.olusturma) or "")[:10] or None,
                            "metin": txt, "sozOdeme": bool(r.soz_odeme_tarihi)})
    if insp.has_table("semantic_dealer_actions"):
        from semantic_bridge import dealers as D

        with engine.connect() as c:
            for r in c.execute(sa.select(D.ACTIONS).where(D.ACTIONS.c.tenant_id == tenant, D.ACTIONS.c.durum != "iptal")):
                if (codes is not None and r.logo_code not in codes) or not (r.notu or "").strip():
                    continue
                out.append({"kaynak": "bayi-aksiyon", "id": r.id, "cari": r.logo_code,
                            "tarih": _day(r.guncelleme) or _day(r.olusturma), "metin": r.notu})
    if insp.has_table("semantic_musteri_actions"):
        from semantic_bridge import musteri as M

        with engine.connect() as c:
            for r in c.execute(sa.select(M.ACTIONS).where(M.ACTIONS.c.tenant_id == tenant, M.ACTIONS.c.durum != "iptal")):
                if codes is not None and r.cari_kodu not in codes:
                    continue
                txt = " ".join(x for x in (r.aciklama, r.sonuc_notu) if x and str(x).strip())
                if txt:
                    out.append({"kaynak": "musteri-aksiyon", "id": r.id, "cari": r.cari_kodu,
                                "tarih": r.tarih or _day(r.olusturma), "metin": txt})
    return out


_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def crm_notes_sql(schema: str, account_column: str, since: date, account_id: Optional[str] = None) -> str:
    """CRM «Cari Ziyareti» etkinliklerinin açıklama ve tahsilat açıklaması (yalnız okuma). Kolon adı ve kimlik doğrulanır.
    `account_id` verilirse yalnız o hesap (ekrandaki «özeti yenile»)."""
    from semantic_bridge import field_sales_sources as src

    p = src.prefix(schema)
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$", account_column or ""):
        raise NoteError("CRM ziyaret–cari kolonu geçerli bir ad değil.")
    one = ""
    if account_id is not None:
        acc = str(account_id).strip().strip("{}")
        if not _GUID.match(acc):
            raise NoteError("CRM hesap kimliği geçersiz.")
        one = f" AND e.{account_column} = '{acc}'"
    return (f"SELECT CAST(e.new_etkinlikId AS nvarchar(40)) AS id, CAST(e.{account_column} AS nvarchar(40)) AS account_id,"
            " e.new_GercZiyTarihi AS tarih, CAST(e.new_info AS nvarchar(4000)) AS info,"
            " CAST(e.new_Tahsilatinfo AS nvarchar(4000)) AS tahsilat"
            f" FROM {p}new_etkinlikBase e WHERE e.statecode = 0 AND CAST(e.new_ziyarettipi AS int) = 4"
            f" AND e.new_GercZiyTarihi >= '{since.isoformat()}'"
            " AND (e.new_info IS NOT NULL OR e.new_Tahsilatinfo IS NOT NULL)" + one)


def crm_notes(rows: Iterable[dict[str, Any]], account_to_code: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        acc = str(r.get("account_id") or "").strip("{}").lower()
        code = account_to_code.get(acc)
        txt = " ".join(str(x).strip() for x in (r.get("info"), r.get("tahsilat")) if x and str(x).strip())
        if not code or not txt:
            continue
        out.append({"kaynak": "crm-etkinlik", "id": str(r.get("id") or "").strip("{}").lower(), "cari": code,
                    "tarih": _day(r.get("tarih")), "metin": txt})
    return out


def account_map(engine: sa.engine.Engine, tenant: str) -> dict[str, str]:
    """CRM hesap kimliği → Logo cari kodu (M30 portföyü)."""
    if not sa.inspect(engine).has_table("semantic_field_portfolio"):
        return {}
    from semantic_bridge import field_sales as F

    with engine.connect() as c:
        return {str(a).strip("{}").lower(): code for code, a in c.execute(
            sa.select(F.PORTFOLIO.c.logo_code, F.PORTFOLIO.c.crm_account_id).where(
                F.PORTFOLIO.c.tenant_id == tenant, F.PORTFOLIO.c.crm_account_id.isnot(None)))}


def known_names(engine: sa.engine.Engine, tenant: str) -> list[str]:
    """Maskelenecek bilinen kişi adları: temsilci adları (M30 portföyü, M38 cariler)."""
    names: set[str] = set()
    insp = sa.inspect(engine)
    with engine.connect() as c:
        if insp.has_table("semantic_field_portfolio"):
            from semantic_bridge import field_sales as F

            names |= {n for (n,) in c.execute(sa.select(F.PORTFOLIO.c.temsilci_ad).where(F.PORTFOLIO.c.tenant_id == tenant).distinct()) if n}
        if insp.has_table("semantic_musteri_accounts"):
            from semantic_bridge import musteri as M

            names |= {n for (n,) in c.execute(sa.select(M.ACCOUNTS.c.temsilci_ad).where(M.ACCOUNTS.c.tenant_id == tenant).distinct()) if n}
    return sorted(names)


# ------------------------------------------------------------------ etiket


def classify(engine: sa.engine.Engine, tenant: str, notes: Iterable[dict[str, Any]], llm: Any, st: dict[str, Any], *,
             names: Iterable[str] = (), force: bool = False, clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    ensure(engine)
    names = list(names)
    t0 = clock()
    out: dict[str, Any] = {"kural": 0, "zeki": 0, "eminDegil": 0, "degismedi": 0, "kalan": 0, "atlandi": None, "degisenCari": []}
    with engine.connect() as c:
        known = {(r.kaynak, r.not_id): r.parmak for r in c.execute(
            sa.select(SIGNALS.c.kaynak, SIGNALS.c.not_id, SIGNALS.c.parmak).where(SIGNALS.c.tenant_id == tenant))}
    changed: set[str] = set()
    for n in notes:
        src, nid, code = n["kaynak"], str(n["id"])[:80], str(n["cari"])[:40]
        text = mask(n.get("metin"), names)
        fp = fingerprint(text, "soz" if n.get("sozOdeme") else "", n.get("tarih") or "")
        if not force and known.get((src, nid)) == fp:
            out["degismedi"] += 1
            continue
        if n.get("sozOdeme"):
            vals = {"etiket": "tahsilat", "olasilik": None, "yontem": "kural"}
            out["kural"] += 1
        elif not text:
            vals = {"etiket": "yok", "olasilik": None, "yontem": "kural"}
            out["kural"] += 1
        elif llm is None or not hasattr(llm, "choose"):
            out["atlandi"] = "model tanımlı değil"
            out["kalan"] += 1
            continue
        elif clock() - t0 > st["budgetSec"]:
            out["kalan"] += 1
            continue
        else:
            try:
                ch = llm.choose(PROMPT.format(metin=text[:1500]), list(LABELS.values()))
            except Exception as e:  # noqa: BLE001
                log.warning("not sinyali: etiket alınamadı: %s", e)
                out["atlandi"] = "model cevap vermedi"
                out["kalan"] += 1
                continue
            key = next((k for k, v in LABELS.items() if v == ch.choice), None)
            if key and ch.confident(st["minProb"], min_margin=st["minMargin"]):
                vals = {"etiket": key, "olasilik": ch.probability, "yontem": "zeki"}
                out["zeki"] += 1
            else:
                vals = {"etiket": None, "olasilik": ch.probability, "yontem": "emin-degil"}
                out["eminDegil"] += 1
        with engine.begin() as c:
            c.execute(SIGNALS.delete().where(SIGNALS.c.tenant_id == tenant, SIGNALS.c.kaynak == src, SIGNALS.c.not_id == nid))
            c.execute(SIGNALS.insert().values(tenant_id=tenant, kaynak=src, not_id=nid, cari_kodu=code, tarih=n.get("tarih"),
                                              parmak=fp, siniflama=now(), **vals))
        changed.add(code)
    out["degisenCari"] = sorted(changed)
    return out


def prune(engine: sa.engine.Engine, tenant: str, notes: Iterable[dict[str, Any]], sources: Iterable[str]) -> int:
    """Kaynağında artık olmayan (silinen, gizlenen, iptal edilen) notun etiketi silinir. Yalnız tam okunan kaynaklar."""
    keep = {(n["kaynak"], str(n["id"])[:80]) for n in notes}
    srcs = list(sources)
    n = 0
    with engine.begin() as c:
        for r in c.execute(sa.select(SIGNALS.c.kaynak, SIGNALS.c.not_id).where(SIGNALS.c.tenant_id == tenant,
                                                                               SIGNALS.c.kaynak.in_(srcs))).all():
            if (r.kaynak, r.not_id) not in keep:
                c.execute(SIGNALS.delete().where(SIGNALS.c.tenant_id == tenant, SIGNALS.c.kaynak == r.kaynak,
                                                 SIGNALS.c.not_id == r.not_id))
                n += 1
    return n


# ------------------------------------------------------------------ cari görünümü ve özet


def _key(n: dict[str, Any]) -> tuple[str, str]:
    return n["kaynak"], str(n["id"])[:80]


def _last(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(notes, key=lambda n: (n.get("tarih") or "", str(n["id"])), reverse=True)[:LAST_N]


def signal_rows(engine: sa.engine.Engine, tenant: str, code: str) -> dict[tuple[str, str], Any]:
    ensure(engine)
    with engine.connect() as c:
        return {(r.kaynak, r.not_id): r for r in c.execute(
            sa.select(SIGNALS).where(SIGNALS.c.tenant_id == tenant, SIGNALS.c.cari_kodu == code))}


def notes_for_view(portal: list[dict[str, Any]], rows: dict[tuple[str, str], Any], code: str) -> list[dict[str, Any]]:
    """Ekran için carinin notları: portal notları (canlı) + CRM notları (gece etiketlenen satırlardan; metinsiz)."""
    mine = [n for n in portal if n["cari"] == code]
    have = {_key(n) for n in mine}
    for (src, nid), r in rows.items():
        if src == "crm-etkinlik" and (src, nid) not in have:
            mine.append({"kaynak": src, "id": nid, "cari": code, "tarih": r.tarih, "metin": None})
    return mine


def summary_input(last: list[dict[str, Any]], rows: dict[tuple[str, str], Any]) -> str:
    """Özetin girdisi: son notların kimliği, tarihi ve etiket satırının parmak izi (metin değişince gece yenilenir)."""
    return fingerprint(*[f"{n['kaynak']}:{n['id']}:{n.get('tarih') or ''}:{getattr(rows.get(_key(n)), 'parmak', '')}"
                         for n in last])


def rule_summary(counts: dict[str, int], last: list[dict[str, Any]], scope: str) -> str:
    """Model yoksa ya da denetimden cümle kalmazsa: etiket sayılarından iki cümle (rakamlar tablodan). `scope`:
    «Son 90 günün notlarında» ya da «Son 5 notta»."""
    if not last:
        return "Bu cari için okunabilir not yok."
    parts = [f"{LABELS[k].lower()} {v}" for k, v in counts.items() if k != "yok" and v]
    first = (f"{scope} " + ", ".join(parts) + " sinyali var.") if parts else f"{scope} belirgin sinyal yok."
    top = last[0]
    lab = LABELS.get(top.get("etiket") or "", "belirsiz")
    return first + f" En son not ({top.get('tarih') or 'tarihsiz'}) «{lab}» olarak etiketlendi."


def _enrich(notes: list[dict[str, Any]], rows: dict[tuple[str, str], Any]) -> list[dict[str, Any]]:
    out = []
    for n in notes:
        r = rows.get(_key(n))
        out.append({**n, "etiket": r.etiket if r else None, "yontem": r.yontem if r else None, "olasilik": r.olasilik if r else None})
    return out


def _counts(enriched: list[dict[str, Any]], since: str) -> tuple[dict[str, int], int]:
    counts = {k: 0 for k in LABELS}
    belirsiz = 0
    for n in enriched:
        if (n.get("tarih") or "") < since:
            continue
        if n["etiket"]:
            counts[n["etiket"]] += 1
        elif n["yontem"] == "emin-degil":
            belirsiz += 1
    return counts, belirsiz


def view(engine: sa.engine.Engine, tenant: str, code: str, portal: list[dict[str, Any]], st: dict[str, Any],
         today: Optional[date] = None) -> dict[str, Any]:
    """Ekran: son 5 notun etiketi, pencere içi etiket sayıları, kayıtlı özet. Not metni gönderilmez (ekranların kendi
    not listesi var); yalnız etiket, kaynak ve tarih."""
    today = today or now().date()
    since = (today - timedelta(days=st["windowDays"])).isoformat()
    rows = signal_rows(engine, tenant, code)
    enriched = _enrich(notes_for_view(portal, rows, code), rows)
    counts, belirsiz = _counts(enriched, since)
    last = _last(enriched)
    with engine.connect() as c:
        s = c.execute(sa.select(SUMMARIES).where(SUMMARIES.c.tenant_id == tenant, SUMMARIES.c.cari_kodu == code)).first()
    girdi = summary_input(last, rows)
    return {
        "cari": code, "gun": st["windowDays"], "sayilar": counts, "belirsiz": belirsiz, "etiketler": LABELS,
        "sonNotlar": [{"kaynak": n["kaynak"], "kaynakAdi": SOURCES.get(n["kaynak"]), "tarih": n.get("tarih"),
                       "etiket": n["etiket"],
                       "etiketAdi": LABELS.get(n["etiket"] or "", "Belirsiz" if n["yontem"] == "emin-degil" else "Sınıflanmadı"),
                       "yontem": n["yontem"], "olasilik": n["olasilik"]} for n in last],
        "ozet": ({"metin": s.metin, "kaynak": s.kaynak, "dusen": s.dusen, "zaman": s.zaman.isoformat() if s.zaman else None,
                  "guncel": s.girdi == girdi} if s else None),
        "kuralOzeti": rule_summary(counts, last, f"Son {st['windowDays']} günün notlarında"),
        "not": "Bilgi amaçlıdır; hiçbir skora ya da önceliğe girmez.",
    }


def write_summary(engine: sa.engine.Engine, tenant: str, code: str, notes: list[dict[str, Any]], llm: Any, st: dict[str, Any],
                  names: Iterable[str] = (), force: bool = False) -> dict[str, Any]:
    """Son 5 notun iki cümlelik özeti (`notes` metinli: portal + o carinin CRM notları). Girdi değişmediyse model
    çağrılmaz. Denetim `guard.check` (kaynaksız rakam, teknoloji adı, alıntı); iki cümleden fazlası kesilir; cümle
    kalmazsa kural özeti."""
    ensure(engine)
    rows = signal_rows(engine, tenant, code)
    mine = [n for n in notes if n["cari"] == code]
    last = _last(mine)
    girdi = summary_input(last, rows)
    with engine.connect() as c:
        cur = c.execute(sa.select(SUMMARIES).where(SUMMARIES.c.tenant_id == tenant, SUMMARIES.c.cari_kodu == code)).first()
    # Kural özeti, model sonradan bağlanınca yeniden denenir; model özeti girdi değişmedikçe yeniden yazılmaz.
    if cur is not None and cur.girdi == girdi and not force and not (cur.kaynak == "kural" and llm is not None):
        return {"metin": cur.metin, "kaynak": cur.kaynak, "dusen": cur.dusen, "onbellek": True}
    names = list(names)
    texts = [mask(n.get("metin"), names) for n in last]
    dated = [f"- {n.get('tarih') or 'tarihsiz'}: {t[:700]}" for n, t in zip(last, texts) if t]
    metin, kaynak, dusen = None, "kural", 0
    if dated and llm is not None:
        raw = str(llm.chat([{"role": "system", "content": SUMMARY_SYSTEM},
                            {"role": "user", "content": SUMMARY_PROMPT.format(notlar="\n".join(dated))}], max_tokens=220) or "")
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        res = G.check(raw, texts, [n.get("tarih") or "" for n in last])
        dusen = res["dusenSayisi"]
        sents = [x for x in re.split(r"(?<=[.!?…])\s+", res["metin"].replace("\n", " ")) if x.strip()]
        if sents:
            metin, kaynak = " ".join(sents[:2]), "zeki"
    if metin is None:
        enriched = _enrich(last, rows)
        counts, _b = _counts(enriched, "")
        metin = rule_summary(counts, enriched, f"Son {len(enriched)} notta")
    with engine.begin() as c:
        c.execute(SUMMARIES.delete().where(SUMMARIES.c.tenant_id == tenant, SUMMARIES.c.cari_kodu == code))
        c.execute(SUMMARIES.insert().values(tenant_id=tenant, cari_kodu=code, girdi=girdi, metin=metin, kaynak=kaynak, dusen=dusen,
                                            zaman=now()))
    return {"metin": metin, "kaynak": kaynak, "dusen": dusen, "onbellek": False}


def meta(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Son gece turunun raporu (özet tablosunda ayrı satır tutulmaz; SIGNALS'tan sayılır)."""
    ensure(engine)
    with engine.connect() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(SIGNALS).where(SIGNALS.c.tenant_id == tenant)).scalar() or 0
        last = c.execute(sa.select(sa.func.max(SIGNALS.c.siniflama)).where(SIGNALS.c.tenant_id == tenant)).scalar()
    return {"etiketli": int(n), "son": last.isoformat() if last else None}


def dump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)
