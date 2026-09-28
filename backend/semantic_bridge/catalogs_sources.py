"""M24 Katalog ve bülten: kaynakların okunması (yalnız okuma — CRM'e, Logo'ya ve T-soft'a yazılmaz).

**Kitap havuzu (CRM `new_kitapBase`, .28 prod):** etkin kart (`statecode = 0`) ve tipi `CATALOG_BOOK_TYPES`
(varsayılan `1,4` = Kitap ve Set; katalogda setler de satılır). Künye, marka (`new_markaBase`), Kitaplık, tür metni,
hedef kitle (seçenek; Türkçe etiketi `StringMap`'ten), yaş aralığı, ilk baskı tarihi, yayıncılık statüsü (etiketi
`StringMap`'ten; «YS01 İptal», «YS11 Çekildi»… SEO «Haklar ve CRM» ile aynı sınıflama `seo_geo.crm.status_flag`),
satış durumu (`new_satisdurumu`, boşsa açık sayılır — doluluğu **ölçülecek**), iki fiyat alanı (`new_kdvdahilfiyat`,
`new_PerakendeBirimFiyat`), kapak bağlantısı (`new_resimurl`, yoksa `new_kapakresmi`). Uzun metinler (kısa bilgi, özet)
toplu okumada alınmaz; yalnız uzunlukları gelir, metin kitap başına okunur (`texts_sql`).

**Stok ve satış hızı = Yönetim raporları › Baskı önerisi tanımı, aynı SQL dosyalarıyla** (`management/sql/baski_oneri`):
satış hızı `logo_satis_hizi.sql` (ağırlıklı aylık adet), stok adedi `crm_kitap.sql` (CRM `powerbikitap.StokAdedi`),
Logo depo stoku `logo_depo_stok.sql`, son satış birim fiyatı `logo_fiyat.sql`. Stok ay sayısı = stok ÷ satış hızı —
Baskı Tekrar'daki «Tükenme süresi» ile aynı formül; stokun kaynağı `CATALOG_STOCK_SOURCE` (crm = Baskı önerisi, logo =
depo stoku). Satış görünümleri yalnız gereken yılların yıllık görünümlerinden okunur (`management.expand_sales`).

**Özel gün bağı:** SEO Sezon takviminin CRM okuması (`seo_geo.seasons.read_crm`: `new_ozelgunlerBase` +
`new_new_kitap_new_ozelgunlerBase`); tarih aynı modülün kuralıyla (`resolve`, `next_occurrence`).

**Telif notu:** yürürlükteki Telif Alış sözleşmesinde `new_haklaraciklama` doluysa kapak/metin kullanımı için uyarı
(`seo_geo.crm.contract_sql`, `in_force`).

**T-soft:** doğrudan çağrılmaz; SEO modülünün eşitlediği ürünlerden (`semantic_seo_products.data_json`) barkodla fiyat,
görsel ve ürün adresi.

**Kampanya sonuçları:** CRM `CampaignBase` sayaçları ve `obs_kampanyagonderimleriBase`'in kampanya başına toplamları.
Kişi kimliği, adı ya da e-posta adresi hiçbir sorguda seçilmez.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc

log = logging.getLogger("semantic.catalogs.sources")

SourceError = bsrc.SourceError
Runner = Callable[[str], list[dict[str, Any]]]
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year

GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")
CHUNK = 800


def prefix(schema: str) -> str:
    from semantic_bridge.editorial import _prefix

    return _prefix(schema)


def q(v: Any) -> str:
    return "'" + str(v).replace("'", "''") + "'"


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


def _day(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v)[:10]
    try:
        return date.fromisoformat(s).isoformat()
    except ValueError:
        return None


def _chunks(items: list[str], n: int = CHUNK) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


# ------------------------------------------------------------------ CRM kitap havuzu


def pool_sql(p: str, types: list[int]) -> str:
    tips = ", ".join(str(int(t)) for t in types) or "1"
    return (
        "SELECT k.new_kitapId AS id, k.new_StokKodu AS stok, k.new_name AS ad, k.new_yazartext AS yazar, m.new_name AS marka,"
        " k.new_isbn13 AS isbn, k.new_ean13 AS ean, k.new_kitap_yayincilikstatusu AS yst,"
        " CAST(k.new_satisdurumu AS int) AS satis_durumu, k.new_Tip AS tip, k.new_hedefkitle AS hedef,"
        " k.new_hedefkitleyasbaslangic AS yas_bas, k.new_hedefkitleyasbitis AS yas_bit, k.new_turlertext AS tur,"
        " kl.new_name AS kitaplik, k.new_webkategorileritext AS web, k.new_ilkyayintarihi AS ilk_yayin,"
        " k.new_kdvdahilfiyat AS fiyat_kdv, k.new_PerakendeBirimFiyat AS fiyat_perakende,"
        " k.new_resimurl AS kapak_url, k.new_kapakresmi AS kapak_dosya,"
        " DATALENGTH(k.new_kisabilgi) AS kisa_len, DATALENGTH(k.new_ozet) AS ozet_len"
        f" FROM {p}new_kitapBase k"
        f" LEFT JOIN {p}new_markaBase m ON m.new_markaId = k.new_yayineviid"
        f" LEFT JOIN {p}new_kitaplikBase kl ON kl.new_kitaplikId = k.new_kitaplikid"
        f" WHERE k.statecode = 0 AND k.new_Tip IN ({tips})"
    )


def texts_sql(p: str, ids: list[str]) -> str:
    """Kitap başına tanıtım metinleri (kısa bilgi, özet). Kimlikler GUID olarak doğrulanmış olmalı."""
    ids = [i for i in ids if GUID.match(str(i))]
    return ("SELECT k.new_kitapId AS id, LEFT(k.new_kisabilgi, 4000) AS kisa, LEFT(k.new_ozet, 6000) AS ozet"
            f" FROM {p}new_kitapBase k WHERE k.new_kitapId IN ({', '.join(q(i) for i in ids) or q('')})")


def read_labels(p: str, run: Runner, attribute: str) -> dict[int, str]:
    from semantic_bridge.seo_geo.crm import label_sql

    out: dict[int, str] = {}
    for r in run(label_sql(p, attribute)):
        try:
            out[int(r["v"])] = str(r["l"]).strip()
        except (TypeError, ValueError, KeyError):
            continue
    return out


def read_pool_crm(crm: Runner, schema: str, types: list[int]) -> dict[str, Any]:
    from semantic_bridge.seo_geo.crm import status_flag

    p = prefix(schema)
    yst = read_labels(p, crm, "new_kitap_yayincilikstatusu")
    hedef = read_labels(p, crm, "new_hedefkitle")
    books = []
    for r in crm(pool_sql(p, types)):
        label = yst.get(int(r["yst"])) if r.get("yst") is not None else None
        kapak = _clean(r.get("kapak_url")) or _clean(r.get("kapak_dosya"))
        books.append({
            "id": str(r["id"]).lower(), "stok": _clean(r.get("stok")), "ad": _clean(r.get("ad")), "yazar": _clean(r.get("yazar")),
            "marka": _clean(r.get("marka")), "isbn": _clean(r.get("isbn")), "ean": re.sub(r"\D", "", str(r.get("ean") or "")) or None,
            "yst": label, "flag": status_flag(label),
            "satisAcik": r.get("satis_durumu") is None or int(r.get("satis_durumu") or 0) == 1,
            "tip": int(r["tip"]) if r.get("tip") is not None else None,
            "hedef": hedef.get(int(r["hedef"])) if r.get("hedef") is not None else None,
            "yasBas": _num(r.get("yas_bas")), "yasBit": _num(r.get("yas_bit")),
            "tur": _clean(r.get("tur")), "kitaplik": _clean(r.get("kitaplik")), "web": _clean(r.get("web")),
            "ilkYayin": _day(r.get("ilk_yayin")),
            "fiyatlar": {"crm": _num(r.get("fiyat_kdv")), "crm-perakende": _num(r.get("fiyat_perakende"))},
            "kapak": kapak if kapak and kapak.lower().startswith(("http://", "https://")) else None,
            "kapakDosya": kapak if kapak and not kapak.lower().startswith(("http://", "https://")) else None,
            "metinVar": bool((r.get("kisa_len") or 0) > 0 or (r.get("ozet_len") or 0) > 0),
        })
    return {"books": books, "hedefler": sorted(set(hedef.values()))}


def read_texts(crm: Runner, schema: str, ids: list[str]) -> dict[str, dict[str, Optional[str]]]:
    from semantic_bridge.seo_geo.crm import clean

    out: dict[str, dict[str, Optional[str]]] = {}
    ids = [i for i in dict.fromkeys(ids) if GUID.match(str(i))]
    for part in _chunks(ids, 400):
        for r in crm(texts_sql(prefix(schema), part)):
            out[str(r["id"]).lower()] = {"kisa": clean(r.get("kisa")), "ozet": clean(r.get("ozet"))}
    return out


# ------------------------------------------------------------------ özel gün ve telif notu


def read_special_days(crm: Runner, schema: str, today: date) -> list[dict[str, Any]]:
    """Özel günler (aynı ad birleşik), bir sonraki tarihi ve bağlı CRM kitap kimlikleri."""
    from semantic_bridge.seo_geo import seasons

    def execute(sql: str, limit: int):
        return None, crm(sql), False

    days, books = seasons.read_crm(schema, execute)
    out = []
    for d in days:
        how = seasons.resolve(d)
        nxt = None
        try:
            nxt = seasons.next_occurrence(how, today) if how["method"] != "unknown" else None
        except Exception:  # noqa: BLE001 — tarih çözülemezse gün yine listede, tarihsiz
            nxt = None
        out.append({"key": d["key"], "ad": d["name"], "baslangic": nxt[0].isoformat() if nxt else None,
                    "bitis": nxt[1].isoformat() if nxt else None, "tarihNeden": how.get("why"),
                    "kitaplar": sorted({str(b["bookId"]).lower() for b in books.get(d["key"], [])})})
    return sorted(out, key=lambda x: (x["baslangic"] is None, x["baslangic"] or "", x["ad"]))


def read_rights_notes(crm: Runner, schema: str, today: date) -> set[str]:
    """Yürürlükte bir Telif Alış sözleşmesinde hak notu olan kitaplar (kapak/metin kullanımı sözleşmeye bağlı)."""
    from semantic_bridge.seo_geo import crm as scrm

    out: set[str] = set()
    for r in crm(scrm.contract_sql(prefix(schema))):
        if (r.get("rights_note") or "").strip() and scrm.in_force(r, today):
            out.add(str(r["book_id"]).lower())
    return out


# ------------------------------------------------------------------ Logo: Baskı önerisi tanımı


def _sales_views(logo: Runner) -> set[int]:
    return {int(str(r["name"])[-4:]) for r in logo("SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'")}


def baski_sql(source_id: str, today: date, years: Optional[set[int]]) -> tuple[str, list[int]]:
    """Baskı önerisi raporunun kaynak SQL'i, satış yer tutucusu yıllık görünümlere açılmış olarak."""
    from semantic_bridge import management as M

    text = M.sql_text("baski-oneri", source_id)
    if M._SALES_PLACEHOLDER.search(text):
        return M.expand_sales(text, today, years)
    return text, []


