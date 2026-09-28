"""M40 Trendyol ve M41 Amazon/yurtdışı: ekrandaki her rakamın sorgu bilgisi (sözleşme `provenance.py`, yakalama
`sorgu_yakala.py`).

Trendyol rakamları satıcı panelinden yüklenen dosyaların satırlarından (portal `semantic_trendyol_*`) ve Logo stok/fiyat
okumasından (`trendyol.KOKEN_LOGO`) gelir; platforma istek gönderilmez, dosyanın SQL'i yoktur — hesap metninde «panel
dosyası» yazar. Amazon/yurtdışı rakamları gece okumasının (`amazon.KOKEN_OKUMA`, Logo + CRM) doldurduğu `semantic_intl_*`
tablolarından gelir. Toptan (kanala satış) satırı kanal karnesinin tablolarından (yıl okuması köken).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import amazon as A
from semantic_bridge.channels import kaynak as KK
from semantic_bridge.channels import refresh as RF
from semantic_bridge.channels import trendyol as TY

TY_T = {
    "semantic_trendyol_imports": ("Trendyol panel dosyaları", "Yüklenen satıcı paneli dışa aktarımları: tür, dosya, satır, eşleşen."),
    "semantic_trendyol_products": ("Trendyol ürünleri (panel dosyası)", "Ürün listesi dosyası: barkod, satıcı stok kodu, "
                                   "Trendyol stoğu, satış fiyatı, satışa açık mı."),
    "semantic_trendyol_orders": ("Trendyol siparişleri (panel dosyası)", "Sipariş dosyası: paket, tarih, durum, adet, tutar."),
    "semantic_trendyol_claims": ("Trendyol iadeleri (panel dosyası)", "İade dosyası: talep, neden, sınıf."),
    "semantic_trendyol_questions": ("Trendyol soruları (panel dosyası)", "Soru dosyası: soru tarihi, cevaplandı mı."),
    "semantic_trendyol_reviews": ("Trendyol yorumları (panel dosyası)", "Yorum dosyası: puan, tarih."),
    "semantic_trendyol_logo": ("Logo stok ve fiyatı (Trendyol kitapları)", "Logo depo stoğu, liste fiyatı ve site fiyatı; "
                               "yalnız Trendyol dosyalarında geçen kitaplar."),
}
AM_T = {
    "semantic_intl_consignment": ("Amazon konsinye", "Konsinye sevk ve dönüş: kitap × yıl adetleri (Logo)."),
    "semantic_intl_sales": ("Yurtdışı satış", "Yurtdışı carileri × ay: satış/iade ciro ve adet, döviz (Logo)."),
    "semantic_intl_books": ("Yurtdışı kitaplar", "Yurtdışı satışında kitap kırılımı (Logo)."),
    "semantic_intl_rights": ("Yurtdışı hakları", "CRM Telif Satış sözleşmeleri: kitap × ülke hakkı."),
    "semantic_intl_params": ("Pazar parametreleri", "Girilen pazar parametreleri: KDV, kargo, komisyon oranı."),
    "semantic_intl_drafts": ("Pazar taslakları", "Zeki AI ürün sayfası taslakları (metin; rakam yok)."),
    "semantic_intl_market_cards": ("Pazar kartları", "Yeni pazar değerlendirme kartları ve kararları."),
}
COMMON = {k: v for k, v in KK.TABLOLAR.items() if k.startswith("semantic_channel_")}
TABLOLAR = {**TY_T, **AM_T, **COMMON}

#: Rakam olmayan sayılar: sayfa, ayarlar ve eşikler (Yönetim ekranı), yıl/ay numaraları, kullanıcının girdiği parametre.
NOT_RAKAM = ("page", "pageSize", "settings", "esik", "listeKdv", "esikSaat", "minStok", "pencereGun", "labels", "kume",
             "yil", "sonAy", "yillar", "aylik[].ay", "toptan.period.yil", "toptan.period.ay", "period.yil", "period.ay",
             "logo.listeKdv", "logo.firm", "read.yil", "read.firm", "job", "yurtdisi.yil", "yurtdisi.sonAy")

PANEL = ("Kaynak: Trendyol satıcı panelinden indirilen dosya (yükleme ekranında dosya adı ve tarihi); platforma istek "
         "gönderilmez. Gösterilen SQL dosya satırlarının portal tablosundan okunmasıdır.")
F_TY_OZET = ("Trendyol özeti: ürün = ürün dosyasındaki satır, satışa açık = satışa açık işaretli; stok farkı türleri = Logo "
             "depo stoğu ile Trendyol stoğunun karşılaştırması; cevapsız/geciken soru; yorum ortalaması ve düşük puan (≤ 3); "
             "paket ve geciken paket (kargo süresi aşan). " + PANEL)
F_TOPTAN = ("Toptan (kanala satış): kanal karnesinde bu platforma eşlenen Logo carilerinin net cirosu, net adedi, iade oranı "
            "ve geçen yıla göre değişimi (faturalı satır, satış − iade).")
F_STOK = ("Stok farkı: Trendyol stoğu (ürün dosyası) ile Logo depo stoğu; Logo stoğu ayardaki en az depo stoğunun altındayken "
          "satışta, Trendyol stoğu Logo'dan fazla, vb. türler. Sayılar tür başına kitap. " + PANEL)
F_FIYAT = ("Fiyat farkı: Trendyol satış fiyatı ile Logo liste fiyatı (KDV dahil, ayardaki KDV ile) ve site fiyatı; indirim = "
           "1 − Trendyol ÷ liste; ayardaki en çok indirimi aşan ya da birim maliyetin altında kalan işaretlenir. " + PANEL)
F_URUN = "Ürünler: ürün dosyası satırları; Logo stok ve fiyatı Logo okumasından. " + PANEL
F_SIPARIS = ("Siparişler: paket sayısı, adet, tutar sipariş dosyasından; geciken = kargoya veriliş süresi aşan paket; kitaplar "
             "= kitap başına adet ve tutar. " + PANEL)
F_IADE = "İadeler: talep sayısı, sınıf başına talep (kurala göre sınıf, bulunamazsa Zeki AI kapalı küme seçimi), kitap başına. " + PANEL
F_SORU = "Sorular: cevapsız ve ayardaki saatten uzun bekleyen (geciken) sorular. " + PANEL
F_YORUM = "Yorumlar: puan ortalaması, düşük puanlı (≤ 3) yorum sayısı, kitap başına. " + PANEL
F_VITRIN = ("Vitrin adayı (kurala göre): son N günde satış hızı = adet ÷ gün, Logo stoğu en az ayardaki adet; hız büyükten "
            "küçüğe. " + PANEL)
F_HAFTA = ("Haftalık: seçilen haftanın (7 gün) paket, adet, tutar, geciken; iade talebi ve sınıfları; cevapsız soru; yorum "
           "(hafta, düşük, ortalama); stok farkı sayıları. Zeki AI özeti yalnız bu olguları açıklar. " + PANEL)
F_DOSYA = "Panel dosyası: dosyanın satır sayısı, kitaba eşleşen satır, içeri alınmayan (kişisel olabilir) kolonlar."
F_ONERI = "Öneri: vitrin önerisinin kitapları ve hızları öneri kaydında (oluşturulduğu andaki hesap)."
F_CARI = "Aday cariler: Logo'da adı ayardaki desenlere uyan cariler (gece okuması) ve eşleme durumu."

F_AM_OZET = ("Amazon/yurtdışı özeti: konsinye (sevk, dönüş, elde kalan) ve yurtdışı satış (net ciro, adet, geçen yıl, ülke "
             "sayısı, döviz) gece okumasının tablolarından; haklar = CRM Telif Satış sözleşmelerinde yurtdışı hakkı olan kitap "
             "ve sözleşme sayısı; taslak ve bekleyen kart kayıt sayısı.")
F_KONSINYE = ("Konsinye: kitap başına sevk − dönüş = elde kalan (Logo konsinye fişleri, ayardaki tip); faturalanan = aynı yıl "
              "Amazon'a faturalanan net adet (kanal karnesi kitap tablosu).")
F_YURTDISI = ("Yurtdışı: ayardaki yurtdışı cari kodları; net ciro = satış − iade (faturalı satır), ülke başına, ay başına; geçen "
              "yıl aynı dönem sonAy'a kadar; döviz toplamı fatura dövizine göre.")
F_HAK = "Haklar: CRM Telif Satış sözleşmelerinde kitap × ülke hakkı, sözleşme başına."
F_PARAM = "Pazar parametreleri: Yönetim yetkilisinin girdiği KDV, kargo birimi ve komisyon oranı (portal kaydı)."
F_KART = "Pazar kartları: değerlendirme kaydı; rakamlar kartın açıldığı andaki konsinye/yurtdışı olgularından."


def _years(out: dict[str, Any]) -> list[int]:
    t = out.get("toptan") if isinstance(out, dict) else None
    p = (t or {}).get("period") or out.get("period") if isinstance(out, dict) else None
    if isinstance(p, dict) and p.get("yil"):
        return [int(p["yil"]), int(p["yil"]) - 1]
    return []


def _kur(engine: Any, tenant: str, q: Y.Yakalanan, out: dict[str, Any], prefix: str) -> Y.Kurucu:
    ys = _years(out)
    keys = [RF.koken_yil(y) for y in ys]
    koken = {"semantic_trendyol_logo": [TY.KOKEN_LOGO], "semantic_channel_cari_months": keys,
             "semantic_channel_kanal_months": keys, "semantic_channel_book_months": keys,
             "semantic_channel_barcodes": [RF.KOKEN_OKUMA, TY.KOKEN_LOGO],
             "semantic_intl_consignment": [A.KOKEN_OKUMA], "semantic_intl_sales": [A.KOKEN_OKUMA],
             "semantic_intl_books": [A.KOKEN_OKUMA], "semantic_intl_rights": [A.KOKEN_OKUMA],
             "semantic_channel_meta": [TY.KOKEN_LOGO] if prefix == "trendyol" else [A.KOKEN_OKUMA]}
    titles = {TY.KOKEN_LOGO: "Trendyol Logo okuması (stok, fiyat, barkod)", A.KOKEN_OKUMA: "Amazon ve yurtdışı gece okuması",
              RF.KOKEN_OKUMA: "Kanal okuması (kart, ad, barkod)"}
    titles.update({RF.koken_yil(y): f"Kanal okuması · {y}" for y in ys})
    return Y.Kurucu(engine, tenant, q, prefix=prefix, tablolar=TABLOLAR, koken=koken, koken_basliklari=titles)


def _map(b: Y.Kurucu, out: dict[str, Any], ref: str, special: Optional[dict[str, str]] = None,
         skip: Iterable[str] = ()) -> P.Kaynaklar:
    """Cevabın bütün üst anahtarları bu hesaba (rakam olmayanlar NOT_RAKAM'da); özel anahtarlar kendi hesabına."""
    special = dict(special or {})
    skip = set(skip) | {"kaynaklar", "page", "pageSize"}
    f = {k: ref for k in out if k not in skip and k not in special}
    f.update({k: v for k, v in special.items() if k in out})
    return b.alanlar(f)


def _toptan(b: Y.Kurucu) -> str:
    return b.hesap("toptan", F_TOPTAN, "semantic_channel_cari_months", "semantic_channel_accounts")


# ------------------------------------------------------------------ Trendyol


def ty_overview(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, out, "trendyol")
    return _map(b, out, b.hesap("ozet", F_TY_OZET, *TY_T), {"toptan": _toptan(b),
                                                            "yuklemeler": b.hesap("dosya", F_DOSYA, "semantic_trendyol_imports")})


def ty_accounts(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, out, "trendyol")
    return _map(b, out, b.hesap("cari", F_CARI, "semantic_channel_meta", "semantic_channel_accounts"), {"toptan": _toptan(b)})


def ty_list(kind: str):
    formulas = {"urun": (F_URUN, ("semantic_trendyol_products", "semantic_trendyol_logo")),
                "stok": (F_STOK, ("semantic_trendyol_products", "semantic_trendyol_logo")),
                "fiyat": (F_FIYAT, ("semantic_trendyol_products", "semantic_trendyol_logo")),
                "siparis": (F_SIPARIS, ("semantic_trendyol_orders",)), "iade": (F_IADE, ("semantic_trendyol_claims",)),
                "soru": (F_SORU, ("semantic_trendyol_questions",)), "yorum": (F_YORUM, ("semantic_trendyol_reviews",)),
                "vitrin": (F_VITRIN, ("semantic_trendyol_orders", "semantic_trendyol_logo")),
                "hafta": (F_HAFTA, tuple(TY_T)), "dosya": (F_DOSYA, ("semantic_trendyol_imports",)),
                "oneri": (F_ONERI, ("semantic_channel_suggestions",))}
    text, tables = formulas[kind]

    def build(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
        b = _kur(engine, tenant, q, out, "trendyol")
        special = {}
        if "logo" in out:
            special["logo"] = b.hesap("logoOkuma", "Logo okuması: okunan kitap ve barkod sayısı, veri sonu.",
                                      "semantic_channel_meta")
        if "yuklemeler" in out:
            special["yuklemeler"] = b.hesap("dosya", F_DOSYA, "semantic_trendyol_imports")
        return _map(b, out, b.hesap(kind, text, *tables), special)
    return build


# ------------------------------------------------------------------ Amazon ve yurtdışı


def am_overview(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, out, "amazon")
    return _map(b, out, b.hesap("ozet", F_AM_OZET, *AM_T, "semantic_channel_meta"), {"toptan": _toptan(b)})


def am_list(kind: str):
    formulas = {"cari": (F_CARI, ("semantic_channel_meta", "semantic_channel_accounts")),
                "kitap": (KK.F_KITAP, ("semantic_channel_book_months", "semantic_channel_books")),
                "konsinye": (F_KONSINYE, ("semantic_intl_consignment", "semantic_channel_book_months")),
                "yurtdisi": (F_YURTDISI, ("semantic_intl_sales",)), "yurtdisiKitap": (F_YURTDISI, ("semantic_intl_books",)),
                "hak": (F_HAK, ("semantic_intl_rights",)), "param": (F_PARAM, ("semantic_intl_params",)),
                "taslak": ("Taslaklar: kayıt sayısı; taslak metni Zeki AI'dan, kaynağı olmayan rakam atılır.", ("semantic_intl_drafts",)),
                "kart": (F_KART, ("semantic_intl_market_cards",)),
                "okuma": ("Okuma bilgisi: gece okumasının okunan satır sayıları, veri sonu, ayarlar.", ("semantic_channel_meta",))}
    text, tables = formulas[kind]

    def build(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
        b = _kur(engine, tenant, q, out, "amazon")
        special = {"toptan": _toptan(b)} if "toptan" in out else {}
        return _map(b, out, b.hesap(kind, text, *tables), special)
    return build
