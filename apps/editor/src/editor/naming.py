"""Is a written name used as a name, and is it this character's name?

Turkish marks no article, so the only sign the writing itself carries for "this word is
used as a proper name" is a capital letter where the sentence does not force one. In the
middle of a sentence — not after a full stop, a dash, a colon or an opening quote — the
capital is the writer's own decision, and over a whole book that decision is stable: a
person's name is written with a capital nearly everywhere it occurs, while a common noun
that only describes someone ("annesi", "tayfa") or a pronoun ("ben", "o") is not. The
share of capitalised mid-sentence uses is therefore a measurement of the book's own
usage: it needs no list of names, no dictionary and no knowledge of which book this is.
(`proofing/series_canon` measures the same physical property to answer a different
question — whether a name can recur across the books of a series.)

Two further invariants need no text at all, only the shape of one generation's proposal:

* a character's alias cannot be another character's canonical name in the same
  generation — one written name cannot be the main name of one person and a second name
  of another, and if it were, every name-based lookup (graph._resolve, vision, event
  actors) would answer with whichever row it reached first;
* an entity the reader declared a collective or a concept is not a person, so it must
  not become a `character` row that people, drawings and events are then attached to.

Everything here is a pure function over strings: no database, no model, no book.
"""

from __future__ import annotations

import math
import re

from . import ledger

# A word: letters only, so digits and the suffix after an apostrophe ("Mert'in" -> "Mert",
# "in") are separate tokens.
_WORD = re.compile(r"[^\W\d_]+")
# A capital immediately after one of these is required by the sentence (or by the
# apostrophe/quotation the layer left behind), so it says nothing about the word.
_FORCED_AFTER = set(".!?…:;\"“”«»'‘’-–—(\n\r\t")
# entity_scope values that are not a person. UNKNOWN is not among them: an entity the
# reader could not classify is still read as a person, as it was before this module.
NON_PERSON_SCOPES = frozenset({"COLLECTIVE", "CONCEPT"})

# reasons a name is refused; they are written into the claim payload and the character row
NOT_A_PROPER_NAME = "NOT_A_PROPER_NAME"
OTHER_CHARACTERS_NAME = "OTHER_CHARACTERS_NAME"
SCOPE_NOT_A_PERSON = "SCOPE_NOT_A_PERSON"


def key(name: str) -> str:
    """Identity key for a written name — the same normalisation the ledger uses, so a
    name compared here and the same name compared in SQL cannot disagree."""
    return ledger.norm(name)




def usage(name: str, text: str) -> tuple[int, int]:
    """(mid-sentence occurrences of the name, of which written with a capital).

    A multi-word name has to occur as that sequence of words; only the first word's
    capitalisation is read, because that is the one the sentence could have forced.

    Words are matched with Turkish case folding. `casefold` is not Turkish — it turns "İ"
    into "i̇" and "I" into "i", so "İlker"/"ilker" would not match while "Irmak"/"ırmak"
    would — so the pairs I/ı and İ/i are mapped before normalising. This is the
    word-counting comparison only; `key` stays the ledger's normalisation, so no identity
    decision can drift away from what SQL sees.
    """
    def fold(s: str) -> str:
        return ledger.norm(s.replace("I", "ı").replace("İ", "i"))

    want = [w for w in (fold(w) for w in _WORD.findall(name or "")) if w]
    if not want:
        return 0, 0
    tokens = [(m.start(), m.group(0)) for m in _WORD.finditer(text or "")]
    folded = [fold(t) for _, t in tokens]
    mid = cap = 0
    for i in range(len(tokens) - len(want) + 1):
        if folded[i:i + len(want)] != want:
            continue
        start = tokens[i][0]
        j = start - 1
        while j >= 0 and text[j] in " \t":
            j -= 1
        if j < 0 or text[j] in _FORCED_AFTER:
            continue                      # the capital here is the sentence's, not the writer's
        mid += 1
        cap += tokens[i][1][:1].isupper()
    return mid, cap


def proper_share(name: str, text: str) -> float | None:
    """Share of mid-sentence uses written with a capital; None when the book never uses
    the name mid-sentence and the question therefore cannot be answered."""
    mid, cap = usage(name, text)
    return cap / mid if mid else None


def is_proper_name(name: str, text: str, *, min_share: float, min_uses: int) -> bool:
    """Does the book write this name the way it writes a name?"""
    mid, cap = usage(name, text)
    return mid >= max(1, min_uses) and cap / mid >= min_share


