"""Turkish syllabification (TDK Yazım Kılavuzu, "Hece yapısı ve satır sonunda kelimelerin
bölünmesi") and the line-end break rules built on it. Pure functions, no I/O.

TDK's rule is deterministic: every syllable has exactly one vowel, and every syllable after
the first starts with exactly one consonant. So between two vowels
  - no consonant:       the break is between the vowels        sa-at, mü-da-fa-a
  - one consonant:      it goes to the next syllable            a-ra-ba
  - two consonants:     one each side                           al-dı, sev-mek
  - three (or more):    only the last goes to the next syllable alt-lık, Türk-çe, kont-rol
Western loanwords follow the same rule (TDK: band-rol, kont-rol, port-re, prog-ram, sant-ral,
sürp-riz, tund-ra, volf-ram) and compounds too (ba-şöğ-ret-men, il-ko-kul).
A line may not start or end with a single letter (u-çurtma, müdafa-a are wrong), and a word
broken at its apostrophe keeps only the apostrophe, no hyphen (Ankara'- is wrong).
"""

from __future__ import annotations

VOWELS = set("aeıioöuüâêîôû")
_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def lower_tr(s: str) -> str:
    """Turkish lower-casing (I -> ı, İ -> i); drops the combining dot some fonts export."""
    return s.translate(_LOWER).lower().replace("i̇", "i")


def is_letter(ch: str) -> bool:
    return ch.isalpha()


def syllable_breaks(word: str) -> list[int] | None:
    """Offsets (into `word`) where a syllable starts, the first excluded.
    None when the word cannot be syllabified (a character that is not a letter, no vowel)."""
    w = lower_tr(word)
    if len(w) != len(word) or not w or not all(is_letter(c) for c in w):
        return None
    vowels = [i for i, c in enumerate(w) if c in VOWELS]
    if not vowels:
        return None
    out = []
    for prev, cur in zip(vowels, vowels[1:]):
        out.append(cur if cur - prev == 1 else cur - 1)
    return out


def syllables(word: str) -> list[str] | None:
    b = syllable_breaks(word)
    if b is None:
        return None
    cuts = [0, *b, len(word)]
    return [word[a:c] for a, c in zip(cuts, cuts[1:])]


def allowed_breaks(word: str) -> list[int] | None:
    """Syllable boundaries where a line may break: no single letter on either side."""
    b = syllable_breaks(word)
    if b is None:
        return None
    return [i for i in b if i >= 2 and len(word) - i >= 2]


def hyphenate(word: str) -> str | None:
    s = syllables(word)
    return None if s is None else "-".join(s)


# TDK's own examples (and a few everyday words): the unit check below must pass.
TDK_EXAMPLES = {
    "araba": "a-ra-ba", "biçimine": "bi-çi-mi-ne", "aldı": "al-dı", "birlik": "bir-lik",
    "sevmek": "sev-mek", "altlık": "alt-lık", "Türkçe": "Türk-çe", "korkmak": "kork-mak",
    "bandrol": "band-rol", "kontrol": "kont-rol", "portre": "port-re", "program": "prog-ram",
    "santral": "sant-ral", "sürpriz": "sürp-riz", "tundra": "tund-ra", "volfram": "volf-ram",
    "başöğretmen": "ba-şöğ-ret-men", "ilkokul": "il-ko-kul", "Karaosmanoğlu": "Ka-ra-os-ma-noğ-lu",
    "müdafaa": "mü-da-fa-a", "uçurtma": "u-çurt-ma", "saat": "sa-at", "kütüphane": "kü-tüp-ha-ne",
    "İstanbul": "İs-tan-bul", "ILIK": "I-LIK", "elektrik": "e-lekt-rik", "şiir": "şi-ir",
}


def self_check() -> None:
    for w, want in TDK_EXAMPLES.items():
        got = hyphenate(w)
        assert got == want, (w, got, want)
    assert allowed_breaks("uçurtma") == [5]          # u-çurtma is not allowed, uçurt-ma is
    assert allowed_breaks("müdafaa") == [2, 4]        # mü-dafaa, müda-faa; not müdafa-a
    assert syllable_breaks("TV3") is None and syllable_breaks("hmm") is None


if __name__ == "__main__":
    self_check()
    print("ok", len(TDK_EXAMPLES))
