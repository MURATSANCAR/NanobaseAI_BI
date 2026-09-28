"""M51 Müşteri hizmetleri: CRM, Logo ve destek masası okumaları (yalnız okuma).

Talep kaydı TİMAŞ'ın destek masasıdır (NanobaseAI Destek, `apps/destek`). Bu modül o masaya **yazmaz** ve ikinci bir
talep sistemi tutmaz; masayı yalnız REST ile okur (`DestekClient`, yalnız GET). CRM'e ve Logo'ya yazılmaz.

Kaynaklar ve tanımlar:

- **Müşteri eşleşmesi** (CRM .28, `Timas_MSCRM`): e-posta → `ContactBase.EMailAddress1/2/3`, B2B web kullanıcısı
  `new_webuserBase.obs_email`, cari `AccountBase.EMailAddress1`; telefon → kişi/cari telefon kolonlarının son 10 hanesi
  (yalnız WHERE'de; e-posta ve telefon **hiç seçilmez**, temsilci zaten biliyor); cari kodu → `AccountBase.new_CariKodu`.
  Birden çok aday çıkarsa temsilci seçer (model karar vermez).
- **Sipariş** `new_siparisBase` (Kural C13): numara `new_name` (B2C/dış sipariş numaraları da aranır), durum `statuscode`
  (etiket CRM'in kendi `StringMap`'inden, okunamazsa C13 listesi), **bekleyen** = `new_bekleyenadet > 0` ve durum
  Tamamlandı / Sevk Edildi / İptal / Birleştirildi / Etkin değil dışı; risk onayı bekleyen = 100000004, 100000016.
- **Sevkiyat** `new_sevkiyatBase` (`new_siparisid` ile), fatura numarası `new_faturanumarasi` (Logo `INVOICE.FICHENO`).
- **Kargo takibi** `new_kargotakipbilgisiBase` (`new_siparisid` ile; takip no `new_kargotakipnumarasi`) ve siparişin kendi
  `new_kargotakipno` / `new_kargotakipurl`; firma adı `new_kargofirmasiBase` (**yalnız** `new_kargofirmasiId`, `new_name`,
  `new_kargokodu`). Kargo firmasının teslim kaydı `new_kargobilgisiBase` (Kural C19: metin kolonlar, virgüllü ondalık)
  takip numarasıyla (`new_KargoTakipNo`) ya da müşteri irsaliye numarasıyla (`new_musteriirsno`) eşlenir — bağın hangisi
  olduğu **ölçülecek** (`SUPPORT_CARGO_MATCH`). Alıcı adı, gönderici adı ve adres kolonları seçilmez.
- **Fatura ve iade** (Logo, kayıt sistemi): `LG_<firma>_01_INVOICE`, `CANCELLED = 0`, TRCODE 7/8/9 satış, 2/3 iade;
  cari kodu (`CLCARD.CODE`) ile. Logo kopyası donmuş olabilir: her yanıtta **veri sonu** (`MAX(DATE_)` faturalı satış)
  yazılır, «fatura kesilmedi» cümlesi bu tarihten sonrası için kurulmaz.

**Kimlik bilgisi yasağı:** CRM `new_kargofirmasiBase` kullanıcı adı / şifre / token / client secret / UPS hesap no ve
`new_webuserBase` şifre / e-posta doğrulama ve parola sıfırlama token kolonları hiçbir sorguda geçmez. Her sorgu
`guard()`'dan geçer; yasak kolon adı geçen SQL çalışmadan hata verir (test: bütün SQL üreticileri taranır).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional
from urllib.parse import quote

from semantic_bridge.field_sales_sources import (  # aynı yardımcılar (M30); SQL'e yalnız doğrulanmış ad/değer girer
    SourceError, _guid_literal, day, firm, guid, lower_keys, num, opt_num, prefix, text,
)

log = logging.getLogger("semantic.support.sources")

Run = Callable[[str], list[dict[str, Any]]]

#: Hiçbir sorguda geçmeyecek kolonlar (kimlik bilgisi, parola, token). Küçük harfle karşılaştırılır.
FORBIDDEN_COLUMNS = (
    "new_kullaniciadi", "new_sifre", "new_token", "new_tokenexpirationdate", "new_clientid", "new_clientsecret",
    "new_ups_shipperaccountnumber", "obs_emailconfirmationtoken", "obs_emailforgotpasswordtoken",
)

#: CRM sipariş durumu (Kural C13); CRM'in StringMap'i okunamazsa bu etiketler.
ORDER_STATUS = {
    1: "Taslak", 2: "Etkin değil", 100000000: "Sevk edildi", 100000001: "İptal", 100000002: "Sipariş",
    100000003: "Birleştirildi", 100000004: "Risk limit onayı bekliyor", 100000005: "Pazarlama bütçesi onayı bekliyor",
    100000011: "Depoda bekliyor", 100000012: "Pusula alındı, toplanıyor", 100000013: "Kutulanıyor",
    100000014: "Kutulandı", 100000015: "Tamamlandı", 100000016: "Risk bilgisi bekleniyor",
}
#: «Bekleyen» sayılmayan durumlar (C13): Tamamlandı, Sevk edildi, İptal, Birleştirildi, Etkin değil.
NOT_PENDING = (100000015, 100000000, 100000001, 100000003, 2)
RISK_STATUS = (100000004, 100000016)
ORDER_TYPE = {1: "B2B", 2: "Dağılım", 3: "Standart", 4: "Fuar", 5: "Etkinlik", 6: "Telif", 7: "Market", 8: "B2C",
              9: "Pazaryeri", 10: "Okul örneği", 11: "Öğretmen örneği", 12: "Tanıtım gönderimi", 13: "Okul satışı",
              14: "Amazon konsinye", 15: "Bağış", 16: "İmza siparişi", 17: "Kırmızı / Mor"}
RISK_REASON = {1: "Açık hesap limiti", 2: "Çek-senet limiti", 3: "Toplam limit", 4: "Sorunlu müşteri"}
SHIPMENT_KIND = {1: "Üretimden giriş", 2: "Faturalı kabul", 4: "İade", 5: "Raf transferi", 6: "Depolar arası sevk",
                 7: "İrsaliye", 8: "Sayım eksiği"}
CHANNEL = {100000008: "Bayi", 100000004: "Dağıtıcı", 100000001: "Kitapçı", 100000003: "Perakende",
           100000005: "E-ticaret", 100000002: "Market", 100000006: "Fuar", 100000009: "Tüketici-okur",
           100000000: "Sincap Kitap", 100000007: "Diğer"}
SALES_TR, RETURN_TR = (7, 8, 9), (2, 3)


def guard(sql: str) -> str:
    """Yasak kolon geçen SQL'i çalıştırmadan durdurur (seçim, koşul ya da sıralama fark etmez)."""
    low = sql.lower()
    for col in FORBIDDEN_COLUMNS:
        if re.search(rf"(?<![a-z0-9_]){re.escape(col)}(?![a-z0-9_])", low):
            raise SourceError("Bu sorgu kimlik bilgisi kolonuna dokunuyor; çalıştırılmadı.")
    return sql


