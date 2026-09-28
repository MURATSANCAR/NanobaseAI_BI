"""Google Alışveriş hazırlığı: T-soft'taki etkin ürünler Merchant Center ürün verisi kurallarına göre denetlenir.

Hiçbir yere gönderilmez. Merchant Center hesabı bağlı değil; ekran sorunları gösterir, besleme dosyası (TSV) bir
insanın elle yüklemesi içindir. Kaynak `semantic_seo_products.data_json` (T-soft product/get kaydı); alan adları
T-soft sürümüne göre değişebildiği için her alan birkaç adla ve büyük/küçük harf duyarsız aranır.

Merchant Center kuralları (Google ürün verisi belirtimi, 2026 itibarıyla):
- id, title (≤150 karakter, tanıtım metni ve TAMAMI BÜYÜK HARF olmaz), description (zorunlu, ≤5000), link, image_link
  (zorunlu, yer tutucu görsel olmaz), availability (in_stock / out_of_stock), price (>0; Türkiye hedefinde TRY, KDV
  dahil), sale_price (price'tan küçük olmalı), gtin (geçerli sağlama haneli EAN/ISBN-13; 2 ile başlayan mağaza içi
  kodlar geçersiz), brand (kitap, film ve müzikte zorunlu değil), condition (new), google_product_category (kitap:
  784 «Medya > Kitaplar»), identifier_exists (geçerli GTIN yoksa «no»).
- Ek denetimler: CRM'de yayın durumu işaretli (satıştan çekildi, artık bizim değil…) ama satışta görünen ürün,
  birden çok üründe aynı GTIN.

Önem düzeyi: engelleyici (ürün reddedilir ya da reklama çıkmamalı) · sorun (ürün geçer ama zayıf/uyarı alır) ·
bilgi (yalnız not). Hazır = engelleyici ve sorun yok.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Iterable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response

from .store import CRM_BOOKS, PRODUCTS, RUNS, iso, loads

log = logging.getLogger("semantic.seo_geo.shopping")

# ------------------------------------------------------------------ sabitler
BLOCKER = "engelleyici"
ISSUE = "sorun"
INFO = "bilgi"
SEVERITIES = (BLOCKER, ISSUE, INFO)
SEV_ORDER = {s: i for i, s in enumerate(SEVERITIES)}

STATUS_READY = "hazir"
STATUS_PROBLEM = "sorunlu"
STATUS_BLOCKED = "engelleyici"
STATUSES = (STATUS_READY, STATUS_PROBLEM, STATUS_BLOCKED)

TITLE_MAX = 150                 # Merchant Center başlık sınırı
DESC_MAX = 5000                 # Merchant Center açıklama sınırı
ADDITIONAL_IMAGES_MAX = 10      # Merchant Center'ın kabul ettiği ek görsel sayısı (Google sınırı; fazlası yok sayılır)
CAPS_MIN_LETTERS = 6            # bundan kısa başlıkta büyük harf denetimi yapılmaz (kısaltmalar)
CAPS_RATIO = 0.8                # harflerin bu oranı ya da fazlası büyükse «tamamı büyük harf»
BOOK_CATEGORY = "784"           # Google ürün kategorisi: Media > Books (Medya > Kitaplar)
BOOK_PREFIXES = ("978", "979")  # ISBN-13 = kitap
CURRENCY = "TRY"

#: kod → (önem, kısa ad, neden)
ISSUES: dict[str, tuple[str, str, str]] = {
    "crm_flag": (BLOCKER, "CRM'de yayın durumu işaretli", "CRM'de satıştan çekildi / artık bizim değil / geri istendi gibi bir "
                                                         "durum var ama ürün sitede satışta; reklama çıkmamalı."),
    "title_missing": (BLOCKER, "Başlık yok", "Başlık zorunludur."),
    "desc_missing": (BLOCKER, "Açıklama yok", "Açıklama zorunludur; ürün sayfasındaki tanıtım metni boş."),
    "link_missing": (BLOCKER, "Ürün adresi yok", "Ürün sayfası adresi (link) zorunludur."),
    "image_missing": (BLOCKER, "Görsel yok", "Ana görsel (image_link) zorunludur."),
    "image_placeholder": (BLOCKER, "Yer tutucu görsel", "Görsel «resim yok» türü bir yer tutucu; Google reddeder."),
    "stock_unknown": (BLOCKER, "Stok bilgisi yok", "Stok durumu (availability) zorunludur; kayıtta stok alanı bulunamadı."),
    "price_zero": (BLOCKER, "Fiyat yok ya da sıfır", "Fiyat sıfırdan büyük olmalı."),
    "currency": (BLOCKER, "Para birimi TRY değil", "Türkiye hedefli üründe fiyat Türk lirası olmalı."),
    "gtin_invalid": (BLOCKER, "Barkod (GTIN) geçersiz", "Barkodun sağlama hanesi tutmuyor ya da uzunluğu yanlış; Google "
                                                      "geçersiz GTIN'li ürünü sınırlar ya da reddeder."),
    "gtin_restricted": (BLOCKER, "Mağaza içi barkod", "2 ile başlayan barkod mağaza içi koddur, GTIN olarak kabul edilmez."),
    "title_long": (ISSUE, f"Başlık {TITLE_MAX} karakterden uzun", "Uzun başlık kesilir; dosyada kısaltıldı."),
    "title_caps": (ISSUE, "Başlık tamamen büyük harf", "Google büyük harfle yazılmış başlığı düzenleme ihlali sayar."),
    "title_promo": (ISSUE, "Başlıkta tanıtım ifadesi", "İndirim, kampanya, ücretsiz kargo gibi ifadeler başlıkta olmaz."),
    "desc_long": (ISSUE, f"Açıklama {DESC_MAX} karakterden uzun", "Fazlası kesilir; dosyada kısaltıldı."),
    "sale_above_price": (ISSUE, "İndirimli fiyat liste fiyatından yüksek", "İndirimli fiyat fiyattan küçük olmalı; dosyaya "
                                                                          "indirimli fiyat yazılmadı."),
    "gtin_missing": (ISSUE, "Barkod (GTIN) yok", "Kitapta ISBN beklenir; barkodsuz ürün eşleşmez ve az gösterilir."),
    "gtin_duplicate": (ISSUE, "Aynı barkod başka üründe de var", "Aynı GTIN'li iki ürün Google'da çakışır."),
    "brand_missing": (ISSUE, "Marka yok", "Kitap dışı yeni ürünlerde marka zorunludur."),
    "gtin_isbn10": (INFO, "ISBN-10 çevrildi", "Barkod 10 haneli ISBN; dosyaya 13 haneli karşılığı yazıldı."),
    "out_of_stock": (INFO, "Stokta yok", "Ürün «stokta yok» olarak gider; reklamı gösterilmez."),
    "not_book": (INFO, "Kitap değil", "Barkod ISBN değil; Google kategorisi elle seçilmeli (dosyada boş)."),
    "brand_missing_book": (INFO, "Yayınevi yok", "Kitapta marka zorunlu değil; yine de yayınevi yazılması önerilir."),
}

# ------------------------------------------------------------------ alan adları (T-soft sürümleri arasında değişir)
K_ID = ("ProductCode", "ProductId")
K_NAME = ("ProductName", "Name", "Title")
K_AUTHOR = ("Model", "ModelName", "Author")
K_BRAND = ("Brand", "BrandName", "Publisher")
K_DESC = ("Details", "Description", "ShortDescription", "SeoDescription")
K_LINK = ("SeoLink", "Url", "ProductUrl", "Link")
K_BARCODE = ("Barcode", "Gtin", "GTIN", "Ean", "Isbn", "ISBN")
K_STOCK = ("Stock", "StockCount", "StockAmount", "StockQuantity", "TotalStock", "Quantity")
K_PRICE_INCL = ("SellingPriceVatIncluded", "PriceVatIncluded", "VatIncludedSellingPrice", "SellingPriceWithVat",
                "ListPriceVatIncluded")
K_PRICE_EXCL = ("SellingPrice", "Price", "ListPrice", "SalePrice")
K_SALE_INCL = ("DiscountedSellingPriceVatIncluded", "DiscountedPriceVatIncluded", "DiscountedSellingPriceWithVat")
K_SALE_EXCL = ("DiscountedSellingPrice", "DiscountedPrice", "DiscountPrice")
K_VAT = ("Vat", "VatRate", "Tax", "TaxRate")
K_CURRENCY = ("Currency", "CurrencyCode", "SellingPriceCurrency", "CurrencyName")
K_CATEGORY = ("DefaultCategoryPath", "DefaultCategoryName", "CategoryName")
K_IMAGE_SINGLE = ("ImageUrlCdn", "ImageUrl")
IMAGE_SIZE_KEYS = ("Original", "Big", "Large", "Zoom", "Medium", "ImageUrl", "Url", "Small")

_PLACEHOLDER = re.compile(r"no[-_ ]?image|no[-_ ]?photo|placeholder|resim[-_ ]?yok|gorsel[-_ ]?yok|görsel[-_ ]?yok|"
                          r"default[-_.]?(image|img|product)|/noimg|dummy", re.I)
_PROMO = [re.compile(p, re.I) for p in (
    r"\bindirim", r"\bkampanya", r"ücretsiz\s+kargo", r"kargo\s+bedava", r"\bbedava\b", r"\ben\s+ucuz",
    r"en\s+uygun\s+fiyat", r"satın\s+al", r"hemen\s+al", r"\bstokta\b", r"%\s*\d+", r"\d+\s*%", r"son\s+\d+\s+adet",
    r"tükenmeden", r"kaçırma")]


def _tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def pick(p: dict[str, Any], keys: Iterable[str]) -> Any:
    """İlk dolu alan; ad büyük/küçük harf duyarsız eşlenir."""
    low = {str(k).lower(): v for k, v in p.items()}
    for k in keys:
        v = p.get(k) if k in p else low.get(k.lower())
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, (list, dict)) and not v:
            continue
        return v
    return None


def text_of(value: Any) -> str:
    from .rules import text_of as _t

    return _t(value)


# ------------------------------------------------------------------ sayılar
def money(v: Any) -> Optional[float]:
    """«1.234,50», «1234.50», «45 TL», 45 → sayı. Okunamazsa None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^0-9,.\-]", "", str(v))
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def price_of(p: dict[str, Any]) -> tuple[Optional[float], Optional[float]]:
    """(fiyat, indirimli fiyat) KDV dahil. KDV dahil alan yoksa hariç fiyat + KDV oranı."""
    vat = money(pick(p, K_VAT)) or 0.0
    factor = 1 + vat / 100 if 0 < vat < 100 else 1.0

    def one(incl: tuple[str, ...], excl: tuple[str, ...]) -> Optional[float]:
        v = money(pick(p, incl))
        if v is not None and v > 0:
            return round(v, 2)
        v = money(pick(p, excl))
        return round(v * factor, 2) if v is not None else None

    price = one(K_PRICE_INCL, K_PRICE_EXCL)
    sale = one(K_SALE_INCL, K_SALE_EXCL)
    if sale is not None and sale <= 0:
        sale = None
    return price, sale