def screen_group_names(groups: list[dict], text: str, *, min_share: float,
                       min_uses: int) -> list[dict]:
    """Decide, for one generation's proposed characters, which are people and which of
    their names are really their names.

    `groups` is [{"canonical": str, "aliases": [str], "entity_scope": str}] in the order
    they were proposed. Returns one verdict per group, in the same order:

        {"person": bool, "reject_reason": str | None, "canonical": str,
         "aliases": [str], "dropped": [{"name", "reason", "mid", "cap", "share"}]}

    A refused alias is not a smaller mistake than a refused character: the mentions that
    carried it are the ones that pointed at the wrong person, so the caller must leave
    them unresolved rather than keep them on this character.
    """
    people = [dict(g) for g in groups if (g.get("entity_scope") or "UNKNOWN") not in NON_PERSON_SCOPES]
    # a name may be claimed as a canonical by more than one person (two people can be
    # written the same way); it is still nobody else's alias.
    canonical_keys: dict[str, set[int]] = {}
    for i, g in enumerate(people):
        canonical_keys.setdefault(key(g.get("canonical") or ""), set()).add(i)

    out: list[dict] = []
    seen_people = -1
    for g in groups:
        scope = g.get("entity_scope") or "UNKNOWN"
        canonical = (g.get("canonical") or "").strip()
        if scope in NON_PERSON_SCOPES:
            out.append({"person": False, "reject_reason": SCOPE_NOT_A_PERSON,
                        "canonical": canonical, "aliases": [], "dropped": []})
            continue
        seen_people += 1
        kept, dropped = [], []
        own = key(canonical)
        for a in g.get("aliases") or []:
            a = (a or "").strip()
            k = key(a)
            if not k or k == own:
                continue
            mid, cap = usage(a, text)
            share = cap / mid if mid else None
            if canonical_keys.get(k, set()) - {seen_people}:
                reason = OTHER_CHARACTERS_NAME
            elif not (mid >= max(1, min_uses) and share is not None and share >= min_share):
                reason = NOT_A_PROPER_NAME
            else:
                kept.append(a)
                continue
            dropped.append({"name": a, "reason": reason, "mid": mid, "cap": cap, "share": share})
        out.append({"person": True, "reject_reason": None, "canonical": canonical,
                    "aliases": kept, "dropped": dropped})
    return out


# ------------------------------------------------------------------ book credits
# The imprint names the people who made the book — «Yayın Yönetmeni: İhsan Sönmez», «Kapak
# Tasarımı: Ravza Kızıltuğ». They are the book's credits, not people of its text: read as
# characters they became «Yayın Yönetmeni», «Kitabın editörü», «kapak tasarımını yapan kişi»
# in two books of 2026-09-23. Labels as publishers print them (folded: lower case, ASCII).
CREDIT_LABELS = (
    "genel yayin yonetmeni", "yayin yonetmeni", "yayin koordinatoru", "yayin editoru", "proje editoru",
    "dizi editoru", "editor", "editorler", "kapak tasarimi", "kapak tasarim", "kapak illustrasyonu",
    "kapak resmi", "kapak", "ic tasarim", "sayfa tasarimi", "sayfa duzeni", "grafik tasarim", "mizanpaj",
    "dizgi", "yayina hazirlayan", "yayina hazirlayanlar", "redaksiyon", "redaktor", "duzelti",
    "son okuma", "ceviri", "ceviren", "cevirmen", "resimleyen", "resimler", "cizer", "cizimler",
    "illustrasyon", "illustrasyonlar", "illustrator", "fotograflar", "baski", "cilt", "matbaa",
)
_CREDIT_ALT = "|".join(re.escape(x) for x in sorted(CREDIT_LABELS, key=len, reverse=True))
_CREDIT = re.compile(rf"\b({_CREDIT_ALT})\b")
_CREDIT_BEFORE = re.compile(rf"\b({_CREDIT_ALT})$")


def _fold(s: str) -> str:
    from .book_type import fold
    return fold(s)


def credit_role(name: str, quote: str, page: int | None, last_page: int) -> str | None:
    """The imprint role this mention names («kapak tasarimi»), or None when it is a person of
    the text. A credit is a name printed right next to a credit label, in an imprint:
      * a block of two or more different labels (an imprint page read as one quote), or
      * one label, the name and at most one other word, on the book's first or last pages.
    «Editör Ahmet kapıyı açtı» in a novel keeps Ahmet a character: one label, two other words."""
    q, n = _fold(quote), _fold(name)
    if not n or n not in q:
        return None
    labels = {m.group(1) for m in _CREDIT.finditer(q)}
    if not labels:
        return None
    i = q.index(n)
    before, after = q[:i].rstrip(), q[i + len(n):].lstrip()
    m = _CREDIT_BEFORE.search(before) or _CREDIT.match(after)
    if not m:
        return None
    if len(labels) >= 2:
        return m.group(1)
    rest = _CREDIT.sub(" ", q.replace(n, " ")).split()
    return m.group(1) if len(rest) <= 1 and edge_page(page, last_page) else None


