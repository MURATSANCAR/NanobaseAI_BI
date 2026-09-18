"""Deterministic first-person agreement between a source text and a claim.

Candidate component; not wired into the production pipeline.

A finite source predicate inflected for first person has the speaker of that
utterance as its subject.  A participant who is named in third person inside
the same utterance is therefore not that speaker.  When a claim reuses the
predicate and puts such a name in a subject case before it, every literal token
can be grounded while the subject has silently changed.  This module reports
only that positive signal.  It never proves a claim: third person singular is
unmarked in Turkish, an ambiguous word is never counted, and a name that also
occurs outside the utterance (a possible reporter) is left to the speaker gates.

The analyzer is injected: ``analyze(word) -> [(lemma, pos, [morpheme ids])]``.
No word list, name list or book specific rule is used.
"""
import re
import unicodedata

VERSION = 'source-person-agreement-v2'
FIRST_PERSONS = frozenset({'A1sg', 'A1pl'})
SECOND_PERSONS = frozenset({'A2sg', 'A2pl'})
PERSONS = FIRST_PERSONS | SECOND_PERSONS | {'A3sg', 'A3pl'}
TENSES = frozenset({'Past', 'Narr', 'Fut', 'Aor', 'Prog1', 'Prog2', 'Pres'})
APOSTROPHES = "'’ʼ`´"
OPENING, CLOSING, STRAIGHT = '“„«‘', '”»', '"\''
WORD = re.compile(r"[^\W\d_]+(?:['’ʼ`´][^\W\d_]+)?")
GENITIVE = re.compile(r'n?[ıiuü]n')
POSSESSED = frozenset({'P3sg', 'P3pl'})
ANY_POSSESSIVE = POSSESSED | {'P1sg', 'P2sg', 'P1pl', 'P2pl'}
PARTICIPLES = frozenset({'PastPart', 'FutPart'})
COORDINATORS = frozenset({'ve', 'ile', 'veya'})
SENTENCE_END = '.!?…'
MAX_BARE_SUFFIX = 4


def lower(text):
    return text.replace('İ', 'i').replace('I', 'ı').lower()


def split(surface):
    for index, char in enumerate(surface):
        if char in APOSTROPHES:
            return surface[:index], surface[index + 1:]
    return surface, None


def words(text):
    """Literal words with character offsets; apostrophe suffixes stay attached."""
    found = []
    for match in WORD.finditer(text):
        surface = match.group()
        stem, suffix = split(surface)
        before = text[:match.start()].rstrip(' \t\r\n' + OPENING + CLOSING + STRAIGHT + '(—–-')
        found.append({'surface': surface, 'stem': lower(stem), 'suffix': None if suffix is None else lower(suffix),
                      'start': match.start(), 'end': match.end(),
                      'sentence_initial': not before or before[-1] in SENTENCE_END + ':'})
    return found


def quoted(text):
    """(start, end, certain) spans of direct speech.  A span is uncertain when
    its opening mark is followed by another opening mark: its real end is unknown."""
    marks = []
    for index, char in enumerate(text):
        if char in OPENING:
            marks.append((index, True))
        elif char in CLOSING:
            marks.append((index, False))
        elif char in STRAIGHT:
            previous, following = text[index - 1:index], text[index + 1:index + 2]
            if char == "'" and previous.isalpha() and following.isalpha():
                continue
            marks.append((index, not previous.strip() or not (previous.isalnum() or previous in SENTENCE_END + ',')))
    spans, start = [], None
    for index, opening in marks:
        if opening:
            if start is not None:
                spans.append((start, index, False))
            start = index + 1
        elif start is not None:
            spans.append((start, index, True))
            start = None
        elif not spans:
            spans.append((0, index, True))
    if start is not None:
        spans.append((start, len(text), True))
    return [span for span in spans if span[0] < span[1]]


def utterances(text):
    """Text without any quotation mark is one utterance (a speech balloon unit)."""
    return quoted(text) or [(0, len(text), True)]


def readings(word, analyze):
    result = []
    for lemma, pos, morphemes in analyze(word['stem'] + (word['suffix'] or '')):
        morphemes, finite = list(morphemes), pos == 'Verb'
        result.append({'lemma': lemma, 'morphemes': morphemes,
                       'verbal_root': bool(morphemes) and morphemes[0] == 'Verb',
                       'person': next((m for m in reversed(morphemes) if m in PERSONS), None) if finite else None,
                       'tenses': sorted(set(morphemes) & TENSES) if finite else []})
    return result


def first_person_predicates(text, analyze):
    """Words inside an utterance whose every reading is a verb-root finite first person."""
    spans, found = utterances(text), []
    for word in words(text):
        span = next((s for s in spans if s[0] <= word['start'] < s[1]), None)
        parsed = readings(word, analyze)
        if span and span[2] and parsed and all(r['verbal_root'] and r['person'] in FIRST_PERSONS for r in parsed):
            found.append({'surface': word['surface'], 'start': word['start'], 'utterance': list(span[:2]),
                          'lemmas': sorted({r['lemma'] for r in parsed}),
                          'persons': sorted({r['person'] for r in parsed})})
    return found


