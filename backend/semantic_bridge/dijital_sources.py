"""M36 Dijital yayın ve e-kitap: CRM, Logo ve Kitap Tasarım Stüdyosu okumaları (yalnız okuma).

**CRM** (canlı 192.168.0.28, `connector_from_file`; hiçbir yazma yok):
- Kitap kartı `new_kitapBase` (etkin): stok kodu, ISBN/barkod, **dijital kimlik** (`new_ekitapisbn` e-ISBN,
  `new_EKitapBarkod`, `new_EKitapStokKodu`), `new_EPubDurumu` (bit, 1 = Evet), `new_Tip` (1 Kitap, 8 Ekitap,
  9 SesliKitap; etiket StringMap'ten), yayıncılık durumu, hedef kitle, türler, KDV dahil liste fiyatı.
- Sözleşme hakları: SEO/GEO'nun okuması aynen (`seo_geo.crm.contract_sql`, `party_sql`): yalnız **Telif Alış**
  (`new_SozlesmeTipi = 5`); e-kitap `new_EKitap`, sesli `new_SesliKitapHakki`, Z-kitap, iletim, serbest metin hak notu
  `new_haklaraciklama`, koruma dışı eser. Telif Satış (1) Timaş'ın hakkı sattığı sözleşmedir, hak kontrolüne girmez.
- Sözleşme düzeyi sayılar (kabul 2 ve 7 ile birebir): yürürlük durumundaki Telif Alış sözleşmelerinde e-kitap/sesli/
  iletim hakkı ve hak notu olan sözleşme sayısı — kitaba bağlı olmayan sözleşmeler dahil.
- Üretim kartı `new_UretimBase`: e-kitap aşamaları (`statuscode` 100000011 «Grafik Aşamasında (Ekitap)», 100000012
  «Doküman Hazır (Ekitap)»), kitap başına en son değişen kart.
- Kitap geçmişi `new_kitapgecmisi`: baskı sayısı ve kapak adresi; yeni baskı / kapak değişikliği tespiti.

**Logo** (yıllar ayrı firma numarası; `budget_sources.firms_by_year`): faturalı satış satırı (`STLINE`, `LINETYPE 0`,
`CANCELLED 0`, `INVOICEREF <> 0`, `TRCODE 7/8/9` satış, `2/3` iade eksi; net = `VATMATRAH` (KDV matrahı, fatura geneli
iskonto dahil; dönem fatura tarihi `INVOICE.DATE_` — karar 2026-10-01)). Satış görünümleri
(`V_SatisRaporu_*`) okunmaz: tanım kokpit ve bütçeyle aynı olsun diye doğrudan `STLINE`. Son 12 ay veri sonundan
geriye sayılır (pencere ekranda yazılır). E-kitap stok kodlarının
satışı aynı sorgudan çıkar (kod listesi SQL'e girmez, plan tuzağı yok).

**Stüdyo** (isteğe bağlı): iş listesi + işin e-kitap görünümü (`editorial_studio_epub.view`), CRM kitap kimliğiyle.
Stüdyo kapalıysa okuma boş döner, katalog yine kurulur.

**M54 hak haritası bağlantı noktası:** telif modülü (`royalty*.py`, `/api/v1/rights/*`) kitap × biçim hak kararını
verince `register_rights_provider(fn)` ile bağlanır; `fn(kitap_idleri, bicim) → {kitap_id: (karar, gerekce)}`.
Bağlıysa kararı o verir (kaynak ekranda «telif hak haritası»), bağlı değilse bu modülün CRM okuması.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.editorial import ACTIVE_STATUS, _prefix
from semantic_bridge.seo_geo import crm as seo_crm

log = logging.getLogger("semantic.dijital.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year

ALIS = seo_crm.ALIS
EBOOK_STAGES = {100000011: "Grafik aşamasında (e-kitap)", 100000012: "Doküman hazır (e-kitap)"}


def prefix(schema: str) -> str:
    try:
        return _prefix(schema)
    except Exception as e:  # noqa: BLE001 — EditorialError: şema adı geçersiz
        raise SourceError(str(e)) from None


def _clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def _num(v: Any) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def _day(v: Any) -> Optional[date]:
    return bsrc._day(v)


def isbn_key(v: Any) -> str:
    """ISBN/EAN karşılaştırma anahtarı: yalnız rakam (ve ISBN-10 sonundaki X); 8 haneden kısaysa boş."""
    s = re.sub(r"[^0-9X]", "", str(v or "").upper())
    return s if len(s) >= 8 else ""


def code_key(v: Any) -> str:
    """Stok kodu anahtarı: büyük harf, boşluksuz."""
    return re.sub(r"\s+", "", str(v or "").upper())


# ------------------------------------------------------------------ CRM SQL


def books_sql(p: str) -> str:
    """Etkin kitap kartları ve dijital kimlik alanları. İç yazışma ve kişisel alan seçilmez."""
    return (
        "SELECT k.new_kitapId AS id, k.new_name AS ad, k.new_StokKodu AS stok_kodu, k.new_isbn13 AS isbn,"
        " k.new_ean13 AS ean, k.new_ekitapisbn AS e_isbn, k.new_EKitapBarkod AS ekitap_barkod,"
        " k.new_EKitapStokKodu AS ekitap_stok_kodu, CAST(ISNULL(k.new_EPubDurumu, 0) AS int) AS epub,"
        " k.new_Tip AS tip, k.new_kitap_yayincilikstatusu AS yayin_durumu, k.new_hedefkitle AS hedef_kitle,"
        " k.new_yazartext AS yazar, k.new_turlertext AS turler, k.new_kdvdahilfiyat AS basili_fiyat,"
        " k.new_ilkyayintarihi AS ilk_yayin"
        f" FROM {p}new_kitapBase k WHERE k.statecode = 0"
    )


def contract_counts_sql(p: str) -> str:
    """Sözleşme düzeyi sayılar (kabul 2 ve 7): yürürlük durumundaki Telif Alış sözleşmeleri; hak notu bütün durumlarda."""
    st = ", ".join(str(s) for s in ACTIVE_STATUS)
    return (
        f"SELECT SUM(CASE WHEN s.statuscode IN ({st}) THEN 1 ELSE 0 END) AS yururlukte,"
        f" SUM(CASE WHEN s.statuscode IN ({st}) AND s.new_EKitap = 1 THEN 1 ELSE 0 END) AS ekitap,"
        f" SUM(CASE WHEN s.statuscode IN ({st}) AND s.new_SesliKitapHakki = 1 THEN 1 ELSE 0 END) AS sesli,"
        f" SUM(CASE WHEN s.statuscode IN ({st}) AND s.new_iletimhakki = 1 THEN 1 ELSE 0 END) AS iletim,"
        " SUM(CASE WHEN ISNULL(s.new_haklaraciklama, '') <> '' THEN 1 ELSE 0 END) AS notlu"
        f" FROM {p}new_sozlesmeBase s WHERE s.new_SozlesmeTipi = {ALIS}"
    )


def production_sql(p: str) -> str:
    codes = ", ".join(str(c) for c in EBOOK_STAGES)
    return (f"SELECT u.new_kitapid AS kitap_id, u.statuscode AS durum, u.ModifiedOn AS tarih"
            f" FROM {p}new_UretimBase u WHERE u.new_kitapid IS NOT NULL AND u.statuscode IN ({codes})")


def history_sql(p: str, since: date) -> str:
    """Kitap geçmişi: baskı sayısı ve kapak adresi. Karşılaştırma için pencereden önceki son satır da gerekir;
    pencere + bir önceki satır kodda seçilir, burada pencerenin bir yıl öncesinden okunur."""
    start = since - timedelta(days=365)
    return (f"SELECT g.new_kitapid AS kitap_id, g.new_baskisayisi AS baski, g.new_kapakurl AS kapak, g.CreatedOn AS tarih"
            f" FROM {p}new_kitapgecmisiBase g WHERE g.statecode = 0 AND g.new_kitapid IS NOT NULL"
            f" AND g.CreatedOn >= '{start.isoformat()}'")


# ------------------------------------------------------------------ Logo SQL


def sales_sql(firm: str, start: date, end: date) -> str:
    """Stok kodu × ay faturalı net adet ve net ciro, [start, end). İade eksi."""
    return f"""
