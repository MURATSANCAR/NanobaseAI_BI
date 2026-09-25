"""Şema denetimi: canlı ürün sayfasının yapılandırılmış verisi (JSON-LD) ve başlık etiketleri.

Sayfalar yalnız okunur: açık kimlik (`TimasZekiBot/1.0`), robots.txt'e uyulur, istekler arası bekleme. Şemayı T-soft
teması üretir; burada yalnız neyin eksik olduğu bulunur ve tema isteği belgesi hazırlanır (T-soft'a yazma yasak).

Kitap sayfasında aranan: Book/Product tipi, isbn, author (Person, sameAs), publisher, numberOfPages, inLanguage,
bookFormat, image, offers (price, priceCurrency, availability), aggregateRating (yorumu olan kitapta), FAQPage,
BreadcrumbList; ayrıca canonical, robots, title ve meta açıklama.
"""
from __future__ import annotations

import json
import re
import urllib.robotparser
from typing import Any, Optional

import httpx

USER_AGENT = "TimasZekiBot/1.0 (+https://timas.com.tr; ai@timas.com.tr)"

#: Denetim → (önem, kısa ad, açıklama).
CHECKS: dict[str, tuple[str, str, str]] = {
    "no_book": ("kritik", "Kitap şeması yok", "Sayfada Book/Product tipinde yapılandırılmış veri bulunamadı."),
    "no_isbn": ("yüksek", "ISBN şemada yok", "Google ve yapay zekâ kitabı ISBN'le tanır."),
    "author_not_person": ("orta", "Yazar kişi olarak tanımlı değil", "author alanı Person tipinde olmalı."),
    "author_no_sameas": ("yüksek", "Yazarın kimlik bağlantısı yok",
                         "author.sameAs (Wikidata/Wikipedia) yok; yapay zekâ yazarı başka bir kişiyle karıştırabilir."),
    "no_publisher": ("orta", "Yayınevi şemada yok", "publisher alanı eksik."),
    "no_pages": ("düşük", "Sayfa sayısı şemada yok", "numberOfPages eksik."),
    "no_offer": ("kritik", "Fiyat/stok şemada yok", "offers (price, priceCurrency, availability) eksik; alışveriş sonuçlarına giremez."),
    "no_rating": ("orta", "Okur puanı şemada yok", "Sayfada yorum var ama aggregateRating yok."),
    "no_faq": ("düşük", "Soru–cevap şeması yok", "Sayfada soru–cevap bölümü var ama FAQPage şeması yok."),
    "desc_is_title": ("yüksek", "Meta açıklama başlıkla aynı", "Canlı sayfadaki meta açıklama başlığın kopyası."),
    "no_canonical": ("orta", "Canonical yok", "Sayfada canonical bağlantısı yok."),
    "noindex": ("kritik", "Sayfa dizine kapalı", "robots meta noindex içeriyor."),
    "fetch_error": ("kritik", "Sayfa açılamadı", "Sayfa 200 dönmedi."),
}


def _items(block: Any) -> list[dict[str, Any]]:
    if isinstance(block, list):
        out = []
        for b in block:
            out += _items(b)
        return out
    if isinstance(block, dict):
        if "@graph" in block:
            return _items(block["@graph"])
        return [block]
    return []


def _types(it: dict[str, Any]) -> set[str]:
    t = it.get("@type")
    return set(t if isinstance(t, list) else [t]) - {None}