def read_stock_speed(logo: Runner, crm: Runner, today: date) -> dict[str, Any]:
    """Stok kodu → {stok (CRM), depo (Logo), hiz, yillik}; ayrıca Logo son satış birim fiyatı. Hata notlara düşer."""
    notes: list[str] = []
    out: dict[str, dict[str, Any]] = {}
    years: Optional[set[int]] = None
    try:
        years = _sales_views(logo)
    except SourceError as e:
        notes.append(f"Logo satış görünümleri okunamadı ({e}).")
    if years is not None:
        try:
            sql, missing = baski_sql("logo_satis_hizi", today, years)
            if missing:
                notes.append(f"Logo'da {', '.join(map(str, missing))} satış görünümü yok; bu yıllar okunmadı.")
            for r in logo(sql):
                k = str(r.get("stok_kodu") or "").strip()
                if k:
                    out.setdefault(k, {})
                    out[k]["hiz"] = float(r.get("satis_hizi") or 0)
                    out[k]["yillik"] = float(r.get("yillik_toplam") or 0)
        except (SourceError, RuntimeError) as e:
            notes.append(f"Satış hızı okunamadı ({e}); stok ay sayısı hesaplanmadı.")
        try:
            sql, _ = baski_sql("logo_fiyat", today, years)
            for r in logo(sql):
                k = str(r.get("stok_kodu") or "").strip()
                if k:
                    out.setdefault(k, {})
                    out[k]["logoFiyat"] = _num(r.get("birim_fiyat"))
                    out[k]["logoFiyatTarihi"] = _day(r.get("son_fiyat_degisikligi"))
        except (SourceError, RuntimeError) as e:
            notes.append(f"Logo son satış fiyatı okunamadı ({e}).")
    try:
        sql, _ = baski_sql("logo_depo_stok", today, None)
        for r in logo(sql):
            k = str(r.get("stok_kodu") or "").strip()
            if k:
                out.setdefault(k, {})["depo"] = _num(r.get("depo_stok"))
    except (SourceError, RuntimeError) as e:
        notes.append(f"Logo depo stoku okunamadı ({e}).")
    try:
        sql, _ = baski_sql("crm_kitap", today, None)
        for r in crm(sql):
            k = str(r.get("stok_kodu") or "").strip()
            if not k:
                continue
            row = out.setdefault(k, {})
            if row.get("stok") is None and r.get("stok_adedi") not in (None, ""):
                row["stok"] = _num(r.get("stok_adedi"))
            if row.get("uzeri") is None and r.get("uzeri_fiyat") not in (None, ""):
                row["uzeri"] = _num(r.get("uzeri_fiyat"))
    except (SourceError, RuntimeError) as e:
        notes.append(f"CRM stok adedi okunamadı ({e}).")
    return {"byCode": out, "notes": notes}