-- Faturalı satış satırları; iade eksi. Net ciro = VATMATRAH.
SELECT I.CODE AS stok_kodu, YEAR(SH.DATE_) AS yil, MONTH(SH.DATE_) AS ay,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE -S.VATMATRAH END) AS ciro
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_01_INVOICE AS SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND SH.DATE_ >= '{start.isoformat()}' AND SH.DATE_ < '{end.isoformat()}'
GROUP BY I.CODE, YEAR(SH.DATE_), MONTH(SH.DATE_)""".strip()


# ------------------------------------------------------------------ çalışan sorgunun etiketi (sorgu bilgisi)


def query_tag(sql: str) -> str:
    """Okumada çalışan SQL'in hangi okuma olduğu (yukarıdaki üreticilerin ayırt edici parçalarından). Logo satışında
    firma ve pencere başı da etikete girer: `logo.satis.<firma>.<YYYY-AA-GG>`."""
    s = sql or ""
    if "L_CAPIPERIOD" in s:
        return "logo.donem"
    if "MAX(DATE_)" in s:
        return "logo.verisonu"
    m = re.search(r"LG_(\d+)_01_STLINE", s)
    if m:
        d = re.search(r"DATE_ >= '(\d{4}-\d{2}-\d{2})'", s)
        return f"logo.satis.{m.group(1)}.{d.group(1) if d else ''}".rstrip(".")
    if "StringMap" in s:
        a = re.search(r"AttributeName = '(\w+)'", s)
        return f"crm.etiket.{a.group(1) if a else ''}".rstrip(".")
    if "new_kitapgecmisiBase" in s:
        return "crm.gecmis"
    if "new_UretimBase" in s:
        return "crm.uretim"
    if "new_sozlesmetarafiBase" in s:
        return "crm.taraflar"
    if "AS yururlukte" in s:
        return "crm.sozlesmeSayilari"
    if "new_new_sozlesme_new_kitapBase" in s:
        return "crm.sozlesmeler"
    if "new_kitapBase" in s:
        return "crm.kitaplar"
    return "diger"


# ------------------------------------------------------------------ okuma: CRM


def _labels(crm: Runner, p: str, attribute: str, entity: str = "new_kitap") -> dict[int, str]:
    try:
        return {int(r["v"]): str(r["l"]) for r in crm(seo_crm.label_sql(p, attribute, entity)) if r.get("v") is not None}
    except SourceError as e:
        log.info("dijital: %s etiketleri okunamadı: %s", attribute, e)
        return {}


def read_crm(crm: Runner, schema: str) -> dict[str, Any]:
    """Kitaplar, kitaba bağlı Telif Alış sözleşmeleri (taraflarıyla), sözleşme sayıları, e-kitap üretim aşaması."""
    p = prefix(schema)
    kinds = _labels(crm, p, "new_tip")
    status = _labels(crm, p, "new_kitap_yayincilikstatusu")
    audience = _labels(crm, p, "new_hedefkitle")
    books = []
    for r in crm(books_sql(p)):
        tip = int(r["tip"]) if r.get("tip") is not None else None
        ys = int(r["yayin_durumu"]) if r.get("yayin_durumu") is not None else None
        hk = int(r["hedef_kitle"]) if r.get("hedef_kitle") is not None else None
        books.append({
            "kitap_id": str(r["id"]).upper(), "ad": _clean(r.get("ad")), "stok_kodu": _clean(r.get("stok_kodu")),
            "isbn": _clean(r.get("isbn")), "ean": _clean(r.get("ean")), "e_isbn": _clean(r.get("e_isbn")),
            "ekitap_barkod": _clean(r.get("ekitap_barkod")), "ekitap_stok_kodu": _clean(r.get("ekitap_stok_kodu")),
            "epub_crm": int(r.get("epub") or 0), "tip": tip, "tip_adi": kinds.get(tip) if tip is not None else None,
            "yayin_durumu": status.get(ys) if ys is not None else None,
            "hedef_kitle": audience.get(hk) if hk is not None else None,
            "yazar": _clean(r.get("yazar")), "turler": _clean(r.get("turler")),
            "basili_fiyat": _num(r.get("basili_fiyat")),
            "ilk_yayin": (_day(r.get("ilk_yayin")).isoformat() if _day(r.get("ilk_yayin")) and _day(r.get("ilk_yayin")).year >= 1950 else None),
        })
    parties: dict[str, list[str]] = {}
    for r in crm(seo_crm.party_sql(p)):
        name = (r.get("person") or r.get("company") or "").strip()
        if name:
            parties.setdefault(str(r["contract_id"]).upper(), []).append(name)
    contracts: dict[str, list[dict[str, Any]]] = {}
    for r in crm(seo_crm.contract_sql(p)):
        cid = str(r["id"]).upper()
        contracts.setdefault(str(r["book_id"]).upper(), []).append({**r, "id": cid, "parties": parties.get(cid, [])})
    counts_rows = crm(contract_counts_sql(p))
    counts = {k: int((counts_rows[0] if counts_rows else {}).get(k) or 0) for k in ("yururlukte", "ekitap", "sesli", "iletim", "notlu")}
    production: dict[str, dict[str, Any]] = {}
    try:
        for r in crm(production_sql(p)):
            kid = str(r["kitap_id"]).upper()
            d = _day(r.get("tarih"))
            cur = production.get(kid)
            if cur is None or (d and (cur["tarih"] or "") < d.isoformat()):
                production[kid] = {"durum": EBOOK_STAGES.get(int(r["durum"])), "tarih": d.isoformat() if d else None}
    except SourceError as e:
        log.info("dijital: üretim aşaması okunamadı: %s", e)
    return {"books": books, "contracts": contracts, "counts": counts, "production": production}


def read_history(crm: Runner, schema: str, since: date) -> dict[str, list[dict[str, Any]]]:
    """Kitap → [{tarih, baski, kapak}] (eskiden yeniye)."""
    out: dict[str, list[dict[str, Any]]] = {}
    for r in crm(history_sql(prefix(schema), since)):
        d = _day(r.get("tarih"))
        if not d:
            continue
        out.setdefault(str(r["kitap_id"]).upper(), []).append(
            {"tarih": d.isoformat(), "baski": int(r["baski"]) if r.get("baski") is not None else None, "kapak": _clean(r.get("kapak"))})
    for v in out.values():
        v.sort(key=lambda x: x["tarih"])
    return out


# ------------------------------------------------------------------ okuma: Logo


def data_end(logo: Runner, firms: dict[int, str]) -> Optional[date]:
    if not firms:
        raise SourceError("Logo'da dönem tanımı okunamadı.")
    return bsrc.read_data_end(logo, firms)


def window12(end: date) -> tuple[date, date]:
    """Veri sonunun ayı dahil son 12 takvim ayı: [ayın 1'i, veri sonu + 1 gün). Kabuldeki `Yıl*12+Ay` aralığıyla aynı."""
    y, m = end.year, end.month - 11
    if m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1), end + timedelta(days=1)


