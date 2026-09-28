"""M34 E-ticaret ve platform yönetimi: okumalar (yalnız okuma).

Üç kaynak aynı kitap için yan yana okunur; hiçbirine yazılmaz.

- **Site (T-soft)** bu modülde **yeniden okunmaz.** SEO & GEO eşitlemesinin gece yazdığı `semantic_seo_products`
  (ürünün T-soft kaydı, `data_json`) ve `semantic_seo_crm_books` (CRM kitap kartı + hak ve yayın durumu özeti) meta
  veritabanından okunur. Fiyat ve stok alanının adı T-soft sürümüne göre değişir; alan seçimi Google Alışveriş
  hazırlığındaki okuyucuyla aynıdır (`seo_geo.shopping.price_of` / `stock_of`). T-soft'a hiçbir istek gitmez.
- **CRM** (`Timas_MSCRM`, .28) kendi bağlantısıyla okunur (`SEMANTIC_CRM_CONNECTION_FILE`): kitap kartı
  `new_kitapBase` — ad, EAN-13, stok kodu, `new_tsoftaktif` («TSOFT Aktif»), durum, KDV dahil fiyat
  (`new_kdvdahilfiyat`), perakende birim fiyatı ve içerik alanlarının **yalnız uzunluğu** (`DATALENGTH`). İçerik
  paketi indirilirken seçilen kitapların metni ayrıca okunur. CRM'e yazılmaz.
- **Logo** köprünün Logo bağlantısıyla, fiziksel tablo adlarıyla ve yıl firmasıyla (`L_CAPIPERIOD`; 411 = 2026,
  211 = 2021–2025); satış görünümleri (`V_SatisRaporu_*`, `ALL2`) kullanılmaz:
  - **Stok bakiyesi** güncel firma, tarih süzgeçsiz: `IOCODE 1,2` giriş − `3,4` çıkış, `LINETYPE 0`, `CANCELLED 0`;
    planlanan üretim girişi (`TRCODE 13`, `STFICHE.PRODSTAT = 1`) sayılmaz (M12/M33 ölçümüyle aynı).
  - **Satış** faturalı satır (`STLINE`, `LINETYPE 0`, `CANCELLED 0`, `INVOICEREF <> 0`), `TRCODE 7/8/9` satış,
    `2/3` iade (eksi); net ciro `LINENET` (kokpit ve bütçeyle aynı satır tanımı).
  - **Pazar yeri carisi** `CLCARD.SPECODE2` ayardaki kanal(lar) (`ECOM_CHANNELS`, varsayılan `E-TICARET`).
  - **Logo liste fiyatı** `PRCLIST` satış listesi, bugün geçerli (seçim M53 ile aynı: cariye bağlı olmayan, küçük
    öncelik, en yeni başlangıç).
  - **Kesim tarihi** güncel firmanın son satış faturası günü; ekranda her Logo rakamının yanında yazar
    (.155 kopyası 2026-08-17'de donmuş).
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import corporate_sales_sources as csrc
from semantic_bridge import sets_sources as ssrc

log = logging.getLogger("semantic.eticaret.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year
firm_ranges = csrc.firm_ranges
current_firm = csrc.current_firm
channel_list = csrc.channel_list
day = csrc.day
num = csrc.num
clean = csrc.clean
pick_price = ssrc.pick_price

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")
_CODE = re.compile(r"^[^'\x00-\x1f]{1,60}$")
_EAN = re.compile(r"^[0-9]{8,14}$")

#: Ürün kartında doluluğu sayılan CRM alanları: anahtar → (kolon, ekrandaki ad). Uzunluk okunur, metin okunmaz.
CARD_FIELDS: dict[str, tuple[str, str]] = {
    "gorsel": ("new_resimurl", "Kapak görseli"),
    "arka_kapak": ("new_ozet", "Arka kapak metni"),
    "spot": ("new_kitapspotu", "Spot"),
    "yazar": ("new_yazartext", "Yazar"),
    "kategori": ("new_webkategorileritext", "Web kategorisi"),
    "anahtar_kelime": ("new_AnahtarKelimeler", "Anahtar kelimeler"),
    "foy": ("new_TantmFyMetni", "Tanıtım föy metni"),
}


def prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def _f(firm: str) -> str:
    if not _FIRM.match(firm or ""):
        raise SourceError(f"Logo firma numarası «{firm}» geçersiz.")
    return firm


def code_ok(code: str) -> bool:
    return bool(_CODE.match(code or ""))


def _lit(v: str) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


def _in(values: Iterable[str]) -> str:
    return ", ".join(_lit(v) for v in values)


def ean_key(v: Any) -> str:
    """Barkod yalnız rakamlarıyla (SEO modülünün CRM eşlemesiyle aynı: `seo_geo.crm.ean_key`)."""
    return re.sub(r"[^0-9]", "", str(v or ""))


def _chunks(items: list[str], n: int = 500) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


# ------------------------------------------------------------------------------------------ CRM SQL


def crm_books_sql(schema: str) -> str:
    """EAN-13'ü olan ya da «TSOFT Aktif» işaretli bütün kitap kartları (durumu ne olursa olsun; pasif kart ayrıca
    işaretlenir). İçerik alanlarının yalnız uzunluğu."""
    p = prefix(schema)
    lens = ", ".join(f"DATALENGTH(k.{col}) AS len_{key}" for key, (col, _) in CARD_FIELDS.items())
    return (
        "SELECT k.new_kitapId AS id, k.new_name AS ad, k.new_ean13 AS ean, k.new_StokKodu AS stok,"
        " CAST(ISNULL(k.new_tsoftaktif, 0) AS int) AS tsoft, k.statecode AS durum, k.new_Tip AS tip,"
        " k.new_kdvdahilfiyat AS fiyat, k.new_PerakendeBirimFiyat AS perakende, k.ModifiedOn AS degisme, "
        f"{lens}"
        f" FROM {p}new_kitapBase k WHERE k.new_ean13 IS NOT NULL OR ISNULL(k.new_tsoftaktif, 0) = 1"
    )


def crm_content_sql(schema: str, eans: list[str]) -> str:
    """İçerik paketi: seçilen kitapların platforma girilecek metinleri (etkin kart). Yalnız okuma."""
    p = prefix(schema)
    bad = [e for e in eans if not _EAN.match(e)]
    if bad:
        raise SourceError(f"Barkod «{bad[0]}» geçersiz.")
    return (
        "SELECT k.new_kitapId AS id, k.new_ean13 AS ean, k.new_isbn13 AS isbn, k.new_StokKodu AS stok, k.new_name AS ad,"
        " k.new_urunadi AS urun_adi, k.new_yazartext AS yazar, k.new_cizerlertext AS cizer, k.new_tercumelertext AS cevirmen,"
        " k.new_sayfasayisi AS sayfa, k.new_kdvdahilfiyat AS fiyat, k.new_webkategorileritext AS kategori,"
        " k.new_AnahtarKelimeler AS anahtar_kelime, LEFT(k.new_kitapspotu, 2000) AS spot, LEFT(k.new_ozet, 6000) AS arka_kapak,"
        " k.new_resimurl AS gorsel_yolu"
        f" FROM {p}new_kitapBase k WHERE k.statecode = 0 AND k.new_ean13 IN ({_in(eans)})"
    )


def read_crm_books(run: Runner, schema: str) -> list[dict[str, Any]]:
    out = []
    for r in run(crm_books_sql(schema)):
        row = {"id": str(r.get("id") or ""), "ad": clean(r.get("ad"), 500), "ean": ean_key(r.get("ean")) or None,
               "stok": clean(r.get("stok"), 60), "tsoft": bool(r.get("tsoft")), "etkin": int(r.get("durum") or 0) == 0,
               "tip": r.get("tip"), "fiyat": num(r.get("fiyat")), "perakende": num(r.get("perakende")),
               "degisme": str(r.get("degisme") or "")[:19] or None,
               "dolu": {k: (num(r.get(f"len_{k}")) or 0) > 0 for k in CARD_FIELDS}}
        out.append(row)
    return out


def read_crm_content(run: Runner, schema: str, eans: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for part in _chunks(sorted(set(eans))):
        for r in run(crm_content_sql(schema, part)):
            key = ean_key(r.get("ean"))
            if key:
                out[key] = {k: (ssrc.strip_html(v, 6000) if k in ("spot", "arka_kapak") else clean(v, 1000))
                            for k, v in r.items() if k != "ean"} | {"ean": key}
    return out


# ------------------------------------------------------------------------------------------ Logo SQL


def data_end_sql(firm: str) -> str:
    return csrc.data_end_sql(_f(firm))


def stock_sql(firm: str) -> str:
    """Stok kodu başına bakiye (tarihsiz, güncel kopya); planlanan üretim girişi hariç."""
    f = _f(firm)
    return f"""