def currency_of(p: dict[str, Any]) -> str:
    raw = str(pick(p, K_CURRENCY) or "").strip().upper()
    if not raw or raw in ("TL", "TRY", "YTL", "₺", "TÜRK LIRASI", "TÜRK LİRASI"):
        return CURRENCY
    return raw


def stock_of(p: dict[str, Any]) -> Optional[float]:
    return money(pick(p, K_STOCK))


def availability(p: dict[str, Any]) -> Optional[str]:
    s = stock_of(p)
    if s is None:
        return None
    return "in_stock" if s > 0 else "out_of_stock"


# ------------------------------------------------------------------ GTIN / ISBN
def digits(v: Any) -> str:
    return re.sub(r"[^0-9Xx]", "", str(v or "")).upper()


def gtin_check_digit(body: str) -> int:
    """GS1 sağlama hanesi: sağdan başlayarak 3,1,3,1… ağırlık."""
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10


def gtin_valid(code: str) -> bool:
    code = str(code or "")
    if not code.isdigit() or len(code) not in (8, 12, 13, 14):
        return False
    return gtin_check_digit(code[:-1]) == int(code[-1])


def isbn10_valid(code: str) -> bool:
    code = str(code or "").upper()
    if not re.fullmatch(r"\d{9}[\dX]", code):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(code))
    return total % 11 == 0


