"""M45 Finansal raporlama: Logo ve CRM okuması (yalnız okuma). Ekran bu SQL'lerin kendisini «SQL'i göster» ile açar.

Tanımlar (mevcut ölçülerle aynı; kabul test sunucusunda doğrudan sorguyla karşılaştırılır):

- **Satış satırı** = `STLINE`, `CANCELLED = 0`, `LINETYPE = 0`, `INVOICEREF <> 0` (faturalı), `TRCODE 7/8/9` satış,
  `2/3` iade (eksi). **Net satış** = Σ `LINENET`; iskonto öncesi = Σ `TOTAL`; iskonto = fark. **Satılan malın
  maliyeti (Logo)** = Σ `AMOUNT × OUTCOST`, yalnız `OUTCOST <> 0` satırlar; maliyetsiz satırlar ayrı sayılır, marja
  katılmaz. Bu tanım M46 bütçe gerçekleşmesi ve kokpitteki satır seviyesi net ciro ile aynıdır.
- **Muhasebe** = `EMFLINE` + `EMFICHE` (iki taraf da iptal değil) + `EMUHACC`. Gelir tablosu yalnız 6 ve 7 ile başlayan
  hesapları okur. Her satır bir **kurala** düşer:
  `yansitma` — 7x1 yansıtma hesaplarının kendisi ve yansıtma fişindeki 6xx karşılıkları (7/A'da gider 7xx'te bir kez
  sayılır; 63x'e aktarılması ikinci kez sayılmaz); `kapanis` — dönem sonu kapanış fişleri (6xx için 690/692 içeren
  fiş; 7xx için bir yansıtma hesabının borç satırını içeren fiş, M46'daki gider tanımıyla aynı); geri kalan `dahil`.
  Rapor yalnız `dahil` satırları toplar; dışarıda kalan tutar ekranda ayrıca yazılır, sessizce kaybolmaz.
- Yıllar Logo'da ayrı firma numarasıdır (411 = 2026, 211 = 2021–2025); eşleme `L_CAPIPERIOD`'dan okunur
  (`budget_sources.firms_by_year`, kopya yıllar atlanır).

Ölçülmemiş varsayımlar parametredir (admin.conf/ortam): kapanış hesapları `FINANCE_CLOSE_ACCOUNTS`, çek/senet durum
kodları `FINANCE_CS_*`, CRM onay bekleyen tahsilat etiketi `FINANCE_CRM_PENDING_LABEL`.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from semantic_bridge import budget_sources as bsrc

log = logging.getLogger("semantic.finance.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
QUERY_TIMEOUT = int(os.environ.get("FINANCE_QUERY_TIMEOUT_SEC", "1800"))
BOOK_CENTER, NO_CENTER = bsrc.BOOK_CENTER, bsrc.NO_CENTER

_CODE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.\-]{0,40}$")


def _conf(key: str, default: str) -> str:
    try:
        from semantic_bridge.admin import conf

        v = conf(key)
    except Exception:  # noqa: BLE001 — yönetim modülü yoksa ortam
        v = os.environ.get(key, "")
    return v if v not in (None, "") else default


def runner(path: str) -> Runner:
    """Ortak Logo/CRM çalıştırıcı (M46 ile aynı), M45'in kendi süresiyle (`FINANCE_QUERY_TIMEOUT_SEC`)."""
    return bsrc.runner(path, timeout=QUERY_TIMEOUT)


firms_by_year = bsrc.firms_by_year
day = bsrc._day


def _codes(raw: str) -> str:
    parts = [p.strip() for p in raw.split(",") if p.strip().isdigit()]
    return "(" + ",".join(f"'{p}'" for p in parts) + ")" if parts else "('')"


def yansitma_accounts() -> str:
    return "('711','721','731','741','751','761','771','781','791')"


def close_accounts() -> str:
    return _codes(_conf("FINANCE_CLOSE_ACCOUNTS", "690,692"))


def check_code(code: str) -> str:
    code = str(code or "").strip()
    if not _CODE.match(code):
        raise SourceError("Hesap kodu geçersiz.")
    return code


def _ymd(d: date) -> str:
    return d.strftime("%Y%m%d")


