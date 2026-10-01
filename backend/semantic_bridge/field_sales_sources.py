"""M30 Saha satış ve tahsilat: Logo ve CRM okuması (yalnız okuma).

Bu dosyadaki **risk, yaşlandırma ve limit** fonksiyonları M59 (bayi risk ve performans) gelince aynen onun da kaynağıdır:
M59 kendi SQL'ini yazmaz, `aging_sql` / `read_aging` / `read_cheque_events` / `read_crm_risk`'i çağırır (analiz kararı,
`docs/analiz/kullanici-ihtiyaclari/M30-saha-satis-tahsilat.md` §14 «M59 ile çakışma»).

Tanımlar (depodaki sertifikalı SQL'lerle aynı):

- **Bakiye ve vadesi geçmiş (FIFO yaklaşımı)** — `configs/semantic/knowledge/logo/knowledge/sql/vadesi-gecmis-yaslandirma-fifo.md`:
  müşteri carisi (`CLCARD.CODE LIKE '120%'`), yıl başından bu yana `CLFLINE` borç − alacak = bakiye; bakiye, carinin en yeni
  vade (`PAYTRANS`, `SIGN = 0`) satırlarından geriye dağıtılır, eski satırlar ödenmiş sayılır. Logo'da ödeme kapama
  kullanılmadığı için sonuç **yaklaşıktır**; ekranda böyle yazılır. Vade planına dağıtılamayan bakiye («plansız») ayrıca
  verilir, kovalara girmez (sertifikalı SQL'de de girmez).
- **Satış** — faturalı satır (`STLINE`, `LINETYPE = 0`, `INVOICEREF <> 0`, `CANCELLED = 0`), TRCODE 7/8/9 satış, 2/3 iade;
  net ciro = Σ `VATMATRAH` satış − Σ `VATMATRAH` iade (KDV matrahı, fatura geneli iskonto dahil; dönem fatura tarihi
  `INVOICE.DATE_` — karar 2026-10-01).
- **Çek olayı** — Kural 12: karşılıksız çıkma `CSTRANS.STATUS = 11`, protesto `STATUS IN (5, 7)`, `DEVIR = 0`,
  `CANCELLED = 0`, dönem hareket tarihi üzerinde; tutar `CSCARD.AMOUNT`, çek başına bir kez. `CSCARD`'da cari kolonu yok:
  çekin müşterisi portföye giriş hareketinin (`STATUS = 1`) `CARDREF`'idir. **Ölçülecek:** `CARDREF`'in bu harekette
  gerçekten cari referansı olduğu (`CARDMD`) ve yıl başı devir satırında dolu olup olmadığı.
- **Son ödeme** — cari hareketinde alacak satırı (`SIGN = 1`), TRCODE listesi ayardan (`FIELD_PAYMENT_TRCODES`, varsayılan
  1 nakit, 20 gelen havale, 61 çek girişi, 62 senet girişi, 70 kredi kartı). **Ölçülecek:** kodların TİMAŞ'taki kullanımı.

Yıllar Logo'da ayrı firmadır (411 = 2026, 211 = 2021–2025); `CLCARD.LOGICALREF` firmadan firmaya değişir, müşteri
**cari kodu** (`CODE`) ile izlenir. Firma/yıl eşlemesi `budget_sources.firms_by_year` ile `L_CAPIPERIOD`'dan okunur.

CRM: temsilci ↔ cari ataması `AccountBase.OwnerId` («BMT») ve «BMT İl» carilerinde `new_illerBase.new_musteritemsilcisi`;
risk ve limitler CRM'de (`AccountBase`, Logo `CLRNUMS.ACCRISKLIMIT` boş); tahsilat onay akışı `new_tahsilatBase`
(Onay Bekliyor → Onaylandı → Logoya Aktarıldı / Reddedildi) okunur, portalda yeniden girilmez.

Saha uygulamasının Logo veritabanındaki tabloları (`VW_MMX_*`) **seçenekli** kaynaktır: `FIELD_MMX_ENABLED=1` olmadan okunmaz;
kullanılıp kullanılmadığı ve satır sayıları ölçülecek. Okunursa yalnız cari kodu, tarih ve tutar kolonları seçilir; konum,
görüşülen kişi ve telefonu hiçbir zaman okunmaz (KVKK).

Kişisel kolonlar (TC/vergi no, telefon, e-posta, adres, IBAN, çek/hesap no) hiçbir sorguda seçilmez.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

log = logging.getLogger("semantic.field.sources")
TZ = ZoneInfo("Europe/Istanbul")
UTC = ZoneInfo("UTC")

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")
_CODE_PREFIX = re.compile(r"^[0-9A-Za-z.]{1,20}$")

#: CRM tahsilat durumu (`new_tahsilatBase.statuscode`).
T_PENDING, T_APPROVED, T_REJECTED, T_TRANSFERRED = 100000000, 100000001, 100000002, 100000003
COLLECTION_STATUS = {T_PENDING: "Onay bekliyor", T_APPROVED: "Onaylandı", T_REJECTED: "Reddedildi",
                     T_TRANSFERRED: "Logo'ya aktarıldı", 2: "Etkin değil"}
COLLECTION_TYPE = {100000004: "Nakit", 100000000: "Çek", 100000001: "Senet", 100000002: "POS",
                   100000003: "Mail order", 100000005: "Telif satış tahsilatı"}
REJECT_REASON = {100000000: "Şekil şartı eksikliği", 100000001: "Makbuz ile evrak uyumsuzluğu",
                 100000002: "Vade uyumsuzluğu", 100000003: "Diğer"}
#: Siparişin riske takıldığı durumlar (`new_siparisBase.statuscode`): Risk Limit Onayı Bekliyor, Risk Bilgisi Bekleniyor.
ORDER_RISK_STATUS = (100000004, 100000016)
ORDER_RISK_REASON = {1: "Açık hesap limiti", 2: "Çek-senet limiti", 3: "Toplam limit", 4: "Sorunlu müşteri"}
#: CRM `AccountBase.new_BMTilveyaCari`: 0 = BMT İl (il tablosundaki temsilci), 1 = BMT Cari (kaydın sahibi).
BMT_IL, BMT_CARI = 0, 1
CHANNEL = {100000008: "Bayi", 100000004: "Dağıtıcı", 100000001: "Kitapçı", 100000003: "Perakende",
           100000005: "E-ticaret", 100000002: "Market", 100000006: "Fuar", 100000009: "Tüketici-okur",
           100000000: "Sincap Kitap", 100000007: "Diğer"}


class SourceError(RuntimeError):
    pass


Run = Callable[[str], list[dict[str, Any]]]


# ------------------------------------------------------------------ yardımcılar


def prefix(schema: str) -> str:
    """`Timas_MSCRM.dbo` → `Timas_MSCRM.dbo.`; adı doğrular (SQL'e yalnız doğrulanmış ad girer)."""
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def firm(f: str) -> str:
    if not _FIRM.match(str(f or "")):
        raise SourceError("Logo firma numarası geçersiz.")
    return str(f)


def code_prefix(p: str) -> str:
    p = (p or "120").strip()
    if not _CODE_PREFIX.match(p):
        raise SourceError("Müşteri cari kodu öneki geçersiz.")
    return p


def _d(d: date) -> str:
    return d.isoformat()


def trcodes(raw: str) -> tuple[int, ...]:
    out = tuple(sorted({int(x) for x in re.split(r"[,\s]+", raw or "") if x.strip().isdigit()}))
    return out or (1, 20, 61, 62, 70)


def lower_keys(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(k).lower(): v for k, v in r.items()} for r in rows]


