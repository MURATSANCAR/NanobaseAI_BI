"""Versioned business definitions. A model selects IDs; it cannot supply SQL or columns.

These are deployment contracts, not claims that a successful SELECT proves accounting
acceptance. Independent live references and the exact contract hash travel with each run.
"""
from dataclasses import asdict, dataclass
import hashlib
import json


@dataclass(frozen=True)
class Metric:
    family: str
    label: str
    unit: str
    expression: str
    definition: str


# Sales amounts: user decision 2026-10-01 — the accounting net is the line VAT base (VATMATRAH):
# it carries invoice-level discounts that Logo keeps on separate discount lines (414 invoices in
# 2026; LINENET misses them) and sums exactly to the invoice header. The period of a sales line is
# its invoice date, not the line (dispatch) date: books, VAT returns and TİMAŞ's own sales report
# use the invoice date.
# One invoice definition for the whole engine. User decision 2026-10-01: an invoice
# count is sales invoices only (retail 7, wholesale 8, service 9); sales return
# invoices (retail 2, wholesale 3) are a separate measure, added only on request.
SALES_INVOICE_CODES = (7, 8, 9)
RETURN_INVOICE_CODES = (2, 3)


def codes_sql(codes):
    return "(" + ",".join(map(str, sorted(codes))) + ")"


