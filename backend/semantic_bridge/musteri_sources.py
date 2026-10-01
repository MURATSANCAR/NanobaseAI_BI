"""M38 Müşteri ilişkileri ve CRM yönetimi: Logo ve CRM okuması (yalnız okuma).

**M30 ile ortak kaynak.** Temsilci ↔ cari ataması, cari kartı, CRM kullanıcıları, tek carinin son faturaları ve kitap
kırılımı, kredi riski göstergesi M30'un fonksiyonlarıdır (`field_sales_sources` / `field_sales`); burada yeniden
yazılmaz. Bu dosya yalnız M38'e özgü okumaları taşır:

- **Günlük alım** — Logo faturalı satır (`STLINE`, `LINETYPE = 0`, `INVOICEREF <> 0`, `CANCELLED = 0`; TRCODE 7/8/9 satış,
  2/3 iade; tutar `VATMATRAH` (KDV matrahı, fatura geneli iskonto dahil; dönem fatura tarihi `INVOICE.DATE_` — karar
  2026-10-01), M30/M46 ile aynı tanım), cari kodu × gün. Carinin 12 ay değeri, önceki 12 ay, iade oranı,
  alım günleri (medyan aralık), aylık grafik ve aksiyonun 30/90 gün sonucu bu tek okumadan hesaplanır.
  Yıllar Logo'da ayrı firmadır (411 = 2026, 211 = 2021–2025): her firma yalnız **kendi yıllarının tarih aralığında**
  okunur (aynı gün iki kopyadan iki kez sayılmaz) ve cari **kodla** (`CLCARD.CODE`) birleşir; LOGICALREF firmalar arasında
  aynı sayılmaz. Birleşim Python'da kolon adıyla yapılır; `SELECT *` UNION yok.
- **CRM sipariş** — cari başına son sipariş tarihi ve 12 ay sipariş sayısı (`new_siparisBase`). CRM canlıdır; Logo kopyası
  donmuş olabileceği için «Logo kesiminden sonra sipariş var» bilgisi risk nedenine yazılır.
- **Veri sağlığı** — etkin cari kartları (ticari alanlar: ad, il, vergi dairesi, kod, bağ, kanal, sahip, izin bayrakları),
  kişi kayıtlarının izin bayrakları (ad/telefon/e-posta **seçilmez**), kampanya gönderimi (seçenekli), güvenlik bulgusu
  için yalnız **varlık ve sayı** (şifre içeren kolonun değeri hiçbir sorguda seçilmez; `new_kargofirmasi` tablosunun
  kolonlarına sorgu atılmaz, yalnız kolon adının varlığı okunur).

Kişisel kolonlar (vergi no/TC, telefon, e-posta, adres, IBAN, kişi adı) hiçbir sorguda seçilmez.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Iterable, Optional

from semantic_bridge import field_sales_sources as fs
from semantic_bridge.field_sales_sources import SourceError, code_prefix, day, firm, guid, lower_keys, num, prefix, text

__all__ = ["SourceError", "day", "guid", "num", "text", "lower_keys"]

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CODE_OK = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü .\-_/]{1,40}$")

#: CRM `AccountBase.new_cariozelKod2` (kanal tipi; Logo özel kod 2 ile eşleşir).
KANAL_TIPI = {100000000: "ABONE", 100000001: "BAYI", 100000002: "DAGITICI", 100000003: "E-TICARET", 100000004: "FUAR",
              100000005: "INTERNET", 100000006: "KITAPCI", 100000007: "KURUM", 100000008: "MAGAZA", 100000009: "MARKET",
              100000010: "MERKEZ", 100000011: "NIHAI"}
#: Güvenlik taramasında kolon adı eşleşen tablo listesi; bu tabloların kolonlarına hiç sorgu atılmaz (kullanıcı kararı
#: 2026-09-28: `new_kargofirmasi` parola/token/secret kolonları hiçbir sorguda seçilmez).
NEVER_QUERY_TABLES = ("new_kargofirmasiBase", "new_kargofirmasi")
SECRET_COLUMN_PATTERNS = ("%sifre%", "%şifre%", "%password%", "%parola%", "%secret%", "%token%")


def code_literal(code: str) -> str:
    s = (code or "").strip()
    if not _CODE_OK.match(s):
        raise SourceError("Cari kodu geçersiz.")
    return s.replace("'", "''")


def _d(d: date) -> str:
    return d.isoformat()


# ------------------------------------------------------------------ Logo: günlük alım (firma yıllarına kırpılmış pencere)


def firm_windows(firms: dict[int, str], start: date, end: date) -> list[tuple[str, date, date]]:
    """[start, end] penceresini firmalara böler: her firma yalnız kendi yıllarının aralığında okunur. Aynı yılı iki firma
    tutmaz (`firms_by_year` tekilleştirir), dolayısıyla bir gün iki kez sayılmaz."""
    by_firm: dict[str, list[int]] = {}
    for y, f in firms.items():
        by_firm.setdefault(f, []).append(int(y))
    out = []
    for f, years in sorted(by_firm.items(), key=lambda kv: min(kv[1])):
        lo, hi = max(start, date(min(years), 1, 1)), min(end, date(max(years), 12, 31))
        if lo <= hi:
            out.append((f, lo, hi))
    return out


def daily_sales_sql(f: str, start: date, end: date, prefix_: str = "120") -> str:
    """Cari kodu × gün: faturalı satış ve iade (`VATMATRAH`), satış faturası sayısı. [start, end] kapalı aralık."""
    f = firm(f)
    return (f"SELECT C.CODE AS code, SH.DATE_ AS gun,"
            f" SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE 0 END) AS satis,"
            f" SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.VATMATRAH ELSE 0 END) AS iade,"
            f" COUNT(DISTINCT CASE WHEN S.TRCODE IN (7,8,9) THEN S.INVOICEREF END) AS fatura"
            f" FROM dbo.LG_{f}_01_STLINE S"
            f" JOIN dbo.LG_{f}_01_INVOICE SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0"
            f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
            f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
            f" AND C.CODE LIKE '{code_prefix(prefix_)}%'"
            f" AND SH.DATE_ >= '{_d(start)}' AND SH.DATE_ < '{_d(end + timedelta(days=1))}'"
            f" GROUP BY C.CODE, SH.DATE_")


def monthly_sql(f: str, code: str, start: date, end: date) -> str:
    """Tek carinin aylık faturalı satış ve iadesi (cari ayrıntısı grafiği; canlı okuma)."""
    f = firm(f)
    return (f"SELECT YEAR(SH.DATE_) AS yil, MONTH(SH.DATE_) AS ay,"
            f" SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE 0 END) AS satis,"
            f" SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.VATMATRAH ELSE 0 END) AS iade"
            f" FROM dbo.LG_{f}_01_STLINE S"
            f" JOIN dbo.LG_{f}_01_INVOICE SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0"
            f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
            f" WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
            f" AND C.CODE = '{code_literal(code)}'"
            f" AND SH.DATE_ >= '{_d(start)}' AND SH.DATE_ < '{_d(end + timedelta(days=1))}'"
            f" GROUP BY YEAR(SH.DATE_), MONTH(SH.DATE_)")


def all_client_codes_sql(f: str) -> str:
    """Firmadaki bütün cari kodları ve ref'leri (veri sağlığı: CRM kaydının Logo'da karşılığı var mı). Yalnız kod ve ref."""
    f = firm(f)
    return f"SELECT C.LOGICALREF AS ref, C.CODE AS code FROM dbo.LG_{f}_CLCARD C"


def read_daily(run: fs.Run, firms: dict[int, str], start: date, end: date, prefix_: str = "120") -> dict[str, dict[str, dict[str, float]]]:
    """Cari kodu → gün → {satis, iade, fatura}. Firmalar kendi yıllarına kırpılır; kod üzerinden birleşir."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    for f, lo, hi in firm_windows(firms, start, end):
        for r in fs.read_rows(run, daily_sales_sql(f, lo, hi, prefix_)):
            code, g = text(r.get("code")), day(r.get("gun"))
            if not code or not g:
                continue
            cur = out.setdefault(code, {}).setdefault(g, {"satis": 0.0, "iade": 0.0, "fatura": 0.0})
            cur["satis"] += num(r.get("satis"))
            cur["iade"] += num(r.get("iade"))
            cur["fatura"] += num(r.get("fatura"))
    return out


