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

MODULES = ("impact", "opportunities", "bing", "tech", "speed", "competitors", "entity", "guides")


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
