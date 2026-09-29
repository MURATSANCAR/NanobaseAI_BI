"""M34 E-ticaret: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`, yakalama `sorgu_yakala.py`).

Uç çalışırken portal tablolarına giden okumalar ve Logo'ya giden sorgular değerleriyle yakalanır; burada her rakam alanı
bir hesap metnine ve o okumalara bağlanır. Gece okumasının CRM/Logo/site sorguları (`eticaret.KOKEN_OKUMA`) kitap ve
fark tablolarının «asıl sorgusu»dur (`origin`).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import eticaret as E
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y

ITEMS = "semantic_eticaret_items"
DIFFS = "semantic_eticaret_diffs"
LOG = "semantic_eticaret_diff_log"
RUNS = "semantic_eticaret_runs"
PROPS = "semantic_seo_proposals"

TABLOLAR = {
    ITEMS: ("Kitap satırı (site · CRM · Logo)", "Gece okumasında kitap başına kurulan satır: sitedeki ürün sayaçları ve fiyatı, "
                                               "CRM kartı, Logo stok bakiyesi, liste fiyatı ve son dönem net satışı."),
    DIFFS: ("Fark kaydı", "Kitap × fark türü: CRM, Logo ve sitedeki değer, etki (sıralama ağırlığı), durum, ilk/son görüldüğü gün."),
    LOG: ("Fark günlüğü", "Her durum geçişi: kim, ne zaman, not."),
    RUNS: ("Okuma kaydı", "Gece okumasının başlangıcı, bitişi ve kaynak başına okunan kayıt sayıları."),
    PROPS: ("Zeki AI kart önerileri", "SEO öneri kaydındaki «E-ticaret» kaynaklı ürün kartı önerileri; puanlar kural denetiminden."),
    "semantic_eticaret_market_reads": ("Pazar yeri Logo okuması (saklanan)",
                                       "Pazar yeri Logo okumasının satırları ve o okumada çalışan Logo sorguları; köprü "
                                       "yeniden başlayınca bir kez buradan okunur, sonra bellekten."),
}
KOKEN = {ITEMS: [E.KOKEN_OKUMA], DIFFS: [E.KOKEN_OKUMA]}
KOKEN_BASLIK = {E.KOKEN_OKUMA: "Gece okuması"}

#: Rakam olmayan sayılar: sayfa numarası/boyu, yıl, ay dizisindeki sıra değil (aylar değerdir), ayar değerleri.
NOT_RAKAM = ("page", "pageSize", "yil", "yillar", "ayarlar", "durum", "esikGun", "satisAyi", "dusukEsik.enAzGoruntulenme",
             "dusukEsik.oran")

F_SITE_AKTIF = ("Sitede satışta = kitap satırlarından sitedeki ürünü aktif olanların sayısı (aynı barkodlu ürünlerden biri "
                "aktifse aktif). CRM «TSOFT Aktif» = CRM kartında «TSOFT Aktif» işaretli satırlar.")
F_ACIK = "Açık fark = durumu «açık» ya da «sonra» olan fark kayıtları (kitap × tür)."
F_TUR = ("Tür sayısı = durumu «açık» ya da «sonra» olan fark kayıtlarının türe göre sayısı. Eksik ürün kartı = «eksik_kart», "
         "satışta olmaması gereken = «hak» türü.")
F_DURUM = "Durum sayısı = bütün fark kayıtlarının durumlarına göre sayısı (açık, sonra, bilinçli, düzeltildi, kapandı)."
F_HAFTA = ("Son 7 gün: kapanan = son 7 günde «kapandı» durumuna geçen fark sayısı; ortalama kapanma = Σ (kapanış − ilk "
           "görülme) gün ÷ kapanan sayısı, bir ondalık.")
F_FARK = ("Fark satırı: CRM, Logo ve sitedeki değerler gece okumasından; etki = kitabın Logo son dönem net adedi (bütün "
          "kanallar; Logo yoksa sitedeki toplam satış adedi) — sıralama ağırlığı. Neden olasılığı Zeki AI'ın kapalı küme "
          "seçimindeki güvenidir (rakam üretmez; eşik altı «belirsiz»). D&R fiyat farkı: TİMAŞ grubu kitabın barkodu D&R "
          "kataloğunun son görüntüsünde; D&R satış fiyatı sitedeki fiyatımızdan (indirimli varsa o) ayardaki toleranstan "
          "fazla düşükse ya da D&R'deki liste fiyatı bizim liste fiyatımızdan (ayardaki esas: CRM ya da Logo) farklıysa; "
          "D&R indirimi = 1 − D&R satış fiyatı ÷ D&R liste fiyatı.")
F_TOPLAM = "Toplam = süzgece uyan fark kaydı sayısı (sayfalı listede görünenden bağımsız)."
F_OKUMA = "Son okumanın kaynak özeti: okunan ürün, CRM kartı, Logo stok kodu ve fiyat sayıları okuma kaydından."
F_KITAP = ("Kitap: Logo stok = güncel firma, IOCODE 1,2 giriş − 3,4 çıkış (planlanan üretim girişi hariç); Logo fiyat = bugün "
           "geçerli satış liste fiyatı; Logo net adet/ciro = son dönem, bütün kanallar, faturalı satır (7,8,9 satış − 2,3 "
           "iade). Site fiyatı, stoğu, görüntülenme, satış ve yorum sitedeki ürün kaydından (tüm zaman sayaçları); dönüşüm = "
           "site satış ÷ görüntülenme. Doluluk = zorunlu alanlardan dolu olanların payı × 100.")
F_ONERI = ("Öneri puanları (önce/sonra) ürün kartının kural denetimi puanıdır (SEO & GEO kuralları); öneri sayısı listedeki "
           "kayıt sayısıdır.")
F_HUNI = ("Huni: görüntülenme ve satış sitedeki ürün sayaçları (tüm zamanlar), dönüşüm = satış ÷ görüntülenme. Ortanca "
          "dönüşüm = görüntülenmesi olan aktif ürünlerin dönüşüm oranlarının ortancası; düşük dönüşüm eşiği = ortanca × ayardaki "
          "oran. Toplamlar aktif ürünlerin Σ görüntülenme, Σ satış, Σ yorum.")
F_PAZAR = ("Pazar yeri carisi (CLCARD.SPECODE2 ayardaki kanal): satış = Σ LINENET (TRCODE 7,8,9), iade = Σ LINENET (2,3), "
           "net = satış − iade; faturalı malzeme satırı (INVOICEREF ≠ 0, LINETYPE 0), iptal hariç. Bu yıl 1 Ocak–kesim günü, "
           "geçen yıl aynı dönem; değişim = (net − geçen yıl net) ÷ |geçen yıl net|; iade oranı = iade ÷ satış. Aylık = o ayın "
           "neti. Yıl sınırında her yıl kendi firma kopyasından okunur.")
F_KITAPLAR = ("Kitap kırılımı: satış/iade adedi = Σ AMOUNT (7,8,9 / 2,3), ciro = Σ LINENET (satış − iade), net adet = satış "
              "− iade adedi, iade oranı = iade ÷ satış adedi. Logo stok ve kalan gün kitap satırından: kalan gün = Logo stok ÷ "
              "(son dönem net adet ÷ gün); tükenme riski = kalan gün < ayardaki eşik.")
F_KESIM = "Kesim = güncel Logo firmasındaki son faturalı satış satırının günü; Logo rakamları bu güne kadardır."


def _kur(engine: Any, tenant: str, q: Y.Yakalanan) -> Y.Kurucu:
    return Y.Kurucu(engine, tenant, q, prefix="eticaret", tablolar=TABLOLAR, koken=KOKEN, koken_basliklari=KOKEN_BASLIK)


def for_overview(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    site = b.hesap("siteAktif", F_SITE_AKTIF, ITEMS)
    acik = b.hesap("acikFark", F_ACIK, DIFFS)
    tur = b.hesap("turSayilari", F_TUR, DIFFS)
    return b.alanlar({
        "gostergeler": site, "gostergeler.siteAktif": site, "gostergeler.crmTsoftAktif": site,
        "gostergeler.acikFark": acik, "gostergeler.eksikKart": tur, "gostergeler.satistaOlmamali": tur,
        "turSayilari": tur, "durumSayilari": b.hesap("durumSayilari", F_DURUM, DIFFS),
        "haftalik": b.hesap("haftalik", F_HAFTA, DIFFS),
        "bugun.items": b.hesap("fark", F_FARK, DIFFS), "bugun.total": b.hesap("bugunToplam", F_TOPLAM, DIFFS),
        "sonOkuma": b.hesap("sonOkuma", F_OKUMA, RUNS),
    })


def for_diffs(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"items": b.hesap("fark", F_FARK, DIFFS), "total": b.hesap("toplam", F_TOPLAM, DIFFS),
                      "turSayilari": b.hesap("turSayilari", F_TUR, DIFFS)})


def for_diff(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    fark = b.hesap("fark", F_FARK, DIFFS)
    return b.alanlar({"etki": fark, "neden": fark, "gunluk": b.sorgu(LOG)})


def for_item(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"kitap": b.hesap("kitap", F_KITAP, ITEMS), "farklar": b.hesap("fark", F_FARK, DIFFS),
                      "gunluk": b.sorgu(LOG, DIFFS), "oneriler": b.hesap("oneri", F_ONERI, PROPS)})


def for_proposals(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"items": b.hesap("oneri", F_ONERI, PROPS, ITEMS)})


def for_funnel(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("huni", F_HUNI, ITEMS)
    return b.alanlar({"items": b.hesap("kitap", F_KITAP, ITEMS), "total": h, "ortancaDonusum": h, "dusukEsik": h, "toplam": h})


def for_marketplaces(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("pazarYeri", F_PAZAR, *_all_logo(b))
    return b.alanlar({"cariler": h, "toplam": h, "kesim": b.hesap("kesim", F_KESIM, *_all_logo(b))})


def for_stock_risk(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"items": b.hesap("kitaplar", F_KITAPLAR, ITEMS, *_all_logo(b))})


def for_marketplace_books(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("kitaplar", F_KITAPLAR, ITEMS, *_all_logo(b))
    return b.alanlar({"items": h, "total": h})


def _all_logo(b: Y.Kurucu) -> list[str]:
    """Bu istekte Logo'ya giden bütün sorguların kimlikleri (fiziksel tablo adı yıl firmasına göre değişir)."""
    return [sid for sid, s in b.k.sources.items() if s["connection"] == "logo"]
