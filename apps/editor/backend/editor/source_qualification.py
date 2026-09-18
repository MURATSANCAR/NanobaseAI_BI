"""Conservative source-qualification preservation, never semantic acceptance.

An explicit uncertainty marker in cited Turkish or English text cannot silently
disappear from an assertion. This bounded lexical gate may request review for
valid paraphrases or unrelated clauses; it never rewrites them or infers scope.
The separate semantic and per-token support reviews remain necessary.
"""
import re
import unicodedata

VERSION = 'source-qualification-v2'
MARKERS = frozenset((
    'galiba', 'belki', 'muhtemelen', 'herhalde', 'sanırım', 'sanıyorum',
    'perhaps', 'maybe', 'possibly', 'probably', 'might',
))


def markers(text):
    value = unicodedata.normalize('NFKC', text)
    # Retain Turkish dotted/dotless I while also recognizing English uppercase
    # witnesses such as MIGHT. Neither normalization supplies source meaning.
    forms = (value.replace('İ', 'i').replace('I', 'ı').lower(), value.casefold())
    words = {word for form in forms for word in re.findall(r'[^\W_]+', form)}
    # Turkish possible/possibility inflections; not all words containing -abilir.
    # These witnesses only avoid a lexical rejection, never establish scope.
    return sorted({word for word in words if word in MARKERS
                   or re.fullmatch(r'olabilir\w*|olabilece\w*|olasılık\w*|ihtimal\w*|tahmin\w*|öner\w*', word)})


def sentence_scope(text, source):
    """Only narrow to sentences containing every claim token in order.

    Dots after short/uppercase/numeric tokens, ellipses and boundaries inside
    open quotation marks are ambiguous. Any such boundary keeps full scope.
    This is a literal-match scope, never semantic or coreference authority.
    """
    def tokens(value):
        value=unicodedata.normalize('NFKC',value).replace('İ','i').replace('I','ı').lower()
        return re.findall(r'[^\W_]+',value)
    bounds=[]
    for match in re.finditer(r'[.!?]\s+',source):
        position=match.start();prefix=source[:position]
        if (prefix.count('"') % 2 or prefix.count('“')!=prefix.count('”')
                or (position and source[position-1] in '.!?')):
            return source,[], 'AMBIGUOUS_SENTENCE_BOUNDARY'
        if source[position]=='.':
            last=re.search(r'([^\W_]+)$',prefix)
            if not last or len(last.group())<4 or not last.group().islower() or not last.group().isalpha():
                return source,[], 'AMBIGUOUS_SENTENCE_BOUNDARY'
        bounds.append(match.end())
    ranges=[];start=0
    for end in bounds+[len(source)]:
        if end>start:ranges.append([start,end])
        start=end
    wanted=tokens(text);matched=[]
    if wanted:
        for start,end in ranges:
            cursor=0
            for token in tokens(source[start:end]):
                if cursor<len(wanted) and token==wanted[cursor]:cursor+=1
            if cursor==len(wanted):matched.append([start,end])
    if not matched:return source,[], 'NO_FULL_CLAIM_SENTENCE_MATCH'
    return '\n'.join(source[start:end] for start,end in matched),matched,'FULL_CLAIM_ORDERED_TOKEN_MATCH'


def qualification_gate(text, reading):
    full_source='\n'.join(view['reading_text'] for view in reading)
    scoped,ranges,scope_reason=sentence_scope(text,full_source)
    source = markers(scoped)
    claim = markers(text)
    passed = not source or bool(claim)
    return {'version': VERSION, 'source_markers': source, 'claim_markers': claim,
            'passed': passed,
            'reason': 'LEXICAL_QUALIFICATION_PRESERVED_OR_ABSENT' if passed
                      else 'SOURCE_QUALIFICATION_MISSING_FROM_CLAIM',
            'source_scope':'MATCHED_SOURCE_SENTENCES' if ranges else 'FULL_CITED_TEXT',
            'matched_sentence_ranges':ranges,'source_scope_reason':scope_reason,
            'all_source_markers':markers(full_source),
            'scope_verified': False, 'semantic_acceptance': False}