SELECT I.CODE AS stok, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
FROM dbo.LG_{f}_01_STLINE AS L
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
LEFT JOIN dbo.LG_{f}_01_STFICHE AS F ON F.LOGICALREF = L.STFICHEREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4)
  AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1)
GROUP BY I.CODE""".strip()


def item_sales_sql(firm: str, a: date, b: date) -> str:
    """Stok kodu başına net adet ve net ciro, [a, b), bütün kanallar (faturalı satır; iade eksi)."""
    f = _f(firm)
    return f"""
SELECT I.CODE AS stok,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE""".strip()


def marketplace_sql(firm: str, channels: list[str], a: date, b: date) -> str:
    """Pazar yeri carisi × ay: satış ve iade ayrı (net ciro = satış − iade), net adet."""
    f = _f(firm)
    return f"""
SELECT C.CODE AS kod, MAX(C.DEFINITION_) AS unvan, MAX(C.SPECODE2) AS kanal, YEAR(S.DATE_) AS yil, MONTH(S.DATE_) AS ay,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE 0 END) AS satis,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.LINENET ELSE 0 END) AS iade,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE 0 END) AS satis_adet,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.AMOUNT ELSE 0 END) AS iade_adet
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE C.SPECODE2 IN ({_in(channels)}) AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0
  AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'