# ------------------------------------------------------------------ değer güvenliği

_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]{1,64}@[A-Za-z0-9.\-]{1,190}\.[A-Za-z]{2,24}$")
_ORDER = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü.\-_/#]{2,60}$")
_CODE = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü .\-_/]{1,40}$")


def email_literal(v: str) -> str:
    s = (v or "").strip().lower()
    if not _EMAIL.match(s):
        raise SourceError("E-posta adresi geçersiz.")
    return s.replace("'", "''")


def phone_digits(v: str) -> str:
    """Son 10 hane (Türkiye cep/sabit hat, başındaki 0/90 atılır). 10 haneden kısa numara aranmaz."""
    d = re.sub(r"\D", "", v or "")
    if len(d) < 10:
        raise SourceError("Telefon numarası en az 10 hane olmalı.")
    return d[-10:]


def order_literal(v: str) -> str:
    s = (v or "").strip()
    if not _ORDER.match(s):
        raise SourceError("Sipariş numarası geçersiz.")
    return s.replace("'", "''")


def code_literal(v: str) -> str:
    s = (v or "").strip()
    if not _CODE.match(s):
        raise SourceError("Cari kodu geçersiz.")
    return s.replace("'", "''")


def like_literal(v: str) -> str:
    s = re.sub(r"\s+", " ", (v or "").strip())[:60]
    if len(s) < 2:
        raise SourceError("Arama en az 2 karakter olmalı.")
    return s.replace("'", "''").replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")


