"""Sözcük seçimi: Türkçe karşılığı olan yabancı sözcükler ve (çocuk/genç kitabında) okurun yaşına ağır sözcükler.

Hat:
1. Kökler (deterministik): `word_variety._read` — içerik sözcükleri ve sözlüğün çözümleyemediği biçimler
   («online» Zemberek'te yok), özel adlar dışarıda.
2. Aday (model, JSON, `EDITOR_WORD_CHOICE_BATCH` köklük çağrılar; hiçbir kök atlanmaz):
   - yabancı: günümüz Batı dillerinden gelmiş, yerleşmemiş ve yaygın Türkçe karşılığı olan sözcük +
     karşılığı. Arapça/Farsça kökenli yerleşik sözcükler istenmez;
   - yaş: yalnız kitap profili çocuk ya da genç okur ise; kitabın yaş aralığındaki okurun anlamını
     bilmeyeceği sözcük + daha basit karşılığı.
   Model listede olmayan sözcük uyduramaz (liste dışı cevap atılır); karşılığın her sözcüğü sözlükte olmalı.
3. Doğrulama (model, kapalı soru, iki sırada ortalama), kitabın kendi cümlesiyle: bu cümlede önerilen
   karşılık doğru ve daha uygun mu (yabancı) / bu sözcük bu yaştaki okur için ağır mı (yaş)? `p ≥ KEEP` → WARN.

Bulgu sözcük başına bir tane: ilk geçtiği sayfa, bütün sayfalar ayrıntıda, öneri alanında karşılık.
Ölçüm: ÖLÇÜM BEKLİYOR — docs/son-okuma/word_choice.md.
"""

from __future__ import annotations

import asyncio
import collections

from .. import book_type, db, schemas
from ..llm import Llm, PromptRef
from . import _continuity as C
from . import _doc_context as D
from . import _messages as M
from . import _spelling_judge as J
from . import _spelling_text as T
from . import _word_variety as W

NAME = "word_choice"
VERSION = "3"
LABEL = "Sözcük seçimi"

DIRECTOR = "book-director"
FOREIGN_LIST = PromptRef("proof_word_foreign", "2")
AGE_LIST = PromptRef("proof_word_age", "2")
BATCH = C.setting("word_choice_batch", 80)                 # EDITOR_WORD_CHOICE_BATCH (yalnız çağrı boyu)
CONTEXT_CHARS = C.setting("word_context_chars", 70)         # EDITOR_WORD_CONTEXT_CHARS
PARALLEL = C.setting("word_variety_parallel", 4)            # EDITOR_WORD_VARIETY_PARALLEL
YOUNG_READERS = ("CHILD", "YOUNG")

BETTER = "Evet: sözcük Türkçeye yerleşmemiş; önerilen karşılık bu cümlede AYNI anlamı verir ve daha uygun."
KEEP_AS_IS = ("Hayır: sözcük Türkçeye yerleşmiş, ya da burada gerekli (terim, ad, alıntı), ya da karşılık "
              "anlamı tam vermiyor, ya da bu cümle kitabın anlatısı değil (künye, yazar/çizer tanıtımı, arka kapak).")
HEAVY = "Evet: bu yaştaki okur bu sözcüğün anlamını büyük olasılıkla bilmez; daha basit sözcük gerekir."
FINE = ("Hayır: bu yaştaki okur anlar ya da bağlamdan çıkarır; ya da sözcük öğretmek için bilerek seçilmiş; ya da "
        "bu cümle çocuğun okuyacağı anlatı değil (künye, yazar/çizer tanıtımı, arka kapak, yetişkine not).")


def list_prompt(kind: str, words: list[str], reader: str) -> str:
    """Her sözcük için sınıf istenir (yalnız «seç» denince model boş liste döndürüyordu, 2026-09-27)."""
    if kind == "foreign":
        ask = ("Aşağıdaki HER sözcüğü sınıflandır:\n"
               "- TURKCE: Türkçe ya da Arapça/Farsça kökenli yerleşik sözcük (kitap, dünya, insan, güzel).\n"
               "- YERLESIK: Batı dillerinden gelmiş ama Türkçeye yerleşmiş, sözlükte olan, herkesin kullandığı "
               "(internet, televizyon, telefon, doktor, otobüs).\n"
               "- KARSILIKLI: Batı dillerinden gelmiş, yerleşmemiş ve aynı anlamı veren yaygın bir Türkçe karşılığı "
               "olan; `karsilik` alanına o karşılığı yaz.\n"
               "Emin değilsen TURKCE ya da YERLESIK de. KARSILIKLI dışındakilerde `karsilik` boş kalır.")
    else:
        ask = (f"Okur {reader}. Aşağıdaki HER sözcüğü sınıflandır:\n"
               "- BILIR: bu yaştaki okur anlamını bilir ya da bağlamdan çıkarır.\n"
               "- AGIR: bu yaştaki okur anlamını büyük olasılıkla bilmez; `karsilik` alanına bu yaşa uygun daha "
               "basit bir sözcük yaz.\nEmin değilsen BILIR de.")
    return ask + "\n\nHer sözcük listede tam bir kez, yazımı değiştirmeden.\n\nSözcükler: " + ", ".join(words)


