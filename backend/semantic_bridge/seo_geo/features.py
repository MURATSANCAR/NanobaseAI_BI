"""SEO/GEO uzman özellikleri: her biri kendi dosyasında, `register(app, ctx)` ile uçlarını ve gece işini ekler.

- impact.py       onaylanan değişikliğin sitede yayına girdiği gün + önce/sonra 28 gün Search Console karşılaştırması
- opportunities.py 4–15. sıradaki ve çok gösterilip az tıklanan sorgular (fırsat listesi)
- bing.py         Bing Webmaster (yalnız okuma) ve IndexNow bildirimi
- tech.py         teknik tarama: canonical, noindex, yönlendirme zinciri, 404, parametreli kopya, sitemap, robots.txt
                  yapay zekâ botları, görsel alt metni
- speed.py        PageSpeed Insights + CrUX: sayfa türü başına hız ve Core Web Vitals
- competitors.py  aynı kitap aramasında rakip sitelerin Google sırası (SerpApi, aylık kota)
- entity.py       kimlik: Wikidata, Organization sameAs, bilgi paneli hazırlığı
- guides.py       soruya cevap veren rehber/liste sayfası taslakları (ZEKİ AI yazar, insan onaylar; hiçbir yere gönderilmez)

Kurallar: T-soft'a ve CRM'e yazma yok; ekranda model/teknoloji adı yok; sessiz sayı tavanı yok (kota ayarı hariç).
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger("semantic.seo_geo")

MODULES = ("impact", "opportunities", "bing", "tech", "speed", "competitors", "entity", "guides",
           # 2. tur (2026-09-27): izleme/uyarı + haftalık rapor, yapay zekânın kaynakları, yarışan sayfalar, sezon takvimi,
           # site içi bağlantılar, Google taraması (URL Denetimi + Cloudflare bot analitiği), okur yorumları, video,
           # satıştan kalkan kitap sayfaları, yazar sayfası güven sinyalleri, Bing'den gelen bağlantılar
           "watch", "ai_sources", "cannibal", "seasons", "links", "crawlbot", "reviews", "video", "sunset",
           "authors", "backlinks",
           # 3. tur (2026-09-28): tek iş listesi, kitap karnesi, yazar biyografisi, SSS taslağı, benzer kitaplar,
           # sorgu–sayfa eşlemesi, izlenen soru önerileri, YouTube, Google Alışveriş hazırlığı, aylık yönetim raporu
           "worklist", "scorecard", "bios", "faq", "similar", "keymap", "qsuggest", "youtube", "shopping", "monthly",
           # 2026-09-28: Search Console site haritası durumu (hata/uyarı/son okuma, 6 saatte bir)
           "gsc_sitemaps",
           # 2026-09-28: Google Merchant Center ürün durumu (onaylı/onaylanmayan/sınırlı, ürün sorunları; 6 saatte bir)
           "merchant")


@dataclass
class Ctx:
    seo: Any                               # SeoGeo: engine(), tenant(), conf(), audit(), gsc(), nightly
    gate: Callable[[Any], str]             # oturum şart → kullanıcı adı
    approver: Callable[[Any], str]         # onay yetkisi şart → kullanıcı adı
    authorize: Callable[[Any], None]       # yalnız çağıran belirteci (zamanlayıcı)


def register(app, ctx: Ctx) -> None:
    for name in MODULES:
        try:
            mod = importlib.import_module(f"{__package__}.{name}")
        except ModuleNotFoundError as e:
            if e.name == f"{__package__}.{name}":
                continue
            raise
        mod.register(app, ctx)
