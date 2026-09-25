"""Yeni Baskı Öneri raporu — Power BI şablonunun ("2025_Yeni_Baskı Öneri Raporu") köprüdeki karşılığı.

Mevcut rapor modeli Logo ve CRM tablolarını bellekte ilişkiyle birleştiriyordu. Burada da öyle: Logo ile
CRM ayrı SQL sunucularında durduğu için tek sorguda birleşemezler; her kaynak kendi sorgusuyla okunur,
birleştirme ve DAX hesapları aşağıda stok koduna göre yapılır.

Mevcut rapordan bilinçli farklar `NOTES` içinde; ekranda da gösterilir.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any, Callable

REPORT_ID = "baski-oneri"
TITLE = "Yeni Baskı Öneri"
DESCRIPTION = "Stok kaç ay yeter, hangi kitap yeniden basılmalı: satış hızı, stok, bekleyen sipariş ve öneri."

# Power BI görsel süzgeçleri: bu yayınevleri raporda gösterilmiyordu.
EXCLUDED_PUBLISHERS = {
    "tekrar": {"Bi Kutu Oyun", "Dikkat ve Zeka Akademisi", "Sincap Kids", "Sincap Kitap", "Uçan Kitap",
               "Bir Ocak Eğitim Yayıncılığı A. Ş.", "Ticari Ürünler"},
    "yeni": {"Bi Kutu Oyun", "Bir Ocak Eğitim Yayıncılığı A. Ş.", "Gülce Kids", "Gülce Kinder", "Karizma",
             "L&M", "Lacivert", "Mavi Kirpi Kitap", "Sincap Kids", "Sincap Kitap", "Uçan Kitap"},
}

# Power BI dosyasında kayıtlı dilimleyici seçimi: rapor bu iki süzgeç seçili açılıyordu.
# Ekranda kaldırılabilir çip olarak durur; kaldırılınca havuzun tamamı görünür (boş değer = None).
DEFAULT_FILTERS = {
    "tekrar": [
        {"key": "statu", "values": [None, "YS04 Aktif",
                                    "YS10A Ürün Fazlası - Stok Eritilecek Ürün (Yeniden Basılabilir)"]},
        {"key": "baski_durum", "values": [None, "Depo Girişi Yapıldı"]},
    ],
    "yeni": [],
}

# Ağırlıklı satış hızı: son çeyrek en ağır, geçen yılın aynı çeyreği mevsimsellik için ikinci.
WEIGHTS = [("ceyrek1_ort", 0.50), ("ceyrek2_ort", 0.10), ("ceyrek3_ort", 0.05), ("ceyrek4_ort", 0.20),
           ("son6_ort", 0.05), ("onceki6_ort", 0.05), ("yillik_ort", 0.05)]

# (id, bağlantı, başlık, açıklama)
SOURCES = [
    ("logo_satis_hizi", "logo", "Satış hızı", "Stok kodu başına son 12 ayın dönemsel satışı (çeyrekler, 6 aylar, yıl)."),
    ("logo_aylik_satis", "logo", "Aylık satış", "Son 12 ay, stok kodu × ay satış adedi."),
    ("logo_fiyat", "logo", "Fiyat listesi", "Güncel fiyat ve fiyatın başladığı tarih."),
    ("logo_depo_stok", "logo", "Depo stoku", "Logo depo stok toplamı (157 kodlar hariç)."),
    ("crm_kitap", "crm", "Kitap kartı", "CRM kitap bilgisi, CRM stoku ve son baskı ayrıntısı."),
    ("crm_bekleyen_siparis", "crm", "Bekleyen sipariş", "Açık sipariş satırlarının stok kodu başına adedi."),
    ("crm_baski_onerisi", "crm", "Baskı önerileri", "Son 30 günde CRM'e girilen baskı önerileri."),
    ("crm_yeni_kitap", "crm", "Yeni kitaplar", "İlk yayını son 12 ay içinde olan kitaplar."),
    ("logo_yeni_kitap_satis", "logo", "Yeni kitap satışı", "Yeni kitapların gün bazında satışı."),
]

# (kaynak, anlatım) — ekranda "nasıl hesaplandı" bölümü
FORMULAS = [
    ("Ort. satış hızı", "0,50 × son 3 ay ort. + 0,20 × 10–12 ay önce ort. + 0,10 × 4–6 ay önce ort. + 0,05 × 7–9 ay önce ort. + 0,05 × son 6 ay ort. + 0,05 × önceki 6 ay ort. + 0,05 × yıllık ort. (aylık adet)"),
    ("Tükenme süresi", "CRM stok adedi ÷ ort. satış hızı — stok kaç ay yeter"),
    ("Marj", "Tükenme süresi − 1; satışı olmayan kitapta bölen yoktur, marj boş kalır"),
    ("Öneri", "Marj ≤ 0 → Risk/Acil · ≤ 0,5 → Kritik · ≤ 1 → Karar Ver · ≤ 1,5 → Takip Et · üstü → Yeterli Stok. "
              "Satışı olmayan kitap stoku varsa Yeterli Stok, stoku da yoksa Risk/Acil sayılır."),
    ("Satış süresi (yeni kitap)", "İlk yayından bugüne geçen ay sayısı"),
    ("Son 1 yıl ort. (yeni kitap)", "Son 12 ay satışı ÷ satış süresi"),
    ("Dağılım satışı", "İlk yayın ayındaki satış (ilk dağıtım)"),
    ("Tekrar sipariş (RPT)", "İlk yayından 1 ay sonrasından bugüne satış; hızı ÷ satış süresi"),
    ("Satış hızı tahmini (yeni kitap)", "0,4 × son 1 yıl ort. + 0,6 × RPT hızı"),
    ("Marj / Öneri (yeni kitap)", "Stok adedi ÷ son 1 yıl ort. − 1; öneri eşikleri yukarıdakiyle aynı"),
]

NOTES = [
    "Rapor, mevcut raporun açılış görünümüyle aynı süzgeçlerle açılır: statü boş, YS04 Aktif ya da "
    "YS10A Ürün Fazlası; baskı durumu boş ya da Depo Girişi Yapıldı. Çipler kaldırılınca havuzun tamamı görünür.",
    "Satış hızı havuzu mevcut raporla aynı: 2024 başından bu yana satışı olan her kitap listede. Son 12 ayda "
    "hiç satmayan kitap da kalır; hızı 0, tükenmesi boş, önerisi \u201cYeterli Stok\u201d olur.",
    "Marj ve öneri, bölen olmadığında mevcut raporun DAX davranışını izler: stok varken sonuç sonsuzdur ve "
    "\u201cYeterli Stok\u201d yazar, stok da yokken boş sonuç \u22121 sayılır ve \u201cRisk/Acil\u201d yazar.",
    "Logo ve CRM ayrı sunucularda olduğu için mevcut rapordaki bellek içi ilişki burada stok koduyla birleştirmedir; sonuç aynı satırlardır.",
    "Dönemler tamamlanmış aylardır ve tarih karşılaştırması ay başına göre yapılır; mevcut rapordaki 'gün sonu' karşılaştırması saatli faturaları son günden düşürebiliyordu.",
    "Mevcut raporda 'Ilk6Ay' en yeni 6 ayı, 'Son6Ay' eski 6 ayı tutuyordu; burada 'Son 6 ay' ve 'Önceki 6 ay' olarak doğru adlarıyla gösterilir.",
    "Yeni kitap ay kolonları mevcut rapordaki gibi ay numarasıyladır ve geçen yıl ile bu yılın aynı ayını toplar "
    "(ör. Eylül = Eylül 2025 + Eylül 2026). Mevcut rapor yılları 2025–2026 diye sabit yazıyordu; burada iki yıl "
    "bugünden kurulur. Baskı Tekrar'ın ay kolonları ise son 12 takvim ayıdır, mevcut rapordaki gibi.",
    "Yeni kitaplarda ilk yayın tarihi CRM'den, satış Logo'dan okunur (mevcut rapor bağlı sunucu üzerinden tek sorguda birleştiriyordu).",
    "Mevcut rapor satış hızını satır satır kayan noktayla toplar; sıfır olması gereken hız −3·10⁻¹⁷, 0,5 olması "
    "gereken hız 0,49999999999999994 çıkabilir ve öneri eşiği yanlış taraftan geçer. Burada önce toplanıp "
    "sonra bölünür; 2026-09-23 karşılaştırmasında 5.053 kitabın 2'sinde öneri bu yüzden farklıdır.",
    "Kullanılmayan 'CRM_BekleyenSiparis' tablosu ve kırık 'Set Kitaplar' sayfası (modelde olmayan tabloya bağlı) alınmadı.",
    "Logo satışı mevcut raporda 'V_SatisRaporu_ALL2' (2015'ten bu yana her yılın birleşimi) ve onun üstündeki "
    "'PBI_FiyatList' görünümlerinden okunuyordu. Burada aynı satırlar yalnız gereken yılların görünümlerinden "
    "okunur: satış hızı 2024'ten, fiyat 2025'ten, aylık ve yeni kitap satışı geçen yıldan bu yana. ALL2 üzerinden "
    "fiyat sorgusu 15 dakikada bitmiyordu; yıllık görünümlerle üç yıl 25 saniyede okunuyor.",
    "Yeni kitap satışı mevcut raporda 'V_SatisRaporu_2025_2026' görünümünden okunuyordu; burada geçen yıl ve bu yılın "
    "yıllık görünümleri okunur, satır kümesi aynıdır.",
]

# Kolon tanımları Power BI şablonundaki tablo görselinden birebir alınmıştır (2025_Yeni_Baskı Öneri Raporu):
# başlık = görseldeki ad, biçim = modeldeki biçim dizesi, toplam = görselin toplam satırı.
#   biçim: text · n0 (#,0) · plain (0) · general (biçimsiz ondalık) · date (Short Date) · oneri
#   toplam: "sum" (Toplam) · "tukenme" (ölçü: Σstok ÷ Σhız) · None (Power BI toplamda boş bırakır)
# key, başlık, grup, biçim, kaynak, toplam
TEKRAR_COLUMNS = [
    ("stok_kodu", "StokKodu", "Kitap", "text", "crm_kitap", None),
    ("urun_adi", "Ürün Adı", "Kitap", "text", "crm_kitap", None),
    ("statu", "Statü", "Kitap", "text", "crm_kitap", None),
    ("yazar", "Yazar", "Kitap", "text", "crm_kitap", None),
    ("yayinevi", "Yayınevi", "Kitap", "text", "crm_kitap", None),
    ("kitaplik", "Kitaplık", "Kitap", "text", "crm_kitap", None),
    ("dizi_tur", "Dizi_Tür", "Kitap", "text", "crm_kitap", None),
    ("sayfa_sayisi", "SayfaSayısı", "Kitap", "plain", "crm_kitap", None),
    ("uzeri_fiyat", "Üzeri_Fiyat", "Kitap", "general", "crm_kitap", None),
    ("baski_durum", "Baskı_Durum", "Baskı", "text", "crm_kitap", None),
    ("son_baski_tarihi", "SonBaskıTarihi", "Baskı", "date", "crm_kitap", None),
    ("son_fiyat_degisikligi", "Son Fiyat Değişiklik", "Baskı", "date", "logo_fiyat", None),
    ("baski_adet", "Baskı_Adet", "Baskı", "n0", "crm_kitap", None),
    ("stok_adedi", "StokAdedi", "Stok ve talep", "n0", "crm_kitap", "sum"),
    ("depo_stok", "Toplam Stok", "Stok ve talep", "n0", "logo_depo_stok", "sum"),
    ("bekleyen_siparis", "Bekleyen Sipariş", "Stok ve talep", "n0", "crm_bekleyen_siparis", "sum"),
    ("oneri_adet", "Öneri Adet", "Stok ve talep", "plain", "crm_baski_onerisi", "sum"),
    ("yillik_toplam", "YillikToplami", "Satış hızı", "n0", "logo_satis_hizi", None),
    ("ort_satis_hizi", "OrtSatisHizi", "Satış hızı", "n0", "hesap:Ort. satış hızı", None),
    ("yillik_ort", "YillikToplamiOrt", "Satış hızı", "n0", "logo_satis_hizi", None),
    ("tukenme_suresi", "Tükenme Süresi", "Satış hızı", "general", "hesap:Tükenme süresi", "tukenme"),
    ("marj", "Marj", "Satış hızı", "general", "hesap:Marj", None),
    ("oneri", "Öneri", "Satış hızı", "oneri", "hesap:Öneri", None),
    ("son6_ort", "Ilk6AyOrt", "Satış hızı", "n0", "logo_satis_hizi", None),
    ("onceki6_ort", "Son6AyOrt", "Satış hızı", "n0", "logo_satis_hizi", None),
    ("ceyrek1_ort", "Ceyrek1Ort", "Satış hızı", "n0", "logo_satis_hizi", None),
    ("ceyrek2_ort", "Ceyrek2Ort", "Satış hızı", "n0", "logo_satis_hizi", None),
    ("ceyrek3_ort", "Ceyrek3Ort", "Satış hızı", "n0", "logo_satis_hizi", None),
    ("ceyrek4_ort", "Ceyrek4Ort", "Satış hızı", "n0", "logo_satis_hizi", None),
]
# Şablonun Yeni Kitap görselinde CRM_YeniKitapDetay alanlarının adı sonuna "1" almış hâlde (Power BI aynı adlı
# CRM_KitapDetay alanlarından ayırmak için ekler); başlıklar görseldeki gibidir.
YENI_COLUMNS = [
    ("stok_kodu", "Malzeme/Hizmet Kodu", "Kitap", "text", "crm_yeni_kitap", None),
    ("urun_adi", "Ürün Adı1", "Kitap", "text", "crm_kitap", None),
    ("yazar", "Yazar1", "Kitap", "text", "crm_kitap", None),
    ("yayinevi", "Yayınevi1", "Kitap", "text", "crm_kitap", None),
    ("kitaplik", "Kitaplık1", "Kitap", "text", "crm_kitap", None),
    ("dizi_tur", "Dizi_Tür1", "Kitap", "text", "crm_kitap", None),
    ("sayfa_sayisi", "SayfaSayısı1", "Kitap", "plain", "crm_kitap", None),
    ("uzeri_fiyat", "Üzeri_Fiyat1", "Kitap", "general", "crm_kitap", None),
    ("ilk_yayin_tarihi", "IlkYayinTarihi", "Baskı", "date", "crm_yeni_kitap", None),
    ("son_baski_tarihi", "SonBaskıTarihi1", "Baskı", "date", "crm_kitap", None),
    ("baski_durum", "Baskı_Durum1", "Baskı", "text", "crm_kitap", None),
    ("baski_adet", "Baskı_Adet", "Baskı", "plain", "crm_kitap", None),
    ("stok_adedi", "StokAdedi1", "Stok ve talep", "general", "crm_kitap", None),
    ("satis_suresi", "SatisSuresi", "Satış hızı", "plain", "hesap:Satış süresi (yeni kitap)", None),
    ("son_bir_yil_satis", "SonBirYilSatis", "Satış hızı", "n0", "logo_yeni_kitap_satis", "sum"),
    ("satis_hizi_tahmini", "SatisHiziTahmini", "Satış hızı", "n0", "hesap:Satış hızı tahmini (yeni kitap)", "sum"),
    ("son_bir_yil_ort", "SonBirYilSatisOrt", "Satış hızı", "n0", "hesap:Son 1 yıl ort. (yeni kitap)", "sum"),
    ("rpt_satis", "RPTSatis", "Satış hızı", "n0", "hesap:Tekrar sipariş (RPT)", "sum"),
    ("rpt_hizi", "RPTHizi", "Satış hızı", "n0", "hesap:Tekrar sipariş (RPT)", "sum"),
    ("marj", "Marj_Y", "Satış hızı", "general", "hesap:Marj / Öneri (yeni kitap)", "sum"),
    ("oneri", "Öneri_Y", "Satış hızı", "oneri", "hesap:Marj / Öneri (yeni kitap)", None),
    ("bu_ay_satis", "BuAyinSatisi", "Satış hızı", "n0", "logo_yeni_kitap_satis", None),
    ("dagilim_satis", "DagilimSatıs", "Satış hızı", "n0", "hesap:Dağılım satışı", "sum"),
]
# Ay başlıkları iki görselde farklı yazılmış; ikisi de şablondaki gibi.
TEKRAR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayis", "Haziran", "Temmuz", "Agustos", "Eylül", "Ekim", "Kasım", "Aralık"]
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

ONERI_LEVELS = ["Risk/Acil", "Kritik", "Karar Ver", "Takip Et", "Yeterli Stok"]


def _num(v: Any) -> float:
    try:
        return float(v) if v is not None and v != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def _key(v: Any) -> str:
    return str(v or "").strip()


def _day(v: Any) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)[:19]).date()
    except ValueError:
        return None


INF, NEG_INF, NAN = "∞", "-∞", "NaN"  # JSON'da sayı olarak taşınamaz; ekran mevcut rapordaki gibi yazar


def _dax_div(a: float | None, b: float | None) -> float | None:
    """DAX bölmesi (Microsoft, "Blanks, empty strings, and zero values"): 5/BLANK = ∞, 0/BLANK = NaN,
    BLANK/BLANK = BLANK; sıfıra bölme de aynı. None = BLANK."""
    if b is None or b == 0:
        if a is None:
            return None
        if a == 0:
            return math.nan
        return math.inf if a > 0 else -math.inf
    if a is None:
        return None
    return a / b


def _marj_oneri(stok: float | None, hiz: float | None) -> tuple[float | None, str | None]:
    """Power BI: Marj = StokAdedi / hız − 1 ve Öneri = IF(Marj <= 0, ...). BLANK − 1 = −1; NaN hiçbir
    eşikten küçük değildir (IEEE), öneri "Yeterli Stok" olur — mevcut rapor çıktısıyla doğrulanacak."""
    q = _dax_div(stok, hiz)
    marj = -1.0 if q is None else q - 1
    return marj, ("Yeterli Stok" if math.isnan(marj) else oneri(marj))


def _out(v: float | None) -> float | str | None:
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return NAN
    if v == math.inf:
        return INF
    if v == -math.inf:
        return NEG_INF
    return v


def _sort_key(v: Any) -> tuple[int, float]:
    """Power BI artan sıralaması: boş en küçük, sonra sayılar, sonra ∞; NaN en sonda."""
    if v is None:
        return (0, 0.0)
    if v == NEG_INF:
        return (1, 0.0)
    if v == INF:
        return (3, 0.0)
    if v == NAN:
        return (4, 0.0)
    return (2, float(v))


def oneri(marj: float | None) -> str | None:
    if marj is None:
        return None
    if marj <= 0:
        return "Risk/Acil"
    if marj <= 0.5:
        return "Kritik"
    if marj <= 1:
        return "Karar Ver"
    if marj <= 1.5:
        return "Takip Et"
    return "Yeterli Stok"


def _months_between(start: date, today: date) -> int:
    """SQL Server DATEDIFF(MONTH, ...) — ay sınırı sayısı, gün önemsiz."""
    return (today.year - start.year) * 12 + today.month - start.month


def _add_month(d: date) -> date:
    """SQL Server DATEADD(MONTH, 1, d): ay sonu taşarsa ayın son gününe oturur."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def _rpt_first_day(ilk: date, zaman: Any) -> date:
    """Power BI: RPT = `[Fatura Tarihi] >= DATEADD(MONTH, 1, ilk yayın)`; fatura tarihi gece yarısıdır.
    İlk yayının saati varsa (CRM UTC saklar, ör. 21:00) sınır günü o saatten sonra başladığı için
    o günün faturaları sayılmaz; ilk sayılan gün ertesi gündür."""
    first = _add_month(ilk)
    t = zaman if isinstance(zaman, datetime) else None
    if t is None and isinstance(zaman, str) and len(zaman) > 10:
        try:
            t = datetime.fromisoformat(zaman[:19])
        except ValueError:
            t = None
    if t is not None and (t.hour, t.minute, t.second, t.microsecond) != (0, 0, 0, 0):
        first = first + timedelta(days=1)
    return first