def edge_page(page: int | None, last_page: int) -> bool:
    """Is this one of the book's first or last pages — where a book prints what is ABOUT it
    (title, imprint, author and illustrator notes, other titles of the series) and not what is
    IN it? The same bound `credit_role` has always used: the first max(6, 8%) pages, the last
    max(4, 5%)."""
    return page is not None and (page <= max(6, round(last_page * 0.08))
                                 or page > last_page - max(4, round(last_page * 0.05)))


# ------------------------------------------------------------------ words and occurrences
def words(text: str) -> list[str]:
    """The words of a text as the comparisons below read them: ASCII-folded with Turkish case
    rules, a suffix after an apostrophe a separate word («Anna’nın» -> anna, nin), a word broken
    at a line end joined again («program- lı» -> programlı)."""
    return _fold(ledger._HYPH.sub(r"\1\2", text or "")).split()


def wkey(name: str) -> str:
    """A written name as `words` reads it: «Anıl Basılı», «ANIL BASILI» and «Anil Basili» are one."""
    return " ".join(words(name))


def name_occurrences(pages: dict[int, str], names) -> dict[int, set[str]]:
    """Which of `names` each page writes, as sets of `wkey(name)` (pages writing none are left out).

    The page is read left to right and at every position the LONGEST name written there wins
    and is consumed: the «Anna» inside «Anna Maria van Schurman» is that longer name's
    occurrence, not a separate «Anna» (nor a separate «Maria»). Names match as whole words."""
    seqs: dict[tuple[str, ...], str] = {}
    for n in names:
        w = tuple(words(n))
        if w:
            seqs.setdefault(w, " ".join(w))
    by_first: dict[str, list[tuple[str, ...]]] = {}
    for s in sorted(seqs, key=len, reverse=True):
        by_first.setdefault(s[0], []).append(s)
    out: dict[int, set[str]] = {}
    for p, text in pages.items():
        toks = words(text)
        found: set[str] = set()
        i = 0
        while i < len(toks):
            for s in by_first.get(toks[i], ()):
                if tuple(toks[i:i + len(s)]) == s:
                    found.add(seqs[s])
                    i += len(s)
                    break
            else:
                i += 1
        if found:
            out[p] = found
    return out


# ------------------------------------------------------------------ an alias needs a link in the book
# Two written names are one person only where the book says so. The proposal's merge rule already
# asks for it («kanıtı olmayan birleştirme yapma») and the cross-window join checks a verbatim quote
# naming both sides; nothing checked it for the names of one proposal. Measured 2026-09-30: a novel's
# narrator «Maria» received the alias «Anna» — a baby born on another page, whose name the book never
# writes on any page that also writes «Maria» (the «Anna» of «Anna Maria van Schurman», a third
# person, is that longer name's). A link needs, at the very least, one page that writes both names.
NO_SHARED_EVIDENCE = "NO_SHARED_EVIDENCE"


def screen_shared_evidence(verdicts: list[dict], pages: dict[int, str]) -> list[dict]:
    """Refuse every alias the book never links to the character's other names.

    `verdicts` is the output of `screen_group_names` (same order, same keys); `pages` maps a page
    number to the page's text. An alias that shares a word with the canonical name («Bulut» of
    «Profesör Bulut») is linked by its own form. Any other alias must be written on at least one
    page together with a name already linked (the canonical, a form-linked alias, or an alias
    linked this way — a chain «Mehmet» → «Memo» → «Memoş» holds). Each name counts only where it
    is written as itself (`name_occurrences`: a name inside a longer name is the longer name's).

    This is a necessary condition, not proof: a shared page does not make two names one person
    (the proposal and its critic decide that); no shared page means nothing in the book joins
    them. A refused alias is listed in `dropped` with reason NO_SHARED_EVIDENCE and the pages that
    write it, so the caller returns the mentions that carried it to unresolved."""
    people = [v for v in verdicts if v.get("person")]
    occ = name_occurrences(pages, [n for v in people for n in [v["canonical"], *v["aliases"]]])
    out = []
    for v in verdicts:
        if not v.get("person") or not v.get("aliases"):
            out.append(v)
            continue
        own = set(words(v["canonical"]))
        anchored = {wkey(v["canonical"])} | {wkey(a) for a in v["aliases"] if own & set(words(a))}
        open_ = [a for a in v["aliases"] if wkey(a) not in anchored]
        grew = True
        while open_ and grew:
            grew = False
            for a in list(open_):
                if any(wkey(a) in f and f & anchored for f in occ.values()):
                    anchored.add(wkey(a))
                    open_.remove(a)
                    grew = True
        refused = {wkey(a) for a in open_}
        dropped = list(v.get("dropped") or []) + [
            {"name": a, "reason": NO_SHARED_EVIDENCE, "mid": None, "cap": None, "share": None,
             "pages": sorted(p for p, f in occ.items() if wkey(a) in f)[:20]} for a in open_]
        out.append({**v, "aliases": [a for a in v["aliases"] if wkey(a) not in refused], "dropped": dropped})
    return out


