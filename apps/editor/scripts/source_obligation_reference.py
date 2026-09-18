"""Independent v2/v3 obligation proof reconstruction; no production imports."""
import hashlib
import json
import re


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def verify_obligations(claim, regions, review):
    version=review.get('version')
    assert version in ('source-obligations-v2','source-obligations-v3'), 'OBLIGATION_VERSION_UNSUPPORTED'
    text=claim['text']
    assert isinstance(text,str) and text.strip(), 'OBLIGATION_EMPTY_CLAIM'
    words=list(re.finditer(r'\S+',text))
    assert 0<len(words)<=128, 'OBLIGATION_TOKEN_BOUND'
    assert regions and len({r['span_id'] for r in regions})==len(regions), 'OBLIGATION_SOURCE_SCOPE'
    units=[];cursor=0
    for number,word in enumerate(words,1):
        end=len(text) if number==len(words) else word.end()
        units.append({'id':'TOKEN_'+str(number).zfill(3),'start':cursor,'end':end,'text':text[cursor:end]})
        cursor=end
    assert cursor==len(text) and ''.join(unit['text'] for unit in units)==text, 'OBLIGATION_CHARACTER_COVERAGE'
    anchors=[];sources=[]
    for region in regions:
        assert isinstance(region['text'],str)
        selected=[]
        for word in re.finditer(r'\S+',region['text']):
            identifier='SOURCE_'+str(len(anchors)+1).zfill(4)
            literal=region['text'][word.start():word.end()]
            anchor={'id':identifier,'span_id':region['span_id'],'start':word.start(),'end':word.end(),
                    'quote':literal,'source_region_sha256':digest(region),'literal_sha256':digest(literal)}
            anchors.append(anchor);selected.append({'id':identifier,'text':literal})
        sources.append({'span_id':region['span_id'],'text':region['text'],'tokens':selected})
    result=review['model_result']
    assert isinstance(result,dict) and set(result)=={'obligations'}, 'OBLIGATION_MODEL_SCHEMA'
    entries=result['obligations'];assert isinstance(entries,list) and len(entries)==len(units)
    by_id={anchor['id']:anchor for anchor in anchors};verified=[]
    for unit,entry in zip(units,entries):
        assert isinstance(entry,dict) and set(entry)=={'id','verdict','support','reason'}
        assert entry['id']==unit['id'] and entry['verdict']=='PASS', 'OBLIGATION_NOT_SUPPORTED'
        assert isinstance(entry['reason'],str) and entry['reason'].strip()
        refs=entry['support'];assert isinstance(refs,list) and 0<len(refs)<=64
        assert all(isinstance(ref,str) and ref in by_id for ref in refs) and len(set(refs))==len(refs)
        verified.append({**unit,'verdict':'PASS','support':[by_id[ref] for ref in refs],'reason':entry['reason']})
    expected={'version':version,'claim_sha256':digest(text),'source_sha256':digest(regions),
              'obligations':units,'source_tokens_sha256':digest(anchors),'model_result':result,
              'passed':True,'coverage_complete':True,'semantic_acceptance':False,
              'reason':'ALL_SOURCE_OBLIGATIONS_SUPPORTED','verified_obligations':verified}
    assert all(review.get(key)==value for key,value in expected.items()), 'OBLIGATION_RECONSTRUCTION_MISMATCH'
    assert review.get('status')=='SOURCE_SUPPORTED_CANDIDATE' and review.get('metrics',{}).get('finish_reason')=='stop'
    assert review.get('input_sha256')==digest({'claim':claim,'obligations':units,'source_regions':sources}), 'OBLIGATION_INPUT_HASH_MISMATCH'
