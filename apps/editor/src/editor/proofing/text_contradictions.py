"""Metin içi çelişki: two statements of the book's OWN TEXT that cannot both be true in the
story (a stated age, a relation, a name, a count, an attribute, the time of day or the order
of events, where someone is, what state an object is in), with nothing in the text that
explains the change.

Why this is not the ledger step (knowledge.detect_contradictions): that step shows the model
only the extracted character cards and event summaries, never the text, and then requires two
verbatim quotes from the text. Measured on every stored call (docs/son-okuma/text_contradictions.md):
prompt v1 produced 19 candidates on one book, all 19 about the vision scans' wording (0 about
the text; 1 stored, false); prompt v2 produced 0 candidates on all six books, because thinking
used the whole 12k budget every time and the no-thinking retry answered an empty list.

Here the model reads the text itself and nothing is believed on its word:
  1. PROPOSE (two independent readers, union, like vision.confirm_text_visual):
     a. per part of the book, a reading of the WHOLE book that is asked only about the
        sentences of that part: which of them conflict with anything elsewhere;
     b. a fact reading per part of the book (only facts that should not change: age, kinship,
        name, count, stated attribute); facts with the same subject and kind but different
        values are paired DETERMINISTICALLY.
  2. VERIFY: both statements must be found on their pages (verbatim after normalisation, or
     snapped to the page's own words); two different places of the text, or no candidate.
  3. JUDGE: each pair is put to the model again as a closed question, in both orders
     (A-then-B and B-then-A), with the whole book as context so an explanation anywhere in
     the text counts. Answer is one token; its probability is read from logprobs
     (Llm.choose). A pair becomes a finding only when both orders say "contradiction" with
     probability >= JUDGE_MIN (chosen by measurement, see the doc).

Measured precision/recall: docs/son-okuma/text_contradictions.md."""

from __future__ import annotations

import asyncio
from itertools import combinations

from .. import ledger, source
from ..llm import Llm

NAME = "text_contradictions"
VERSION = "1"
LABEL = "Metin içi çelişki"

DIRECTOR = "book-director"
# Probability the judge must give "contradiction" in BOTH orders. Chosen on the six books'
# labelled pairs and the injected known cases (doc, section "Eşik"): at 0.5 the confirmed set
# kept every injected case the judge saw and dropped the pairs labelled false.
JUDGE_MIN = 0.5
# One fact reading covers this many words of story text: a part must fit the fact list's
# schema bound (120 items) with room; the densest measured part (1 500 words) gave 41 facts.
PART_WORDS = 1500
# The direct "find the contradictions" reader (propose_window) answered an empty list on all
# six books AND on all 16 injected contradictions (doc, "Ölçüm 2"): it is kept for a stronger
# model and switched off, it only cost GPU time.
WINDOW_READER = False
PARALLEL = 4          # judge calls in flight: small next to a running GPU analysis

KINDS = ["ZAMAN", "KARAKTER", "YER", "NESNE", "SAYI"]
FACT_KINDS = ["YAS", "AKRABALIK", "AD", "SAYI", "OZELLIK"]
KIND_TR = {"ZAMAN": "zaman/sıra", "KARAKTER": "karakter bilgisi", "YER": "yer", "NESNE": "nesnenin durumu",
           "SAYI": "sayı"}
FACT_TO_KIND = {"YAS": "KARAKTER", "AKRABALIK": "KARAKTER", "AD": "KARAKTER", "SAYI": "SAYI",
                "OZELLIK": "KARAKTER"}

STR = {"type": "string", "maxLength": 600}
INT = {"type": "integer"}


def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def _arr(items: dict, n: int = 120) -> dict:
    return {"type": "array", "items": items, "maxItems": n}   # project rule: every list bounded


REF = _obj({"page": INT, "paragraph": INT, "quote": STR})
PROPOSE_SCHEMA = _obj({"candidates": _arr(_obj({
    "kind": {"type": "string", "enum": KINDS}, "a": REF, "b": REF, "why": STR}), 60)})
FACT_SCHEMA = _obj({"facts": _arr(_obj({
    "subject": STR, "kind": {"type": "string", "enum": FACT_KINDS}, "aspect": STR, "value": STR,
    "page": INT, "paragraph": INT, "quote": STR}))})

INTRO = ("Aşağıda resimli bir çocuk kitabının METNİ var. Her paragraf [sSAYFA pPARAGRAF] ile başlar. "
         "Künye, yazar/çizer tanıtımı ve arka kapak yazıları da metnin içinde olabilir; bunlar hikâye değildir.\n\n")