def read_monthly(run: fs.Run, firms: dict[int, str], code: str, start: date, end: date) -> list[dict[str, Any]]:
    acc: dict[tuple[int, int], dict[str, float]] = {}
    for f, lo, hi in firm_windows(firms, start, end):
        for r in fs.read_rows(run, monthly_sql(f, code, lo, hi)):
            k = (int(num(r.get("yil"))), int(num(r.get("ay"))))
            cur = acc.setdefault(k, {"satis": 0.0, "iade": 0.0})
            cur["satis"] += num(r.get("satis"))
            cur["iade"] += num(r.get("iade"))
    return [{"ay": f"{y:04d}-{m:02d}", "satis": round(v["satis"], 2), "iade": round(v["iade"], 2),
             "net": round(v["satis"] - v["iade"], 2)} for (y, m), v in sorted(acc.items())]


def read_clients(run: fs.Run, cur_firm: str, prev_firms: Iterable[str], prefix_: str = "120") -> list[dict[str, Any]]:
    """M30'un cari kartı okuması (`clients_sql`) bu yılın ve önceki yıl firmalarından; kod üzerinden birleşir, bu yılın
    kartı kazanır. Yalnız önceki yılda kartı olan cari (bu yıl alım yok) de listeye girer."""
    cur = fs.read_rows(run, fs.clients_sql(cur_firm, prefix_))
    seen = {text(c.get("code")) for c in cur}
    older: list[dict[str, Any]] = []
    for pf in prev_firms:
        for c in fs.read_rows(run, fs.clients_sql(pf, prefix_)):
            code = text(c.get("code"))
            if code and code not in seen:
                seen.add(code)
                older.append({**c, "ref": -1})     # ref yalnız bu yılın firmasında anlamlı; eski kart ref ile eşlenmez
    return older + cur                               # by_ref sözlüğünde bu yılın kartı en son yazılır


