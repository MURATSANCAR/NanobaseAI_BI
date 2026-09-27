"""M6 Sözleşmeler: hakediş (telif) hesabı.

Hesap tek yöndür: sözleşme şartları + kaynaktan okunan adet/tutar → satırlar → brüt telif → avans mahsubu →
stopaj → ödenecek net. Kaynak:

- **Satış** Logo'nun yıllık satış görünümlerinden (`V_SatisRaporu_<yıl>`, yalnız faturalı satır; bkz.
  `management.expand_sales`) kitabın stok kodu (CRM `new_kitap.new_StokKodu` = Logo `[Malzeme/Hizmet Kodu]`)
  ile okunur. Dönem ay sınırındadır (`Yıl*12+Ay`; tarih aralığı planı bozar). İade satırları düşülür.
- **Baskı** adedi kaynakta tutulmadığı için hakediş açılırken kitap başına girilir (ekranda yazılır).

Matrah: net esasta dönemin net satış tutarı; brüt esasta adet × kapak (liste) fiyatı. İskonto verilmişse matrah
o oranda azalır. Kademeli ödemede oran, sözleşme başından bu yana birikmiş adede göre dilim dilim uygulanır.
Taraflara pay oranında bölünür. Sözleşme yabancı para birimindeyse dönem sonundaki Logo kuru ile çevrilir;
kur ekranda girilir ya da TCMB'nin o günkü döviz alış kurundan okunur; kur yoksa tutar TL kalır ve
uyarı yazılır (avans mahsubu yapılmaz).

Buradaki `compute` saf bir işlevdir: veritabanına dokunmaz, girdiyi aynı verince aynı sonucu verir.
"""
from __future__ import annotations

import calendar
import hashlib
import json
from datetime import date
from typing import Any, Optional

from semantic_bridge import contracts_terms as T

SALES_FILTER = "s.[Satır Türü] = N'Malzeme'"


# ------------------------------------------------------------------------------------------ dönem

def month_bounds(start: str, end: str) -> tuple[date, date]:
    """Dönem ay sınırına oturmalı: başlangıç ayın ilk günü, bitiş ayın son günü."""
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        raise T.ContractError("Dönem tarihleri YYYY-AA-GG biçiminde olmalı.") from None
    if a.day != 1:
        raise T.ContractError("Dönem ayın ilk günü başlamalı (satış ay ay okunur).")
    if b.day != calendar.monthrange(b.year, b.month)[1]:
        raise T.ContractError("Dönem ayın son günü bitmeli (satış ay ay okunur).")
    if b < a:
        raise T.ContractError("Dönem bitişi başlangıçtan önce olamaz.")
    if (b.year - a.year) * 12 + b.month - a.month >= 36:
        raise T.ContractError("Bir hakediş dönemi en çok 36 ay olabilir.")
    return a, b


def periods(terms: dict[str, Any], upto: date) -> list[tuple[date, date]]:
    """Sözleşme başından `upto`ya kadar dönem sınırları (ödeme takvimi önerisi için)."""
    if not terms.get("start"):
        return []
    s = date.fromisoformat(terms["start"])
    s = date(s.year, s.month, 1)
    step = int(terms.get("periodMonths") or 6)
    end_limit = date.fromisoformat(terms["end"]) if terms.get("end") else upto
    out = []
    while s <= min(upto, end_limit) and len(out) < 400:
        m = s.month - 1 + step
        e_year, e_month = s.year + m // 12, m % 12 + 1
        nxt = date(e_year, e_month, 1)
        last = date.fromordinal(nxt.toordinal() - 1)
        out.append((s, last))
        s = nxt
    return out


def ym(d: date) -> int:
    return d.year * 12 + d.month


# ------------------------------------------------------------------------------------------ SQL

def _values(codes: list[str]) -> str:
    return ", ".join("(N'" + str(c).replace("'", "''") + "')" for c in codes)