def _center_case(col: str = "C.CODE") -> str:
    return (f"CASE WHEN {col} IS NULL OR {col} = '.' OR {col} = '' THEN '{NO_CENTER}' "
            f"WHEN {col} LIKE '[0-9]%' THEN '{BOOK_CENTER}' ELSE {col} END")


def _rule_cte(firm: str, start: date, end: date) -> str:
    """Yansıtma ve kapanış fişleri (yalnız işaretli fişler)."""
    y, k = yansitma_accounts(), close_accounts()
    return f"""X AS (
  SELECT K.ACCFICHEREF AS ref,
    MAX(CASE WHEN LEFT(KA.CODE, 3) IN {y} THEN 1 ELSE 0 END) AS yans,
    MAX(CASE WHEN LEFT(KA.CODE, 3) IN {y} AND K.SIGN = 0 THEN 1 ELSE 0 END) AS kap7,
    MAX(CASE WHEN LEFT(KA.CODE, 3) IN {k} THEN 1 ELSE 0 END) AS kap6
  FROM dbo.LG_{firm}_01_EMFLINE AS K
  JOIN dbo.LG_{firm}_EMUHACC AS KA ON KA.LOGICALREF = K.ACCOUNTREF
  WHERE K.CANCELLED = 0 AND K.DATE_ >= '{_ymd(start)}' AND K.DATE_ < '{_ymd(end)}'
    AND (LEFT(KA.CODE, 3) IN {y} OR LEFT(KA.CODE, 3) IN {k})
  GROUP BY K.ACCFICHEREF)"""


def _rule_case() -> str:
    y = yansitma_accounts()
    return (f"CASE WHEN LEFT(A.CODE, 3) IN {y} THEN 'yansitma' "
            f"WHEN A.CODE LIKE '7%' AND X.kap7 = 1 THEN 'kapanis' "
            f"WHEN A.CODE LIKE '6%' AND X.kap6 = 1 THEN 'kapanis' "
            f"WHEN A.CODE LIKE '6%' AND X.yans = 1 THEN 'yansitma' ELSE 'dahil' END")


# ------------------------------------------------------------------ SQL: muhasebe


def account_actuals_sql(firm: str, year: int) -> str:
    """6 ve 7 ile başlayan hesaplar × ay × masraf merkezi × kural: borç ve alacak toplamı."""
    a, b = date(year, 1, 1), date(year + 1, 1, 1)
    return f"""
-- Gelir tablosu hesapları (6xx, 7xx). Kural: dahil | yansitma | kapanis — rapor yalnız 'dahil' satırları toplar.
WITH {_rule_cte(firm, a, b)}
SELECT MONTH(L.DATE_) AS ay, A.CODE AS hesap, MAX(A.DEFINITION_) AS hesap_adi,
  {_center_case()} AS merkez_kodu, {_rule_case()} AS kural,
  SUM(L.DEBIT) AS borc, SUM(L.CREDIT) AS alacak, COUNT(*) AS satir
FROM dbo.LG_{firm}_01_EMFLINE AS L
JOIN dbo.LG_{firm}_01_EMFICHE AS F ON F.LOGICALREF = L.ACCFICHEREF
JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = L.ACCOUNTREF
LEFT JOIN dbo.LG_{firm}_EMCENTER AS C ON C.LOGICALREF = L.CENTERREF
LEFT JOIN X ON X.ref = L.ACCFICHEREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND (A.CODE LIKE '6%' OR A.CODE LIKE '7%')
  AND L.DATE_ >= '{_ymd(a)}' AND L.DATE_ < '{_ymd(b)}'
GROUP BY MONTH(L.DATE_), A.CODE, {_center_case()}, {_rule_case()}""".strip()


def accounts_sql(firm: str) -> str:
    return (f"SELECT CODE AS hesap, DEFINITION_ AS ad FROM dbo.LG_{firm}_EMUHACC "
            f"WHERE CODE LIKE '6%' OR CODE LIKE '7%'")


