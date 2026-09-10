"""A name for every table the vendor's documents never named.

Two hundred and thirteen tables in this catalog have no description in either source, and they are
the ones that matter most for finding anything: a question is routed to a table by what the table
says it is, and a table that says nothing is a table no question reaches. They are undocumented for
a reason — e-defter, e-arşiv, the approval flow, DİİB, collateral management and the marketplace
integration are all modules that postdate the structure document by a decade or more.

What they are is not a mystery, though. `EINVOICEDET` holds `INVOICEREF`, `PROFILEID`, `ESTATUS`;
`GUARANTOR` holds `GNAMESURNAME`, `ADDR1`, `TELNRS1`; `STSHIPPEDAMOUNT` holds `ORDTRANSREF` and
`SHIPPEDAMOUNT`. Each of these is a reading of the vendor's own naming and of what the columns
plainly are — the same reading a person who knows Logo would make, written down once.

It goes to `derived`, the slot the catalog keeps for what this system concluded, and loses to
anything anybody writes in the portal. `description` stays reserved for what a source actually said.

    python backend/scripts/describe_undocumented_tables.py [--apply]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semantic_layer.config import SemanticSettings          # noqa: E402
from semantic_layer.store.catalog_store import open_store    # noqa: E402

SOURCE = "convention"

_NOT_A_TABLE = re.compile(r"(YEDEK|BACKUP|_BAK|_COPY|PERFTEST|_TMP|TEMP\d|_OLD|_ESKI|_TEST)", re.I)

#: Read from the table's own name and the columns it holds. Ordered here by what the database
#: actually carries, so the ones a question is most likely to reach are the ones written most exactly.
NAMED: dict[str, str] = {
    # izleme ve aktarım
    "LG_HISTORY": "Kayıt değişiklik geçmişi — hangi tablodaki hangi kaydı kim, ne zaman değiştirdi",
    "CHANGELOG": "Kullanıcı işlem günlüğü — hangi kullanıcı hangi formda ne yaptı",
    "DATAEXCHHISTORY": "Veri aktarım geçmişi (e-belge ve entegrasyon gönderim/alım kayıtları)",
    "RESPONSEHISTORY": "e-Belge yanıt geçmişi — GİB/entegratör dönüş kodları ve durumları",
    "EXIMHISTORY": "İthalat/ihracat işlem geçmişi",
    "RULEHISTORY": "Onay kuralı işlem geçmişi",
    # e-belge
    "EINVOICEDET": "e-Fatura detayları — senaryo, durum, taraf bilgileri ve GİB alanları",
    "EARCHIVEDET": "e-Arşiv fatura detayları — gönderim yöntemi, ÖKC ve internet satış bilgileri",
    "EBOOKDETAILDOC": "e-Defter belge detayları — muhasebe fişine bağlı belge bilgileri",
    "EBOOKINFO": "e-Defter berat bilgileri — dönem, kontrol numarası ve sorumlu bilgileri",
    "EBOOKPARAMS": "e-Defter parametreleri — modül ve işlem türü eşleştirmeleri",
    "DOCSCHEMA": "Belge şema tanımları — e-belge tür ve eklenti eşleştirmesi",
    "DOCPRINT": "Belge basım kayıtları — hangi belge hangi tasarımla kaç kez basıldı",
    "FICHEOBJECT": "Fişe eklenen nesne/dosya kayıtları",
    # muhasebe dağıtımı
    "ACCDISTDETLN": "Muhasebe fişi masraf merkezi/proje dağıtım satırları",
    "PREACCDISTDETLINE": "Muhasebeleştirme öncesi masraf merkezi/proje dağıtım satırları",
    "ACCDISTTEMP": "Masraf dağıtım şablonu",
    "ACCDISTTEMPLN": "Masraf dağıtım şablonu satırları",
    "GLASSGN": "Muhasebe hesabı ataması — modül ve işlem türüne göre hesap/masraf merkezi",
    "ACCFCASGN": "Muhasebe fişi ile kaynak fiş arasındaki bağ",
    "EMUHACCSUBACCASGN": "Muhasebe hesabı - alt hesap ataması",
    "TAXDECLLINEACC": "Beyanname satırı ile muhasebe hesabı ilişkisi",
    "FINTBLHEADER": "Mali tablo tanım başlığı",
    # döviz karşılıkları
    "STLINEEXCH": "Malzeme hareketi satırlarının döviz tutarları",
    "ORDLINEEXCH": "Sipariş satırlarının döviz tutarları",
    "INVOICEEXCH": "Fatura toplamlarının döviz tutarları",
    "STFEXCH": "Stok fişi toplamlarının döviz tutarları",
    "ORDFEXCH": "Sipariş fişi toplamlarının döviz tutarları",
    # sipariş / sevkiyat / stok
    "STSHIPPEDAMOUNT": "Sipariş satırına karşılık sevk edilen miktarlar",
    "STLNIOPEGGING": "Stok giriş-çıkış hareketlerinin birbirine eşleştirilmesi",
    "STLINENEGLEVEL": "Negatif stok seviyesine düşüren hareketler",
    "LOCATIONSFOR": "Stok yeri (raf) atamaları",
    "PRCLSTDIV": "Fiyat listesinin ambar/bölüm dağılımı",
    "DEMANDFICHE": "Talep fişi başlıkları",
    "DEMANDLINE": "Talep fişi satırları",
    "DEMANDPEGGING": "Talebin hangi kaynakla karşılandığının eşleştirmesi",
    # cari / risk / teminat
    "CLCOLLATRLRISK": "Cari hesap teminat ve risk toplamları",
    "COLLATRLCARD": "Teminat kartları (çek, senet, ipotek, teminat mektubu)",
    "COLLATRLROLL": "Teminat portföy (rulo) kayıtları",
    "COLLATRLTRAN": "Teminat hareketleri",
    "COLLCOMMPAYTR": "Teminat komisyon ve ödeme hareketleri (BSMV, damga vergisi dahil)",
    "GUARANTOR": "Kefil bilgileri — ad, adres ve iletişim",
    "CLPARAMS": "Cari hesap parametreleri",
    "CLPARAMHEADER": "Cari hesap parametre başlığı ve barkod ayarları",
    "CLBRANCHPAYPLANS": "Cari hesabın işyeri bazlı ödeme planları",
    "DISCPAYTRANS": "İskontolu ödeme hareketleri",
    "CSPAYMENT": "Çek/senet ödeme kayıtları",
    "REPAYPLANS": "Geri ödeme planları",
    "REPAYPLANSLN": "Geri ödeme planı satırları",
    # nakit
    "CASHFLOWCARD": "Nakit akış raporu kartı",
    "CASHFLOWLINE": "Nakit akış raporu satırları",
    "CASHFLOWDEF": "Nakit akış tanımları",
    "GNTOTBN": "Banka genel toplamları",
    "GNTOTCSH": "Kasa genel toplamları",
    # dış ticaret
    "INVEXIMINFO": "İthalat/ihracat fatura bilgileri — ülke, gümrük ve taşıma tarafları",
    "INVEXIMLINES": "İthalat/ihracat fatura satırları — gümrük beyanname ve DİİB bağları",
    "IMPSRVREL": "İthalat hizmet faturası ile fatura ilişkisi",
    "DIIB": "Dahilde İşleme İzin Belgesi (DİİB) başlıkları",
    "DIIBLINE": "DİİB satırları — GTİP ve miktar bilgileri",
    "DIIBBOMLINE": "DİİB ürün reçetesi satırları",
    # onay akışı
    "APPROVAL": "Onay akışı kayıtları — hangi belge hangi aşamada, kim gönderdi",
    "APPROVERS": "Bir onay kaydını onaylayan kullanıcılar",
    "APPROVE": "Onay kayıtları — işyeri ve modül bazında",
    "RULES": "Onay/iş kuralı tanımları",
    # üretim ve maliyet
    "COSTDISTPEG": "Maliyet dağıtımının hangi hareketle eşleştiğinin kaydı",
    "PRODUCTLINE": "Üretim hattı tanımları ve kapasiteleri",
    "PRODUCERPARAMS": "Müstahsil parametreleri — stopaj, borsa, bağkur ve komisyon oranları",
    "FAREGNEWVALUE": "Sabit kıymet yeniden değerleme kayıtları",
    "RETAMOUNT": "İade miktarı",
    # tanım ve kullanıcı alanları
    "DEFNFLDSTRANV": "Kullanıcı tanımlı alan değerleri — hareketler",
    "DEFNFLDSCARDV": "Kullanıcı tanımlı alan değerleri — kartlar",
    "EXTRAINFO": "Ek bilgi kayıtları — kullanıcı tanımlı serbest alanlar",
    "APPPARAM": "Kullanıcı uygulama parametreleri (görünüm ve varsayılan ayarlar)",
    "PROJECT": "Proje kartları",
    "MARK": "Marka tanımları",
    "MARKETPLACE": "Pazaryeri entegrasyon tanımı",
    "SUPPEVALCR": "Tedarikçi değerlendirme kriterleri",
    "SUPPEVALCRLN": "Tedarikçi değerlendirme kriter satırları",
    "DIVATRANS": "DIVA veri aktarım hareketleri",
    # --- ikinci geçiş: kalan tablolar, kolonlarından okunarak -------------------------------------
    # e-belge ve GİB
    "EINVOICELOG": "e-Fatura işlem günlüğü",
    "EPRODUCERRECDET": "e-Müstahsil makbuzu detayları",
    "ETRADESMANINVDET": "e-Serbest meslek / esnaf fatura detayları",
    "GIBACCFICHE": "GİB'e aktarılan muhasebe fişi",
    "GIBACCFICHELN": "GİB'e aktarılan muhasebe fişi satırları",
    "OKCINFO": "Ödeme kaydedici cihaz (ÖKC) bilgileri — seri no, Z no, fiş no",
    "LDXRECDELREQ": "Veri aktarımında kayıt silme talebi",
    "DOCSELLIST": "Belge seçim listesi tanımları",
    "SPECTEMPLATES": "Özel belge şablonları",
    "LG_RECKEEPING": "Kayıt saklama (defter-beyan) parametreleri",
    # dış ticaret
    "EXIMDISTFC": "Dış ticaret masraf dağıtım fişleri",
    "EXIMDISTLN": "Dış ticaret masraf dağıtım satırları",
    "EXIMDISTPEG": "Dış ticaret masraf dağıtımının hareketle eşleştirilmesi",
    "EXIMWHFC": "Dış ticaret antrepo fişleri",
    "EXIMWHTRANS": "Dış ticaret antrepo hareketleri",
    "CREDITLETTERS": "Akreditifler — vade, poliçe ve belge teslim tarihleri",
    "STFCEXTINF": "Stok fişi ek bilgileri (Intrastat / gümrük)",
    "UETDSVOYAGE": "U-ETDS sefer bildirimi — plaka, sürücü, sefer tarihleri",
    "UETDSCARGOINFO": "U-ETDS yük bildirimi — yükleme/boşaltma yeri ve taşıma türü",
    # muhasebe ve vergi
    "EMDEMDETLN": "Muhasebe fişi talep dağıtım satırları",
    "EMFLNINFCOEF": "Muhasebe satırı enflasyon düzeltme katsayıları",
    "STLNINFCOEF": "Malzeme hareketi enflasyon düzeltme katsayıları",
    "EXCDIFFTRANS": "Kur farkı hareketleri — kapatan ve kapatılan fişlerle birlikte",
    "ACCCRREL": "Muhasebe hesabı - masraf merkezi - proje ilişkisi",
    "ACCOUNTTEMPLATES": "Muhasebe hesap şablonları",
    "COMPANSEACC": "Karşılık hesap eşleştirmesi",
    "MULTIADDTAXLN": "Çoklu ek vergi (ÖTV) satırları",
    "DEDUCTLIMITS": "Tevkifat alt limitleri",
    "JOURNAL": "Yevmiye numaralama durumu — son yevmiye no ve tarihi",
    "KSDISTDETLINES": "Kasa masraf dağıtım satırları",
    # toplamlar
    "GNTOTCL": "Cari hesap genel toplamları",
    "GNTOTST": "Malzeme genel toplamları — planlanan giriş/çıkış",
    "GNTOTVRNT": "Varyant genel toplamları — planlanan giriş/çıkış",
    "VRNTINVENS": "Varyant ambar aylık alım/satış toplamları",
    # stok ve üretim
    "INVENVAL": "Stok değerleme fişi — maliyet yöntemi ve muhasebe hesapları",
    "INVENVALLN": "Stok değerleme satırları",
    "STLINECOST": "Malzeme hareketinin maliyet bileşenleri (malzeme, işçilik, GÜG)",
    "DISPLINECOST": "İş emri maliyet bileşenleri",
    "PACKAGEFICHE": "Paketleme fişleri — brüt/net ağırlık",
    "PACKAGEFCLN": "Paketleme fişi satırları",
    "PACKAGEASGN": "Paket - hareket ataması",
    # sipariş ve kampanya
    "ORDPEGGING": "Sipariş karşılama eşleştirmesi",
    "ORDCMPRICE": "Sipariş kampanya fiyatları",
    "ORDCMFINTRANS": "Sipariş kampanya hareketleri",
    # cari ve tahsilat
    "INSTALCARD": "Taksit kartları — vade, kefil ve seri bilgileri",
    "DISCPAYLINES": "Ödeme planı iskonto satırları",
    "REMINDHIST": "Borç hatırlatma geçmişi — gönderim tarihi ve seviyesi",
    # tanım ve sistem
    "APPROVEUSER": "Onay kullanıcıları",
    "BARCODETMP": "Barkod şablonları",
    "CHARSETASGN": "Özellik seti ataması",
    "LABELS": "Etiket tanımları",
    "PLUGINS": "Eklenti (plugin) tanımları",
    "PROCESSLOG": "İşlem günlüğü — çalıştırılan işlemler ve sonuçları",
    "MBSCRMRELP": "CRM ilişki kayıtları",
    "DIVAMAIN": "DIVA veri aktarım tanımları",
}

#: Logo's table-naming grammar. What a suffix says about a table is consistent across three hundred
#: of them, so a table that was never described is still not anonymous.
_SUFFIX: list[tuple[str, str]] = [
    ("FICHE", "{} fişleri"), ("FCHE", "{} fişleri"),
    ("LINES", "{} satırları"), ("LINE", "{} satırları"), ("LN", "{} satırları"),
    ("TOTALS", "{} toplamları"), ("TOTS", "{} toplamları"), ("TOT", "{} toplamları"),
    ("PARAMS", "{} parametreleri"), ("PARAM", "{} parametreleri"),
    ("HISTORY", "{} geçmişi"), ("HIST", "{} geçmişi"),
    ("CARD", "{} kartları"), ("CARDS", "{} kartları"),
    ("DEF", "{} tanımları"), ("DEFS", "{} tanımları"),
    ("ASGN", "{} ataması"), ("REL", "{} ilişkisi"), ("REF", "{} referansları"),
    ("TRANS", "{} hareketleri"), ("TRAN", "{} hareketleri"),
    ("EXCH", "{} döviz tutarları"), ("TEMP", "{} şablonu"),
]

#: The words the suffix is attached to.
_STEM: dict[str, str] = {
    "CL": "Cari hesap", "CLIENT": "Cari hesap", "ST": "Malzeme", "ITM": "Malzeme", "ITEM": "Malzeme",
    "INV": "Fatura", "INVOICE": "Fatura", "ORD": "Sipariş", "ORF": "Sipariş", "BN": "Banka",
    "KS": "Kasa", "CS": "Çek/senet", "EM": "Muhasebe", "EMUH": "Muhasebe", "ACC": "Muhasebe",
    "FA": "Sabit kıymet", "PR": "Fiyat", "PRC": "Fiyat", "SRV": "Hizmet", "WS": "İş istasyonu",
    "PROD": "Üretim", "BOM": "Ürün reçetesi", "DIST": "Dağıtım", "PAY": "Ödeme", "EXIM": "Dış ticaret",
    "TAX": "Vergi", "TAXDECL": "Beyanname", "DEMAND": "Talep", "COLLATRL": "Teminat",
    "APPROVAL": "Onay", "CAMP": "Kampanya", "CAMPAIGN": "Kampanya", "EBOOK": "e-Defter",
    "EARCHIVE": "e-Arşiv", "EINVOICE": "e-Fatura", "WF": "İş akışı", "WFLOW": "İş akışı",
    "USER": "Kullanıcı", "SLS": "Satış temsilcisi", "PER": "Personel", "EMP": "Çalışan",
    "SUPP": "Tedarikçi", "PROJ": "Proje", "PROJECT": "Proje", "CASHFLOW": "Nakit akış",
}


def describe(entity: str) -> tuple[str, str]:
    """(text, why) for one table — the written reading first, the naming grammar after it."""
    n = entity.upper()
    if text := NAMED.get(n):
        return text, "yazılmış tanım"
    for suffix, shape in _SUFFIX:
        if n.endswith(suffix) and len(n) > len(suffix):
            if stem := _STEM.get(n[: -len(suffix)]):
                return shape.format(stem), "adlandırma kalıbı"
    return "", ""


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn)
    profiles = store.list_profiles(s.datasource_id)

    written = pattern = still = 0
    missing: list[str] = []
    changed = []
    for p in profiles:
        if _NOT_A_TABLE.search(p.entity) or (p.description or "").strip():
            continue
        if any(d.get("source") == SOURCE for d in p.derived):
            continue
        text, why = describe(p.entity)
        if not text:
            still += 1
            if p.entity not in missing:
                missing.append(p.entity)
            continue
        p.derived.append({"source": SOURCE, "text": text})
        changed.append(p)
        if why == "yazılmış tanım":
            written += 1
        else:
            pattern += 1

    print(f"yazılmış tanımla açıklanan : {written} profil")
    print(f"adlandırma kalıbıyla       : {pattern} profil")
    print(f"hâlâ açıklamasız           : {still} profil ({len(missing)} farklı tablo)")
    if missing:
        print("   ", ", ".join(sorted(missing)[:20]))
    if not apply:
        print("\n(kuru çalışma — yazmak için --apply)")
        return 0
    for p in changed:
        store.upsert_profile(p)
    print(f"\n{len(changed)} profil güncellendi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
