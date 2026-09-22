"""Deterministic candidate rules for the `spelling` check. Every rule returns candidates:
dicts with page, span, start, end, quote, kind, suggestion, needs_model (bool) and details.
Exact TDK rules (particle harmony, apostrophe consonant assimilation, spacing) do not need a
model; word-level guesses (a form the dictionaries do not know, a doubled syllable) do.

The thresholds and exclusions are explained next to each rule, with the measurement that
chose them in docs/son-okuma/spelling.md.
"""

from __future__ import annotations

import collections
import re

from ._spelling_text import APOS, HYPH, Lexicon, Tok, edit_distance, lower_tr

BACK, FRONT = set("aıou"), set("eiöü")
VOWELS = BACK | FRONT | set("âîû")
VOICELESS = set("çfhkpsşt")
TR_LETTERS = set("abcçdefgğhıijklmnoöprsştuüvyzâîû")
# not a spelling question: letters outside the Turkish alphabet mean a foreign word or a
# mixed-script extraction artefact ("taraфından")
FOREIGN = re.compile(r"[^abcçdefgğhıijklmnoöprsştuüvyzâîûABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZÂÎÛ'’`\-­‐‑]")
LAUGH = re.compile(r"(?:h[aeıiou]){2,}|(?:[aeıiou]h){2,}", re.I)
RUN3 = re.compile(r"(.)\1\1", re.I)
Q_PARTICLE = re.compile(r"^(m[iıuü])(y?(?:sın|sin|sun|sün|ım|im|um|üm|yım|yim|yum|yüm|sınız|siniz|sunuz|sünüz|"
                        r"ız|iz|uz|üz|yız|yiz|yuz|yüz|ydı|ydi|ydu|ydü|ymış|ymiş|ymuş|ymüş|ydım|ydim|ydum|ydüm)?)$")
PARTICLES = ("mi", "mı", "mu", "mü", "de", "da", "ki")


def last_vowel(w: str) -> str | None:
    for ch in reversed(lower_tr(w)):
        if ch in VOWELS:
            return {"â": "a", "î": "i", "û": "u"}.get(ch, ch)
    return None


def first_vowel(w: str) -> str | None:
    for ch in lower_tr(w):
        if ch in VOWELS:
            return ch
    return None


def harmony_ok(stem_last: str, suffix_vowel: str) -> bool:
    if suffix_vowel in "ae":
        return (suffix_vowel == "a") == (stem_last in BACK)
    four = {"a": "ı", "ı": "ı", "o": "u", "u": "u", "e": "i", "i": "i", "ö": "ü", "ü": "ü"}
    return four.get(stem_last) == suffix_vowel


def expected_vowel(stem_last: str, suffix_vowel: str) -> str:
    if suffix_vowel in "ae":
        return "a" if stem_last in BACK else "e"
    return {"a": "ı", "ı": "ı", "o": "u", "u": "u", "e": "i", "i": "i", "ö": "ü", "ü": "ü"}[stem_last]


def cand(t: Tok, kind: str, suggestion: str | None, needs_model: bool, **details) -> dict:
    return {"page": t.page, "span": t.span, "start": t.start, "end": t.end, "src": t.src,
            "quote": t.printed, "kind": kind, "suggestion": suggestion, "needs_model": needs_model,
            "details": details}


def expressive(w: str) -> str | None:
    """Intentional children's-book forms: stretched sounds (3+ same letters: "Çoook" is two
    o's only in "Yook" - see the model step), laughter ("Ahahaha", "burAHAHAHAya"), stylised
    case inside a word ("TiRtIlDaN")."""
    if RUN3.search(w):
        return "uzatma"
    if LAUGH.search(w):
        return "gülme/ses"
    if re.search(r"[a-zçğıöşü][A-ZÇĞİÖŞÜ]", w):
        return "stilize yazım"
    return None


def stretched(lex: Lexicon, w: str) -> bool:
    """A doubled vowel ("Yook", "daldıım", "tazelee") or a doubled final letter ("Heyy",
    "canımm") whose single form is a word: a stretched sound. A doubled consonant inside a
    word ("ekrannın") is not a way of speaking and stays a candidate."""
    lw = lower_tr(w)
    for m in re.finditer(r"(.)\1", lw):
        ch, i = m.group(1), m.start()
        if ch in VOWELS or i + 2 == len(lw):
            if lex.valid(lw[:i] + lw[i + 1:]):
                return True
    return False


