"""H2 Okuyucu veri tabanı: CRM okumaları (yalnız okuma) ve etkinlik dosyası ayrıştırıcı.

**Okunan CRM kayıtları (`Timas_MSCRM`, prod .28):**
- Kişi `ContactBase` (etkin, `StateCode = 0`): e-posta (1 ve 2), cep telefonu, ad/soyad (yalnız bellekte özet için;
  saklanmaz), doğum tarihi/yılı (üç alan), il (`new_il`, yoksa ev adresi ili → `new_illerBase`), cinsiyet, form tipi
  (`new_geliskanali`), kayıt tipi (`new_kayittipi`), ilgili departman, serbest ilgi alanı metni, bağlı firma
  (`ParentCustomerId`), izin bayrakları ve izin güncelleme tarihleri, KVKK/İYS onay bayrakları, oluşturma/değişme.
- Müşteri adayı `LeadBase` (durumlar ayarla, varsayılan açık `StateCode = 0`): e-posta, cep, ad, doğum tarihi, il
  (`new_kisiil`), katılım kaynağı ve alt kaynak, UTM kaynak/kampanya, ilgi alanı (`new_ilgialani` →
  `new_uzmanlikalaniBase.new_name`), KVKK bayrağı, izin bayrakları, bağlı kişi (`ParentContactId`).
- Firma olarak açılmış okur `AccountBase` (`new_FirmaKanal` = ayar, varsayılan 100000009 «Tüketici-Okur»).
- İYS günlüğü `obs_iyslogBase` (hatalı kayıt hariç): müşteri, müşteri türü, entegrasyon alanı, kanal, izin durumu,
  izin tarihi. İstek/cevap metni (kişisel veri içerebilir) **seçilmez**.
- İYS entegrasyon alanları `obs_iysintegrationfieldBase` (6 satır) → kanal eşlemesi.
- Etkinlik katılımı `new_new_etkinlik_contactBase` × `new_etkinlikBase` (kişi başına sayı ve son tarih).
- Esere katkı veren kişiler `new_eserkatilimBase` (yazar, çevirmen, çizer…; okur sayılmaz, ayarla).
- Kampanya geçmişi `CampaignBase` (28 satır; ad, gönderim, okunma, tıklama, kara liste).
- Seçim listesi etiketleri `StringMapBase` (form tipi, kayıt tipi, cinsiyet, İYS kanalı; Türkçe).

Portal kişisel veriyi kopyalamaz: toplu okumada ad/e-posta/telefon yalnız bellekte normalize edilip tuzlu özete
çevrilir. Ad/e-posta/telefon ekranda yalnız açıkça verilen yetkiyle, kayıt başına **anlık** okunur (`personal_sql`).

CRM'e hiçbir yoldan yazılmaz. Seçilen kolonlar sabit listedir; parola/anahtar alanı yoktur.
"""
from __future__ import annotations

import csv
import io
import logging
import re
import zipfile
from datetime import date, datetime
from typing import Any, Iterable, Optional
from xml.etree import ElementTree

from semantic_bridge import budget_sources as bsrc

log = logging.getLogger("semantic.readers.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")
#: `IN (...)` listesi parça büyüklüğü (sorgu metni boyu için; parçalar birleştirilir, kesilmez).
CHUNK = 800

#: Kaynak başına okunan izin bayrakları. Hangi değerin ne anlama geldiği `readers.settings()["flagRules"]`'tadır.
CONTACT_FLAGS = ("DoNotEMail", "DoNotBulkEMail", "DoNotPhone", "obs_donotsms", "obs_SmsezinVerme",
                 "obs_AramayazinVerme", "new_kvkkonayi", "new_iysonayi")
LEAD_FLAGS = ("DoNotEMail", "DoNotBulkEMail", "DoNotPhone", "obs_donotkvkk")
ACCOUNT_FLAGS = ("DoNotEMail", "DoNotBulkEMail", "DoNotPhone", "obs_donotsms")
FLAGS = {"crm_contact": CONTACT_FLAGS, "crm_lead": LEAD_FLAGS, "crm_account": ACCOUNT_FLAGS}

#: İYS günlüğündeki müşteri türü (Dynamics nesne kodu) → portal kaynağı.
CUSTOMER_TYPES = {2: "crm_contact", 4: "crm_lead", 1: "crm_account"}


def prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def guid(v: str) -> str:
    s = str(v or "").strip().strip("{}")
    if not _GUID.match(s):
        raise SourceError("Kayıt kimliği geçersiz.")
    return s.upper()


def _chunks(items: list[str], n: int = CHUNK) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _ints(values: Iterable[int]) -> str:
    return ", ".join(str(int(v)) for v in values)


def _flags(alias: str, names: Iterable[str]) -> str:
    return ", ".join(f"CAST({alias}.{n} AS int) AS {n}" for n in names)


# ------------------------------------------------------------------ toplu okuma SQL


def contacts_sql(schema: str) -> str:
    p = prefix(schema)
    return (
        "SELECT c.ContactId AS id, c.EMailAddress1 AS eposta, c.EMailAddress2 AS eposta2, c.MobilePhone AS cep,"
        " c.FirstName AS ad, c.LastName AS soyad, c.BirthDate AS dogum, c.new_DogumTarihi AS dogum2,"
        " c.obs_DogumYili AS dogum_yili, i.new_name AS il, CAST(c.GenderCode AS int) AS cinsiyet,"
        " CAST(c.new_geliskanali AS int) AS form_tipi, CAST(c.new_kayittipi AS int) AS kayit_tipi,"
        " CAST(c.new_ilgilidepartman AS int) AS departman, c.new_SMKitap_ilgiAlani AS ilgi_metni,"
        " c.ParentCustomerId AS kurum_id, " + _flags("c", CONTACT_FLAGS) + ","
        " c.obs_emailpermissionupdatedate AS email_izin_tarihi, c.obs_smspermissionupdatedate AS sms_izin_tarihi,"
        " c.obs_callpermissionupdatedate AS arama_izin_tarihi, c.CreatedOn AS olusturma, c.ModifiedOn AS degisme"
        f" FROM {p}ContactBase c"
        f" LEFT JOIN {p}new_illerBase i ON i.new_illerId = COALESCE(c.new_il, c.new_evadresil)"
        " WHERE c.StateCode = 0"
    )


def leads_sql(schema: str, states: tuple[int, ...] = (0,)) -> str:
    p = prefix(schema)
    return (
        "SELECT l.LeadId AS id, CAST(l.StateCode AS int) AS durum, l.EMailAddress1 AS eposta, l.EMailAddress2 AS eposta2,"
        " l.MobilePhone AS cep, l.FirstName AS ad, l.LastName AS soyad, l.obs_birthdate AS dogum, i.new_name AS il,"
        " l.obs_mainsourcename AS katilim_kaynagi, l.obs_subsourcename AS alt_kaynak, l.obs_utm_source AS utm_kaynak,"
        " l.obs_utm_campaign AS utm_kampanya, u.new_name AS ilgi, l.ParentContactId AS kisi_id, "
        + _flags("l", LEAD_FLAGS) + ", l.CreatedOn AS olusturma, l.ModifiedOn AS degisme"
        f" FROM {p}LeadBase l"
        f" LEFT JOIN {p}new_illerBase i ON i.new_illerId = l.new_kisiil"
        f" LEFT JOIN {p}new_uzmanlikalaniBase u ON u.new_uzmanlikalaniId = l.new_ilgialani"
        f" WHERE l.StateCode IN ({_ints(states or (0,))})"
    )


def accounts_sql(schema: str, channel: int) -> str:
    p = prefix(schema)
    return (
        "SELECT a.AccountId AS id, a.EMailAddress1 AS eposta, a.Telephone1 AS cep, a.Name AS ad, i.new_name AS il, "
        + _flags("a", ACCOUNT_FLAGS) + ", a.CreatedOn AS olusturma, a.ModifiedOn AS degisme"
        f" FROM {p}AccountBase a LEFT JOIN {p}new_illerBase i ON i.new_illerId = a.new_cariyeaitil"
        f" WHERE a.StateCode = 0 AND a.new_FirmaKanal = {int(channel)}"
    )


def contact_interests_sql(schema: str) -> str:
    p = prefix(schema)
    return (f"SELECT x.contactid AS id, u.new_name AS ilgi FROM {p}new_contact_new_uzmanlikalaniBase x"
            f" JOIN {p}new_uzmanlikalaniBase u ON u.new_uzmanlikalaniId = x.new_uzmanlikalaniid")


