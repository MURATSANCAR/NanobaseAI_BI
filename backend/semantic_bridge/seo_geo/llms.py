"""llms.txt önerisi: yapay zekâ motorlarına sitenin ne olduğunu anlatan dosya (llmstxt.org biçimi).

Yalnız eşitlenmiş T-soft verisinden, modelsiz ve belirlenimli kurulur; uydurma bilgi girmez. Dosya T-soft'a
gönderilmez (T-soft'a yazma yasak; API'de bu dosya için yöntem de yok) — ekranda gösterilir, panelden yüklenir.

İki dosya: `llms.txt` (özet: yayınevleri, kategoriler, en çok satan ve en çok kitabı olan yazarlar — kaç tanesinin
listelendiği başlıkta yazar) ve `llms-full.txt` (bütün aktif kitaplar, sınırsız).
"""
from __future__ import annotations

import collections
from typing import Any

from . import rules

SITEMAPS = ("product", "category", "brand", "model", "content", "blog")


def _num(v: Any) -> int:
    try:
        return int(float(str(v or 0).replace(",", ".")))
    except ValueError:
        return 0


def _link(site: str, slug: Any) -> str:
    slug = str(slug or "").strip().lstrip("/")
    return f"{site.rstrip('/')}/{slug}" if slug else site


def _book(p: dict[str, Any], site: str) -> str:
    name = rules.text_of(p.get("ProductName"))
    author = rules.text_of(p.get("Model"))
    extra = " · ".join(x for x in (author, rules.text_of(p.get("Brand")), f"ISBN {p['Barcode']}" if p.get("Barcode") else "") if x)
    return f"- [{name}]({_link(site, p.get('SeoLink'))}): {extra}" if extra else f"- [{name}]({_link(site, p.get('SeoLink'))})"


def build(products: list[dict[str, Any]], site: str, top: int = 100) -> dict[str, Any]:
    # Kitap = ISBN'li ürün (978/979 önekli barkod); oyun hamuru, kırtasiye gibi ticari ürünler listelere girmez.
    active = [p for p in products if str(p.get("IsActive", "1")).lower() not in ("0", "false")
              and str(p.get("Barcode") or "").strip().startswith(("978", "979"))]
    brands = collections.Counter(rules.text_of(p.get("Brand")) for p in active if p.get("Brand"))
    brand_link = {rules.text_of(p.get("Brand")): p.get("BrandLink") for p in active if p.get("Brand")}
    cats = collections.Counter(" > ".join(x.strip() for x in f"{p.get('DefaultCategoryPath') or ''}{p.get('DefaultCategoryName') or ''}".split(">") if x.strip())
                               for p in active)
    authors = collections.Counter(rules.text_of(p.get("Model")) for p in active if rules.text_of(p.get("Model")))
    sellers = sorted(active, key=lambda p: (-_num(p.get("CountTotalSales")), rules.text_of(p.get("ProductName"))))
    sellers = [p for p in sellers if _num(p.get("CountTotalSales")) > 0]

    head = [
        "# Timaş Yayınları",
        "",
        f"> Timaş Yayınları ve yayınevlerinin kitaplarının satıldığı resmî site. {len(active):,} aktif kitap, "
        f"{len(brands)} yayınevi/marka, {len(authors):,} yazar.".replace(",", "."),
        "",
        f"Site: {site.rstrip('/')}/",
        "",
        "## Yayınevleri",
        "",
        *[f"- [{b}]({_link(site, brand_link.get(b))}): {n} kitap" for b, n in brands.most_common()],
        "",
        "## Kategoriler",
        "",
        *[f"- {c}: {n} kitap" for c, n in cats.most_common() if c],
        "",
    ]
    short = head + [
        f"## En çok satan kitaplar (ilk {min(top, len(sellers))} / {len(sellers)})",
        "",
        *[_book(p, site) for p in sellers[:top]],
        "",
        f"## En çok kitabı olan yazarlar (ilk {min(top, len(authors))} / {len(authors)})",
        "",
        *[f"- {a}: {n} kitap" for a, n in authors.most_common(top)],
        "",
        "## Site haritaları",
        "",
        *[f"- [{s}]({site.rstrip('/')}/xml/sitemap/{s}.xml)" for s in SITEMAPS],
        "",
        "## Optional",
        "",
        f"- [Bütün kitaplar]({site.rstrip('/')}/llms-full.txt): {len(active)} kitabın tam listesi",
        "",
    ]
    by_brand: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for p in sorted(active, key=lambda p: rules.text_of(p.get("ProductName"))):
        by_brand[rules.text_of(p.get("Brand")) or "Diğer"].append(p)
    full = head + [f"## Bütün kitaplar ({len(active)})", ""]
    for b, items in sorted(by_brand.items(), key=lambda kv: -len(kv[1])):
        full += [f"### {b} ({len(items)})", "", *[_book(p, site) for p in items], ""]
    return {"llms": "\n".join(short), "full": "\n".join(full), "books": len(active), "brands": len(brands),
            "authors": len(authors), "listedSellers": min(top, len(sellers)), "sellers": len(sellers)}
