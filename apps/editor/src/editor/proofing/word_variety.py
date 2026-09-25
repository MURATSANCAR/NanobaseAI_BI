"""Kelime çeşitliliği ve yakın tekrar (redaksiyon): kitabın tekil kelime haritası, anlamlarıyla.

Soru (yayınevi redaksiyonu): bir kitapta hangi sözcük kaç kez, hangi anlamda geçiyor; aynı sözcük
aynı anlamda kısa aralıkla tekrarlanıyor mu? «göze girdi», «gözüme toz kaçtı», «dolabın gözü»
üç ayrı «göz»dür: yan yana geçseler de tekrar değildir.

Hat:
1. Kök (deterministik): `_spelling_text.read_book` belirteçleri; özel adlar, bozuk span'lar ve
   hikâye dışı sayfalar dışarıda. Her biçim Zemberek (zeyrek) ile köke iner («gözüme» → göz,
   «yüzdü» → yüzmek; ad «yüz» ile karışmaz). Birden çok kök varsa `_word_variety.choose_lemmas`.
2. Anlam (model, `book-director`, JSON şema): kitapta en az iki kez geçen her içerik kökünün
   (ad, sıfat, zarf, fiil) bütün geçişleri bağlamlarıyla gruplanır: anlam etiketi + deyim.
   Hiçbir kök ya da geçiş atlanmaz; atanamayan geçiş bir kez yeniden sorulur, yine atanamazsa
   haritada «belirsiz» olarak görünür ve sayılır.
3. Yakın tekrar (deterministik): aynı kök + AYNI ANLAM, ardışık geçişler arasında en çok
   `EDITOR_WORD_ECHO_SENTENCES` cümle (varsayılan 1: aynı ya da bir sonraki cümle). İkileme
   («yavaş yavaş», «göz göze») tekrar değildir.
4. Yargı (model, kapalı soru, iki sırada sorulup ortalanır, `_spelling_judge._ab`): bu tekrar
   redaksiyonda düzeltilmeli mi, yoksa bilinçli mi (vurgu, tekrar sanatı, diyalog, terim)?
   `p ≥ KEEP` → WARN bulgu; öneri alanına modelin aynı anlamı veren karşılıkları.

Çıktı: bulgular (yakın tekrar) + `stats.map` (kelime haritası: her kök, biçimleri, sayfaları,
anlamları) + çeşitlilik ölçüleri (MTLD, tekil kök sayısı, bir kez geçenler). Harita kart
servisinde `GET /v1/books/{id}/proofing/word-map`.

Ölçüm: ÖLÇÜM BEKLİYOR — docs/son-okuma/word_variety.md.
"""

from __future__ import annotations

import asyncio
import collections

from ..llm import Llm, PromptRef
from . import _continuity as C
from . import _spelling_judge as J
from . import _spelling_text as T
from . import _word_variety as W

NAME = "word_variety"
VERSION = "1"
LABEL = "Kelime çeşitliliği ve yakın tekrar"

DIRECTOR = "book-director"
SENSES = PromptRef("proof_word_senses", "1")
ALTERNATIVES = PromptRef("proof_word_alternatives", "1")

# Yakın tekrar penceresi, cümle cinsinden: 0 = aynı cümle, 1 = aynı ya da bir sonraki cümle.
# Okurun tekrarı fark ettiği mesafe; sözcük sayısı değil cümle, çünkü çocuk kitabında cümle kısa,
# romanda uzun — cümle ikisine de uyar.
ECHO_SENTENCES = C.setting("word_echo_sentences", 1)       # EDITOR_WORD_ECHO_SENTENCES
# Anlam çağrısı başına geçiş sayısı: yalnız çağrı boyu (hız/bağlam), kapsamı değiştirmez.
SENSE_BATCH = C.setting("word_sense_batch", 80)            # EDITOR_WORD_SENSE_BATCH
# Geçişin iki yanında gösterilen karakter (anlam için bağlam).
CONTEXT_CHARS = C.setting("word_context_chars", 70)        # EDITOR_WORD_CONTEXT_CHARS
PARALLEL = C.setting("word_variety_parallel", 4)           # EDITOR_WORD_VARIETY_PARALLEL


def _alt_schema() -> dict:
    from .. import schemas
    return schemas.obj({"oneriler": schemas.arr({"type": "string", "maxLength": 80}, 0, 5)})