def _guids(values: Iterable[str]) -> str:
    out = sorted({_guid_literal(str(v)) for v in values if v})
    if not out:
        raise SourceError("Kimlik listesi boş.")
    return ", ".join(f"'{g}'" for g in out)


def _texts(values: Iterable[str], unicode: bool = True) -> str:
    out = sorted({str(v).strip()[:60].replace("'", "''") for v in values if v and str(v).strip()})
    if not out:
        raise SourceError("Liste boş.")
    n = "N" if unicode else ""
    return ", ".join(f"{n}'{v}'" for v in out)


def _phone_expr(col: str) -> str:
    """Kolonun yalnız rakamlarının son 10'u (boşluk, tire, parantez, artı, nokta atılır)."""
    e = col
    for ch in (" ", "-", "(", ")", "+", "."):
        e = f"REPLACE({e}, '{ch}', '')"
    return f"RIGHT({e}, 10)"


# ------------------------------------------------------------------ CRM: müşteri eşleşmesi


def crm_contacts_sql(schema: str, *, email: Optional[str] = None, phone: Optional[str] = None) -> str:
    """Etkin kişiler: kimlik, ad, bağlı cari. E-posta/telefon yalnız koşulda."""
    p = prefix(schema)
    conds = []
    if email:
        e = email_literal(email)
        conds.append(" OR ".join(f"LOWER(c.{col}) = N'{e}'" for col in ("EMailAddress1", "EMailAddress2", "EMailAddress3")))
    if phone:
        d = phone_digits(phone)
        conds.append(" OR ".join(f"{_phone_expr('c.' + col)} = '{d}'" for col in ("MobilePhone", "Telephone1", "Telephone2")))
    if not conds:
        raise SourceError("Kişi araması için e-posta ya da telefon gerekli.")
    return guard("SELECT c.ContactId AS contact_id, c.FullName AS ad, c.ParentCustomerId AS account_id,"
                 " CAST(c.ParentCustomerIdType AS int) AS account_type, c.new_carikodu AS cari_kodu"
                 f" FROM {p}ContactBase c WHERE c.StateCode = 0 AND (({') OR ('.join(conds)}))")


def crm_webusers_sql(schema: str, email: str) -> str:
    """B2B web kullanıcısı (bayi personeli): ad, soyad, bağlı firma. Şifre ve token kolonları geçmez."""
    p = prefix(schema)
    return guard("SELECT w.new_webuserId AS webuser_id, w.new_name AS ad, w.new_soyad AS soyad, w.new_firmaid AS account_id"
                 f" FROM {p}new_webuserBase w WHERE w.statecode = 0 AND LOWER(w.obs_email) = N'{email_literal(email)}'")


_ACCOUNT_COLS = ("a.AccountId AS account_id, a.Name AS unvan, a.new_CariKodu AS cari_kodu, a.new_logicalref AS logicalref,"
                 " CAST(a.new_FirmaKanal AS int) AS kanal")


def crm_accounts_sql(schema: str, *, ids: Iterable[str] = (), code: Optional[str] = None,
                     email: Optional[str] = None, phone: Optional[str] = None) -> str:
    """Etkin cariler kimlik, cari kodu, e-posta ya da telefonla. Adres, telefon, vergi no seçilmez."""
    p = prefix(schema)
    conds = []
    ids = [i for i in ids if i]
    if ids:
        conds.append(f"a.AccountId IN ({_guids(ids)})")
    if code:
        conds.append(f"a.new_CariKodu = N'{code_literal(code)}'")
    if email:
        e = email_literal(email)
        conds.append(" OR ".join(f"LOWER(a.{col}) = N'{e}'" for col in ("EMailAddress1", "EMailAddress2", "EMailAddress3")))
    if phone:
        d = phone_digits(phone)
        conds.append(" OR ".join(f"{_phone_expr('a.' + col)} = '{d}'" for col in ("Telephone1", "Telephone2")))
    if not conds:
        raise SourceError("Cari araması için bir ölçüt gerekli.")
    return guard(f"SELECT {_ACCOUNT_COLS} FROM {p}AccountBase a WHERE a.StateCode = 0 AND (({') OR ('.join(conds)}))")