def num(v: Any) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0.0
    return n if n == n else 0.0


def opt_num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def text(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def day(v: Any) -> Optional[str]:
    """Tarih → İstanbul günü (ISO). CRM tarihleri UTC saklanır (gece yarısı = önceki gün 21:00); saatli değer İstanbul'a
    çevrilir. Logo tarihleri saatsizdir. 1900 ve öncesi Logo/CRM'in «boş» değeridir."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        s = v.strip().replace(" ", "T", 1).replace("Z", "+00:00")
        try:
            v = datetime.fromisoformat(s) if len(s) > 10 else date.fromisoformat(s[:10])
        except ValueError:
            return None
    if isinstance(v, datetime):
        if v.hour or v.minute:
            v = (v.replace(tzinfo=UTC) if v.tzinfo is None else v).astimezone(TZ)
        v = v.date()
    if not isinstance(v, date) or v.year < 1901:
        return None
    return v.isoformat()


def guid(v: Any) -> Optional[str]:
    s = text(v)
    return s.lower().strip("{}") if s else None


# ------------------------------------------------------------------ CRM: temsilci, cari, risk


def crm_users_sql(schema: str) -> str:
    """Etkileşimli CRM kullanıcıları ve BMT bayrağı (`new_bmt`, `new_KullancTipi` 1 = BMT, 2 = kurum temsilcisi)."""
    p = prefix(schema)
    return ("SELECT u.SystemUserId AS id, u.FullName AS ad, u.DomainName AS domain,"
            " CAST(u.new_bmt AS int) AS bmt, CAST(u.new_KullancTipi AS int) AS tip"
            f" FROM {p}SystemUserBase u WHERE u.IsDisabled = 0 AND u.DomainName IS NOT NULL AND u.DomainName <> ''")


def crm_accounts_sql(schema: str) -> str:
    """Etkin cariler, sahip (BMT), «BMT İl / BMT Cari» seçimi, il ve il temsilcisi, kanal, risk ve limitler.
    Kişisel kolon (adres, telefon, vergi no) seçilmez."""
    p = prefix(schema)
    return ("SELECT a.AccountId AS account_id, a.Name AS unvan, a.new_CariKodu AS cari_kodu, a.new_logicalref AS logicalref,"
            " a.OwnerId AS owner_id, CAST(a.OwnerIdType AS int) AS owner_type, CAST(a.new_BMTilveyaCari AS int) AS bmt_il_cari,"
            " CAST(a.new_FirmaKanal AS int) AS kanal, il.new_name AS il, il.new_musteritemsilcisi AS il_temsilci,"
            " a.new_acikhesaprisklimiti AS limit_acik, a.new_ceksenet AS limit_cek, a.new_toplamrisklimiti AS limit_toplam,"
            " a.new_acikhesapriski AS risk_acik, a.new_ceksenetriski AS risk_cek, a.new_toplamrisk AS risk_toplam,"
            " a.new_crmaciksiparisriski AS risk_siparis, a.new_CariYilHedef AS yil_hedef"
            f" FROM {p}AccountBase a LEFT JOIN {p}new_illerBase il ON il.new_illerId = a.new_cariyeaitil"
            " WHERE a.StateCode = 0")


def crm_risk_orders_sql(schema: str) -> str:
    """Riske takılmış açık siparişler (cari başına): sayı, tutar, en eski tarih, takılma sebebi."""
    p = prefix(schema)
    codes = ", ".join(str(x) for x in ORDER_RISK_STATUS)
    return ("SELECT s.new_firmaid AS account_id, COUNT(*) AS adet, SUM(s.new_toplamsatistutari) AS tutar,"
            " MIN(s.new_siparistarihi) AS en_eski, MAX(CAST(s.new_risketakilmasebebi AS int)) AS sebep"
            f" FROM {p}new_siparisBase s WHERE s.statecode = 0 AND CAST(s.statuscode AS int) IN ({codes})"
            " GROUP BY s.new_firmaid")


def crm_orders_for_sql(schema: str, account_id: str, limit_days: int, today: date) -> str:
    """Bir carinin son siparişleri (brifing). `account_id` GUID olarak doğrulanır."""
    p = prefix(schema)
    gid = _guid_literal(account_id)
    since = today - timedelta(days=max(1, int(limit_days)))
    return ("SELECT s.new_name AS no, s.new_siparistarihi AS tarih, CAST(s.statuscode AS int) AS durum,"
            " s.new_toplamsatistutari AS tutar, CAST(s.new_risketakilmasebebi AS int) AS sebep"
            f" FROM {p}new_siparisBase s WHERE s.new_firmaid = '{gid}' AND s.statecode = 0"
            f" AND s.new_siparistarihi >= '{_d(since)}' ORDER BY s.new_siparistarihi DESC")


def crm_order_status_sql(schema: str) -> str:
    """Sipariş durum etiketleri (StringMap, Türkçe)."""
    p = prefix(schema)
    return ("SELECT s.AttributeValue AS code, s.Value AS label"
            f" FROM {p}StringMapBase s"
            f" WHERE s.ObjectTypeCode = (SELECT TOP 1 e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_siparis')"
            " AND s.AttributeName = 'statuscode' AND s.LangId = 1055")


def crm_collections_sql(schema: str, since: date) -> str:
    """Tahsilat kayıtları: onay bekleyenlerin hepsi + `since`'ten sonra açılan ya da karara bağlananlar.
    Vergi/TC no, çek no, hesap no, banka/şube numarası seçilmez."""
    p = prefix(schema)
    s = _d(since)
    return ("SELECT t.new_tahsilatId AS id, t.new_name AS ad, t.new_musteriid AS account_id, t.OwnerId AS owner_id,"
            " CAST(t.statuscode AS int) AS durum, CAST(t.new_tahsilattipi AS int) AS tip, t.new_tutar AS tutar,"
            " t.new_vadetarihi AS vade, t.new_tahsilattarihi AS tahsilat_tarihi, t.CreatedOn AS olusturma,"
            " t.new_onaylanmatarihi AS onay_tarihi, t.new_reddedilmetarihi AS red_tarihi,"
            " CAST(t.new_TahsilatReddilmeSebebi AS int) AS red_sebep, t.new_reddilmesebebi AS red_metin, t.ModifiedOn AS degisme"
            f" FROM {p}new_tahsilatBase t WHERE t.statecode = 0"
            f" AND (CAST(t.statuscode AS int) = {T_PENDING} OR t.CreatedOn >= '{s}' OR t.ModifiedOn >= '{s}')")


def crm_visits_sql(schema: str, account_column: str, since: date) -> str:
    """Seçenekli: CRM «Cari Ziyareti» etkinlikleri (tip 4) cari başına son tarih ve sayı. Etkinliği cariye bağlayan kolon
    ölçülmedi (`FIELD_CRM_VISIT_ACCOUNT_COLUMN`); boşsa bu sorgu hiç koşmaz."""
    p = prefix(schema)
    if not _NAME.match(account_column or ""):
        raise SourceError("CRM ziyaret–cari kolonu geçerli bir ad değil.")
    return (f"SELECT e.{account_column} AS account_id, MAX(e.new_GercZiyTarihi) AS son, COUNT(*) AS adet"
            f" FROM {p}new_etkinlikBase e WHERE e.statecode = 0 AND CAST(e.new_ziyarettipi AS int) = 4"
            f" AND e.new_GercZiyTarihi >= '{_d(since)}' GROUP BY e.{account_column}")


_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def _guid_literal(v: str) -> str:
    s = (v or "").strip().strip("{}")
    if not _GUID.match(s):
        raise SourceError("CRM kimliği geçersiz.")
    return s


# ------------------------------------------------------------------ Logo: cari kartı, bakiye, yaşlandırma


def clients_sql(f: str, prefix_: str = "120") -> str:
    """Müşteri carileri: ref, kod, unvan, şehir, kanal (özel kod 2). Adres, telefon, vergi no seçilmez."""
    f = firm(f)
    return (f"SELECT C.LOGICALREF AS ref, C.CODE AS code, C.DEFINITION_ AS unvan, C.CITY AS il, C.SPECODE2 AS kanal"
            f" FROM dbo.LG_{f}_CLCARD C WHERE C.CODE LIKE '{code_prefix(prefix_)}%'")


def aging_sql(f: str, year: int, asof: date, prefix_: str = "120", clientref: Optional[int] = None) -> str:
    """Sertifikalı FIFO yaşlandırmanın cari başına biçimi (kovalar kolon). `clientref` verilirse tek cari.
    Aynı CTE'ler: B = yıl başından bakiye, P = en yeni vadeden geriye birikimli plan, A = açık kalan pay."""
    f = firm(f)
    y0 = f"{int(year)}-01-01"
    only = f" AND L.CLIENTREF = {int(clientref)}" if clientref is not None else ""
    a = _d(asof)
    return f"""
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN = 0 THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
  FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
  WHERE L.CANCELLED = 0 AND C.CODE LIKE '{code_prefix(prefix_)}%' AND L.DATE_ >= '{y0}'{only}
  GROUP BY L.CLIENTREF),
P AS (SELECT PT.CARDREF, PT.DATE_, PT.TOTAL,
    SUM(PT.TOTAL) OVER (PARTITION BY PT.CARDREF ORDER BY PT.DATE_ DESC, PT.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) AS kumulatif
  FROM dbo.LG_{f}_01_PAYTRANS PT WHERE PT.CANCELLED = 0 AND PT.SIGN = 0 AND PT.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye > 0)),
A AS (SELECT P.CARDREF, DATEDIFF(day, P.DATE_, '{a}') AS gun,
    CASE WHEN B.bakiye >= P.kumulatif THEN P.TOTAL WHEN B.bakiye > P.kumulatif - P.TOTAL THEN B.bakiye - (P.kumulatif - P.TOTAL) ELSE 0 END AS acik
  FROM P JOIN B ON B.CLIENTREF = P.CARDREF)
SELECT B.CLIENTREF AS ref, B.bakiye AS bakiye,
  SUM(CASE WHEN A.acik > 0 AND A.gun <= 0 THEN A.acik ELSE 0 END) AS gelmemis,
  SUM(CASE WHEN A.acik > 0 AND A.gun BETWEEN 1 AND 30 THEN A.acik ELSE 0 END) AS k_1_30,
  SUM(CASE WHEN A.acik > 0 AND A.gun BETWEEN 31 AND 60 THEN A.acik ELSE 0 END) AS k_31_60,
  SUM(CASE WHEN A.acik > 0 AND A.gun BETWEEN 61 AND 90 THEN A.acik ELSE 0 END) AS k_61_90,
  SUM(CASE WHEN A.acik > 0 AND A.gun > 90 THEN A.acik ELSE 0 END) AS k_90p
FROM B LEFT JOIN A ON A.CARDREF = B.CLIENTREF
GROUP BY B.CLIENTREF, B.bakiye""".strip()


def payments_sql(f: str, since: date, codes: tuple[int, ...], prefix_: str = "120") -> str:
    """Cari başına ödeme (alacak satırı, ayardaki TRCODE'lar): son ödeme tarihi, penceredeki toplam."""
    f = firm(f)
    tc = ", ".join(str(int(c)) for c in codes)
    return (f"SELECT C.CODE AS code, MAX(L.DATE_) AS son, SUM(L.AMOUNT) AS toplam, COUNT(*) AS adet"
            f" FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF"
            f" WHERE L.CANCELLED = 0 AND L.SIGN = 1 AND L.TRCODE IN ({tc}) AND C.CODE LIKE '{code_prefix(prefix_)}%'"
            f" AND L.DATE_ >= '{_d(since)}' GROUP BY C.CODE")


def last_payment_sql(f: str, code: str, codes: tuple[int, ...]) -> str:
    """Tek carinin son ödeme satırı (tarih, tutar, tür)."""
    f = firm(f)
    tc = ", ".join(str(int(c)) for c in codes)
    return (f"SELECT TOP 5 L.DATE_ AS tarih, L.AMOUNT AS tutar, L.TRCODE AS tur"
            f" FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF"
            f" WHERE L.CANCELLED = 0 AND L.SIGN = 1 AND L.TRCODE IN ({tc}) AND C.CODE = '{_code_literal(code)}'"
            f" ORDER BY L.DATE_ DESC, L.LOGICALREF DESC")


def sales_sql(f: str, start: date, end: date, prefix_: str = "120") -> str:
    """Cari başına faturalı satış ve iade (net ciro = satış − iade), son fatura tarihi. [start, end] kapalı aralık."""
    f = firm(f)
    return (f"SELECT C.CODE AS code,"
            f" SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE 0 END) AS satis,"
            f" SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.VATMATRAH ELSE 0 END) AS iade,"
            f" MAX(CASE WHEN S.TRCODE IN (7,8,9) THEN SH.DATE_ END) AS son_fatura"
            f" FROM dbo.LG_{f}_01_STLINE S"
            f" JOIN dbo.LG_{f}_01_INVOICE SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0"
            f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
            f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
            f" AND C.CODE LIKE '{code_prefix(prefix_)}%'"
            f" AND SH.DATE_ >= '{_d(start)}' AND SH.DATE_ < '{_d(end + timedelta(days=1))}'"
            f" GROUP BY C.CODE")


def invoices_for_sql(f: str, code: str, limit: int = 3) -> str:
    """Tek carinin son satış faturaları (brifing «son siparişler»): tarih, belge no, net tutar."""
    f = firm(f)
    return (f"SELECT TOP {max(1, int(limit))} I.DATE_ AS tarih, I.FICHENO AS no, I.TRCODE AS tur, I.NETTOTAL AS tutar"
            f" FROM dbo.LG_{f}_01_INVOICE I JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = I.CLIENTREF"
            f" WHERE I.CANCELLED = 0 AND I.TRCODE IN (7,8,9) AND C.CODE = '{_code_literal(code)}'"
            f" ORDER BY I.DATE_ DESC, I.LOGICALREF DESC")


def items_for_sql(f: str, code: str, start: date, end: date) -> str:
    """Tek carinin kitap (stok kodu) başına net adet ve net ciro."""
    f = firm(f)
    return (f"SELECT I.CODE AS stok, MAX(I.NAME) AS ad,"
            f" SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,"
            f" SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE -S.VATMATRAH END) AS ciro"
            f" FROM dbo.LG_{f}_01_STLINE S"
            f" JOIN dbo.LG_{f}_01_INVOICE SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0"
            f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
            f" JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
            f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
            f" AND C.CODE = '{_code_literal(code)}' AND SH.DATE_ >= '{_d(start)}' AND SH.DATE_ < '{_d(end + timedelta(days=1))}'"
            f" GROUP BY I.CODE")


def similar_items_sql(f: str, code: str, city: Optional[str], channel: Optional[str], start: date, end: date,
                      prefix_: str = "120") -> str:
    """Benzer cariler (aynı şehir ve aynı kanal özel kodu, bu cari hariç) kitap × cari: net adet, ciro. Ayrı cari sayısı
    Python'da birleştirilir (iki yıl firmasında cari ref'i farklı, kod aynı)."""
    f = firm(f)
    conds = []
    if city:
        conds.append(f"C.CITY = N'{_str_literal(city)}'")
    if channel:
        conds.append(f"C.SPECODE2 = N'{_str_literal(channel)}'")
    if not conds:
        raise SourceError("Benzer cari için şehir ya da kanal gerekli.")
    return (f"SELECT I.CODE AS stok, MAX(I.NAME) AS ad, C.CODE AS cari,"
            f" SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,"
            f" SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE -S.VATMATRAH END) AS ciro"
            f" FROM dbo.LG_{f}_01_STLINE S"
            f" JOIN dbo.LG_{f}_01_INVOICE SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0"
            f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
            f" JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
            f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
            f" AND C.CODE LIKE '{code_prefix(prefix_)}%' AND C.CODE <> '{_code_literal(code)}' AND {' AND '.join(conds)}"
            f" AND SH.DATE_ >= '{_d(start)}' AND SH.DATE_ < '{_d(end + timedelta(days=1))}'"
            f" GROUP BY I.CODE, C.CODE")


def first_sales_sql(f: str, since: date) -> str:
    """Firmada ilk faturalı satışı `since`'ten sonra olan kitaplar (yeni çıkanlar; önceki yıl firmasında satışı olmayanlar
    ayrıca elenir)."""
    f = firm(f)
    return (f"SELECT I.CODE AS stok, MAX(I.NAME) AS ad, MIN(S.DATE_) AS ilk"
            f" FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
            f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9)"
            f" GROUP BY I.CODE HAVING MIN(S.DATE_) >= '{_d(since)}'")