def trial_sql(firm: str, year: int) -> str:
    """Mizan denkliği: bütün hesaplar, ay ay Σ borç ve Σ alacak."""
    return f"""
SELECT MONTH(L.DATE_) AS ay, SUM(L.DEBIT) AS borc, SUM(L.CREDIT) AS alacak, COUNT(*) AS satir, MAX(L.DATE_) AS son
FROM dbo.LG_{firm}_01_EMFLINE AS L
JOIN dbo.LG_{firm}_01_EMFICHE AS F ON F.LOGICALREF = L.ACCFICHEREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND L.DATE_ >= '{year}0101' AND L.DATE_ < '{year + 1}0101'
GROUP BY MONTH(L.DATE_)""".strip()


def entries_sql(firm: str, code: str, start: date, end: date, page: int, size: int) -> str:
    """Bir hesabın (ve alt hesaplarının) fiş satırları, sayfalı. Her satırın rapordaki kuralı yazılır."""
    code = check_code(code)
    return f"""
WITH {_rule_cte(firm, start, end)}
SELECT CONVERT(date, L.DATE_) AS tarih, F.FICHENO AS fis_no, F.TRCODE AS fis_turu, A.CODE AS hesap,
  A.DEFINITION_ AS hesap_adi, L.LINEEXP AS aciklama, L.DEBIT AS borc, L.CREDIT AS alacak,
  C.CODE AS merkez, {_rule_case()} AS kural, COUNT(*) OVER () AS toplam
FROM dbo.LG_{firm}_01_EMFLINE AS L
JOIN dbo.LG_{firm}_01_EMFICHE AS F ON F.LOGICALREF = L.ACCFICHEREF
JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = L.ACCOUNTREF
LEFT JOIN dbo.LG_{firm}_EMCENTER AS C ON C.LOGICALREF = L.CENTERREF
LEFT JOIN X ON X.ref = L.ACCFICHEREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND (A.CODE = '{code}' OR A.CODE LIKE '{code}.%')
  AND L.DATE_ >= '{_ymd(start)}' AND L.DATE_ < '{_ymd(end)}'
ORDER BY L.DATE_, F.FICHENO, L.LOGICALREF
OFFSET {int(page) * int(size)} ROWS FETCH NEXT {int(size)} ROWS ONLY""".strip()


# ------------------------------------------------------------------ SQL: satış


_SIGN = "(CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END)"
_SALES_WHERE = "S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"


def _measures() -> str:
    return f"""SUM({_SIGN} * S.AMOUNT) AS adet,
  SUM({_SIGN} * S.TOTAL) AS brut,
  SUM({_SIGN} * S.LINENET) AS net,
  SUM(CASE WHEN S.OUTCOST <> 0 THEN {_SIGN} * S.AMOUNT * S.OUTCOST ELSE 0 END) AS maliyet,
  SUM(CASE WHEN S.OUTCOST <> 0 THEN {_SIGN} * S.LINENET ELSE 0 END) AS maliyetli_net,
  SUM(CASE WHEN S.OUTCOST = 0 THEN {_SIGN} * S.AMOUNT ELSE 0 END) AS maliyetsiz_adet,
  SUM(CASE WHEN S.OUTCOST = 0 THEN {_SIGN} * S.LINENET ELSE 0 END) AS maliyetsiz_net"""


def sales_month_sql(firm: str, year: int) -> str:
    """Ay ay fatura net satış, iade, iskonto ve maliyet kapsamı (mutabakat ve «yaklaşık» notları)."""
    return f"""
-- Faturalı satış satırları; iade eksi. Net = LINENET, iskonto öncesi = TOTAL.
SELECT MONTH(S.DATE_) AS ay, {_measures()},
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE 0 END) AS satis_net,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.LINENET ELSE 0 END) AS iade_net,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE 0 END) AS satis_satir,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) AND S.OUTCOST = 0 THEN 1 ELSE 0 END) AS maliyetsiz_satir
FROM dbo.LG_{firm}_01_STLINE AS S
WHERE {_SALES_WHERE} AND S.DATE_ >= '{year}0101' AND S.DATE_ < '{year + 1}0101'
GROUP BY MONTH(S.DATE_)""".strip()


def sales_period_sql(firm: str, start: date, end: date) -> str:
    """Bir tarih aralığının toplamı (geçen yılın aynı dönemi, gün gününe)."""
    return f"""
SELECT {_measures()}
FROM dbo.LG_{firm}_01_STLINE AS S
WHERE {_SALES_WHERE} AND S.DATE_ >= '{_ymd(start)}' AND S.DATE_ < '{_ymd(end)}'""".strip()


