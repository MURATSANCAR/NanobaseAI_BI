"""H3 E-ticaret müşterileri: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`, yakalama `sorgu_yakala.py`).

Sipariş, satır ve müşteri tabloları sitenin (T-soft) sipariş servisinden gece okunur; bu okumanın SQL'i yoktur (dış
servis). Ekranda gösterilen SQL uçta bu tablolardan okuyan ifadelerin kendisidir; hesap metninde kaynak adı yazar.
Logo uzlaşması (D2C net ciro) kanal karnesinin tablolarından okunur; onları dolduran Logo sorgusu `origin` olarak eklenir.
Kişisel veri: SQL metni gösterilir, sonuç satırı hiçbir zaman kayda girmez.
"""
from __future__ import annotations

from typing import Any

from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y

ORD, LIN, CUS, MOV, PST = ("semantic_commerce_orders", "semantic_commerce_order_lines", "semantic_commerce_customers",
                           "semantic_commerce_segment_moves", "semantic_commerce_product_stats")
TRG, RUN, MEM, CMP, META = ("semantic_commerce_triggers", "semantic_commerce_trigger_runs", "semantic_commerce_run_members",
                            "semantic_commerce_campaigns", "semantic_commerce_meta")
KANAL_KOKEN = "kanal.okuma"   # channels.refresh.KOKEN_OKUMA — kanal tablolarını dolduran Logo sorguları

TABLOLAR = {
    ORD: ("Site siparişleri", "Sitenin sipariş servisinden gece okunan siparişler: tarih, durum, geçerli mi, tutar, müşteri anahtarı."),
    LIN: ("Sipariş satırları", "Sipariş başına kitap satırları: barkod, adet, tutar."),
    CUS: ("Site müşterileri (RFM)", "Müşteri anahtarı başına sipariş sayısı, ciro, ilk/son sipariş, segment ve R/F/M puanı."),
    MOV: ("Segment geçişleri", "Müşterinin segmentinin değiştiği anlar."),
    PST: ("Ürün sayaçları (günlük)", "Sitedeki ürün görüntülenme sayacının gece farkı."),
    TRG: ("Tetikler", "Kayıtlı tetik tanımları."),
    RUN: ("Tetik listeleri", "Tetik koşusu: aday, bağlı okur, ulaşılabilir, hedef ve kontrol sayıları."),
    MEM: ("Liste üyeleri", "Koşunun hedef ve kontrol grubu üyeleri (anahtarlar)."),
    CMP: ("Kampanya sonucu", "Kampanyanın hedef/kontrol sonucu (son hesap)."),
    META: ("Okuma bilgisi", "Site okumasının zamanı, sayıları ve hataları."),
    "semantic_channel_kanal_months": ("Kanal ay satışı (Logo)", "Kanal karnesinin Logo ay tablosu."),
    "semantic_channel_cari_months": ("Cari ay satışı (Logo)", "Kanal karnesinin Logo cari ay tablosu."),
    "semantic_channel_accounts": ("Kanal cari eşlemesi", "Cari → platform eşlemesi."),
}
KOKEN = {"semantic_channel_kanal_months": [KANAL_KOKEN], "semantic_channel_cari_months": [KANAL_KOKEN]}
KOKEN_BASLIK = {KANAL_KOKEN: "Kanal karnesi okuması"}

#: Rakam olmayan sayılar: istekteki gün sayısı, sayfa, ayar ve eşikler, tetik parametreleri (kullanıcının girdiği değerler).
NOT_RAKAM = ("page", "pageSize", "days", "minViews", "rules", "gun", "settings", "defaults", "limits", "values", "job",
             "items[].params", "items[].lastRun.params", "items[].controlShare", "items[].lastRun.controlShare",
             "params", "controlShare", "run.params", "run.controlShare", "logo.yil", "logo.ay")

SITE = "Site siparişleri sitenin sipariş servisinden gece okunur (T-soft); iptal/iade edilen sipariş «geçerli değil» sayılır."
F_OZET = (SITE + " Dönem (dün / 7 gün / bu ay) ve önceki eşit dönem: sipariş = geçerli sipariş sayısı, ciro = Σ tutar, "
          "sepet = ciro ÷ sipariş, müşteri = tekil müşteri anahtarı, yeni = ilk geçerli siparişi bu dönemde olan, tekrar = "
          "müşteri − yeni, iptal = geçersiz sipariş, misafir = üyeliksiz. Değişim = bu dönem ÷ önceki − 1.")
F_TOP = "En çok satanlar: dönemdeki geçerli siparişlerin satırlarında barkod başına Σ adet, Σ tutar, sipariş sayısı."
F_DUSUS = ("Düşüş uyarısı: dünün geçerli sipariş sayısı ÷ önceki dört haftanın aynı gününün ortalaması; düşüş = 1 − oran, "
           "ayardaki yüzdeyi aşarsa uyarı.")
F_LOGO = ("Logo uzlaşması: kanal karnesinde site platformuna eşlenen carilerin ay net cirosu (faturalı satır, KDV hariç, "
          "iade eksi) ile aynı ayın site sipariş tutarı; fark = site − Logo, oran = site ÷ Logo − 1.")
F_SEG = ("Segment: müşteri başına sipariş sayısı, ciro ve son sipariş gününe göre kural (aktif gün, sadık sipariş ve ciro "
         "eşikleri); pay = segmentteki müşteri ÷ toplam müşteri.")