def logo_data_end(logo: Runner) -> Optional[str]:
    """Logo'daki son faturalı satış satırının tarihi (donmuş kopyada stok ve satış bu güne kadardır)."""
    firms = firms_by_year(logo)
    if not firms:
        return None
    firm = firms[max(firms)]
    rows = logo(f"SELECT MAX(DATE_) AS son FROM dbo.LG_{firm}_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 "
                f"AND INVOICEREF <> 0 AND TRCODE IN (7,8,9)")
    return _day(rows[0].get("son")) if rows else None


# ------------------------------------------------------------------ T-soft (SEO deposundan)


def read_tsoft(engine, tenant: str, site: str = "") -> dict[str, dict[str, Any]]:
    """Barkod → {fiyat (KDV dahil), gorsel, url}. SEO modülü kurulu değilse boş."""
    import sqlalchemy as sa

    try:
        t = sa.Table("semantic_seo_products", sa.MetaData(), autoload_with=engine)
    except Exception:  # noqa: BLE001 — tablo yok
        return {}
    out: dict[str, dict[str, Any]] = {}
    with engine.connect() as c:
        for r in c.execute(sa.select(t.c.data_json).where(t.c.tenant_id == tenant)):
            try:
                d = json.loads(r.data_json or "{}")
            except ValueError:
                continue
            ean = re.sub(r"\D", "", str(d.get("Barcode") or ""))
            if len(ean) < 8:
                continue
            price = next((_num(d.get(k)) for k in ("SellingPriceVatIncluded", "SellingPrice") if _num(d.get(k)) is not None), None)
            imgs = d.get("ImageUrls") or []
            img = None
            if imgs and isinstance(imgs[0], dict):
                img = imgs[0].get("Medium") or imgs[0].get("Small") or imgs[0].get("ImageUrl")
            link = str(d.get("SeoLink") or "").strip().lstrip("/")
            url = f"{site.rstrip('/')}/{link}" if site and link else None
            out[ean] = {"fiyat": price, "gorsel": img if img and str(img).startswith("http") else None, "url": url}
    return out