# --- 1. unknown word forms ---------------------------------------------------------------

def _suggestions(lex: Lexicon, w: str) -> list[tuple[str, str]]:
    """(suggestion, how). Particle split first: "geliyormu" -> "geliyor mu", "diyorki"."""
    out = []
    lw = lower_tr(w)
    from ._spelling_text import segment
    seg = segment(lex, lw, 3)
    glue = []
    if len(seg) == 2:
        k = len(seg[0])
        glue = [(w[:k] + " " + w[k:], "bitişik yazılmış iki sözcük")]
    for p in PARTICLES:
        for k in range(2, len(lw) - 1):
            head, tail = lw[:k], lw[k:]
            m = Q_PARTICLE.match(tail) if p.startswith("m") else (tail == p and tail)
            if (p.startswith("m") and m and tail.startswith(p)) or (not p.startswith("m") and tail == p):
                if lex.valid(head) and len(head) >= 2 and (w[:k] + " " + w[k:]) not in {x for x, _ in out}:
                    out.append((w[:k] + " " + w[k:], "ayrı yazılan ek/bağlaç bitişik"))
    seen = {s for s, _ in out}
    ranked = []
    for s in lex.suggest(w):
        if s in seen or lower_tr(s) == lw or " " in s:
            continue
        d = edit_distance(lower_tr(s), lw)
        if d <= 2:
            ranked.append((d, s))
            seen.add(s)
    ranked.sort(key=lambda x: x[0])
    # an attached particle first, then one-letter corrections, then two glued words, then the rest
    one = [(s, "sözlük önerisi (uzaklık 1)") for d, s in ranked if d == 1]
    two = [(s, f"sözlük önerisi (uzaklık {d})") for d, s in ranked if d > 1]
    q = [x for x in out if x[0].split(" ")[-1][:2] in ("mi", "mı", "mu", "mü")]
    other = [x for x in out if x not in q]
    return (q + one + other + [g for g in glue if g[0] not in seen] + two)[:5]


def _caps_ocr_ambiguous(lex: Lexicon, w: str) -> bool:
    idx = [i for i, ch in enumerate(w) if ch in "Iİ"]
    if not idx or len(idx) > 6:
        return False
    for mask in range(1, 2 ** len(idx)):
        v = list(w)
        for k, i in enumerate(idx):
            if mask >> k & 1:
                v[i] = "İ" if w[i] == "I" else "I"
        if lex.valid("".join(v)):
            return True
    return False


def unknown_words(tokens: list[Tok], lex: Lexicon, vocab_pages: dict[str, set], capital_mid: set[str],
                  stats: collections.Counter) -> list[dict]:
    out = []
    for t in tokens:
        if t.garbled or t.fragment:
            continue
        w = t.base
        if len(w) <= 2:
            stats["skip_short"] += 1
            continue
        if FOREIGN.search(w):
            stats["skip_foreign"] += 1
            continue
        if "-" in w or "‐" in w:
            parts = re.split(r"[-‐‑]", w)
            # spelled-out syllables ("Or-man") or a hyphenated compound whose parts are words
            if lex.valid("".join(parts)) or all(lex.valid(x) or len(x) <= 2 for x in parts):
                continue
        if lex.valid(w):
            continue
        why = expressive(w)
        if why or stretched(lex, w):
            stats["skip_expressive"] += 1
            continue
        is_caps = w.isupper()
        if is_caps and t.src == "OCR" and _caps_ocr_ambiguous(lex, w):
            # the OCR model confuses I/İ in capitals ("KITAP" for "KİTAP"); a form that is a word with
            # the other dot is the reader's slip, not the book's
            stats["skip_ocr_caps"] += 1
            continue
        if w[:1].isupper() and not is_caps:
            # a capitalised form is a name when it is written capitalised inside a sentence
            # somewhere in the book (here or elsewhere): name_spelling looks at names
            if not t.sent_start or lower_tr(w) in capital_mid:
                stats["skip_name"] += 1
                continue
        # the book's own vocabulary: a form printed on two or more pages is a choice (invented
        # words, a character's way of speaking); a slip is rarely repeated identically
        if len(vocab_pages.get(lower_tr(w), ())) >= 2:
            stats["skip_book_vocabulary"] += 1
            continue
        sugg = _suggestions(lex, w)
        out.append(cand(t, "bilinmeyen_kelime", sugg[0][0] if sugg else None, True,
                        word=w, suggestions=[s for s, _ in sugg], how=[h for _, h in sugg]))
    return out


