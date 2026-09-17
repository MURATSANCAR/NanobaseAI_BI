#!/usr/bin/env python3
"""Real operator's scoped credentials against the actual uploaded book and PostgreSQL."""
import hashlib,json,os,subprocess,time,urllib.error,urllib.request,uuid
from pathlib import Path
root=Path(__file__).resolve().parents[1];os.chdir(root)
base=os.environ['EDITOR_VERIFY_BASE_URL'].rstrip('/')
book=None if os.environ.get('EDITOR_ACCESS_FULL_BOOK')=='1' else json.loads((root/'evidence/upload-ui/verification.json').read_text())
operator=(root/'secrets/api_token').read_text().strip()
prefix='real-book-access:'+str(uuid.uuid4())
checks=[];issued=[];succeeded=False


def call(method,path,body=None,key=None,token=operator,expected=200):
    headers={'Authorization':'Bearer '+token}
    if key:headers['Idempotency-Key']=prefix+':'+key
    if isinstance(body,dict):body=json.dumps(body).encode();headers['Content-Type']='application/json'
    try:
        with urllib.request.urlopen(urllib.request.Request(base+('' if path=='/metrics' else '/v1')+path,data=body,headers=headers,method=method),timeout=120) as response:
            code=response.status;result=response.read()
    except urllib.error.HTTPError as exc:code=exc.code;result=exc.read()
    assert code==expected,(path,code,result[:100])
    return json.loads(result)


def sql(query):
    return subprocess.check_output(['docker','compose','exec','-T','postgres','psql','-U','postgres','-d','editor','-Atc',query],text=True).strip()


me=call('GET','/me');assert me['user_id']=='installation-operator' and me['can_manage_access']
generation=None
if book is None:
    generation=json.loads((root/'evidence/source-spans-run.json').read_text())['generation_id']
    ref=json.loads(sql("SELECT json_build_object('work',e.work_id,'version',cv.id,'edition',e.id,'sha',cv.sha256,'bytes',s.manifest->'bytes') FROM editor.generations g JOIN editor.content_versions cv ON cv.id=g.content_version_id JOIN editor.editions e ON e.id=cv.edition_id JOIN editor.source_probes s ON s.sha256=cv.sha256 WHERE g.id='"+generation+"'"))
    upload_id=sql("SELECT id FROM editor.uploads WHERE content_version_id='"+ref['version']+"' ORDER BY created_at DESC LIMIT 1")
    book={'status':{'work_id':str(ref['work']),'content_version_id':str(ref['version'])},'source_sha256':ref['sha'],'source_bytes':ref['bytes'],'upload_id':upload_id}