# ------------------------------------------------------------------ CRM kampanya sonuçları ve ilgi alanları


def campaigns_sql(p: str) -> str:
    return ("SELECT CampaignId AS id, Name AS ad, TypeCode AS tur, StateCode AS durum, StatusCode AS alt_durum,"
            " ActualStart AS baslangic, ActualEnd AS bitis, CreatedOn AS olusturma,"
            " obs_totalcount AS toplam, obs_sentcount AS okunmayan, obs_readcount AS okunan, obs_clickcount AS tiklanan,"
            " obs_blacklistcount AS kara_liste"
            f" FROM {p}CampaignBase")


def sends_sql(p: str) -> str:
    """Kampanya başına gönderim toplamları; kişi kolonları seçilmez."""
    return ("SELECT obs_kampanyaid AS kampanya, COUNT(*) AS gonderim,"
            " SUM(CASE WHEN obs_okunmadurumu = 1 THEN 1 ELSE 0 END) AS okunan,"
            " SUM(CASE WHEN obs_tiklanmadurumu = 1 THEN 1 ELSE 0 END) AS tiklanan,"
            " MAX(CreatedOn) AS son"
            f" FROM {p}obs_kampanyagonderimleriBase WHERE statecode = 0 GROUP BY obs_kampanyaid")