# --- 2. a doubled syllable inside a valid form ("ortalamamamız") ---------------------------

DITTO = re.compile(r"(?=(([bcçdfgğhjklmnprsştvyz][aeıioöuü])\2))")


def _lemmas(lex: Lexicon, w: str) -> set[tuple[str, str]]:
    return {(a.dict_item.lemma, a.dict_item.primary_pos.value) for a in lex.analyses(w)}


def doubled_syllables(tokens: list[Tok], lex: Lexicon, vocab_pages: dict[str, set]) -> list[dict]:
    """"ortalamamamız" for "ortalamamız": a verbal noun in -mA that the lexicon holds as a
    noun of its own (ortalama, dondurma, yazma) with its "ma/me" written twice. The doubled
    form is still grammatical (ortala-ma-ma-mız, "our not averaging"), which is why no
    dictionary catches it. Turkish produces "-mama/-meme" on purpose all the time
    (negation + verbal noun: "çıkmamaya", "söylememek"), so the rule keeps only the case
    where the single form is that lexical noun and the doubled form has no noun reading
    (measured on six books: 44 raw consonant+vowel doublings, all grammatical except this
    pattern). The sentence decides: model."""
    out = []
    for t in tokens:
        if t.garbled or t.fragment or len(t.base) < 6 or not lex.valid(t.base):
            continue
        w = lower_tr(t.base)
        if len(vocab_pages.get(w, ())) >= 2:
            continue
        mine = _lemmas(lex, w)
        if not mine or any(pos in ("Noun", "Adj") for _, pos in mine):
            continue
        verbs = {lower_tr(lem) for lem, pos in mine if pos == "Verb"}
        for m in re.finditer(r"(?=(mama|meme))", w):
            i = m.start()
            fixed = w[:i] + w[i + 2:]
            nouns = {lower_tr(lem) for lem, pos in _lemmas(lex, fixed) if pos == "Noun"}
            if any(n[-2:] in ("ma", "me") and (n[:-2] + "mak" in verbs or n[:-2] + "mek" in verbs)
                   for n in nouns):
                sugg = t.base[:i] + t.base[i + 2:]
                out.append(cand(t, "tekrarlanan_hece", sugg, True, word=t.base, unit=w[i:i + 2]))
                break
    return out


# --- 3. doubled words -----------------------------------------------------------------------

# conjunctions, postpositions and particles are not reduplicated in Turkish ("koş koş",
# "tak tak", "bir bir", "çok çok" are; "ve ve" is not)
FUNCTION_WORDS = {"ve", "ile", "ama", "fakat", "ancak", "çünkü", "için", "gibi", "de", "da", "ki", "mi",
                  "mı", "mu", "mü", "veya", "yahut", "ise", "diye", "kadar", "bu", "şu"}


def doubled_words(spans: list[dict]) -> list[dict]:
    """The same word twice in a row with only a space or a line break between.
    - a doubled function word inside a line: exact slip, no model;
    - a word at the end of one printed line repeated at the start of the next (same case):
      the classic typesetting slip, but Turkish reduplicates content words on purpose
      ("zangır / zangır", "püfür / püfür"), so the sentence decides: model.
    OCR supplements are left out: their order on the page is unresolved (source.py)."""
    out = []
    flat = [(s, t) for s in spans if not s["garbled"] and not s["supplement"] for t in s["toks"]]
    for (s1, a), (s2, b) in zip(flat, flat[1:]):
        if a.fragment or b.fragment or a.word != b.word and lower_tr(a.word) != lower_tr(b.word):
            continue
        w = lower_tr(a.word)
        if s1 is s2:
            gap = s1["text"][a.end:b.start]
            if gap.strip():
                continue  # "Koş, koş" / "Ne? Ne?"
            if w in FUNCTION_WORDS:
                out.append({**cand(a, "tekrarlanan_kelime", a.word, False, word=a.word, across_line=False),
                            "quote": a.printed + " " + b.printed, "end": b.end})
        elif s1["page"] == s2["page"] and a.word == b.word and not SENT_END_RX.search(s1["text"]):
            out.append({**cand(a, "tekrarlanan_kelime", a.word, w not in FUNCTION_WORDS, word=a.word,
                               across_line=True), "quote": a.printed + " / " + b.printed})
    return out


SENT_END_RX = re.compile(r"[.!?…:;,\"”’»)]\s*$")


