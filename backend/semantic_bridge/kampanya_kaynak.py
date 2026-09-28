"""M35 Kampanyalar: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`, yakalama `sorgu_yakala.py`).

Uç çalışırken portal tablolarına ve CRM'e giden okumalar değerleriyle yakalanır; her rakam alanı bir hesap metnine ve o
okumalara bağlanır. Kitap tablosunu gece dolduran CRM/Logo sorguları (`kampanya.KOKEN_OKUMA`) ve kampanya sonucunu
dolduran Logo sorgusu (`kampanya.koken_sonuc(id)`) «asıl sorgu» olarak eklenir.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import kampanya as C
from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y

CAMPS, ITEMS, CAL, RES, LEARN = ("semantic_kampanya_campaigns", "semantic_kampanya_items", "semantic_kampanya_calendar",
                                 "semantic_kampanya_results", "semantic_kampanya_learnings")
SNAPS, BOOKS, CRMT, META = ("semantic_kampanya_price_snapshots", "semantic_kampanya_books", "semantic_kampanya_crm_types",
                            "semantic_kampanya_meta")
DAYS = "semantic_seo_seasons_days"

TABLOLAR = {
    CAMPS: ("Kampanya kaydı", "Kampanyanın başlığı, kanalı, tarihleri, durumu, kanal kesintisi ve beklenen satış artışı."),
    ITEMS: ("Kampanya kitapları (hesap)", "Kitap başına liste ve kampanya fiyatı, indirim, net, telif, marj, stok, tükenme "
                                          "tahmini ve kontroller; son simülasyonda hesaplanıp saklanır."),
    CAL: ("Kampanya takvimi", "Elle girilen platform dönemleri ve notlar."),
    RES: ("Kampanya sonucu (günlük satış)", "Kitap × gün × dönem (önce / kampanya / sonra): adet, iade, net tutar, maliyet."),
    LEARN: ("Kampanya öğrenimleri", "Biten kampanyadan yazılan öğrenim notları."),
    SNAPS: ("Site fiyat kaydı", "Günlük site fiyatı ve indirimli fiyatı (son 30 gün en düşük fiyat kuralı için)."),
    BOOKS: ("Kitap verisi (Logo + CRM)", "Gece okumasında kitap başına: liste fiyatı (CRM/Logo), KDV, stok, satış hızı, son 12 ay "
                                         "adet ve tutar, bu yılın maliyetli satışı, sözleşme sınırları, hak, sezon bağları."),
    CRMT: ("CRM kampanya türü", "Bayi kampanyasının gece sınıflanan türü."),
    META: ("Okuma bilgisi", "Veri sonu, satış hızı penceresi, son okuma özeti."),
    DAYS: ("Özel günler", "Takvimdeki özel günler (SEO & GEO sezon takvimi)."),
}
KOKEN = {BOOKS: [C.KOKEN_OKUMA], ITEMS: [C.KOKEN_OKUMA], SNAPS: [C.KOKEN_OKUMA]}
KOKEN_BASLIK = {C.KOKEN_OKUMA: "Gece okuması (kitap verisi)"}

#: Rakam olmayan sayılar: sayfa, ayar ve eşik değerleri (Yönetim → Kampanyalar), sıra, karakter sınırı.
NOT_RAKAM = ("page", "pageSize", "ayarlar", "kanalCari", "window", "status.last", "status.startedAt", "status.finishedAt",
             "esikler", "metinTurleri", "sira",
             "kitaplar[].sira", "kitaplar[].hesap.sira")

F_SAYILAR = "Durum sayısı = kampanya kayıtlarının durumlarına göre sayısı; kitap sayısı = gece okumasındaki kitap satırları."
F_OZET = ("Kampanya özeti: kitap = kampanyadaki kitap sayısı; ortalama indirim = indirimlerin ortalaması; marj oranı (önce/"
          "sonra) = Σ marj ÷ Σ net (marjı bilinen kitaplarda); kırmızı/sarı = kontrol sayıları; maliyeti eksik ve stok riski = "
          "o kontrolü taşıyan kitap sayısı.")
F_SIM = ("Kitap hesabı (kurala göre, model yok): liste fiyatı = ayardaki kaynak (CRM ya da Logo, KDV dahil; elle girildiyse o); "
         "kampanya fiyatı = liste × (1 − indirim); net = fiyat ÷ (1 + KDV) × (1 − kanal kesintisi); telif = satıştan ödenen "
         "sözleşmelerin oranı × esas (liste, net ya da perakende); marj = net − birim maliyet − telif, marj oranı = marj ÷ net. "
         "Birim maliyet: fiyatlama modülünün birim maliyeti, yoksa Logo bu yıl Σ maliyet ÷ maliyetli adet. Günlük hız = son "
         "pencere net adet ÷ gün; tükenme = stok ÷ (hız × beklenen artış). Kontroller: asgari fiyat, son 30 gün en düşük site "
         "fiyatı, marj alt sınırı, hak, stok.")
F_ADAY = ("Aday kitap (kurala göre): stok ayı = stok ÷ aylık net adet; düşüş = 1 − son pencere ÷ önceki pencere net adet; "
          "sezon = kitabın bağlı olduğu özel gün kampanya tarihinden önceki gün sayısı içinde; marj oranı = varsayılan indirimde "
          "(net − birim maliyet − telif) ÷ net. Puan sinyallerin ağırlıklı toplamı; toplam = kurala uyan kitap sayısı.")
F_SONUC = ("Sonuç: her dönem (önce / kampanya / sonra) Σ adet, Σ iade, Σ net tutar; günlük adet = adet ÷ Logo kesimine kadar "
           "geçen gün; iade oranı = iade ÷ adet; marj = maliyetli tutar − maliyet, marj oranı = marj ÷ maliyetli tutar. Değişim: "
           "satış = kampanya günlük adet ÷ önce günlük adet; iade ve marj puanı = kampanya − önce. Kitap: dönem adetleri, "
           "değişim = kampanya adet ÷ önce adet. Seri: gün başına Σ adet ve Σ tutar.")
F_CRM = ("CRM bayi kampanyası etkisi: kampanyaya bağlı sipariş satırlarında Σ adet ve Σ tutar (CRM'de okunur; salt okuma). "
         "Tür gece sınıflamasıdır.")
F_OGRENIM = "Öğrenim kayıtları: kampanyanın özet rakamları öğrenim yazıldığı anda kampanya sonucundan kopyalanır."
F_KITAP = ("Kitap araması: stok = Logo stok bakiyesi; liste = ayardaki kaynaktan KDV dahil liste fiyatı; son 12 ay = net adet "
           "(gece okuması).")


def _kur(engine: Any, tenant: str, q: Y.Yakalanan, koken: Optional[dict[str, list[str]]] = None,
         basliklar: Optional[dict[str, str]] = None) -> Y.Kurucu:
    return Y.Kurucu(engine, tenant, q, prefix="kampanya", tablolar=TABLOLAR, koken={**KOKEN, **(koken or {})},
                    koken_basliklari={**KOKEN_BASLIK, **(basliklar or {})})


def _camp_fields(b: Y.Kurucu, prefix: str) -> dict[str, str]:
    """Kampanya nesnesinin rakamları: başlık alanları (indirim, kesinti, bütçe, artış), kitaplar ve özet."""
    head = b.hesap("kampanya", "Kampanya başlığındaki oranlar (varsayılan indirim, kanal kesintisi, beklenen artış) ve "
                               "bütçe kampanya kaydında girilen değerlerdir.", CAMPS)
    return {f"{prefix}varsayilanIndirim": head, f"{prefix}kanalKesinti": head, f"{prefix}beklenenArtis": head,
            f"{prefix}butce": head, f"{prefix}kitaplar": b.hesap("kitapHesabi", F_SIM, ITEMS, BOOKS, SNAPS),
            f"{prefix}ozet": b.hesap("ozet", F_OZET, ITEMS), f"{prefix}uyarilar": head, f"{prefix}metin": head}


def for_overview(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    f = {"sayilar": b.hesap("sayilar", F_SAYILAR, CAMPS, BOOKS), "kitapSayisi": "hesap:sayilar",
         "status.fiyatKaydi": b.hesap("fiyatKaydi", "Site fiyat kaydı: kayıtlı gün sayısı ve ilk gün, günlük site fiyatı "
                                                    "tablosundan (gece okumasında yazılır).", META, SNAPS),
         "takvim": b.hesap("takvim", "Takvim: özel günler, elle girilen dönemler ve kampanyalar tarih aralığında.", CAL, CAMPS, DAYS)}
    for key in ("onayBekleyen", "yurutulen"):
        f.update({k.replace("[]", "[]", 1): v for k, v in _camp_fields(b, f"{key}[].").items()})
        f[f"{key}"] = "hesap:ozet"
    return b.alanlar(f)


def for_calendar(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("takvim", "Takvim: özel günler, elle girilen dönemler ve kampanyalar tarih aralığında; çakışma = aynı kanal "
                          "ve platformda kesişen tarihler.", CAL, CAMPS, DAYS)
    return b.alanlar({"items": h, "kampanyalar": h, "cakismalar": h})


def for_candidates(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("aday", F_ADAY, BOOKS)
    return b.alanlar({"items": h, "total": h})


def for_books(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> Optional[P.Kaynaklar]:
    if not q.queries:
        return None   # arama iki harften kısa: sorgu koşmadı, rakam yok
    b = _kur(engine, tenant, q)
    h = b.hesap("kitap", F_KITAP, BOOKS)
    return b.alanlar({"items": h, "total": h})


def for_crm(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("crm", F_CRM, *[sid for sid, s in b.k.sources.items() if s["connection"] == "crm"], CRMT)
    return b.alanlar({"items": h, "total": h})


def for_list(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    f = _camp_fields(b, "items[].")
    f.update({"items": "hesap:ozet", "total": b.hesap("toplam", "Toplam = süzgece uyan kampanya sayısı.", CAMPS),
              "sayilar": b.hesap("sayilar", F_SAYILAR, CAMPS)})
    return b.alanlar(f)


def for_campaign(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar(_camp_fields(b, ""))


def for_results(engine: Any, tenant: str, cid: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    key = C.koken_sonuc(cid)
    b = _kur(engine, tenant, q, koken={RES: [key]}, basliklar={key: "Kampanya sonucu okuması"})
    h = b.hesap("sonuc", F_SONUC, RES, ITEMS)
    f = {"donemler": h, "degisim": h, "kitaplar": h, "seri": h, "ogrenimler": b.hesap("ogrenim", F_OGRENIM, LEARN)}
    if "crmEtki" in out:
        f["crmEtki"] = b.hesap("crm", F_CRM, *[sid for sid, s in b.k.sources.items() if s["connection"] == "crm"] or [RES])
    return b.alanlar(f)


def for_learnings(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("ogrenim", F_OGRENIM, LEARN)
    return b.alanlar({"items": h, "total": h})