def crm_account_search_sql(schema: str, q: str, offset: int, size: int, channels: Iterable[int] = ()) -> str:
    """Bayi seçimi: ad ya da cari kodunda geçen (sayfalı; `size + 1` satır okunur, fazlası «devamı var» demektir)."""
    p = prefix(schema)
    s = like_literal(q)
    ch = [int(c) for c in channels if str(c).strip().lstrip("-").isdigit()]
    only = f" AND CAST(a.new_FirmaKanal AS int) IN ({', '.join(str(c) for c in ch)})" if ch else ""
    return guard(f"SELECT {_ACCOUNT_COLS} FROM {p}AccountBase a WHERE a.StateCode = 0{only}"
                 f" AND (a.Name LIKE N'%{s}%' OR a.new_CariKodu LIKE N'{s}%')"
                 f" ORDER BY a.Name, a.AccountId OFFSET {max(0, int(offset))} ROWS FETCH NEXT {max(1, int(size)) + 1} ROWS ONLY")


# ------------------------------------------------------------------ CRM: sipariş, sevkiyat, kargo

_ORDER_COLS = ("s.new_siparisId AS order_id, s.new_name AS no, s.new_siparistarihi AS tarih, CAST(s.statuscode AS int) AS durum,"
               " CAST(s.new_siparistipi AS int) AS tip, s.new_siparisadeti AS adet, s.new_bekleyenadet AS bekleyen,"
               " s.new_sevktarihi AS sevk_tarihi, s.new_tamamlanditarihi AS tamamlandi, s.new_toplamsatistutari AS tutar,"
               " s.new_kdvlitoplamtutar AS kdvli_tutar, s.new_kargotakipno AS takip_no, s.new_kargotakipurl AS takip_url,"
               " s.new_kargofirmasiid AS kargo_firma_id, s.new_firmaid AS account_id, s.new_webuserid AS webuser_id,"
               " CAST(s.new_risketakilmasebebi AS int) AS risk_sebep, s.new_b2csiparisnumarasi AS b2c_no,"
               " s.new_yenib2csiparisnumarasi AS yeni_b2c_no, s.new_dissiparisno AS dis_no, s.ModifiedOn AS degisme")


def crm_orders_sql(schema: str, *, accounts: Iterable[str] = (), webusers: Iterable[str] = (),
                   order_no: Optional[str] = None, since: Optional[date] = None, open_only: bool = False) -> str:
    """Siparişler: cariye/web kullanıcısına ait (pencere `since`'ten beri; açık olanlar tarihten bağımsız hep gelir) ya da
    numarasıyla. Numara `new_name`, B2C ve dış sipariş numaralarında aranır."""
    p = prefix(schema)
    who = []
    accounts = [a for a in accounts if a]
    webusers = [w for w in webusers if w]
    if accounts:
        who.append(f"s.new_firmaid IN ({_guids(accounts)})")
    if webusers:
        who.append(f"s.new_webuserid IN ({_guids(webusers)})")
    conds = ["s.statecode = 0"]
    if order_no:
        o = order_literal(order_no)
        conds.append("(" + " OR ".join(f"s.{c} = N'{o}'" for c in
                                        ("new_name", "new_b2csiparisnumarasi", "new_yenib2csiparisnumarasi", "new_dissiparisno")) + ")")
    elif who:
        conds.append("(" + " OR ".join(who) + ")")
        pending = f"(s.new_bekleyenadet > 0 AND CAST(s.statuscode AS int) NOT IN ({', '.join(str(x) for x in NOT_PENDING)}))"
        if open_only:
            conds.append(pending)
        elif since is not None:
            conds.append(f"(s.new_siparistarihi >= '{since.isoformat()}' OR {pending})")
    else:
        raise SourceError("Sipariş araması için cari, web kullanıcısı ya da sipariş numarası gerekli.")
    return guard(f"SELECT {_ORDER_COLS} FROM {p}new_siparisBase s WHERE {' AND '.join(conds)}"
                 " ORDER BY s.new_siparistarihi DESC, s.new_name DESC")


def crm_shipments_sql(schema: str, order_ids: Iterable[str]) -> str:
    p = prefix(schema)
    return guard("SELECT v.new_sevkiyatId AS shipment_id, v.new_name AS no, v.new_siparisid AS order_id,"
                 " v.new_sevktarihi AS tarih, CAST(v.statuscode AS int) AS durum, CAST(v.new_sevkiyat_islemturu AS int) AS tur,"
                 " v.new_faturanumarasi AS fatura_no, v.new_kdvlitoplamtutar AS tutar, CAST(v.new_logoyaaktarildi AS int) AS logoda"
                 f" FROM {p}new_sevkiyatBase v WHERE v.statecode = 0 AND v.new_siparisid IN ({_guids(order_ids)})"
                 " ORDER BY v.new_sevktarihi DESC")