PROPOSE = (
    "Görevin bir son okuma editörü gibi hikâye METNİNİN kendi içindeki çelişkileri bulmak: metnin iki yerinde "
    "söylenen ve hikâyede İKİSİ BİRDEN DOĞRU OLAMAYACAK iki ifade.\n"
    "Şimdi YALNIZ s{lo}–s{hi} sayfalarını cümle cümle oku. Her cümledeki bilgiyi (kim, kimin nesi, kaç yaşında, "
    "kaç tane, ne zaman, nerede, neyin durumu, hangi özellik) kitabın GERİ KALANINDA (önceki ve sonraki "
    "sayfalarda) aynı konu hakkında söylenenlerle karşılaştır.\n"
    "Türler: ZAMAN (gündüz/gece, önce/sonra, gün sırası, süre; olmuş bir olay sonra hiç olmamış gibi anlatılıyor), "
    "KARAKTER (yaş, akrabalık, ad, meslek, metinde söylenen bir özellik iki yerde farklı), YER (biri bir yerde "
    "iken aynı anda başka yerde), NESNE (kırılmış/kaybolmuş bir şey açıklamasız sağlam/yerinde), SAYI (kaç kişi, "
    "kaç tane iki yerde farklı).\n"
    "Çelişki DEĞİLDİR: zamanla değişen durum (sonraki gün, büyüme, taşınma), metnin açıkladığı değişim, rüya, "
    "hayal, oyun, şaka, yalan, bir karakterin yanlış bilgisi, mecaz ve abartı, farklı kişiler/nesneler, "
    "çizimlerle ilgili her şey.\n"
    "Her aday için iki ifadeyi `a` ve `b` içinde sayfa, paragraf ve METİNDEN KELİMESİ KELİMESİNE alıntıyla ver; "
    "ifadelerden biri s{lo}–s{hi} içinde olmalı. "
    "Emin olmadığın adayı da yaz (ayrıca denetlenecek) ama uydurma alıntı yazma. Çelişki yoksa boş liste döndür.")

FACTS = (
    "Aşağıdaki sayfalardan hikâye boyunca DEĞİŞMEMESİ gereken bilgileri çıkar; yalnız metnin açıkça söylediklerini:\n"
    "YAS (bir karakterin yaşı), AKRABALIK (kimin nesi olduğu: annesi, dedesi, kardeşi...), AD (bir karakterin adı "
    "veya lakabı), SAYI (bir grubun kaç kişi/tane olduğu: üç kardeş, beş yavru), OZELLIK (metnin söylediği kalıcı "
    "bir özellik: gözlüklü, kör, tek kanatlı, kırmızı kürklü).\n"
    "`subject` bilginin kime/neye ait olduğu (metindeki adıyla); `aspect` hangi özelliği olduğu, kısa ve genel "
    "bir adla (yaş, annesi, babası, dedesi, kardeş sayısı, adı, kürk rengi, göz rengi...): iki yerde aynı özellik "
    "söyleniyorsa `aspect` AYNI yazılmalı; `value` o özelliğin değeri; `quote` metinden kelimesi kelimesine. Rüya, hayal, varsayım içindeki bilgileri alma. Tahmin yapma.\n\n")

JUDGE = (
    "Soru: Aşağıdaki iki ifade bu hikâyede İKİSİ BİRDEN doğru olabilir mi?\n"
    "Önce kitabın tamamına bak: iki ifade aynı kişi/nesne/zaman hakkında mı; aradaki metin değişimi açıklıyor mu "
    "(zaman geçti, taşındılar, tamir edildi, yanlış anlaşılmıştı); ifadelerden biri rüya, hayal, oyun, şaka, "
    "yalan, mecaz, bir karakterin yanlış sözü mü? Bunlardan biri varsa çelişki yoktur.\n\n"
    "İfade 1 (s{p1}): “{q1}”\nİfade 2 (s{p2}): “{q2}”\n\n"
    "Cevap tek harf: C = gerçek çelişki (ikisi birden doğru olamaz, metin açıklamıyor); "
    "U = çelişki yok (bağdaşıyor ya da metin açıklıyor); B = karar verilemiyor.")


# ------------------------------------------------------------------ reading
def paragraphs(pages: list[dict]) -> list[dict]:
    return [{"page": p["page_no"], "idx": s["idx"], "text": s["text"]} for p in pages for s in p["spans"]]


