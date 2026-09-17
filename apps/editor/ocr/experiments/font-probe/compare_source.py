import json,os,subprocess,urllib.request,unicodedata
from pathlib import Path
root=Path('/data/nanobaseai/editor');os.chdir(root);gen=json.loads((root/'evidence/source-spans-run.json').read_text())['generation_id']
font=json.loads((root/'evidence/font-gsub-character-probe-v2.json').read_text())
mapping={}
for page in font['page_results']:
 for item in page['characters']:
  candidates=item['candidates'];code=str(item['original_codepoint'])
  if len(candidates)==1:
   if code in mapping:assert mapping[code]==candidates[0]
   mapping[code]=candidates[0]
headers={'Authorization':'Bearer '+(root/'secrets/api_token').read_text().strip()};rows=[]
for page in range(44,49):
 with urllib.request.urlopen(urllib.request.Request(f'http://127.0.0.1:8810/v1/generations/{gen}/source_spans?pdf_page={page}&limit=100',headers=headers)) as response:r=json.load(response)
 assert not r['has_more'];rows+=r['items']
code="""import json,sys,unicodedata
from editor.book_store import get_records,source_for
from editor.source_pipeline import optical_verdict
x=json.load(sys.stdin)
assert source_for(x['gen'])['sha256']==x['source_sha256'],'FONT_SOURCE_SCOPE_MISMATCH'
rows=[r for r in get_records(x['gen'],'source_spans') if 44<=r['data']['pdf_page']<=48]
assert json.loads(json.dumps(rows,default=str))==x['rows'],'API_PG_MISMATCH'
result=[]
for row in rows:
 d=row['data'];original=d['pdf_text'];candidate=''.join(chr(x['mapping'].get(str(ord(c)),ord(c))) for c in original)
 usable=bool(d['pdf_word_regions']) and not any(unicodedata.category(c) in ('Co','Cs') or c=='\ufffd' for c in candidate)
 v=optical_verdict({'text':d['raw_text'],'score':d['score'],'region_text':d['region_text'],'region_score':d['region_score']},d['secondary_text'],candidate,usable,d.get('reread_measurement'))
 result.append({'page':d['pdf_page'],'id':str(row['id']),'baseline':d['status'],'candidate':v,'native_before':d['pdf_usable'],'native_after':usable,'changed':original!=candidate,'font_recovered_text':candidate,'source_text_unchanged':d['raw_text']})
print(json.dumps(result,ensure_ascii=False))
"""
result=json.loads(subprocess.check_output(['docker','compose','exec','-T','api','python','-c',code],input=json.dumps({'gen':gen,'rows':rows,'mapping':mapping,'source_sha256':font['source_sha256']}),text=True))
summary={'generation_id':gen,'regions':len(result),'native_newly_usable':sum(not r['native_before'] and r['native_after'] for r in result),'improved':sum(r['baseline']=='NEEDS_REVIEW' and r['candidate']['status']=='TEXT_AGREED' for r in result),'new_conflicts':sum(r['baseline']=='TEXT_AGREED' and r['candidate']['status']=='NEEDS_REVIEW' for r in result),'api_pg_equal':True,'source_writes':0,'semantic_acceptance':False}
(root/'evidence/font-recovery-source-comparison.json').write_text(json.dumps({'summary':summary,'comparisons':result},ensure_ascii=False,indent=2));print(json.dumps(summary))