def sold_codes_sql(f: str) -> str:
    f = firm(f)
    return (f"SELECT DISTINCT I.CODE AS stok FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
            f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9)")


def cheque_events_sql(f: str, since: date, prefix_: str = "120") -> str:
    """Kural 12 olay okuması, cari kodu başına: `since`'ten sonra karşılıksız çıkan ve protesto edilen müşteri çek/senedi
    (çek başına bir kez, tutar `CSCARD.AMOUNT`). Çekin carisi = portföye giriş hareketinin `CARDREF`'i."""
    f = firm(f)
    s = _d(since)
    return f"""
WITH O AS (SELECT G.CSREF, MIN(G.CARDREF) AS cari FROM dbo.LG_{f}_01_CSTRANS G
  WHERE G.STATUS = 1 AND G.CANCELLED = 0 AND G.CARDREF > 0 GROUP BY G.CSREF),
K AS (SELECT K.LOGICALREF, K.AMOUNT, O.cari,
    CASE WHEN EXISTS (SELECT 1 FROM dbo.LG_{f}_01_CSTRANS T WHERE T.CSREF = K.LOGICALREF AND T.STATUS = 11
      AND T.DEVIR = 0 AND T.CANCELLED = 0 AND T.DATE_ >= '{s}') THEN 1 ELSE 0 END AS karsiliksiz,
    CASE WHEN EXISTS (SELECT 1 FROM dbo.LG_{f}_01_CSTRANS T WHERE T.CSREF = K.LOGICALREF AND T.STATUS IN (5, 7)
      AND T.DEVIR = 0 AND T.CANCELLED = 0 AND T.DATE_ >= '{s}') THEN 1 ELSE 0 END AS protesto,
    (SELECT MAX(T.DATE_) FROM dbo.LG_{f}_01_CSTRANS T WHERE T.CSREF = K.LOGICALREF AND T.STATUS IN (5, 7, 11)
      AND T.DEVIR = 0 AND T.CANCELLED = 0 AND T.DATE_ >= '{s}') AS son
  FROM dbo.LG_{f}_01_CSCARD K JOIN O ON O.CSREF = K.LOGICALREF
  WHERE K.CANCELLED = 0 AND K.DOC IN (1, 2))
SELECT C.CODE AS code,
  SUM(K.karsiliksiz) AS karsiliksiz_adet, SUM(CASE WHEN K.karsiliksiz = 1 THEN K.AMOUNT ELSE 0 END) AS karsiliksiz_tutar,
  SUM(K.protesto) AS protesto_adet, SUM(CASE WHEN K.protesto = 1 THEN K.AMOUNT ELSE 0 END) AS protesto_tutar,
  MAX(K.son) AS son
FROM K JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = K.cari
WHERE (K.karsiliksiz = 1 OR K.protesto = 1) AND C.CODE LIKE '{code_prefix(prefix_)}%'
GROUP BY C.CODE""".strip()