def data_end_sql(firm: str) -> str:
    return (f"SELECT MAX(S.DATE_) AS son, MAX(CASE WHEN S.OUTCOST <> 0 THEN S.DATE_ END) AS son_maliyetli "
            f"FROM dbo.LG_{firm}_01_STLINE AS S WHERE {_SALES_WHERE} AND S.TRCODE IN (7,8,9)")


def _kanal(col: str = "C.SPECODE2") -> str:
    return f"ISNULL(NULLIF(LTRIM(RTRIM({col})), ''), N'Grup kodu boş')"


def profit_items_sql(firm: str, year: int) -> str:
    """Kitap (stok kodu) × kanal (cari grup kodu) × ay."""
    return f"""
SELECT MONTH(S.DATE_) AS ay, I.CODE AS stok_kodu, {_kanal()} AS kanal, {_measures()}
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
LEFT JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE {_SALES_WHERE} AND S.DATE_ >= '{year}0101' AND S.DATE_ < '{year + 1}0101'
GROUP BY MONTH(S.DATE_), I.CODE, {_kanal()}""".strip()


def profit_clients_sql(firm: str, year: int) -> str:
    """Cari × kanal × ay."""
    return f"""
SELECT MONTH(S.DATE_) AS ay, ISNULL(C.CODE, N'#YOK') AS cari_kodu, MAX(C.DEFINITION_) AS cari_adi,
  {_kanal()} AS kanal, {_measures()}
FROM dbo.LG_{firm}_01_STLINE AS S
LEFT JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE {_SALES_WHERE} AND S.DATE_ >= '{year}0101' AND S.DATE_ < '{year + 1}0101'
GROUP BY MONTH(S.DATE_), ISNULL(C.CODE, N'#YOK'), {_kanal()}""".strip()


def client_uncosted_sql(firm: str, year: int) -> str:
    """Yalnız maliyetsiz satırlar: cari × kitap × ay adedi (carinin yaklaşık maliyeti için; saklanmaz)."""
    return f"""
SELECT MONTH(S.DATE_) AS ay, ISNULL(C.CODE, N'#YOK') AS cari_kodu, {_kanal()} AS kanal, I.CODE AS stok_kodu,
  SUM({_SIGN} * S.AMOUNT) AS adet
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
LEFT JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE {_SALES_WHERE} AND S.OUTCOST = 0 AND S.DATE_ >= '{year}0101' AND S.DATE_ < '{year + 1}0101'
GROUP BY MONTH(S.DATE_), ISNULL(C.CODE, N'#YOK'), {_kanal()}, I.CODE""".strip()


# ------------------------------------------------------------------ SQL: nakit


CASH_GROUPS = ("100", "101", "102", "103", "108", "120", "121", "300", "320", "321")


def position_sql(firm: str, year: int, asof: date) -> str:
    """Hesap grubu bakiyeleri (yılın açılış fişi dahil) veri son gününe kadar: kasa, banka, çek, alacak, borç."""
    groups = ",".join(f"'{g}'" for g in CASH_GROUPS)
    return f"""
SELECT LEFT(A.CODE, 3) AS grup, SUM(L.DEBIT) AS borc, SUM(L.CREDIT) AS alacak
FROM dbo.LG_{firm}_01_EMFLINE AS L
JOIN dbo.LG_{firm}_01_EMFICHE AS F ON F.LOGICALREF = L.ACCFICHEREF
JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = L.ACCOUNTREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND LEFT(A.CODE, 3) IN ({groups})
  AND L.DATE_ >= '{year}0101' AND L.DATE_ < '{_ymd(asof + timedelta(days=1))}'
GROUP BY LEFT(A.CODE, 3)""".strip()


def bank_daily_sql(firm: str, year: int) -> str:
    """Kasa + banka (100, 102) gün gün giriş ve çıkış; açılış fişi hariç. Nakit tahmininin gerçekleşeni."""
    return f"""
SELECT CONVERT(date, L.DATE_) AS gun, SUM(L.DEBIT) AS giris, SUM(L.CREDIT) AS cikis
FROM dbo.LG_{firm}_01_EMFLINE AS L
JOIN dbo.LG_{firm}_01_EMFICHE AS F ON F.LOGICALREF = L.ACCFICHEREF
JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = L.ACCOUNTREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND F.TRCODE <> 1 AND LEFT(A.CODE, 3) IN ('100', '102')
  AND L.DATE_ >= '{year}0101' AND L.DATE_ < '{year + 1}0101'
GROUP BY CONVERT(date, L.DATE_)""".strip()


