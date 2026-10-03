"""Logo kodlu kolonların doğrulanmış anlamları: sözleşme kırılımı ve süzgeci olarak.

Her kayıt canlı veriyle sınandı (2026-10-03, LG_411 ve LG_211; docs/analiz/kolon-eslestirme/):
kodlar ya faturanın kendi e-belge XML'inden (FICHEOBJECT.LDATA, UBL ProfileID/InvoiceTypeCode),
ya kolonun başka bir alanla birebir örtüşmesinden, ya da yayımlanmış kod listesinden (GİB, Logo)
geldi. Burada yalnız emin olunan kodlar var; listede olmayan kod «diğer» diye gösterilir, tahmin
edilmez. Model kod ya da kolon seçemez: yalnız kırılım kimliği ve sorudaki değeri verir.
"""
from .contracts import ContractError
from .language import fold

# İade (14) ve harici iptal (23) durumları sözlükte etiketle görünür ama süzgeç kelimesi değildir:
# «iade/iptal edilen faturalar» iade faturası ve iptal edilmiş fatura demektir, e-belge durumu değil.


class Coded:
    def __init__(self, label, level, column, codes, aliases, other="Diğer kod", text=False, label_only=()):
        self.label, self.level, self.column = label, level, column
        self.codes, self.aliases, self.other, self.text = codes, aliases, other, text
        self.label_only = set(label_only)        # etiketiyle gösterilir, süzgeç kelimesi olarak eşlenmez

    def expression(self, alias):
        """Kodun Türkçe karşılığını üreten SQL; bilinmeyen kod «diğer (kod)» olarak görünür."""
        col = f"{alias}.{self.column}"
        if self.text:
            col = f"LTRIM(RTRIM(ISNULL({col},'')))"
        whens = " ".join(f"WHEN {col}={self._sql(c)} THEN N'{t.replace("'", "''")}'" for c, t in self.codes.items())
        tail = f"N'{self.other} (' + CAST({col} AS nvarchar(20)) + N')'"
        return f"CASE {whens} ELSE {tail} END"

    def _sql(self, code):
        return "N'" + code + "'" if self.text else str(code)

    def words(self):
        """Kod kümesini anan kelimeler: etiketler (süzgeç dışı olanlar hariç) ve eş anlamlılar."""
        out = {}
        for c, t in self.codes.items():                   # etiketin kendisi de bir kelimedir (2 ve 3 ikisi de e-Arşiv)
            if c not in self.label_only:
                out.setdefault(fold(t), set()).add(c)
        for w, m in self.aliases.items():
            out.setdefault(fold(w), set()).update(m)
        return out

    def codes_for(self, op, value):
        """Sorudaki değeri bilinen kodlara çevirir; eşleşmeyen değerle hesap yapılmaz."""
        wanted, words = fold(value), self.words()
        codes = set(words.get(wanted, ()))          # tam eşleşme önce: «mükellefi değil» «mükellefi»ni de içerir
        if not codes:
            # Değerin içinde geçen kelimelerden yalnız en uzunları: «e-fatura mükellefi olmayan» içindeki
            # «e-fatura mükellefi» olumlu koda gitmesin. İçerme (contains) ayrıca değeri içeren kelimeyi de alır.
            hits = [w for w in words if w and (w in wanted or (op == "contains" and wanted in w))]
            for word in hits:
                if not any(word != other and word in other for other in hits):
                    codes |= words[word]
        if not codes:
            raise ContractError(f"«{value}» değeri {self.label} kırılımının doğrulanmış kodlarından biri değil.")
        return codes

    def asked(self, codes, question):
        """Seçilen kodlardan birini anan bir kelime soruda geçiyor mu (modelin uydurduğu değere karşı)."""
        q = fold(question)
        return any(word and word in q and matched & codes for word, matched in self.words().items())

    def predicate(self, alias, op, value):
        codes = self.codes_for(op, value)
        col = f"{alias}.{self.column}"
        if self.text:
            col = f"LTRIM(RTRIM(ISNULL({col},'')))"
        return f"{col} IN (" + ",".join(self._sql(c) for c in sorted(codes)) + ")"


_EDOC = {0: "Kağıt fatura", 1: "e-Fatura", 2: "e-Arşiv fatura", 3: "e-Arşiv fatura"}
_SCENARIO = {1: "Temel fatura", 2: "Ticari fatura", 0: "Senaryo seçilmemiş"}
# logoyazilimdestek.com «e-belgelerin veritabanı statü karşılıkları»; e-Arşiv faturada ESTATUS 2 yazılır.
_STATUS = {0: "GİB'e gönderilecek", 1: "Onay gönderildi", 2: "Onaylandı", 3: "Paketlendi", 4: "GİB'e gönderildi",
           5: "GİB'e gönderilemedi", 6: "GİB'de işlendi", 7: "GİB'de işlenemedi", 8: "Alıcıya gönderildi",
           9: "Alıcıya gönderilemedi", 10: "Alıcıda işlendi", 11: "Alıcıda işlenemedi", 12: "Kabul edildi",
           13: "Reddedildi", 14: "İade edildi", 19: "Alındı", 22: "Sunucuya gönderildi", 23: "Harici yollardan iptal edildi"}
# GİB KDV istisna kodları; TİMAŞ satışlarının çoğu 335 (basılı kitap). Boş = istisna kodu girilmemiş.
_VAT = {"335": "Basılı kitap ve süreli yayın teslimi (335)", "301": "Mal ihracatı (301)",
        "302": "Hizmet ihracatı (302)", "351": "İstisna olmayan diğer (351)", "350": "Diğer istisnalar (350)",
        "": "İstisna kodu yok"}

CODED = {
    "e_document": Coded(
        "belge türü",
        "invoice", "EINVOICE", _EDOC,
        {"kağıt": (0,), "kağıt fatura": (0,), "e-fatura": (1,), "efatura": (1,), "e fatura": (1,),
         "e-arşiv": (2, 3), "earşiv": (2, 3), "e arşiv": (2, 3), "e-arşiv fatura": (2, 3)}),
    "einvoice_scenario": Coded(
        "e-Fatura senaryosu",
        "invoice", "PROFILEID", _SCENARIO,
        {"temel": (1,), "temel fatura": (1,), "ticari": (2,), "ticari fatura": (2,)}),
    "einvoice_status": Coded(
        "e-belge durumu",
        "invoice", "ESTATUS", _STATUS,
        {"reddedildi": (13,), "reddedilen": (13,), "kabul edildi": (12,), "kabul edilen": (12,),
         "gönderilemedi": (5, 9), "gönderilemeyen": (5, 9), "işlenemedi": (7, 11), "işlenemeyen": (7, 11),
         "gönderilecek": (0,), "gönderilmeyi bekleyen": (0,)}, other="Diğer durum", label_only=(14, 23)),
    "vat_exemption": Coded(
        "KDV istisnası",
        "line", "VATEXCEPTCODE", _VAT,
        {"basılı kitap": ("335",), "kitap istisnası": ("335",), "335": ("335",), "ihracat": ("301", "302"),
         "mal ihracatı": ("301",), "hizmet ihracatı": ("302",), "istisnasız": ("",), "istisna kodu yok": ("",)},
        other="Diğer istisna kodu", text=True),
    "customer_einvoice_user": Coded(
        "müşteri e-Fatura mükellefi mi",
        "client", "ACCEPTEINV", {1: "e-Fatura mükellefi", 0: "e-Fatura mükellefi değil"},
        {"e-fatura mükellefi": (1,), "mükellef": (1,), "evet": (1,), "e-fatura mükellefi değil": (0,),
         "e-fatura mükellefi olmayan": (0,), "mükellefi olmayan": (0,), "mükellefi değil": (0,),
         "mükellef olmayan": (0,), "mükellef değil": (0,), "hayır": (0,)}),
    "customer_legal_form": Coded(
        "müşteri şahıs mı şirket mi",
        "client", "ISPERSCOMP", {1: "Şahıs", 0: "Şirket"},
        {"şahıs": (1,), "bireysel": (1,), "gerçek kişi": (1,), "şirket": (0,), "tüzel": (0,), "kurumsal": (0,)}),
}


def sql_alias(dim, family):
    """Kodlu kırılımın bu ailede hangi tablo takma adından okunduğu; okunamıyorsa hata."""
    level = CODED[dim].level
    if level == "client":
        return "c"
    if family == "invoice":
        return "f"                       # fatura ailesinde satır f fatura başlığıdır
    if family == "sales":
        return "h" if level == "invoice" else "f"
    raise ContractError(f"{CODED[dim].label} kırılımı bu ölçünün kayıt düzeyinde yok.")


def columns(dim, family, firm, period):
    """Şema doğrulaması için okunan tablo ve kolon."""
    level = CODED[dim].level
    table = (f"LG_{firm}_CLCARD" if level == "client" else
             f"LG_{firm}_{period}_INVOICE" if level == "invoice" or family == "invoice" else f"LG_{firm}_{period}_STLINE")
    return table, CODED[dim].column
