"""Yazar, kategori ve yayınevi sayfaları: denetim ve öneri (SEO başlığı, meta açıklama, tanıtım metni).

Kaynak: T-soft `link/getLinks` (sayfanın başlık/açıklaması; `semantic_seo_links`) + eşitlenmiş ürünler. Bağ:
ürünün `ModelId` → yazar sayfasının `TableId`, `BrandId` → yayınevi, `DefaultCategoryId` → kategori. Yazar için
Wikidata bilgisi (varsa) basın-web modülünün doğrulanmış kaydından (`semantic_web_authors`, yalnız tek ve kesin
eşleşme) gelir.

Model yalnız verilen bilgiyi kullanır: sayfanın kitapları, satışları, kategori dağılımı, Wikidata özeti. Doğum yeri,
ödül, eğitim gibi verilmeyen bilgi yazılmaz; gerçeklik denetimi (`propose.unsupported`) öneriyi kaynağa karşı tarar.
Öneriler yalnız kayıttır; T-soft'a yazılmaz.
"""
from __future__ import annotations

import collections
import json
import re
from typing import Any, Optional

from . import propose, rules

KINDS = {"model": "Yazar", "category": "Kategori", "brand": "Yayınevi"}
FIELDS = ("SeoTitle", "SeoDescription", "Intro")

#: Sayfa kuralları: (ağırlık, önem, kısa ad, neden).
PAGE_RULES: dict[str, tuple[int, str, str, str]] = {
    "title_missing": (25, "kritik", "SEO başlığı yok", "Sayfa başlığı boşsa arama sonucunda ne olduğu anlaşılmaz."),
    "title_is_name": (15, "yüksek", "Başlık yalnız ad",
                      "Başlık yalnız adı taşıyor; \"kitapları\", yayınevi ya da konu gibi aranan kelimeler yok."),
    "title_length": (6, "orta", "SEO başlığı uzunluğu uygun değil", "Kısa başlık az şey anlatır, uzunu Google keser."),
    "desc_missing": (20, "kritik", "Meta açıklama yok", "Google sayfadan rastgele bir parça gösterir."),
    "desc_is_title": (15, "yüksek", "Meta açıklama başlığın kopyası",
                      "Açıklama başlığı tekrar ediyor; sayfanın ne sunduğunu anlatmıyor."),
    "desc_length": (8, "orta", "Meta açıklama uzunluğu uygun değil", "Çok kısa açıklama boş kalır, uzunu kesilir."),
    "intro_missing": (15, "yüksek", "Tanıtım metni yok",
                      "Sayfada yazarı ya da kategoriyi anlatan metin yok; yapay zekâ cevapları \"bu yazar kim?\" "
                      "sorusunda bu siteyi kaynak gösteremez."),
}
RULE_FIELD = {"title_missing": "SeoTitle", "title_is_name": "SeoTitle", "title_length": "SeoTitle",
              "desc_missing": "SeoDescription", "desc_is_title": "SeoDescription", "desc_length": "SeoDescription",
              "intro_missing": "Intro"}


def _num(v: Any) -> int:
    try:
        return int(float(str(v or 0).replace(",", ".")))
    except ValueError:
        return 0


