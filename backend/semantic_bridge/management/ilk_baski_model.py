"""M10 İlk baskı ve satış tahmini — hesap çekirdeği (veritabanı ve ağ yok; saf fonksiyonlar).

Yeni kitabın satışı, ona benzeyen ve daha önce çıkmış kitapların («emsal») ilk aylarındaki gerçek satışından
tahmin edilir:

1. Lansman: kitabın Logo'daki ilk net satış ayı (CRM ilk yayın ayıyla en çok ±LAUNCH_TOLERANCE ay farkla; daha büyük
   fark başka baskının/kodun devamıdır, emsal havuzuna girmez). İlk satış 2015 başına yapışıksa geçmişi kesiktir, girmez.
2. Emsal puanı: CRM'de editörün girdiği emsal, aynı yazar, aynı dizi, aynı kitaplık, aynı yayınevi, aynı hedef kitle,
   tür örtüşmesi, fiyat ve sayfa yakınlığı; yakın zamanda çıkanın ağırlığı büyük. Ağırlıklar `PARAMS`'ta, geçmiş
   sınamada seçildi (bkz. `docs/analiz/ilk-baski-tahmini/`).
3. Tahmin: en yüksek puanlı K emsalin ilk 6 / 12 aylık satışının puan ağırlıklı ortancası (baz). Emsalin çıktığı
   dönem ile yeni kitabın döneminin pazar düzeyi farklıysa (okul dönemi, büyüme), portföy toplamının oranıyla
   düzeltilir; yeni kitabın dönemi gelecekteyse portföy düzeyi ZEKİ AI tahmin modelinden gelir.
4. Senaryolar ve güven aralığı: geçmiş sınamadaki gerçekleşen/tahmin oranlarının dağılımından (kalibre edilmiş;
   emsal sayısı az ya da zayıfsa aralık geniş).

Aşama 2 (ilk satış takibi): kitap çıktıktan sonra gerçekleşen ilk aylar emsallerin aynı aylarından sonraki
büyümesiyle ileri taşınır (revize tahmin).
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

DATA_START = 2015 * 12  # Logo yıllık satış görünümlerinin ilki: Ocak 2015
LAUNCH_TOLERANCE = 3    # CRM ilk yayın ayı ile ilk satış ayı arasındaki en büyük fark (ay)

# Geçmiş sınamada seçilen ayarlar, ufuk başına (2026-09-28; koordinat inişi, amaç ortanca |log(gerçek/tahmin)|,
# seçim dönemi 2021-07…2023-12 lansmanları; sınama 2024+ lansmanları seçimde kullanılmadı). Ayrıntı:
# docs/analiz/ilk-baski-tahmini/README.md. `beta` pazar düzeyi düzeltmesinin üssü: tahmin servisinin portföy
# tahminiyle denendi, iki ufukta da iyileştirmedi (0 seçildi).
PARAMS: dict[int, dict[str, float]] = {
    6: {"w_emsal": 6, "w_author": 1, "w_series": 2, "w_library": 0.5, "w_publisher": 0.5, "w_audience": 0,
        "w_genre": 0, "w_price": 1, "w_pages": 0.5, "base": 0.05, "tau_years": 3.0, "k": 15, "beta": 0.0},
    12: {"w_emsal": 6, "w_author": 2, "w_series": 2, "w_library": 0, "w_publisher": 1, "w_audience": 0,
         "w_genre": 0.5, "w_price": 2, "w_pages": 0.5, "base": 0.05, "tau_years": 3.0, "k": 10, "beta": 0.0},
}


def params_for(h: int, p: dict | None = None) -> dict:
    """Ufkun ayarları: `p` ufuk → ayar sözlüğü (JSON'dan gelince anahtar metin) ya da doğrudan ayar sözlüğü."""
    src = p if p is not None else PARAMS
    if "k" in src:
        return src
    return src.get(h) or src.get(str(h)) or PARAMS[6]


# Senaryo kantilleri: kötümser / baz / iyimser ve güven aralığı (%80).
SCENARIOS = (("kotumser", "Kötümser", 0.2), ("baz", "Baz", 0.5), ("iyimser", "İyimser", 0.8))
BAND = (0.1, 0.9)

# Logo KANAL değerleri → ekrandaki kanal adı. Listede olmayan kanal kendi adıyla gösterilir (sessizce kaybolmaz).
CHANNELS: dict[str, str] = {
    "KITAPCI": "Kitapçı", "ZINCIR": "Kitabevi zinciri", "ZİNCİR MAĞ": "Kitabevi zinciri", "DAGITICI": "Bölgesel dağıtım",
    "E-TICARET": "E-ticaret", "KURUM": "Kurum ve okul", "HAVUZ": "Kurum ve okul", "FUAR": "Fuar",
    "YURTDIŞI": "İhracat", "MAGAZA": "Mağaza ve perakende", "PERAKENDE": "Mağaza ve perakende",
    "YAZAR": "Yazar", "MARKET": "Diğer", "PERSONEL": "Diğer", "TUKETICI": "Mağaza ve perakende", "DIGER": "Diğer",
}

AY = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def mi(y: int | str, m: int | str) -> int:
    return int(y) * 12 + int(m) - 1


def ms(i: int) -> str:
    return f"{i // 12}-{i % 12 + 1:02d}"


def month_name(i: int) -> str:
    return f"{AY[i % 12]} {i // 12}"


def month_of(value: Any) -> int | None:
    """'2026-03-14' / date → ay indeksi."""
    if value is None or value == "":
        return None
    s = value.isoformat() if isinstance(value, date) else str(value)
    if len(s) < 7 or not s[:4].isdigit():
        return None
    return mi(s[:4], s[5:7])


_TR = str.maketrans("İIıŞşĞğÜüÖöÇçÂâÎîÛû", "iiissgguuooccaaiiuu")


def norm(s: Any) -> str:
    if s is None:
        return ""
    t = str(s).translate(_TR).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def parts(s: Any) -> frozenset[str]:
    """Birden çok değerli metin (yazarlar, türler): virgül, noktalı virgül, '&', ' ve ' ile ayrılır."""
    if not s:
        return frozenset()
    raw = re.split(r"[,;/&|]| ve ", str(s))
    return frozenset(p for p in (norm(x) for x in raw) if len(p) > 1)


def num(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 0 and math.isfinite(x) else None


def channel_label(k: str) -> str:
    return CHANNELS.get(str(k or "").strip().upper(), str(k or "Diğer").strip().title() or "Diğer")


@dataclass
class Book:
    code: str
    name: str = ""
    publisher: str = ""
    library: str = ""
    series: str = ""
    authors_text: str = ""
    audience: str = ""
    genre_text: str = ""
    pages: float | None = None
    price: float | None = None
    first_pub: str | None = None      # CRM ilk yayın günü (İstanbul)
    status: str = ""
    active: bool = True
    target: int | None = None         # CRM ilk yıl satış hedefi
    # türetilenler
    authors: frozenset[str] = frozenset()
    genres: frozenset[str] = frozenset()
    n_publisher: str = ""
    n_library: str = ""
    n_series: str = ""
    n_audience: str = ""
    launch: int | None = None         # lansman ayı (ilk net satış ayı)
    valid_launch: bool = False        # emsal havuzuna girebilir mi

    def finish(self) -> "Book":
        self.authors = parts(self.authors_text)
        self.genres = parts(self.genre_text)
        self.n_publisher, self.n_library = norm(self.publisher), norm(self.library)
        self.n_series, self.n_audience = norm(self.series), norm(self.audience)
        return self

    def public(self) -> dict:
        return {"code": self.code, "name": self.name, "publisher": self.publisher or None, "library": self.library or None,
                "series": self.series or None, "authors": self.authors_text or None, "audience": self.audience or None,
                "genre": self.genre_text or None, "pages": self.pages, "price": self.price, "firstPub": self.first_pub,
                "status": self.status or None, "launch": ms(self.launch) if self.launch is not None else None,
                "salesTarget": self.target}


def book_from_record(r: dict) -> Book:
    return Book(
        code=str(r.get("stok_kodu") or "").strip(), name=str(r.get("ad") or "").strip(),
        publisher=str(r.get("yayinevi") or "").strip(), library=str(r.get("kitaplik") or "").strip(),
        series=str(r.get("dizi") or "").strip(), authors_text=str(r.get("yazar") or "").strip(),
        audience=str(r.get("hedef_kitle") or "").strip(), genre_text=str(r.get("tur") or "").strip(),
        pages=num(r.get("sayfa")), price=num(r.get("fiyat")),
        first_pub=str(r["ilk_yayin"])[:10] if r.get("ilk_yayin") else None,
        status=str(r.get("statu") or "").strip(), active=int(r.get("kart_durumu") or 0) == 0,
        target=int(r["ilk_yil_hedefi"]) if num(r.get("ilk_yil_hedefi")) else None,
    ).finish()


@dataclass
class Outcome:
    """Bir lansmanın ilk 12 ayı (ay 0 = lansman ayı)."""
    months: list[float]                  # 12 aylık net adet (gözlenmeyen ay None değil, eksikse liste kısa)
    channels: dict[str, float]           # ilk 6 ay, kanal → adet
    net: float                           # ilk 6 ay net tutar
    listv: float                         # ilk 6 ay liste tutarı

    def total(self, h: int) -> float | None:
        return sum(self.months[:h]) if len(self.months) >= h else None


@dataclass
class Dataset:
    books: dict[str, Book]
    sales: dict[str, dict[int, float]]
    portfolio: dict[int, float]
    end: int                              # son tam ay
    emsal: dict[str, list[str]]
    outcomes: dict[str, Outcome] = field(default_factory=dict)
    price_median: dict[int, float] = field(default_factory=dict)   # lansman yılı → fiyat ortancası
    by_launch: list[str] = field(default_factory=list)             # geçerli lansmanlar, lansman ayına göre


def build_dataset(kitaplar: Iterable[dict], emsal: Iterable[dict], sales_rows: Iterable[dict], end: int) -> Dataset:
    """Kaynak satırlarından veri kümesi. `end` son tam ay; ondan sonraki satış (yarım ay) kullanılmaz."""
    books: dict[str, Book] = {}
    for r in kitaplar:
        b = book_from_record(r)
        if not b.code:
            continue
        old = books.get(b.code)
        # Aynı stok kodunda birden çok kart: etkin ve ilk yayını dolu olan tercih edilir.
        if old is None or (b.active, bool(b.first_pub)) > (old.active, bool(old.first_pub)):
            books[b.code] = b
    sales: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    chan: dict[str, dict[int, dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    money: dict[str, dict[int, list[float]]] = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0]))
    portfolio: dict[int, float] = defaultdict(float)
    for r in sales_rows:
        m = mi(r["yil"], r["ay"])
        if m > end:
            continue
        k = str(r["stok_kodu"]).strip()
        q = float(r.get("miktar") or 0)
        sales[k][m] += q
        portfolio[m] += q
        chan[k][m][channel_label(r.get("kanal"))] += q
        mm = money[k][m]
        mm[0] += float(r.get("net_tutar") or 0)
        mm[1] += float(r.get("liste_tutar") or 0)
    em: dict[str, list[str]] = defaultdict(list)
    for r in emsal:
        a, b = str(r["stok_kodu"]).strip(), str(r["emsal_stok_kodu"]).strip()
        if a and b and a != b and b not in em[a]:
            em[a].append(b)
    ds = Dataset(books=books, sales={k: dict(v) for k, v in sales.items()}, portfolio=dict(portfolio), end=end, emsal=dict(em))
    prices: dict[int, list[float]] = defaultdict(list)
    for k, b in books.items():
        s = ds.sales.get(k)
        b.launch, b.valid_launch = launch_of(b, s)
        if not b.valid_launch:
            continue
        L = b.launch
        months = [s.get(L + j, 0.0) for j in range(12) if L + j <= end]
        ch: dict[str, float] = defaultdict(float)
        net = lst = 0.0
        for j in range(6):
            for c, q in chan[k].get(L + j, {}).items():
                ch[c] += q
            mm = money[k].get(L + j)
            if mm:
                net += mm[0]
                lst += mm[1]
        ds.outcomes[k] = Outcome(months=months, channels=dict(ch), net=net, listv=lst)
        if b.price:
            prices[L // 12].append(b.price)
    ds.price_median = {y: _median(v) for y, v in prices.items() if v}
    ds.by_launch = sorted(ds.outcomes, key=lambda c: books[c].launch)
    return ds


# Basılı kitap stok kodları. Ölçüm 2026-09-28 (CRM `powerbikitap.Tip` ile): 15201 = kitap (7.873 «Kitap» kaydı),
# 15205/15206 = set ve toplama set (bağımsız basılmaz), 15204/15304 = dergi sayısı, 157xx = e-kitap, sesli kitap,
# öğretmen kılavuzu, bülten (Logo satış görünümü zaten dışarıda tutar), 15301/15305 = ticari ürün. İlk baskı
# tahmini yalnız kitapları emsal havuzuna ve «yayımlanacak» listesine alır.
BOOK_CODE_PREFIXES = ("15201",)


def is_book(code: str) -> bool:
    return str(code).startswith(BOOK_CODE_PREFIXES)


def launch_of(b: Book, s: dict[int, float] | None) -> tuple[int | None, bool]:
    """(lansman ayı, emsal olabilir mi). Satışı yoksa lansman CRM ilk yayın ayıdır ama emsal olamaz."""
    crm = month_of(b.first_pub)
    if not is_book(b.code):
        first = min((m for m, q in (s or {}).items() if q > 0), default=crm)
        return first, False
    pos = [m for m, q in (s or {}).items() if q > 0]
    if not pos:
        return crm, False
    first = min(pos)
    if first <= DATA_START + 1:  # satış 2015 başından beri var: lansman gözlenmedi
        return first, False
    if crm is not None and abs(first - crm) > LAUNCH_TOLERANCE:
        return first, False
    return first, True


def _median(v: list[float]) -> float:
    v = sorted(v)
    n = len(v)
    return v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def wquantile(values: list[float], weights: list[float], q: float) -> float:
    """Ağırlıklı kantil (doğrusal ara değer, ağırlık merkezleri)."""
    pairs = sorted(zip(values, weights))
    tot = sum(w for _, w in pairs)
    if tot <= 0:
        return _median(values)
    acc, pts = 0.0, []
    for v, w in pairs:
        pts.append(((acc + w / 2) / tot, v))
        acc += w
    if q <= pts[0][0]:
        return pts[0][1]
    for (p0, v0), (p1, v1) in zip(pts, pts[1:]):
        if q <= p1:
            return v0 + (v1 - v0) * ((q - p0) / (p1 - p0) if p1 > p0 else 0)
    return pts[-1][1]


def _near(a: float | None, b: float | None, scale: float = 0.3) -> float:
    if not a or not b:
        return 0.0
    return math.exp(-abs(math.log(a / b)) / scale)


def rel_price(ds: Dataset, price: float | None, month: int | None) -> float | None:
    """Fiyat, çıktığı yılın lansman fiyatı ortancasına oranla (enflasyondan arınır)."""
    if not price or month is None:
        return None
    y = month // 12
    med = ds.price_median.get(y) or ds.price_median.get(y - 1) or ds.price_median.get(max(ds.price_median, default=y))
    return price / med if med else None


def similarity(ds: Dataset, t: Book, t_month: int, a: Book, p: dict, emsal: set[str]) -> tuple[float, list[str]]:
    """Emsal puanı ve gerekçesi (ekranda gösterilir)."""
    s, why = p["base"], []
    if a.code in emsal:
        s += p["w_emsal"]; why.append("CRM emsali")
    if t.authors and a.authors and t.authors & a.authors:
        s += p["w_author"]; why.append("aynı yazar")
    if t.n_series and t.n_series == a.n_series:
        s += p["w_series"]; why.append("aynı dizi")
    if t.n_library and t.n_library == a.n_library:
        s += p["w_library"]; why.append("aynı kitaplık")
    if t.n_publisher and t.n_publisher == a.n_publisher:
        s += p["w_publisher"]; why.append("aynı yayınevi")
    if t.n_audience and t.n_audience == a.n_audience:
        s += p["w_audience"]; why.append("aynı hedef kitle")
    if t.genres and a.genres:
        j = len(t.genres & a.genres) / len(t.genres | a.genres)
        if j > 0:
            s += p["w_genre"] * j; why.append("benzer tür")
    pr = _near(rel_price(ds, t.price, t_month), rel_price(ds, a.price, a.launch))
    if pr > 0.5:
        why.append("benzer fiyat")
    s += p["w_price"] * pr
    pg = _near(t.pages, a.pages)
    if pg > 0.5:
        why.append("benzer sayfa sayısı")
    s += p["w_pages"] * pg
    age = max(0, t_month - (a.launch or t_month)) / 12
    return s * math.exp(-age / p["tau_years"]), why


def market_factor(ds: Dataset, a_launch: int, t_launch: int, h: int, level: dict[int, float] | None) -> float:
    """Yeni kitabın dönemindeki portföy düzeyi ÷ emsalin dönemindeki. `level` gelecek ayların tahminini de taşır."""
    src = level or ds.portfolio

    def window(start: int) -> float | None:
        vals = [src.get(start + j) for j in range(h)]
        return sum(vals) if all(v is not None for v in vals) else None

    num_, den = window(t_launch), window(a_launch)
    if not num_ or not den or num_ <= 0 or den <= 0:
        return 1.0
    return num_ / den


@dataclass
class Forecast:
    h: int
    base: float
    analogs: list[dict]
    values: list[float]
    weights: list[float]
    strength: float  # emsal gücü: puanların toplamı (güven düzeyi)


def pool_for(ds: Dataset, cutoff: int, h: int) -> list[str]:
    """Kesimde ilk h ayı tamamen gözlenmiş lansmanlar."""
    return [c for c in ds.by_launch if ds.books[c].launch + h - 1 <= cutoff and (ds.outcomes[c].total(h) or 0) > 0]


def forecast(ds: Dataset, t: Book, t_launch: int, cutoff: int, h: int, p: dict | None = None,
             level: dict[int, float] | None = None, pool: list[str] | None = None, emsal: list[str] | None = None) -> Forecast | None:
    p = params_for(h, p)
    em = set(emsal if emsal is not None else ds.emsal.get(t.code, []))
    scored = []
    for c in pool if pool is not None else pool_for(ds, cutoff, h):
        if c == t.code:
            continue
        a = ds.books[c]
        s, why = similarity(ds, t, t_launch, a, p, em)
        scored.append((s, c, why))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    top = scored[: int(p["k"])]
    vals, wts, rows = [], [], []
    for s, c, why in top:
        a = ds.books[c]
        y = ds.outcomes[c].total(h)
        f = market_factor(ds, a.launch, t_launch, h, level) ** p["beta"] if p["beta"] else 1.0
        vals.append(y * f)
        wts.append(s)
        rows.append({"code": c, "name": a.name, "authors": a.authors_text or None, "publisher": a.publisher or None,
                     "library": a.library or None, "launch": ms(a.launch), "score": round(s, 3), "reasons": why,
                     "sales": round(y), "adjusted": round(y * f), "factor": round(f, 3)})
    return Forecast(h=h, base=wquantile(vals, wts, 0.5), analogs=rows, values=vals, weights=wts,
                    strength=sum(w for w in wts))


def confidence_tier(fc: Forecast, p: dict | None = None) -> str:
    """Emsal gücüne göre güven: güçlü eşleşmeli emsal (CRM emsali / aynı yazar / dizi) varsa yüksek."""
    strong = sum(1 for a in fc.analogs if {"CRM emsali", "aynı yazar", "aynı dizi"} & set(a["reasons"]))
    if strong >= 3:
        return "yuksek"
    if strong >= 1:
        return "orta"
    return "dusuk"


def revise(ds: Dataset, fc: Forecast, actual: list[float], h: int) -> float | None:
    """Aşama 2: gerçekleşen ilk m ay × emsallerin m. aydan h. aya büyüme oranı (puan ağırlıklı ortanca)."""
    m = len(actual)
    if m == 0:
        return fc.base
    got = sum(actual)
    vals, wts = [], []
    for a, w in zip(fc.analogs, fc.weights):
        o = ds.outcomes[a["code"]]
        early = sum(o.months[:m])
        full = o.total(h)
        if early > 0 and full:
            vals.append(got * full / early)
            wts.append(w)
    if not vals:
        return None
    return max(got, wquantile(vals, wts, 0.5))
