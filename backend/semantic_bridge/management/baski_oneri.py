"""Yeni Baskı Öneri raporu — Power BI şablonunun ("2025_Yeni_Baskı Öneri Raporu") köprüdeki karşılığı.

Power BI modeli Logo ve CRM tablolarını bellekte ilişkiyle birleştiriyordu. Burada da öyle: Logo ile
CRM ayrı SQL sunucularında durduğu için tek sorguda birleşemezler; her kaynak kendi sorgusuyla okunur,
birleştirme ve DAX hesapları aşağıda stok koduna göre yapılır.

Power BI'dan bilinçli farklar `NOTES` içinde; ekranda da gösterilir.
"""
from __future__ import annotations

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
    "Rapor Power BI dosyasının açılış görünümüyle aynı süzgeçlerle açılır: statü boş, YS04 Aktif ya da "
    "YS10A Ürün Fazlası; baskı durumu boş ya da Depo Girişi Yapıldı. Çipler kaldırılınca havuzun tamamı görünür.",
    "Satış hızı havuzu Power BI ile aynı: 2024 başından bu yana satışı olan her kitap listede. Son 12 ayda "
    "hiç satmayan kitap da kalır; hızı 0, tükenmesi boş, önerisi \u201cYeterli Stok\u201d olur.",
    "Marj ve öneri, bölen olmadığında Power BI'ın DAX davranışını izler: stok varken sonuç sonsuzdur ve "
    "\u201cYeterli Stok\u201d yazar, stok da yokken boş sonuç \u22121 sayılır ve \u201cRisk/Acil\u201d yazar.",
    "Logo ve CRM ayrı sunucularda olduğu için Power BI'daki bellek içi ilişki burada stok koduyla birleştirmedir; sonuç aynı satırlardır.",
    "Dönemler tamamlanmış aylardır ve tarih karşılaştırması ay başına göre yapılır; Power BI'daki 'gün sonu' karşılaştırması saatli faturaları son günden düşürebiliyordu.",
    "Power BI'da 'Ilk6Ay' en yeni 6 ayı, 'Son6Ay' eski 6 ayı tutuyordu; burada 'Son 6 ay' ve 'Önceki 6 ay' olarak doğru adlarıyla gösterilir.",
    "Yeni kitap ay kolonları son 12 ayın takvim aylarıdır; Power BI iki yılın aynı ayını topluyordu.",
    "Yeni kitaplarda ilk yayın tarihi CRM'den, satış Logo'dan okunur (Power BI bağlı sunucu üzerinden tek sorguda birleştiriyordu).",
    "Power BI satış hızını satır satır kayan noktayla toplar; sıfır olması gereken hız −3·10⁻¹⁷, 0,5 olması "
    "gereken hız 0,49999999999999994 çıkabilir ve öneri eşiği yanlış taraftan geçer. Burada önce toplanıp "
    "sonra bölünür; 2026-09-23 karşılaştırmasında 5.053 kitabın 2'sinde öneri bu yüzden farklıdır.",
    "Kullanılmayan 'CRM_BekleyenSiparis' tablosu ve kırık 'Set Kitaplar' sayfası (modelde olmayan tabloya bağlı) alınmadı.",
    "Logo satışı Power BI'da 'V_SatisRaporu_ALL2' (2015'ten bu yana her yılın birleşimi) ve onun üstündeki "
    "'PBI_FiyatList' görünümlerinden okunuyordu. Burada aynı satırlar yalnız gereken yılların görünümlerinden "
    "okunur: satış hızı 2024'ten, fiyat 2025'ten, aylık ve yeni kitap satışı geçen yıldan bu yana. ALL2 üzerinden "
    "fiyat sorgusu 15 dakikada bitmiyordu; yıllık görünümlerle üç yıl 25 saniyede okunuyor.",
    "Yeni kitap satışı Power BI'da 'V_SatisRaporu_2025_2026' görünümünden okunuyordu; burada geçen yıl ve bu yılın "
    "görünümleri son 12 aya sınırlanarak okunur. İlk yayın son 12 ayda olduğu için satır kümesi aynıdır.",
]