F_RFM = "RFM matrisi: R (son siparişten bu yana gün aralığı) × F (sipariş sayısı aralığı) hücresinde müşteri sayısı ve Σ ciro."
F_GECIS = "Segment geçişi: son N günde bir segmentten ötekine geçen müşteri sayısı; kaybettiği = segmentten çıkanlar."
F_MUSTERI = "Müşteri: sipariş sayısı, ciro, ilk/son sipariş ve R/F/M puanı müşteri tablosundan (gece hesaplanır)."
F_KART = ("Müşteri kartı: siparişler ve satırları site sipariş tablosundan; iade/iptal = geçerli olmayan sipariş sayısı; "
          "kategori adedi = müşterinin aldığı kitapların kategori ağacı düğümüne göre adet.")
F_HUNI = ("Ürün hunisi: görüntülenme = son N günün gece sayaç farkları toplamı (ürün sayacı), adet/tutar/sipariş = aynı "
          "dönemin geçerli sipariş satırları; oran = adet ÷ görüntülenme; zayıf = görüntülenmesi eşik üstünde, oranı en düşük "
          "olanlar. Kapsanan gün = sayaç farkı olan gün sayısı.")
F_TETIK = ("Tetik listesi: aday = tetik kuralına uyan müşteri; bağlı = okur kaydına bağlanan; ulaşılabilir = seçilen kanalda "
           "izni olan; hedef ve kontrol = ulaşılabilirlerin kontrol payıyla bölünmesi (anahtara göre sabit).")
F_KAMPANYA = ("Kampanya sonucu: hedef ve kontrol grubunda pencere içinde geçerli siparişi olan kişi (alan), sipariş, ciro; "
              "oran = alan ÷ kişi; fark = hedef oranı − kontrol oranı, %95 güven aralığı iki oranın farkı (normal yaklaşım); "
              "ek alan = fark × hedef kişi; ek ciro = (hedef − kontrol kişi başına ciro) × hedef kişi.")
F_TAZELIK = "Okuma bilgisi: son okumanın okunan sipariş, geçersiz, anahtarsız ve üye sayıları (okuma kaydından)."
F_YENI = "Yeni kitaplar: kategori ağacı kitap profilinde son N günde açılan, barkodlu ve etkin kartlar."


def _kur(engine: Any, tenant: str, q: Y.Yakalanan, logo_year: Any = None) -> Y.Kurucu:
    koken, titles = dict(KOKEN), dict(KOKEN_BASLIK)
    if logo_year:
        # Kanal karnesinin yıl tabloları o yılın okumasıyla dolar (channels.refresh.koken_yil).
        keys = [f"{KANAL_KOKEN}.{int(logo_year)}", KANAL_KOKEN]
        koken.update({"semantic_channel_kanal_months": keys, "semantic_channel_cari_months": keys})
        titles[keys[0]] = f"Kanal karnesi okuması · {int(logo_year)}"
    return Y.Kurucu(engine, tenant, q, prefix="commerce", tablolar=TABLOLAR, koken=koken, koken_basliklari=titles)


def for_overview(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, (out.get("logo") or {}).get("yil"))
    oz = b.hesap("ozet", F_OZET, ORD)
    f = {"cur": oz, "prev": oz, "change": oz, "top": b.hesap("top", F_TOP, LIN, ORD),
         "freshness": b.hesap("tazelik", F_TAZELIK, META, ORD), "drop": b.hesap("dusus", F_DUSUS, ORD),
         "segments": b.hesap("segment", F_SEG, CUS)}
    if out.get("logo"):
        f["logo"] = b.hesap("logo", F_LOGO, "semantic_channel_kanal_months", "semantic_channel_cari_months", ORD)
    return b.alanlar(f)


def for_rfm(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"matrix": b.hesap("rfm", F_RFM, CUS), "segments": b.hesap("segment", F_SEG, CUS),
                      "moves": b.hesap("gecis", F_GECIS, MOV)})


def for_moves(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("gecis", F_GECIS, MOV)
    return b.alanlar({"items": h, "kaybettigi": h})


def for_customers(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("musteri", F_MUSTERI, CUS)
    return b.alanlar({"items": h, "total": h})


def for_customer(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    m = b.hesap("musteri", F_MUSTERI, CUS)
    k = b.hesap("kart", F_KART, ORD, LIN)
    return b.alanlar({"siparis": m, "ciro": m, "r": m, "f": m, "m": m, "siparisler": k, "iadeIptal": k, "kategoriler": k,
                      "gecisler": b.hesap("gecis", F_GECIS, MOV)})


def for_funnel(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("huni", F_HUNI, PST, LIN, ORD)
    return b.alanlar({"items": h, "total": h, "weakCount": h, "coveredDays": h})


def for_new_books(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"items": b.hesap("yeni", F_YENI)})


def for_triggers(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"items": b.hesap("tetik", F_TETIK, RUN, TRG)})


def for_runs(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("tetik", F_TETIK, RUN)
    return b.alanlar({"items": h, "total": h})


def for_run(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("tetik", F_TETIK, RUN)
    return b.alanlar({"candidates": h, "linked": h, "reachable": h, "target": h, "control": h, "excluded": h,
                      "exportedCount": h, "info": h})


def for_campaigns(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"items": b.hesap("kampanya", F_KAMPANYA, CMP)})


def for_campaign(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"result": b.hesap("kampanya", F_KAMPANYA, ORD, MEM, CMP), "run": b.hesap("tetik", F_TETIK, RUN)})


def for_segments_summary(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("segment", F_SEG + " Tekrar oranı = birden fazla siparişi olan ÷ alıcı.", CUS)
    return b.alanlar({"segmentler": h, "alici": h, "tekrarAlan": h, "tekrarOrani": h, "aktifTekrar": h})


def for_meta(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"freshness": b.hesap("tazelik", F_TAZELIK, META, ORD)})