def isbn10_to_13(code: str) -> str:
    body = "978" + code[:9]
    return body + str(gtin_check_digit(body))


def normalize_gtin(raw: Any) -> tuple[Optional[str], list[str]]:
    """Barkod → (GTIN ya da None, sorun kodları)."""
    d = digits(raw)
    if not d:
        return None, ["gtin_missing"]
    if len(d) == 10 and isbn10_valid(d):
        return isbn10_to_13(d), ["gtin_isbn10"]
    if "X" in d or not gtin_valid(d):
        return None, ["gtin_invalid"]
    if (len(d) in (12, 13) and d[0] == "2") or (len(d) == 14 and d[1] == "2"):
        return None, ["gtin_restricted"]
    return d, []


def is_book(gtin: Optional[str]) -> bool:
    return bool(gtin) and len(gtin) == 13 and gtin.startswith(BOOK_PREFIXES)


# ------------------------------------------------------------------ başlık
def title_issues(title: str) -> list[str]:
    t = (title or "").strip()
    if not t:
        return ["title_missing"]
    out: list[str] = []
    if len(t) > TITLE_MAX:
        out.append("title_long")
    letters = [c for c in t if c.isalpha()]
    if len(letters) >= CAPS_MIN_LETTERS and sum(1 for c in letters if c.isupper()) / len(letters) >= CAPS_RATIO:
        out.append("title_caps")
    low = _tr_lower(t)
    if any(p.search(low) for p in _PROMO):
        out.append("title_promo")
    return out