# --- 4. question particle and "da" harmony -------------------------------------------------------

def particle_harmony(spans: list[dict], lex: Lexicon) -> list[dict]:
    """The separately written question particle and the conjunction "de/da" follow the vowel
    harmony of the word before (TDK): "geliyor mu", "sen de". The last-vowel rule has
    lexical exceptions (saat, hal, kalp: front suffixes after a back vowel); the dictionary
    decides those by the word's own locative ("saatte" is a word, "saatta" is not).
    "de" after a back vowel is NOT checked: "de" is also the imperative of "demek"
    ("Gak de, guk de" = say gak) - measured, all four such hits in six books were that."""
    out = []
    for s in spans:
        if s["garbled"]:
            continue
        toks = s["toks"]
        for a, b in zip(toks, toks[1:]):
            gap = s["text"][a.end:b.start]
            if gap != " " or a.fragment or b.word.isupper():
                continue
            bw = lower_tr(b.word)
            is_q = bool(Q_PARTICLE.match(bw))
            if not is_q and bw != "da":
                continue
            prev = lower_tr(a.word)
            if FOREIGN.search(prev) or not lex.valid(a.base) or (len(prev) < 3 and prev not in ("o", "bu", "şu")):
                continue
            lv = last_vowel(prev)
            if not lv:
                continue
            pv = bw[1]
            front = lv in FRONT
            loc_f = prev + ("te" if prev[-1] in VOICELESS else "de")
            loc_b = prev + ("ta" if prev[-1] in VOICELESS else "da")
            if lex.valid(loc_f) != lex.valid(loc_b):
                front = lex.valid(loc_f)  # the word's own class ("saatte": front)
            rounded = lv in "oöuü"
            if pv in "ae":
                want = "e" if front else "a"
            else:
                want = ("ü" if front else "u") if rounded else ("i" if front else "ı")
            if want == pv:
                continue
            fixed = b.word[0] + want + b.word[2:]
            out.append({**cand(b, "ek_uyumu", fixed, False, word=b.word, previous=a.word,
                               rule="soru eki" if is_q else "bağlaç da/de"),
                        "quote": a.printed + " " + b.printed, "start": a.start})
    return out


# --- 5. apostrophe with proper nouns -----------------------------------------------------------

SUFFIX_START = re.compile(r"^(?:n?[ıiuü]n|y?[ıiuü]|y?[ae]|[dt][ae]n?|[dt][ae]ki|l[ae]r|n?[ıiuü]m|y?l[ae]|"
                          r"c[ıiuü]k|ç[ıiuü]k|s[ıiuü]|[dt][ıiuü]|[ıiuü]n)")


def apostrophes(tokens: list[Tok], lex: Lexicon, names: dict[str, int]) -> list[dict]:
    """TDK: suffixes on proper nouns are separated with an apostrophe; common nouns take
    none. Exact rules:
    a) a name of the book (written with an apostrophe elsewhere in the book) carrying a
       suffix with no apostrophe ("Mertin", "Ayşeye");
    b) an apostrophe after a common word ("kitap'ı"); not after abbreviations or letters
       ("cm'den", "‘b’yi"), nor an elision mark ("bi’şey": the base is not a word of 3+);
    c) the suffix after the apostrophe breaks consonant assimilation ("Mert'de"), the buffer
       letter ("Defne'e") or vowel harmony ("Mert'ın"). A name follows its pronunciation
       ("Holmes’u" is right), so vowel harmony is reported only for a name the book itself
       inflects the regular way elsewhere."""
    out = []
    by_name = collections.defaultdict(list)
    for t in tokens:
        if t.garbled or t.fragment:
            continue
        w = t.word
        if not t.apos:
            if w[:1].isupper() and not w.isupper() and not t.sent_start and not lex.common(w) \
                    and lower_tr(w) not in names:
                lw = lower_tr(w)
                for n in sorted(names, key=len, reverse=True):
                    if len(n) >= 3 and lw.startswith(n) and len(lw) > len(n) and SUFFIX_START.match(lw[len(n):]):
                        out.append(cand(t, "kesme_eksik", w[:len(n)] + "’" + w[len(n):], False,
                                        word=w, name=w[:len(n)], suffix=w[len(n):]))
                        break
            continue
        base, suf = t.base, t.suffix
        if base[:1].islower() and len(base) >= 3 and first_vowel(base) and lex.common(base) \
                and not lex.proper(base) and lower_tr(base) not in names:
            out.append(cand(t, "gereksiz_kesme", base + suf, False, word=w))
            continue
        if base[:1].isupper() and not base.isupper() and not FOREIGN.search(base):
            by_name[lower_tr(base)].append(t)
    for name, ts in by_name.items():
        checked = [(t, _suffix_problem(t.base, t.suffix)) for t in ts]
        good = sum(1 for _, why in checked if not why)
        for t, why in checked:
            if not why:
                continue
            kind, fixed = why
            if kind == "uyum" and not good:
                continue  # a name's harmony follows its pronunciation ("Holmes’u"); only the
                # book's own regular inflection of the same name shows the reading
            out.append(cand(t, "ek_uyumu", t.base + t.apos + fixed, False, word=t.word, rule=kind))
    return out


