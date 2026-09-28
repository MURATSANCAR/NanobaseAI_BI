"""SEO & GEO: ekrandaki her rakamın sorgu bilgisi (G5 yayılımı; sözleşme `provenance.py`, yakalama `sorgu_yakala.py`).

SEO & GEO'nun 38 ekranı ~60 okuma ucundan beslenir; her uç kendi portal tablosunu (`semantic_seo_*`) okur. Uçlara tek
tek dokunmak yerine paketin kaydında bir ara katman kurulur (`install`): `/api/v1/seo-geo/*` okuma (GET) isteği
çalışırken portal veritabanına giden her okuma değerleriyle yakalanır; cevap JSON nesnesiyse `kaynaklar` eklenir.
Gösterilen SQL o istekte koşan metnin kendisidir (kılavuzdaki «gösterilen = çalışan» güvencesi). Uç başına hesap metni
`SPECS`'tedir; cevabın bütün üst anahtarları o hesaba bağlanır, hesabın girdileri o istekteki bütün okumalardır.

Dış servisten gelen rakamlar (Search Console, Bing, T-soft, YouTube, hız ölçümü, arama sonuçları, yapay zekâ
ölçümleri) gece okumasında portal tablosuna yazılır; SQL'i yoktur — hesap metninde kaynağın adı yazar. CRM'den gelen
tabloların (kitap kartı, yazar, biyografi kaynağı, özel günler) asıl CRM sorgusu `origin` olarak eklenir.

Önbellekten dönen uçta (ör. yapay zekâ kaynakları, yarışan sayfalar) o istekte okuma olmaz: son hesaplamada çalışan
sorgular gösterilir ve açıklamada «önbellekten» yazar. Hiç okuması olmayan uçta kayıt kurulamaz; pencere nedenini yazar.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from typing import Any, Callable, Optional

from semantic_bridge import provenance as P
from semantic_bridge import sorgu_yakala as Y

log = logging.getLogger("semantic.seo_geo.kaynak")

PREFIX = "/api/v1/seo-geo/"

TABLOLAR: dict[str, tuple[str, str]] = {
    "semantic_seo_products": ("Site ürünleri", "T-soft ürün kaydı (gece eşitlemesi): ad, alanlar, puan, kurallar, satış ve görüntülenme sayaçları."),
    "semantic_seo_proposals": ("Öneriler", "Ürün ve sayfa önerileri: durum, puan önce/sonra, karar."),
    "semantic_seo_runs": ("Eşitleme turları", "T-soft/CRM/Search Console turları: başlangıç, bitiş, okunan kayıt."),
    "semantic_seo_gsc_sitemaps": ("Site haritası okuması", "Search Console'dan okunan site haritaları ve özet (son okuma)."),
    "semantic_seo_gsc_sitemaps_hist": ("Site haritası geçmişi", "Her okumada harita başına sayılar (artışı görmek için)."),
    "semantic_seo_gsc": ("Search Console verisi", "Search Console'dan gece okunan günlük/sorgu/sayfa raporu (son 28 gün)."),
    "semantic_seo_questions": ("İzlenen sorular", "Yapay zekâ görünürlüğü ölçümünde izlenen sorular."),
    "semantic_seo_links": ("Site sayfaları", "T-soft yazar/kategori/yayınevi sayfaları (başlık, açıklama)."),
    "semantic_seo_redirects": ("Yönlendirme önerileri", "Anasayfaya giden eski adres ve önerilen hedef, güven düzeyi."),
    "semantic_seo_schema": ("Şema taraması", "Sayfa başına yapılandırılmış veri ve eksikler."),
    "semantic_seo_geo_results": ("Yapay zekâ ölçümleri", "Soru × motor cevabı: Timaş anıldı mı, kaynak gösterildi mi."),
    "semantic_seo_crm_books": ("CRM kitap kartları", "CRM kitap kartı, hak kararı ve yayın durumu (gece okuması)."),
    "semantic_seo_author_crm": ("CRM yazar kaydı", "Yazarın CRM kaydı ve ödülleri."),
    "semantic_seo_backlink_counts": ("Gelen bağlantı sayıları", "Bing'den okunan sayfa başına dış bağlantı sayısı."),
    "semantic_seo_backlink_snaps": ("Gelen bağlantı anlık görüntüleri", "Okuma başına toplam sayılar."),
    "semantic_seo_backlinks": ("Gelen bağlantılar", "Sayfaya bağlantı veren dış adresler."),
    "semantic_seo_bing": ("Bing verisi", "Bing Webmaster'dan okunan sorgu/sayfa/trafik/tarama raporları."),
    "semantic_seo_bios": ("Biyografi taslakları", "Yazar biyografisi taslakları ve kararları."),
    "semantic_seo_bios_src": ("Biyografi kaynağı", "CRM'den okunan yazar–kitap bağı ve özgeçmiş uzunlukları."),
    "semantic_seo_botstats": ("Bot istatistikleri", "Tarayıcı bot istekleri (günlük)."),
    "semantic_seo_crawlbot_state": ("Google taraması durumu", "URL Denetimi turunun durumu."),
    "semantic_seo_entity": ("Kimlik denetimi", "Wikidata/Wikipedia kimlik denetimi sonuçları."),
    "semantic_seo_faq": ("Soru–cevap taslakları", "Kitap soru–cevap taslakları ve kararları."),
    "semantic_seo_guides": ("Rehber taslakları", "Rehber/liste sayfası taslakları."),
    "semantic_seo_impact": ("Değişiklik etkisi", "Onaylanan değişikliğin önce/sonra 28 gün Search Console ölçümü."),
    "semantic_seo_indexnow_log": ("IndexNow günlüğü", "Bildirilen adresler."),
    "semantic_seo_indexnow_state": ("IndexNow durumu", "Bildirim durumu."),
    "semantic_seo_inspect": ("URL Denetimi", "Google'ın adres başına son hâli (dizin, kapsam, canonical)."),
    "semantic_seo_inspect_hist": ("URL Denetimi geçmişi", "Adres başına önceki denetimler."),
    "semantic_seo_inspect_usage": ("URL Denetimi kotası", "Gün başına kullanılan denetim."),
    "semantic_seo_keymap_decisions": ("Sorgu–sayfa kararları", "Arama başına seçilen hedef sayfa."),
    "semantic_seo_links_edges": ("Site içi bağlantılar", "Taranan sayfaların birbirine verdiği bağlantılar."),
    "semantic_seo_links_summary": ("Bağlantı özeti", "Sayfa başına gelen bağlantı sayıları."),
    "semantic_seo_monthly": ("Aylık rapor", "Aylık yönetim raporunun rakamları (ay kapanınca yazılır)."),
    "semantic_seo_opps": ("Fırsat verisi", "Search Console sorgu+sayfa kırılımı ve fırsat hesabı (son 28 gün)."),
    "semantic_seo_qsuggest": ("Soru önerileri", "Üretilen soru önerileri ve kararları."),
    "semantic_seo_qsuggest_crm": ("CRM tema/yaş bağları", "Kitap tema ve yaş bağları (CRM)."),
    "semantic_seo_reviews": ("Okur yorumları", "Ürün başına yorum sayısı, puan toplamı, yıldız dağılımı."),
    "semantic_seo_seasons_books": ("Özel gün kitapları", "Özel gün ↔ kitap bağı (CRM)."),
    "semantic_seo_seasons_days": ("Özel günler", "Özel günler (CRM + kodda hesaplanan tarihler)."),
    "semantic_seo_seasons_weeks": ("Özel gün aramaları", "Search Console haftalık gösterim (özel gün anahtar kelimeleri)."),
    "semantic_seo_serp": ("Arama sonuçları", "Kitap araması başına Google organik sıraları (aylık kotalı okuma)."),
    "semantic_seo_serp_usage": ("Arama kotası", "Ay başına kullanılan arama."),
    "semantic_seo_similar_decisions": ("Benzer kitap kararları", "Öneri kararları."),
    "semantic_seo_similar_src": ("Benzer kitap kaynağı", "CRM emsal kitap, tema ve yaş bağları."),
    "semantic_seo_speed": ("Hız ölçümleri", "PageSpeed ve CrUX ölçümleri (her ölçüm eklenir)."),
    "semantic_seo_sunset": ("Satıştan kalkan sayfalar", "Aday sayfa ve öneri (301 / stokta yok / 410)."),
    "semantic_seo_tech": ("Teknik tarama", "Sayfa başına durum kodu, zincir, canonical, robots, başlık."),
    "semantic_seo_tech_snap": ("Teknik tarama özeti", "Tur başına sorun sayıları."),
    "semantic_seo_watch_daily": ("İzleme günlük serisi", "Günlük tıklama/gösterim geçmişi."),
    "semantic_seo_watch_events": ("İzleme olayları", "Dedektörlerin çıkardığı olaylar."),
    "semantic_seo_watch_reports": ("Haftalık raporlar", "Haftalık rapor kayıtları."),
    "semantic_seo_watch_state": ("İzleme durumu", "Dedektör durumu."),
    "semantic_seo_worklist_cache": ("İş listesi", "Toplanan iş maddeleri ve etki puanı."),
    "semantic_seo_worklist_log": ("İş listesi günlüğü", "Madde durum geçişleri."),
    "semantic_seo_worklist_state": ("İş listesi durumu", "Madde başına durum."),
    "semantic_seo_youtube": ("YouTube videoları", "Video başına YouTube kaydı ve denetim."),
    "semantic_web_authors": ("Doğrulanmış yazar kaydı", "Basın-web modülünün doğrulanmış yazar kaydı (Wikidata)."),
}

GSC = "Search Console (gece okuması, son 28 gün): tıklama, gösterim, tıklama oranı = tıklama ÷ gösterim, ortalama sıra."
TSOFT = "T-soft ürün kaydı (gece eşitlemesi; T-soft'a yazılmaz)"

#: (yol kalıbı, hesap adı, hesap metni). İlk uyan kullanılır; kalıbı olmayan uç (dosya indirme, /me) atlanır.
SPECS: list[tuple[str, str, str]] = [
    (r"overview", "ozet", f"Ürün denetimi: {TSOFT}. Aktif ürün sayısı, ortalama puan (kural denetimi, 100 üzerinden), puanı "
                          "70 altındaki ürün, kural başına ihlal eden ürün, öneri durumları, bu hafta onaylanan; öncelik listesi "
                          f"satış ve görüntülenme sayacına göre. Arama özeti: {GSC} CRM özeti: hak kararı ve yayın durumu sayıları."),
    (r"products/[^/]+", "urun", f"Ürün: puan ve ihlal edilen kurallar {TSOFT}ndan; açıklama kelime sayısı; sınırlar Yönetim "
                               "ayarıdır; öneri puanı önce/sonra kural denetimiyle hesaplanır."),
    (r"products", "urunler", f"Ürün listesi: puan, kurallar, satış ve görüntülenme {TSOFT}ndan; toplam = süzgece uyan aktif ürün."),
    (r"history", "gecmis", "Karar geçmişi: öneri kayıtları (kim, ne zaman, puan önce/sonra); toplam = kayıt sayısı."),
    (r"search/[^/]+", "arama", GSC),
    (r"llms", "llms", f"Dosya önerisi {TSOFT}ndan kurulur: kitap, yayınevi, yazar ve satıcı sayıları aktif ürünlerden."),
    (r"redirects", "yonlendirme", "Yönlendirme önerileri (kurallı): güven düzeyine ve duruma göre sayılar; gösterim "
                                  "Search Console'dan; toplam = süzgece uyan kayıt."),
    (r"pages/[^/]+/[^/]+", "sayfa", f"Sayfa: kitap sayısı ve satış toplamı sayfaya bağlı ürünlerden ({TSOFT}); denetim puanı kurallarla."),
    (r"pages", "sayfalar", f"Yazar/kategori/yayınevi sayfaları: kitap sayısı, satış toplamı ({TSOFT}), denetim puanı; toplam = kayıt."),
    (r"schema", "sema", "Şema taraması: sayfa başına eksik alanlar; sorun başına sayfa sayısı; taranan sayfa sayısı."),
    (r"questions", "gorunurluk", "Yapay zekâ görünürlüğü: soru × motor ölçümünde Timaş'ın anılma ve sitenin kaynak "
                                "gösterilme sayısı ve oranı (ölçüm kaydı); tur ilerlemesi."),
    (r"crm", "crm", "CRM kitap kartları (gece okuması): hak kararı (var / incele / eksik / yok…) ve yayın durumu sayıları; "
                    "yürürlükteki sözleşme sayısı."),
    (r"opportunities", "firsat", GSC + " Yakın sıra: ortalama sırası 4–15 olan sorgu+sayfa; tahmini ek tıklama = sitenin "
                                     "kendi tıklama oranı eğrisiyle ilk üçe çıkınca fark. Düşük tıklama: aynı sıradaki tipik "
                                     "oranın yarısından az tıklanan."),
    (r"impact", "etki", "Değişiklik etkisi: yayına girdiği günün öncesi ve sonrası 28 gün Search Console tıklama, gösterim, "
                        "oran, sıra; site geneli aynı pencerelerde; fark = sonra − önce."),
    (r"bing/list/[^/]+", "bingListe", "Bing Webmaster (gece okuması): sorgu/sayfa satırları — tıklama, gösterim, sıra; "
                                       "Search Console ile yan yana."),
    (r"bing", "bing", "Bing Webmaster (gece okuması): sorgu, sayfa, günlük trafik, tarama istatistiği ve sorunları."),
    (r"indexnow", "indexnow", "IndexNow: bildirilen adres sayıları ve son bildirimler (günlük)."),
    (r"tech/robots", "robots", "robots.txt denetimi: yapay zekâ botları için izin/engel satırları (teknik taramanın okuması)."),
    (r"tech/sitemaps", "sitemap", "Site haritaları: adres sayıları ve sorunlar (teknik taramanın okuması)."),
    (r"tech", "teknik", "Teknik tarama: sayfa başına durum kodu, yönlendirme zinciri, canonical, noindex, başlık; sorun "
                        "türüne göre sayfa sayısı; tur özeti."),
    (r"speed", "hiz", "Hız ölçümü (PageSpeed laboratuvar + CrUX gerçek kullanıcı, p75): LCP, INP, CLS, FCP, TTFB; eşik "
                      "Google'ınkidir; sayfa türü başına ortalama."),
    (r"competitors/summary", "rakipOzet", "Rakipler: arama sonuçlarında alan adı başına ilk 3/ilk 10 sayısı ve ortalama sıra."),
    (r"competitors", "rakip", "Rakipler: kitap araması başına sitemizin ve rakip alan adlarının Google organik sırası (aylık kotalı okuma)."),
    (r"entity/google-books", "googleBooks", "Kimlik: kitap kayıtlarının dış kataloglarda bulunma sayıları (kimlik denetimi önbelleği)."),
    (r"entity/authors", "kimlikYazar", "Kimlik: yazarın Wikidata/Wikipedia kaydı var mı; sayılar denetim önbelleğinden."),
    (r"entity", "kimlik", "Kimlik: kurum, yazar ve kitapların Wikidata/Wikipedia kaydı; geçti/kaldı sayıları."),
    (r"guides/topics/[^/]+/books", "rehberKitap", f"Rehber konusu kitapları: satış ve görüntülenme {TSOFT}ndan; eşleşme CRM kartından."),
    (r"guides/topics", "rehberKonu", GSC + " Konu = liste/öneri niyetli sorguların kümesi; gösterim toplamı."),
    (r"guides/[^/]+", "rehberTaslak", "Rehber taslağı: kitap listesi ve kararı; kitap sayısı taslağın kendisinden."),
    (r"guides", "rehber", "Rehber taslakları: durum sayıları; konu gösterimi Search Console'dan."),
    (r"watch/report", "haftalik", "Haftalık rapor: haftanın tıklama/gösterim toplamı ve önceki haftayla fark (Search Console), "
                                  "olay sayıları."),
    (r"watch", "izleme", "İzleme: dedektör olayları (tıklama düşüşü = son günlerin ortalaması ÷ önceki pencere, tek gün "
                         "sapması = sağlam z-puanı); günlük seri."),
    (r"ai-source-questions", "yzSoru", "Yapay zekânın kaynakları: soru başına kaynak gösterilen alan adları (ölçüm kaydından)."),
    (r"ai-sources/[^/]+", "yzAlan", "Alan adı: kaç cevapta kaynak gösterildiği, hangi sorularda; Timaş anıldı mı (ölçüm kaydından)."),
    (r"ai-sources", "yzKaynak", "Yapay zekânın kaynakları: ölçüm cevaplarında alan adı başına kaynak gösterilme sayısı ve "
                                "payı; Timaş'ın anıldığı cevap sayısı."),
    (r"cannibal", "yarisan", GSC + " Yarışan arama: en az iki adresimizin gösterim aldığı arama; baskın adresin gösterim payı; "
                                    "önem kuralla (pay ve sıra eşikleri)."),
    (r"seasons/[^/]+", "sezonGun", "Özel gün: bağlı kitaplar (CRM), sayfa hazırlık durumu; geçen yıl artışı Search Console haftalık gösteriminden."),
    (r"seasons", "sezon", "Sezon takvimi: yaklaşan özel günler, bağlı kitap sayısı (CRM), hazır sayfa sayısı, geçen yıl gösterim artışı."),
    (r"links/url", "baglantiAdres", "Adres: gelen/giden site içi bağlantı sayıları (teknik taramanın bağlantı grafiği)."),
    (r"links", "baglanti", "Site içi bağlantılar: gelen bağlantı = bağlantı veren farklı taranmış sayfa; yetim sayfa = hiç "
                           "bağlantı almayan envanter sayfası; sayılar bağlantı grafiğinden."),
    (r"crawlbot/bots", "bot", "Bot istekleri: gün ve bot başına istek sayısı."),
    (r"crawlbot/urls", "denetimAdres", "URL Denetimi: adres başına Google kararı, kapsam, son tarama."),
    (r"crawlbot", "tarama", "Google taraması: URL Denetimi sonuçlarının karar/kapsam dağılımı, günlük kota kullanımı."),
    (r"reviews", "yorum", f"Okur yorumları: kitap başına yorum sayısı (T-soft sayaç ve yorum okumasının büyüğü), ortalama "
                          "puan, yıldız dağılımı; yorumsuz çok satan sayısı; şemada puanı görünmeyen sayfa."),
    (r"video", "video", "Kitap videoları: CRM kartında video bağlantısı olan kitap sayısı; şemada VideoObject olan sayfa sayısı."),
    (r"sunset", "satistanKalkan", "Satıştan kalkan: aday sayfa sayıları öneri türüne göre (kurallı); gösterim Search Console'dan."),
    (r"authors-trust", "yazarGuven", "Yazar güven sinyalleri: sinyal başına var/yok; puan = sinyallerin ağırlıklı toplamı."),
    (r"backlinks", "geriBaglanti", "Gelen bağlantılar (Bing, gece okuması): sayfa başına dış bağlantı sayısı, bağlantı veren "
                                  "alan adı sayısı; yeni/kaybolan = son iki anlık görüntünün farkı."),
    (r"worklist/log", "isGunluk", "İş listesi günlüğü: madde durum geçişleri."),
    (r"worklist/group/[^/]+", "isGrup", "İş listesi grubu: maddeler ve etki puanı."),
    (r"worklist", "isListesi", "İş listesi: etki puanı = önem puanı + satış puanı (log10 T-soft satış) + arama puanı (log10 "
                               "gösterim) + tahmini ek tıklama puanı + kayıt sayısı puanı; kaynak ve sorumluya göre sayılar."),
    (r"scorecard/[^/]+", "karne", "Kitap karnesi: bölüm başına durum (öteki modüllerin tablolarından); genel not = bilinen "
                                  "bölümlerin ağırlıklı ortalaması (iyi 100, dikkat 60, sorun 20)."),
    (r"scorecard", "karneListe", "Kitap karneleri: kitap başına genel not ve sorunlu bölüm sayısı."),
    (r"bios/[^/]+", "biyografi", "Yazar: kitap sayısı ve özgeçmiş uzunluğu (CRM); taslak durumu."),
    (r"bios", "biyografiler", "Yazar biyografileri: yazar başına kitap sayısı (CRM), taslak durum sayıları."),
    (r"faq/[^/]+", "sss", "Kitap soru–cevapları: taslak ve kararlar; kitap bilgisi CRM kartından."),
    (r"faq", "sssListe", "Soru–cevap: kitap başına taslak durumu; durum sayıları; satış sırası T-soft sayacından."),
    (r"similar/[^/]+", "benzer", "Benzer kitaplar: emsal/tema/yaş bağından öneriler (CRM), karar durumları."),
    (r"similar", "benzerListe", "Benzer kitaplar: kitap başına öneri sayısı ve karar durumları."),
    (r"keymap", "sorguSayfa", GSC + " Arama başına sıralanan sayfa (en çok tıklanan adres) ve hedef sayfa; uyumsuzluk sayıları."),
    (r"qsuggest", "soruOneri", "Soru önerileri (kurallı): kaynak başına öneri sayısı; aramadan gelenlerde gösterim (Search "
                               "Console); tema/yaş bağından gelenlerde kitap sayısı (CRM)."),
    (r"youtube", "youtube", "YouTube videoları (gece okuması): izlenme, beğeni, yorum; denetim sorunu sayıları."),
    (r"shopping", "alisveris", f"Alışveriş hazırlığı: ürün verisi kurallarına göre sorun sayıları; ürünler {TSOFT}ndan."),
    (r"gsc-sitemaps", "siteHaritasi", "Search Console site haritaları (gece okuması): harita başına gönderilen/dizine "
                                     "eklenen adres, hata ve uyarı sayısı; artış = son iki okumanın farkı."),
    (r"monthly", "aylik", "Aylık rapor: ayın Search Console tıklama, gösterim, oran, sıra; önceki ay ve geçen yıl aynı ayla "
                          "fark; puanı ≥ 80 olan çok satanların payı; karar, teknik sorun ve anılma sayıları."),
]
_COMPILED = [(re.compile(rf"^{pat}$"), name, text) for pat, name, text in SPECS]
_SKIP = re.compile(r"\.(csv|tsv|md|html|pdf|xml|json)$|^me$")


def spec_for(path: str) -> Optional[tuple[str, str]]:
    rest = path[len(PREFIX):] if path.startswith(PREFIX) else path
    rest = rest.strip("/")
    if not rest or _SKIP.search(rest):
        return None
    for rx, name, text in _COMPILED:
        if rx.match(rest):
            return name, text
    return None


# ------------------------------------------------------------------ CRM kaynaklı tabloların asıl sorgusu


def _crm_origins(conf: Callable[[str], str]) -> dict[str, list[tuple[str, str, str]]]:
    """Tablo → [(kimlik, başlık, SQL)]: CRM'den gece okunan tabloların çalışan SQL'i (şema ayardan; değerler yerinde)."""
    from semantic_bridge.editorial import _prefix

    from . import authors, bios, crm, seasons

    p = _prefix(conf("CRM_SCHEMA"))
    books = [("seo.crm.kitap", "CRM kitap kartları", crm.book_sql(p)),
             ("seo.crm.sozlesme", "CRM telif alış sözleşmeleri", crm.contract_sql(p)),
             ("seo.crm.taraf", "CRM sözleşme tarafları", crm.party_sql(p)),
             ("seo.crm.yayin", "CRM yayıncılık durumu etiketleri", crm.label_sql(p, "new_kitap_yayincilikstatusu")),
             ("seo.crm.hedef", "CRM hedef kitle etiketleri", crm.label_sql(p, "new_hedefkitle")),
             ("seo.crm.tip", "CRM kitap tipi etiketleri", crm.label_sql(p, "new_tip"))]
    return {
        "semantic_seo_crm_books": books,
        "semantic_seo_author_crm": [("seo.crm.yazar", "CRM yazar kaydı", authors.crm_sql(p)),
                                    ("seo.crm.odul", "CRM yazar ödülleri", authors.awards_sql(p))],
        "semantic_seo_bios_src": [("seo.crm.katilimciTipi", "CRM katılımcı türleri", bios.type_sql(p)),
                                  ("seo.crm.katilim", "CRM eser katılımı", bios.participation_sql(p))],
        "semantic_seo_seasons_days": [("seo.crm.ozelGun", "CRM özel günler", seasons.days_sql(p))],
        "semantic_seo_seasons_books": [("seo.crm.ozelGunKitap", "CRM özel gün ↔ kitap bağı", seasons.links_sql(p))],
    }


def build(engine: Any, tenant: str, path: str, out: dict[str, Any], q: Y.Yakalanan,
          conf: Optional[Callable[[str], str]] = None, cached: bool = False) -> P.Kaynaklar:
    spec = spec_for(path)
    if spec is None:
        raise P.ProvenanceError("Bu uç için sorgu bilgisi tanımlı değil.")
    name, text = spec
    if not q.queries:
        raise P.ProvenanceError("Bu ekranın rakamları bu istekte veritabanından okunmadı (dış servis ya da bellek); "
                                "sorgu bilgisi yok.")
    b = Y.Kurucu(engine, tenant, q, prefix="seo", tablolar=TABLOLAR)
    if cached:
        for s in b.k.sources.values():
            s["description"] = ((s.get("description") or "") + " Önbellekten: bu sorgu son hesaplamada çalıştı.").strip()
    if conf is not None:
        try:
            origins = _crm_origins(conf)
        except Exception as e:  # noqa: BLE001 — CRM şeması tanımlı değilse köken eklenmez; rakam düşmez
            log.info("seo kaynak: CRM kökeni kurulamadı: %s", e)
            origins = {}
        db = P.connection_database(_crm_file())
        added: dict[str, str] = {}
        for sid, s in list(b.k.sources.items()):
            if s["connection"] != "portal":
                continue
            for t in Y.tables_of(s["sql"]):
                for oid, title, sql in origins.get(t, []):
                    if oid not in added:
                        try:
                            b.k.sorgu(oid, title, "crm", sql, database=db,
                                      description="Bu tabloyu dolduran gece CRM okumasının sorgusu (şema ayardan).")
                            added[oid] = oid
                        except P.ProvenanceError as e:
                            log.info("seo kaynak: %s: %s", oid, e)
                            continue
                    if oid in added and oid not in s["origin"]:
                        s["origin"].append(oid)
    ref = b.k.hesap(name, text, b.girdi())
    fields = {k: ref for k in out if k not in ("kaynaklar",)}
    return b.alanlar(fields)


def _crm_file() -> Optional[str]:
    from . import crm

    return getattr(crm, "CONNECTION_FILE", None)


# ------------------------------------------------------------------ ara katman


_last: dict[str, list[dict[str, Any]]] = {}
_last_lock = threading.Lock()


class SorguBilgisiAraKatmani:
    """Saf ASGI ara katmanı: yalnız `/api/v1/seo-geo/*` GET isteklerine dokunur; öbür bütün istekler (akış, indirme,
    sohbet) olduğu gibi geçer. İstek bu görevde koşar; bağlam değişkeni (yakalama) uca ve iş parçacığına geçer."""

    def __init__(self, app: Any, seo: Any) -> None:
        self.app, self.seo = app, seo

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        path = scope.get("path", "") if scope.get("type") == "http" else ""
        if scope.get("type") != "http" or scope.get("method") != "GET" or not path.startswith(PREFIX) or spec_for(path) is None:
            await self.app(scope, receive, send)
            return
        try:
            engine, tenant = self.seo.engine(), self.seo.tenant()
        except Exception:  # noqa: BLE001 — kurulum hazır değilse uç kendi hatasını verir
            await self.app(scope, receive, send)
            return
        messages: list[dict[str, Any]] = []

        async def keep(message: dict[str, Any]) -> None:
            messages.append(message)

        with Y.yakala(engine) as q:
            await self.app(scope, receive, keep)
        start = next((m for m in messages if m.get("type") == "http.response.start"), None)
        headers = list((start or {}).get("headers") or [])
        ctype = next((v for k, v in headers if k.lower() == b"content-type"), b"")
        if start is None or start.get("status") != 200 or not ctype.startswith(b"application/json"):
            for m in messages:
                await send(m)
            return
        body = b"".join(m.get("body", b"") for m in messages if m.get("type") == "http.response.body")
        try:
            data = json.loads(body)
        except ValueError:
            data = None
        if isinstance(data, dict):
            key = path + "?" + scope.get("query_string", b"").decode("latin-1")
            cached = False
            if q.queries:
                with _last_lock:
                    _last[key] = list(q.queries)
            else:
                with _last_lock:
                    prev = _last.get(key)
                if prev:
                    q.extend(prev)
                    cached = True
            conf = getattr(self.seo, "conf", None)
            data = P.bagla(data, lambda: build(engine, tenant, path, data, q, conf, cached))
            body = json.dumps(data, ensure_ascii=False, default=str, separators=(",", ":")).encode("utf-8")
        headers = [(k, v) for k, v in headers if k.lower() != b"content-length"] + [(b"content-length", str(len(body)).encode())]
        await send({**start, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})


def install(app: Any, seo: Any) -> None:
    """Sorgu bilgisi ara katmanını paket kaydında bir kez ekler."""
    app.add_middleware(SorguBilgisiAraKatmani, seo=seo)