def promo_words(title: str) -> list[str]:
    low = _tr_lower(title or "")
    return [m.group(0) for p in _PROMO for m in [p.search(low)] if m]


def feed_title(name: str, author: str) -> str:
    """Kitap adı + « - yazar» (sığarsa); sığmazsa yalnız ad, o da uzunsa sözcük sınırında kesilir."""
    name, author = name.strip(), author.strip()
    if author and _tr_lower(author) not in _tr_lower(name) and len(name) + 3 + len(author) <= TITLE_MAX:
        return f"{name} - {author}"
    return clip(name, TITLE_MAX)


def clip(s: str, n: int) -> str:
    if len(s) <= n:
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > n * 0.6 else cut).rstrip(" ,;:-")


# ------------------------------------------------------------------ görsel ve adres
def images_of(p: dict[str, Any], site: str) -> list[str]:
    out: list[str] = []
    imgs = pick(p, ("ImageUrls", "Images")) or []
    if isinstance(imgs, list):
        for im in imgs:
            u = None
            if isinstance(im, dict):
                u = next((im.get(k) for k in IMAGE_SIZE_KEYS if im.get(k)), None)
            elif isinstance(im, str):
                u = im
            if u:
                out.append(_abs(str(u), site))
    if not out:
        raw = pick(p, K_IMAGE_SINGLE)
        if raw:
            out.append(_abs(str(raw), site))
    seen: set[str] = set()
    return [u for u in out if not (u in seen or seen.add(u))]


def _abs(u: str, site: str) -> str:
    u = u.strip()
    if u.startswith("//"):
        return "https:" + u
    return u if u.startswith("http") else f"{(site or 'https://timas.com.tr').rstrip('/')}/{u.lstrip('/')}"


def link_of(p: dict[str, Any], site: str) -> Optional[str]:
    link = pick(p, K_LINK)
    return _abs(str(link), site) if link else None