# Kolon → kaynak eşlemesi ekranda başlıktan sorguya gidişi sağlar.
TEKRAR_COLUMNS = [
    # key, etiket, grup, biçim, kaynak
    ("stok_kodu", "Stok kodu", "Kitap", "text", "crm_kitap"),
    ("urun_adi", "Ürün adı", "Kitap", "text", "crm_kitap"),
    ("statu", "Statü", "Kitap", "text", "crm_kitap"),
    ("yazar", "Yazar", "Kitap", "text", "crm_kitap"),
    ("yayinevi", "Yayınevi", "Kitap", "text", "crm_kitap"),
    ("kitaplik", "Kitaplık", "Kitap", "text", "crm_kitap"),
    ("dizi_tur", "Dizi / tür", "Kitap", "text", "crm_kitap"),
    ("sayfa_sayisi", "Sayfa", "Kitap", "int", "crm_kitap"),
    ("uzeri_fiyat", "Üzeri fiyat", "Kitap", "money", "crm_kitap"),
    ("baski_durum", "Baskı durumu", "Baskı", "text", "crm_kitap"),
    ("son_baski_tarihi", "Son baskı", "Baskı", "date", "crm_kitap"),
    ("son_fiyat_degisikligi", "Son fiyat değişikliği", "Baskı", "date", "logo_fiyat"),
    ("baski_adet", "Baskı adedi", "Baskı", "int", "crm_kitap"),
    ("stok_adedi", "Stok (CRM)", "Stok ve talep", "int", "crm_kitap"),
    ("depo_stok", "Depo stoku (Logo)", "Stok ve talep", "int", "logo_depo_stok"),
    ("bekleyen_siparis", "Bekleyen sipariş", "Stok ve talep", "int", "crm_bekleyen_siparis"),
    ("oneri_adet", "Öneri adedi (30 gün)", "Stok ve talep", "int", "crm_baski_onerisi"),
    ("yillik_toplam", "Yıllık satış", "Satış hızı", "int", "logo_satis_hizi"),
    ("ort_satis_hizi", "Ort. satış hızı", "Satış hızı", "dec", "hesap:Ort. satış hızı"),
    ("yillik_ort", "Yıllık ort.", "Satış hızı", "dec", "logo_satis_hizi"),
    ("tukenme_suresi", "Tükenme (ay)", "Satış hızı", "dec", "hesap:Tükenme süresi"),
    ("marj", "Marj", "Satış hızı", "dec", "hesap:Marj"),
    ("oneri", "Öneri", "Satış hızı", "oneri", "hesap:Öneri"),
    ("son6_ort", "Son 6 ay ort.", "Satış hızı", "dec", "logo_satis_hizi"),
    ("onceki6_ort", "Önceki 6 ay ort.", "Satış hızı", "dec", "logo_satis_hizi"),
    ("ceyrek1_ort", "Son 3 ay ort.", "Satış hızı", "dec", "logo_satis_hizi"),
    ("ceyrek2_ort", "4–6 ay önce ort.", "Satış hızı", "dec", "logo_satis_hizi"),
    ("ceyrek3_ort", "7–9 ay önce ort.", "Satış hızı", "dec", "logo_satis_hizi"),
    ("ceyrek4_ort", "10–12 ay önce ort.", "Satış hızı", "dec", "logo_satis_hizi"),
]
YENI_COLUMNS = [
    ("stok_kodu", "Stok kodu", "Kitap", "text", "crm_yeni_kitap"),
    ("urun_adi", "Ürün adı", "Kitap", "text", "crm_kitap"),
    ("yazar", "Yazar", "Kitap", "text", "crm_kitap"),
    ("yayinevi", "Yayınevi", "Kitap", "text", "crm_kitap"),
    ("kitaplik", "Kitaplık", "Kitap", "text", "crm_kitap"),
    ("dizi_tur", "Dizi / tür", "Kitap", "text", "crm_kitap"),
    ("sayfa_sayisi", "Sayfa", "Kitap", "int", "crm_kitap"),
    ("uzeri_fiyat", "Üzeri fiyat", "Kitap", "money", "crm_kitap"),
    ("ilk_yayin_tarihi", "İlk yayın", "Baskı", "date", "crm_yeni_kitap"),
    ("son_baski_tarihi", "Son baskı", "Baskı", "date", "crm_kitap"),
    ("baski_durum", "Baskı durumu", "Baskı", "text", "crm_kitap"),
    ("baski_adet", "Baskı adedi", "Baskı", "int", "crm_kitap"),
    ("stok_adedi", "Stok (CRM)", "Stok ve talep", "int", "crm_kitap"),
    ("satis_suresi", "Satış süresi (ay)", "Satış hızı", "int", "hesap:Satış süresi (yeni kitap)"),
    ("son_bir_yil_satis", "Son 1 yıl satış", "Satış hızı", "int", "logo_yeni_kitap_satis"),
    ("satis_hizi_tahmini", "Satış hızı tahmini", "Satış hızı", "dec", "hesap:Satış hızı tahmini (yeni kitap)"),
    ("son_bir_yil_ort", "Son 1 yıl ort.", "Satış hızı", "dec", "hesap:Son 1 yıl ort. (yeni kitap)"),
    ("rpt_satis", "Tekrar sipariş (RPT)", "Satış hızı", "int", "hesap:Tekrar sipariş (RPT)"),
    ("rpt_hizi", "RPT hızı", "Satış hızı", "dec", "hesap:Tekrar sipariş (RPT)"),
    ("marj", "Marj", "Satış hızı", "dec", "hesap:Marj / Öneri (yeni kitap)"),
    ("oneri", "Öneri", "Satış hızı", "oneri", "hesap:Marj / Öneri (yeni kitap)"),
    ("bu_ay_satis", "Bu ay satış", "Satış hızı", "int", "logo_yeni_kitap_satis"),
    ("dagilim_satis", "Dağılım satışı", "Satış hızı", "int", "hesap:Dağılım satışı"),
]
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