def list_schema(kind: str, n: int) -> dict:
    classes = ["TURKCE", "YERLESIK", "KARSILIKLI"] if kind == "foreign" else ["BILIR", "AGIR"]
    return schemas.obj({"sozcukler": schemas.arr(schemas.obj({
        "sozcuk": {"type": "string", "maxLength": 80}, "sinif": {"type": "string", "enum": classes},
        "karsilik": {"type": "string", "maxLength": 80}}), n, n)})


def reader_of(prof: dict) -> str | None:
    a, b = prof.get("age_from"), prof.get("age_to")
    if prof.get("audience") not in YOUNG_READERS:
        return None
    if a and b:
        return f"{a}-{b} yaş arası bir çocuk"
    return "bir çocuk" if prof.get("audience") == "CHILD" else "bir genç"


def check_prompt(kind: str, what: str, reader: str | None, word: str, alt: str, marked: str, x: str, y: str) -> str:
    head = f"Okuduğun metin {what}; redaksiyonunu yapan deneyimli bir editörsün.\n\nCümle: «{marked}»\n\n"
    if kind == "foreign":
        q = f"Bu cümlede [[{word}]] yerine «{alt}» yazmak doğru ve daha uygun mu?"
    else:
        q = f"Okur {reader}. [[{word}]] sözcüğü bu okur için ağır mı? (Daha basit karşılık: «{alt}».)"
    return head + q + f"\nA) {x}\nB) {y}\nYalnız A ya da B yaz."


async def _candidates(llm: Llm, kind: str, words: list[str], reader: str | None, stats) -> dict[str, str]:
    sem = asyncio.Semaphore(PARALLEL)
    known = set(words)

    async def ask(part):
        async with sem:
            out, _ = await llm.chat(DIRECTOR, [{"role": "user", "content": list_prompt(kind, part, reader or "")}],
                                    prompt=FOREIGN_LIST if kind == "foreign" else AGE_LIST,
                                    schema=list_schema(kind, len(part)), max_tokens=600 + 30 * len(part),
                                    temperature=0.0, thinking=False)
        stats[f"{kind}_calls"] += 1
        return out

    got: dict[str, str] = {}
    for out in await asyncio.gather(*(ask(words[i:i + BATCH]) for i in range(0, len(words), BATCH))):
        for w in (out or {}).get("sozcukler", []):
            s, k = W.lower_tr((w.get("sozcuk") or "").strip()), (w.get("karsilik") or "").strip()
            if s not in known:
                stats[f"{kind}_not_in_list"] += 1        # model listede olmayanı yazdı
            elif w.get("sinif") in ("KARSILIKLI", "AGIR") and k and W.lower_tr(k) != s:
                got.setdefault(s, k)
    return got