def crm_tracking_sql(schema: str, order_ids: Iterable[str]) -> str:
    p = prefix(schema)
    return guard("SELECT k.new_kargotakipbilgisiId AS id, k.new_name AS irsaliye_no, k.new_kargotakipnumarasi AS takip_no,"
                 " k.new_siparisid AS order_id, k.CreatedOn AS olusturma"
                 f" FROM {p}new_kargotakipbilgisiBase k WHERE k.statecode = 0 AND k.new_siparisid IN ({_guids(order_ids)})")


def crm_cargo_info_sql(schema: str, tracking_nos: Iterable[str], irs_nos: Iterable[str] = ()) -> str:
    """Kargo firmasının gönderi kaydı (C19). Alıcı/gönderici adı ve adres seçilmez; tutar/desi metin döner, çevrim Python'da."""
    p = prefix(schema)
    conds = []
    t = [x for x in tracking_nos if x and str(x).strip()]
    i = [x for x in irs_nos if x and str(x).strip()]
    if t:
        conds.append(f"b.new_KargoTakipNo IN ({_texts(t)})")
    if i:
        conds.append(f"b.new_musteriirsno IN ({_texts(i)})")
    if not conds:
        raise SourceError("Kargo kaydı için takip ya da irsaliye numarası gerekli.")
    return guard("SELECT b.new_kargobilgisiId AS id, b.new_KargoTakipNo AS takip_no, b.new_musteriirsno AS irsaliye_no,"
                 " b.new_kargofirmasi AS firma, b.new_sevkiyatcikissubesi AS cikis_sube, b.new_sevkiyatvarissubesi AS varis_sube,"
                 " b.new_alicisehir AS alici_sehir, b.new_kargoirstarihi AS irs_tarihi, b.new_TeslimTarihi AS teslim_tarihi,"
                 " b.new_teslimsaati AS teslim_saati, b.new_iadedurumu AS iade_durumu, b.new_sevkadeti AS sevk_adeti,"
                 " b.new_desi AS desi, b.new_Tutar AS tutar"
                 f" FROM {p}new_kargobilgisiBase b WHERE b.statecode = 0 AND ({' OR '.join(conds)})")


def crm_cargo_firms_sql(schema: str) -> str:
    """Kargo firması adları. **Yalnız** kimlik, ad ve kod; kullanıcı adı/şifre/token/secret kolonları asla."""
    p = prefix(schema)
    return guard(f"SELECT f.new_kargofirmasiId AS id, f.new_name AS ad, f.new_kargokodu AS kod FROM {p}new_kargofirmasiBase f")


def crm_order_status_sql(schema: str) -> str:
    p = prefix(schema)
    return guard("SELECT s.AttributeValue AS code, s.Value AS label"
                 f" FROM {p}StringMapBase s"
                 f" WHERE s.ObjectTypeCode = (SELECT TOP 1 e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_siparis')"
                 " AND s.AttributeName = 'statuscode' AND s.LangId = 1055")


def crm_knowledge_sql(schema: str) -> str:
    """CRM bilgi bankası makaleleri (SSS kaynağı): son sürüm, onaylı ya da yayımlanmış."""
    p = prefix(schema)
    return guard("SELECT k.knowledgearticleId AS id, k.Title AS baslik, k.Content AS icerik, k.Keywords AS anahtar"
                 f" FROM {p}KnowledgeArticleBase k WHERE k.IsLatestVersion = 1 AND k.StateCode IN (1, 3)")


def crm_email_templates_sql(schema: str) -> str:
    """CRM e-posta şablonlarının adları (gövde kolonu yok; SSS açığı listesinde «şablonu var» diye gösterilir)."""
    p = prefix(schema)
    return guard(f"SELECT e.new_emailsablonId AS id, e.new_name AS ad FROM {p}new_emailsablonBase e WHERE e.statecode = 0")


# ------------------------------------------------------------------ Logo: fatura, iade, veri sonu


