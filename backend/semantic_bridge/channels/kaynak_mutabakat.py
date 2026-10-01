"""Aşama 0 (satış modeli) ve Aşama 1 (mutabakat, hakediş): ekrandaki her rakamın sorgu bilgisi (sözleşme `provenance.py`,
yakalama `sorgu_yakala.py`).

Model ekranı ölçüm toplamlarını portal kaydından (`semantic_channel_meta` › `model:<platform>`) okur; o toplamları
dolduran Logo/CRM sorguları «asıl sorgu» (`model.<platform>`) olarak eklenir. Mutabakat ve hakediş rakamları panel
dosyası satırlarından (portal) ve Logo okumasının yazdığı tablolardan (`semantic_mp_logo_*`, asıl sorgu
`mutabakat.<platform>`) gelir.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y
from semantic_bridge.channels import mutabakat as MU
from semantic_bridge.channels import pazaryeri_model as PM

TABLOLAR = {
    "semantic_channel_meta": ("Ölçüm ve okuma kaydı", "Satış modeli ölçümünün ham toplamları ve mutabakat okumasının özeti."),
    "semantic_channel_accounts": ("Cari ↔ platform eşlemesi", "M42 eşlemesinde platforma bağlı cariler."),
    "semantic_channel_barcodes": ("Barkodlar", "Barkod → stok kodu (Logo)."),
    "semantic_trendyol_orders": ("Trendyol siparişleri (panel dosyası)", "Sipariş dosyası: paket, sipariş no, tarih, durum, adet, tutar."),
    "semantic_trendyol_claims": ("Trendyol iadeleri (panel dosyası)", "İade dosyası: talep, sipariş no, durum, adet."),
    "semantic_mp_orders": ("Pazar yeri sipariş/iade raporu (panel dosyası)", "Sipariş no, barkod/SKU, tarih, durum, adet, tutar."),
    "semantic_mp_settlement": ("Hakediş / hesap ekstresi (panel dosyası)", "İşlem satırları: tarih, tip, kalem, sipariş no, "
                               "işaretli tutar (TİMAŞ lehine +), ödeme tarihi, belge no."),
    "semantic_mp_imports": ("Panel dosyaları", "Yüklenen hakediş ve sipariş/iade raporları: tür, dosya, satır, kolonlar."),
    "semantic_mp_logo_invoices": ("Logo faturaları (mutabakat okuması)", "Panel numarasıyla eşleşen ya da pazar yeri carisine "
                                  "kesilen faturalar: tür, tarih, NETTOTAL, cari kodu, eşleşen alan."),
    "semantic_mp_logo_lines": ("Logo fatura satırları (mutabakat okuması)", "Bu faturaların malzeme (kitap, adet) ve hizmet "
                               "(kesinti kalemi) satırları; LINENET."),
    "semantic_mp_logo_cash": ("Logo cari hareketleri (mutabakat okuması)", "Pazar yeri carilerinin fatura dışı hareketleri gün × tür."),
}

#: Rakam olmayan sayılar: sayfa, ayarlar, yıl ve ay numaraları, Logo kod numaraları.
NOT_RAKAM = ("page", "pageSize", "job", "ayarlar", "donem.yillar", "okuma.toleransGun", "items[].tur",
             "items[].faturalar[].ref", "items[].faturalar[].tur", "cariler[].kartTuru", "kesinti.kalemler[].tur",
             "hakedis.hareketler[].modul", "hakedis.hareketler[].tur", "belgeMetni[].tur", "doluluk[].tur",
             "okuma.pazarYeriCarileri[].kartTuru")

F_MODEL = ("Satış modeli (kural): pazar yeri carileri = M42 eşlemesinde bu platforma bağlı, kanal kodu bu platforma bağlı "
           "ya da unvanında Yönetim ayarındaki adlar geçen Logo carileri. Konsinye izi = ayardaki günden eski faturalanmamış "
           "satış irsaliyesi ya da sevkten bu kadar günden geç faturalanan sevk; toptan izi = toptan satış faturası (TRCODE 8); "
           "kendi mağaza izi = perakende satış faturası (7), belge alanında platform adı geçen perakende fatura ya da çok "
           "sayıda farklı cariye kesilen fatura, panel siparişinin tüketici faturasında bulunması ya da satış olmadan "
           "platformdan alınan hizmet faturası. Tek iz → o model; konsinye + toptan → konsinye; kendi mağaza ile öteki birlikte "
           "→ belirsiz (karma); iz yok → belirsiz. Güçlü = iz ayardaki ay sayısı kadar farklı ayda.")
F_KESINTI = ("Kesinti (Logo): pazar yeri carilerinden alınan faturalardaki (TRCODE 1, 4) hizmet satırları; kalem hizmet "
             "kartı adından kuralla (komisyon, kargo, hizmet bedeli, reklam, stopaj, ceza). Tutar LINENET (KDV hariç).")
F_HAREKET = "Hakediş yolu (Logo): pazar yeri carilerinin fatura dışı cari hareketleri, modül × tür × yön (0 borç, 1 alacak)."
F_MUTABAKAT = ("Mutabakat: panel siparişi/iadesi ↔ Logo faturası. Anahtar: panel sipariş numarasının faturanın belge "
               "alanlarında (FICHENO, DOCODE, SPECODE, CYPHCODE, GENEXP1–4, DOCTRACKINGNR) geçmesi; yoksa pazar yeri carisinin "
               "fatura satırında barkod + gün (± tolerans) + adet. Tutar farkı = panel tutarı − Logo NETTOTAL (KDV dahil); "
               "eşik ayarda. Eksik = faturası beklenen (iptal/bekliyor değil) panel kaydının Logo'da faturası yok; fazla = "
               "iptal siparişe fatura, bir siparişe fazla fatura ya da pazar yeri carisine kesilip panelde karşılığı yok.")
F_HAKEDIS = ("Hakediş: ekstre satırlarının işaretli tutarları (TİMAŞ lehine +) kalem ve ay başına; kesinti = −(komisyon + kargo "
             "+ hizmet + stopaj + reklam + ceza + diğer); net = ödeme dışı satırların toplamı. Logo kesintisi pazar yeri "
             "carisinden alınan hizmet faturalarının hizmet satırları (KDV hariç) ve ekstredeki belge numarasıyla bulunan "
             "faturalar; Logo tahsilatı pazar yeri carilerinin fatura dışı alacak hareketleri. Logo'da bulunamayan uydurulmaz.")
F_DOSYA = "Panel dosyası: satır sayısı, tanınan ve içeri alınmayan kolon adları (değer yok)."


def _kur(engine: Any, tenant: str, q: Y.Yakalanan, platform: str, prefix: str) -> Y.Kurucu:
    koken = {"semantic_channel_meta": [PM.koken(platform), MU.koken(platform)],
             "semantic_mp_logo_invoices": [MU.koken(platform)], "semantic_mp_logo_lines": [MU.koken(platform)],
             "semantic_mp_logo_cash": [MU.koken(platform)]}
    titles = {PM.koken(platform): f"Satış modeli ölçümü · {platform}", MU.koken(platform): f"Mutabakat okuması · {platform}"}
    return Y.Kurucu(engine, tenant, q, prefix=prefix, tablolar=TABLOLAR, koken=koken, koken_basliklari=titles)


def _map(b: Y.Kurucu, out: dict[str, Any], ref: str, special: Optional[dict[str, str]] = None,
         skip: Iterable[str] = ()) -> P.Kaynaklar:
    special = dict(special or {})
    skip = set(skip) | {"kaynaklar", "page", "pageSize", "job", "me"}
    f = {k: ref for k in out if k not in skip and k not in special}
    f.update({k: v for k, v in special.items() if k in out})
    return b.alanlar(f)


def model(engine: Any, tenant: str, platform: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, platform, f"model.{platform}")
    h = b.hesap("model", F_MODEL, "semantic_channel_meta", "semantic_mp_logo_invoices")
    return _map(b, out, h, {"kesinti": b.hesap("kesinti", F_KESINTI, "semantic_channel_meta"),
                            "hakedis": b.hesap("hareket", F_HAREKET, "semantic_channel_meta"),
                            "panel": b.hesap("panel", F_MUTABAKAT, "semantic_mp_logo_invoices")})


def mutabakat(engine: Any, tenant: str, platform: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, platform, f"mutabakat.{platform}")
    return _map(b, out, b.hesap("mutabakat", F_MUTABAKAT, *TABLOLAR))


def hakedis(engine: Any, tenant: str, platform: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, platform, f"hakedis.{platform}")
    h = b.hesap("hakedis", F_HAKEDIS, "semantic_mp_settlement", "semantic_mp_logo_lines", "semantic_mp_logo_invoices",
                "semantic_mp_logo_cash")
    return _map(b, out, h, {"logoFaturasiYok": b.hesap("faturasiz", F_HAKEDIS + " " + F_MUTABAKAT, *TABLOLAR)})


def dosyalar(engine: Any, tenant: str, platform: str, out: dict[str, Any], q: Y.Yakalanan) -> P.Kaynaklar:
    b = _kur(engine, tenant, q, platform, f"dosya.{platform}")
    return _map(b, out, b.hesap("dosya", F_DOSYA, "semantic_mp_imports"))