def data_end_sql(f: str) -> str:
    f = firm(f)
    return (f"SELECT MAX(DATE_) AS son FROM dbo.LG_{f}_01_STLINE "
            f"WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9)")


# ------------------------------------------------------------------ seçenekli: saha uygulaması (VW_MMX_*)


def mmx_visits_sql(f: str, since: date) -> str:
    """Cari kodu başına son ziyaret tarihi ve sayı. İçerik, konum, görüşülen kişi ve telefonu seçilmez."""
    f = firm(f)
    return (f"SELECT V.CARI_KODU AS code, MAX(V.TARIH) AS son, COUNT(*) AS adet FROM dbo.VW_MMX_{f}_ZIYARET V"
            f" WHERE V.TARIH >= '{_d(since)}' GROUP BY V.CARI_KODU")


def mmx_collections_sql(f: str, since: date) -> str:
    """Saha uygulamasına girilen tahsilat/ödeme: cari kodu, belge no, tür, tutar, vade, kayıt tarihi, senkron durumu,
    satış elemanı adı. Çek/senet ayrıntısı (JSON), banka hesap no seçilmez."""
    f = firm(f)
    return (f"SELECT M.CARI_CODE AS code, M.FICHE_NO AS no, M.CP_TYPENAME AS tur, M.TOTAL AS tutar, M.EXPIRY_DATE AS vade,"
            f" M.CREATED_DATE AS tarih, M.IS_SYNC AS senkron, M.STATUS AS durum, M.SLSMAN_DEFINITION AS eleman"
            f" FROM dbo.VW_MMX_{f}_01_COLLECTION_PAYMENT M WHERE M.CREATED_DATE >= '{_d(since)}'")