def is_placeholder(url: str) -> bool:
    return bool(_PLACEHOLDER.search(url or ""))


# ------------------------------------------------------------------ denetim
def audit(p: dict[str, Any], site: str, *, crm_flag: Optional[str] = None,
          duplicate_gtins: Optional[set[str]] = None) -> dict[str, Any]:
    """Tek ürün → {row: besleme satırı, issues: [{code, severity, title, detail}], status}."""
    codes: list[tuple[str, str]] = []           # (kod, ayrıntı)
    name = text_of(pick(p, K_NAME))
    author = text_of(pick(p, K_AUTHOR))
    brand = text_of(pick(p, K_BRAND))
    for c in title_issues(name):
        detail = ""
        if c == "title_long":
            detail = f"{len(name)} karakter"
        elif c == "title_promo":
            detail = ", ".join(promo_words(name))
        codes.append((c, detail))

    desc_raw = text_of(pick(p, K_DESC))
    if not desc_raw:
        codes.append(("desc_missing", ""))
    elif len(desc_raw) > DESC_MAX:
        codes.append(("desc_long", f"{len(desc_raw)} karakter"))

    link = link_of(p, site)
    if not link:
        codes.append(("link_missing", ""))

    imgs = images_of(p, site)
    if not imgs:
        codes.append(("image_missing", ""))
    elif is_placeholder(imgs[0]):
        codes.append(("image_placeholder", imgs[0]))

    avail = availability(p)
    if avail is None:
        codes.append(("stock_unknown", ""))
    elif avail == "out_of_stock":
        codes.append(("out_of_stock", ""))

    price, sale = price_of(p)
    cur = currency_of(p)
    if price is None or price <= 0:
        codes.append(("price_zero", "" if price is None else f"{price:.2f}"))
    if cur != CURRENCY:
        codes.append(("currency", cur))
    if sale is not None and price is not None and sale > price:
        codes.append(("sale_above_price", f"{sale:.2f} > {price:.2f}"))
    if sale is not None and (price is None or sale >= price):
        sale = None

    gtin, gcodes = normalize_gtin(pick(p, K_BARCODE))
    for c in gcodes:
        codes.append((c, digits(pick(p, K_BARCODE)) if c in ("gtin_invalid", "gtin_restricted", "gtin_isbn10") else ""))
    book = is_book(gtin)
    if gtin and not book:
        codes.append(("not_book", ""))
    if gtin and duplicate_gtins and gtin in duplicate_gtins:
        codes.append(("gtin_duplicate", gtin))
    if not brand:
        codes.append(("brand_missing_book" if book or not gtin else "brand_missing", ""))
    if crm_flag:
        from .watch import FLAG_TEXT

        codes.append(("crm_flag", FLAG_TEXT.get(crm_flag, crm_flag)))

    issues = sorted(({"code": c, "severity": ISSUES[c][0], "title": ISSUES[c][1], "detail": d} for c, d in codes),
                    key=lambda i: (SEV_ORDER[i["severity"]], i["code"]))
    sev = {i["severity"] for i in issues}
    status = STATUS_BLOCKED if BLOCKER in sev else STATUS_PROBLEM if ISSUE in sev else STATUS_READY
    row = {
        "id": str(pick(p, K_ID) or ""),
        "title": feed_title(name, author) if name else "",
        "description": clip(desc_raw, DESC_MAX),
        "link": link or "",
        "image_link": imgs[0] if imgs else "",
        "additional_image_link": ",".join(imgs[1:1 + ADDITIONAL_IMAGES_MAX]),
        "availability": avail or "",
        "price": f"{price:.2f} {cur}" if price and price > 0 else "",
        "sale_price": f"{sale:.2f} {cur}" if sale else "",
        "gtin": gtin or "",
        "brand": brand,
        "condition": "new",
        "google_product_category": BOOK_CATEGORY if book else "",
        "product_type": text_of(pick(p, K_CATEGORY)).replace("/", " > ") if pick(p, K_CATEGORY) else "",
        "identifier_exists": "yes" if gtin else "no",
    }
    return {"row": row, "issues": issues, "status": status, "price": price, "salePrice": sale, "currency": cur,
            "gtin": gtin, "book": book, "name": name, "author": author, "image": imgs[0] if imgs else None, "url": link}


