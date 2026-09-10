"""What the vendor never documented, worked out from what it did.

After the dictionary is carried into the catalog, five thousand columns are still nameless. They are
not an oversight in the import: the documents describe a release from 2000 and the customer runs one
with e-invoicing, IFRS valuation columns and an approval module that did not exist then. The
documents are exhausted; these columns are in none of them.

They are not unknowable, though. Logo names columns consistently across three hundred tables, and
nine thousand of those names *are* documented. `USERNAME` means the same thing in the table nobody
wrote about as in the twenty that were. `PARAMVAL1` is the first of `PARAMVAL`. `DISTTOTALUFRS` is
`DISTTOTAL` under IFRS. Each of these is a reading of the vendor's own vocabulary, not a guess about
a column nobody has ever seen.

So it is written where a reading belongs. `description` stays what the source said — empty here —
and this goes to `derived`, which the catalog keeps separate and labelled, and which loses to
anything a person writes in the portal. Nothing here can overwrite anybody.

    python backend/scripts/derive_column_meanings.py [--apply]
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semantic_layer.config import SemanticSettings          # noqa: E402
from semantic_layer.profiler import logo_dictionary          # noqa: E402
from semantic_layer.store.catalog_store import open_store    # noqa: E402

SOURCE = "convention"

#: Tables that are somebody's copy, not the business's data. Describing them spends effort on rows no
#: question is ever about, and puts them in the way of routing a question to the real one.
_NOT_A_TABLE = re.compile(r"(YEDEK|BACKUP|_BAK|_COPY|PERFTEST|_TMP|TEMP\d|_OLD|_ESKI|_TEST)", re.I)

#: The audit block Logo stamps on every record. Documented on some tables, absent on others, always
#: the same six fields.
_AUDIT = {
    "CREATEDBY": "Kaydı oluşturan kullanıcı", "CREATEDDATE": "Kaydın oluşturulma tarihi",
    "CREADEDDATE": "Kaydın oluşturulma tarihi", "CREATEDHOUR": "Kaydın oluşturulma saati",
    "CREATEDMIN": "Kaydın oluşturulma dakikası", "CREATEDSEC": "Kaydın oluşturulma saniyesi",
    "MODIFIEDBY": "Kaydı son değiştiren kullanıcı", "MODIFIEDDATE": "Kaydın son değiştirilme tarihi",
    "MODIFIEDHOUR": "Kaydın son değiştirilme saati", "MODIFIEDMIN": "Kaydın son değiştirilme dakikası",
    "MODIFIEDSEC": "Kaydın son değiştirilme saniyesi",
}

#: A suffix the vendor uses consistently, and what it does to the meaning of the name it is added to.
_SUFFIX = [
    ("UFRS", "{} — UFRS (IFRS) değerlemesi"),
    ("REF", "{} referansı"),
    ("DATE", "{} tarihi"),
    ("CODE", "{} kodu"),
    ("NO", "{} numarası"),
]


#: Logo's core vocabulary, in Turkish, matched on the whole name.
#:
#: These are documented — `LOGICALREF` is explained in three hundred tables — but each table words it
#: differently ("Item Card Logical Reference", "Cari hesap kartı fiziksel adresi"), so no single
#: wording is dominant enough to carry to a table that lacks one, and carrying one table's wording to
#: another would say the wrong thing. The meaning is not in doubt; only the phrasing is. So the
#: phrasing is written once, here, in the language the questions arrive in.
_CANONICAL: dict[str, str] = {
    # kimlik ve durum
    "LOGICALREF": "Kaydın fiziksel referansı — birincil anahtar; diğer tablolar *REF kolonlarıyla buna bağlanır",
    "CODE": "Kart/kayıt kodu", "NAME": "Ad", "NAME2": "İkinci ad", "SURNAME": "Soyad",
    "DEFINITION_": "Açıklama / unvan", "ACTIVE": "Kullanım durumu (0 kullanımda, 1 kullanım dışı)",
    "CANCELLED": "İptal bayrağı (0 geçerli, 1 iptal)", "STATUS": "Durum", "ESTATUS": "e-Belge durumu",
    "STATUSDESC": "Durum açıklaması", "PRIORITY": "Öncelik", "TYP": "Tür", "TYPECODE": "Tür kodu",
    "GLOBALID": "Kurum genelinde tekil kayıt kimliği", "GLOBALCODE": "Kurum genelinde tekil kod",
    "RECHASH": "Kayıt özet değeri — kaydın değişip değişmediğinin denetimi",
    # sınıflama
    "TRCODE": "İşlem/belge türü kodu", "MODULENR": "Modül numarası", "LINENO_": "Satır numarası",
    "SPECODE": "Özel kod", "CYPHCODE": "Yetki kodu", "TRADINGGRP": "Ticari işlem grubu",
    "CARDTYPE": "Kart türü", "DOCTYPE": "Belge türü", "DOCODE": "Belge kodu", "FICHETYPE": "Fiş türü",
    "TRANSTYPE": "Hareket türü", "PAYTYPE": "Ödeme türü", "USERTYPE": "Kullanıcı türü",
    # tarih ve zaman
    "DATE_": "Belge/hareket tarihi", "SDATE": "Tarih", "BEGDATE": "Başlangıç tarihi",
    "ENDDATE": "Bitiş tarihi", "DUEDATE": "Vade tarihi", "CURRENTDATE": "Güncel tarih",
    "CURRENTTIME": "Güncel saat", "PRINTDATE": "Basım tarihi", "PRINTCNT": "Basım sayısı",
    # tutar ve miktar
    "AMOUNT": "Miktar", "TOTAL": "Toplam tutar", "PRICE": "Birim fiyat", "ORGPRICE": "Orijinal birim fiyat",
    "ITMDISC": "Malzeme iskontosu", "INFLATIONDIFF": "Enflasyon düzeltme farkı",
    "TRRATE": "İşlem dövizi kuru", "REPORTRATE": "Raporlama dövizi kuru",
    "CLTRCURR": "Cari işlem dövizi türü", "CLTRRATE": "Cari işlem dövizi kuru",
    "CLTRNET": "Cari işlem dövizi net tutarı", "EXIMVAT": "İthalat/ihracat KDV tutarı",
    "VATFLAG": "KDV uygulanıyor mu", "VATEXCEPTCODE": "KDV istisna kodu",
    "VATEXCEPTREASON": "KDV istisna gerekçesi",
    # referanslar
    "CLIENTREF": "Cari hesap referansı", "CLCARDREF": "Cari hesap kartı referansı",
    "ITEMREF": "Malzeme referansı", "ACCOUNTREF": "Muhasebe hesabı referansı",
    "CENTERREF": "Masraf merkezi referansı", "UOMREF": "Birim referansı",
    "INVOICEREF": "Fatura referansı", "FICHEREF": "Fiş referansı", "FICHENO": "Fiş numarası",
    "STFREF": "Stok fişi referansı", "TRANSREF": "Hareket referansı", "PARENTREF": "Üst kayıt referansı",
    "DOCREF": "Belge referansı", "OFFERREF": "Teklif referansı", "FAREF": "Sabit kıymet referansı",
    "FAREGREF": "Sabit kıymet kaydı referansı", "PERREF": "Personel referansı", "USREF": "Kullanıcı referansı",
    "WSREF": "İş istasyonu referansı", "BNACCREF": "Banka hesabı referansı",
    "EMFLINEREF": "Muhasebe hareketi referansı", "SOURCEFREF": "Kaynak fiş referansı",
    "SOURCEINDEX": "Kaynak ambar/işyeri indeksi", "APPROVALREF": "Onay kaydı referansı",
    "CRELETTERREF": "Akreditif referansı", "LEASINGREF": "Leasing sözleşmesi referansı",
    # yer ve kuruluş
    "BRANCH": "İşyeri (şube) numarası", "FACTORYNR": "Fabrika numarası", "WAREHOUSE": "Ambar numarası",
    "CITY": "Şehir", "COUNTRY": "Ülke", "POSTCODE": "Posta kodu",
    # kimlik bilgileri
    "TAXNR": "Vergi numarası", "TCKNO": "TC kimlik numarası", "IBAN": "IBAN",
    "ISPERSCOMP": "Şahıs şirketi mi", "ISCOMP": "Tüzel kişi (şirket) mi",
    "PAYERID": "Ödeyen kimlik numarası", "PAYERTYPE": "Ödeyen türü",
    # serbest metin
    "EXPLAIN": "Açıklama", "EXPLANATION": "Açıklama", "EXP": "Açıklama", "LINEEXP": "Satır açıklaması",
    "DELIVERYCODE": "Teslimat kodu", "CAMPAIGNCODE": "Kampanya kodu",
    "USEDINPERIODS": "Kaydın kullanıldığı dönemler",
}

#: Numbered free-text slots the vendor leaves for the customer: GENEXP1..6, UINFO1..8.
_NUMBERED = {
    "GENEXP": "Genel açıklama alanı",
    "UINFO": "Kullanıcı tanımlı bilgi alanı",
    "ROLLUPOVERHRPCOSTG": "Toplanmış (roll-up) genel üretim gideri — raporlama dövizi, grup",
    "ROLLUPOVERHCOSTG": "Toplanmış (roll-up) genel üretim gideri — grup",
}

#: Rolled-up production cost components: the cost of a product with everything beneath it added in.
_ROLLUP = {
    "ROLLUPMATERIALCOST": "Toplanmış malzeme maliyeti", "ROLLUPWSCOST": "Toplanmış iş istasyonu maliyeti",
    "ROLLUPLABORCOST": "Toplanmış işçilik maliyeti", "ROLLUPOVERHCOST": "Toplanmış genel üretim gideri",
    "ROLLUPTOTALCOST": "Toplanmış toplam maliyet",
    "ROLLUPMATERIALRPCOST": "Toplanmış malzeme maliyeti — raporlama dövizi",
    "ROLLUPWSRPCOST": "Toplanmış iş istasyonu maliyeti — raporlama dövizi",
    "ROLLUPLABORRPCOST": "Toplanmış işçilik maliyeti — raporlama dövizi",
    "ROLLUPOVERHRPCOST": "Toplanmış genel üretim gideri — raporlama dövizi",
    "ROLLUPTOTALRPCOST": "Toplanmış toplam maliyet — raporlama dövizi",
}


#: An array the vendor flattened into columns: `PROMLINES16_PRICE`, `ACCARR10_ACCTYPE`. The group is
#: repeated N times and the field after the underscore is the documented one.
_ARRAY = re.compile(r"^([A-Z]+?)(\d+)_(.+)$")

#: What the documents could not say, because the modules did not exist when they were written.
#:
#: These are read from the vendor's naming, from what the surrounding columns do, and from what the
#: Turkish regulation behind them requires — e-fatura and e-arşiv became mandatory a decade after the
#: structure document was typed, UFRS valuation and the approval flow later still. They are stated as
#: readings, not as documentation: they go to `derived`, and a single word from anyone in the portal
#: replaces them.
_DOMAIN: list[tuple[str, str]] = [
    # e-belge (e-fatura / e-arşiv / e-irsaliye / e-müstahsil)
    ("ACCEPTEINVPUBLIC", "Kamu e-faturası kabul ediliyor mu"),
    ("ACCEPTEINV", "e-Fatura mükellefi / e-fatura kabul ediliyor mu"),
    ("ACCEPTEDESP", "e-İrsaliye kabul ediliyor mu"),
    ("ACCEPTESLIP", "e-Müstahsil makbuzu kabul ediliyor mu"),
    ("EARCHIVE", "e-Arşiv faturası"),
    ("EINVOICE", "e-Fatura"),
    ("EDESPATCH", "e-İrsaliye"),
    ("PROFILEID", "e-Belge senaryosu (TEMELFATURA / TICARIFATURA)"),
    ("SENDMOD", "e-Belge gönderim yöntemi"),
    ("GUID", "e-Belge tekil kimliği (UUID)"),
    ("ETTN", "e-Belge evrensel tekil tanımlama numarası (ETTN)"),
    # ek vergi (ÖTV) — 2000 sonrası
    ("ADDTAXEFFECTKDV", "Ek verginin KDV matrahına etkisi"),
    ("ADDTAXINLINENET", "Ek vergi satır net tutarına dahil mi"),
    ("ADDTAX", "Ek vergi (ÖTV)"),
    ("ATAXEXCEPTREASON", "Ek vergi istisna gerekçesi"),
    ("ATAXEXCEPTCODE", "Ek vergi istisna kodu"),
    # onay akışı
    ("APPRFLOWACTION", "Onay akışı işlemi"),
    ("APPRFLOWSTAT", "Onay akışı durumu"),
    ("APPRFLOWGRP", "Onay akışı grubu"),
    ("APPROVERGROUPREF", "Onaylayan grup referansı"),
    ("APPROVEDATE", "Onay tarihi"),
    ("APPROVED", "Onaylandı mı"),
    ("APPROVE", "Onay bayrağı"),
    # banka / vergi
    ("BSMV", "BSMV (banka ve sigorta muameleleri vergisi)"),
    ("BNBSMV", "BSMV (banka ve sigorta muameleleri vergisi)"),
    # maliyet grupları
    ("ACTOVERHCOSTG", "Gerçekleşen genel üretim gideri (grup)"),
    ("OVERHCOSTG", "Genel üretim gideri (grup)"),
    ("ACTCOSTCALCULATED", "Gerçekleşen maliyet hesaplandı mı"),
    # muhasebe / beyan
    ("APPSPEVATMATRAH", "Özel matrah uygulanan KDV matrahı"),
    ("APPCLDEDUCTLIM", "Tevkifat alt limiti uygulanıyor mu"),
    ("DEDUCT", "Tevkifat"),
    # kart / adres
    ("ADRESSNO", "Adres numarası"),
    ("ADDR", "Adres satırı"),
    ("BUYERCLIENTREF", "Alıcı cari hesap referansı"),
    ("AGENCYCODE", "Acente kodu"),
    ("AGENCY", "Acente"),
]


def vocabulary() -> dict[str, str]:
    """Every column name the vendor documented, and what it said — across all tables.

    A name is only usable this way if the vendor means one thing by it. `LOGICALREF` is the record's
    own reference in all three hundred tables; a name that means two different things in two tables
    says nothing about a third, and is dropped rather than guessed at.
    """
    said: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for table in (logo_dictionary.dictionary().get("tables") or {}).values():
        for column, meta in (table.get("columns") or {}).items():
            text = (meta.get("description_tr") or meta.get("description") or "").strip()
            if text:
                said[column][text] += 1
    out = {}
    for column, texts in said.items():
        (best, n), = texts.most_common(1)
        if n / sum(texts.values()) >= 0.6:      # one dominant reading, not a coin toss
            out[column] = best
    return out


def derive(name: str, vocab: dict[str, str]) -> tuple[str, str]:
    """(text, why) for a column the documents never named — or ("", "") when they say nothing."""
    n = name.upper()
    # The core vocabulary is written here rather than voted on, because the vendor's wording for it
    # varies table by table while the meaning does not.
    if text := _CANONICAL.get(n) or _ROLLUP.get(n):
        return text, "çekirdek Logo sözlüğü"
    if m := re.match(r"^([A-Z_]+?)(\d+)$", n):
        if base := _NUMBERED.get(m.group(1)):
            return f"{base} {m.group(2)}", "numaralı alan"
    if text := vocab.get(n):
        return text, "aynı ad sözlükte belgeli"
    for prefix in ("CAPIBLOCK_", "CAPIBLOK_"):
        if n.startswith(prefix) and (text := _AUDIT.get(n[len(prefix):])):
            return text, "denetim bloğu"
    if text := _AUDIT.get(n):
        return text, "denetim bloğu"
    if m := re.match(r"^(.*?)(\d+)$", n):
        if base := vocab.get(m.group(1)):
            return f"{base} ({m.group(2)}. değer)", "numaralı varyant"
    for suffix, shape in _SUFFIX:
        if n.endswith(suffix) and len(n) > len(suffix) and (base := vocab.get(n[:-len(suffix)])):
            return shape.format(base.rstrip(".")), f"'{suffix}' eki"
    if m := _ARRAY.match(n):
        group, index, field = m.groups()
        if base := vocab.get(field):
            return f"{base} — {group} dizisi, {index}. eleman", "dizi kolonu"
    # Last, and only where the vendor's own vocabulary runs out: what the name means in a Turkish ERP
    # whose modules postdate the documents. Longest match first, so ACCEPTEINVPUBLIC does not answer
    # to ACCEPTEINV.
    for token, text in sorted(_DOMAIN, key=lambda kv: -len(kv[0])):
        if token in n:
            return text, "alan bilgisi (çıkarım)"
    return "", ""


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn)
    profiles = store.list_profiles(s.datasource_id)
    vocab = vocabulary()
    print(f"sözlükte tek anlamlı kolon adı: {len(vocab)}")

    filled = collections.Counter()
    still = collections.Counter()
    changed = []
    for p in profiles:
        if _NOT_A_TABLE.search(p.entity):
            continue
        touched = False
        for c in p.columns:
            if (c.description or "").strip() or c.meaning():
                continue
            text, why = derive(c.name, vocab)
            if text:
                c.add_derived(SOURCE, text)
                filled[why] += 1
                touched = True
            else:
                still[p.entity] += 1
        if touched:
            changed.append(p)

    print(f"\n{sum(filled.values())} kolon türetildi:")
    for why, n in filled.most_common():
        print(f"   {why:34} {n:5}")
    print(f"\n{sum(still.values())} kolon hâlâ açıklamasız — en çok: {still.most_common(6)}")
    if not apply:
        print("\n(kuru çalışma — yazmak için --apply)")
        return 0
    for p in changed:
        store.upsert_profile(p)
    print(f"\n{len(changed)} profil güncellendi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
