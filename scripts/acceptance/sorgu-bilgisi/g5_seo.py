"""G5 · SEO & GEO sorgu bilgisi kabulü (yalnız okuma). `kabul_g5.py` çağırır.

Bütün SEO & GEO okuma uçları (dosya indirmeleri hariç, yol parametresiz olanlar) çağrılır; her cevapta K1–K3.
Doğrudan SQL referansları:
  S1  genel bakış «T-soft ürünü» = portalda semantic_seo_products satır sayısı (tenant);
  S2  genel bakış «Düzeltilmesi gereken» = aktif ve puanı 70 altı ürün sayısı;
  S3  ara katman SEO dışı yola dokunmaz (kanal karnesinin cevabı kendi kaydını taşır, SEO kaydı eklenmez).
"""
from __future__ import annotations

import sqlalchemy as sa

import kabul as KB
from semantic_bridge.seo_geo import kaynak as K

PATHS = ["overview", "products", "history", "search/daily", "search/queries", "search/pages", "llms", "redirects",
         "pages?type=yazar", "schema", "questions", "crm", "opportunities", "impact", "bing", "indexnow", "tech", "speed",
         "competitors", "competitors/summary", "entity", "guides", "guides/topics", "watch", "watch/report", "ai-sources",
         "ai-source-questions", "cannibal", "seasons", "links", "crawlbot", "crawlbot/bots", "crawlbot/urls", "reviews",
         "video", "sunset", "authors-trust", "backlinks", "worklist", "worklist/log", "scorecard", "bios", "faq",
         "similar", "keymap", "qsuggest", "youtube", "shopping", "monthly"]


def kabul(heavy: bool) -> None:
    no_read = []
    for p in PATHS:
        st, out = KB.http(f"/api/v1/seo-geo/{p}", 900)
        if st != 200:
            KB.check(f"seo /{p}", None, f"HTTP {st}")
            continue
        k = out.get("kaynaklar") or {}
        if k.get("error"):
            no_read.append(p)
            KB.check(f"seo /{p} · sorgu bilgisi", None, k["error"])
            continue
        KB.run_all(f"seo /{p}", KB.contract(f"seo /{p}", out), heavy)
        if p == "overview":
            with KB.portal().connect() as c:
                n = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_products")).scalar()
                f = c.execute(sa.text("SELECT COUNT(*) FROM semantic_seo_products WHERE active = true AND score < 70")).scalar()
            KB.check("S1 seo: «T-soft ürünü» = doğrudan sayım", int(n or 0) == int(out.get("products") or 0), f"{n} · {out.get('products')}")
            KB.check("S2 seo: «Düzeltilmesi gereken» = doğrudan sayım", int(f or 0) == int(out.get("failing") or 0), f"{f} · {out.get('failing')}")
    st, sc = KB.http("/api/v1/channels/scorecard", 900)
    if st == 200:
        seo_ids = [sid for sid in ((sc.get("kaynaklar") or {}).get("sources") or {}) if sid.startswith("seo.")]
        KB.check("S3 seo ara katmanı öbür yollara dokunmaz", not seo_ids, ", ".join(seo_ids[:3]))
    if no_read:
        print("Bu istekte veritabanı okuması olmayan SEO uçları (dış servis/bellek):", ", ".join(no_read))
    assert K.spec_for("/api/v1/seo-geo/overview")
