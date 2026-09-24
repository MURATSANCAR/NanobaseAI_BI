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
    edge = page is not None and (page <= max(6, round(last_page * 0.08))
                                 or page > last_page - max(4, round(last_page * 0.05)))
    return m.group(1) if len(rest) <= 1 and edge else None