def cash_flows_daily_sql(firm: str, start: date, end: date) -> str:
    """Olasılıklı nakit bandının geçmişi: kasa + banka (100, 102) gün gün **müşteri tahsilatı** (aynı fişte 120 satırı
    olan girişler) ve **satıcı ödemesi** (aynı fişte 320 satırı olan çıkışlar). Çek/senet tahsili ve ödemesi (101/103
    karşılıklı fişler) bu serilere girmez: onlar vadesi belli kalemdir, tabloda kuraldan gelir. Açılış fişi hariç."""
    return f"""
-- Nakit bandı geçmişi: 100/102 hareketi, karşı tarafı 120 (tahsilat) ya da 320 (ödeme) olan fişlerden.
WITH K AS (
  SELECT L.ACCFICHEREF AS ref,
    MAX(CASE WHEN LEFT(A.CODE, 3) = '120' THEN 1 ELSE 0 END) AS musteri,
    MAX(CASE WHEN LEFT(A.CODE, 3) = '320' THEN 1 ELSE 0 END) AS satici
  FROM dbo.LG_{firm}_01_EMFLINE AS L
  JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = L.ACCOUNTREF
  WHERE L.CANCELLED = 0 AND L.DATE_ >= '{_ymd(start)}' AND L.DATE_ < '{_ymd(end)}' AND LEFT(A.CODE, 3) IN ('120', '320')
  GROUP BY L.ACCFICHEREF)
SELECT CONVERT(date, L.DATE_) AS gun,
  SUM(CASE WHEN K.musteri = 1 THEN L.DEBIT ELSE 0 END) AS tahsilat,
  SUM(CASE WHEN K.satici = 1 THEN L.CREDIT ELSE 0 END) AS odeme
FROM dbo.LG_{firm}_01_EMFLINE AS L
JOIN dbo.LG_{firm}_01_EMFICHE AS F ON F.LOGICALREF = L.ACCFICHEREF
JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = L.ACCOUNTREF
JOIN K ON K.ref = L.ACCFICHEREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND F.TRCODE <> 1 AND LEFT(A.CODE, 3) IN ('100', '102')
  AND L.DATE_ >= '{_ymd(start)}' AND L.DATE_ < '{_ymd(end)}'
GROUP BY CONVERT(date, L.DATE_)""".strip()


def fifo_due_sql(firm: str, year: int, asof: date, *, payable: bool) -> str:
    """Açık kalemlerin vadeye göre dağılımı (FIFO yaklaşımı; bilgi paketindeki yaşlandırma sorgusu, `GETDATE()`
    yerine veri son günüyle). Logo'da ödeme kapama kullanılmadığı için carinin net bakiyesi en yeni vade
    satırlarından geriye dağıtılır; sonuç yaklaşıktır."""
    prefix, sign = ("320", 1) if payable else ("120", 0)
    bal = "L.SIGN = 1" if payable else "L.SIGN = 0"
    return f"""
-- FIFO yaklaşımı ({'satıcı borcu' if payable else 'müşteri alacağı'}): kapama olmadığı için bakiye en yeni vadelerden geriye dağıtılır.
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN {bal} THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
    FROM dbo.LG_{firm}_01_CLFLINE AS L JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = L.CLIENTREF
    WHERE L.CANCELLED = 0 AND C.CODE LIKE '{prefix}%' AND L.DATE_ >= '{year}0101' AND L.DATE_ < '{_ymd(asof + timedelta(days=1))}'
    GROUP BY L.CLIENTREF),
  P AS (SELECT P.CARDREF, P.DATE_, P.TOTAL,
      SUM(P.TOTAL) OVER (PARTITION BY P.CARDREF ORDER BY P.DATE_ DESC, P.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) AS kumulatif
    FROM dbo.LG_{firm}_01_PAYTRANS AS P WHERE P.CANCELLED = 0 AND P.SIGN = {sign}
      AND P.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye > 0)),
  A AS (SELECT P.CARDREF, P.DATE_,
      CASE WHEN B.bakiye >= P.kumulatif THEN P.TOTAL WHEN B.bakiye > P.kumulatif - P.TOTAL
           THEN B.bakiye - (P.kumulatif - P.TOTAL) ELSE 0 END AS acik
    FROM P JOIN B ON B.CLIENTREF = P.CARDREF)
SELECT CONVERT(date, A.DATE_) AS vade, SUM(A.acik) AS tutar, COUNT(DISTINCT A.CARDREF) AS cari
FROM A WHERE A.acik > 0
GROUP BY CONVERT(date, A.DATE_)""".strip()


