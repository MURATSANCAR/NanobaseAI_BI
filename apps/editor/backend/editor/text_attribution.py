"""Source-grounded Turkish dialogue attribution, without a book-specific lexicon.

This identifies explicit written attributions, not visual character identities
or the truth of an utterance. Unverified regions always break the text stream.
"""
import re
import unicodedata

from editor.source_alignment import reading_order, valid_box

VERSION = 'explicit-text-attribution-v1'
NAME = r'[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:[ \t]+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+){0,2}'
VERB = r'(?:dedi|sordu|yanıtladı|cevap verdi|bağırdı|fısıldadı|seslendi|ekledi|açıkladı|mırıldandı)'
PATTERNS = [re.compile(
    opening + r'(?P<quote>[^' + excluded + r']{1,1200}?)' + closing
    + r'\s*(?:diye\s+)?(?P<verb>' + VERB + r')\s+(?P<label>' + NAME + r')(?=[ \t]*[.!?]|\Z)')
    for opening, closing, excluded in (
        (r'["“]', r'["”]', '"“”'),
        (r"(?<!\w)['‘]", r"['’](?!\w)", "'‘’"),
    )]


def _adjacent(previous, current):
    x, y, w, h = previous; nx, ny, nw, nh = current
    same_line = abs(y+h/2-ny-nh/2) <= .6*max(h, nh)
    if same_line:
        return nx >= x and -.01 <= nx-(x+w) <= .08
    overlap = max(0, min(x+w, nx+nw)-max(x, nx)) / min(w, nw)
    return ny >= y and 0 <= ny-(y+h) <= 1.5*max(h, nh) and overlap >= .5


def segments(rows):
    """Keep a character-to-source map, and never bridge a missing/unknown region."""
    text=''; origins=[]; previous=None; previous_source=None
    for row in reading_order(rows):
        d=row['data']; box=d['bbox']
        source=(d.get('pdf_page'), d.get('render_sha256'))
        usable=d['status']=='TEXT_AGREED' and d.get('role')=='TEXT' and valid_box(box)
        if not usable or (previous is not None and (source != previous_source or not _adjacent(previous, box))):
            if text: yield text, origins
            text=''; origins=[]; previous=None
        if not usable: continue
        if text:
            text+='\n'; origins.append(None)
        raw=d['text']; text+=raw; origins.extend([str(row['id'])]*len(raw)); previous=box; previous_source=source
    if text: yield text, origins


def extract(rows, page_role):
    result={'method':VERSION, 'language':'tr', 'page_role':page_role,
            'attributions':[], 'named_mentions':[], 'visual_identity_verified':False,
            'eligible_for_synthesis':False}
    if page_role != 'NARRATIVE':
        result['reason']='NARRATIVE_SCOPE_NOT_VERIFIED'
        return result
    mentions={}
    for text, origins in segments(rows):
        matches=sorted((m for pattern in PATTERNS for m in pattern.finditer(text)), key=lambda m:m.start())
        for match in matches:
            if any(other is not match and max(match.start(),other.start()) < min(match.end(),other.end())
                   for other in matches):
                continue
            refs=list(dict.fromkeys(ref for ref in origins[match.start():match.end()] if ref))
            quote_refs=list(dict.fromkeys(ref for ref in origins[match.start('quote'):match.end('quote')] if ref))
            label=match.group('label')
            label_key=unicodedata.normalize('NFKC',label).replace('İ','i').replace('I','ı').lower()
            entry={'label':label, 'label_key':label_key, 'quote':match.group('quote'),
                   'source_text':match.group(), 'source_span_refs':refs, 'quote_span_refs':quote_refs,
                   'reporting_verb':match.group('verb'), 'status':'EXPLICIT_TEXT_ATTRIBUTION',
                   'visual_identity_verified':False, 'eligible_for_synthesis':False}
            result['attributions'].append(entry)
            mention=mentions.setdefault(label_key, {'label':label,'label_key':label_key,'source_span_refs':[]})
            mention['source_span_refs']=list(dict.fromkeys(mention['source_span_refs']+refs))
    result['named_mentions']=list(mentions.values())
    result['reason']='EXPLICIT_ATTRIBUTIONS_ONLY'
    return result


def speaker_for_claim(claim, attributions):
    from editor.source_pipeline import quote_tokens
    if claim.get('kind') != 'STATEMENT': return None
    needle=quote_tokens(claim.get('quote','')); refs=set(claim.get('span_refs',[]))
    if not needle or not refs: return None
    matches=[]
    def contains(a,b):
        return bool(b) and any(a[i:i+len(b)]==b for i in range(len(a)-len(b)+1))
    for item in attributions:
        utterance=quote_tokens(item['quote'])
        if refs <= set(item['quote_span_refs']) and contains(utterance,needle):
            matches.append(item)
    if len(matches) != 1: return None
    return {'label':matches[0]['label'],
            'source_span_refs':list(dict.fromkeys(ref for m in matches for ref in m['source_span_refs'])),
            'method':VERSION}