METRICS = {
    "sales_amount": Metric("sales", "Satış tutarı", "TRY", "SUM(CASE WHEN f.TRCODE IN (7,8,9) THEN f.VATMATRAH ELSE 0 END)", "Faturalı malzeme satırının KDV matrahı: satır ve fatura geneli iskonto sonrası, KDV hariç; iadeler düşülmeden satış (7/8/9); dönem fatura tarihine göre."),
    "net_sales": Metric("sales", "Net satış tutarı", "TRY", "SUM(CASE WHEN f.TRCODE IN (2,3) THEN -f.VATMATRAH ELSE f.VATMATRAH END)", "Faturalı malzeme satırının KDV matrahında satış (7/8/9) eksi iade (2/3); satır ve fatura geneli iskonto sonrası, KDV hariç; dönem fatura tarihine göre."),
    "sold_quantity": Metric("sales", "Satılan adet", "adet", "SUM(CASE WHEN f.TRCODE IN (7,8) THEN f.AMOUNT ELSE 0 END)", "Faturalı malzeme satırı; perakende/toptan 7/8, iadeler düşülmeden miktar; hizmet 9 hariç."),
    "net_quantity": Metric("sales", "Net satılan adet", "adet", "SUM(CASE WHEN f.TRCODE IN (2,3) THEN -f.AMOUNT WHEN f.TRCODE IN (7,8) THEN f.AMOUNT ELSE 0 END)", "Faturalı malzeme; 7/8 miktarı eksi 2/3 iade miktarı."),
    "return_amount": Metric("sales", "İade tutarı", "TRY", "SUM(CASE WHEN f.TRCODE IN (2,3) THEN f.VATMATRAH ELSE 0 END)", "İptal edilmemiş faturalı malzeme iadesi; KDV matrahı (iskonto sonrası, KDV hariç), pozitif gösterim; dönem fatura tarihine göre."),
    "accounting_net_sales": Metric("ledger", "Muhasebe net satışı", "TRY", "SUM(f.CREDIT-f.DEBIT) [600-602, 610-612]", "Muhasebe fiş satırları (EMFLINE, iptal olmayan fiş): 600-602 brüt satış hesaplarının alacak-borç bakiyesi ile 610-612 satış indirim ve iade hesaplarının bakiyesi toplamı; gelir tablosu net satışı. Hizmet satışı, kargo ve diğer satış gelirleri ile iskonto fiyat farkları dahil; dönem sonu kapanış (FINANCE_CLOSE_ACCOUNTS) ve yansıtma (7x1) hesabı içeren fişler hariç (M45 kuralı); dönem fiş satırı tarihine göre; yalnız gün/ay/yıl kırılımı."),
    "invoice_count": Metric("invoice", "Fatura sayısı", "belge", "SUM(CASE WHEN f.TRCODE IN (7,8,9) THEN 1 ELSE 0 END)", "İptal edilmemiş satış faturası başlıkları (perakende, toptan, hizmet); satış iadesi faturaları dahil değildir. Satırlar değil fatura belgeleri sayılır (7/8/9)."),
    "return_invoice_count": Metric("invoice", "İade faturası sayısı", "belge", "SUM(CASE WHEN f.TRCODE IN (2,3) THEN 1 ELSE 0 END)", "İptal edilmemiş satış iadesi faturası başlıkları (perakende ve toptan iade); fatura sayısına dahil edilmez (2/3)."),
    "invoice_count_with_returns": Metric("invoice", "Fatura sayısı (iadeler dahil)", "belge", "SUM(CASE WHEN f.TRCODE IN (2,3,7,8,9) THEN 1 ELSE 0 END)", "Satış faturası sayısı ile satış iadesi faturası sayısının toplamı; yalnız iadeler açıkça istendiğinde kullanılır (2/3/7/8/9)."),
    "invoice_amount": Metric("invoice", "Fatura toplamı", "TRY", "SUM(CASE WHEN f.TRCODE IN (7,8,9) THEN f.NETTOTAL ELSE 0 END)", "İptal edilmemiş satış faturası NETTOTAL; iade faturaları düşülmez, fatura toplamı satır net cirosu değildir."),
    "collections": Metric("collection", "Müşteri ödeme hareketleri", "TRY", "SUM(f.AMOUNT)", "120 müşteri carileri, iptal olmayan alacak hareketleri SIGN=1; nakit/havale/çek/senet/kart (1,20,61,62,70). Çek/senet teslimi dahil, yalnız nakit tahsil değildir."),
    "active_books": Metric("crm_books", "Aktif kitap kaydı", "kayıt", "COUNT_BIG(*)", "CRM kitap kartı statecode=0 ve kurum metadata etiketinde Aktif/Etkin durum nedeni; Pasif etiketli kartlar hariç."),
    "active_authors": Metric("crm_authors", "Aktif yazar kişi kaydı", "kişi", "COUNT_BIG(*)", "CRM kişi kartı statecode=0, Etkin durum nedeni ve new_yazarmi=1; ayrı yazar sözlüğü sayısı değildir."),
    "active_customers": Metric("crm_customers", "Aktif müşteri kaydı", "kayıt", "COUNT_BIG(*)", "CRM AccountBase statecode=0 ve Aktif Müşteri durum nedeni; potansiyel, pasif, arşiv ve sorunlu müşteri statüleri dahil değildir."),
}
# Logo transaction types each metric reads; the executor's TRCODE scope is their union.
TRANSACTION_CODES = {
    "sold_quantity": {7, 8}, "net_quantity": {2, 3, 7, 8}, "sales_amount": {7, 8, 9},
    "net_sales": {2, 3, 7, 8, 9}, "return_amount": {2, 3},
    "invoice_count": set(SALES_INVOICE_CODES), "invoice_amount": set(SALES_INVOICE_CODES),
    "return_invoice_count": set(RETURN_INVOICE_CODES),
    "invoice_count_with_returns": set(SALES_INVOICE_CODES) | set(RETURN_INVOICE_CODES),
}
DIMENSIONS = {
    "book": "Kitap stok kodu ve adı (aynı adlı farklı kitaplar birleştirilmez)",
    "channel": "Logo müşteri kartı SPECODE2 satış kanalı",
    "customer": "Logo müşteri kartı CODE ve DEFINITION_",
    "author": "Aktif CRM kitap kartındaki new_yazartext künye metni; kişi kimliği veya telif sahibi değildir",
    "publisher": "CRM kitap kartının new_yayineviid ilişkisindeki aktif marka/yayınevi",
    "subbrand": "CRM new_yayinciid aktif Marka kimliği ve adı; alternatif new_YayneviAltMarka değildir",
    "author_group": "Aktif Yazar katılım rolüyle bağlı gerçek kişi UUID kümesi; ortak yazarlı kitabın satışı kümede bir kez sayılır, kişilere dağıtılmaz",
    "day": "İşlem günü (satışta fatura tarihi)", "month": "İşlem yılı ve ayı (satışta fatura tarihi)", "year": "İşlem yılı (satışta fatura tarihi)",
    # Logo kodlu alanlar (logo_codes.CODED): kodların anlamı canlı veriyle doğrulandı 2026-10-03.
    "e_document": "Belge türü / kesiliş biçimi (fatura tipi DEĞİL): Kağıt fatura, e-Fatura ya da e-Arşiv fatura (Logo fatura başlığı EINVOICE)",
    "einvoice_scenario": "e-Faturanın GİB senaryosu: Temel fatura ya da Ticari fatura (fatura başlığı PROFILEID)",
    "einvoice_type": "Fatura tipi (GİB fatura tipi; «fatura tipine göre» bu kırılımdır): Satış, İstisna ya da Tevkifat (fatura başlığı EINVOICETYP; KDV istisna kodundan ayrı, fatura düzeyinde)",
    "einvoice_status": "Faturanın e-Fatura/e-Arşiv gönderim durumu: Onaylandı, Alıcıda işlendi, Kabul edildi, Reddedildi, GİB'e gönderilemedi… (fatura başlığı ESTATUS)",
    "vat_exemption": "GİB KDV istisna kodu: 335 basılı kitap ve süreli yayın teslimi, 301 mal ihracatı, 302 hizmet ihracatı, 351 istisna olmayan diğer (satışta satır, fatura sayısında fatura başlığı VATEXCEPTCODE)",
    "customer_einvoice_user": "Müşterinin e-Fatura mükellefi olup olmadığı (Logo cari kartı ACCEPTEINV)",
    "customer_legal_form": "Müşterinin şahıs (TC kimlik no) ya da şirket (vergi no) olduğu (Logo cari kartı ISPERSCOMP)",
}
# Logo kodlu kırılım ve süzgeçler; hangi kayıt düzeyinde okundukları logo_codes.CODED'da.
CODED_DIMENSIONS = ("e_document", "einvoice_scenario", "einvoice_type", "einvoice_status", "vat_exemption",
                    "customer_einvoice_user", "customer_legal_form")
