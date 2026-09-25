"""Ürün SEO/GEO denetimi: her ürün için sorun listesi ve 0–100 puan.

Kurallar T-soft'un döndürdüğü alanlara bakar; eşikler Yönetim ekranından gelir (`SEO_*`). Alan adları mağazanın
konsol kataloğundaki adlardır (SeoTitle, SeoDescription, Details, SearchKeywords, Barcode, ImageUrl). Sayfanın
kendisini (JSON-LD, canonical) bu katman okumaz; o Search Console / tarama verisiyle ayrı değerlendirilir.

Her sorun kullanıcıya "neden" olarak gösterilir: ne eksik, arama motoru ve yapay zekâ cevabı açısından neden
önemli. Metinler koddadır, çünkü kuralın kendisini anlatırlar; ürüne özel metin yoktur.
"""
from __future__ import annotations

import html
import re
from typing import Any

#: Kural kimliği → (ağırlık, önem, kısa ad, açıklama). Ağırlık puandan düşülür; toplam 100'ü geçebilir, puan 0'da durur.
RULES: dict[str, tuple[int, str, str, str]] = {
    "meta_missing": (25, "kritik", "Meta açıklama yok",
                     "Google arama sonucunda sayfadan rastgele bir parça gösterir; yapay zekâ cevaplarında kitabın "
                     "kısa ve doğru bir özeti alınamaz."),
    "meta_length": (8, "orta", "Meta açıklama uzunluğu uygun değil",
                    "Çok kısa açıklama arama sonucunu boş bırakır, çok uzunu Google keser."),
    "title_missing": (20, "kritik", "SEO başlığı yok",
                      "Başlık etiketi ürün adından otomatik kurulur; yazar ve yayınevi gibi aranan bilgiler eksik kalır."),
    "title_length": (6, "orta", "SEO başlığı uzunluğu uygun değil",
                     "Kısa başlık aranan kelimeleri taşımaz, uzun başlık arama sonucunda kesilir."),
    "title_duplicate": (10, "yüksek", "SEO başlığı başka üründe de var",
                        "Aynı başlıklı sayfalar arasında Google hangisini göstereceğini seçemez; biri geri düşer."),
    "desc_missing": (20, "kritik", "Ürün açıklaması yok",
                     "Sayfada kitabı anlatan metin yok; arama motoru ve yapay zekâ neyle eşleştireceğini bilemez."),
    "desc_short": (12, "yüksek", "Ürün açıklaması kısa",
                   "Kısa metin hem aramada zayıf kalır hem de yapay zekâ cevaplarında alıntılanacak içerik vermez."),
    "faq_missing": (6, "orta", "Soru–cevap bloğu yok",
                    "Yapay zekâ asistanları doğrudan soru–cevap biçimindeki içeriği daha kolay alıntılar "
                    "(\"hangi yaş grubu için?\", \"kaç sayfa?\")."),
    "keywords_missing": (5, "düşük", "Arama kelimeleri boş",
                         "Sitenin kendi arama kutusu bu ürünü eş anlamlı ya da yazım farklı aramalarda bulamaz."),
    "image_missing": (8, "yüksek", "Ürün görseli yok",
                      "Google Görseller ve alışveriş sonuçlarında ürün görünmez; paylaşımda önizleme çıkmaz."),
    "barcode_missing": (8, "yüksek", "ISBN/barkod yok",
                        "Kitap ISBN'siyle eşleştirilemez; Google alışveriş ve kitap bilgi kutusu ürünü tanımaz."),
}


def text_of(value: Any) -> str:
    """HTML'den düz metin: etiketler atılır, varlıklar çözülür, boşluklar teke iner."""
    raw = html.unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    return re.sub(r"\s+", " ", raw).strip()


def words(value: Any) -> int:
    return len(re.findall(r"\w+", text_of(value)))


def _has_image(p: dict[str, Any]) -> bool:
    if str(p.get("ImageUrl") or "").strip():
        return True
    imgs = p.get("ImageUrls") or p.get("Images") or []
    return bool(imgs)


def thresholds(conf) -> dict[str, int]:
    def n(key: str, default: int) -> int:
        try:
            return int(conf(key) or default)
        except ValueError:
            return default

    return {"title_min": n("SEO_TITLE_MIN", 30), "title_max": n("SEO_TITLE_MAX", 65),
            "meta_min": n("SEO_META_MIN", 120), "meta_max": n("SEO_META_MAX", 160),
            "desc_min_words": n("SEO_DESC_MIN_WORDS", 150)}


def audit(p: dict[str, Any], lim: dict[str, int], duplicate_titles: set[str]) -> dict[str, Any]:
    """Tek ürünün sorunları ve puanı. `duplicate_titles`: birden çok üründe geçen (küçük harfli) SEO başlıkları."""
    issues: list[dict[str, Any]] = []

    def add(rule: str, detail: str) -> None:
        weight, severity, title, why = RULES[rule]
        issues.append({"rule": rule, "severity": severity, "title": title, "detail": detail, "why": why, "weight": weight})

    meta = text_of(p.get("SeoDescription"))
    if not meta:
        add("meta_missing", "SeoDescription alanı boş.")
    elif not lim["meta_min"] <= len(meta) <= lim["meta_max"]:
        add("meta_length", f"{len(meta)} karakter; beklenen {lim['meta_min']}–{lim['meta_max']}.")

    title = text_of(p.get("SeoTitle"))
    if not title:
        add("title_missing", "SeoTitle alanı boş.")
    else:
        if not lim["title_min"] <= len(title) <= lim["title_max"]:
            add("title_length", f"{len(title)} karakter; beklenen {lim['title_min']}–{lim['title_max']}.")
        if title.lower() in duplicate_titles:
            add("title_duplicate", f"«{title}» başlığı başka ürünlerde de kullanılıyor.")

    details = p.get("Details") or ""
    n_words = words(details)
    if n_words == 0:
        add("desc_missing", "Details alanı boş.")
    else:
        if n_words < lim["desc_min_words"]:
            add("desc_short", f"{n_words} kelime; en az {lim['desc_min_words']} beklenir.")
        if "?" not in text_of(details):
            add("faq_missing", "Açıklamada soru–cevap biçiminde bölüm yok.")

    if not text_of(p.get("SearchKeywords")):
        add("keywords_missing", "SearchKeywords alanı boş.")
    if not _has_image(p):
        add("image_missing", "ImageUrl boş, ek görsel yok.")
    if not str(p.get("Barcode") or "").strip():
        add("barcode_missing", "Barcode alanı boş.")

    score = max(0, 100 - sum(i["weight"] for i in issues))
    return {"score": score, "issues": issues}


def duplicate_titles(products: list[dict[str, Any]]) -> set[str]:
    seen: dict[str, int] = {}
    for p in products:
        t = text_of(p.get("SeoTitle")).lower()
        if t:
            seen[t] = seen.get(t, 0) + 1
    return {t for t, n in seen.items() if n > 1}