CAMPAIGN_TYPES = {1: "Reklam", 2: "Doğrudan pazarlama", 3: "Etkinlik", 4: "Anket", 5: "Diğer"}


def read_campaigns(crm: Runner, schema: str) -> list[dict[str, Any]]:
    p = prefix(schema)
    sends = {str(r["kampanya"]).lower(): r for r in crm(sends_sql(p)) if r.get("kampanya")}
    out = []
    for r in crm(campaigns_sql(p)):
        cid = str(r["id"]).lower()
        s = sends.get(cid) or {}
        out.append({"id": cid, "ad": _clean(r.get("ad")), "tur": CAMPAIGN_TYPES.get(int(r["tur"])) if r.get("tur") is not None else None,
                    "etkin": int(r.get("durum") or 0) == 0, "baslangic": _day(r.get("baslangic")), "bitis": _day(r.get("bitis")),
                    "olusturma": _day(r.get("olusturma")),
                    "toplam": _num(r.get("toplam")), "okunan": _num(r.get("okunan")), "tiklanan": _num(r.get("tiklanan")),
                    "karaListe": _num(r.get("kara_liste")),
                    "gonderimKaydi": int(s.get("gonderim") or 0), "gonderimOkunan": int(s.get("okunan") or 0),
                    "gonderimTiklanan": int(s.get("tiklanan") or 0), "sonGonderim": _day(s.get("son"))})
    return sorted(out, key=lambda x: x["baslangic"] or x["olusturma"] or "", reverse=True)


def campaign_counts(crm: Runner, schema: str, campaign_id: str) -> Optional[dict[str, Any]]:
    if not GUID.match(campaign_id or ""):
        return None
    rows = crm(campaigns_sql(prefix(schema)) + f" WHERE CampaignId = {q(campaign_id)}")
    if not rows:
        return None
    r = rows[0]
    return {"toplam": _num(r.get("toplam")), "okunan": _num(r.get("okunan")), "tiklanan": _num(r.get("tiklanan")),
            "karaListe": _num(r.get("kara_liste")), "ad": _clean(r.get("ad"))}


def read_interests(crm: Runner, schema: str) -> list[dict[str, Any]]:
    """CRM kitap ilgi alanları (sözlük; kişi bağları sayılmaz, yalnız ad)."""
    p = prefix(schema)
    return [{"id": str(r["id"]).lower(), "ad": _clean(r.get("ad")), "etkin": int(r.get("durum") or 0) == 0}
            for r in crm(f"SELECT new_kitapilgialanId AS id, new_name AS ad, statecode AS durum FROM {p}new_kitapilgialanBase")
            if _clean(r.get("ad"))]