def sales_sql(codes: list[str], a: date, b: date) -> str:
    """Stok kodu × satış/iade: adet, net tutar, adet × birim fiyat. `{satis:Y-Y}` yer tutucusu köprüde açılır."""
    if not codes:
        raise T.ContractError("Stok kodu olmadan satış okunamaz.")
    return (
        "SELECT s.[Malzeme/Hizmet Kodu] AS kod, s.[Satis_Iade] AS tur, SUM(s.[Miktar]) AS miktar,"
        " SUM(s.[Net Tutar]) AS net, SUM(s.[Miktar] * s.[Birim Fiyat]) AS liste"
        f" FROM {{satis:{a.year}-{b.year}}} AS s"
        f" JOIN (VALUES {_values(codes)}) AS kod(k) ON kod.k = s.[Malzeme/Hizmet Kodu]"
        f" WHERE s.[Yıl] * 12 + s.[Ay] BETWEEN {ym(a)} AND {ym(b)} AND {SALES_FILTER}"
        " GROUP BY s.[Malzeme/Hizmet Kodu], s.[Satis_Iade]"
    )


def data_end_sql(year: int) -> str:
    """Logo satışının son fatura günü (veri nereye kadar)."""
    return f"SELECT TOP 1 [Fatura Tarihi] AS son FROM dbo.V_SatisRaporu_{int(year)} ORDER BY [Fatura Tarihi] DESC"


#: Döviz kuru TCMB'nin açık günlük kur dosyasından (döviz alış) okunur. 2026-09-27 ölçümü: Logo'nun kur tabloları
#: seyrek (`LG_EXCHANGE_211`: 2021–2025 arasında USD için 29 gün, `L_DAILYEXCHANGES` yalnız bir tür), hakediş
#: kuru için güvenilir değil. Hafta sonu ve tatilde dosya yok (404); en çok 10 gün geriye gidilir.
TCMB_URL = "https://www.tcmb.gov.tr/kurlar/{ym}/{dmy}.xml"


def tcmb_rate(currency: str, on: date, fetch) -> Optional[dict[str, Any]]:
    """`on` gününe ya da önceki son iş gününe ait döviz alış kuru. `fetch(url) -> (durum, metin)`."""
    import re as _re
    for back in range(0, 11):
        d = date.fromordinal(on.toordinal() - back)
        status, text = fetch(TCMB_URL.format(ym=d.strftime("%Y%m"), dmy=d.strftime("%d%m%Y")))
        if status != 200 or not text:
            continue
        m = _re.search(r'CurrencyCode="%s">(.*?)</Currency>' % _re.escape(currency), text, _re.S)
        if not m:
            return None
        unit = _re.search(r"<Unit>([\d.]+)</Unit>", m.group(1))
        buy = _re.search(r"<ForexBuying>([\d.]+)</ForexBuying>", m.group(1))
        if not buy:
            return None
        rate = float(buy.group(1)) / float(unit.group(1) if unit else 1)
        return {"rate": rate, "on": d.isoformat(), "source": "TCMB döviz alış"}
    return None