def book_text(paras: list[dict]) -> str:
    return "\n".join(f"[s{x['page']} p{x['idx']}] {x['text']}" for x in paras)


def parts(paras: list[dict]) -> list[list[dict]]:
    """Consecutive whole pages up to PART_WORDS words (a page is never split)."""
    by_page: dict[int, list[dict]] = {}
    for x in paras:
        by_page.setdefault(x["page"], []).append(x)
    out, cur, n = [], [], 0
    for _, ps in sorted(by_page.items()):
        w = sum(len(x["text"].split()) for x in ps)
        if cur and n + w > PART_WORDS:
            out.append(cur)
            cur, n = [], 0
        cur += ps
        n += w
    if cur:
        out.append(cur)
    return out


def locate(pages_by_no: dict[int, dict], page: int, paragraph: int | None, quote: str) -> dict | None:
    """The statement as it is printed: the span of the page that holds the quote (the given
    paragraph first), else the page's own words the quote is a near copy of. None = not on the page."""
    p = pages_by_no.get(page)
    q = (quote or "").strip().strip("“”\"'")
    if not p or not q:
        return None
    k = source.key(q)
    spans = sorted(p["spans"], key=lambda s: s["idx"] != paragraph)
    for s in spans:
        if k and k in source.key(s["text"]):
            return {"page": page, "idx": s["idx"], "quote": q}
    raw = "\n".join(s["text"] for s in p["spans"])
    snapped = ledger.snap_quote(q, raw)
    if snapped:
        for s in spans:
            if source.key(snapped) in source.key(s["text"]):
                return {"page": page, "idx": s["idx"], "quote": snapped}
        return {"page": page, "idx": None, "quote": snapped}
    return None


# ------------------------------------------------------------------ proposers
async def propose_window(llm: Llm, text: str, part: list[dict]) -> list[dict]:
    """The whole book is the context (the same prefix for every part, so the server's prefix
    cache reads it once); the question is about one part: does any sentence HERE conflict with
    anything anywhere in the book. Asking about the whole book at once was measured to answer
    an empty list on all six books, injected contradictions included."""
    lo, hi = part[0]["page"], part[-1]["page"]
    ask = PROPOSE.replace("{lo}", str(lo)).replace("{hi}", str(hi))
    out, _ = await llm.chat(DIRECTOR, [{"role": "user", "content": INTRO + text + "\n\n" + ask}],
                            schema=PROPOSE_SCHEMA, max_tokens=8000, temperature=0.0, thinking=False)
    return [{"kind": c["kind"], "a": c["a"], "b": c["b"], "why": c["why"], "by": "window"}
            for c in out["candidates"]]


async def facts_of(llm: Llm, part: list[dict]) -> list[dict]:
    out, _ = await llm.chat(DIRECTOR, [{"role": "user", "content": FACTS + INTRO + book_text(part)}],
                            schema=FACT_SCHEMA, max_tokens=8000, temperature=0.0, thinking=False)
    return out["facts"]


def _value_key(v: str) -> str:
    return ledger.norm(v)


def pair_facts(facts: list[dict]) -> list[dict]:
    """Same subject + same kind + different value = a candidate pair (deterministic). The
    first statement of each distinct value represents it."""
    groups: dict[tuple, dict[str, dict]] = {}
    for f in facts:
        subj, aspect, val = ledger.norm(f["subject"]), ledger.norm(f["aspect"]), _value_key(f["value"])
        if not subj or not aspect or not val:
            continue
        # aspect is NOT part of the key: the reader names one aspect differently on two pages
        # («kardeş sayısı» / «kaç kardeş»), measured to hide injected count conflicts
        groups.setdefault((subj, f["kind"]), {}).setdefault(val, f)
    out = []
    for (subj, kind), vals in groups.items():
        for x, y in combinations(sorted(vals.values(), key=lambda f: (f["page"], f["paragraph"])), 2):
            out.append({"kind": FACT_TO_KIND[kind], "why": f"{x['subject']} — {x['aspect']}: “{x['value']}” / “{y['value']}”",
                        "a": {"page": x["page"], "paragraph": x["paragraph"], "quote": x["quote"]},
                        "b": {"page": y["page"], "paragraph": y["paragraph"], "quote": y["quote"]}, "by": "facts"})
    return out


