"""Model önerisi: ürünün kendi T-soft kaydından SEO başlığı, meta açıklama, arama kelimeleri ve açıklama.

Model yalnız verilen metindeki bilgiyi kullanır; sayfa sayısı, yaş grubu, ödül gibi kayıtta olmayan bilgiyi
uydurmaması istenir ve çıktı kurallarla yeniden denetlenir. Sonuç yalnız öneridir: kullanıcı onaylamadan
T-soft'a hiçbir şey gitmez. Model LLM kapısından (`rt.llm_for("seo", …)`) gider; dış buluta gitmez.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from . import rules

#: Öneride değiştirilebilen alanlar. SeoLink (adres) bilerek yok: adres değişimi mevcut bağlantıları ve
#: Google'daki sıralamayı kırar, yönlendirme ayrı bir iştir.
FIELDS = ("SeoTitle", "SeoDescription", "SearchKeywords", "Details")

PROMPT = """Sen Timaş Yayınları'nın e-ticaret sitesi için Türkçe SEO ve yapay zekâ görünürlüğü (GEO) editörüsün.
Aşağıdaki kitap ürününün kaydını iyileştir. Kurallar:
- YALNIZ aşağıdaki kayıtta yazan bilgiyi kullan. Kayıtta olmayan sayfa sayısı, yaş grubu, ödül, baskı sayısı,
  yazar biyografisi, tarih UYDURMA. Emin olmadığın bilgiyi yazma.
- SeoTitle: {title_min}–{title_max} karakter. Kitap adı + yazar (kayıtta varsa) + "Timaş Yayınları".
- SeoDescription: {meta_min}–{meta_max} karakter, kitabı anlatan tek paragraf, tırnak ve emoji yok.
- SearchKeywords: virgülle ayrılmış 5–10 arama kelimesi (kitap adı, yazar, konu, tür; yazım varyantları).
- Details: HTML. Mevcut açıklamadaki bilgiyi koru, en az {desc_min_words} kelimeye ulaşacak biçimde kitabın
  konusunu anlatan paragraflar yaz; sonuna <h3>Sıkça Sorulan Sorular</h3> başlığı altında kayıttaki bilgiyle
  cevaplanabilen 2–4 soru–cevap ekle (<p><strong>Soru?</strong><br>Cevap</p>). Kayıt kısaysa daha az soru yaz.
- Mevcut alan zaten kurallara uyuyorsa aynen bırak.
Sadece şu JSON'u döndür, başka hiçbir şey yazma:
{{"SeoTitle": "...", "SeoDescription": "...", "SearchKeywords": "...", "Details": "..."}}

ÜRÜN KAYDI
Ürün adı: {name}
Marka/yayınevi: {brand}
Kategori: {category}
Barkod/ISBN: {barcode}
Mevcut SeoTitle: {seo_title}
Mevcut SeoDescription: {seo_desc}
Mevcut SearchKeywords: {keywords}
Mevcut kısa açıklama: {short}
Mevcut açıklama (HTML'siz):
{details}
"""


def _category(p: dict[str, Any]) -> str:
    for k in ("DefaultCategoryPath", "DefaultCategoryName", "CategoryName"):
        if p.get(k):
            return str(p[k])
    return "-"


def build_prompt(p: dict[str, Any], lim: dict[str, int]) -> str:
    return PROMPT.format(
        **lim, name=p.get("ProductName") or "-", brand=p.get("Brand") or "-", category=_category(p),
        barcode=p.get("Barcode") or "-", seo_title=rules.text_of(p.get("SeoTitle")) or "(boş)",
        seo_desc=rules.text_of(p.get("SeoDescription")) or "(boş)",
        keywords=rules.text_of(p.get("SearchKeywords")) or "(boş)",
        short=rules.text_of(p.get("ShortDescription")) or "(boş)",
        details=rules.text_of(p.get("Details")) or "(boş)")


def parse(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        raise ValueError("Model cevap vermedi.")
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Model cevabında JSON bulunamadı.")
    data = json.loads(m.group(0))
    out = {k: str(data.get(k) or "").strip() for k in FIELDS}
    if not any(out.values()):
        raise ValueError("Model boş öneri döndürdü.")
    return out


def suggest(llm: Any, p: dict[str, Any], lim: dict[str, int]) -> dict[str, str]:
    raw = llm.chat([{"role": "user", "content": build_prompt(p, lim)}], max_tokens=3000, temperature=0.2)
    return parse(raw)


def changed(p: dict[str, Any], fields: dict[str, str]) -> dict[str, str]:
    """Mevcut kayıttan gerçekten farklı olan alanlar; yalnız bunlar T-soft'a gider."""
    return {k: v for k, v in fields.items() if k in FIELDS and v and v.strip() != str(p.get(k) or "").strip()}