def duplicate_gtins(products: Iterable[dict[str, Any]]) -> set[str]:
    seen: dict[str, int] = {}
    for p in products:
        g, _ = normalize_gtin(pick(p, K_BARCODE))
        if g:
            seen[g] = seen.get(g, 0) + 1
    return {g for g, n in seen.items() if n > 1}


FEED_COLUMNS = ("id", "title", "description", "link", "image_link", "additional_image_link", "availability", "price",
                "sale_price", "gtin", "brand", "condition", "google_product_category", "product_type", "identifier_exists")


def _cell(v: Any) -> str:
    return re.sub(r"[\t\r\n]+", " ", str(v if v is not None else "")).strip()


def feed_tsv(rows: Iterable[dict[str, Any]]) -> str:
    """Merchant Center'a elle yüklenecek sekmeyle ayrılmış dosya: başlık satırı + satırlar; değerde sekme/satır sonu olmaz."""
    lines = ["\t".join(FEED_COLUMNS)]
    lines.extend("\t".join(_cell(r.get(c)) for c in FEED_COLUMNS) for r in rows)
    return "\n".join(lines) + "\n"


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = {s: 0 for s in STATUSES}
    by_issue: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] += 1
        for code in {i["code"] for i in r["issues"]}:
            by_issue[code] = by_issue.get(code, 0) + 1
    return {"products": len(results), "ready": by_status[STATUS_READY], "problem": by_status[STATUS_PROBLEM],
            "blocked": by_status[STATUS_BLOCKED],
            "issues": [{"code": c, "severity": ISSUES[c][0], "title": ISSUES[c][1], "why": ISSUES[c][2],
                        "count": by_issue.get(c, 0)} for c in sorted(ISSUES, key=lambda c: (SEV_ORDER[ISSUES[c][0]], c))]}


def _num(v: Any) -> int:
    try:
        return int(float(str(v or 0).replace(",", ".")))
    except ValueError:
        return 0


# ------------------------------------------------------------------ çalışan kısım
def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