def read_sales(logo: Runner, firms: dict[int, str], start: date, stop: date) -> list[dict[str, Any]]:
    """Pencere içindeki her yılın firmasından stok kodu × ay satış."""
    out: list[dict[str, Any]] = []
    for year in range(start.year, stop.year + 1):
        firm = firms.get(year)
        if not firm:
            continue
        a = max(start, date(year, 1, 1))
        b = min(stop, date(year + 1, 1, 1))
        if a >= b:
            continue
        for r in logo(sales_sql(firm, a, b)):
            code = _clean(r.get("stok_kodu"))
            if code:
                out.append({"stok_kodu": code, "ay": f"{int(r['yil']):04d}-{int(r['ay']):02d}",
                            "adet": float(r.get("adet") or 0), "ciro": float(r.get("ciro") or 0)})
    return out


# ------------------------------------------------------------------ okuma: stüdyo


def read_studio(jobs: Optional[Callable[[], Any]], view: Optional[Callable[[str], dict]]) -> Optional[dict[str, dict[str, Any]]]:
    """CRM kitap kimliği → stüdyodaki en yeni işin e-kitap durumu. Stüdyo bağlı değilse ya da okunamazsa None
    (katalog yine kurulur, stüdyo kolonları bir önceki okumadan kalır)."""
    if not jobs:
        return None
    try:
        data = jobs()
    except Exception as e:  # noqa: BLE001 — stüdyo kapalıysa katalog yine kurulur
        log.info("dijital: stüdyo işleri okunamadı: %s", e)
        return None
    items = data.get("items") if isinstance(data, dict) else data
    latest: dict[str, dict[str, Any]] = {}
    for j in items or []:
        kid = str((j.get("source") or {}).get("crm_book_id") or "").upper()
        if not kid:
            continue
        if kid not in latest or (j.get("created_at") or 0) > (latest[kid].get("created_at") or 0):
            latest[kid] = j
    out: dict[str, dict[str, Any]] = {}
    for kid, j in latest.items():
        st: dict[str, Any] = {"is": j.get("id"), "durum": "is_var", "denetim": None, "e_isbn": None}
        if view is not None:
            try:
                v = view(str(j.get("id"))) or {}
                st.update(studio_state(v))
            except Exception as e:  # noqa: BLE001
                log.info("dijital: stüdyo e-kitap durumu okunamadı (%s): %s", j.get("id"), e)
        out[kid] = st
    return out