# ------------------------------------------------------------------ judge
async def judge(llm: Llm, text: str, a: dict, b: dict, sem: asyncio.Semaphore) -> dict:
    async def ask(x, y):
        body = INTRO + text + "\n\n" + JUDGE.format(p1=x["page"], q1=x["quote"], p2=y["page"], q2=y["quote"])
        async with sem:
            probs, _ = await llm.choose(DIRECTOR, [{"role": "user", "content": body}], ["C", "U", "B"])
        return probs
    fwd, rev = await asyncio.gather(ask(a, b), ask(b, a))
    return {"forward": fwd, "reverse": rev, "p_contradiction": min(fwd["C"], rev["C"])}


# ------------------------------------------------------------------ check
async def check(pages: list[dict], llm: Llm | None = None) -> tuple[list[dict], dict]:
    llm = llm or Llm(None)
    paras = paragraphs(pages)
    if not paras:
        return [], {"paragraphs": 0}
    text = book_text(paras)
    by_no = {p["page_no"]: p for p in pages}
    ps = parts(paras)
    windows = WINDOW_READER
    got = await asyncio.gather(*(propose_window(llm, text, part) for part in (ps if windows else [])),
                               *(facts_of(llm, part) for part in ps), return_exceptions=True)
    failed = [g for g in got if isinstance(g, BaseException)]
    if len(failed) == len(got):
        raise RuntimeError(f"no reader answered: {failed[0]}")
    nw = len(ps) if windows else 0
    whole = [c for g in got[:nw] if not isinstance(g, BaseException) for c in g]
    facts = [f for g in got[nw:] if not isinstance(g, BaseException) for f in g]
    raw = whole + pair_facts(facts)

    # verify both statements on their pages; merge the same pair proposed twice
    cands: dict[tuple, dict] = {}
    unverified = 0
    for c in raw:
        a = locate(by_no, c["a"]["page"], c["a"]["paragraph"], c["a"]["quote"])
        b = locate(by_no, c["b"]["page"], c["b"]["paragraph"], c["b"]["quote"])
        if not a or not b:
            unverified += 1
            continue
        if (a["page"], a["idx"]) == (b["page"], b["idx"]) or source.key(a["quote"]) == source.key(b["quote"]):
            unverified += 1          # one statement cannot contradict itself
            continue
        a, b = sorted((a, b), key=lambda s: (s["page"], s["idx"] or 0))
        key = (a["page"], a["idx"], b["page"], b["idx"])
        if key in cands:
            cands[key]["by"] = sorted(set(cands[key]["by"]) | {c["by"]})
        else:
            cands[key] = {**c, "a": a, "b": b, "by": [c["by"]]}

    sem = asyncio.Semaphore(PARALLEL)
    verdicts = await asyncio.gather(*(judge(llm, text, c["a"], c["b"], sem) for c in cands.values()),
                                    return_exceptions=True)
    findings = []
    judged_failed = 0
    for c, v in zip(cands.values(), verdicts):
        if isinstance(v, BaseException):
            judged_failed += 1
            continue
        c["judge"] = v
        if v["p_contradiction"] < JUDGE_MIN:
            continue
        a, b = c["a"], c["b"]
        findings.append({
            "page": b["page"], "severity": "WARN", "quote": b["quote"],
            "message": (f"Metin içi çelişki ({KIND_TR[c['kind']]}): s.{a['page']} “{a['quote']}” ile "
                        f"s.{b['page']} “{b['quote']}” birlikte doğru olamaz. {c['why']}").strip(),
            "suggestion": "İki yeri karşılaştırıp birini düzeltin ya da değişimi açıklayan bir cümle ekleyin.",
            "details": {"kind": c["kind"], "a": a, "b": b, "why": c["why"], "proposed_by": c["by"],
                        "judge": {k: v[k] for k in ("forward", "reverse")},
                        "p_contradiction": round(v["p_contradiction"], 3)}})
    stats = {"paragraphs": len(paras), "parts": len(ps), "proposed_window": len(whole), "facts": len(facts),
             "proposed_facts": len(raw) - len(whole), "unverified_quotes": unverified,
             "candidates": len(cands), "judge_failed": judged_failed, "readers_failed": len(failed),
             "confirmed": len(findings),
             "candidates_detail": [{"kind": c["kind"], "a": c["a"], "b": c["b"], "why": c["why"], "by": c["by"],
                                    "p": round(c["judge"]["p_contradiction"], 3) if "judge" in c else None}
                                   for c in cands.values()]}
    return findings, stats


async def run(generation_id: str):
    pages = await asyncio.to_thread(source.read, generation_id)
    return await check(pages, Llm(generation_id))   # calls recorded against the generation