def _marj_oneri(stok: float, hiz: float | None) -> tuple[float | None, str | None]:
    """Power BI'daki `Marj` = StokAdedi / hız − 1 ve onun üstündeki `Öneri`.

    DAX'ın bölen-yok davranışı birebir yansıtılır: stok varken sıfıra ya da boşa bölmek
    sonsuz verir (marj gösterilmez, öneri "Yeterli Stok"), stok da yokken sonuç boştur ve
    `boş − 1 = −1` olduğu için öneri "Risk/Acil" olur. Yeni kitapta satış süresi 0 ise
    bölen SQL'de NULLIF ile boş gelir; aynı dal çalışır.
    """
    if not hiz:  # 0 ya da None
        return (None, "Yeterli Stok") if stok > 0 else (-1.0, "Risk/Acil")
    marj = stok / hiz - 1
    return marj, oneri(marj)


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


def _round(v: float | None, n: int = 2) -> float | None:
    return None if v is None else round(v, n)


def build(run: Callable[[str, dict | None], dict], today: date | None = None) -> dict:
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
    month_cols = [(f"ay_{y}_{m:02d}", f"{MONTHS[m - 1]} {str(y)[2:]}") for y, m in order]

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
        speed = sum(_num(h.get(c)) * w for c, w in WEIGHTS)
        stok = _num(b.get("stok_adedi"))
        # Power BI gibi: iadesi satışından fazla olan kitapta hız eksidir ve tükenme de eksi gösterilir.
        tuk = stok / speed if speed else None
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
            "ort_satis_hizi": _round(speed),
            "yillik_ort": _round(_num(h.get("yillik_ort"))),
            "tukenme_suresi": _round(tuk),
            "marj": _round(marj),
            "oneri": marj_oneri,
            **{c: _round(_num(h.get(c))) for c in ("son6_ort", "onceki6_ort", "ceyrek1_ort", "ceyrek2_ort", "ceyrek3_ort", "ceyrek4_ort")},
        }
        a = aylik.get(k, {})
        for (key, _), (_, m) in zip(month_cols, order):
            row[key] = a.get(m, 0)
        tekrar.append(row)
    # Power BI sıralaması: en önce tükenecek üstte; satışı olmayan (hız 0) en sonda.
    tekrar.sort(key=lambda r: (r["tukenme_suresi"] is None, r["tukenme_suresi"] or 0))

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
            continue  # Power BI satır üretmiyordu: satış tablosuyla iç birleşim
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
        stok = _num(b.get("stok_adedi"))
        marj, marj_oneri = _marj_oneri(stok, son_yil_ort)
        row = {
            "stok_kodu": k,
            **{c: b.get(c) for c in ("urun_adi", "yazar", "yayinevi", "kitaplik", "dizi_tur", "sayfa_sayisi", "uzeri_fiyat",
                                     "son_baski_tarihi", "baski_durum", "baski_adet", "stok_adedi")},
            "ilk_yayin_tarihi": ilk.isoformat(),
            "satis_suresi": sure,
            "son_bir_yil_satis": son_yil,
            "satis_hizi_tahmini": _round(tahmin),
            "son_bir_yil_ort": _round(son_yil_ort),
            "rpt_satis": rpt,
            "rpt_hizi": _round(rpt_hizi),
            "marj": _round(marj),
            "oneri": marj_oneri,
            "bu_ay_satis": bu_ay,
            "dagilim_satis": dagilim,
        }
        for (key, _), (y, m) in zip(month_cols, order):
            row[key] = sum(q for d, q in sales if d.year == y and d.month == m)
        yeni_rows.append(row)
    yeni_rows.sort(key=lambda r: -r["son_bir_yil_satis"])

    def cols(spec):
        base = [{"key": k, "label": l, "group": g, "format": f, "source": s} for k, l, g, f, s in spec]
        return base + [{"key": k, "label": l, "group": "Son 12 ay satış", "format": "int",
                        "source": "logo_aylik_satis" if spec is TEKRAR_COLUMNS else "logo_yeni_kitap_satis"}
                       for k, l in month_cols]

    def view(view_id, title, hint, spec, data, filters):
        columns = cols(spec)
        # Satırlar kolon sırasında dizi: binlerce satırda anahtar tekrarı yükü yarıya indirir.
        return {"id": view_id, "title": title, "hint": hint, "columns": columns, "filters": filters,
                "defaultFilters": DEFAULT_FILTERS.get(view_id, []),
                "rows": [[r.get(c["key"]) for c in columns] for r in data]}

    return {
        "views": [
            view("tekrar", "Baskı Tekrar", "En önce tükenecek kitap üstte", TEKRAR_COLUMNS, tekrar,
                 ["oneri", "baski_durum", "yayinevi", "statu"]),
            view("yeni", "Yeni Kitap", "İlk yayını son 12 ayda olanlar, en çok satan üstte", YENI_COLUMNS, yeni_rows,
                 ["oneri", "baski_durum", "yayinevi"]),
        ],
        "oneriLevels": ONERI_LEVELS,
        "sourceStats": {sid: {"rows": len(r.get("records") or []), "dbMs": r.get("dbMs"), "skipped": r.get("skipped"),
                              "sql": r.get("sql"), "warning": r.get("warning")}
                        for sid, r in res.items()},
        "warnings": sorted({r["warning"] for r in res.values() if r.get("warning")}),
        "asOf": today.isoformat(),
    }
