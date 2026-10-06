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
- SeoTitle: {title_min}–{title_max} karakter. Biçim: "Kitap adı - Yazar | Yayınevi". Yazar kayıtta varsa MUTLAKA başlıkta
  olsun (çok yazarlıysa ilk yazar). Yayınevi kayıttaki Brand ile birebir aynı yazılır, kısaltılmaz ("Timaş Çocuk"
  "Timaş" olmaz); karakter sınırı yalnız "Kitap adı - Yazar" kısmına uygulanır, yayınevi her zaman eklenir. Kategori adı başlığa girmez.
- SeoDescription: {meta_min}–{meta_max} karakter (sınırı aşma, say), kitabı anlatan tek paragraf; başlığı tekrar etme,
  tırnak ve emoji yok. Yazar adını geçir.
- SearchKeywords: virgülle ayrılmış 5–10 arama kelimesi (kitap adı, yazar, konu, tür; yazım varyantları).
- Details: HTML. Mevcut açıklamadaki bilgiyi koru, en az {desc_min_words} kelimeye ulaşacak biçimde kitabın
  konusunu anlatan paragraflar yaz; sonuna <h3>Sıkça Sorulan Sorular</h3> başlığı altında kayıttaki bilgiyle
  cevaplanabilen 2–4 soru–cevap ekle (<p><strong>Soru?</strong><br>Cevap</p>). Kayıt kısaysa daha az soru yaz.
- Mevcut alan zaten kurallara uyuyorsa aynen bırak.
Sadece şu JSON'u döndür, başka hiçbir şey yazma:
{{"SeoTitle": "...", "SeoDescription": "...", "SearchKeywords": "...", "Details": "..."}}

ÜRÜN KAYDI
Ürün adı: {name}
Yazar: {author}
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


TARGET_BLOCK = """
HEDEF ARAMA SORGUSU
Bu ürün sayfası Google'da şu sorguda görünüyor ama az tıklanıyor ya da ilk sıralarda değil: «{query}»
- SeoTitle ve SeoDescription'da bu sorgunun kelimelerini, kayıttaki bilgiyle çelişmeden ve doğal biçimde geçir;
  SearchKeywords'e sorguyu ekle.
- Sorguda kayıtta karşılığı olmayan bir istek varsa (ör. "pdf", "özet", "ücretsiz", "indir", başka bir yayınevi) onu
  metne YAZMA; yalnız kayıttaki bilgiyle uyuşan kelimeleri kullan.
"""


def build_prompt(p: dict[str, Any], lim: dict[str, int], target: Optional[str] = None) -> str:
    base = _prompt(p, lim)
    if not (target or "").strip():
        return base
    head, sep, tail = base.partition("ÜRÜN KAYDI")
    return head + TARGET_BLOCK.format(query=target.strip()[:300]) + "\n" + sep + tail


def target_check(fields: dict[str, str], query: Optional[str]) -> Optional[dict[str, Any]]:
    """Hedef sorgunun anlamlı kelimeleri (3+ harf) başlıkta, meta açıklamada ve arama kelimelerinde geçiyor mu?
    Kelime kökü (ilk 5 harf) karşılaştırılır; Türkçe ek farkı eksik sayılmaz. Yalnız bilgi: onayı insan verir."""
    q = (query or "").strip()
    if not q:
        return None
    words = [w for w in re.findall(r"\w+", _lower(q)) if len(w) >= 3]

    def has(text: Any) -> list[str]:
        stems = {_stem(t) for t in re.findall(r"\w+", _lower(rules.text_of(text) or ""))}
        return [w for w in words if _stem(w) not in stems]

    miss_t, miss_m, miss_k = has(fields.get("SeoTitle")), has(fields.get("SeoDescription")), has(fields.get("SearchKeywords"))
    return {"query": q, "words": words, "inTitle": not miss_t, "inMeta": not miss_m, "inKeywords": not miss_k,
            "missingTitle": miss_t, "missingMeta": miss_m}


