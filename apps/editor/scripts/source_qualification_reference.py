"""Independent lexical qualification v1/v2 reconstruction; no product import."""
import re
import unicodedata


def expected_qualification(claim, views, version):
    assert version in ('source-qualification-v1','source-qualification-v2')
    current=version=='source-qualification-v2'
    def tokens(text):
        return re.findall(r'[^\W_]+',unicodedata.normalize('NFKC',text).replace('İ','i').replace('I','ı').lower())
    def witnesses(text):
        value=unicodedata.normalize('NFKC',text)
        words={word for form in (value.replace('İ','i').replace('I','ı').lower(),value.casefold()) for word in re.findall(r'[^\W_]+',form)}
        fixed={'galiba','belki','muhtemelen','herhalde','sanırım','sanıyorum','perhaps','maybe','possibly','probably','might'}
        pattern=r'olabilir\w*|olabilece\w*|olasılık\w*|ihtimal\w*|tahmin\w*'+(r'|öner\w*' if current else '')
        return sorted(word for word in words if word in fixed or re.fullmatch(pattern,word))
    full='\n'.join(view['reading_text'] for view in views);scope=full;ranges=[]
    scope_reason='NO_FULL_CLAIM_SENTENCE_MATCH'
    if current:
        boundaries=[];ambiguous=False
        for boundary in re.finditer(r'[.!?]\s+',full):
            at=boundary.start();before=full[:at]
            if before.count('"')%2 or before.count('“')!=before.count('”') or (at>0 and full[at-1] in '.!?'):
                ambiguous=True;break
            if full[at]=='.':
                previous=re.search(r'([^\W_]+)$',before)
                if previous is None or len(previous.group())<4 or not previous.group().islower() or not previous.group().isalpha():
                    ambiguous=True;break
            boundaries.append(boundary.end())
        if ambiguous:scope_reason='AMBIGUOUS_SENTENCE_BOUNDARY'
        else:
            wanted=tokens(claim.get('text') or '');start=0
            for end in boundaries+[len(full)]:
                candidate=tokens(full[start:end]);cursor=0
                for token in candidate:
                    if cursor<len(wanted) and wanted[cursor]==token:cursor+=1
                if wanted and cursor==len(wanted) and end>start:ranges.append([start,end])
                start=end
            if ranges:
                scope='\n'.join(full[start:end] for start,end in ranges);scope_reason='FULL_CLAIM_ORDERED_TOKEN_MATCH'
    source=witnesses(scope);candidate=witnesses(claim.get('text') or '');passed=not source or bool(candidate)
    expected={'version':version,'source_markers':source,'claim_markers':candidate,'passed':passed,
              'reason':'LEXICAL_QUALIFICATION_PRESERVED_OR_ABSENT' if passed else 'SOURCE_QUALIFICATION_MISSING_FROM_CLAIM',
              'scope_verified':False,'semantic_acceptance':False}
    if current:expected.update(source_scope='MATCHED_SOURCE_SENTENCES' if ranges else 'FULL_CITED_TEXT',
                               matched_sentence_ranges=ranges,source_scope_reason=scope_reason,all_source_markers=witnesses(full))
    return expected


def verify_qualification(claim, views, gate):
    assert isinstance(gate,dict),'SOURCE_QUALIFICATION_MISSING'
    expected=expected_qualification(claim,views,gate.get('version'))
    assert gate==expected and expected['passed'],'SOURCE_QUALIFICATION_NOT_PRESERVED'