async def run(generation_id: str):
    from .word_variety import _boxes, _read
    lex = T.lexicon()
    rd = await asyncio.to_thread(_read, generation_id, lex)
    occs: list[W.Occ] = rd["occs"]
    stats = collections.Counter()
    by = collections.defaultdict(list)
    for o in occs:
        if o.pos in W.CONTENT_POS:
            by[o.lemma].append(o)
    # dört harften kısa kök (bozuk çözümleme: «re», «nim», «cağ») ve kitapta hep büyük harfle geçen biçim (kısaltma ya da
    # başlık: «ISBN», «TSE») sözcük seçimi konusu değildir
    short = [lem for lem in by if len(lem) < 4]
    caps = [lem for lem, os_ in by.items() if all(len(o.word) > 1 and o.word.isupper() for o in os_)]
    for lem in set(short) | set(caps):
        del by[lem]
    stats["skip_short_lemma"], stats["skip_all_caps_lemma"] = len(short), len(caps)
    unknown = {f: ps for f, ps in rd["unknown"].items() if f.isalpha() and len(f) >= 4}
    prof = await D.profile(generation_id)
    what, reader = book_type.describe(prof), reader_of(prof)
    llm = Llm(D.llm_gid(generation_id))
    words = sorted(by)
    stats["lemmas"], stats["unknown_forms"] = len(words), len(unknown)

    foreign = await _candidates(llm, "foreign", words + sorted(unknown), None, stats)
    heavy = await _candidates(llm, "age", words, reader, stats) if reader else {}
    stats["foreign_candidates"], stats["age_candidates"] = len(foreign), len(heavy)
    stats["age_part"] = "on" if reader else "off (okur çocuk/genç değil)"

    # karşılığın her sözcüğü sözlükte olmalı
    def valid(alt: str) -> bool:
        return W.valid_suggestion(alt, lex.valid)
    # karşılık sözcüğün kendisine bir-iki harf uzaksa bu bir yazım farkıdır («suiistimal»/«suistimal»),
    # yabancı ya da ağır sözcük değil; yazım denetiminin işi
    def spelling_variant(w: str, alt: str) -> bool:
        return " " not in alt and T.edit_distance(W.lower_tr(w), W.lower_tr(alt)) <= 2

    cands = [("foreign", w, a) for w, a in foreign.items() if valid(a) and not spelling_variant(w, a)] + \
            [("age", w, a) for w, a in heavy.items() if valid(a) and not spelling_variant(w, a) and w not in foreign]
    stats["dropped_invalid_alternative"] = len(foreign) + len(heavy) - len(cands)

    # bu sözcüğün kitaptaki geçişleri: kök için okuma katmanından, çözümlenemeyen biçim için sayfalar
    tokens_of = {w: by.get(w) for _, w, _ in cands}
    span_text = rd["span_text"]
    first_ctx: dict[str, tuple[str, int, W.Occ | None]] = {}
    for kind, w, _ in cands:
        os_ = tokens_of.get(w)
        if os_:
            o = os_[0]
            first_ctx[w] = (W.marked_context(span_text[(o.page, o.span)], o.start, o.end, CONTEXT_CHARS), o.page, o)
        else:
            page = unknown[w][0]
            txt = next((t for (pg, _), t in span_text.items() if pg == page and w in W.lower_tr(t)), "")
            i = W.lower_tr(txt).find(w)
            first_ctx[w] = (W.marked_context(txt, i, i + len(w), CONTEXT_CHARS) if i >= 0 else f"[[{w}]]", page, None)

    sem = asyncio.Semaphore(PARALLEL)

    async def judge(kind, w, alt):
        marked, page, _ = first_ctx[w]
        x, y = (BETTER, KEEP_AS_IS) if kind == "foreign" else (HEAVY, FINE)
        async with sem:
            p, _ = await J._ab(llm, lambda a, b: check_prompt(kind, what, reader, w, alt, marked, a, b), x, y, [page])
        return kind, w, alt, p

    judged = await asyncio.gather(*(judge(*c) for c in cands))
    kept = [j for j in judged if j[-1] >= J.KEEP]
    stats["dropped_by_check"] = len(judged) - len(kept)
    bv = await asyncio.to_thread(D.book_version, generation_id)
    firsts = [first_ctx[w][2] for _, w, _, _ in kept if first_ctx[w][2] is not None]
    boxes = await asyncio.to_thread(_boxes, bv, firsts) if bv else {}
    findings = []
    for kind, w, alt, p in kept:
        marked, page, o = first_ctx[w]
        os_ = tokens_of.get(w) or []
        pages = sorted({x.page for x in os_}) or sorted(set(unknown.get(w, [])))
        count = len(os_) or len(unknown.get(w, []))
        findings.append(M.put(NAME, {
            # yaşa ağır sözcük tek tek bilgi düzeyinde; editörün uyarısı kitap geneli özettir (aşağıda)
            "page": page, "severity": "WARN" if kind == "foreign" else "INFO",
            "quote": marked.replace("[[", "").replace("]]", ""),
            "bbox": boxes.get(o.idx) if o is not None else None, "suggestion": alt,
            "details": {"kind": kind, "word": w, "alternative": alt, "count": count, "pages": pages, "p": round(p, 3),
                        "context": marked, "group": "yabancı sözcük" if kind == "foreign" else "yaşa ağır sözcük",
                        "confidence": round(p, 3)}}))
        stats["kept_" + kind] += 1
    heavy_rows = sorted((f for f in findings if f["details"]["kind"] == "age"), key=lambda f: -f["details"]["p"])
    if heavy_rows:
        # Tek tek yüzlerce uyarı yerine kitap geneli tek uyarı: çok sayıda ağır sözcük, kitabın beyan edilen yaşla
        # uyumsuzluğunu (ya da CRM yaş aralığının yanlışlığını) gösterir. Tam liste ayrıntıda, güven sırasıyla.
        words_in_book = max(len(occs), 1)
        per1k = round(sum(f["details"]["count"] for f in heavy_rows) / words_in_book * 1000, 1)
        findings.append(M.put(NAME, {
            "page": None, "severity": "WARN", "quote": None,
            "details": {"kind": "age_summary", "reader": reader, "count": len(heavy_rows), "per1000": per1k,
                        "age_from": prof.get("age_from"), "age_to": prof.get("age_to"),
                        "words": [{"word": f["details"]["word"], "alternative": f["details"]["alternative"],
                                   "count": f["details"]["count"], "pages": f["details"]["pages"], "p": f["details"]["p"]}
                                  for f in heavy_rows],
                        "group": "yaşa ağır sözcük", "confidence": heavy_rows[0]["details"]["p"]}}))
    # sıra metne değil kayıtlı alanlara bağlı (metin değişince bulguların sırası oynamasın)
    findings.sort(key=lambda f: (f["page"] or 0, f["details"]["kind"], f["details"].get("word") or ""))
    return findings, dict(stats)