def fold_sales(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Satış/iade satırlarını kitap başına toplar. İade adet ve tutarı düşer (görünüm işaretiyle ya da
    işaretsiz tutsa da)."""
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        code = str(r.get("kod") or "").strip()
        if not code:
            continue
        ret = str(r.get("tur") or "").strip().lower().startswith("iade")
        acc = out.setdefault(code, {"qty": 0.0, "net": 0.0, "list": 0.0, "retQty": 0.0})
        q, n, l = (float(r.get(k) or 0) for k in ("miktar", "net", "liste"))
        if ret:
            q, n, l = -abs(q), -abs(n), -abs(l)
            acc["retQty"] += -q
        acc["qty"] += q
        acc["net"] += n
        acc["list"] += l
    return out


# ------------------------------------------------------------------------------------------ hesap

def _tiered(rate_flat: float, tiers: list[dict[str, Any]], before: float, qty: float) -> list[tuple[float, float]]:
    """(adet, oran) dilimleri. Kademe yoksa tek dilim; adet eksiyse (iade) dilim birikmişin tepesinden geri sayılır."""
    if not tiers:
        return [(qty, rate_flat)]
    lo, hi = (before, before + qty) if qty >= 0 else (before + qty, before)
    parts = []
    for i, t in enumerate(tiers):
        a = t["from"]
        b = tiers[i + 1]["from"] if i + 1 < len(tiers) else float("inf")
        seg = max(0.0, min(hi, b) - max(lo, a))
        if seg:
            parts.append((seg if qty >= 0 else -seg, t["rate"]))
    return parts or [(qty, tiers[0]["rate"])]


def compute(terms: dict[str, Any], *, period_start: str, period_end: str,
            sales: dict[str, dict[str, float]], prior_qty: Optional[dict[str, float]] = None,
            prints: Optional[dict[str, float]] = None, list_prices: Optional[dict[str, float]] = None,
            advance_used: float = 0.0, carry_in: float = 0.0, fx: Optional[dict[str, Any]] = None,
            data_end: Optional[str] = None) -> dict[str, Any]:
    """Bir dönemin hakedişi. `sales` stok kodu → {qty, net, list}; `prints` stok kodu → basılan adet;
    `list_prices` stok kodu → elle verilen kapak fiyatı; `prior_qty` kademeler için dönem öncesi birikmiş adet;
    `advance_used` önceki onaylı hakedişlerde avanstan düşülen; `carry_in` önceki dönemden devreden eksi tutar."""
    a, b = month_bounds(period_start, period_end)
    pt = terms.get("paymentType") or "satis"
    cur = terms.get("currency") or "TRY"
    basis = terms.get("basis") or "net"
    rates = terms.get("rates") or {}
    tiers = (terms.get("tiers") or []) if pt in T.TIERED else []
    disc = float(terms.get("discountPct") or 0) / 100
    prior_qty = prior_qty or {}
    prints = prints or {}
    list_prices = list_prices or {}
    warns: list[str] = []
    if pt not in T.SALES_BASED + T.PRINT_BASED:
        raise T.ContractError(f"«{T.PAYMENT_TYPES.get(pt, pt)}» sözleşmede hakediş hesaplanmaz; ödeme takvimine tutar olarak girilir.")
    if basis == "degisken":
        warns.append("Telif esası «değişken»; net satış tutarı üzerinden hesaplandı, sözleşme maddesine göre kontrol edin.")
    if data_end and data_end < b.isoformat():
        warns.append(f"Logo satışı {T.day_tr(data_end)} gününe kadar; dönemin bu günden sonrası eksik okunmuş olabilir.")

    parties = [p for p in terms.get("parties") or []]
    shares = [p.get("share") for p in parties]
    if not parties:
        payees = [("Hak sahibi", 1.0)]
    elif all(s is None for s in shares):
        payees = [(p["name"], 1 / len(parties)) for p in parties]
        if len(parties) > 1:
            warns.append("Taraf payları girilmemiş; telif taraflara eşit bölündü.")
    else:
        payees = [(p["name"], float(p.get("share") or 0) / 100) for p in parties]
        tot = sum(s for _, s in payees)
        if abs(tot - 1) > 0.0001:
            warns.append(f"Taraf payları toplamı %{T.fmt_num(tot * 100)}; bölüşüm bu paylarla yapıldı.")

    books = [bk for bk in terms.get("books") or []]
    if not books:
        raise T.ContractError("Sözleşmeye kitap bağlanmamış; hakediş hesaplanamaz.")
    lines: list[dict[str, Any]] = []
    total_qty = 0.0
    total_base = 0.0

    def rate_for(fmt: str) -> Optional[float]:
        r = rates.get(fmt)
        if r is None and fmt != "karton":
            r = rates.get("karton")
            if r is not None:
                warns.append(f"{T.RATE_KEYS.get(fmt, fmt)} oranı yok; karton kapak oranı kullanıldı.")
        return r

    for bk in books:
        code = bk.get("stockCode")
        title = bk["title"]
        fmt = bk.get("format") or "karton"
        flat = rate_for(fmt)
        if flat is None and not tiers:
            warns.append(f"«{title}» için telif oranı yok; satır hesaplanmadı.")
            continue
        if not code:
            warns.append(f"«{title}» kitabının stok kodu yok; satışı okunamadı.")
            continue
        comps: list[tuple[str, float, float]] = []   # (kaynak, adet, birim matrah)
        if pt in T.SALES_BASED:
            s = sales.get(code) or {"qty": 0.0, "net": 0.0, "list": 0.0, "retQty": 0.0}
            qty = s["qty"]
            if basis == "brut":
                price = list_prices.get(code) or bk.get("listPrice")
                if price is None:
                    price = (s["list"] / qty) if qty else 0.0
                    if qty:
                        warns.append(f"«{title}» kapak fiyatı girilmemiş; Logo satış satırlarındaki birim fiyatın ortalaması ({T.fmt_num(price)}) kullanıldı.")
                base_amt = qty * float(price)
            else:
                base_amt = s["net"]
            comps.append(("satış", qty, base_amt))
        if pt in T.PRINT_BASED:
            pq = float(prints.get(code) or 0)
            price = list_prices.get(code) or bk.get("listPrice")
            if pq and price is None:
                raise T.ContractError(f"«{title}» baskı hakedişi için kapak fiyatı girilmeli.")
            comps.append(("baskı", pq, pq * float(price or 0)))
        for src, qty, base_amt in comps:
            base_amt *= (1 - disc)
            total_qty += qty
            total_base += base_amt
            unit = (base_amt / qty) if qty else 0.0
            parts = _tiered(flat or 0.0, tiers, float(prior_qty.get(code) or 0), qty) if src == "satış" else [(qty, flat or (tiers[0]["rate"] if tiers else 0))]
            royalty = sum(q * unit * r / 100 for q, r in parts)
            eff_rate = (royalty / base_amt * 100) if base_amt else (parts[0][1] if parts else 0)
            for name, share in payees:
                lines.append({
                    "book": title, "stockCode": code, "format": fmt, "source": src, "party": name,
                    "share": round(share * 100, 4), "quantity": round(qty, 2),
                    "returns": round((sales.get(code) or {}).get("retQty", 0.0), 2) if src == "satış" else 0,
                    "base": round(base_amt * share, 2), "rate": round(eff_rate, 4),
                    "tiers": [{"quantity": round(q, 2), "rate": r} for q, r in parts] if len(parts) > 1 else None,
                    "royalty": round(royalty * share, 2),
                })

    gross_try = round(sum(ln["royalty"] for ln in lines), 2)
    out_cur = "TRY"
    gross = gross_try
    fx_info = None
    if cur != "TRY":
        if fx and fx.get("rate"):
            rate = float(fx["rate"])
            gross = round(gross_try / rate, 2)
            out_cur = cur
            fx_info = {"currency": cur, "rate": rate, "on": fx.get("on"), "source": fx.get("source")}
            for ln in lines:
                ln["royaltyCurrency"] = round(ln["royalty"] / rate, 2)
        else:
            warns.append(f"Sözleşme {T.CURRENCIES.get(cur, cur)}; dönem sonu kuru girilmedi ve TCMB'den okunamadı, tutar TL bırakıldı ve avans mahsubu yapılmadı.")

    advance = float(terms.get("advance") or 0)
    offset = 0.0
    amount = round(gross + carry_in, 2)
    if carry_in:
        warns.append(f"Önceki dönemden devreden {T.money(carry_in, out_cur)} düşüldü.")
    if advance and terms.get("advanceRecoupable", True) and out_cur == cur and amount > 0:
        remaining = max(0.0, advance - advance_used)
        offset = round(min(remaining, amount), 2)
    after = round(amount - offset, 2)
    carry_out = 0.0
    if after < 0:
        carry_out, after = after, 0.0
        warns.append("İade satıştan fazla; eksi tutar sonraki döneme devreder, bu dönem ödeme yok.")
    wpct = float(terms.get("withholdingPct") or 0)
    withholding = round(after * wpct / 100, 2)
    net = round(after - withholding, 2)
    return {
        "periodStart": a.isoformat(), "periodEnd": b.isoformat(), "paymentType": pt, "basis": basis,
        "currency": out_cur, "contractCurrency": cur, "fx": fx_info,
        "quantity": round(total_qty, 2), "base": round(total_base, 2), "grossTry": gross_try,
        "gross": gross, "carryIn": round(carry_in, 2), "advance": advance or None,
        "advanceUsedBefore": round(advance_used, 2), "advanceOffset": offset,
        "advanceRemaining": round(max(0.0, advance - advance_used - offset), 2) if advance else None,
        "withholdingPct": wpct or None, "withholding": withholding, "net": net, "carryOut": round(carry_out, 2),
        "lines": lines, "warnings": list(dict.fromkeys(warns)), "dataEnd": data_end,
        "inputs": {"prints": prints, "listPrices": list_prices},
    }


def fingerprint(result: dict[str, Any]) -> str:
    """Hesabın girdisi ve sonucu değişmediyse aynı iz (onayda «hesap değişti mi» denetimi)."""
    keep = {k: result.get(k) for k in ("periodStart", "periodEnd", "gross", "net", "advanceOffset", "lines")}
    return hashlib.sha256(json.dumps(keep, sort_keys=True, default=str).encode()).hexdigest()[:16]