# ------------------------------------------------------------------ CRM: sipariş, kullanıcı e-postası


def crm_last_orders_sql(schema: str, since: date) -> str:
    """Cari başına son sipariş tarihi (tüm zaman) ve `since`'ten sonraki sipariş sayısı."""
    p = prefix(schema)
    return ("SELECT s.new_firmaid AS account_id, MAX(s.new_siparistarihi) AS son,"
            f" SUM(CASE WHEN s.new_siparistarihi >= '{_d(since)}' THEN 1 ELSE 0 END) AS adet"
            f" FROM {p}new_siparisBase s WHERE s.statecode = 0 AND s.new_firmaid IS NOT NULL GROUP BY s.new_firmaid")


def crm_user_mail_sql(schema: str) -> str:
    """İç e-posta (yalnız çalışanın kurum adresi; haftalık risk özeti temsilcinin kendisine gider)."""
    p = prefix(schema)
    return ("SELECT u.SystemUserId AS id, u.DomainName AS domain, u.InternalEMailAddress AS eposta"
            f" FROM {p}SystemUserBase u WHERE u.IsDisabled = 0 AND u.DomainName IS NOT NULL AND u.DomainName <> ''")


# ------------------------------------------------------------------ CRM: veri sağlığı


def crm_health_accounts_sql(schema: str) -> str:
    """Etkin carilerin veri sağlığı kolonları. Vergi **dairesi** ticari bilgidir ve tekrar adayında kullanılır; vergi
    numarası (şahısta TC) seçilmez. Sahibin kim olduğu için kullanıcı adı ayrı sorguda (M30 `crm_users_sql`)."""
    p = prefix(schema)
    return ("SELECT a.AccountId AS account_id, a.Name AS ad, a.new_CariKodu AS cari_kodu, a.new_logicalref AS logicalref,"
            " a.OwnerId AS owner_id, CAST(a.OwnerIdType AS int) AS owner_type,"
            " CAST(a.new_FirmaKanal AS int) AS kanal, CAST(a.new_cariozelKod2 AS int) AS kanal_tipi,"
            " il.new_name AS il, a.new_VergiDairesi AS vergi_dairesi, a.CreatedOn AS olusturma,"
            " CAST(a.new_caricalismasekli AS int) AS calisma, CAST(a.new_sahissirketi AS int) AS sahis,"
            " CAST(a.new_carituru AS int) AS cari_turu, CAST(a.obs_iys_customertype AS int) AS iys_tip,"
            " CAST(a.DoNotEMail AS int) AS eposta_yok, CAST(a.DoNotBulkEMail AS int) AS toplu_yok,"
            " CAST(a.obs_donotsms AS int) AS sms_izni, a.obs_emailpermissionupdatedate AS eposta_izin_tarihi,"
            " CASE WHEN ISNULL(a.new_izinalinanurl, '') = '' AND ISNULL(a.new_izinalinanipadresi, '') = '' THEN 0 ELSE 1 END AS izin_kaniti"
            f" FROM {p}AccountBase a LEFT JOIN {p}new_illerBase il ON il.new_illerId = a.new_cariyeaitil"
            " WHERE a.StateCode = 0")


def crm_all_users_sql(schema: str) -> str:
    """Bütün kullanıcılar (devre dışı olanlar dahil): sahipsiz kayıt = sahibi devre dışı kullanıcı ya da takım."""
    p = prefix(schema)
    return ("SELECT u.SystemUserId AS id, u.FullName AS ad, CAST(u.IsDisabled AS int) AS kapali"
            f" FROM {p}SystemUserBase u")