def _prompt(p: dict[str, Any], lim: dict[str, int]) -> str:
    return PROMPT.format(
        **lim, name=p.get("ProductName") or "-", author=rules.text_of(p.get("Model")) or "-",
        brand=p.get("Brand") or "-", category=_category(p),
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


#: Kural → modelin düzelttiği alan. Listede olmayan kural (görsel, ISBN) elle çözülür; ekranda öyle yazar.
RULE_FIELD = {
    "meta_missing": "SeoDescription", "meta_same_as_title": "SeoDescription", "meta_length": "SeoDescription",
    "title_missing": "SeoTitle", "title_length": "SeoTitle", "title_duplicate": "SeoTitle",
    "desc_missing": "Details", "desc_short": "Details", "faq_missing": "Details",
    "keywords_missing": "SearchKeywords",
}


def fixable(issues: list[dict[str, Any]]) -> bool:
    return any(i.get("rule") in RULE_FIELD for i in issues)


def _cut(text: str, limit: int) -> str:
    """Sınırı aşan metni cümle sonundan, yoksa kelime sınırından keser; kelime ortadan bölünmez."""
    if len(text) <= limit:
        return text
    head = text[:limit]
    end = max(head.rfind(". "), head.rfind("! "), head.rfind("? "), head.rfind(".") if head.endswith(".") else -1)
    if end >= limit * 0.6:
        return head[:end + 1].strip()
    return head[:head.rfind(" ")].rstrip(" ,;:-–") if " " in head else head


def publisher_title(title: str, brand: Optional[str], max_len: int) -> str:
    """Başlık «Kitap adı - Yazar | Yayınevi». Yayınevi ürünün yayınevi (T-soft Brand) ile birebir, kısaltmasız ve HER
    ZAMAN yazılır (e-ticaret ekibi 10-06: «60–65 karakterde marka düşüyordu»); karakter sınırı yalnız «Kitap adı -
    Yazar» kısmına uygulanır, bütün başlık CRM alanının 100 karakterini aşmaz. Sitede yayınevi boşsa yayınevi
    gösterilmez (tahmin edilen yayınevi çoğu kez yanlıştı; kullanıcı kararı 10-05)."""
    t, b = (title or "").strip(), re.sub(r"\s+", " ", str(brand or "")).strip()
    if not t:
        return t
    base = core_title(t)
    if len(base) > max_len:
        base = _cut(base, max_len)
    if not b:
        return base
    full = f"{base} | {b}"
    return full if len(full) <= TITLE_HARD_MAX else _cut(base, TITLE_HARD_MAX - len(b) - 3) + f" | {b}"


#: CRM SEO başlığı alanının uzunluğu; yayınevi eklenmiş başlık bunu aşmaz.
TITLE_HARD_MAX = 100
_SENT_END = re.compile(r"[.!?…][\"'»”’)]*$")
_SENT_SPLIT = re.compile(r"[.!?…][\"'»”’)]*(?=\s|$)")
#: Nokta taşıyan ama cümle bitirmeyen kısaltmalar ve tek harfli baş harf («Sharon M.», «Prof. Dr.»).
_ABBREV = re.compile(r"(?:\b[A-ZÇĞİÖŞÜ]|\b(?:Dr|Prof|Doç|Yrd|Av|Op|Uzm|Hz|Sn|St|vb|vs|bkz|Mr|Mrs|Ms|Jr|No|s|c|Cilt|Haz|Çev|Ed))\.$", re.I)

def core_title(title: str) -> str:
    """Başlığın «| Yayınevi» öncesi kısmı (uzunluk kuralı buna uygulanır)."""
    t = (title or "").strip()
    return t.rsplit(" | ", 1)[0].strip() if " | " in t else t


def complete_sentence(text: str) -> bool:
    """Metin tam cümleyle mi bitiyor (nokta, ünlem, soru, üç nokta; ardından tırnak/parantez olabilir)."""
    t = (text or "").strip()
    return bool(_SENT_END.search(t)) and not _ABBREV.search(t)


def fit_meta(text: str, max_len: int, floor: int = 70) -> Optional[str]:
    """Meta açıklama asla yarım cümleyle bitmez (e-ticaret ekibi 10-06: 216 açıklama «…okuyucuya eşsiz bir» diye
    kesilmişti). Sınıra sığan en uzun tam-cümle öneki döner; tam cümle `floor` karakterden kısa kalırsa ya da hiç
    yoksa None (açıklama yeniden yazılmalı; kelime ortasından/cümle ortasından kesilmez)."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if not t:
        return None
    if len(t) <= max_len and complete_sentence(t):
        return t
    best = None
    for m in _SENT_SPLIT.finditer(t):
        if m.end() <= max_len and not _ABBREV.search(t[:m.end()]):
            best = t[:m.end()].strip()
    return best if best and len(best) >= floor else None


def enforce(fields: dict[str, str], lim: dict[str, int], brand: Optional[str] = None) -> dict[str, str]:
    """Model sayamasa da sınır aşılmaz: ürün önerisinde (brand verilir) başlık «Ad - Yazar | Yayınevi» olur, sınır
    yalnız «Ad - Yazar» kısmına uygulanır; rehber/sayfa önerisinde başlık kelime sınırından kısalır. Meta açıklama
    yalnız cümle sonundan kısalır; sığan tam cümle yoksa boş bırakılır (yarım cümle hiçbir yere gitmez)."""
    out = dict(fields)
    t = out.get("SeoTitle", "")
    if brand is not None:  # ürün önerisi: yayınevi birebir ya da yok; rehber/sayfa önerileri brand vermez
        t = publisher_title(t, brand, lim["title_max"])
    elif len(t) > lim["title_max"]:
        t = _cut(t, lim["title_max"])
    out["SeoTitle"] = t
    m = out.get("SeoDescription", "")
    out["SeoDescription"] = (fit_meta(m, lim["meta_max"]) or "") if m else m
    return out


def _source_text(p: dict[str, Any]) -> str:
    parts = [p.get(k) for k in ("ProductName", "Model", "Brand", "Barcode", "SeoTitle", "SeoDescription",
                                "SearchKeywords", "ShortDescription", "Details", "DefaultCategoryPath",
                                "DefaultCategoryName")]
    return _lower(rules.text_of(" ".join(str(x) for x in parts if x)))


def _fold(s: str) -> str:
    """Karşılaştırma için aksan ve ı/i farkı silinmiş küçük harf («Gazzâlî» = «Gazzali», «İskender» = «Iskender»)."""
    import unicodedata
    s = _lower(s or "").replace("ı", "i")
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _lower(s: str) -> str:
    """Türkçe küçük harf: `casefold` "İ"yi "i̇" (noktalı) yapar, "İlk" kaynaktaki "ilk" ile eşleşmezdi."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def _blocks(html_text: Any) -> str:
    """Blok etiketleri (paragraf, başlık, satır) cümle sınırı sayılır; yoksa başlığın ilk kelimesi cümle ortası görünür."""
    return rules.text_of(re.sub(r"<\s*/?\s*(p|h\d|li|br|div|ul|ol)\b[^>]*>", ". ", str(html_text or ""), flags=re.I))


def _stem(word: str) -> str:
    """Türkçe ek yüzünden aynı ad farklı görünmesin: kesme işaretinden sonrası atılır, uzun kelimede kök ~ ilk 5 harf."""
    w = _lower(re.split(r"['’]", word)[0])
    return w[:5] if len(w) > 6 else w


def unsupported(p: dict[str, Any], fields: dict[str, str]) -> list[str]:
    """Gerçeklik denetimi: önerideki sayılar ve cümle ortasındaki özel adlar kaynak kayıtta geçiyor mu?
    Geçmeyen her biri listelenir; ekranda "kaynakta yok" diye gösterilir, onaylayan kişi bakar."""
    src = _source_text(p)
    stems = {_stem(t) for t in re.findall(r"\w+", src)}
    found: list[str] = []
    text = " ".join(_blocks(fields.get(k)) for k in FIELDS)
    # İstemin kendi yazdırdığı bölüm başlığı kaynaktan gelmez; denetlenmez.
    text = re.sub(r"Sıkça Sorulan Sorular", ". ", text, flags=re.I)
    for n in re.findall(r"\b\d[\d.,]*\b", text):
        n = n.strip(".,")
        if n and n not in src and n not in found:
            found.append(n)
    for sentence in re.split(r"(?<=[.!?:])\s+", text):
        for w in sentence.split()[1:]:
            w = w.strip("\"'“”‘’()[]«»,.;:!?-–")
            if len(w) > 2 and w[0].isupper() and not w.isupper() and _stem(w) not in stems:
                base = re.split(r"['’]", w)[0]
                if base not in found:
                    found.append(base)
    return found


META_PROMPT = """Aşağıdaki kitap için Google arama sonucunda görünecek meta açıklamayı yaz.
- {lo}–{hi} karakter (boşluk dahil; say). Bir ya da iki TAM cümle; son cümle nokta ile biter, yarım cümle yok.
- İlk cümlede kitabın ne anlattığı; yazar adı ({author}) mutlaka geçer. Okura neden okuması gerektiğini sade söyle.
- Başlığı aynen tekrar etme. Tırnak, emoji, ünlem, HTML, «Hemen inceleyin» gibi satış kalıbı yok.
- YALNIZ aşağıdaki kayıtta yazan bilgiyi kullan; kayıtta olmayan kişi, yer, ödül, sayı, yaş UYDURMA.
Yalnız açıklama metnini döndür, başka hiçbir şey yazma.

Başlık: {title}
Kayıt:
{source}"""


def meta_problems(text: str, p: dict[str, Any], title: str, lim: dict[str, int]) -> list[str]:
    """Meta açıklamanın kalite denetimi (boş liste = kabul): tam cümle, 120–160 karakter, yazar adı, başlığın
    aynısı değil, kayıtta olmayan isim/sayı yok, tırnak/emoji/HTML/ünlem yok."""
    out = []
    t = (text or "").strip()
    if not t:
        return ["boş"]
    if not complete_sentence(t):
        out.append("tam cümleyle bitmiyor")
    if not lim["meta_min"] <= len(t) <= lim["meta_max"]:
        out.append(f"{len(t)} karakter; {lim['meta_min']}–{lim['meta_max']} olmalı")
    author = re.split(r"\s*[,;&]\s*|\s+ve\s+", rules.text_of(p.get("Model") or ""))[0].strip()
    if author and _fold(author.split()[-1]) not in _fold(t):
        out.append(f"yazar adı ({author}) geçmiyor")
    if title and _lower(core_title(title)) == _lower(t.rstrip(".")):
        out.append("başlığın aynısı")
    if re.search(r"[\"“”«»<>!]|[\U0001F300-\U0001FAFF]", t):
        out.append("tırnak/ünlem/emoji/HTML var")
    bad = unsupported(p, {"SeoDescription": t})
    if bad:
        out.append("kayıtta olmayan: " + ", ".join(bad[:5]))
    return out


def rewrite_meta(llm: Any, p: dict[str, Any], title: str, lim: dict[str, int], tries: int = 8) -> Optional[str]:
    """Yalnız meta açıklamayı yeniden yazdırır; `meta_problems` boş olan ilk cevap döner. Olmazsa en az sorunlu tam
    cümleli cevap döner (çağıran «aralık dışı» sayar). Her denemede neyin yanlış olduğu modele açıkça söylenir."""
    src = rules.text_of(" ".join(str(p.get(k) or "") for k in ("ProductName", "Model", "Brand", "ShortDescription", "Details")))[:3500]
    author = re.split(r"\s*[,;&]\s*|\s+ve\s+", rules.text_of(p.get("Model") or ""))[0].strip() or "kayıtta yok"
    lo, hi = lim["meta_min"] + 10, lim["meta_max"] - 5
    messages = [{"role": "user", "content": META_PROMPT.format(lo=lo, hi=hi, author=author, title=title, source=src)}]
    best, best_n = None, 99
    for k in range(tries):
        raw = llm.chat(messages, max_tokens=400, temperature=0.3 if k < 3 else 0.5) or ""
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip().strip('"“”')
        text = re.sub(r"\s+", " ", text)
        cand = fit_meta(text, lim["meta_max"], floor=1) or text
        probs = meta_problems(cand, p, title, lim)
        if not probs:
            return cand
        if complete_sentence(cand) and len(probs) < best_n:
            best, best_n = cand, len(probs)
        fix = []
        if len(text) < lim["meta_min"]:
            fix.append(f"şu an {len(text)} karakter, çok kısa: kayıttaki bilgiden bir tam cümle daha ekle, toplam {lo}–{hi} karakter olsun")
        elif len(text) > lim["meta_max"]:
            fix.append(f"şu an {len(text)} karakter, çok uzun: kısalt, toplam {lo}–{hi} karakter olsun")
        fix += [x for x in probs if "karakter" not in x]
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "Düzelt: " + "; ".join(fix) + ". Yalnız açıklamayı döndür."}]
    return best


