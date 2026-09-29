"""M54 Telif dönemi ve haklar: kaynak okuma (CRM .28 ve Logo, yalnız okuma).

Bu dosya yalnız SQL üretir ve satırları biçimler; hesap M6'nın motorundadır (`contracts_royalty`), portal kayıtları
`royalty.py`'dadır. CRM'e ve Logo'ya hiçbir şey yazılmaz.

Kapsam (analiz §13, kabul 1): `new_sozlesmeBase` etkin (`statecode = 0`), Telif Alış (`new_SozlesmeTipi = 5`), ödeme
şekli satıştan / satıştan kademeli (`new_TelifTipi` 2, 7), durum yürürlükte (`statuscode` 100000000 Aktif-Sözleşme,
100000007 Aktif-Yenileme). Ödeme şekli ve durum kodları Yönetim ayarından değişir (`ROYALTY_CRM_PAYMENT_TYPES`,
`ROYALTY_CRM_STATUSES`); «Aktif (Proje)» (100000006) varsayılan kapsamda değil — yayımlanmamış projenin satışı yoktur,
ölçülecek.

Sözleşme başlığı M6'nın sorgusuyla birebir aynı kolonlarla okunur (`contracts.crm_contract_sql`'in WHERE'i kapsamla
değiştirilir) ve M6'nın `crm_contract` eşlemesinden geçer: toplu koşunun gördüğü şartlar, sözleşme sayfasının gördüğüyle
aynıdır. Kitap ve taraf tek sorguda bütün kapsam için okunur (sözleşme başına sorgu yok, satır tavanı yok).

Satış M6'nın satış sorgusudur (`contracts_royalty.sales_sql`, yıllık `V_SatisRaporu_<yıl>`, faturalı satır, ay sınırı);
stok kodları 500'lük gruplarla okunur (tek sorgu çok uzamasın diye; veri kesilmez, bütün gruplar okunur).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import contracts as C
from semantic_bridge import crm_rights
from semantic_bridge import contracts_royalty as R
from semantic_bridge import contracts_terms as T

Runner = Callable[[str], list[dict[str, Any]]]

ZERO = "00000000-0000-0000-0000-000000000000"
ALIS, SATIS = 5, 1
DEFAULT_STATUSES = (100000000, 100000007)
DEFAULT_PAYMENT_CODES = (2, 7)
CODE_CHUNK = 500
_GUID = re.compile(r"^\{?[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\}?$")


class SourceError(RuntimeError):
    """Kaynağa ulaşılamadı ya da beklenmeyen biçim; ekrana düz cümle gider."""


def codes_of(text: str, default: Iterable[int]) -> tuple[int, ...]:
    """«100000000, 100000007» → (100000000, 100000007). Boş ya da bozuksa varsayılan."""
    out = tuple(int(x) for x in re.findall(r"\d+", text or ""))
    return out or tuple(default)


def _ints(xs: Iterable[int]) -> str:
    return ", ".join(str(int(x)) for x in xs)


def scope_where(statuses: Iterable[int], payment_codes: Iterable[int]) -> str:
    return (f"s.statecode = 0 AND s.new_SozlesmeTipi = {ALIS} AND s.new_TelifTipi IN ({_ints(payment_codes)})"
            f" AND s.statuscode IN ({_ints(statuses)})")


def heads_sql(p: str, statuses: Iterable[int], payment_codes: Iterable[int]) -> str:
    """M6'nın sözleşme başlığı sorgusu, kapsamdaki bütün sözleşmeler için (kolonlar birebir M6'nınki)."""
    head = C.crm_contract_sql(p, ZERO)[0]
    marker = f" WHERE s.new_sozlesmeId = '{ZERO}'"
    if marker not in head:
        raise SourceError("Sözleşme başlığı sorgusu beklenen biçimde değil; M6 sorgusu değişmiş.")
    return head.replace(marker, " WHERE " + scope_where(statuses, payment_codes)) + " ORDER BY s.new_sozlesmeId"


def books_sql(p: str, statuses: Iterable[int], payment_codes: Iterable[int]) -> str:
    """Kapsamdaki sözleşmelerin kitapları (M6'nın kitap kolonları + sözleşme kimliği)."""
    return ("SELECT sk.new_sozlesmeid AS sid, k.new_kitapId, k.new_name, k.new_StokKodu, k.new_isbn13, k.new_kdvdahilfiyat,"
            " k.new_EKitapStokKodu"
            f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_kitapBase k ON k.new_kitapId = sk.new_kitapid"
            f" JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid"
            f" WHERE {scope_where(statuses, payment_codes)} ORDER BY sk.new_sozlesmeid, k.new_name")


def parties_sql(p: str, statuses: Iterable[int], payment_codes: Iterable[int]) -> str:
    """Kapsamdaki sözleşmelerin tarafları (M6'nın taraf kolonları + e-posta). T.C./vergi no ve banka bilgisi okunmaz."""
    return ("SELECT t.new_sozlesmeid AS sid, t.new_kisi, t.new_Firma, c.FullName AS kisi, a.Name AS firma, t.new_Odeme,"
            " CAST(ISNULL(t.new_aracivarmi, 0) AS int) AS araci, c.EMailAddress1 AS kisi_eposta, a.EMailAddress1 AS firma_eposta"
            f" FROM {p}new_sozlesmetarafiBase t JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = t.new_sozlesmeid"
            f" LEFT JOIN {p}ContactBase c ON c.ContactId = t.new_kisi LEFT JOIN {p}AccountBase a ON a.AccountId = t.new_Firma"
            f" WHERE t.statecode = 0 AND {scope_where(statuses, payment_codes)} ORDER BY t.new_sozlesmeid, t.new_Odeme DESC")


def _gid(v: Any) -> str:
    return str(v or "").strip().strip("{}").lower()


def scope_contracts(heads: list[dict[str, Any]], books: list[dict[str, Any]], parties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CRM satırları → [{crmId, no, crmStatus, status, terms, emails}] (M6 eşlemesiyle)."""
    by_books: dict[str, list[dict[str, Any]]] = {}
    for b in books:
        by_books.setdefault(_gid(b.get("sid")), []).append(b)
    by_parties: dict[str, list[dict[str, Any]]] = {}
    for t in parties:
        by_parties.setdefault(_gid(t.get("sid")), []).append(t)
    out = []
    for h in heads:
        sid = _gid(h.get("new_sozlesmeId"))
        if not sid:
            continue
        ps = by_parties.get(sid, [])
        crm = C.crm_contract(h, by_books.get(sid, []), ps)
        emails: dict[str, str] = {}
        for t in ps:
            for idcol, mailcol in (("new_kisi", "kisi_eposta"), ("new_Firma", "firma_eposta")):
                pid, mail = _gid(t.get(idcol)), str(t.get(mailcol) or "").strip()
                if pid and mail:
                    emails[pid] = mail
        out.append({"crmId": sid, "no": crm["no"], "crmStatus": crm["crmStatus"], "status": crm["status"],
                    "terms": crm["terms"], "emails": emails})
    return out


def read_scope(crm: Runner, p: str, statuses: Iterable[int], payment_codes: Iterable[int]) -> list[dict[str, Any]]:
    st, pc = tuple(statuses), tuple(payment_codes)
    return scope_contracts(crm(heads_sql(p, st, pc)), crm(books_sql(p, st, pc)), crm(parties_sql(p, st, pc)))


def scope_count_sql(p: str, statuses: Iterable[int], payment_codes: Iterable[int]) -> str:
    """Kabul 1'in referansı: kapsamdaki sözleşme sayısı (koşudaki satır sayısıyla eşit olmalı)."""
    return f"SELECT COUNT(*) AS n FROM {p}new_sozlesmeBase s WHERE {scope_where(statuses, payment_codes)}"


# ------------------------------------------------------------------------------------------ Logo satış

def sales_years_sql() -> str:
    return "SELECT name FROM sys.views WHERE name LIKE 'V[_]SatisRaporu[_]20[0-9][0-9]'"


def present_years(logo: Runner) -> set[int]:
    return {int(str(r["name"])[-4:]) for r in logo(sales_years_sql())}


def read_sales(logo: Runner, codes: Iterable[str], a: date, b: date, present: set[int], today: date) -> tuple[list[dict[str, Any]], list[int]]:
    """Stok kodu × ay × satış/iade satırları (M6 sorgusu). Kod listesi gruplara bölünür; hepsi okunur."""
    from semantic_bridge.management import expand_sales

    codes = sorted({str(c).strip() for c in codes if str(c or "").strip()})
    rows: list[dict[str, Any]] = []
    missing: set[int] = set()
    for i in range(0, len(codes), CODE_CHUNK):
        sql, miss = expand_sales(R.sales_sql(codes[i:i + CODE_CHUNK], a, b), today, present)
        missing |= set(miss)
        rows += logo(sql)
    return rows, sorted(missing)


def read_data_end(logo: Runner, present: set[int], upto_year: int) -> Optional[str]:
    last = max([y for y in present if y <= upto_year] or [0])
    if not last:
        return None
    rows = logo(R.data_end_sql(last))
    return str(rows[0]["son"])[:10] if rows and rows[0].get("son") else None


def month_of(r: dict[str, Any]) -> int:
    return int(r.get("yil") or 0) * 12 + int(r.get("ay") or 0)


def group_by_code(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(str(r.get("kod") or "").strip(), []).append(r)
    return out


# ------------------------------------------------------------------------------------------ yenilemeler

def renewals_sql(p: str, frm: Optional[date], to: Optional[date], contract_id: Optional[str] = None) -> str:
    """Bitişi [frm, to) aralığında olan etkin, süreli sözleşmeler (bütün türler; kabul 7). `frm` boşsa geçmişe açık.
    `contract_id` verilirse yalnız o sözleşme (tarih ve süre koşulu uygulanmaz)."""
    if contract_id:
        cond = ["s.statecode = 0", f"s.new_sozlesmeId = '{_check_guid(contract_id)}'"]
        frm = to = None
    else:
        cond = ["s.statecode = 0", "ISNULL(s.new_suresizsozlesme, 0) = 0", "s.new_SozlesmeBitisTarihi IS NOT NULL"]
    if frm:
        cond.append(f"s.new_SozlesmeBitisTarihi >= '{frm.isoformat()}'")
    if to:
        cond.append(f"s.new_SozlesmeBitisTarihi < '{to.isoformat()}'")
    return ("SELECT s.new_sozlesmeId AS id, s.new_name AS no, CAST(s.new_SozlesmeTipi AS int) AS tip_kod,"
            " CAST(s.new_TelifTipi AS int) AS odeme_kod, CAST(s.statuscode AS int) AS durum_kod,"
            " s.new_SozlesmeBaslangicTarihi AS bas, s.new_SozlesmeBitisTarihi AS bit,"
            " s.new_SzlemeYenilenmeSklyl AS yenileme_yil, s.new_yenilemebaslangictarihi AS yen_bas,"
            " s.new_yenilemebitistarihi AS yen_bit, s.new_imhaSuresiAy AS imha_ay, s.new_RaporVermeSresi AS rapor_suresi,"
            " s.new_YaynlanmamasHalindeFesihTarihi AS yayinlanmama_fesih, s.new_sozlesmeavanstutari AS avans,"
            " CAST(s.new_sozlesmeparabirimi AS int) AS para_kod, s.new_yazar_text AS yazar, s.new_mutercim_text AS mutercim,"
            " s.new_cizer_text AS cizer, s.new_stokkodutext AS stok, s.new_stokaditext AS kitap"
            f" FROM {p}new_sozlesmeBase s WHERE {' AND '.join(cond)} ORDER BY s.new_SozlesmeBitisTarihi, s.new_name")


def renewal_count_sql(p: str, frm: date, to: date) -> str:
    """Kabul 7'nin referansı."""
    return (f"SELECT COUNT(*) AS n FROM {p}new_sozlesmeBase WHERE statecode = 0 AND ISNULL(new_suresizsozlesme, 0) = 0"
            f" AND new_SozlesmeBitisTarihi >= '{frm.isoformat()}' AND new_SozlesmeBitisTarihi < '{to.isoformat()}'")


# ------------------------------------------------------------------------------------------ haklar

#: Hak kartında gösterilen CRM hak bitleri (kolon → anahtar). M6'nın sekiz hakkına ek: Z-kitap, yabancı dile çeviri,
#: yurtdışı telif satışı, mali hakların devri.
RIGHT_COLUMNS = {**{col: key for col, key in T.RIGHT_FROM_CRM.items()},
                 "new_ZKitapHakki": "zkitap", "new_yabancidilecevirihakki": "yabanci-dil",
                 "new_yurtdisitelifsatis": "yurtdisi-satis", "new_malihaklardevir": "mali-devir"}
RIGHT_LABELS = {**T.RIGHT_KEYS, "zkitap": "Z-kitap", "yabanci-dil": "Yabancı dile çeviri",
                "yurtdisi-satis": "Yurtdışına telif satışı", "mali-devir": "Mali hakların devri"}


def book_head_sql(p: str, book_id: str) -> str:
    g = _check_guid(book_id)
    return (f"SELECT k.new_kitapId, k.new_name, k.new_StokKodu, k.new_isbn13, k.new_EKitapStokKodu"
            f" FROM {p}new_kitapBase k WHERE k.new_kitapId = '{g}'")


def book_contracts_sql(p: str, book_id: str) -> str:
    """Kitaba bağlı etkin Telif Alış ve Telif Satış sözleşmeleri, hak bitleriyle ve CRM lisans şartlarıyla
    (`crm_rights`: orijinal dil, satılan ülke ve hakkı devreden firma bağlı kayıtlardan adıyla okunur)."""
    g = _check_guid(book_id)
    bits = ", ".join(f"CAST(ISNULL(s.{col}, 0) AS int) AS [{col}]" for col in RIGHT_COLUMNS)
    return ("SELECT s.new_sozlesmeId AS id, s.new_name AS no, CAST(s.new_SozlesmeTipi AS int) AS tip_kod,"
            " CAST(s.statuscode AS int) AS status, s.new_SozlesmeBaslangicTarihi AS bas, s.new_SozlesmeBitisTarihi AS ends,"
            " CAST(ISNULL(s.new_suresizsozlesme, 0) AS int) AS open_ended, s.new_fesihtarihi AS terminated,"
            " CAST(ISNULL(s.new_KorumaDEser, 0) AS int) AS public_domain, s.new_haklaraciklama AS rights_note,"
            " CAST(s.new_orjinaldili AS nvarchar(200)) AS orjinal_dil, CAST(s.new_telifsatilanulke AS nvarchar(200)) AS satilan_ulke,"
            " CAST(s.new_hakdevredenfirma AS nvarchar(200)) AS hak_devreden, s.new_yazar_text AS yazar,"
            f" s.new_mutercim_text AS mutercim, s.new_cizer_text AS cizer, {bits}, {crm_rights.columns('s')}"
            f" FROM {p}new_new_sozlesme_new_kitapBase sk JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid"
            f"{crm_rights.joins(p, 's')}"
            f" WHERE sk.new_kitapid = '{g}' AND s.statecode = 0 AND s.new_SozlesmeTipi IN ({ALIS}, {SATIS})"
            " ORDER BY s.new_SozlesmeTipi DESC, s.new_name")


def book_parties_sql(p: str, book_id: str) -> str:
    g = _check_guid(book_id)
    return ("SELECT t.new_sozlesmeid AS sid, c.FullName AS kisi, a.Name AS firma"
            f" FROM {p}new_sozlesmetarafiBase t JOIN {p}new_new_sozlesme_new_kitapBase sk ON sk.new_sozlesmeid = t.new_sozlesmeid"
            f" LEFT JOIN {p}ContactBase c ON c.ContactId = t.new_kisi LEFT JOIN {p}AccountBase a ON a.AccountId = t.new_Firma"
            f" WHERE t.statecode = 0 AND sk.new_kitapid = '{g}'")


def contract_options_sql(p: str) -> str:
    """Sözleşme varlığının seçim listesi etiketleri (dil, ülke gibi alanlar seçim listesiyse etiketi görünür)."""
    return ("SELECT s.AttributeName AS attr, s.AttributeValue AS code, s.Value AS label"
            f" FROM {p}StringMapBase s WHERE s.ObjectTypeCode = (SELECT TOP 1 e.ObjectTypeCode FROM {p}EntityView e"
            " WHERE e.Name = 'new_sozlesme') AND s.AttributeName IN ('new_orjinaldili', 'new_telifsatilanulke',"
            " 'new_hakdevredenfirma') AND s.LangId = 1055")


def notes_sql(p: str) -> str:
    """Serbest metinli hak açıklaması olan etkin Telif Alış sözleşmeleri (sınıflandırma için)."""
    return ("SELECT s.new_sozlesmeId AS id, s.new_name AS no, s.new_haklaraciklama AS metin, s.new_stokaditext AS kitap"
            f" FROM {p}new_sozlesmeBase s WHERE s.statecode = 0 AND s.new_SozlesmeTipi = {ALIS}"
            " AND LEN(LTRIM(RTRIM(ISNULL(s.new_haklaraciklama, '')))) > 0 ORDER BY s.new_name")


def rights_bit_count_sql(p: str, col: str = "new_iletimhakki") -> str:
    """Kabul 8'in referansı: etkin Telif Alış sözleşmelerinde bu hakkı taşıyan kitap sayısı."""
    if col not in RIGHT_COLUMNS:
        raise SourceError("Bilinmeyen hak kolonu.")
    return (f"SELECT COUNT(DISTINCT sk.new_kitapid) AS n FROM {p}new_new_sozlesme_new_kitapBase sk"
            f" JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid"
            f" WHERE s.statecode = 0 AND s.new_SozlesmeTipi = {ALIS} AND s.{col} = 1")


def _check_guid(v: str) -> str:
    if not _GUID.match(v or ""):
        raise SourceError("Kimlik geçerli değil.")
    return _gid(v)


def option_label(options: dict[str, dict[int, str]], attr: str, value: Any) -> Optional[str]:
    """Seçim listesi koduysa etiketi; kayıt kimliğiyse (başka tabloya bağ) yok; düz metinse kendisi."""
    s = str(value or "").strip()
    if not s:
        return None
    if _GUID.match(s):
        return None
    try:
        code = int(float(s))
    except ValueError:
        return s
    return options.get(attr.lower(), {}).get(code) or f"Kod {code}"
