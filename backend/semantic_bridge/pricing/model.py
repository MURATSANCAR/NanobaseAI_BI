"""Fiyatlama ve maliyet hesabı (M9) — saf fonksiyonlar, veritabanı yok.

Birim maliyetin ve başabaşın **tek sahibi** burasıdır: ilk baskı tahmini (M10), üretim (M12) ve bütçe (M46)
aynı hesabı istiyorsa `unit_cost()` / `scenario()` çağrılır, formül kopyalanmaz.

Tanımlar (hepsi ₺, KDV hariç; kapak fiyatı KDV dahil yazılır):

- **Baskı birim fiyatı** c(Q) = a + b / Q. «a» adet başına değişen kısım (kâğıt, baskı, cilt), «b» baskıya bir kez
  giren hazırlık (kalıp, ayar). Geçmişteki matbaa faturalarından ölçülür ya da kullanıcı girer. Q = baskı adedi.
- **Sabit giderler** F: kitabın bir kez ödenen giderleri (telif avansı, çeviri, grafik/kapak, redaksiyon, pazarlama,
  diğer). Avans telife mahsup edilir: ödenecek telif = max(avans, oran × satış tabanı); avansı aşan kısım
  değişken telif olur. Bu yüzden avans ayrıca değişken telife eklenmez.
- **Net birim gelir** N = P / (1 + KDV) × (1 − kanal iskontosu). Kanal iskontosu gerçek satıştan ölçülür.
- **Telif (adet başına)** R = oran × taban; taban «kapak» (brüt) = P / (1 + KDV), «net» = N (sözleşmedeki telif türü).
  Sözleşmenin telif tipi «baskıdan ödeme» ise telif basılan adet üzerinden, «satıştan ödeme» ise satılan adet
  üzerinden doğar (CRM `new_TelifTipi`); baskıdan ödemede telif satıştan bağımsız, baskıyla birlikte ödenir.
- **Dağıtım ve diğer değişken gider** t × N (nakliye, komisyon; oran).
- **Başabaş satış adedi** S* = (Q·c(Q) + F) / (N·(1 − t) − R). Basılan her kitabın baskı bedeli satılsın
  satılmasın ödenir; bu yüzden baskı toplamı sabit gibi girer, satılan adet ise ayrı değişkendir.
- **Satış oranı** s: basılanın ne kadarının hesap döneminde satılacağı (varsayılan 1 = hepsi). Kâr, kâr marjı ve
  fiyat önerisi s ile hesaplanır; satılmayan kitap depoda kalan maliyettir.
- **Hedef marja göre fiyat** (marj = kâr / net gelir):
  P = (Q·c + F') · (1 + KDV) / (S·(1 − d)(1 − t − m) − r·k·A) ; k = 1 (kapak tabanı) ya da (1 − d) (net tabanı),
  A = S (satıştan telif) ya da Q (baskıdan telif).
  F' = F − avans (avans telif içinde karşılanır; avans değişken telifi aşıyorsa ayrıca kontrol edilir).
  Payda ≤ 0 ise hedef marj bu gider yapısıyla hiçbir fiyatta tutmaz; sonuç `None` + neden.
- Kapak fiyatı yukarı 5 ₺'ye yuvarlanır (Timaş'ın kapak fiyatlarının tamamı 5'in katı — CRM üretim kayıtlarında ölçüldü).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

#: Aşama 1 baskı adedi senaryoları (iş tanımı).
DEFAULT_QTYS = (1000, 2000, 3000, 5000)
PRICE_STEP = 5.0

FIXED_KEYS = ("avans", "ceviri", "grafik", "redaksiyon", "pazarlama", "diger")
FIXED_LABELS = {
    "avans": "Telif avansı",
    "ceviri": "Çeviri",
    "grafik": "Grafik, çizim ve kapak",
    "redaksiyon": "Redaksiyon ve yayına hazırlık",
    "pazarlama": "Pazarlama",
    "diger": "Diğer sabit gider",
}


@dataclass
class CostInputs:
    """Bir kitabın maliyet girdileri. Oranlar 0–1 arası."""

    print_per_copy: float            # a: adet başına baskı (kâğıt + baskı + cilt), ₺
    print_setup: float = 0.0         # b: baskı başına hazırlık, ₺
    fixed: dict[str, float] = field(default_factory=dict)  # FIXED_KEYS → ₺
    royalty_rate: float = 0.0        # telif oranı
    royalty_base: str = "kapak"      # "kapak" (brüt: KDV hariç kapak fiyatı) | "net" (net satış)
    royalty_on: str = "satis"        # "satis" (satılan adet) | "baski" (basılan adet; «baskıdan ödeme» sözleşmeleri)
    vat: float = 0.10                # kitap KDV oranı
    discount: float = 0.0            # ağırlıklı kanal iskontosu (kapak fiyatına göre)
    variable_rate: float = 0.0       # dağıtım/komisyon, net gelirin oranı
    sell_through: float = 1.0        # basılanın satılan oranı

    def fixed_total(self) -> float:
        return float(sum(max(0.0, float(v or 0)) for v in self.fixed.values()))

    def advance(self) -> float:
        return max(0.0, float(self.fixed.get("avans") or 0))


def print_unit(inp: CostInputs, qty: float) -> float:
    """c(Q) = a + b / Q."""
    if qty <= 0:
        raise ValueError("Baskı adedi sıfırdan büyük olmalı.")
    return inp.print_per_copy + inp.print_setup / qty


def net_unit(price: float, vat: float, discount: float) -> float:
    return price / (1 + vat) * (1 - discount)


def royalty_unit(inp: CostInputs, price: float) -> float:
    base = price / (1 + inp.vat) if inp.royalty_base != "net" else net_unit(price, inp.vat, inp.discount)
    return inp.royalty_rate * base


def unit_cost(inp: CostInputs, qty: float) -> dict[str, float]:
    """Basılan adet başına maliyet (fiyattan bağımsız kısım): baskı + sabit giderlerin payı.
    Telif ve dağıtım satılan adede bağlıdır; `scenario()` onları fiyatla birlikte ekler."""
    c = print_unit(inp, qty)
    fixed = inp.fixed_total()
    parts = {"baski": c, **{k: max(0.0, float(inp.fixed.get(k) or 0)) / qty for k in FIXED_KEYS}}
    return {"perCopy": c + fixed / qty, "print": c, "fixedShare": fixed / qty, "parts": parts}


def scenario(inp: CostInputs, qty: float, price: Optional[float]) -> dict:
    """Bir baskı adedinin bütün tablosu. `price` yoksa yalnız maliyet tarafı."""
    uc = unit_cost(inp, qty)
    print_total = uc["print"] * qty
    fixed = inp.fixed_total()
    adv = inp.advance()
    out: dict = {
        "qty": qty, "printUnit": round(uc["print"], 4), "printTotal": round(print_total, 2),
        "fixedTotal": round(fixed, 2), "unitCost": round(uc["perCopy"], 4),
        "totalCost": round(print_total + fixed, 2), "parts": {k: round(v, 4) for k, v in uc["parts"].items()},
    }
    if price is None or price <= 0:
        return out
    sold = qty * inp.sell_through
    n = net_unit(price, inp.vat, inp.discount)
    r = royalty_unit(inp, price)
    var = inp.variable_rate * n
    on_print = inp.royalty_on == "baski"
    royalty_total = max(adv, r * (qty if on_print else sold))   # avans mahsup edilir
    revenue = n * sold
    # Avans F içinde sayıldı; telifin avansı aşan kısmı eklenir.
    cost = print_total + fixed + (royalty_total - adv) + var * sold
    profit = revenue - cost
    if on_print:  # telif baskıyla ödenir: satıştan bağımsız, sabit gibi
        breakeven = (print_total + fixed - adv + royalty_total) / (n - var) if n - var > 0 else None
    else:
        breakeven = breakeven_units(n, var, r, print_total, fixed, adv)
    out.update({
        "price": price, "netUnit": round(n, 4), "royaltyUnit": round(r, 4), "variableUnit": round(var, 4),
        "sold": round(sold, 2), "revenue": round(revenue, 2), "royaltyTotal": round(royalty_total, 2),
        "profit": round(profit, 2), "margin": round(profit / revenue, 4) if revenue else None,
        "breakeven": None if breakeven is None else math.ceil(breakeven - 1e-9),
        "breakevenShare": None if breakeven is None else round(breakeven / qty, 4),
        "costToPrice": round((uc["perCopy"]) / (price / (1 + inp.vat)), 4),
    })
    return out


def breakeven_units(n: float, var: float, r: float, print_total: float, fixed: float, adv: float) -> Optional[float]:
    """Kârın sıfır olduğu satış adedi. İki bölge: satıştan doğan telif avansın altındaysa telif maliyeti avanstır
    (zaten F içinde), üstündeyse her adet r kadar telif öder ve avans mahsup edilir."""
    if n - var <= 0:
        return None
    s1 = (print_total + fixed) / (n - var)
    if r * s1 <= adv + 1e-9:
        return s1
    if n - var - r <= 0:
        return None
    return (print_total + fixed - adv) / (n - var - r)


def price_for_margin(inp: CostInputs, qty: float, target_margin: float) -> dict:
    """Hedef kâr marjını (net gelire oranla) veren en düşük kapak fiyatı (KDV dahil, 5 ₺'ye yukarı)."""
    sold = qty * inp.sell_through
    if sold <= 0:
        return {"price": None, "reason": "Satış oranı sıfır; fiyat hesaplanamaz."}
    d, t, m, v = inp.discount, inp.variable_rate, target_margin, inp.vat
    k = 1.0 if inp.royalty_base != "net" else (1 - d)
    royalty_qty = qty if inp.royalty_on == "baski" else sold
    denom = sold * (1 - d) * (1 - t - m) - inp.royalty_rate * k * royalty_qty
    base_cost = print_unit(inp, qty) * qty + inp.fixed_total() - inp.advance()
    if denom <= 0:
        return {"price": None, "reason": "Bu iskonto, telif ve gider oranlarıyla hedef marj hiçbir fiyatta tutmuyor."}
    raw = base_cost * (1 + v) / denom
    price = round_price(raw)
    # Avans, satıştan doğan telifi aşıyorsa telif maliyeti avanstır: fiyatı o koşulla yeniden bul.
    for _ in range(200):
        sc = scenario(inp, qty, price)
        if sc["margin"] is not None and sc["margin"] >= m - 1e-9:
            break
        price += PRICE_STEP
    return {"price": price, "raw": round(raw, 2), "reason": None}


def round_price(p: float, step: float = PRICE_STEP) -> float:
    return float(math.ceil(p / step - 1e-9) * step)


def quantile(values: Iterable[float], q: float) -> Optional[float]:
    xs = sorted(float(x) for x in values if x is not None)
    if not xs:
        return None
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def fit_print_curve(points: Iterable[tuple[float, float]]) -> Optional[dict]:
    """Geçmiş (adet, baskı birim fiyatı) çiftlerinden c(Q) = a + b/Q en küçük kareler uydurması.
    En az 3 nokta ve iki farklı adet gerekir. a < 0 ya da b < 0 çıkarsa (veri bu şekli taşımıyor) yalnız ortalama."""
    pts = [(float(q), float(c)) for q, c in points if q and q > 0 and c and c > 0]
    if len(pts) < 3 or len({q for q, _ in pts}) < 2:
        return None
    xs = [1 / q for q, _ in pts]
    ys = [c for _, c in pts]
    n = len(pts)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx else 0.0
    a = my - b * mx
    if a <= 0 or b < 0:
        return {"a": round(my, 4), "b": 0.0, "n": n, "shape": "ortalama"}
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    ss_res = sum(e * e for e in resid)
    ss_tot = sum((y - my) ** 2 for y in ys)
    return {"a": round(a, 4), "b": round(b, 2), "n": n, "shape": "a+b/Q",
            "r2": round(1 - ss_res / ss_tot, 4) if ss_tot else None}


def recommend(inp: CostInputs, qty: float, target_margin: float, comparables: list[float]) -> dict:
    """Önerilen kapak fiyatı aralığı: alt sınır maliyetten (hedef marj), pazar bandı emsal kitaplardan (P25–P75).
    Öneri = alt sınır ile emsal ortancasının büyüğü; alt sınır emsal üst çeyreğini aşıyorsa uyarı."""
    floor = price_for_margin(inp, qty, target_margin)
    p25, p50, p75 = (quantile(comparables, q) for q in (0.25, 0.5, 0.75))
    notes: list[str] = []
    if floor["price"] is None:
        return {"floor": None, "floorReason": floor["reason"], "band": [p25, p75], "median": p50, "price": None,
                "notes": [floor["reason"]]}
    price = floor["price"]
    if p50 is not None and p50 > price:
        price = round_price(p50)
        notes.append("Emsal kitapların ortancası maliyet alt sınırının üstünde; öneri emsal ortancası.")
    elif p50 is not None:
        notes.append("Maliyet alt sınırı emsal ortancasının üstünde; öneri alt sınır.")
    if p75 is not None and floor["price"] > p75:
        notes.append("Hedef marjı veren fiyat emsallerin üst çeyreğini aşıyor: adedi, gideri ya da marj hedefini gözden geçirin.")
    if p50 is None:
        notes.append("Emsal fiyat yok; öneri yalnız maliyetten.")
    return {"floor": floor["price"], "floorReason": None, "band": [p25, p75], "median": p50, "price": price,
            "notes": notes}
