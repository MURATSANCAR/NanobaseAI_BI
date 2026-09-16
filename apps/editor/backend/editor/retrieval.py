"""Generation-filtered vector retrieval plus local BM25 and reranking."""
import math
import re
from collections import Counter
import httpx
from psycopg.types.json import Jsonb
from editor.config import connection
from editor.book_store import get_records, identifier, fence, save_record

COLLECTION='editor_bge_m3_1024_v1'


def embed(text):
    with httpx.Client(timeout=180,trust_env=False) as client:
        r=client.post('http://embedding:8080/v1/embeddings',json={'model':'editor-embedding','input':text})
        r.raise_for_status(); vector=r.json()['data'][0]['embedding']
    if len(vector)!=1024: raise RuntimeError('EMBEDDING_DIMENSION_MISMATCH')
    return vector


def build_index(job):
    gen=job['generation_id']
    with httpx.Client(timeout=120,trust_env=False) as client:
        r=client.get(f'http://qdrant:6333/collections/{COLLECTION}')
        if r.status_code==404:
            client.put(f'http://qdrant:6333/collections/{COLLECTION}',json={'vectors':{'size':1024,'distance':'Cosine'}}).raise_for_status()
        else: r.raise_for_status()
        for evidence in get_records(gen,'evidence'):
            key=evidence['record_key']; d=evidence['data']
            # A colored activity panel can have good embedded text but poor OCR.
            # Preserve both candidates, including the source labels, for retrieval.
            text='OCR adayı:\n'+d['ocr_text']+'\nPDF metin katmanı adayı:\n'+d['text_layer']
            if not text.strip(): text='Görsel sayfa '+str(d['pdf_page'])
            with connection() as db:
                fence(db,job)
                rid=save_record(db,gen,'passages',key,{'text':text,'evidence_refs':[str(evidence['id'])],'pdf_page':d['pdf_page']},True)
                delivered=db.execute('SELECT delivered_at FROM editor.outbox WHERE id=%s',(rid,)).fetchone()['delivered_at']
            if delivered: continue
            vector=embed(text)
            client.put(f'http://qdrant:6333/collections/{COLLECTION}/points',params={'wait':'true'},json={'points':[
              {'id':rid,'vector':vector,'payload':{'generation_id':str(gen),'evidence_id':str(evidence['id'])}}]}).raise_for_status()
            with connection() as db:
                fence(db,job)
                db.execute('UPDATE editor.outbox SET delivered_at=now() WHERE id=%s',(rid,))
        r=client.post(f'http://qdrant:6333/collections/{COLLECTION}/points/count',json={'exact':True,'filter':{'must':[{'key':'generation_id','match':{'value':str(gen)}}]}})
        r.raise_for_status()
        if r.json()['result']['count']!=len(get_records(gen,'evidence')):
            raise RuntimeError('INDEX_COUNT_MISMATCH')


def tokens(text): return re.findall(r'\w+',text.casefold())


def search(gen,question):
    rows=get_records(gen,'passages'); by_id={str(r['id']):r for r in rows}
    counts=[Counter(tokens(r['data']['text'])) for r in rows]
    average=sum(sum(c.values()) for c in counts)/max(1,len(counts)); q=tokens(question)
    sparse=[]
    for row,c in zip(rows,counts):
        score=0
        for term in q:
            freq=c[term]; df=sum(term in other for other in counts)
            idf=math.log(1+(len(rows)-df+0.5)/(df+0.5))
            score+=idf*freq*2.2/(freq+1.2*(0.25+0.75*sum(c.values())/max(1,average)))
        sparse.append((str(row['id']),score))
    with httpx.Client(timeout=180,trust_env=False) as client:
        r=client.post(f'http://qdrant:6333/collections/{COLLECTION}/points/search',json={'vector':embed(question),'limit':12,'with_payload':True,
          'filter':{'must':[{'key':'generation_id','match':{'value':str(gen)}}]}})
        r.raise_for_status(); dense=r.json()['result']
        ranking=Counter()
        for ordered in ([p['id'] for p in dense],[p[0] for p in sorted(sparse,key=lambda x:-x[1])[:12]]):
            for rank,rid in enumerate(ordered):
                if rid in by_id: ranking[rid]+=1/(60+rank+1)
        candidates=[by_id[rid] for rid,_ in ranking.most_common(12)]
        r=client.post('http://reranker:8080/v1/rerank',json={'model':'editor-reranker','query':question,'documents':[r['data']['text'] for r in candidates]})
        r.raise_for_status(); ranked=r.json(); ranked=ranked.get('results',ranked.get('data',[]))
        return [candidates[x['index']] for x in sorted(ranked,key=lambda x:-x.get('relevance_score',x.get('score',0)))[:5]]