def logo_invoices_sql(f: str, code: str, since: date) -> str:
    """Tek carinin `since`'ten beri satış (7/8/9) ve iade (2/3) faturaları: tarih, belge no, tür, net tutar."""
    f = firm(f)
    return guard(f"SELECT I.DATE_ AS tarih, I.FICHENO AS no, I.TRCODE AS tur, I.NETTOTAL AS tutar"
                 f" FROM dbo.LG_{f}_01_INVOICE I JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = I.CLIENTREF"
                 f" WHERE I.CANCELLED = 0 AND I.TRCODE IN (2,3,7,8,9) AND C.CODE = '{code_literal(code)}'"
                 f" AND I.DATE_ >= '{since.isoformat()}' ORDER BY I.DATE_ DESC, I.LOGICALREF DESC")


def logo_invoices_by_no_sql(f: str, numbers: Iterable[str]) -> str:
    """Sevkiyattaki fatura numaraları Logo'da: tarih, tür, net tutar, cari kodu (sipariş → sevkiyat → fatura yolu)."""
    f = firm(f)
    return guard(f"SELECT I.FICHENO AS no, I.DATE_ AS tarih, I.TRCODE AS tur, I.NETTOTAL AS tutar, C.CODE AS cari"
                 f" FROM dbo.LG_{f}_01_INVOICE I LEFT JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = I.CLIENTREF"
                 f" WHERE I.CANCELLED = 0 AND I.FICHENO IN ({_texts(numbers, unicode=False)})")


def logo_client_sql(f: str, code: str) -> str:
    f = firm(f)
    return guard(f"SELECT C.LOGICALREF AS ref, C.CODE AS code, C.DEFINITION_ AS unvan, C.CITY AS il, C.SPECODE2 AS kanal"
                 f" FROM dbo.LG_{f}_CLCARD C WHERE C.CODE = '{code_literal(code)}'")


def logo_data_end_sql(f: str) -> str:
    f = firm(f)
    return guard(f"SELECT MAX(DATE_) AS son FROM dbo.LG_{f}_01_STLINE "
                 f"WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9)")


# ------------------------------------------------------------------ satır biçimleri


def status_label(code: Any, labels: Optional[dict[int, str]] = None) -> str:
    c = int(num(code))
    return (labels or {}).get(c) or ORDER_STATUS.get(c) or f"Durum {c}"


def is_pending(o: dict[str, Any]) -> bool:
    return num(o.get("bekleyen")) > 0 and int(num(o.get("durum"))) not in NOT_PENDING


def text_number(v: Any) -> Optional[float]:
    """C19 metin sayısı: «1.234,50» / «12,5» / «12.5» → float."""
    s = text(v)
    if not s:
        return None
    s = s.replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def order_row(r: dict[str, Any], labels: Optional[dict[int, str]] = None, firms: Optional[dict[str, str]] = None) -> dict[str, Any]:
    code = int(num(r.get("durum")))
    return {
        "id": guid(r.get("order_id")), "no": text(r.get("no")), "tarih": day(r.get("tarih")),
        "durum": code, "durumAd": status_label(code, labels), "tip": ORDER_TYPE.get(int(num(r.get("tip")))),
        "adet": opt_num(r.get("adet")), "bekleyen": opt_num(r.get("bekleyen")), "acik": is_pending(r),
        "riskte": code in RISK_STATUS, "riskSebep": RISK_REASON.get(int(num(r.get("risk_sebep")))),
        "sevkTarihi": day(r.get("sevk_tarihi")), "tamamlandi": day(r.get("tamamlandi")),
        "tutar": opt_num(r.get("tutar")), "kdvliTutar": opt_num(r.get("kdvli_tutar")),
        "takipNo": text(r.get("takip_no")), "takipUrl": _safe_url(r.get("takip_url")),
        "kargoFirma": (firms or {}).get(guid(r.get("kargo_firma_id")) or ""),
        "accountId": guid(r.get("account_id")), "webuserId": guid(r.get("webuser_id")),
        "digerNo": [x for x in (text(r.get("b2c_no")), text(r.get("yeni_b2c_no")), text(r.get("dis_no"))) if x],
    }


def _safe_url(v: Any) -> Optional[str]:
    s = text(v)
    return s if s and re.match(r"^https?://", s, re.I) else None


def shipment_row(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": guid(r.get("shipment_id")), "no": text(r.get("no")), "orderId": guid(r.get("order_id")),
            "tarih": day(r.get("tarih")), "tamamlandi": int(num(r.get("durum"))) == 100000000,
            "tur": SHIPMENT_KIND.get(int(num(r.get("tur")))), "faturaNo": text(r.get("fatura_no")),
            "tutar": opt_num(r.get("tutar")), "logoda": bool(num(r.get("logoda")))}


