"""M42 Kanallar ve D2C: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`, yakalama `sorgu_yakala.py`).

Kanal karnesi, kanal detayı, kitap × kanal matrisi, hedefler ve D2C ekranları portaldaki kanal tablolarından
(`semantic_channel_*`) okunur. Uç çalışırken bu okumalar değerleriyle yakalanır; tabloları gece dolduran Logo/CRM
sorguları yıl anahtarıyla (`refresh.koken_yil(y)`) saklanır ve «asıl sorgu» (`origin`) olarak eklenir.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import refresh as RF

KANAL, CARI, BOOKM, BOOKS = ("semantic_channel_kanal_months", "semantic_channel_cari_months",
                             "semantic_channel_book_months", "semantic_channel_books")
ACC, SUG, BARC, TARG = ("semantic_channel_accounts", "semantic_channel_suggestions", "semantic_channel_barcodes",
                        "semantic_channel_crm_targets")
SETT, META, IMP, IMPR = ("semantic_channel_settings", "semantic_channel_meta", "semantic_channel_imports",
                         "semantic_channel_import_rows")
H3_ORD = "semantic_commerce_orders"

TABLOLAR = {
    KANAL: ("Kanal kodu × ay (Logo)", "Logo kanal kodu (cari özel kod) × ay: satış/iade ciro ve adet, brüt satış, iskonto, "
                                      "maliyet — şirket toplamı ve kanal kıyası."),
    CARI: ("Cari grubu × ay (Logo)", "E-ticaret carileri (cari grubu) × ay: satış/iade ciro ve adet, iskonto, maliyetli ciro, "
                                     "maliyet, maliyetsiz satır."),
    BOOKM: ("Kitap × cari grubu × ay (Logo)", "Kitap × cari grubu × ay: satış/iade adedi, net ciro, maliyet."),
    BOOKS: ("Kitap adları", "Stok kodu → kitap adı (Logo malzeme kartı)."),
    ACC: ("Cari ↔ platform eşlemesi", "Logo cari kartı, CRM karşılığı, önerilen/onaylı platform."),
    SUG: ("Kanal önerileri", "İskonto, stok payı ve D2C önerileri (taslak/onay)."),
    BARC: ("Barkodlar", "Barkod → stok kodu (Logo)."),
    TARG: ("CRM satış hedefleri", "Bölge × yıl hedefi (adet), aylık dağılım."),
    SETT: ("Kanal ayarları", "Kanal kodu/bölge eşlemesi ve ek kanal maliyeti."),
    META: ("Okuma bilgisi", "Logo veri sonu, yıl okumaları, CRM sipariş özeti, uyarılar."),
    IMP: ("Panel dosyaları", "Yüklenen pazar yeri panel dosyası (Excel/CSV) başlığı."),
    IMPR: ("Panel dosyası satırları", "Yüklenen dosyanın satırları: kitap, satış adedi (kişisel kolon alınmaz)."),
    H3_ORD: ("Site siparişleri", "Sitenin sipariş servisinden gece okunan siparişler (e-ticaret müşteri modülü)."),
}

#: Rakam olmayan sayılar: yıl ve ay numarası, sayfa, ayar, eşik ve kullanıcının girdiği simülasyon değerleri.
NOT_RAKAM = ("page", "pageSize", "period.yil", "period.ay", "years", "defaultYear", "missingScope", "settings", "extraCosts",
             "months", "yil", "aylik[].ay", "esik", "iskontoPuan", "hacimYuzde", "aralik.ay", "crmYilKodu", "oran",
             "bolgeler[].yil", "items[].yil", "data.years", "data.startedAt", "kanalaSatisAylari")

F_OLCU = ("Ölçüler (faturalı satır, Logo): net ciro = satış cirosu (TRCODE 7,8,9 LINENET) − iade cirosu (2,3); net adet = "
          "satış − iade adedi; iskonto oranı = iskonto ÷ brüt satış; iade oranı = iade cirosu ÷ satış cirosu; brüt kâr = "
          "maliyetli ciro − maliyet, marj = brüt kâr ÷ maliyetli ciro (yalnız maliyeti girilmiş satırlar); iade sonrası marj "
          "iadenin cirosu ve maliyeti düşülerek; katkı = iade sonrası brüt kâr − net ciro × ek kanal maliyeti oranı.")
F_DONEM = ("Dönem: yılın başından seçilen aya kadar; veri sonunun ayı kısmi ise o ay gün payıyla (gün ÷ ayın gün sayısı) "
           "ağırlıklandırılır. Geçen yıl aynı dönem aynı ağırlıklarla.")
F_KARNE = (F_OLCU + " Platform = cari grubunun (eşlemedeki) platformu; değişim = net ciro ÷ geçen yıl − 1; pay (e-ticaret) = "
           "platform net cirosu ÷ e-ticaret carileri toplamı; pay (şirket) = ÷ bütün kanal kodlarının toplamı; bu ay = yalnız "
           "seçilen ay. " + F_DONEM)
F_HEDEF = ("Hedef: CRM bölge hedefi (adet) platforma eşlenen bölgelerden; bütçe (onaylı plan) kanal hedefi = kitap hedefi × "
           "kanalın geçen yıl o kitaptaki net adet payı (kitap o yıl kanalda yoksa kanalın genel payı).")
F_KITAP = ("Kitap: satış adedi, iade adedi, net adet = satış − iade, net ciro, iade oranı = iade ÷ satış adedi; marj "
           "maliyetli satırlardan. " + F_DONEM)
F_IADE = "İadeler: son N ayda (seçilen ay dahil) kanala iade edilen kitaplar; iade adedi büyükten küçüğe."
F_MATRIS = "Matris: hücre = kitabın o platformdaki net adedi (satış − iade), alım (satış) ve iade adedi; toplam = bütün platformlar."
F_SIM = ("İskonto simülasyonu (kurala göre): yeni iskonto = brüt satış × Δ puan; adet değişimi brüt satışı, net satışı ve "
         "maliyeti aynı oranda değiştirir; iade oranı sabit; marj maliyetli satırlardan; başabaş = aynı brüt kârı korumak "
         "için gereken adet değişimi. Taban seçilen dönemin kanal ölçüleridir.")
F_D2C = ("D2C: site platformunun (timas.com.tr) net cirosu ve e-ticaret içindeki payı karneden; güçlü kitap = D2C'deki payı "
         "genel D2C payının ayardaki indeks katından yüksek ve en az ayardaki adedi olan kitap. Site özeti (sipariş, ciro, "
         "müşteri, tekrar oranı, sepet) site sipariş tablosundan.")
F_ESLEME = "Eşleme: cari kartı sayıları ve durumlar (önerilen / onaylı / platform değil) eşleme kaydından."
F_KANALKOD = "Kanal kodu: bu yılın kanal kodu × ay tablosunda Σ (satış cirosu − iade cirosu)."
F_BOLGE = "Bölge: CRM hedef satırı; yıllık = hedef toplamı, aylık toplam = aylık dağılımın toplamı, satır = hedef satır sayısı."
F_ONERI = "Öneri: simülasyon ve D2C set önerisinin rakamları öneri kaydında saklanır (oluşturulduğu andaki hesap)."
F_DOSYA = ("Panel dosyası: yüklenen dosyadaki satış (sell-through) adetleri ile aynı dönemde kanala satış (Logo sell-in) "
           "adetleri kitap başına yan yana; oran = panel satışı ÷ kanala satış.")
F_META = "Okuma bilgisi: yıl okumalarının satır sayıları, son okuma zamanı, CRM sipariş tipleri ve uyarı sayıları okuma kaydından."


def _years(out: dict[str, Any], extra: Iterable[int] = ()) -> list[int]:
    ys: set[int] = {int(y) for y in extra}
    p = out.get("period") if isinstance(out, dict) else None
    if isinstance(p, dict) and p.get("yil"):
        ys |= {int(p["yil"]), int(p["yil"]) - 1}
    return sorted(ys)


def _kur(engine: Any, tenant: str, q: Y.Yakalanan, years: Iterable[int] = ()) -> Y.Kurucu:
    keys = [RF.koken_yil(y) for y in years]
    koken = {KANAL: keys, CARI: keys, BOOKM: keys, ACC: [RF.KOKEN_OKUMA], BOOKS: [RF.KOKEN_OKUMA], BARC: [RF.KOKEN_OKUMA],
             TARG: [f"{RF.KOKEN_OKUMA}.hedef.{y}" for y in years], META: [RF.KOKEN_OKUMA]}
    titles = {RF.koken_yil(y): f"Kanal okuması · {y}" for y in years}
    titles.update({f"{RF.KOKEN_OKUMA}.hedef.{y}": f"CRM hedef okuması · {y}" for y in years})
    titles[RF.KOKEN_OKUMA] = "Kanal okuması (kart, CRM, ad, barkod)"
    return Y.Kurucu(engine, tenant, q, prefix="kanal", tablolar=TABLOLAR, koken=koken, koken_basliklari=titles)


def for_meta(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, out.get("years") or [])
    h = b.hesap("okuma", F_META, META)
    return b.alanlar({"data": h, "alerts": h, "crmOrders": h})


def for_scorecard(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, _years(out))
    k = b.hesap("karne", F_KARNE, CARI, KANAL, ACC)
    return b.alanlar({"platforms": k, "platforms[].hedef": b.hesap("hedef", F_HEDEF, TARG, CARI), "toplam": k,
                      "platformDisi": k, "kanallar": b.hesap("kanalKiyas", F_OLCU + " Kanal kodu başına; pay = ÷ şirket.", KANAL),
                      "period": b.hesap("donem", F_DONEM, META)})


def for_channel(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, _years(out))
    k = b.hesap("kanal", F_KARNE, CARI, ACC)
    f = {"donem": k, "gecenYil": k, "degisim": k, "aylik": b.hesap("aylik", F_OLCU + " Ay ay, bu yıl ve geçen yıl.", CARI),
         "cariler": b.hesap("cariler", F_OLCU + " Cari grubu başına; CRM sipariş sayısı son N günün CRM siparişlerinden.",
                            CARI, META), "crmSiparisGun": "hesap:cariler", "hedef": b.hesap("hedef", F_HEDEF, TARG, CARI),
         "period": b.hesap("donem", F_DONEM, META), "imports": b.hesap("dosya", F_DOSYA, IMP)}
    return b.alanlar(f)


def for_books(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, _years(out))
    h = b.hesap("kitap", F_KITAP, BOOKM, BOOKS)
    return b.alanlar({"items": h, "total": h, "period": b.hesap("donem", F_DONEM, META)})


def for_returns(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    ys = _years(out)
    ar = out.get("aralik") or {}
    if ar.get("bas"):
        ys = sorted(set(ys) | {int(str(ar["bas"])[:4])})
    b = _kur(engine, tenant, q, ys)
    h = b.hesap("iade", F_IADE + " " + F_KITAP, BOOKM, BOOKS)
    return b.alanlar({"items": h, "total": h, "period": b.hesap("donem", F_DONEM, META)})


def for_matrix(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, _years(out))
    h = b.hesap("matris", F_MATRIS, BOOKM, BOOKS)
    return b.alanlar({"items": h, "total": h, "columns": h, "period": b.hesap("donem", F_DONEM, META)})


def for_targets(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, _years(out))
    h = b.hesap("hedef", F_HEDEF, TARG, CARI, BOOKM)
    return b.alanlar({"crm": h, "bolgeler": b.hesap("bolge", F_BOLGE, TARG), "m46": h, "period": b.hesap("donem", F_DONEM, META)})


def for_simulate(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, _years(out))
    h = b.hesap("simulasyon", F_SIM + " " + F_OLCU, CARI)
    f = {k: h for k in out if k not in ("platform", "label", "iskontoPuan", "hacimYuzde", "period", "kaynaklar")}
    f["period"] = b.hesap("donem", F_DONEM, META)
    return b.alanlar(f)


def for_accounts(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    h = b.hesap("esleme", F_ESLEME, ACC, META)
    return b.alanlar({"items": h, "counts": h, "cards": h})


def for_kanal_codes(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, [out["yil"]] if out.get("yil") else [])
    return b.alanlar({"items": b.hesap("kanalKod", F_KANALKOD, KANAL)})


def for_regions(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    ys = sorted({int(x["yil"]) for x in out.get("items") or [] if x.get("yil")})
    b = _kur(engine, tenant, q, ys)
    return b.alanlar({"items": b.hesap("bolge", F_BOLGE, TARG)})


def for_d2c(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, _years(out))
    h = b.hesap("d2c", F_D2C + " " + F_KARNE, CARI, KANAL, BOOKM, H3_ORD)
    f = {"d2c": h, "toplam": h, "site": b.hesap("site", F_D2C, H3_ORD), "kitaplar": h, "genelD2cPay": h, "d2cAdet": h,
         "pazarYeriAdet": h, "period": b.hesap("donem", F_DONEM, META)}
    if "oneriler" in out:
        f["oneriler"] = b.hesap("oneri", F_ONERI, SUG)
    return b.alanlar(f)


def for_suggestions(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"items": b.hesap("oneri", F_ONERI, SUG)})


def for_imports(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q)
    return b.alanlar({"items": b.hesap("dosya", F_DOSYA, IMP, IMPR)})


def for_import(engine: Any, tenant: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    ys = sorted({int(str(m)[:4]) for m in out.get("kanalaSatisAylari") or []})
    b = _kur(engine, tenant, q, ys)
    h = b.hesap("dosya", F_DOSYA, IMP, IMPR, BOOKM)
    return b.alanlar({k: h for k, v in out.items() if k not in ("kanalaSatisAylari",)})
