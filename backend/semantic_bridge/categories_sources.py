"""H1 Kategori ağacı: kaynakların okunması (yalnız okuma — CRM'e, Logo'ya ve T-soft'a yazılmaz).

**CRM (`Timas_MSCRM`, .28 prod):** aktif kitap = `new_kitapBase.statecode = 0 AND new_Tip = 1` (2026-09-24'te 9.091).
Bir kitabın bugünkü sınıflamaları birbirine bağlı olmayan yedi ayrı yerde durur; hepsi okunur ve tek «mevcut» kayıtta
birleştirilir:

- kart alanları: Kitaplık (`new_kitaplikid` → `new_kitaplikBase`), dizi, yayınevi/marka (`new_yayineviid` →
  `new_markaBase`), hedef kitle (seçenek; etiketi CRM'in `StringMap`'inden), yaş başlangıç/bitiş + yaş metni, tür metni,
  raf türü, web kategorisi metni («Çocuk;6 - 10 Yaş Öykü Hikaye»), editör ve yayın yönetmeni (SystemUser);
- çoka-çok bağlar: ürün kategorisi (ağaç, `new_anakategoriid`), raf kategorisi, sergilenecek kategori, tema, anahtar
  kelime, tür (`new_new_kitap_new_turBase` → `new_turBase`).

Uzun metinler (arka kapak, spot, anahtar kelime metni) toplu okumada alınmaz — yalnız uzunlukları (`DATALENGTH`) gelir;
metin, kitabın profil ekranı ve öneri üretimi için o kitaba özel sorguyla okunur. Böylece gece turu 9 bin kartın
ntext alanlarını taşımaz.

**Logo:** öncelik puanı = son N ayın (varsayılan 24, `CATEGORY_PRIORITY_MONTHS`) net satış adedi, faturalı satır
tanımıyla (`budget_sources` ile aynı: `CANCELLED = 0`, `LINETYPE = 0`, `INVOICEREF <> 0`, TRCODE 7/8/9 satış − 2/3
iade). Yıl → firma eşlemesi `L_CAPIPERIOD`'dan (`budget_sources.firms_by_year`); pencere verinin bittiği günden geriye
sayılır (Logo kopyası donmuşsa pencere de onunla kayar, ekranda veri sonu yazılır).

**T-soft:** doğrudan çağrılmaz; SEO & GEO modülünün eşitlediği ürünler (`semantic_seo_products.data_json`:
`Barcode`, `DefaultCategoryId/Name/Path`, `Categories`) ve kategori sayfaları (`semantic_seo_links`, tür `category`)
okunur. CRM kitabına barkodla (EAN-13) bağlanır.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.editorial import _prefix

log = logging.getLogger("semantic.categories.sources")

SourceError = bsrc.SourceError
Runner = Callable[[str], list[dict[str, Any]]]
runner = bsrc.runner

#: Çoka-çok sınıflamalar: anahtar → (bağ tablosu, bağdaki kolon, sözlük tablosu, sözlüğün birincil anahtarı, ad).
LINKS: dict[str, tuple[str, str, str, str, str]] = {
    "urunkategorisi": ("new_new_urunkategorisi_new_kitapBase", "new_urunkategorisiid", "new_urunkategorisiBase",
                       "new_urunkategorisiId", "Ürün kategorisi"),
    "raf": ("new_new_kitap_new_rafkategorisiBase", "new_rafkategorisiid", "new_rafkategorisiBase",
            "new_rafkategorisiId", "Raf kategorisi"),
    "sergilenecek": ("new_new_kitap_new_bukitaphangialtkategorileBase", "new_bukitaphangialtkategorilerdeolmalid",
                     "new_bukitaphangialtkategorilerdeolmalBase", "new_bukitaphangialtkategorilerdeolmalId",
                     "Sergilenecek kategori"),
    "tema": ("new_new_kitap_new_temaBase", "new_temaid", "new_temaBase", "new_temaId", "Tema"),
    "anahtarkelime": ("new_new_anahtarkelime_new_kitapBase", "new_anahtarkelimeid", "new_anahtarkelimeBase",
                      "new_anahtarkelimeId", "Anahtar kelime"),
    "tur": ("new_new_kitap_new_turBase", "new_turid", "new_turBase", "new_turId", "Tür"),
}
#: Kart üstündeki tek değerli sınıflamaların sözlükleri (eşleme seçicisi için).
CARD_VOCABS: dict[str, tuple[str, str]] = {
    "kitaplik": ("new_kitaplikBase", "new_kitaplikId"),
    "marka": ("new_markaBase", "new_markaId"),
}
ACTIVE_BOOK = "k.statecode = 0 AND k.new_Tip = 1"

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean(v: Any, n: int = 0) -> Optional[str]:
    """HTML etiketini ve fazla boşluğu atar. `n` verilirse metin o uzunlukta kesilir ve «…» eklenir (yalnız istem
    metni için; kırpıldığı `clipped()` ile ekrana söylenir)."""
    if v is None:
        return None
    import html as _html

    t = _WS.sub(" ", _html.unescape(_TAG.sub(" ", str(v)))).strip()
    if not t:
        return None
    return (t[: n - 1].rstrip() + "…") if n and len(t) > n else t


def guid(v: Any) -> Optional[str]:
    s = str(v or "").strip().strip("{}").upper()
    return s or None


def _day(v: Any) -> Optional[str]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v)
    return s[:19] if s[:4].isdigit() else None


# ------------------------------------------------------------------ CRM SQL


def books_sql(schema: str) -> str:
    """Aktif kitapların künyesi ve kart üstündeki sınıflamaları; uzun metinlerin yalnız uzunluğu."""
    p = _prefix(schema)
    return (
        "SELECT k.new_kitapId AS id, k.new_StokKodu AS stok, k.new_name AS ad, k.new_urunadi AS urun_adi,"
        " k.new_isbn13 AS isbn, k.new_ean13 AS ean, k.new_kitap_yayincilikstatusu AS yst, k.new_yazartext AS yazar,"
        " k.new_kitaplikid AS kitaplik_id, kl.new_name AS kitaplik, k.new_diziid AS dizi_id, dz.new_name AS dizi,"
        " k.new_yayineviid AS marka_id, m.new_name AS marka,"
        " k.new_turlertext AS tur_metni, k.new_rafturu AS raf_turu, k.new_webkategorileritext AS web,"
        " k.new_hedefkitle AS hedef, k.new_hedefkitleyasbaslangic AS yas_bas, k.new_hedefkitleyasbitis AS yas_bit,"
        " k.new_yaslartext AS yas_metni,"
        " k.new_Editor AS editor_id, eu.FullName AS editor, k.new_yayinyonetmeni AS yonetmen_id, yu.FullName AS yonetmen,"
        " CAST(ISNULL(k.new_tsoftaktif, 0) AS int) AS tsoft,"
        " DATALENGTH(k.new_ozet) AS ozet_len, DATALENGTH(k.new_kitapspotu) AS spot_len,"
        " k.CreatedOn AS olusturma, k.ModifiedOn AS degisme"
        f" FROM {p}new_kitapBase k"
        f" LEFT JOIN {p}new_kitaplikBase kl ON kl.new_kitaplikId = k.new_kitaplikid"
        f" LEFT JOIN {p}new_diziBase dz ON dz.new_diziId = k.new_diziid"
        f" LEFT JOIN {p}new_markaBase m ON m.new_markaId = k.new_yayineviid"
        f" LEFT JOIN {p}SystemUserBase eu ON eu.SystemUserId = k.new_Editor"
        f" LEFT JOIN {p}SystemUserBase yu ON yu.SystemUserId = k.new_yayinyonetmeni"
        f" WHERE {ACTIVE_BOOK}"
    )


def link_sql(schema: str, key: str) -> str:
    """Aktif kitapların bir çoka-çok sınıflamadaki bağları: (kitap, sözlük kaydı)."""
    p = _prefix(schema)
    table, col, _vt, _pk, _ = LINKS[key]
    return (f"SELECT l.new_kitapid AS book, l.{col} AS ref FROM {p}{table} l"
            f" JOIN {p}new_kitapBase k ON k.new_kitapId = l.new_kitapid WHERE {ACTIVE_BOOK}")


def vocab_sql(schema: str, key: str) -> str:
    """Sözlüğün tamamı (pasifler dahil; eski bağlar pasif kayda gidebilir, ekranda «pasif» yazılır)."""
    p = _prefix(schema)
    if key in LINKS:
        _t, _c, table, pk, _ = LINKS[key]
    else:
        table, pk = CARD_VOCABS[key]
    extra = ", new_anakategoriid AS parent" if key == "urunkategorisi" else ""
    return f"SELECT {pk} AS id, new_name AS name, statecode AS state{extra} FROM {p}{table}"


def book_text_sql(schema: str, book_id: str) -> str:
    """Tek kitabın uzun metinleri (profil ekranı ve öneri istemi). Kimlik GUID biçiminde doğrulanmış olmalı."""
    p = _prefix(schema)
    return (
        "SELECT k.new_kitapId AS id, LEFT(k.new_ozet, 6000) AS ozet, LEFT(k.new_kitapspotu, 2000) AS spot,"
        " LEFT(k.new_AnahtarKelimeler, 2000) AS anahtar_metin, LEFT(k.new_TantmFyMetni, 3000) AS tanitim,"
        " LEFT(k.new_kitabinonecikanyanlari, 2000) AS one_cikan, k.new_sayfasayisi AS sayfa, k.new_ilkyayintarihi AS ilk_yayin"
        f" FROM {p}new_kitapBase k WHERE k.new_kitapId = '{book_id}'"
    )


GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


def audience_labels(schema: str, run: Runner) -> dict[int, str]:
    """Hedef kitle seçeneklerinin CRM'deki Türkçe etiketleri (1 Çocuk, 2 Genç, 3 Yetişkin — CRM'den okunur)."""
    from semantic_bridge.seo_geo.crm import label_sql

    out: dict[int, str] = {}
    for r in run(label_sql(_prefix(schema), "new_hedefkitle")):
        try:
            out[int(r["v"])] = str(r["l"]).strip()
        except (TypeError, ValueError, KeyError):
            continue
    return out


def status_labels(schema: str, run: Runner) -> dict[int, str]:
    from semantic_bridge.seo_geo.crm import label_sql

    out: dict[int, str] = {}
    for r in run(label_sql(_prefix(schema), "new_kitap_yayincilikstatusu")):
        try:
            out[int(r["v"])] = str(r["l"]).strip()
        except (TypeError, ValueError, KeyError):
            continue
    return out


def _int(v: Any) -> Optional[int]:
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def split_text(v: Any) -> list[str]:
    """«Roman;Öykü» / «Roman, Öykü» → ["Roman", "Öykü"]. Ayraç CRM'de `;` (web kategorisi) — tür metninde ölçülecek,
    ikisi de kabul edilir."""
    s = clean(v)
    if not s:
        return []
    return [x.strip() for x in re.split(r"[;,]", s) if x.strip()]


def web_parts(v: Any) -> tuple[Optional[str], Optional[str]]:
    """Web kategorisi metni «Çocuk;6 - 10 Yaş Öykü Hikaye» → («Çocuk», «6 - 10 Yaş Öykü Hikaye»)."""
    s = clean(v)
    if not s:
        return None, None
    root, _, rest = s.partition(";")
    return (root.strip() or None), (rest.strip() or None)


def read_crm(schema: str, run: Runner) -> dict[str, Any]:
    """Aktif kitapların birleşik «mevcut» kaydı + sözlükler. Dönüş: {books: {id: snap}, vocab: {...}, labels: {...}}."""
    audience = audience_labels(schema, run)
    ystat = status_labels(schema, run)
    vocab: dict[str, dict[str, dict[str, Any]]] = {}
    for key in (*LINKS.keys(), *CARD_VOCABS.keys()):
        items: dict[str, dict[str, Any]] = {}
        for r in run(vocab_sql(schema, key)):
            vid = guid(r.get("id"))
            if not vid:
                continue
            items[vid] = {"id": vid, "name": clean(r.get("name")) or "—", "active": _int(r.get("state")) in (0, None)}
            if key == "urunkategorisi":
                items[vid]["parent"] = guid(r.get("parent"))
        vocab[key] = items
    books: dict[str, dict[str, Any]] = {}
    for r in run(books_sql(schema)):
        bid = guid(r.get("id"))
        if not bid:
            continue
        root, sub = web_parts(r.get("web"))
        hedef = _int(r.get("hedef"))
        yst = _int(r.get("yst"))
        books[bid] = {
            "id": bid, "stok": clean(r.get("stok")), "ad": clean(r.get("ad")) or clean(r.get("urun_adi")),
            "isbn": clean(r.get("isbn")), "ean": re.sub(r"[^0-9]", "", str(r.get("ean") or "")) or None,
            "yazar": clean(r.get("yazar")), "yayincilikStatusu": ystat.get(yst) if yst is not None else None,
            "kitaplik": _ref(r, "kitaplik_id", "kitaplik"), "dizi": _ref(r, "dizi_id", "dizi"),
            "marka": _ref(r, "marka_id", "marka"),
            "hedefKitle": {"code": hedef, "label": audience.get(hedef)} if hedef is not None else None,
            "yas": _age(r), "yasMetni": clean(r.get("yas_metni")),
            "turMetni": clean(r.get("tur_metni")), "rafTuru": clean(r.get("raf_turu")),
            "web": clean(r.get("web")), "webRoot": root, "webSub": sub,
            "editor": _ref(r, "editor_id", "editor"), "yonetmen": _ref(r, "yonetmen_id", "yonetmen"),
            "tsoftAktif": bool(_int(r.get("tsoft"))),
            "ozetVar": (_int(r.get("ozet_len")) or 0) > 0, "spotVar": (_int(r.get("spot_len")) or 0) > 0,
            "olusturma": _day(r.get("olusturma")), "degisme": _day(r.get("degisme")),
            **{k: [] for k in LINKS},
        }
    for key in LINKS:
        names = vocab.get(key, {})
        for r in run(link_sql(schema, key)):
            b = books.get(guid(r.get("book")) or "")
            ref = guid(r.get("ref"))
            if b is None or not ref:
                continue
            item = names.get(ref) or {"id": ref, "name": "—", "active": False}
            if not any(x["id"] == ref for x in b[key]):
                b[key].append({"id": ref, "name": item["name"]})
    for b in books.values():
        for key in LINKS:
            b[key].sort(key=lambda x: x["name"].casefold())
    return {"books": books, "vocab": vocab, "labels": {"hedefKitle": {str(k): v for k, v in audience.items()}}}


def _ref(r: dict[str, Any], id_col: str, name_col: str) -> Optional[dict[str, Any]]:
    rid = guid(r.get(id_col))
    return {"id": rid, "name": clean(r.get(name_col)) or "—"} if rid else None


def _age(r: dict[str, Any]) -> Optional[dict[str, Optional[int]]]:
    a, b = _int(r.get("yas_bas")), _int(r.get("yas_bit"))
    if a is None and b is None:
        return None
    return {"bas": a, "bit": b}


def read_book_text(schema: str, run: Runner, book_id: str) -> dict[str, Any]:
    bid = guid(book_id) or ""
    if not GUID.match(bid):
        raise SourceError("Kitap kimliği geçerli değil.")
    rows = run(book_text_sql(schema, bid))
    if not rows:
        return {}
    r = rows[0]
    return {"ozet": clean(r.get("ozet")), "spot": clean(r.get("spot")), "anahtarMetin": clean(r.get("anahtar_metin")),
            "tanitim": clean(r.get("tanitim")), "oneCikan": clean(r.get("one_cikan")), "sayfa": _int(r.get("sayfa")),
            "ilkYayin": _day(r.get("ilk_yayin"))}


# ------------------------------------------------------------------ Logo: öncelik puanı


def priority_sql(firm: str, start: date, end_excl: date) -> str:
    return f"""