def cargo_row(r: dict[str, Any]) -> dict[str, Any]:
    return {"takipNo": text(r.get("takip_no")), "irsaliyeNo": text(r.get("irsaliye_no")), "firma": text(r.get("firma")),
            "cikisSube": text(r.get("cikis_sube")), "varisSube": text(r.get("varis_sube")),
            "aliciSehir": text(r.get("alici_sehir")), "irsTarihi": text(r.get("irs_tarihi")),
            "teslimTarihi": text(r.get("teslim_tarihi")), "teslimSaati": text(r.get("teslim_saati")),
            "iadeDurumu": text(r.get("iade_durumu")), "sevkAdeti": text_number(r.get("sevk_adeti")),
            "desi": text_number(r.get("desi")), "tutar": text_number(r.get("tutar"))}


def invoice_row(r: dict[str, Any]) -> dict[str, Any]:
    tr = int(num(r.get("tur")))
    return {"no": text(r.get("no")), "tarih": day(r.get("tarih")), "tur": tr,
            "turAd": "İade" if tr in RETURN_TR else "Satış", "iade": tr in RETURN_TR, "tutar": opt_num(r.get("tutar")),
            "cari": text(r.get("cari"))}


# ------------------------------------------------------------------ destek masası (REST, yalnız okuma)


class DestekError(RuntimeError):
    pass


#: Masadan okunan talep alanları. Açıklama (gövde) yalnız sınıflama ve taslak için okunur, köprüde saklanmaz.
TICKET_FIELDS = ("name", "subject", "status", "status_category", "priority", "ticket_type", "agent_group", "raised_by",
                 "contact", "customer", "opening_date", "opening_time", "first_responded_on", "resolution_date",
                 "response_by", "resolution_by", "agreement_status", "feedback_rating", "via_customer_portal",
                 "modified", "_assign")


class DestekClient:
    """NanobaseAI Destek (Frappe Helpdesk) REST istemcisi. **Yalnız GET**: talep, makale okunur; masaya hiçbir şey yazılmaz.
    Kimlik: masada açılan salt okuma API kullanıcısının anahtarı (`DESTEK_API_KEY` / `DESTEK_API_SECRET`)."""

    PAGE = 500

    def __init__(self, base: str, key: str, secret: str, timeout: float = 20.0, verify: Any = True,
                 http: Optional[Callable[[str, dict[str, str]], Any]] = None):
        self.base = (base or "").rstrip("/")
        self.key, self.secret, self.timeout, self.verify = key or "", secret or "", timeout, verify
        self._http = http

    @property
    def configured(self) -> bool:
        return bool(self.base and self.key and self.secret)

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        if not self.configured:
            raise DestekError("Destek masası bağlantısı ayarlanmamış (Yönetim → Ayarlar → Müşteri hizmetleri).")
        if not path.startswith("/api/resource/") and not path.startswith("/api/method/frappe.client.get_count"):
            raise DestekError("Destek masasına yalnız okuma çağrısı yapılır.")
        q = "&".join(f"{k}={quote(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False), safe='')}"
                     for k, v in params.items() if v is not None)
        url = f"{self.base}{quote(path, safe='/._')}" + (f"?{q}" if q else "")
        headers = {"Authorization": f"token {self.key}:{self.secret}", "Accept": "application/json"}
        if self._http is not None:
            return self._http(url, headers)
        import httpx

        try:
            r = httpx.get(url, headers=headers, timeout=self.timeout, verify=self.verify)
        except httpx.HTTPError as e:
            raise DestekError("Destek masasına ulaşılamadı.") from e
        if r.status_code in (401, 403):
            raise DestekError("Destek masası okuma anahtarını kabul etmedi.")
        if r.status_code >= 400:
            raise DestekError(f"Destek masası {r.status_code} döndü.")
        return r.json()

    def _all(self, doctype: str, fields: Iterable[str], filters: list[Any], order: str) -> list[dict[str, Any]]:
        """Sayfa sayfa hepsi (sessiz tavan yok)."""
        out: list[dict[str, Any]] = []
        start = 0
        while True:
            page = (self._get(f"/api/resource/{doctype}", {
                "fields": list(fields), "filters": filters, "order_by": order,
                "limit_start": str(start), "limit_page_length": str(self.PAGE)}) or {}).get("data") or []
            out.extend(page)
            if len(page) < self.PAGE:
                return out
            start += self.PAGE

    def tickets(self, *, modified_since: Optional[str] = None, opened_from: Optional[str] = None,
                opened_to: Optional[str] = None, raised_by: Optional[str] = None,
                with_description: bool = False) -> list[dict[str, Any]]:
        filters: list[Any] = []
        if modified_since:
            filters.append(["modified", ">", modified_since])
        if opened_from:
            filters.append(["opening_date", ">=", opened_from])
        if opened_to:
            filters.append(["opening_date", "<=", opened_to])
        if raised_by:
            filters.append(["raised_by", "=", raised_by])
        fields = list(TICKET_FIELDS) + (["description"] if with_description else [])
        return self._all("HD Ticket", fields, filters, "modified asc" if modified_since else "opening_date desc")

    def open_tickets(self) -> list[dict[str, Any]]:
        """Açık (çözülmemiş) talepler, açılış tarihinden bağımsız: SLA ve kuyruk sayıları için."""
        return self._all("HD Ticket", TICKET_FIELDS, [["status_category", "!=", "Resolved"]], "opening_date desc")

    def ticket(self, name: str) -> dict[str, Any]:
        if not re.match(r"^[0-9A-Za-z\-_.]{1,40}$", str(name or "")):
            raise DestekError("Talep numarası geçersiz.")
        return (self._get(f"/api/resource/HD Ticket/{name}", {}) or {}).get("data") or {}

    def articles(self) -> list[dict[str, Any]]:
        return self._all("HD Article", ("name", "title", "content", "category", "modified"),
                         [["status", "=", "Published"]], "modified desc")