def same_name(source_word, stem):
    if source_word['stem'] == stem:
        return True
    return source_word['suffix'] is None and source_word['stem'].startswith(stem) \
        and len(source_word['stem']) - len(stem) <= MAX_BARE_SUFFIX


def subject_names(claim, analyze):
    """Name-like claim words that can be a subject: a bare capitalised word, or an
    apostrophe genitive whose nearest possessed head is a participle.  A genitive
    absorbed first by a word that is possessed in every reading is a possessor.  Words the
    claim itself quotes are skipped.  A sentence-initial common word is harmless
    because a conflict also needs the same word inside the source utterance."""
    claim_words, spans, found = words(claim), quoted(claim), []
    for position, word in enumerate(claim_words):
        surface, marked = word['surface'], word['suffix'] is not None
        if any(s[0] <= word['start'] < s[1] for s in spans):
            continue
        suffix = word['suffix']
        if not marked:
            if not surface[0].isupper() or surface.isupper():
                continue
            # Turkish marks case once, on the last conjunct: "A ve B'yi".
            rest = claim_words[position + 1:]
            while len(rest) >= 2 and rest[0]['stem'] in COORDINATORS and rest[0]['suffix'] is None:
                suffix, rest = rest[1]['suffix'], rest[2:]
                if suffix is not None:
                    break
            if suffix is None:
                found.append({**word, 'case': 'NOMINATIVE', 'subject_from': word['end']})
                continue
        if not GENITIVE.fullmatch(suffix):
            continue
        for later in claim_words[position + 1:]:
            parsed = readings(later, analyze)
            if not parsed:
                continue
            participle = any(r['verbal_root'] and PARTICIPLES & set(r['morphemes']) and POSSESSED & set(r['morphemes'])
                             for r in parsed)
            if participle:
                found.append({**word, 'case': 'GENITIVE', 'subject_from': later['start']})
                break
            if all(any(m in ANY_POSSESSIVE for m in r['morphemes']) for r in parsed):
                break
    return found


def review(source, claim, analyze):
    predicates = first_person_predicates(source, analyze)
    source_words, claim_words = words(source), words(claim)
    conflicts, transfers = [], []
    for predicate in predicates:
        lemmas = set(predicate['lemmas'])
        reused = [w for w in claim_words
                  if any(r['verbal_root'] and r['lemma'] in lemmas for r in readings(w, analyze))]
        if not reused:
            continue
        transfers.append({'source_word': predicate['surface'], 'claim_words': [w['surface'] for w in reused]})
        begin, end = predicate['utterance']
        for name in subject_names(claim, analyze):
            if not any(name['subject_from'] <= w['start'] for w in reused):
                continue
            hits = [w for w in source_words if same_name(w, name['stem'])]
            inside = [w for w in hits if begin <= w['start'] < end]
            if inside and len(inside) == len(hits):
                conflicts.append({'source_predicate': predicate['surface'], 'persons': predicate['persons'],
                                  'claim_name': name['surface'], 'claim_case': name['case'],
                                  'source_mentions_inside_utterance': [w['surface'] for w in inside],
                                  'source_mentions_outside_utterance': 0})
    if conflicts:
        status, reason = 'NEEDS_REVIEW', 'FIRST_PERSON_PREDICATE_ASSIGNED_TO_NAME_INSIDE_SAME_UTTERANCE'
    else:
        status, reason = 'NO_SIGNAL', 'NO_FIRST_PERSON_NAME_CONFLICT'
    return {'version': VERSION, 'status': status, 'reason': reason, 'conflicts': conflicts,
            'source_first_person_predicates': predicates, 'transfers': transfers, 'proves_claim': False}


def tense_shifts(source, claim, analyze):
    """Report only.  A sentence-final source verb and a claim verb share one
    unambiguous lemma but differ in tense marking.  Non-final source verbs are
    skipped because a later coordinated verb may carry their tense suffix."""
    def finite(text, final_only):
        table = {}
        for word in words(text):
            parsed = readings(word, analyze)
            if not parsed or not all(r['verbal_root'] and r['person'] for r in parsed):
                continue
            if final_only and text[word['end']:].lstrip(CLOSING + STRAIGHT + ' ')[:1] not in tuple(SENTENCE_END):
                continue
            lemma_set, tense_set = {r['lemma'] for r in parsed}, {tuple(r['tenses']) for r in parsed}
            if len(lemma_set) == 1 and len(tense_set) == 1:
                table.setdefault(lemma_set.pop(), set()).add((word['surface'], tense_set.pop()))
        return table
    source_forms, claim_forms = finite(unicodedata.normalize('NFC', source), True), finite(claim, False)
    shifts = []
    for lemma in sorted(set(source_forms) & set(claim_forms)):
        source_tenses = {t for _, t in source_forms[lemma]}
        for surface, tenses in sorted(claim_forms[lemma]):
            if tenses not in source_tenses:
                shifts.append({'lemma': lemma, 'claim_word': surface, 'claim_tenses': list(tenses),
                               'source_forms': sorted([s, list(t)] for s, t in source_forms[lemma])})
    return shifts