def crm_contact_consent_sql(schema: str) -> str:
    """Kişi kayıtlarının izin bayrakları ve bağlı olduğu cari. Kişinin adı, telefonu, e-postası **seçilmez**."""
    p = prefix(schema)
    return ("SELECT c.ContactId AS contact_id, c.ParentCustomerId AS account_id,"
            " CAST(c.new_kvkkonayi AS int) AS kvkk, CAST(c.new_iysonayi AS int) AS iys,"
            " CAST(c.DoNotBulkEMail AS int) AS toplu_yok, CAST(c.DoNotEMail AS int) AS eposta_yok,"
            " CAST(c.new_VeriDurumu AS int) AS veri_durumu"
            f" FROM {p}ContactBase c WHERE c.StateCode = 0")


def crm_campaign_sends_sql(schema: str, table: str, account_col: str, date_col: str, since: date) -> str:
    """Seçenekli: cariye kampanya gönderimi (cari başına son gönderim tarihi ve sayı). Tablo ve kolon adları ayardan
    (`MUSTERI_CAMPAIGN_*`); yapısı ölçülecek."""
    p = prefix(schema)
    for n in (table, account_col, date_col):
        if not _NAME.match(n or ""):
            raise SourceError("Kampanya tablosu/kolonu geçerli bir ad değil.")
    return (f"SELECT k.{account_col} AS account_id, MAX(k.{date_col}) AS son, COUNT(*) AS adet"
            f" FROM {p}{table} k WHERE k.{date_col} >= '{_d(since)}' AND k.{account_col} IS NOT NULL GROUP BY k.{account_col}")


def secret_columns_sql(schema: str) -> str:
    """Şifre/parola/token/secret adlı kolonlar (yalnız ad; değer okunmaz). Veritabanı adı şemadan."""
    db, _, _sch = (schema or "").strip().rpartition(".")
    info = f"{db}.INFORMATION_SCHEMA.COLUMNS" if db else "INFORMATION_SCHEMA.COLUMNS"
    if db and not _NAME.match(db):
        raise SourceError("CRM veritabanı adı geçersiz.")
    likes = " OR ".join(f"LOWER(COLUMN_NAME) LIKE N'{x}'" for x in SECRET_COLUMN_PATTERNS)
    return (f"SELECT TABLE_NAME AS tablo, COLUMN_NAME AS kolon FROM {info} WHERE ({likes})"
            " AND DATA_TYPE IN ('nvarchar','varchar','ntext','text','nchar','char')")


def secret_count_sql(schema: str, table: str, column: str) -> str:
    """Kolonun dolu satır sayısı (değer seçilmez). `NEVER_QUERY_TABLES` için çağrılmaz."""
    if table in NEVER_QUERY_TABLES or table.lower().startswith("new_kargofirmasi"):
        raise SourceError("Bu tabloya sorgu atılmaz.")
    p = prefix(schema)
    for n in (table, column):
        if not _NAME.match(n or ""):
            raise SourceError("Tablo/kolon adı geçersiz.")
    return f"SELECT COUNT(*) AS n FROM {p}{table} WHERE {column} IS NOT NULL AND LEN(CAST({column} AS nvarchar(20))) > 0"


def webservice_log_secret_sql(schema: str) -> str:
    """Web servis günlüğünde istek gövdesi şifre alanı taşıyan satır sayısı (yalnız sayı)."""
    p = prefix(schema)
    return (f"SELECT COUNT(*) AS n FROM {p}new_webservicelogBase w WHERE w.new_requestJSON LIKE N'%sifre%'"
            " OR w.new_requestJSON LIKE N'%password%' OR w.new_requestJSON LIKE N'%parola%'")


def views_sql(schema: str, like: str = "%password%") -> str:
    """Adı şifre çağrıştıran görünümler (yalnız ad)."""
    db, _, _sch = (schema or "").strip().rpartition(".")
    if db and not _NAME.match(db):
        raise SourceError("CRM veritabanı adı geçersiz.")
    info = f"{db}.INFORMATION_SCHEMA.VIEWS" if db else "INFORMATION_SCHEMA.VIEWS"
    return f"SELECT TABLE_NAME AS ad FROM {info} WHERE LOWER(TABLE_NAME) LIKE N'{like}'"


def crm_account_count_sql(schema: str) -> str:
    p = prefix(schema)
    return f"SELECT COUNT(*) AS n FROM {p}AccountBase WHERE StateCode = 0"


def opt_guid(v: Any) -> Optional[str]:
    return guid(v)