# ------------------------------------------------------------------ literal güvenliği


_CODE_OK = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü .\-_/]{1,40}$")


def _code_literal(code: str) -> str:
    s = (code or "").strip()
    if not _CODE_OK.match(s):
        raise SourceError("Cari kodu geçersiz.")
    return s.replace("'", "''")


def _str_literal(v: str) -> str:
    return str(v)[:80].replace("'", "''")


# ------------------------------------------------------------------ okuma (çağıran bağlantıyı verir)


def query_tag(sql: str) -> str:
    """Okumada çalışan SQL'in hangi okuma olduğu (sorgu bilgisi başlığı için; yukarıdaki üreticilerin ayırt edici
    parçalarından). Logo okumalarında firma kopyası ve pencere başı etikete girer."""
    s = sql or ""
    firm_ = re.search(r"LG_(\d+)_", s)
    f = firm_.group(1) if firm_ else ""
    since = re.search(r"DATE_ >= '(\d{4}-\d{2}-\d{2})'", s)
    d = since.group(1) if since else ""
    if "L_CAPIPERIOD" in s:
        return "logo.donem"
    # M38 (müşteri ilişkileri) okumaları
    if "InternalEMailAddress AS eposta" in s:
        return "crm.kullanici_eposta"
    if "AS kapali" in s and "SystemUserBase" in s:
        return "crm.tum_kullanicilar"
    if "MAX(s.new_siparistarihi) AS son" in s:
        return "crm.son_siparis"
    if "new_VergiDairesi" in s:
        return "crm.cari_saglik"
    if "ContactBase" in s:
        return "crm.kisiler"
    if "INFORMATION_SCHEMA" in s or "new_webservicelogBase" in s:
        return "crm.guvenlik"
    if "COUNT(*) AS n FROM" in s and "AccountBase WHERE StateCode" in s:
        return "crm.cari_sayisi"
    if "COUNT(*) AS n FROM" in s:
        return "crm.guvenlik"
    if "GROUP BY k." in s:
        return "crm.kampanya"
    if "S.DATE_ AS gun" in s or "SH.DATE_ AS gun" in s:
        return f"logo.gunluk_satis.{f}.{d}"
    if "YEAR(S.DATE_) AS yil" in s or "YEAR(SH.DATE_) AS yil" in s:
        return f"logo.aylik_cari.{f}.{d}"
    if "C.CODE AS code FROM" in s and "_CLCARD" in s:
        return f"logo.cari_kodlari.{f}"
    # M59 (bayi riski) okumaları: aynı kaynak dosyasının üreticileriyle birlikte
    if "CreditOnHold" in s:
        return "crm.cari_bayrak"
    if "new_anliklimit" in s:
        return "crm.risk_gecmisi"
    if "YEAR(S.DATE_) AS y" in s or "YEAR(SH.DATE_) AS y" in s:
        return f"logo.aylik_satis.{f}.{d}"
    if "YEAR(L.DATE_) AS y" in s:
        return f"logo.aylik_odeme.{f}.{d}"
    if "VW_MMX_" in s:
        return "logo.saha_ziyaret" if "ZIYARET" in s else "logo.saha_tahsilat"
    if "SystemUserBase u WHERE u.IsDisabled" in s:
        return "crm.kullanicilar"
    if "new_tahsilatBase" in s:
        return "crm.tahsilat"
    if "new_etkinlikBase" in s:
        return "crm.ziyaret"
    if "StringMapBase" in s:
        return "crm.siparis_durum"
    if "new_siparisBase s WHERE s.new_firmaid =" in s:
        return "crm.siparisler"
    if "new_siparisBase" in s:
        return "crm.riskli_siparis"
    if "AccountBase a" in s:
        return "crm.cariler"
    if "MAX(DATE_) AS son FROM" in s:
        return f"logo.verisonu.{f}"
    if "_CSTRANS" in s:
        return f"logo.cek.{f}"
    if "WITH B AS" in s:
        return f"logo.yaslandirma.{f}"
    if "SELECT TOP 5 L.DATE_" in s:
        return f"logo.son_odeme.{f}"
    if "_CLFLINE" in s:
        return f"logo.odeme.{f}"
    if "_01_INVOICE I " in s:  # satış satırının fatura bağı (SH) değil, fatura listesi
        return f"logo.faturalar.{f}"
    if "AS son_fatura" in s:
        return f"logo.satis.{f}.{d}"
    if "C.CODE AS cari" in s:
        return f"logo.benzer.{f}.{d}"
    if "MIN(S.DATE_) AS ilk" in s:
        return f"logo.yeni_kitap.{f}"
    if "SELECT DISTINCT I.CODE AS stok" in s:
        return f"logo.satilmis.{f}"
    if "_ITEMS I" in s:
        return f"logo.kitaplar.{f}.{d}"
    if "_CLCARD C WHERE" in s:
        return f"logo.cariler.{f}"
    return "diger"