def studio_state(v: dict[str, Any]) -> dict[str, Any]:
    """Stüdyonun e-kitap görünümünden özet: yok / hazırlanıyor / hazır (denetim sonucu) / eski / hata."""
    status = str(v.get("status") or "none")
    check = v.get("check") or {}
    res = v.get("result") or {}
    eisbn = res.get("eisbn") or (v.get("meta") or {}).get("eisbn")
    if status == "done":
        durum = "eski" if v.get("stale") else "hazir"
    elif status in ("running", "queued"):
        durum = "hazirlaniyor"
    elif status == "error":
        durum = "hata"
    else:
        durum = "is_var"
    return {"durum": durum, "denetim": check.get("status") if status == "done" else None, "e_isbn": _clean(eisbn)}


# ------------------------------------------------------------------ M54 hak haritası (bağlantı noktası)


RightsProvider = Callable[[list[str], str], dict[str, tuple[str, str]]]
_rights_provider: dict[str, Optional[RightsProvider]] = {"fn": None}


def register_rights_provider(fn: Optional[RightsProvider]) -> None:
    """M54 telif modülü main'e girince app.py'de bağlanır. None bağı kaldırır."""
    _rights_provider["fn"] = fn


def external_rights(ids: Iterable[str], bicim: str) -> Optional[dict[str, tuple[str, str]]]:
    fn = _rights_provider["fn"]
    if fn is None:
        return None
    try:
        return {str(k).upper(): v for k, v in (fn(list(ids), bicim) or {}).items()}
    except Exception as e:  # noqa: BLE001 — hak haritası okunamazsa CRM okumasına düşülür, ekranda yazılır
        log.warning("dijital: telif hak haritası okunamadı: %s", e)
        return None