def clean_html(v: Any) -> str:
    """Talep gövdesi/makale HTML'i → düz metin (etiketler ve alıntılanmış eski yazışma atılır)."""
    s = str(v or "")
    s = re.split(r"(?i)<blockquote|-----\s*original message|(?:^|\n)\s*(?:on .{5,80} wrote:|.{5,80} tarihinde .{0,80} yazdı:)", s)[0]
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
         .replace("&#39;", "'").replace("&quot;", '"'))
    s = re.sub(r"[ \t]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()


def ticket_datetime(t: dict[str, Any], day_key: str = "opening_date", time_key: str = "opening_time") -> Optional[datetime]:
    d = t.get(day_key)
    if not d:
        return None
    tm = str(t.get(time_key) or "00:00:00").split(".")[0]
    try:
        return datetime.fromisoformat(f"{str(d)[:10]}T{tm if len(tm) >= 5 else '00:00:00'}")
    except ValueError:
        return None


def parse_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(v).replace(" ", "T").split(".")[0].replace("Z", ""))
    except ValueError:
        return None


def assignees(t: dict[str, Any]) -> list[str]:
    raw = t.get("_assign")
    if isinstance(raw, list):
        return [str(x) for x in raw]
    try:
        v = json.loads(raw or "[]")
        return [str(x) for x in v] if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def rating_5(v: Any) -> Optional[float]:
    """Frappe «Rating» alanı 0–1 kesir saklar (0,8 = 4 yıldız); eski kayıtta 1–5 olabilir. 0/boş = puan verilmemiş."""
    n = opt_num(v)
    if not n or n <= 0:
        return None
    return round(n * 5, 2) if n <= 1 else min(5.0, n)


def since_months(today: date, months: int) -> date:
    y, m = today.year, today.month - max(0, int(months))
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def years_between(start: date, end: date) -> list[int]:
    return list(range(start.year, end.year + 1))


def as_date(v: Any) -> Optional[date]:
    d = day(v)
    return date.fromisoformat(d) if d else None


def guid_or_none(v: Any) -> Optional[str]:
    try:
        return _guid_literal(str(v)).lower() if v else None
    except SourceError:
        return None


def is_after(a: Optional[str], b: Optional[str]) -> bool:
    return bool(a and b and a > b)


def days_between(a: Optional[str], b: Optional[str]) -> Optional[int]:
    if not a or not b:
        return None
    return (date.fromisoformat(b[:10]) - date.fromisoformat(a[:10])).days


def ago(today: date, days: int) -> date:
    return today - timedelta(days=max(0, int(days)))