def contributors_sql(schema: str) -> str:
    """Esere katkı veren kişiler (yazar, çevirmen, çizer…): okur sayımının dışında tutulur (ayar)."""
    p = prefix(schema)
    return f"SELECT DISTINCT e.new_Katilimsaglayan AS id FROM {p}new_eserkatilimBase e WHERE e.statecode = 0"


def events_sql(schema: str) -> str:
    p = prefix(schema)
    return (
        "SELECT x.contactid AS id, COUNT(*) AS sayi,"
        " MAX(COALESCE(e.new_BalangTarihi, e.new_GercZiyTarihi, e.CreatedOn)) AS son"
        f" FROM {p}new_new_etkinlik_contactBase x"
        f" LEFT JOIN {p}new_etkinlikBase e ON e.new_etkinlikId = x.new_etkinlikid"
        " GROUP BY x.contactid"
    )


def iys_sql(schema: str, customer_ids: Optional[list[str]] = None, with_type: bool = True) -> str:
    """İYS günlüğü, hatasız kayıtlar. İstek/cevap gövdesi seçilmez. `with_type=False`: müşteri türü kolonu tabloda
    yoksa (ölçülecek) tür, kimliğin hangi kaynakta olduğundan bulunur."""
    p = prefix(schema)
    typ = "CAST(g.obs_customeridIdType AS int)" if with_type else "CAST(NULL AS int)"
    sql = (f"SELECT g.obs_iyslogId AS id, g.obs_customerid AS musteri, {typ} AS musteri_turu,"
           " g.obs_iysintegrationfieldid AS alan, CAST(g.obs_channel AS int) AS kanal,"
           " CAST(g.obs_permissionstatus AS int) AS durum, g.obs_permissiondate AS tarih, g.CreatedOn AS olusturma"
           f" FROM {p}obs_iyslogBase g WHERE ISNULL(g.obs_iserror, 0) = 0")
    if customer_ids is not None:
        sql += f" AND g.obs_customerid IN ({', '.join(chr(39) + guid(i) + chr(39) for i in customer_ids)})"
    return sql


def iys_fields_sql(schema: str) -> str:
    p = prefix(schema)
    return ("SELECT f.obs_iysintegrationfieldId AS id, f.obs_name AS ad, f.obs_entityname AS varlik,"
            " f.obs_iysfieldname AS iys_alan, f.obs_iysrecipient AS alici, f.obs_sendfieldname AS gonderim_alani"
            f" FROM {p}obs_iysintegrationfieldBase f")


def campaigns_sql(schema: str) -> str:
    p = prefix(schema)
    return ("SELECT c.CampaignId AS id, c.Name AS ad, c.obs_totalcount AS gonderim, c.obs_readcount AS okunma,"
            " c.obs_clickcount AS tiklama, c.obs_blacklistcount AS kara_liste, c.ActualStart AS baslangic,"
            " c.CreatedOn AS olusturma FROM {p}CampaignBase c".replace("{p}", p))


def labels_sql(schema: str) -> str:
    """Seçim listesi etiketleri (Türkçe). Nesne kodu adla bulunur."""
    p = prefix(schema)
    return (
        "SELECT e.Name AS varlik, s.AttributeName AS alan, s.AttributeValue AS kod, s.Value AS etiket"
        f" FROM {p}StringMapBase s JOIN {p}EntityView e ON e.ObjectTypeCode = s.ObjectTypeCode"
        " WHERE s.LangId = 1055 AND ("
        "(e.Name = 'contact' AND s.AttributeName IN ('new_geliskanali', 'new_kayittipi', 'gendercode', 'new_ilgilidepartman'))"
        " OR (e.Name = 'obs_iyslog' AND s.AttributeName = 'obs_channel'))"
    )


# ------------------------------------------------------------------ kayıt başına anlık okuma (kişisel veri)