def _read(generation_id: str, lex) -> dict:
    """Belirteçler → sözcük geçişleri (Occ) ve sayımlar. Model yok."""
    bk = T.read_book(generation_id, lex)
    story = {p["page_no"] for p in C.story_pages(bk["pages"])}
    span_keys = [(s["page"], s["idx"]) for s in bk["spans"]]
    span_text = {(s["page"], s["idx"]): s["text"] for s in bk["spans"]}
    toks = bk["tokens"]
    sids = W.sentence_ids([t.sent_start for t in toks])
    stats = collections.Counter()
    raw = []            # (idx, tok, form)
    form_cands: dict[str, list] = {}
    form_counts = collections.Counter()
    for i, t in enumerate(toks):
        if t.garbled or t.fragment:
            stats["skip_garbled_or_fragment"] += 1
            continue
        if t.page not in story:
            stats["skip_non_story_page"] += 1
            continue
        if W.word_kind(t.base, t.apos, t.sent_start) == "name":
            stats["skip_name"] += 1
            continue
        form = W.lower_tr(t.base)
        if form not in form_cands:
            form_cands[form] = W.candidates(lex.analyses(form))
        cs = form_cands[form]
        if t.base[:1].isupper() and not t.base.isupper() and cs and all(c[4] for c in cs):
            stats["skip_name"] += 1       # cümle başında, sözlükte yalnız özel ad
            continue
        form_counts[form] += 1
        raw.append((i, t, form))
    chosen = W.choose_lemmas(form_cands, form_counts)
    occs, unknown = [], collections.defaultdict(list)
    for i, t, form in raw:
        if form not in chosen:
            unknown[form].append(t.page)
            continue
        lem, pos, amb = chosen[form]
        occs.append(W.Occ(i, t.page, t.span, t.start, t.end, sids[i], form, t.word, lem, pos, amb))
    stats["read_tokens"] = len(raw)
    return {"occs": occs, "unknown": unknown, "span_keys": span_keys, "span_text": span_text,
            "stats": stats}


async def _senses(llm: Llm, units: dict[str, list[W.Occ]], contexts: dict[int, str], stats) -> dict[str, list[dict]]:
    senses: dict[str, list[dict]] = {}
    sem = asyncio.Semaphore(PARALLEL)

    async def ask(call):
        body, ids = W.sense_prompt(call, contexts, senses)
        schema = W.sense_schema(len(call), len(ids))
        async with sem:
            out, _ = await llm.chat(DIRECTOR, [{"role": "user", "content": body}], prompt=SENSES, schema=schema,
                                    pages=sorted({o.page for _, part in call for o in part}),
                                    max_tokens=600 + 16 * len(ids), temperature=0.0, thinking=False)
        stats["sense_calls"] += 1
        return out, ids

    for rnd in W.rounds(units, SENSE_BATCH):
        results = await asyncio.gather(*(ask(call) for call in rnd))
        missing = []
        for out, ids in results:
            for n in W.merge_senses(out, ids, senses):
                missing.append(ids[n])
        if missing:
            # atlanan geçişler bir kez daha, kendi kökleriyle ve bilinen etiketlerle sorulur
            again = collections.defaultdict(list)
            for lem, o in missing:
                again[lem].append(o)
            stats["sense_retried"] += len(missing)
            for call in [c for r in W.rounds(dict(again), SENSE_BATCH) for c in r]:
                out, ids = await ask(call)
                stats["sense_unassigned"] += len(W.merge_senses(out, ids, senses))
    return senses


async def _alternatives(llm: Llm, lemma: str, sense: dict | None, marked: str, page: int) -> list[str]:
    body = (f"Aşağıdaki pasajda «{lemma}» sözcüğü aynı anlamda kısa aralıkla tekrarlanıyor ([[ ]] içinde). "
            "Tekrarı gidermek için sonraki geçişlerin yerine konabilecek, cümlede aynı anlamı veren sözcük ya "
            "da söyleyişler öner (Türkçe, en fazla 5; iyi karşılık yoksa boş liste).\n\n"
            + (f"Anlam: {sense['label']}\n" if sense else "") + f"Pasaj: «{marked}»")
    out, _ = await llm.chat(DIRECTOR, [{"role": "user", "content": body}], prompt=ALTERNATIVES,
                            schema=_alt_schema(), pages=[page], max_tokens=400, temperature=0.0, thinking=False)
    return [s.strip() for s in out.get("oneriler", []) if s.strip() and W.lower_tr(s.strip()) != lemma]