work=book['status']['work_id'];sha=book['source_sha256']
edition=sql("SELECT edition_id FROM editor.uploads WHERE id='"+book['upload_id']+"'")
source_before=sql("SELECT md5(manifest::text) FROM editor.source_probes WHERE sha256='"+sha+"'")
reviews_before=sql('SELECT count(*) FROM editor.reviews')
records_before=sql("SELECT md5(string_agg(id::text||data::text,'' ORDER BY id)) FROM editor.records")
try:
    for name,role,scope in [('reader','READER',[work]),('no_books','READER',[]),('editor','EDITOR',[work])]:
        body={'user_id':me['user_id'],'label':'Gerçek kitap erişim kabulü: '+name,'role':role,'work_ids':scope}
        created=call('POST','/access/keys',body,name,expected=201)
        assert created['token'] and created['secret_available'];issued.append(created)
        duplicate=call('POST','/access/keys',body,name,expected=201)
        assert duplicate['id']==created['id'] and duplicate['token'] is None
        token_hash=sql("SELECT token_hash FROM editor.access_keys WHERE id='"+created['id']+"'")
        assert token_hash==hashlib.sha256(created['token'].encode()).hexdigest()
        created['name']=name
    reader,empty,editor=[item['token'] for item in issued]
    assert call('GET','/me',token=reader)['can_write'] is False
    assert [r['id'] for r in call('GET','/works',token=reader)['items']]==[work]
    assert call('GET','/source-probes/'+sha,token=reader)['sha256']==sha
    assert call('GET','/works',token=empty)['items']==[]
    assert call('GET','/uploads',token=empty)['items']==[]
    for path in ('/source-probes/'+sha,'/works/'+work+'/analyses','/uploads/'+book['upload_id']):
        call('GET',path,token=empty,expected=404)
    for path in ('/system','/metrics','/model-services','/access/users','/access/keys'):
        call('GET',path,token=reader,expected=403)
    body={'expected_bytes':book['source_bytes'],'expected_sha256':sha}
    call('POST','/editions/'+edition+'/uploads',body,'denied-upload',reader,403)
    call('POST','/content-versions/'+book['status']['content_version_id']+'/analyses',{'purpose':'validation'},'denied-analysis',reader,403)
    call('POST','/access/keys',{'user_id':me['user_id'],'label':'not-created','role':'ADMIN'},'denied-admin',reader,403)
    call('POST','/editions/'+edition+'/verified-sources',{'sha256':sha},'denied-hash-attachment',editor,403)
    call('POST','/access/grants',{'work_id':work,'user_id':me['user_id'],'role':'REVOKE'},'owner-grant',expected=409)
    if generation:
        evidence=call('GET','/generations/'+generation+'/evidence?limit=100',token=reader)['items']
        assert len(evidence)==48
        spans=call('GET','/generations/'+generation+'/source_spans?limit=1',token=reader)
        assert spans['total']==int(sql("SELECT count(*) FROM editor.records WHERE generation_id='"+generation+"' AND kind='source_spans'"))
        for path in ('/generations/'+generation,'/generations/'+generation+'/source_spans','/evidence/'+evidence[0]['id'],'/visuals/'+evidence[0]['id'],'/reviews?generation_id='+generation):
            call('GET',path,token=empty,expected=404)
        call('POST','/questions',{'generation_id':generation,'question':'Kitabın konusu nedir?','mode':'editor_preview'},'reader-preview',reader,403)
        call('POST','/generations/'+generation+'/activate',{'purpose':'validation'},'reader-activate',reader,403)
    # Authorized write: the exact original PDF, same actual edition and content version.
    upload=call('POST','/editions/'+edition+'/uploads',body,'editor-upload',editor,201)
    original=Path(os.environ['EDITOR_VERIFY_PDF']).read_bytes();assert hashlib.sha256(original).hexdigest()==sha
    call('PUT',upload['upload_url'].removeprefix('/v1'),original,token=editor)
    call('POST','/uploads/'+upload['id']+'/complete',{'confirm':True},'editor-complete',editor,202)
    for _ in range(90):
        state=call('GET','/uploads/'+upload['id'],token=editor)
        if state['status']=='COMPLETED':break
        assert state['status']=='PARSING';time.sleep(2)
    else:raise RuntimeError('SCOPED_UPLOAD_DID_NOT_COMPLETE')
    assert state['content_version_id']==book['status']['content_version_id']
    # No plaintext keys in application audit or idempotency storage.
    stored=sql("SELECT string_agg(detail::text,'') FROM editor.access_audit")+sql("SELECT string_agg(response::text,'') FROM editor.idempotency")
    assert all(item['token'] not in stored for item in issued)
    assert sql("SELECT md5(manifest::text) FROM editor.source_probes WHERE sha256='"+sha+"'")==source_before
    assert sql('SELECT count(*) FROM editor.reviews')==reviews_before
    assert sql("SELECT md5(string_agg(id::text||data::text,'' ORDER BY id)) FROM editor.records")==records_before
    assert sql('SELECT count(*) FROM editor.users')=='1' # Existing real operator; no fictitious user accounts.
    # UI verifier receives its own short-lived key via a private local file, never stdout.
    fd=os.open(root/'secrets/access-verification-reader',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:stream.write(reader)
    report={'api':base,'release':call('GET','/system')['release'],'work_id':work,'generation_id':generation,'source_sha256':sha,'credential_ids':[i['id'] for i in issued],
            'scoped_read':'PASS','out_of_scope_404':'PASS','reader_writes_403':'PASS','admin_routes_403':'PASS',
            'scoped_editor_real_upload':'PASS','hashed_keys_only':True,'one_time_secret':True,
            'source_manifest_unchanged':True,'analysis_records_unchanged':True,'editorial_decisions_written':0,'real_user_accounts':1,'semantic_acceptance':False}
    (root/'evidence/access-verification.json').write_text(json.dumps(report,indent=2));succeeded=True
    print(json.dumps(report,indent=2))
finally:
    # Keep only the reader credential until the browser check; revoke all others now.
    for item in issued:
        if item.get('name')!='reader' or not succeeded:
            call('POST','/access/keys/'+item['id']+'/revoke',{'reason':'Gerçek API kabul kontrolü tamamlandı'},'revoke-'+item['id'])
            call('GET','/me',token=item['token'],expected=401)
