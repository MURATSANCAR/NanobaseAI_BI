"""Pure selection of an independently supported regional OCR candidate.

No source record is modified and no semantic/character acceptance is granted.
The caller retains every original reader output and its crop/source geometry.
"""
import hashlib
import math
import re
import unicodedata

VERSION = 'independent-region-selection-v2'


def word_tokens(text):
    """Keep word boundaries and negation; do not dehyphenate or join words."""
    if not isinstance(text, str):
        raise ValueError('READER_TEXT_SCHEMA_MISMATCH')
    normalized = unicodedata.normalize('NFKC', text).replace('İ', 'i').replace('I', 'ı').lower()
    return re.findall(r'[^\W_]+', normalized)


def _corrupt(text):
    return any(unicodedata.category(char) in ('Co', 'Cs') or char == '\ufffd' for char in text)


def _hash(text):
    return hashlib.sha256(text.encode('utf-8', errors='surrogatepass')).hexdigest()


def select_regional_candidate(line, secondary, pdf_text, pdf_usable, reread=None):
    """Return literal region text only when independent readers support it.

    A rejected candidate has selected_text=None: callers must not confuse the
    unchanged full-page reading with an accepted fallback. Unstable rereads do
    not vote; two stable disagreeing rereads veto selection. Paddle full-page
    and crop readings are the same model family, not two independent votes.
    """
    full_page = line['text']
    region = line.get('region_text') or ''
    full_tokens = word_tokens(full_page)
    candidate_tokens = word_tokens(region)
    secondary_tokens = word_tokens(secondary)
    native_tokens = word_tokens(pdf_text)
    if not isinstance(pdf_usable, bool):
        raise ValueError('PDF_USABILITY_SCHEMA_MISMATCH')
    score = line.get('region_score')
    score_ok = (isinstance(score, (int, float)) and not isinstance(score, bool)
                and math.isfinite(score) and .9 <= score <= 1)
    secondary_agrees = bool(secondary_tokens) and secondary_tokens == candidate_tokens and not _corrupt(secondary)
    native_agrees = pdf_usable and bool(native_tokens) and native_tokens == candidate_tokens and not _corrupt(pdf_text)
    secondary_conflict = (bool(secondary_tokens) or _corrupt(secondary)) and not secondary_agrees
    native_conflict = pdf_usable and not native_agrees
    blockers = []
    if not candidate_tokens:
        blockers.append('EMPTY_REGION')
    if _corrupt(region):
        blockers.append('CORRUPT_REGION_TEXT')
    if not score_ok:
        blockers.append('LOW_OR_INVALID_REGION_SCORE')
    if not secondary_agrees and not native_agrees:
        blockers.append('NO_INDEPENDENT_READER_AGREEMENT')
    if secondary_conflict:
        blockers.append('SECONDARY_READER_CONFLICT')
    if native_conflict:
        blockers.append('USABLE_PDF_CONFLICT')
    reread_state = 'NOT_AVAILABLE'
    reread_hashes = []
    crop_provenance = None
    if reread is not None:
        readings = reread.get('readings')
        if (not isinstance(readings, list) or len(readings) != 2
                or [reading.get('psm') for reading in readings] != [7, 13]):
            raise ValueError('REREAD_SCHEMA_MISMATCH')
        raw = [reading['text'] for reading in readings]
        reread_tokens = [word_tokens(text) for text in raw]
        reread_hashes = [{'psm': reading['psm'], 'text_sha256': _hash(reading['text'])} for reading in readings]
        stable = bool(reread_tokens[0]) and reread_tokens[0] == reread_tokens[1]
        if stable:
            agrees = reread_tokens[0] == candidate_tokens and not any(_corrupt(text) for text in raw)
            reread_state = 'AGREES' if agrees else 'DISAGREES'
            if not agrees:
                blockers.append('STABLE_REREAD_CONFLICT')
        else:
            reread_state = 'UNSTABLE'
        # The caller verifies these immutable measurements against their source
        # artifacts. Require a scoped crop and retained raw-TSV hashes here too.
        digest_ok = lambda value: isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None
        if (reread.get('bbox') == line.get('bbox') and isinstance(line.get('bbox'), list)
                and digest_ok(reread.get('crop_sha256'))
                and all(digest_ok(reading.get('tsv_sha256')) for reading in readings)):
            crop_provenance = {'bbox': reread['bbox'], 'crop_sha256': reread['crop_sha256'],
                'source_span_id': reread.get('source_span_id'),
                'readings': [{'psm': reading['psm'], 'tsv_sha256': reading['tsv_sha256'],
                              'text_sha256': _hash(reading['text'])} for reading in readings]}
    superseded = (secondary_conflict and not _corrupt(secondary) and native_agrees
                  and score_ok and bool(candidate_tokens) and not _corrupt(region)
                  and reread_state == 'AGREES' and crop_provenance is not None)
    if superseded:
        blockers.remove('SECONDARY_READER_CONFLICT')
    supported = not blockers
    return {
        'method': VERSION,
        'status': 'SUPPORTED_REGIONAL_CANDIDATE' if supported else 'NEEDS_REVIEW',
        'selected_text': region if supported else None,
        'selected_reader': 'REGIONAL_OCR' if supported else None,
        'raw_full_page_text': full_page,
        'raw_secondary_text': secondary,
        'superseded_readers': ['FULL_PAGE_TESSERACT_SUPERSEDED'] if superseded else [],
        'full_page_tokens_differ': candidate_tokens != full_tokens,
        'blockers': blockers,
        'supporting_readers': ([name for name, agrees in
            (('TESSERACT', secondary_agrees), ('TESSERACT_CROP', superseded), ('NATIVE_PDF', native_agrees)) if agrees]),
        'reread_state': reread_state,
        'provenance': {
            'full_page_text_sha256': _hash(full_page),
            'region_text_sha256': _hash(region),
            'secondary_text_sha256': _hash(secondary),
            'pdf_text_sha256': _hash(pdf_text),
            'region_score': score,
            'pdf_usable': pdf_usable,
            'reread_text_hashes': reread_hashes,
            'crop_measurement': crop_provenance,
            'supersession': 'FULL_PAGE_TESSERACT_SUPERSEDED' if superseded else None,
            'comparison': 'NFKC_TR_CASE_WORD_TOKENS_NO_JOINING',
        },
        'eligible_for_synthesis': False,
        'visual_identity_verified': False,
    }