GROUP BY C.CODE, YEAR(S.DATE_), MONTH(S.DATE_)""".strip()


def marketplace_books_sql(firm: str, code: str, a: date, b: date) -> str:
    """Tek pazar yeri carisinin kitap kırılımı: satış, iade ve net (adet + ciro)."""
    f = _f(firm)
    if not code_ok(code):
        raise SourceError("Cari kodu geçersiz.")
    return f"""
SELECT I.CODE AS stok, MAX(I.NAME) AS ad,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE 0 END) AS satis_adet,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.AMOUNT ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro,
  MAX(S.DATE_) AS son
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE C.CODE = {_lit(code)} AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0
  AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE""".strip()


def channel_books_sql(firm: str, channels: list[str], a: date, b: date) -> str:
    """Bütün pazar yeri carilerinin toplam kitap kırılımı (stok tükenme riski listesi için)."""
    f = _f(firm)
    return f"""
SELECT I.CODE AS stok, MAX(I.NAME) AS ad,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE 0 END) AS satis_adet,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.AMOUNT ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro,
  MAX(S.DATE_) AS son
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE C.SPECODE2 IN ({_in(channels)}) AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0
  AND S.TRCODE IN (2,3,7,8,9) AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE""".strip()


def read_data_end(run: Runner, firms: dict[int, str]) -> Optional[date]:
    rows = run(data_end_sql(current_firm(firms)))
    return day(rows[0].get("son")) if rows else None


def read_stock(run: Runner, firms: dict[int, str]) -> dict[str, float]:
    return {str(r["stok"]).strip(): num(r.get("bakiye")) or 0.0 for r in run(stock_sql(current_firm(firms))) if r.get("stok")}


def read_prices(run: Runner, firms: dict[int, str], today: date) -> dict[str, dict[str, Any]]:
    return ssrc.read_prices(run, firms, today)


def read_item_sales(run: Runner, firms: dict[int, str], a: date, b: date) -> dict[str, dict[str, float]]:
    """[a, b) aralığı yıl firmalarına bölünür, stok koduyla toplanır."""
    out: dict[str, dict[str, float]] = {}
    for firm, x, y in firm_ranges(firms, a, b):
        for r in run(item_sales_sql(firm, x, y)):
            code = str(r.get("stok") or "").strip()
            if not code:
                continue
            cur = out.setdefault(code, {"adet": 0.0, "ciro": 0.0})
            cur["adet"] += num(r.get("adet")) or 0.0
            cur["ciro"] += num(r.get("ciro")) or 0.0
    return out


def read_marketplaces(run: Runner, firms: dict[int, str], channels: list[str], a: date, b: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for firm, x, y in firm_ranges(firms, a, b):
        for r in run(marketplace_sql(firm, channels, x, y)):
            rows.append({"kod": str(r.get("kod") or "").strip(), "unvan": clean(r.get("unvan"), 200), "kanal": clean(r.get("kanal"), 40),
                         "yil": int(r.get("yil") or 0), "ay": int(r.get("ay") or 0),
                         "satis": num(r.get("satis")) or 0.0, "iade": num(r.get("iade")) or 0.0,
                         "satisAdet": num(r.get("satis_adet")) or 0.0, "iadeAdet": num(r.get("iade_adet")) or 0.0})
    return rows


def read_marketplace_books(run: Runner, firms: dict[int, str], code: str, a: date, b: date) -> list[dict[str, Any]]:
    return _books(run, [marketplace_books_sql(firm, code, x, y) for firm, x, y in firm_ranges(firms, a, b)])


def read_channel_books(run: Runner, firms: dict[int, str], channels: list[str], a: date, b: date) -> list[dict[str, Any]]:
    return _books(run, [channel_books_sql(firm, channels, x, y) for firm, x, y in firm_ranges(firms, a, b)])


def _books(run: Runner, sqls: list[str]) -> list[dict[str, Any]]:
    by: dict[str, dict[str, Any]] = {}
    for sql in sqls:
        for r in run(sql):
            k = str(r.get("stok") or "").strip()
            cur = by.setdefault(k, {"stok": k, "ad": clean(r.get("ad"), 300), "satisAdet": 0.0, "iadeAdet": 0.0, "ciro": 0.0, "son": None})
            cur["satisAdet"] += num(r.get("satis_adet")) or 0.0
            cur["iadeAdet"] += num(r.get("iade_adet")) or 0.0
            cur["ciro"] += num(r.get("ciro")) or 0.0
            last = day(r.get("son"))
            if last and (cur["son"] is None or last.isoformat() > cur["son"]):
                cur["son"] = last.isoformat()
    return list(by.values())


# ------------------------------------------------------------------------------------------ site (meta veritabanı)


def read_site(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """SEO & GEO eşitlemesinin son hâli: ürünler (ham T-soft kaydı) ve CRM hak/yayın özeti. T-soft'a gidilmez."""
    from semantic_bridge.seo_geo.store import CRM_BOOKS, PRODUCTS, RUNS, ensure, loads

    ensure(engine)
    with engine.connect() as c:
        products = [dict(r) for r in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.code, PRODUCTS.c.name,
                                                         PRODUCTS.c.active, PRODUCTS.c.data_json, PRODUCTS.c.synced_at)
                                               .where(PRODUCTS.c.tenant_id == tenant)).mappings()]
        books = {r["ean"]: {"rights": r["rights"], "statusFlag": r["status_flag"], "data": loads(r["data_json"], {})}
                 for r in c.execute(sa.select(CRM_BOOKS.c.ean, CRM_BOOKS.c.rights, CRM_BOOKS.c.status_flag, CRM_BOOKS.c.data_json)
                                    .where(CRM_BOOKS.c.tenant_id == tenant)).mappings()}
        last = {k: c.execute(sa.select(RUNS.c.finished_at).where(RUNS.c.tenant_id == tenant, RUNS.c.kind == k,
                                                                  RUNS.c.error.is_(None), RUNS.c.finished_at.isnot(None))
                             .order_by(RUNS.c.started_at.desc()).limit(1)).scalar() for k in ("tsoft", "crm")}
    for p in products:
        p["data"] = loads(p.pop("data_json"), {})
    return {"products": products, "rights": books, "tsoftAt": last["tsoft"], "crmAt": last["crm"]}


def tsoft_values(p: dict[str, Any]) -> dict[str, Any]:
    """T-soft kaydından karşılaştırılan alanlar. Fiyat KDV dahil; alan yoksa None (uydurulmaz)."""
    from semantic_bridge.seo_geo import shopping

    price, sale = shopping.price_of(p)
    return {"ad": clean(shopping.pick(p, shopping.K_NAME), 500), "barkod": ean_key(p.get("Barcode")) or None,
            "fiyat": price, "indirimli": sale, "stok": shopping.stock_of(p),
            "views": _int(p.get("StatViews")), "sales": _int(p.get("CountTotalSales")), "comments": _int(p.get("CommentCount")),
            "url": p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or None}


def _int(v: Any) -> int:
    try:
        return int(float(str(v or 0).replace(",", ".")))
    except ValueError:
        return 0


def year_window(cut: Optional[date], months: int) -> tuple[date, date]:
    """Kesim gününe kadar son `months` ay: [a, b). Kesim yoksa bugün."""
    end = (cut or date.today()) + timedelta(days=1)
    return end - timedelta(days=round(months * 30.4375)), end