# ------------------------------------------------------------------ pages about the book, not in it
# An author's note («Gazetecilik mezunu … Köpek dostu Dali ile çimlerde yuvarlanmayı seviyor»), an
# illustrator's note, a title page: the people there are the book's makers and their life, not
# people of its story. Read as a story they became «Kitabın yazarı» and «yazarın köpeği» as
# CONFIRMED characters (2026-09-30). Such a page is known two ways, neither a list of words:
#   * a page role that says so — the extractor's NON_STORY suggestion or the editor's decision
#     (FRONT_MATTER / NON_STORY); the suggestion never removes the page from the reading, it only
#     decides that a person who appears on NO other page is not a person of the story;
#   * one of the book's first or last pages (`edge_page`) that writes the full name of one of the
#     book's contributors (the publisher's CRM record: authors, illustrators).
PARATEXT_ONLY = "PARATEXT_ONLY"


def about_the_book_pages(roles) -> list[int]:
    """Pages the page roles put outside the text: FRONT_MATTER always; NON_STORY only in a book that
    has STORY pages. A non-fiction book (an essay, a biography, a study) is NON_STORY on every page —
    İbn Sina 148/148, Takılı Kalan Zihin 110/110 (2026-10-02) — and there NON_STORY says nothing about
    which page talks about the book: read as paratext it refused every person the book discusses
    («İbn Sînâ'nın babası Abdullah, annesi Sitâre», Aristoteles, Platon) as PARATEXT_ONLY."""
    rows = [(int(r["page_no"]), r["role"]) for r in roles]
    story = any(role == "STORY" for _, role in rows)
    return [p for p, role in rows if role == "FRONT_MATTER" or (role == "NON_STORY" and story)]


def paratext_pages(pages: dict[int, str], role_pages, contributors, last_page: int) -> set[int]:
    """Pages about the book rather than in it (see above). A contributor's name counts only in
    full and only with two or more words, so a one-word name the story also uses cannot turn a
    story page into an author's page."""
    out = {int(p) for p in role_pages}
    names = [c for c in contributors or [] if len(words(c)) >= 2]
    if names:
        edge = {p: t for p, t in pages.items() if edge_page(p, last_page)}
        out |= set(name_occurrences(edge, names))
    return out


# ------------------------------------------------------------------ which page a description rests on
def description_pages(description: str, pages: dict[int, str], candidates, name_words: set[str],
                      top: int = 3) -> list[int]:
    """The pages among `candidates` (the character's own pages) whose text carries what the
    description says, best first; empty when no page carries any of it.

    A character's first page is where it is first NAMED — in a picture book often a cast page
    that prints only the names («Somurtkan Hala Sirkenaz Bitirim Hürdeniz») — and it was cited
    as the source of «Somurtkan Hala'nın torunu, planlı programlı», which the book says on pages
    58 and 62 (2026-09-30). Here the description's own words are looked for on the pages:
    names are left out (`name_words`: every name of every character — they say who, not what),
    a word is compared by its first five letters (Turkish suffixes: torunu ~ torun, programlı ~
    program), words shorter than four letters are ignored, and each word weighs by how rare it
    is in the book (a word on every page says nothing about any page)."""
    def stems(text: str) -> set[str]:
        return {w[:5] for w in words(text) if len(w) >= 4 and w not in name_words}

    want = stems(description)
    if not want:
        return []
    page_stems = {p: stems(t) & want for p, t in pages.items()}
    n = max(1, len(page_stems))
    df: dict[str, int] = {}
    for st in page_stems.values():
        for s in st:
            df[s] = df.get(s, 0) + 1
    scored = []
    for p in dict.fromkeys(candidates):
        got = page_stems.get(p) or set()
        score = sum(math.log((n + 1) / (df[s] + 1)) for s in got)
        if score > 0:
            scored.append((-score, p))
    return [p for _, p in sorted(scored)[:top]]