def violations(fields: dict[str, str], lim: dict[str, int]) -> list[str]:
    """Önerinin uzunluk sınırlarına uymayan alanları, modele geri söylenecek biçimde."""
    out = []
    t, m = fields.get("SeoTitle", ""), fields.get("SeoDescription", "")
    c = core_title(t)
    if t and not lim["title_min"] <= len(c) <= lim["title_max"]:
        out.append(f"SeoTitle «| Yayınevi» öncesi {len(c)} karakter, {lim['title_min']}–{lim['title_max']} olmalı")
    if m and not lim["meta_min"] <= len(m) <= lim["meta_max"]:
        out.append(f"SeoDescription {len(m)} karakter, {lim['meta_min']}–{lim['meta_max']} olmalı")
    if m and not complete_sentence(m):
        out.append("SeoDescription tam cümleyle bitmiyor; son cümleyi tamamla ya da kısalt, nokta ile bitir")
    if t and m and t.strip().lower() == m.strip().lower():
        out.append("SeoDescription SeoTitle ile aynı olmamalı")
    return out


def suggest(llm: Any, p: dict[str, Any], lim: dict[str, int], target: Optional[str] = None) -> dict[str, str]:
    """Öneri; sınır dışı çıkarsa model bir kez, neyin yanlış olduğu söylenerek düzeltmeye çağrılır. İkinci
    cevap da uymazsa öneri olduğu gibi döner — ekran sayacı kırmızı gösterir, kullanıcı düzenler. `target`: fırsat
    ekranından gelen hedef arama sorgusu (kişisel veri maskeli)."""
    messages = [{"role": "user", "content": build_prompt(p, lim, target)}]
    raw = llm.chat(messages, max_tokens=3000, temperature=0.2)
    fields = parse(raw)
    wrong = violations(fields, lim)
    if wrong:
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "Düzelt: " + "; ".join(wrong) + ". Aynı JSON biçiminde yalnız düzeltilmiş hâli döndür."}]
        # En çok iki düzeltme turu; daha iyi olan (daha az ihlal) tutulur.
        for _ in range(2):
            try:
                reply = llm.chat(messages, max_tokens=3000, temperature=0.2)
                fixed = parse(reply)
            except ValueError:
                break
            now = violations(fixed, lim)
            if len(now) < len(wrong):
                fields, wrong = fixed, now
            if not wrong:
                break
            messages += [{"role": "assistant", "content": reply},
                         {"role": "user", "content": "Hâlâ yanlış: " + "; ".join(now) + ". Karakterleri say, yalnız JSON döndür."}]
    return enforce(fields, lim, p.get("Brand") or "")


def changed(p: dict[str, Any], fields: dict[str, str]) -> dict[str, str]:
    """Mevcut kayıttan gerçekten farklı olan alanlar; yalnız bunlar T-soft'a gider."""
    return {k: v for k, v in fields.items() if k in FIELDS and v and v.strip() != str(p.get(k) or "").strip()}