class Shopping:
    """Denetim okumada hesaplanır; sonuç son T-soft/CRM eşitleme zamanına bağlı önbellekte durur (açıklama metni
    önbelleğe girmez; besleme dosyası her indirmede veritabanından yeniden kurulur)."""

    def __init__(self, seo: Any) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self._cache: tuple[Any, list[dict[str, Any]], dict[str, Any]] | None = None

    def site(self) -> str:
        return (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")

    def _key(self) -> tuple[Any, ...]:
        tenant = self.seo.tenant()
        with self.seo.engine().connect() as c:
            p = c.execute(sa.select(sa.func.count(), sa.func.max(PRODUCTS.c.synced_at)).where(
                PRODUCTS.c.tenant_id == tenant)).first()
            b = c.execute(sa.select(sa.func.count(), sa.func.max(CRM_BOOKS.c.synced_at)).where(
                CRM_BOOKS.c.tenant_id == tenant)).first()
        return (tenant, tuple(p or ()), tuple(b or ()), self.site())

    def _rows(self):
        """Etkin ürünler + CRM yayın durumu: (product_id, data, crm_flag), yield ile."""
        from . import EAN

        tenant = self.seo.tenant()
        j = PRODUCTS.outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
        q = (sa.select(PRODUCTS.c.product_id, PRODUCTS.c.data_json, PRODUCTS.c.score, CRM_BOOKS.c.status_flag)
             .select_from(j).where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
             .order_by(PRODUCTS.c.product_id))
        with self.seo.engine().connect() as c:
            for pid, raw, score, flag in c.execution_options(yield_per=500).execute(q):
                yield pid, loads(raw, {}), score, flag

    def _dups(self) -> set[str]:
        return duplicate_gtins(p for _, p, _, _ in self._rows())

    def results(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        key = self._key()
        with self._lock:
            if self._cache and self._cache[0] == key:
                return self._cache[1], self._cache[2]
            site, dups = self.site(), self._dups()
            out: list[dict[str, Any]] = []
            for pid, p, score, flag in self._rows():
                a = audit(p, site, crm_flag=flag, duplicate_gtins=dups)
                out.append({"id": pid, "name": a["name"], "author": a["author"] or None, "url": a["url"],
                            "image": a["image"], "gtin": a["gtin"], "book": a["book"], "price": a["price"],
                            "salePrice": a["salePrice"], "currency": a["currency"], "availability": a["row"]["availability"] or None,
                            "status": a["status"], "issues": a["issues"], "score": score,
                            "sales": _num(p.get("CountTotalSales"))})
            out.sort(key=lambda r: (-r["sales"], r["id"]))
            summ = summarize(out)
            self._cache = (key, out, summ)
            return out, summ

    def feed(self, scope: str) -> tuple[str, int]:
        site, dups = self.site(), self._dups()
        rows = []
        for _, p, _, flag in self._rows():
            a = audit(p, site, crm_flag=flag, duplicate_gtins=dups)
            if scope == "tumu" or (scope == "hazir" and a["status"] == STATUS_READY) or \
                    (scope == "uygun" and a["status"] != STATUS_BLOCKED):
                rows.append(a["row"])
        return feed_tsv(rows), len(rows)


FEED_SCOPES = {"uygun": "engelleyicisi olmayanlar", "hazir": "yalnız hazır olanlar", "tumu": "bütün etkin ürünler"}


def register(app, ctx) -> None:
    seo = ctx.seo
    shop = Shopping(seo)

    @app.get("/api/v1/seo-geo/shopping")
    def seo_shopping(request: Request, issue: str = "", status: str = "", q: str = "", start: int = 0,
                     limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if issue and issue not in ISSUES:
            raise _err(422, "Bilinmeyen sorun türü.")
        if status and status not in STATUSES:
            raise _err(422, "Durum hazır, sorunlu ya da engelleyici olmalı.")
        items, summ = shop.results()
        if issue:
            items = [r for r in items if any(i["code"] == issue for i in r["issues"])]
        if status:
            items = [r for r in items if r["status"] == status]
        if q.strip():
            ql = _tr_lower(q.strip())
            items = [r for r in items if ql in _tr_lower(r["name"] or "") or ql in (r["gtin"] or "")
                     or ql in _tr_lower(r["author"] or "")]
        with seo.engine().connect() as c:
            last = c.execute(sa.select(RUNS.c.finished_at).where(RUNS.c.tenant_id == seo.tenant(), RUNS.c.kind == "tsoft",
                                                                  RUNS.c.error.is_(None))
                             .order_by(RUNS.c.started_at.desc()).limit(1)).scalar()
        start = max(0, start)
        return {"total": len(items), "start": start, "items": items[start:start + max(1, limit)], "summary": summ,
                "lastSync": iso(last), "merchant": bool(seo.conf("MERCHANT_ACCOUNT_ID")),
                "scopes": FEED_SCOPES, "limits": {"title": TITLE_MAX, "description": DESC_MAX},
                "bookCategory": BOOK_CATEGORY}

    @app.get("/api/v1/seo-geo/shopping/feed.tsv")
    def seo_shopping_feed(request: Request, kapsam: str = "uygun") -> Response:
        """Merchant Center'a elle yüklenecek dosya. Hiçbir yere gönderilmez."""
        user = ctx.gate(request)
        if kapsam not in FEED_SCOPES:
            raise _err(422, "Kapsam uygun, hazir ya da tumu olmalı.")
        body, n = shop.feed(kapsam)
        seo.audit(user, "export", "shopping-feed", "Google Alışveriş besleme dosyası", {"scope": kapsam, "rows": n})
        return Response(body, media_type="text/tab-separated-values; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="google-alisveris-{kapsam}.tsv"'})