def _suffix_problem(base: str, suf: str) -> tuple[str, str] | None:
    b, s = lower_tr(base), lower_tr(suf)
    if not s or not b or len(b) < 2:
        return None
    lv = last_vowel(b)
    end = b[-1]
    if s[0] in "dc" and end in VOICELESS:
        return "ünsüz benzeşmesi", ("t" if s[0] == "d" else "ç") + suf[1:]
    if s[0] in "tç" and end not in VOICELESS and re.match(r"^[tç][ae]n?$|^[tç][ae]ki$", s):
        return "ünsüz benzeşmesi", ("d" if s[0] == "t" else "c") + suf[1:]
    if end in VOWELS and re.match(r"^[ıiuü]n$|^[ıiuü]$|^[ae]$", s):
        return "kaynaştırma harfi", ("n" + suf if s.endswith("n") else "y" + suf)
    fv = first_vowel(s)
    if lv and fv and fv in "aeıiuü" and not harmony_ok(lv, fv):
        i = s.index(fv)
        return "uyum", suf[:i] + expected_vowel(lv, fv) + suf[i + 1:]
    return None


# --- 6. punctuation spacing ----------------------------------------------------------------------

PUNCT_RULES = [
    # (kind, regex on the span text, message); the "glyph" group is the mark whose printed
    # neighbourhood is measured (see _spelling_geometry)
    ("noktalama_öncesi_boşluk", re.compile(r"(?<=[^\W\d_])[ \t]+(?P<g>[,;:!?]|\.(?!\.)|…)(?=\s|$|[”\"’»])"),
     "Noktalama işaretinden önce boşluk olmaz.", "before"),
    ("noktalama_sonrası_boşluk_yok", re.compile(r"(?<=[^\W\d_])(?P<g>[,;:])(?=[^\W\d_])"),
     "Virgül, noktalı virgül ve iki noktadan sonra boşluk bırakılır.", "after"),
    ("cümle_sonu_bitişik", re.compile(r"(?<=[a-zçğıöşü]{2})(?P<g>[.!?])(?=[A-ZÇĞİÖŞÜ][a-zçğıöşü])"),
     "Cümle sonu işaretinden sonra boşluk bırakılır.", "after"),
    ("tırnak_içi_boşluk", re.compile(r"(?P<g>[“«])[ \t]+(?=\S)"), "Açılan tırnaktan sonra boşluk konmaz.", "after_open"),
    ("tırnak_içi_boşluk", re.compile(r"(?<=\S)[ \t]+(?P<g>[”»])"), "Kapanan tırnaktan önce boşluk konmaz.", "before"),
    ("çift_nokta", re.compile(r"(?<=[^\W\d_])(?P<g>\.\.)(?![.\w])"),
     "İki nokta yan yana: nokta ya da üç nokta olmalı.", None),
    ("çift_virgül", re.compile(r"(?P<g>,,|;;|::)"), "Aynı işaret iki kez yazılmış.", None),
    # exactly four dots (five or more are table-of-contents leaders)
    ("dört_nokta", re.compile(r"(?<![.…])(?P<g>\.{4}|…\.|\.…)(?![.…])"), "Üç nokta dört nokta olarak yazılmış.", None),
]


