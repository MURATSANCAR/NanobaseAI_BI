"""Void a lone reader's objection when it is a diacritic-only non-word.

Candidate component; not wired into the production pipeline.

Optical acceptance keeps a region in review when one independent reader
disagrees.  Some objections differ from the supported reading only in Turkish
diacritics and are not Turkish word forms at all ("serinligi" against
"serinliği").  This module never produces or corrects text.  It only decides
whether such an objection may be set aside, and only when

* at least two independent readers already agree on the whole region,
* the objecting reading has the same words up to diacritics,
* every differing agreed word is a valid word form and the objecting one is not,
* every differing word has at least ``MIN_LETTERS`` letters and is not a
  line-end hyphen fragment.

Two valid forms ("sırada" / "sirada"), two invalid forms, names and sound words
stay in review.  The selected text is always a raw reader output.

The analyzer is injected: ``is_word(lowercase word) -> bool``.
"""
import re
import unicodedata

VERSION = 'source-diacritic-witness-v1'
MIN_LETTERS = 3
WORD = re.compile(r'[^\W\d_]+')
FOLD = str.maketrans('ıİşŞğĞçÇöÖüÜâÂîÎûÛ', 'iIsSgGcCoOuUaAiIuU')


def lower(text):
    return text.replace('İ', 'i').replace('I', 'ı').lower()


def tokens(text):
    return [lower(w) for w in WORD.findall(unicodedata.normalize('NFC', text))]


def fold(word):
    return unicodedata.normalize('NFKD', word.translate(FOLD)).encode('ascii', 'ignore').decode().lower()


def hyphen_fragments(text):
    """Indexes of words that are only a piece of a word split at a line end."""
    text = unicodedata.normalize('NFC', text)
    found = [m for m in WORD.finditer(text)]
    broken = set()
    for index, match in enumerate(found):
        if text[match.end():match.end() + 1] in '-‐‑' and not text[match.end() + 1:match.end() + 2].isalpha():
            broken.update({index, index + 1})
    return broken


def review(readings, is_word):
    """``readings``: {reader name: raw text} of independent readers for one region."""
    parsed = {name: tokens(text) for name, text in readings.items() if tokens(text)}
    result = {'version': VERSION, 'decision': 'NO_DECISION', 'text_corrections': 0}
    groups = {}
    for name, words in parsed.items():
        groups.setdefault(tuple(words), []).append(name)
    agreed = [(words, names) for words, names in groups.items() if len(names) >= 2]
    if len(agreed) != 1:
        return {**result, 'reason': 'NO_TWO_READER_AGREEMENT'}
    agreed_words, supporters = agreed[0]
    objectors = [name for name in parsed if name not in supporters]
    if not objectors:
        return {**result, 'reason': 'NO_OBJECTION'}
    fragments = set().union(*(hyphen_fragments(readings[name]) for name in parsed))
    details = []
    for name in objectors:
        words = parsed[name]
        if len(words) != len(agreed_words) or [fold(w) for w in words] != [fold(w) for w in agreed_words]:
            return {**result, 'reason': 'OBJECTION_NOT_DIACRITIC_ONLY', 'objector': name}
        for index, (kept, objected) in enumerate(zip(agreed_words, words)):
            if kept == objected:
                continue
            if index in fragments:
                return {**result, 'reason': 'LINE_END_FRAGMENT', 'objector': name}
            if len(kept) < MIN_LETTERS:
                return {**result, 'reason': 'WORD_TOO_SHORT', 'objector': name}
            kept_ok, objected_ok = is_word(kept), is_word(objected)
            if not kept_ok or objected_ok:
                return {**result, 'objector': name, 'words': [kept, objected],
                        'reason': 'BOTH_VALID' if kept_ok else 'AGREED_WORD_NOT_VALID'}
            details.append({'objector': name, 'agreed': kept, 'objected': objected})
    return {**result, 'decision': 'OBJECTION_VOID', 'reason': 'DIACRITIC_VETO_NOT_A_WORD',
            'supporters': sorted(supporters), 'objectors': sorted(objectors), 'words': details}