def cheques_sql(firm: str) -> str:
    """Çek/senet kartları: belge türü × durum × vade. Hangi türün giriş, hangisinin çıkış olduğu ayarda
    (`FINANCE_CS_IN_DOC`, `FINANCE_CS_IN_STATUS`, `FINANCE_CS_OUT_DOC`, `FINANCE_CS_OUT_STATUS`); ölçülecek."""
    return f"""
SELECT CS.DOC AS tur, CS.CURRSTAT AS durum, CONVERT(date, CS.DUEDATE) AS vade, SUM(CS.AMOUNT) AS tutar, COUNT(*) AS adet
FROM dbo.LG_{firm}_01_CSCARD AS CS
GROUP BY CS.DOC, CS.CURRSTAT, CONVERT(date, CS.DUEDATE)""".strip()


def crm_pending_collections_sql() -> str:
    """CRM'de onayı bekleyen (Logo'ya henüz düşmemiş) tahsilat kayıtları, vadeye göre."""
    label = _conf("FINANCE_CRM_PENDING_LABEL", "Onay Bekliyor").replace("'", "''")
    return f"""
SELECT CONVERT(date, t.new_vadetarihi) AS vade, SUM(t.new_tutar) AS tutar, COUNT(*) AS adet
FROM new_tahsilatBase AS t
JOIN StringMap AS m ON m.AttributeName = 'statuscode' AND m.AttributeValue = t.statuscode
  AND m.ObjectTypeCode = (SELECT ObjectTypeCode FROM MetadataSchema.Entity WHERE Name = 'new_tahsilat')
WHERE t.statecode = 0 AND m.Value = N'{label}' AND t.new_vadetarihi IS NOT NULL
GROUP BY CONVERT(date, t.new_vadetarihi)""".strip()


def _int_set(key: str, default: str) -> set[int]:
    return {int(p) for p in _conf(key, default).split(",") if p.strip().lstrip("-").isdigit()}


def cheque_direction(tur: Any, durum: Any) -> Optional[str]:
    """Belge türü + durum → giris | cikis | None (tahmine girmez). Varsayılanlar Logo belgelerinden; ölçülecek:
    tür 1 müşteri çeki, 2 müşteri senedi (durum 1 portföyde, 4 tahsile verildi); tür 3 kendi çekimiz, 4 borç
    senedimiz (durum 9/10 verildi)."""
    try:
        t, d = int(tur), int(durum)
    except (TypeError, ValueError):
        return None
    if t in _int_set("FINANCE_CS_IN_DOC", "1,2") and d in _int_set("FINANCE_CS_IN_STATUS", "1,4"):
        return "giris"
    if t in _int_set("FINANCE_CS_OUT_DOC", "3,4") and d in _int_set("FINANCE_CS_OUT_STATUS", "9,10"):
        return "cikis"
    return None


# ------------------------------------------------------------------ okuma yardımcıları


def f(v: Any) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 0.0
    return x if x == x else 0.0


def clean(v: Any) -> Optional[str]:
    return bsrc._clean(v)


def read_data_end(run: Runner, firms: dict[int, str]) -> tuple[Optional[date], Optional[date]]:
    """(son faturalı satış günü, maliyeti işlenmiş son satış günü) — en son yılın kopyasından."""
    last = max(firms)
    rows = run(data_end_sql(firms[last]))
    if not rows:
        return None, None
    return day(rows[0].get("son")), day(rows[0].get("son_maliyetli"))


def to_day(v: Any) -> Optional[str]:
    d = day(v)
    return d.isoformat() if d else None


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")