def read_rows(run: Run, sql: str) -> list[dict[str, Any]]:
    return lower_keys(run(sql))


def read_aging(run: Run, f: str, year: int, asof: date, prefix_: str = "120") -> dict[int, dict[str, float]]:
    """Cari ref → bakiye, gelmemiş, kovalar, vadesi geçmiş ve plansız bakiye (M59 aynı fonksiyonu kullanır)."""
    out: dict[int, dict[str, float]] = {}
    for r in read_rows(run, aging_sql(f, year, asof, prefix_)):
        k = {x: round(num(r.get(x)), 2) for x in ("bakiye", "gelmemis", "k_1_30", "k_31_60", "k_61_90", "k_90p")}
        k["vadesi_gecmis"] = round(k["k_1_30"] + k["k_31_60"] + k["k_61_90"] + k["k_90p"], 2)
        k["plansiz"] = round(max(0.0, k["bakiye"] - k["vadesi_gecmis"] - k["gelmemis"]), 2) if k["bakiye"] > 0 else 0.0
        out[int(r["ref"])] = k
    return out


def read_cheque_events(run: Run, firms: Iterable[str], since: date, prefix_: str = "120") -> dict[str, dict[str, Any]]:
    """Cari kodu → karşılıksız/protesto olayları (firmalar toplanır: 12 ay iki yılı kesebilir)."""
    out: dict[str, dict[str, Any]] = {}
    for f in firms:
        for r in read_rows(run, cheque_events_sql(f, since, prefix_)):
            code = text(r.get("code"))
            if not code:
                continue
            cur = out.setdefault(code, {"karsiliksiz_adet": 0, "karsiliksiz_tutar": 0.0, "protesto_adet": 0,
                                        "protesto_tutar": 0.0, "son": None})
            cur["karsiliksiz_adet"] += int(num(r.get("karsiliksiz_adet")))
            cur["karsiliksiz_tutar"] += num(r.get("karsiliksiz_tutar"))
            cur["protesto_adet"] += int(num(r.get("protesto_adet")))
            cur["protesto_tutar"] += num(r.get("protesto_tutar"))
            d = day(r.get("son"))
            if d and (cur["son"] is None or d > cur["son"]):
                cur["son"] = d
    return out