def personal_sql(schema: str, source: str, ids: list[str]) -> str:
    """Açıkça verilen yetkiyle ekranda ya da dışa aktarımda gösterilecek ad/e-posta/telefon + güncel izin bayrakları.
    Yalnız verilen kayıtlar okunur."""
    p = prefix(schema)
    lst = ", ".join(f"'{guid(i)}'" for i in ids)
    if source == "crm_contact":
        return ("SELECT c.ContactId AS id, c.FullName AS ad, c.EMailAddress1 AS eposta, c.EMailAddress2 AS eposta2,"
                " c.MobilePhone AS cep, " + _flags("c", CONTACT_FLAGS) + ", CAST(c.StateCode AS int) AS durum"
                f" FROM {p}ContactBase c WHERE c.ContactId IN ({lst})")
    if source == "crm_lead":
        return ("SELECT l.LeadId AS id, l.FullName AS ad, l.EMailAddress1 AS eposta, l.EMailAddress2 AS eposta2,"
                " l.MobilePhone AS cep, " + _flags("l", LEAD_FLAGS) + ", CAST(l.StateCode AS int) AS durum"
                f" FROM {p}LeadBase l WHERE l.LeadId IN ({lst})")
    if source == "crm_account":
        return ("SELECT a.AccountId AS id, a.Name AS ad, a.EMailAddress1 AS eposta, NULL AS eposta2, a.Telephone1 AS cep, "
                + _flags("a", ACCOUNT_FLAGS) + ", CAST(a.StateCode AS int) AS durum"
                f" FROM {p}AccountBase a WHERE a.AccountId IN ({lst})")
    raise SourceError(f"«{source}» kaynağından kişi bilgisi okunamaz.")


def name_search_sql(schema: str, text: str) -> str:
    """Ada göre arama (yalnız kişisel veri yetkisiyle çağrılır). Yalnız kimlik döner."""
    p = prefix(schema)
    t = re.sub(r"[%_\[\]]", "", text or "").strip()[:80].replace("'", "''")
    if len(t) < 3:
        raise SourceError("Ad araması için en az 3 harf yazın.")
    return (f"SELECT 'crm_contact' AS kaynak, c.ContactId AS id FROM {p}ContactBase c"
            f" WHERE c.StateCode = 0 AND c.FullName LIKE N'%{t}%'"
            f" UNION ALL SELECT 'crm_lead', l.LeadId FROM {p}LeadBase l WHERE l.FullName LIKE N'%{t}%'")


# ------------------------------------------------------------------ okuma