def stats(products: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """(tür, TableId) → aktif kitap sayısı, toplam satış, en çok satan kitaplar, kategoriler, yayınevleri, yaşlar."""
    out: dict[tuple[str, str], dict[str, Any]] = collections.defaultdict(
        lambda: {"books": 0, "sales": 0, "items": [], "cats": collections.Counter(), "brands": collections.Counter(),
                 "authors": collections.Counter()})
    for p in products:
        if str(p.get("IsActive", "1")).lower() in ("0", "false"):
            continue
        cat = " > ".join(x.strip() for x in f"{p.get('DefaultCategoryPath') or ''}{p.get('DefaultCategoryName') or ''}".split(">") if x.strip())
        keys = [("model", str(p.get("ModelId") or "")), ("brand", str(p.get("BrandId") or "")),
                ("category", str(p.get("DefaultCategoryId") or ""))]
        keys += [("category", str(c.get("CategoryId"))) for c in (p.get("Categories") or []) if isinstance(c, dict)]
        for key in dict.fromkeys(k for k in keys if k[1] and k[1] != "0"):
            s = out[key]
            s["books"] += 1
            s["sales"] += _num(p.get("CountTotalSales"))
            s["items"].append((_num(p.get("CountTotalSales")), rules.text_of(p.get("ProductName")), rules.text_of(p.get("Model"))))
            if cat:
                s["cats"][cat] += 1
            if p.get("Brand"):
                s["brands"][rules.text_of(p.get("Brand"))] += 1
            if p.get("Model"):
                s["authors"][rules.text_of(p.get("Model"))] += 1
    return out


def audit(kind: str, name: str, title: Any, desc: Any, lim: dict[str, int]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []

    def add(rule: str, detail: str) -> None:
        w, sev, t, why = PAGE_RULES[rule]
        issues.append({"rule": rule, "severity": sev, "title": t, "detail": detail, "why": why, "weight": w,
                       "field": RULE_FIELD[rule]})

    t, d, n = rules.text_of(title), rules.text_of(desc), rules.text_of(name)
    if not t:
        add("title_missing", "Sayfanın Title alanı boş.")
    elif t.casefold() == n.casefold():
        add("title_is_name", f"Başlık: «{t}».")
    elif not lim["title_min"] <= len(t) <= lim["title_max"]:
        add("title_length", f"{len(t)} karakter; beklenen {lim['title_min']}–{lim['title_max']}.")
    if not d:
        add("desc_missing", "Sayfanın Description alanı boş.")
    elif d.casefold() in (t.casefold(), n.casefold()):
        add("desc_is_title", f"Açıklama: «{d[:80]}».")
    elif not lim["meta_min"] <= len(d) <= lim["meta_max"]:
        add("desc_length", f"{len(d)} karakter; beklenen {lim['meta_min']}–{lim['meta_max']}.")
    # T-soft'ta yazar ve kategori için okunabilir tanıtım alanı yok; yayınevinde kısa açıklama vardır.
    if kind in ("model", "category"):
        add("intro_missing", "T-soft'ta bu sayfa için tanıtım metni yok.")
    return {"score": max(0, 100 - sum(i["weight"] for i in issues)), "issues": issues}


PROMPT = """Sen Timaş Yayınları'nın e-ticaret sitesi (timas.com.tr) için Türkçe SEO ve yapay zekâ görünürlüğü editörüsün.
Aşağıdaki {kind_tr} sayfası için öneri yaz. Kurallar:
- YALNIZ aşağıdaki bilgiyi kullan. Doğum yeri/tarihi, eğitim, ödül, kişisel hayat gibi verilmeyen bilgi UYDURMA.
  Wikidata özeti verildiyse yalnız oradaki bilgiyi kullanabilirsin.
- SeoTitle: {title_min}–{title_max} karakter. {title_hint}
- SeoDescription: {meta_min}–{meta_max} karakter, tek paragraf; başlığı tekrar etme, tırnak ve emoji yok.
- Intro: 80–160 kelimelik tanıtım paragrafı (HTML değil düz metin). {intro_hint}
Sadece şu JSON'u döndür: {{"SeoTitle": "...", "SeoDescription": "...", "Intro": "..."}}

SAYFA
Tür: {kind_tr}
Ad: {name}
Mevcut başlık: {title}
Mevcut açıklama: {desc}
Sitedeki aktif kitap sayısı: {books}
Toplam satış adedi: {sales}
En çok satan kitaplar: {top}
Kategoriler: {cats}
Yayınevleri: {brands}
{extra}"""

HINTS = {
    "model": ("Biçim: \"Ad Soyad Kitapları | Timaş Yayınları\" ya da sığıyorsa en bilinen kitabıyla.",
              "Yazarı sitedeki kitapları, konuları ve (verildiyse) Wikidata bilgisiyle tanıt; kitap adlarını geçir."),
    "category": ("Biçim: \"<Kategori> Kitapları | Timaş Yayınları\".",
                 "Kategoride ne tür kitaplar olduğunu, öne çıkan kitap ve yazarları anlat."),
    "brand": ("Biçim: \"<Yayınevi> Kitapları | Timaş Yayın Grubu\".",
              "Yayınevinin hangi alanlarda kitap yayımladığını, öne çıkan kitap ve yazarlarını anlat."),
}


def facts(kind: str, name: str, st: dict[str, Any], wiki: Optional[dict[str, Any]]) -> dict[str, Any]:
    items = sorted(st.get("items", []), key=lambda x: (-x[0], x[1]))
    return {
        "books": st.get("books", 0), "sales": st.get("sales", 0),
        "top": [{"name": n, "author": a, "sales": s} for s, n, a in items[:12]],
        "cats": [c for c, _ in st.get("cats", collections.Counter()).most_common(6)],
        "brands": [b for b, _ in st.get("brands", collections.Counter()).most_common(6)],
        "authors": [a for a, _ in st.get("authors", collections.Counter()).most_common(8)] if kind != "model" else [],
        "wikidata": wiki,
    }


def build_prompt(kind: str, name: str, title: Any, desc: Any, f: dict[str, Any], lim: dict[str, int]) -> str:
    th, ih = HINTS[kind]
    extra = []
    if f.get("authors"):
        extra.append("Öne çıkan yazarlar: " + ", ".join(f["authors"]))
    if f.get("wikidata"):
        w = f["wikidata"]
        extra.append("Wikidata özeti: " + json.dumps({k: w.get(k) for k in ("description", "born", "died", "occupations", "awards", "works")
                                                      if w.get(k)}, ensure_ascii=False))
    return PROMPT.format(kind_tr=KINDS[kind], name=name, title=rules.text_of(title) or "(boş)", desc=rules.text_of(desc) or "(boş)",
                         books=f["books"], sales=f["sales"],
                         top="; ".join(f"{t['name']}" + (f" ({t['author']})" if kind != "model" and t["author"] else "") for t in f["top"]) or "-",
                         cats=", ".join(f["cats"]) or "-", brands=", ".join(f["brands"]) or "-",
                         extra="\n".join(extra), title_hint=th, intro_hint=ih, **lim)


def source_record(kind: str, name: str, title: Any, desc: Any, f: dict[str, Any]) -> dict[str, Any]:
    """Gerçeklik denetimi için kaynak: ürün kaydı biçiminde (propose.unsupported bunu okur)."""
    text = " ".join([name, rules.text_of(title), rules.text_of(desc), " ".join(t["name"] + " " + (t["author"] or "") for t in f["top"]),
                     " ".join(f["cats"]), " ".join(f["brands"]), " ".join(f.get("authors") or []),
                     json.dumps(f.get("wikidata") or {}, ensure_ascii=False), "Timaş Yayınları Timaş Yayın Grubu"])
    return {"ProductName": name, "Details": text}


def suggest(llm: Any, kind: str, name: str, title: Any, desc: Any, f: dict[str, Any], lim: dict[str, int]) -> dict[str, str]:
    raw = llm.chat([{"role": "user", "content": build_prompt(kind, name, title, desc, f, lim)}], max_tokens=1500, temperature=0.2)
    text = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Model cevabında JSON bulunamadı.")
    data = json.loads(m.group(0))
    out = {k: rules.text_of(data.get(k)) for k in FIELDS}
    if not any(out.values()):
        raise ValueError("Model boş öneri döndürdü.")
    fixed = propose.enforce({"SeoTitle": out["SeoTitle"], "SeoDescription": out["SeoDescription"]}, lim)
    return {**out, **fixed}