#: Bu tutarın altındaki limit «tanımlanmamış» sayılır. 2026-09-28 CRM: 44.322 etkin carinin 6.086'sında toplam limit tam
#: 1 ₺ (yurt dışı dağıtıcılar dahil, riski milyonlarca ₺), 22'sinde 2–10 ₺; portföyde 10 ₺'den büyük limitli 3.094 carinin
#: yalnız 15'i 1.000 ₺'nin altında (12 ₺ gibi), gerçek limitler 2.501 / 5.000 / 15.000 ₺'den başlıyor. Yer tutucu limit
#: doluluğu «%47.799.611» gibi anlamsız sayılar veriyordu.
MIN_REAL_LIMIT = 1000.0


def risk_of(acc: dict[str, Any]) -> dict[str, Any]:
    """CRM limit/risk alanlarından doluluk (M59 aynı fonksiyonu kullanır). Limit 0/boş ya da `MIN_REAL_LIMIT`in altında
    (yer tutucu) ise doluluk yok (aşmış sayılmaz)."""
    lim, risk = opt_num(acc.get("limit_toplam")), opt_num(acc.get("risk_toplam"))
    return {
        "limit_acik": opt_num(acc.get("limit_acik")), "limit_cek": opt_num(acc.get("limit_cek")), "limit_toplam": lim,
        "risk_acik": opt_num(acc.get("risk_acik")), "risk_cek": opt_num(acc.get("risk_cek")), "risk_toplam": risk,
        "risk_siparis": opt_num(acc.get("risk_siparis")),
        "risk_doluluk": (round(risk / lim, 4) if lim and lim >= MIN_REAL_LIMIT and risk is not None else None),
    }


def read_crm_risk(run: Run, schema: str) -> dict[str, dict[str, Any]]:
    """CRM cari GUID → risk/limit ve riske takılmış sipariş özeti (M59 okur)."""
    accs = {guid(r.get("account_id")): risk_of(r) for r in read_rows(run, crm_accounts_sql(schema))}
    for r in read_rows(run, crm_risk_orders_sql(schema)):
        g = guid(r.get("account_id"))
        if g in accs:
            accs[g]["siparis_riskte"] = int(num(r.get("adet")))
            accs[g]["siparis_riskte_tutar"] = num(r.get("tutar"))
            accs[g]["siparis_riskte_sebep"] = ORDER_RISK_REASON.get(int(num(r.get("sebep"))))
    return accs