def punctuation(spans: list[dict]) -> list[dict]:
    """Spacing and doubled marks, on the publisher's text layer only (an OCR reading
    normalises spacing and cannot show it). Spacing candidates carry `geometry` so the
    check can measure the printed gap: the layer holds space characters the typesetter
    kerned away and loses spaces at line ends (measured: docs, "Boşluk ölçümü")."""
    out = []
    for s in spans:
        if s["garbled"] or s["src"] != "TEXT_LAYER":
            continue
        text = s["text"]
        for name, rx, msg, geo in PUNCT_RULES:
            for m in rx.finditer(text):
                a, b = max(0, m.start() - 14), min(len(text), m.end() + 14)
                out.append({"page": s["page"], "span": s["idx"], "start": m.start(), "end": m.end(),
                            "src": s["src"], "quote": text[a:b].replace("\n", " "), "kind": name,
                            "suggestion": None, "needs_model": False,
                            "details": {"rule": msg},
                            "geometry": geo and {"mode": geo, "left": text[max(0, m.start("g") - 12):m.start("g")],
                                                 "mark": m.group("g"), "right": text[m.end("g"):m.end("g") + 12]}})
    return out


# --- 7. capital letter after a full stop --------------------------------------------------------

ABBR = re.compile(r"(?:\b(?:[A-ZÇĞİÖŞÜ]|Dr|Prof|Doç|Av|Sn|St|vb|vs|bkz|örn|yy|No|sf|s|Mr|Mrs|Ms)|\d)$")


def capitals(spans: list[dict]) -> list[dict]:
    """A sentence begins with a capital letter: ". küçük" inside one span. Abbreviations,
    numbers ("6. hükümdar") and ellipsis ("..." may continue the sentence) are excluded.
    An OCR reading is checked against the page image by the model step."""
    out = []
    for s in spans:
        if s["garbled"]:
            continue
        text = s["text"]
        for m in re.finditer(r"(?<![.…])\.[ \t]+([a-zçğıöşü][^\W\d_]*)", text):
            before = text[:m.start()]
            if ABBR.search(before):
                continue
            a = max(0, m.start() - 24)
            w = m.group(1)
            out.append({"page": s["page"], "span": s["idx"], "start": m.start(), "end": m.end(),
                        "src": s["src"], "quote": text[a:m.end()], "kind": "büyük_harf",
                        "suggestion": w[0].translate(str.maketrans("iı", "İI")).upper() + w[1:],
                        "needs_model": s["src"] == "OCR", "details": {"word": w}})
    return out


# --- 8. house style: one convention per book ------------------------------------------------------

STYLE = {
    "kesme_işareti": [("’", re.compile(r"(?<=[^\W\d_])’(?=[^\W\d_])")), ("'", re.compile(r"(?<=[^\W\d_])'(?=[^\W\d_])"))],
    "üç_nokta": [("…", re.compile(r"…")), ("...", re.compile(r"(?<!\.)\.\.\.(?!\.)"))],
    "tırnak": [("“ ”", re.compile(r"[“”]")), ('" "', re.compile(r'"'))],
    "konuşma_çizgisi": [("–", re.compile(r"^\s*–\s", re.M)), ("—", re.compile(r"^\s*—\s", re.M)),
                        ("-", re.compile(r"^\s*-\s(?=\S)", re.M))],
}
# A book has a house style when one form carries at least this share of all uses; the
# minority form is then reported page by page (measured: docs, "Tutarlılık").
HOUSE_SHARE = 0.8


def house_style(spans: list[dict]) -> list[dict]:
    out = []
    for kind, forms in STYLE.items():
        per = {f: collections.defaultdict(list) for f, _ in forms}
        for s in spans:
            if s["garbled"] or s["src"] != "TEXT_LAYER":
                continue  # OCR normalises quote and apostrophe shapes; only the layer shows the print
            for f, rx in forms:
                for m in rx.finditer(s["text"]):
                    per[f][s["page"]].append((s, m))
        counts = {f: sum(len(v) for v in per[f].values()) for f in per}
        total = sum(counts.values())
        if not total:
            continue
        major = max(counts, key=counts.get)
        if counts[major] / total < HOUSE_SHARE:
            continue
        for f in counts:
            if f == major or not counts[f]:
                continue
            for page, hits in sorted(per[f].items()):
                s, m = hits[0]
                a, b = max(0, m.start() - 20), min(len(s["text"]), m.end() + 20)
                out.append({"page": page, "span": s["idx"], "start": m.start(), "end": m.end(),
                            "src": s["src"], "quote": s["text"][a:b].replace("\n", " "),
                            "kind": "tutarlılık", "suggestion": major, "needs_model": False,
                            "details": {"style": kind, "used": f, "book_majority": major,
                                        "count_on_page": len(hits), "book_counts": counts}})
    return out