-- Faturalı satış satırları; iade eksi. Net adet = Σ AMOUNT (satış) − Σ AMOUNT (iade).
SELECT I.CODE AS stok_kodu,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{start.isoformat()}' AND S.DATE_ < '{end_excl.isoformat()}'
GROUP BY I.CODE""".strip()


def months_back(end: date, months: int) -> date:
    """Veri sonundan geriye `months` ay: pencerenin ilk günü (ayın aynı günü; ay kısa ise ayın son günü)."""
    import calendar

    y, m = end.year, end.month - months
    while m <= 0:
        m += 12
        y -= 1
    d = min(end.day, calendar.monthrange(y, m)[1])
    return date(y, m, d)


def read_priority(run: Runner, months: int) -> dict[str, Any]:
    """Stok kodu → son `months` ayın net adedi. Pencere [veri sonu − months, veri sonu]; yıl sınırında her yıl kendi
    firmasından okunur."""
    firms = bsrc.firms_by_year(run)
    if not firms:
        raise SourceError("Logo'da dönem bulunamadı.")
    end = bsrc.read_data_end(run, firms)
    if end is None:
        raise SourceError("Logo'da faturalı satış satırı bulunamadı.")
    start = months_back(end, months)
    out: dict[str, float] = {}
    for y in range(start.year, end.year + 1):
        firm = firms.get(y)
        if not firm:
            log.warning("kategori önceliği: %s yılının Logo dönemi yok, atlandı", y)
            continue
        a = max(start, date(y, 1, 1))
        b = min(date.fromordinal(end.toordinal() + 1), date(y + 1, 1, 1))
        for r in run(priority_sql(firm, a, b)):
            code = str(r.get("stok_kodu") or "").strip()
            if code:
                out[code] = out.get(code, 0.0) + float(r.get("adet") or 0)
    return {"byCode": out, "start": start.isoformat(), "end": end.isoformat(), "months": months,
            "years": sorted(y for y in range(start.year, end.year + 1) if firms.get(y))}


# ------------------------------------------------------------------ T-soft (SEO deposundan, yalnız okuma)


def read_tsoft(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """{products: {ean: {...}}, categories: {id: {...}}, syncedAt}. SEO eşitlemesi yoksa boş sözlükler."""
    from semantic_bridge.seo_geo.store import LINKS as SEO_LINKS, PRODUCTS, ensure as seo_ensure

    seo_ensure(engine)
    products: dict[str, dict[str, Any]] = {}
    cats: dict[str, dict[str, Any]] = {}
    last: Optional[str] = None
    with engine.connect() as c:
        for r in c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.active, PRODUCTS.c.data_json, PRODUCTS.c.synced_at)
                           .where(PRODUCTS.c.tenant_id == tenant)).mappings():
            try:
                d = json.loads(r["data_json"] or "{}")
            except ValueError:
                continue
            ean = re.sub(r"[^0-9]", "", str(d.get("Barcode") or ""))
            cid = str(d.get("DefaultCategoryId") or "").strip()
            path = " > ".join(x.strip() for x in f"{d.get('DefaultCategoryPath') or ''}".split(">") if x.strip())
            name = clean(d.get("DefaultCategoryName"))
            if cid and cid != "0":
                cat = cats.setdefault(cid, {"id": cid, "name": name or cid, "path": path or None, "products": 0,
                                            "title": None, "link": None})
                cat["products"] += 1
            others = [str(x.get("CategoryId")) for x in (d.get("Categories") or []) if isinstance(x, dict) and x.get("CategoryId")]
            if ean:
                products[ean] = {"productId": r["product_id"], "active": bool(r["active"]), "categoryId": cid or None,
                                 "categoryName": name, "categoryPath": path or None, "categories": others}
            s = r["synced_at"].isoformat() if r["synced_at"] is not None else None
            if s and (last is None or s > last):
                last = s
        for r in c.execute(sa.select(SEO_LINKS.c.table_id, SEO_LINKS.c.title, SEO_LINKS.c.link)
                           .where(SEO_LINKS.c.tenant_id == tenant, SEO_LINKS.c.type == "category")).mappings():
            cid = str(r["table_id"] or "").strip()
            if not cid:
                continue
            cat = cats.setdefault(cid, {"id": cid, "name": clean(r["title"]) or cid, "path": None, "products": 0,
                                        "title": None, "link": None})
            cat["title"], cat["link"] = clean(r["title"]), r["link"]
    return {"products": products, "categories": cats, "syncedAt": last}