def _s(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def _id(v: Any) -> Optional[str]:
    s = _s(v)
    return s.strip("{}").upper() if s else None


def read_all(run: Runner, schema: str, cfg: dict[str, Any]) -> dict[str, Any]:
    """Bütün kaynaklar tek turda. Bir kaynak okunamazsa hata `errors`'a yazılır, diğerleri sürer; kişi okunamazsa tur
    geçersizdir (çağıran eski durumu korur)."""
    out: dict[str, Any] = {"contacts": [], "leads": [], "accounts": [], "iys": [], "iysFields": [], "events": {},
                           "interests": {}, "contributors": set(), "campaigns": [], "labels": {}, "errors": {},
                           "readAt": datetime.now().isoformat(timespec="seconds")}

    def step(key: str, fn):
        try:
            return fn()
        except SourceError as e:
            out["errors"][key] = str(e)
            log.warning("okur kaynağı okunamadı (%s): %s", key, e)
            return None

    rows = step("crm_contact", lambda: run(contacts_sql(schema)))
    if rows is None:
        raise SourceError(out["errors"]["crm_contact"])
    out["contacts"] = rows
    out["leads"] = step("crm_lead", lambda: run(leads_sql(schema, tuple(cfg["leadStates"])))) or []
    if cfg.get("accountChannel"):
        out["accounts"] = step("crm_account", lambda: run(accounts_sql(schema, cfg["accountChannel"]))) or []
    def read_iys() -> list[dict[str, Any]]:
        try:
            return run(iys_sql(schema))
        except SourceError as e:
            log.warning("İYS günlüğü müşteri türüyle okunamadı, türsüz deneniyor: %s", e)
            return run(iys_sql(schema, with_type=False))
    out["iys"] = step("iys", read_iys) or []
    out["iysFields"] = step("iys_alan", lambda: run(iys_fields_sql(schema))) or []
    for r in step("etkinlik", lambda: run(events_sql(schema))) or []:
        if r.get("id"):
            out["events"][_id(r["id"])] = {"sayi": int(r.get("sayi") or 0), "son": r.get("son")}
    for r in step("ilgi", lambda: run(contact_interests_sql(schema))) or []:
        if r.get("id") and _s(r.get("ilgi")):
            out["interests"].setdefault(_id(r["id"]), []).append(_s(r["ilgi"]))
    out["contributors"] = {_id(r["id"]) for r in (step("katki", lambda: run(contributors_sql(schema))) or []) if r.get("id")}
    out["campaigns"] = step("kampanya", lambda: run(campaigns_sql(schema))) or []
    labels: dict[str, dict[str, str]] = {}
    for r in step("etiket", lambda: run(labels_sql(schema))) or []:
        labels.setdefault(str(r["alan"]).lower(), {})[str(r["kod"])] = _s(r["etiket"]) or str(r["kod"])
    out["labels"] = labels
    return out


def read_personal(run: Runner, schema: str, keys: list[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(kaynak, kimlik) listesinin anlık kişi bilgisi. Parçalı okunur, sonuç kesilmez."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    by: dict[str, list[str]] = {}
    for src, sid in keys:
        if src in FLAGS:
            by.setdefault(src, []).append(sid)
    for src, ids in by.items():
        for part in _chunks(sorted(set(ids))):
            for r in run(personal_sql(schema, src, part)):
                out[(src, _id(r["id"]))] = r
    return out


def read_iys_for(run: Runner, schema: str, ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for part in _chunks(sorted(set(ids))):
        rows.extend(run(iys_sql(schema, part)))
    return rows


# ------------------------------------------------------------------ etkinlik dosyası (CSV / XLSX)


class FileError(ValueError):
    """Dosya okunamadı; kişiye olduğu gibi gösterilir."""


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise FileError("Dosyanın karakter kodlaması okunamadı.")


def _parse_csv(data: bytes) -> list[list[str]]:
    text = _decode(data)
    sample = text[:4096]
    delim = max((";", ",", "\t", "|"), key=lambda d: sample.count(d))
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text), delimiter=delim)]


_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group(0):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _parse_xlsx(data: bytes) -> list[list[str]]:
    """İlk sayfa. Kütüphanesiz (zip + XML): paylaşılan metin, satır içi metin ve sayı hücreleri."""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise FileError("Excel dosyası açılamadı.") from None
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.iter(f"{_NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{_NS}t")))
    sheets = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    if not sheets:
        raise FileError("Excel dosyasında sayfa yok.")
    root = ElementTree.fromstring(z.read(sheets[0]))
    rows: list[list[str]] = []
    for row in root.iter(f"{_NS}row"):
        cells: dict[int, str] = {}
        for c in row.iter(f"{_NS}c"):
            ref, typ = c.get("r") or "", c.get("t")
            v = c.find(f"{_NS}v")
            if typ == "s" and v is not None and v.text is not None:
                val = shared[int(v.text)] if int(v.text) < len(shared) else ""
            elif typ == "inlineStr":
                val = "".join(t.text or "" for t in c.iter(f"{_NS}t"))
            else:
                val = v.text if v is not None and v.text is not None else ""
                if re.fullmatch(r"-?\d+\.0", val):
                    val = val[:-2]
            idx = _col_index(ref) if ref else len(cells)
            cells[idx] = val.strip()
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def parse_file(file_name: str, data: bytes) -> tuple[list[str], list[list[str]]]:
    """Başlık satırı + veri satırları. Boş satırlar atılır; satır sayısına sınır yoktur."""
    if not data:
        raise FileError("Dosya boş.")
    name = (file_name or "").lower()
    if name.endswith(".xlsx") or data[:2] == b"PK":
        rows = _parse_xlsx(data)
    elif name.endswith((".csv", ".txt", ".tsv")) or not name:
        rows = _parse_csv(data)
    else:
        raise FileError("Yalnız CSV ya da Excel (.xlsx) yüklenebilir.")
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if len(rows) < 2:
        raise FileError("Dosyada başlık satırı ve en az bir kişi satırı olmalı.")
    header = [(h or "").strip() or f"Kolon {i + 1}" for i, h in enumerate(rows[0])]
    width = len(header)
    body = [(r + [""] * width)[:width] for r in rows[1:]]
    return header, body


def year_of(v: Any) -> Optional[int]:
    """Doğum yılı: tarih nesnesi, «1987», «12.03.1987», «1987-03-12»."""
    if v is None:
        return None
    if isinstance(v, (datetime, date)):
        y = v.year
    else:
        m = re.search(r"(19\d{2}|20\d{2})", str(v))
        if not m:
            return None
        y = int(m.group(1))
    return y if 1900 <= y <= date.today().year else None