async def run(generation_id: str):
    lex = T.lexicon()
    rd = await asyncio.to_thread(_read, generation_id, lex)
    occs: list[W.Occ] = rd["occs"]
    stats = rd["stats"]
    span_text = rd["span_text"]
    contexts = {o.idx: W.marked_context(span_text[(o.page, o.span)], o.start, o.end, CONTEXT_CHARS) for o in occs}

    by_lemma = collections.defaultdict(list)
    for o in occs:
        by_lemma[o.lemma].append(o)
    content = {lem: os_ for lem, os_ in by_lemma.items() if any(o.pos in W.CONTENT_POS for o in os_)}
    # anlam: iki kez ya da daha çok geçen her içerik kökü (bir kez geçenin anlamı haritada tektir)
    units = {lem: os_ for lem, os_ in content.items() if len(os_) >= 2}

    llm = Llm(generation_id)
    senses = await _senses(llm, units, contexts, stats)

    # yakın tekrar: aynı kök + aynı anlam
    findings = []
    near_different = []
    cands = []
    for lem, os_ in sorted(units.items()):
        single, dup = W.drop_reduplication(os_)
        stats["skip_reduplication"] += dup
        same_sense_idx = set()
        groups = collections.defaultdict(list)
        for o in single:
            groups[o.sense].append(o)
        for sense_no, grp in groups.items():
            if sense_no is None:
                continue      # anlamı atanamayan geçiş tekrar sayılmaz (haritada «belirsiz»)
            for cl in W.clusters(grp, ECHO_SENTENCES):
                cands.append((lem, sense_no, cl))
                same_sense_idx.update(o.idx for o in cl)
        # aynı kök yakın geçmiş ama anlamlar farklı: tekrar değil (haritada görünür, sayılır)
        for cl in W.clusters(single, ECHO_SENTENCES):
            if not any(o.idx in same_sense_idx for o in cl) and len({o.sense for o in cl}) > 1:
                near_different.append({"lemma": lem, "pages": sorted({o.page for o in cl}),
                                       "senses": [senses[lem][o.sense]["label"] if o.sense is not None else "?"
                                                  for o in cl],
                                       "passage": W.passage(rd["span_keys"], span_text, cl)[1]})
    stats["candidates"] = len(cands)
    stats["near_repeat_different_sense"] = len(near_different)

    sem = asyncio.Semaphore(PARALLEL)

    async def judge(lem, sense_no, cl):
        sense = senses[lem][sense_no]
        plain, marked = W.passage(rd["span_keys"], span_text, cl)
        pages = sorted({o.page for o in cl})
        async with sem:
            p, _ = await J._ab(llm, lambda x, y: W.flaw_prompt(lem, sense, marked, x, y), W.FLAW, W.FINE, pages)
        return lem, sense, cl, plain, marked, pages, p

    judged = await asyncio.gather(*(judge(*c) for c in cands))
    kept = [j for j in judged if j[-1] >= J.KEEP]
    stats["dropped_as_intentional"] = len(judged) - len(kept)

    async def alternatives(lem, sense, cl, marked):
        async with sem:
            return await _alternatives(llm, lem, sense, marked, cl[1].page)

    alts_of = await asyncio.gather(*(alternatives(lem, sense, cl, marked) for lem, sense, cl, _, marked, _, _ in kept))
    for (lem, sense, cl, plain, marked, pages, p), alts in zip(kept, alts_of):
        where = ", ".join(f"s.{o.page} «{o.word}»" for o in cl)
        findings.append({
            "page": cl[1].page, "severity": "WARN", "quote": plain,
            "message": f"«{lem}» aynı anlamda ({sense['label']}) {len(cl)} kez yakın geçiyor: {where}.",
            "suggestion": ", ".join(alts) or None,
            "details": {"lemma": lem, "sense": sense["label"], "idiom": sense["idiom"], "count": len(cl),
                        "pages": pages, "forms": [o.word for o in cl], "p_flaw": round(p, 3),
                        "passage_marked": marked, "window_sentences": ECHO_SENTENCES}})
        stats["kept"] += 1
    findings.sort(key=lambda f: (f["page"], f["message"]))

    # harita ve çeşitlilik
    seq = [o.lemma for o in occs]
    content_n = sum(len(v) for v in content.values())
    out_stats = {**dict(stats),
                 "word_tokens": len(occs),
                 "content_tokens": content_n,
                 "distinct_lemmas": len(by_lemma),
                 "distinct_content_lemmas": len(content),
                 "hapax_content_lemmas": sum(1 for v in content.values() if len(v) == 1),
                 "polysemous_lemmas": sum(1 for lem in units if len(senses.get(lem, [])) > 1),
                 "idiom_senses": sum(1 for lem in units for s in senses.get(lem, []) if s["idiom"]),
                 "mtld_lemma": W.mtld(seq),
                 "mtld_form": W.mtld([o.form for o in occs]),
                 "near_repeat_different_sense_examples": near_different,
                 "unknown_forms": [{"form": f, "count": len(ps), "pages": sorted(set(ps))}
                                   for f, ps in sorted(rd["unknown"].items(), key=lambda kv: -len(kv[1]))],
                 "map": W.build_map(occs, senses, contexts)}
    return findings, out_stats