def _month_order(today: date) -> list[tuple[int, int]]:
    """Son 12 takvim ayı, eskiden yeniye: (yıl, ay)."""
    out = []
    y, m = today.year, today.month
    for _ in range(12):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def build(run: Callable[[str, dict | None], dict], today: date | None = None, inputs: dict | None = None) -> dict:
    """`run(source_id, params)` kaynağı çalıştırır ve {columns, records, ...} döner."""
    today = today or date.today()
    res = {}

    def rows(source_id: str, params: dict | None = None) -> list[dict]:
        res[source_id] = run(source_id, params)
        return res[source_id]["records"]

    kitap_rows = rows("crm_kitap")
    hiz = {_key(r["stok_kodu"]): r for r in rows("logo_satis_hizi")}
    aylik: dict[str, dict[int, float]] = {}
    for r in rows("logo_aylik_satis"):
        aylik.setdefault(_key(r["stok_kodu"]), {})[int(r["ay"])] = _num(r["miktar"])
    fiyat = {_key(r["stok_kodu"]): r for r in rows("logo_fiyat")}
    depo = {_key(r["stok_kodu"]): _num(r["depo_stok"]) for r in rows("logo_depo_stok")}
    bekleyen = {_key(r["stok_kodu"]): _num(r["bekleyen_siparis"]) for r in rows("crm_bekleyen_siparis")}
    onerilen = {_key(r["stok_kodu"]): _num(r["oneri_adet"]) for r in rows("crm_baski_onerisi")}
    yeni_rows_crm = [r for r in rows("crm_yeni_kitap") if _key(r["stok_kodu"])]
    yeni = {_key(r["stok_kodu"]): _day(r["ilk_yayin_tarihi"]) for r in yeni_rows_crm}
    yeni_zaman = {_key(r["stok_kodu"]): r.get("ilk_yayin_zamani") for r in yeni_rows_crm}
    yeni_satis_rows = rows("logo_yeni_kitap_satis", {"stok_kodlari": sorted(yeni)}) if yeni else []
    if not yeni:
        res["logo_yeni_kitap_satis"] = {"records": [], "columns": [], "dbMs": 0, "skipped": "Yeni kitap yok"}

    # Kitap kartı stok koduna göre tek satır: detay birden fazlaysa en son baskı esas alınır.
    kitap: dict[str, dict] = {}
    for r in kitap_rows:
        k = _key(r["stok_kodu"])
        if not k:
            continue
        prev = kitap.get(k)
        if prev is None or (_day(r.get("son_baski_tarihi")) or date.min) > (_day(prev.get("son_baski_tarihi")) or date.min):
            kitap[k] = r

    order = _month_order(today)
    # Yeni Kitap ay kolonları Power BI gibi ay numarasıyladır ve geçen yıl ile bu yılın aynı ayını toplar
    # (Power BI: V_SatisRaporu_2025_2026 üzerinde PIVOT ... FOR Ay IN ([1]..[12])).
    yeni_years = (today.year - 1, today.year)
    yeni_month_cols = [(f"ay_{m:02d}", MONTHS[m - 1]) for m in range(1, 13)]

    # ---- Baskı Tekrar: baskı tarihi geçen yılın bu ayından eski ve son 12 ayda satışı olan kitaplar
    cutoff = date(today.year - 1, today.month, 1)
    tekrar = []
    for k, h in hiz.items():
        b = kitap.get(k)
        if b is None:
            continue
        bt = _day(b.get("baski_tarihi"))
        if bt is None or bt >= cutoff:
            continue
        if (b.get("yayinevi") or "") in EXCLUDED_PUBLISHERS["tekrar"]:
            continue
        # Hız Power BI'daki gibi SQL'de satır satır hesaplanır (Logo_SatisHizi.SatisHizi); yoksa ağırlıklardan.
        speed = _num(h["satis_hizi"]) if "satis_hizi" in h else sum(_num(h.get(c)) * w for c, w in WEIGHTS)
        stok = b.get("stok_adedi")
        stok = None if stok is None or stok == "" else _num(stok)
        tuk = _dax_div(stok, speed)  # mevcut rapor: Tükenme Süresi = SUM(StokAdedi) / SUM(OrtSatisHizi)
        marj, marj_oneri = _marj_oneri(stok, speed)
        f = fiyat.get(k) or {}
        row = {
            **{c: b.get(c) for c in ("stok_kodu", "urun_adi", "statu", "yazar", "yayinevi", "kitaplik", "dizi_tur",
                                     "sayfa_sayisi", "uzeri_fiyat", "baski_durum", "son_baski_tarihi", "baski_adet", "stok_adedi")},
            "son_fiyat_degisikligi": f.get("son_fiyat_degisikligi"),
            "depo_stok": depo.get(k),
            "bekleyen_siparis": bekleyen.get(k),
            "oneri_adet": onerilen.get(k),
            "yillik_toplam": _num(h.get("yillik_toplam")),
            "ort_satis_hizi": speed,
            "yillik_ort": _num(h.get("yillik_ort")),
            "tukenme_suresi": _out(tuk),
            "marj": _out(marj),
            "oneri": marj_oneri,
            **{c: _num(h.get(c)) for c in ("son6_ort", "onceki6_ort", "ceyrek1_ort", "ceyrek2_ort", "ceyrek3_ort", "ceyrek4_ort")},
        }
        a = aylik.get(k, {})
        for m in range(1, 13):  # mevcut rapor: Sorgu3 ay numarasına göre Ocak..Aralık (son 12 ay, her ay bir kez)
            row[f"ay_{m:02d}"] = a.get(m, 0)
        tekrar.append(row)
    # Power BI sıralaması: en önce tükenecek üstte; satışı olmayan (hız 0) en sonda.
    tekrar.sort(key=lambda r: _sort_key(r["tukenme_suresi"]))

    # ---- Yeni Kitap
    per_day: dict[str, list[tuple[date, float]]] = {}
    for r in yeni_satis_rows:
        d = _day(r["gun"])
        if d:
            per_day.setdefault(_key(r["stok_kodu"]), []).append((d, _num(r["miktar"])))
    window_start = date(order[0][0], order[0][1], 1)
    yeni_rows = []
    for k, ilk in yeni.items():
        sales = per_day.get(k)
        if not sales or ilk is None:
            continue  # mevcut rapor satır üretmiyordu: satış tablosuyla iç birleşim
        b = kitap.get(k) or {}
        if (b.get("yayinevi") or None) in EXCLUDED_PUBLISHERS["yeni"] or not b.get("yayinevi"):
            continue
        sure = _months_between(ilk, today)
        rpt_from = _rpt_first_day(ilk, yeni_zaman.get(k))
        son_yil = sum(q for d, q in sales if d >= window_start)
        dagilim = sum(q for d, q in sales if d.year == ilk.year and d.month == ilk.month)
        rpt = sum(q for d, q in sales if d >= rpt_from)
        bu_ay = sum(q for d, q in sales if d.year == today.year and d.month == today.month)
        son_yil_ort = son_yil / sure if sure else None
        rpt_hizi = rpt / sure if sure else None
        tahmin = (son_yil_ort * 0.4 + rpt_hizi * 0.6) if sure else None
        stok = b.get("stok_adedi")
        stok = None if stok is None or stok == "" else _num(stok)
        marj, marj_oneri = _marj_oneri(stok, son_yil_ort)
        row = {
            "stok_kodu": k,
            **{c: b.get(c) for c in ("urun_adi", "yazar", "yayinevi", "kitaplik", "dizi_tur", "sayfa_sayisi", "uzeri_fiyat",
                                     "son_baski_tarihi", "baski_durum", "baski_adet", "stok_adedi")},
            "ilk_yayin_tarihi": ilk.isoformat(),
            "satis_suresi": sure,
            "son_bir_yil_satis": son_yil,
            "satis_hizi_tahmini": tahmin,
            "son_bir_yil_ort": son_yil_ort,
            "rpt_satis": rpt,
            "rpt_hizi": rpt_hizi,
            "marj": _out(marj),
            "oneri": marj_oneri,
            "bu_ay_satis": bu_ay,
            "dagilim_satis": dagilim,
        }
        for m in range(1, 13):
            row[f"ay_{m:02d}"] = sum(q for d, q in sales if d.month == m and d.year in yeni_years)
        yeni_rows.append(row)
    yeni_rows.sort(key=lambda r: -r["son_bir_yil_satis"])

    def cols(spec):
        base = [{"key": k, "label": l, "group": g, "format": f, "source": src, "total": t} for k, l, g, f, src, t in spec]
        if spec is TEKRAR_COLUMNS:
            return base + [{"key": f"ay_{m:02d}", "label": TEKRAR_MONTHS[m - 1], "group": "Son 12 ay satış", "format": "n0",
                            "source": "logo_aylik_satis", "total": "sum"} for m in range(1, 13)]
        group = f"Aylık satış ({yeni_years[0]} + {yeni_years[1]})"
        return base + [{"key": k, "label": l, "group": group, "format": "n0", "source": "logo_yeni_kitap_satis", "total": "sum"}
                       for k, l in yeni_month_cols]

    def view(view_id, title, hint, spec, data, filters):
        columns = cols(spec)
        # Satırlar kolon sırasında dizi: binlerce satırda anahtar tekrarı yükü yarıya indirir.
        return {"id": view_id, "title": title, "hint": hint, "columns": columns, "filters": filters,
                "defaultFilters": DEFAULT_FILTERS.get(view_id, []),
                "rows": [[r.get(c["key"]) for c in columns] for r in data]}

    # ---- ZEKI AI Tahminleme: Power BI sekmelerinin yanında ikinci görüş. Satırlar yukarıdaki listelerden okunur,
    # onlar değiştirilmez. Talep tahmini gecelik (baski-oneri-tahmin), stok ve sipariş bu okumadan (5 dk).
    from semantic_bridge.management import zeki_tahmin

    forecast = (inputs or {}).get(zeki_tahmin.REPORT_ID)
    forecast_error = ((inputs or {}).get("_errors") or {}).get(zeki_tahmin.REPORT_ID)
    sql_list = []
    for sid, st in ((forecast or {}).get("sourceStats") or {}).items():
        meta = next((x for x in zeki_tahmin.SOURCES if x[0] == sid), None)
        if meta and st.get("sql"):
            sql_list.append({"id": sid, "title": meta[2], "description": meta[3], "sql": st["sql"]})
    for sid in ("crm_kitap", "crm_bekleyen_siparis"):
        meta = next((x for x in SOURCES if x[0] == sid), None)
        if meta and (res.get(sid) or {}).get("sql"):
            sql_list.append({"id": sid, "title": meta[2], "description": meta[3], "sql": res[sid]["sql"]})
    tab = zeki_tahmin.tab(tekrar, yeni_rows, bekleyen, forecast, today, sql_list, error=forecast_error)
    tab_view = {"id": "tahmin", "title": "ZEKI AI Tahminleme",
                "hint": "Stoku en önce bitecek kitap üstte (ZEKI AI tahminine göre)",
                "columns": tab["columns"], "filters": ["oneri", "guven", "liste", "yayinevi", "yazar", "statu", "urun_adi"],
                "defaultFilters": [], "explain": tab["explain"], "emptyText": tab["emptyText"],
                "oneriLevels": zeki_tahmin.ONERI_LEVELS,
                "rows": [[r.get(c["key"]) for c in tab["columns"]] for r in tab["rows"]]}

    return {
        "views": [
            view("tekrar", "Baskı Tekrar", "En önce tükenecek kitap üstte", TEKRAR_COLUMNS, tekrar,
                 ["oneri", "baski_durum", "yayinevi", "yazar", "statu", "urun_adi"]),
            view("yeni", "Yeni Kitap", "İlk yayını son 12 ayda olanlar, en çok satan üstte", YENI_COLUMNS, yeni_rows,
                 ["oneri", "baski_durum", "yayinevi", "yazar", "urun_adi"]),
            tab_view,
        ],
        "oneriLevels": ONERI_LEVELS,
        "sourceStats": {sid: {"rows": len(r.get("records") or []), "dbMs": r.get("dbMs"), "skipped": r.get("skipped"),
                              "sql": r.get("sql"), "warning": r.get("warning")}
                        for sid, r in res.items()},
        "warnings": sorted({r["warning"] for r in res.values() if r.get("warning")}),
        "asOf": today.isoformat(),
    }
