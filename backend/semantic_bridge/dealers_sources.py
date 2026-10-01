"""M59 Kitapçı/bayi risk ve performans: Logo ve CRM okuması (yalnız okuma).

**Yeniden yazılmayanlar.** Bakiye ve FIFO yaşlandırma, çek/senet olayı, CRM limit/risk doluluğu, temsilci ↔ cari ataması
ve Logo cari listesi M30'un (`field_sales_sources.py`, `field_sales.py`) fonksiyonlarıdır; M59 onları çağırır
(`aging_sql` / `read_aging`, `read_cheque_events`, `risk_of`, `crm_accounts_sql`, `crm_users_sql`, `crm_risk_orders_sql`,
`clients_sql`, `payments_sql`, `F.assign`, `F.match_clients`, `F.logo_calendar`). Aynı tanım iki yerde yazılmaz; M30
testleri değişmeden geçer.

**Burada yalnız M59'a özgü okumalar var:**

- Aylık faturalı satış/iade/fatura sayısı (cari kodu × ay) — 12 aylık seri, iade oranı, sipariş düzensizliği ve
  tahsilat süresi (DSO) yaklaşımı. Satış tanımı M30/M46 ile aynı: `STLINE` faturalı satır (`LINETYPE = 0`,
  `INVOICEREF <> 0`, `CANCELLED = 0`), TRCODE 7/8/9 satış, 2/3 iade, tutar `VATMATRAH` (KDV matrahı, fatura geneli
  iskonto dahil; dönem fatura tarihi `INVOICE.DATE_` — karar 2026-10-01). Fatura sayısı ayrı fatura başlığı
  (`COUNT(DISTINCT INVOICEREF)`).
- Aylık ödeme (cari alacak satırı, ayardaki TRCODE listesi — M30 `FIELD_PAYMENT_TRCODES` ile aynı küme).
- CRM cari bayrakları: «Sorunlu Müşteri» (`StatusCode` 100000003), `CreditOnHold`, `new_vadegun`, `new_ekacikhesaplimiti`.
  **Ölçülecek:** doluluk (analiz §6).
- CRM risk onay geçmişi (tek cari): riske takılan siparişler, anlık limit/risk, onaylayan/reddeden, onay/ret tarihleri.

Yıllar Logo'da ayrı firmadır (411 = 2026, 211 = 2021–2025); 12 ay iki firmayı kesebilir, iki firma okunup **cari kodu**
ile birleştirilir (LOGICALREF firmadan firmaya değişir). Kişisel kolon (adres, telefon, vergi no, çek/hesap no) seçilmez.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import field_sales_sources as fsrc
from semantic_bridge.field_sales_sources import (  # noqa: F401 — M59'un kullandığı ortak parçalar tek yerden
    SourceError, code_prefix, day, firm, guid, lower_keys, num, opt_num, prefix, read_rows, text,
)

Run = Callable[[str], list[dict[str, Any]]]

#: CRM cari durumu «Sorunlu Müşteri».
CRM_PROBLEM_STATUS = 100000003


def _d(d: date) -> str:
    return d.isoformat()


# ------------------------------------------------------------------ Logo: aylık seriler


def monthly_sales_sql(f: str, start: date, end: date, prefix_: str = "120") -> str:
    """Cari kodu × ay: faturalı satış, iade (VATMATRAH) ve satış faturası sayısı. [start, end] kapalı aralık."""
    f = firm(f)
    return (f"SELECT C.CODE AS code, YEAR(SH.DATE_) AS y, MONTH(SH.DATE_) AS m,"
            f" SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE 0 END) AS satis,"
            f" SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.VATMATRAH ELSE 0 END) AS iade,"
            f" COUNT(DISTINCT CASE WHEN S.TRCODE IN (7,8,9) THEN S.INVOICEREF END) AS fatura,"
            f" MAX(CASE WHEN S.TRCODE IN (7,8,9) THEN SH.DATE_ END) AS son_fatura"
            f" FROM dbo.LG_{f}_01_STLINE S"
            f" JOIN dbo.LG_{f}_01_INVOICE SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0"
            f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
            f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
            f" AND C.CODE LIKE '{code_prefix(prefix_)}%'"
            f" AND SH.DATE_ >= '{_d(start)}' AND SH.DATE_ < '{_d(end + timedelta(days=1))}'"
            f" GROUP BY C.CODE, YEAR(SH.DATE_), MONTH(SH.DATE_)")


def monthly_payments_sql(f: str, start: date, end: date, codes: tuple[int, ...], prefix_: str = "120") -> str:
    """Cari kodu × ay: ödeme (alacak satırı, ayardaki TRCODE'lar) toplamı."""
    f = firm(f)
    tc = ", ".join(str(int(c)) for c in codes)
    return (f"SELECT C.CODE AS code, YEAR(L.DATE_) AS y, MONTH(L.DATE_) AS m, SUM(L.AMOUNT) AS odeme"
            f" FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF"
            f" WHERE L.CANCELLED = 0 AND L.SIGN = 1 AND L.TRCODE IN ({tc}) AND C.CODE LIKE '{code_prefix(prefix_)}%'"
            f" AND L.DATE_ >= '{_d(start)}' AND L.DATE_ < '{_d(end + timedelta(days=1))}'"
            f" GROUP BY C.CODE, YEAR(L.DATE_), MONTH(L.DATE_)")


def month_keys(end: date, n: int = 12) -> list[str]:
    """`end`'in ayı dahil geriye `n` ay, eskiden yeniye: ['2025-09', …, '2026-08']."""
    out = []
    y, m = end.year, end.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def window_start(end: date, months: int = 12) -> date:
    """Seri penceresinin ilk günü: `end`'in ayından geriye `months` ayın ilk ayının 1'i."""
    first = month_keys(end, months)[0]
    return date(int(first[:4]), int(first[5:7]), 1)


def read_monthly(run: Run, firms: Iterable[str], start: date, end: date, pay_codes: tuple[int, ...],
                 prefix_: str = "120") -> dict[str, dict[str, dict[str, float]]]:
    """Cari kodu → ay → {satis, iade, fatura, odeme}; iki firma (yıl) cari koduyla toplanır. Son fatura günü `_son`."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for f in firms:
        for r in read_rows(run, monthly_sales_sql(f, start, end, prefix_)):
            code = text(r.get("code"))
            if not code:
                continue
            key = f"{int(num(r.get('y'))):04d}-{int(num(r.get('m'))):02d}"
            cell = out.setdefault(code, {}).setdefault(key, {"satis": 0.0, "iade": 0.0, "fatura": 0, "odeme": 0.0})
            cell["satis"] += num(r.get("satis"))
            cell["iade"] += num(r.get("iade"))
            cell["fatura"] += int(num(r.get("fatura")))
            d = day(r.get("son_fatura"))
            if d and (out[code].get("_son") is None or d > out[code]["_son"]):
                out[code]["_son"] = d  # type: ignore[assignment]
        for r in read_rows(run, monthly_payments_sql(f, start, end, pay_codes, prefix_)):
            code = text(r.get("code"))
            if not code:
                continue
            key = f"{int(num(r.get('y'))):04d}-{int(num(r.get('m'))):02d}"
            cell = out.setdefault(code, {}).setdefault(key, {"satis": 0.0, "iade": 0.0, "fatura": 0, "odeme": 0.0})
            cell["odeme"] += num(r.get("odeme"))
    return out


def read_last_payments(run: Run, firms: Iterable[str], since: date, codes: tuple[int, ...],
                       prefix_: str = "120") -> dict[str, dict[str, Any]]:
    """Cari kodu → son ödeme günü ve penceredeki toplam (M30 `payments_sql`, iki firma birleşik)."""
    out: dict[str, dict[str, Any]] = {}
    for f in firms:
        for r in read_rows(run, fsrc.payments_sql(f, since, codes, prefix_)):
            code = text(r.get("code"))
            if not code:
                continue
            cur = out.setdefault(code, {"son": None, "toplam": 0.0})
            d = day(r.get("son"))
            if d and (cur["son"] is None or d > cur["son"]):
                cur["son"] = d
            cur["toplam"] += num(r.get("toplam"))
    return out


# ------------------------------------------------------------------ CRM: cari bayrakları, risk onay geçmişi


def crm_account_flags_sql(schema: str) -> str:
    """Etkin cariler: «Sorunlu Müşteri» durumu, kredi askıda, vade günü, ek açık hesap limiti. Kişisel kolon seçilmez."""
    p = prefix(schema)
    return ("SELECT a.AccountId AS account_id, CAST(a.StatusCode AS int) AS durum, CAST(a.CreditOnHold AS int) AS kredi_askida,"
            " a.new_vadegun AS vade_gun, a.new_ekacikhesaplimiti AS ek_limit"
            f" FROM {p}AccountBase a WHERE a.StateCode = 0")


_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _guid_literal(v: str) -> str:
    s = (v or "").strip().strip("{}")
    if not _GUID.match(s):
        raise SourceError("CRM kimliği geçersiz.")
    return s


def crm_risk_history_sql(schema: str, account_id: str, since: date) -> str:
    """Tek carinin riske takılan (ya da limite takılma bayrağı olan) siparişleri: sebep, anlık limit/risk, onaylayan,
    reddeden, onay/ret tarihi. Onay/ret tarih kolonları siparişin genel onay alanlarıdır (risk onayına özgü olup
    olmadıkları **ölçülecek**)."""
    p = prefix(schema)
    gid = _guid_literal(account_id)
    return ("SELECT s.new_name AS no, s.new_siparistarihi AS tarih, CAST(s.statuscode AS int) AS durum,"
            " s.new_toplamsatistutari AS tutar, CAST(s.new_risketakilmasebebi AS int) AS sebep,"
            " s.new_anliklimit AS anlik_limit, s.new_anlikrisk AS anlik_risk,"
            " s.new_risklimitionaylayanid AS onaylayan_id, s.new_risklimitireddedenid AS reddeden_id,"
            " s.new_onaylanmatarihi AS onay_tarihi, s.new_reddedilmetarihi AS red_tarihi"
            f" FROM {p}new_siparisBase s WHERE s.new_firmaid = '{gid}' AND s.statecode = 0"
            " AND (s.new_risketakilmasebebi IS NOT NULL OR s.new_siparislimitetakildi = 1"
            f" OR CAST(s.statuscode AS int) IN ({', '.join(str(x) for x in fsrc.ORDER_RISK_STATUS)}))"
            f" AND s.new_siparistarihi >= '{_d(since)}' ORDER BY s.new_siparistarihi DESC")


def read_account_flags(run: Run, schema: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in read_rows(run, crm_account_flags_sql(schema)):
        g = guid(r.get("account_id"))
        if not g:
            continue
        out[g] = {"sorunlu": int(num(r.get("durum"))) == CRM_PROBLEM_STATUS,
                  "kredi_askida": bool(int(num(r.get("kredi_askida")))),
                  "vade_gun": int(num(r.get("vade_gun"))) if opt_num(r.get("vade_gun")) is not None else None,
                  "ek_limit": opt_num(r.get("ek_limit"))}
    return out


def history_rows(rows: list[dict[str, Any]], users: dict[str, str]) -> list[dict[str, Any]]:
    """Risk onay geçmişi satırlarını ekran biçimine çevirir (kullanıcı GUID → ad)."""
    out = []
    for r in lower_keys(rows):
        st = int(num(r.get("durum")))
        out.append({"no": text(r.get("no")), "tarih": day(r.get("tarih")), "tutar": num(r.get("tutar")),
                    "riskte": st in fsrc.ORDER_RISK_STATUS,
                    "sebep": fsrc.ORDER_RISK_REASON.get(int(num(r.get("sebep")))),
                    "anlikLimit": opt_num(r.get("anlik_limit")), "anlikRisk": opt_num(r.get("anlik_risk")),
                    "onaylayan": users.get(guid(r.get("onaylayan_id")) or "") if r.get("onaylayan_id") else None,
                    "reddeden": users.get(guid(r.get("reddeden_id")) or "") if r.get("reddeden_id") else None,
                    "onayTarihi": day(r.get("onay_tarihi")), "redTarihi": day(r.get("red_tarihi"))})
    return out
