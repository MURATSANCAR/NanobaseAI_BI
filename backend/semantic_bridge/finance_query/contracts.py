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


METRICS = {
    "sales_amount": Metric("sales", "Satış tutarı", "TRY", "SUM(CASE WHEN f.TRCODE IN (7,8,9) THEN f.LINENET ELSE 0 END)", "Faturalı malzeme satırı, iskonto sonrası KDV hariç; iadeler düşülmeden satış (7/8/9)."),
    "net_sales": Metric("sales", "Net satış tutarı", "TRY", "SUM(CASE WHEN f.TRCODE IN (2,3) THEN -f.LINENET ELSE f.LINENET END)", "Faturalı malzeme satırında satış (7/8/9) eksi iade (2/3); iskonto sonrası KDV hariç."),
    "sold_quantity": Metric("sales", "Satılan adet", "adet", "SUM(CASE WHEN f.TRCODE IN (7,8) THEN f.AMOUNT ELSE 0 END)", "Faturalı malzeme satırı; perakende/toptan 7/8, iadeler düşülmeden miktar; hizmet 9 hariç."),
    "net_quantity": Metric("sales", "Net satılan adet", "adet", "SUM(CASE WHEN f.TRCODE IN (2,3) THEN -f.AMOUNT WHEN f.TRCODE IN (7,8) THEN f.AMOUNT ELSE 0 END)", "Faturalı malzeme; 7/8 miktarı eksi 2/3 iade miktarı."),
    "return_amount": Metric("sales", "İade tutarı", "TRY", "SUM(CASE WHEN f.TRCODE IN (2,3) THEN f.LINENET ELSE 0 END)", "İptal edilmemiş faturalı malzeme iadesi; LINENET, KDV hariç, pozitif gösterim."),
    "invoice_count": Metric("invoice", "Fatura sayısı", "belge", "COUNT_BIG(*)", "İptal edilmemiş satış fatura başlıkları; satırlar değil INVOICE belgeleri (7/8/9)."),
    "invoice_amount": Metric("invoice", "Fatura toplamı", "TRY", "SUM(f.NETTOTAL)", "İptal edilmemiş satış faturası NETTOTAL; fatura toplamı, satır net cirosu değildir."),
    "collections": Metric("collection", "Müşteri ödeme hareketleri", "TRY", "SUM(f.AMOUNT)", "120 müşteri carileri, iptal olmayan alacak hareketleri SIGN=1; nakit/havale/çek/senet/kart (1,20,61,62,70). Çek/senet teslimi dahil, yalnız nakit tahsil değildir."),
    "active_books": Metric("crm_books", "Aktif kitap kaydı", "kayıt", "COUNT_BIG(*)", "CRM kitap kartı statecode=0 ve kurum metadata etiketinde Aktif/Etkin durum nedeni; Pasif etiketli kartlar hariç."),
    "active_authors": Metric("crm_authors", "Aktif yazar kişi kaydı", "kişi", "COUNT_BIG(*)", "CRM kişi kartı statecode=0, Etkin durum nedeni ve new_yazarmi=1; ayrı yazar sözlüğü sayısı değildir."),
    "active_customers": Metric("crm_customers", "Aktif müşteri kaydı", "kayıt", "COUNT_BIG(*)", "CRM AccountBase statecode=0 ve Aktif Müşteri durum nedeni; potansiyel, pasif, arşiv ve sorunlu müşteri statüleri dahil değildir."),
}
DIMENSIONS = {
    "book": "Kitap stok kodu ve adı (aynı adlı farklı kitaplar birleştirilmez)",
    "channel": "Logo müşteri kartı SPECODE2 satış kanalı",
    "customer": "Logo müşteri kartı CODE ve DEFINITION_",
    "author": "Aktif CRM kitap kartındaki new_yazartext künye metni; kişi kimliği veya telif sahibi değildir",
    "publisher": "CRM kitap kartının new_yayineviid ilişkisindeki aktif marka/yayınevi",
    "day": "İşlem günü", "month": "İşlem yılı ve ayı", "year": "İşlem yılı",
}
CONTRACT = {"version": "2.0", "metrics": {k: asdict(v) for k, v in METRICS.items()},
            "dimensions": DIMENSIONS,
            "sources": "Tek şirket. SEMANTIC_FIRMS kapsamı ile L_CAPIPERIOD dönemleri; çakışmada tahmin yok.",
            "joins": "Logo ITEMS.CODE -> CRM new_kitapBase.new_stokkodu; aktif anahtar tekilliği zorunlu. LEFT JOIN; ölçüler çoğalmaz. Eşleşmeyen satışlar NULL CRM alanlarıyla korunur ve toplam kontrol edilir.",
            "family_merge": "Satış/fatura/tahsilat farklı aileleri ortak müşteri/kanal/gün/ay/yıl kırılımında önce ayrı ayrı toplanır, bütün anahtarların birleşimi korunur (FULL OUTER). Yalnız bir ailede hareketi olan kırılım kaybolmaz; diğer ailenin tam okunmuş dönemde olmayan hareketi 0 olur. Ham hareket tabloları birbirine JOIN edilmez.",
            "operations": "Toplulaştırma sonrası açık pay/paydalı oran, fark, yüzde değişim ve hesap sonucu filtresi. Sıfır veya eksik payda NULL; dönem eşleşmesi yoksa değer sıfır varsayılmaz. Limit en son uygulanır."}
CONTRACT_HASH = hashlib.sha256(json.dumps(CONTRACT, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class ContractError(ValueError):
    """The complete requested answer cannot be established under this contract."""

    def __init__(self, message, code="UNSUPPORTED_CAPABILITY"):
        super().__init__(message)
        self.code = code