CONTRACT = {"version": "2.5", "metrics": {k: asdict(v) for k, v in METRICS.items()},
            "dimensions": DIMENSIONS,
            "sources": "Tek şirket. SEMANTIC_FIRMS kapsamı ile L_CAPIPERIOD dönemleri; çakışmada tahmin yok.",
            "joins": "Logo ITEMS.CODE -> CRM new_kitapBase.new_stokkodu; aktif anahtar tekilliği zorunlu; alt marka/kişi grubu kırılımında çoğul kodlar eşleştirilmeden NULL ve kapsam açıklamasıyla korunur. LEFT JOIN; ölçüler çoğalmaz. Eşleşmeyen satışlar NULL CRM alanlarıyla korunur ve toplam kontrol edilir.",
            "family_merge": "Satış/fatura/tahsilat farklı aileleri ortak müşteri/kanal/gün/ay/yıl kırılımında önce ayrı ayrı toplanır, bütün anahtarların birleşimi korunur (FULL OUTER). Yalnız bir ailede hareketi olan kırılım kaybolmaz; diğer ailenin tam okunmuş dönemde olmayan hareketi 0 olur. Ham hareket tabloları birbirine JOIN edilmez.",
            "operations": "Toplulaştırma sonrası açık pay/paydalı oran, fark, yüzde değişim ve hesap sonucu filtresi. Sıfır veya eksik payda NULL; dönem eşleşmesi yoksa değer sıfır varsayılmaz. Limit en son uygulanır."}
CONTRACT_HASH = hashlib.sha256(json.dumps(CONTRACT, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ContractError(ValueError):
    """The complete requested answer cannot be established under this contract."""

    def __init__(self, message, code="UNSUPPORTED_CAPABILITY"):
        super().__init__(message)
        self.code = code
