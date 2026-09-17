"""Administrator-managed users, scoped keys and explicit book grants."""
import hashlib
import secrets
import uuid
from typing import Literal
from fastapi import APIRouter,Header,HTTPException
from pydantic import BaseModel,Field
from psycopg.types.json import Jsonb
from editor.access import admin,principal,actor_id,ensure_work
from editor.config import connection

router=APIRouter(prefix='/v1')


def audit(db,action,target,detail):
    db.execute('INSERT INTO editor.access_audit(id,actor_id,action,target_id,detail) VALUES (%s,%s,%s,%s,%s)',
               (uuid.uuid4(),actor_id(),action,str(target),Jsonb(detail)))


@router.get('/me')
def me():
    p=principal()
    return {'user_id':p.user_id,'display_name':p.display_name,'role':p.role,
            'can_write':p.role in ('ADMIN','EDITOR'),'can_create_work':p.role in ('ADMIN','EDITOR') and p.work_ids is None,
            'can_manage_access':p.role=='ADMIN' and p.system_role=='ADMIN' and p.work_ids is None,
            'work_scope':list(p.work_ids) if p.work_ids is not None else None}


class User(BaseModel):
    display_name:str=Field(min_length=1,max_length=200)
    system_role:Literal['ADMIN','MEMBER']='MEMBER'


@router.post('/access/users',status_code=201)
def create_user(body:User,idempotency_key:str=Header()):
    admin()
    from editor.book_api import mutate
    def action(db):
        rid=str(uuid.uuid4())
        db.execute('INSERT INTO editor.users(id,display_name,system_role) VALUES (%s,%s,%s)',(rid,body.display_name,body.system_role))
        audit(db,'USER_CREATED',rid,body.model_dump())
        return {'id':rid,**body.model_dump(),'enabled':True}
    return mutate('/access/users',body,idempotency_key,action)


@router.get('/access/users')
def users(offset:int=0,limit:int=50):
    admin()
    if offset<0 or not 1<=limit<=100:raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        rows=db.execute('SELECT id,display_name,system_role,enabled FROM editor.users ORDER BY created_at,id LIMIT %s OFFSET %s',(limit+1,offset)).fetchall()
    return {'items':rows[:limit],'has_more':len(rows)>limit}


class Enabled(BaseModel):
    enabled:bool


@router.post('/access/users/{user_id}/status')
def user_status(user_id:str,body:Enabled,idempotency_key:str=Header()):
    admin()
    if user_id in ('installation-operator',actor_id()) and not body.enabled:raise HTTPException(409,'CANNOT_DISABLE_CURRENT_ADMIN')
    from editor.book_api import mutate
    def action(db):
        row=db.execute('UPDATE editor.users SET enabled=%s WHERE id=%s RETURNING id,enabled',(body.enabled,user_id)).fetchone()
        if not row:raise HTTPException(404,'Kayıt bulunamadı')
        audit(db,'USER_STATUS',user_id,body.model_dump());return row
    return mutate('/access/users/'+user_id+'/status',body,idempotency_key,action)


class Key(BaseModel):
    user_id:str=Field(min_length=1,max_length=100)
    label:str=Field(min_length=1,max_length=200)
    role:Literal['ADMIN','EDITOR','READER']='READER'
    work_ids:list[uuid.UUID]|None=Field(default=None,max_length=100)