def parse(html: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for raw in re.findall(r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", html, re.S | re.I):
        try:
            items += _items(json.loads(raw.strip()))
        except ValueError:
            continue
    meta = lambda name: (re.search(rf'<meta\s+name="{name}"\s+content="([^"]*)"', html, re.I) or [None, None])[1]  # noqa: E731
    title = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    canon = re.search(r'<link\s+rel="canonical"\s+href="([^"]*)"', html, re.I)
    return {"items": items, "title": title.group(1).strip() if title else None, "description": meta("description"),
            "robots": meta("robots"), "canonical": canon.group(1) if canon else None}


def has_faq(details_text: str) -> bool:
    """Ürünün kendi açıklamasında soru–cevap bölümü var mı (sayfanın menüsündeki "Sıkça Sorulan Sorular"
    bağlantısı sayılmaz; o yüzden sayfa değil T-soft açıklaması okunur)."""
    return bool(re.search(r"S[ıi]k[çc]a Sorulan Sorular", details_text, re.I)) or details_text.count("?") >= 2


def audit(page: dict[str, Any], comment_count: int, faq_in_description: bool = False) -> list[str]:
    """Sayfanın eksikleri (CHECKS anahtarları)."""
    found: list[str] = []
    book = next((it for it in page["items"] if _types(it) & {"Book", "Product"}), None)
    types = set().union(*[_types(it) for it in page["items"]]) if page["items"] else set()
    if not book:
        found.append("no_book")
    else:
        if not book.get("isbn") and not book.get("gtin13"):
            found.append("no_isbn")
        author = book.get("author")
        authors = author if isinstance(author, list) else [author] if author else []
        if authors:
            if not all(isinstance(a, dict) and "Person" in _types(a) for a in authors):
                found.append("author_not_person")
            if not any(isinstance(a, dict) and a.get("sameAs") for a in authors):
                found.append("author_no_sameas")
        if not book.get("publisher"):
            found.append("no_publisher")
        if not book.get("numberOfPages"):
            found.append("no_pages")
        offers = book.get("offers")
        o = offers[0] if isinstance(offers, list) and offers else offers
        if not isinstance(o, dict) or not o.get("price") or not o.get("availability"):
            found.append("no_offer")
        if comment_count > 0 and not book.get("aggregateRating"):
            found.append("no_rating")
    if faq_in_description and "FAQPage" not in types:
        found.append("no_faq")
    t, d = (page["title"] or "").strip().casefold(), (page["description"] or "").strip().casefold()
    if t and d and t == d:
        found.append("desc_is_title")
    if not page["canonical"]:
        found.append("no_canonical")
    if page["robots"] and "noindex" in page["robots"].lower():
        found.append("noindex")
    return found


def organization(page: dict[str, Any]) -> Optional[dict[str, Any]]:
    org = next((it for it in page["items"] if "Organization" in _types(it)), None)
    return {k: org.get(k) for k in ("name", "description", "url", "logo", "sameAs", "foundingDate")} if org else None


class Fetcher:
    """robots.txt'e uyan, kimliği açık, tek bağlantılı okuyucu."""

    def __init__(self, site: str):
        self.site = site.rstrip("/")
        self.robots = urllib.robotparser.RobotFileParser()
        try:
            r = httpx.get(f"{self.site}/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=20, follow_redirects=True)
            self.robots.parse(r.text.splitlines())
        except httpx.HTTPError:
            self.robots.parse([])
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30, follow_redirects=True)

    def allowed(self, url: str) -> bool:
        return self.robots.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> tuple[int, str]:
        r = self.client.get(url)
        return r.status_code, r.text if r.status_code == 200 else ""

    def close(self) -> None:
        self.client.close()


def theme_request(counts: dict[str, int], checked: int, org: Optional[dict[str, Any]], example: Optional[dict[str, Any]]) -> str:
    """T-soft / ajans için tema isteği belgesi (Markdown). Sayılar son taramadan."""
    pct = lambda k: f"%{round(100 * counts.get(k, 0) / checked)}" if checked else "—"  # noqa: E731
    ex = example or {}
    person = {"@type": "Person", "name": ex.get("author") or "Yazar Adı",
              "sameAs": [ex.get("wikidata") or "https://www.wikidata.org/wiki/Q…", "https://tr.wikipedia.org/wiki/…"]}
    book = {"@context": "https://schema.org", "@type": ["Book", "Product"], "name": ex.get("name") or "Kitap Adı",
            "isbn": ex.get("isbn") or "978…", "author": person,
            "publisher": {"@type": "Organization", "name": ex.get("brand") or "Timaş Yayınları"},
            "numberOfPages": ex.get("pages") or 240, "inLanguage": "tr", "bookFormat": "https://schema.org/Paperback",
            "image": ex.get("image") or "https://timas.com.tr/…jpg",
            "offers": {"@type": "Offer", "price": ex.get("price") or "0.00", "priceCurrency": "TRY",
                       "availability": "https://schema.org/InStock", "url": ex.get("url") or "https://timas.com.tr/…"},
            "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.8", "reviewCount": "12"}}
    faq = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": "Bu kitap hangi yaş grubu için?", "acceptedAnswer": {"@type": "Answer", "text": "…"}}]}
    orgj = {"@context": "https://schema.org", "@type": "Organization", "name": "Timaş Yayınları", "url": "https://timas.com.tr",
            "logo": "https://timas.com.tr/…logo.png", "foundingDate": "…",
            "sameAs": ["https://www.instagram.com/…", "https://x.com/…", "https://www.youtube.com/…", "https://www.wikidata.org/wiki/Q…"]}
    lines = [
        "# timas.com.tr — yapılandırılmış veri (schema.org) tema isteği",
        "",
        f"Son tarama: {checked} kitap sayfası (yalnız okunarak). Aşağıdaki oranlar bu taramadan.",
        "",
        "## 1. Kitap sayfası (Book + Product)",
        "",
        f"- Yazar `Person` olarak ve `sameAs` ile (Wikidata/Wikipedia): eksik {pct('author_no_sameas')}. Veri: CRM yazar kaydına "
        "Wikidata kimliği alanı; T-soft yazar (Model) kaydına aktarılır, tema `sameAs`'a basar.",
        f"- `aggregateRating`: yorumu olup puanı şemada olmayan {counts.get('no_rating', 0)} sayfa. Tema, T-soft CommentCount/CommentRate "
        "alanlarından basmalı; yorum yoksa hiç basmamalı.",
        f"- `numberOfPages`: eksik {pct('no_pages')}. Kaynak: künye (Additional6).",
        f"- `offers` (price, priceCurrency, availability): eksik {pct('no_offer')}.",
        f"- ISBN: eksik {pct('no_isbn')}.",
        "",
        "Örnek (gerçek kitaptan):",
        "",
        "```json",
        json.dumps(book, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 2. Soru–cevap (FAQPage)",
        "",
        f"Açıklamasında soru–cevap bölümü olup şeması olmayan {counts.get('no_faq', 0)} sayfa. Ürün açıklamasındaki "
        "«Sıkça Sorulan Sorular» başlığı altındaki soru/cevaplar FAQPage olarak basılmalı. (Google zengin sonuç göstermese de "
        "yapay zekâ motorları bu biçimi alıntılar.)",
        "",
        "```json",
        json.dumps(faq, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 3. Kurum (Organization)",
        "",
        f"Şu an: `{json.dumps(org or {}, ensure_ascii=False)[:300]}`. Ad «Timaş Yayınları» olmalı, açıklama kampanya metni yerine "
        "yayınevini anlatmalı; logo, kuruluş yılı ve sosyal hesaplar `sameAs`'ta.",
        "",
        "```json",
        json.dumps(orgj, ensure_ascii=False, indent=2),
        "```",
        "",
        "## 4. Başlık etiketleri",
        "",
        f"Meta açıklama başlığın kopyası: {pct('desc_is_title')}. T-soft SEO şablonu (`%UrunAd% %KatAd% %Marka% %Model%`) açıklama için "
        "kullanılmamalı; ürünün kendi SEO açıklaması (CRM'den) basılmalı.",
        "",
        "## 5. llms.txt",
        "",
        "Site kökündeki `llms.txt` şu an boş. İçerik SEO & GEO → llms.txt ekranından indirilir, site köküne konur.",
    ]
    return "\n".join(lines)