@router.post('/access/keys',status_code=201)
def create_key(body:Key,idempotency_key:str=Header()):
    admin()
    if not idempotency_key or len(idempotency_key)>200:raise HTTPException(400,'Idempotency-Key gerekli')
    fingerprint=hashlib.sha256(body.model_dump_json().encode()).hexdigest()
    with connection() as db:
        db.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('access-key:'+actor_id()+':'+idempotency_key,))
        old=db.execute('SELECT id,request_hash FROM editor.access_keys WHERE created_by=%s AND request_key=%s',(actor_id(),idempotency_key)).fetchone()
        if old:
            if old['request_hash']!=fingerprint:raise HTTPException(409,'IDEMPOTENCY_CONFLICT')
            return {'id':str(old['id']),'token':None,'secret_available':False}
        user=db.execute('SELECT system_role FROM editor.users WHERE id=%s AND enabled',(body.user_id,)).fetchone()
        if not user:raise HTTPException(404,'Kayıt bulunamadı')
        if body.role=='ADMIN' and user['system_role']!='ADMIN':raise HTTPException(409,'USER_IS_NOT_ADMIN')
        for work in body.work_ids or []:ensure_work(db,work,write=False)
        token=secrets.token_urlsafe(48);rid=uuid.uuid4()
        db.execute('''INSERT INTO editor.access_keys(id,user_id,label,token_hash,role,work_ids,created_by,request_key,request_hash)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                   (rid,body.user_id,body.label,hashlib.sha256(token.encode()).hexdigest(),body.role,body.work_ids,actor_id(),idempotency_key,fingerprint))
        audit(db,'KEY_CREATED',rid,body.model_dump(mode='json'))
        return {'id':str(rid),'token':token,'secret_available':True}


@router.get('/access/keys')
def keys(offset:int=0,limit:int=50):
    admin()
    if offset<0 or not 1<=limit<=100:raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        rows=db.execute('SELECT id,user_id,label,role,work_ids,created_at,revoked_at FROM editor.access_keys ORDER BY created_at,id LIMIT %s OFFSET %s',(limit+1,offset)).fetchall()
    return {'items':rows[:limit],'has_more':len(rows)>limit}


class Revoke(BaseModel):
    reason:str=Field(min_length=1,max_length=500)


@router.post('/access/keys/{key_id}/revoke')
def revoke(key_id:uuid.UUID,body:Revoke,idempotency_key:str=Header()):
    admin()
    if principal().key_id==str(key_id):raise HTTPException(409,'CANNOT_REVOKE_CURRENT_KEY')
    from editor.book_api import mutate
    def action(db):
        row=db.execute('UPDATE editor.access_keys SET revoked_at=COALESCE(revoked_at,now()) WHERE id=%s RETURNING id,revoked_at',(key_id,)).fetchone()
        if not row:raise HTTPException(404,'Kayıt bulunamadı')
        audit(db,'KEY_REVOKED',key_id,body.model_dump())
        return {'id':str(row['id']),'revoked_at':row['revoked_at'].isoformat()}
    return mutate('/access/keys/'+str(key_id)+'/revoke',body,idempotency_key,action)


class Grant(BaseModel):
    work_id:uuid.UUID
    user_id:str=Field(min_length=1,max_length=100)
    role:Literal['EDITOR','READER','REVOKE']


@router.post('/access/grants')
def grant(body:Grant,idempotency_key:str=Header()):
    admin()
    from editor.book_api import mutate
    def action(db):
        ensure_work(db,body.work_id)
        owner=db.execute('SELECT owner_id FROM editor.works WHERE id=%s',(body.work_id,)).fetchone()['owner_id']
        if body.user_id==owner:raise HTTPException(409,'OWNER_ACCESS_IS_IMPLICIT')
        if not db.execute('SELECT 1 FROM editor.users WHERE id=%s',(body.user_id,)).fetchone():raise HTTPException(404,'Kayıt bulunamadı')
        if body.role=='REVOKE':
            db.execute('DELETE FROM editor.book_access WHERE work_id=%s AND user_id=%s',(body.work_id,body.user_id))
        else:
            db.execute('''INSERT INTO editor.book_access(work_id,user_id,role,granted_by) VALUES (%s,%s,%s,%s)
              ON CONFLICT(work_id,user_id) DO UPDATE SET role=excluded.role,granted_by=excluded.granted_by,updated_at=now()''',
              (body.work_id,body.user_id,body.role,actor_id()))
        audit(db,'BOOK_GRANT',body.work_id,body.model_dump(mode='json'));return body.model_dump(mode='json')
    return mutate('/access/grants',body,idempotency_key,action)


@router.get('/access/grants')
def grants(work_id:uuid.UUID,offset:int=0,limit:int=50):
    admin()
    if offset<0 or not 1<=limit<=100:raise HTTPException(400,'INVALID_PAGINATION')
    with connection() as db:
        ensure_work(db,work_id,write=False)
        rows=db.execute('SELECT user_id,role,granted_by,updated_at FROM editor.book_access WHERE work_id=%s ORDER BY user_id LIMIT %s OFFSET %s',(work_id,limit+1,offset)).fetchall()
    return {'items':rows[:limit],'has_more':len(rows)>limit}
