"""Request-scoped identity and book authorization, including credential restrictions."""
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import hmac
from fastapi import Header, HTTPException
from editor.config import connection,secret


@dataclass(frozen=True)
class Principal:
    user_id: str
    display_name: str
    role: str
    system_role: str
    key_id: str|None=None
    work_ids: tuple[str,...]|None=None


current: ContextVar[Principal|None]=ContextVar('editor_principal',default=None)
write_scope: ContextVar[bool]=ContextVar('editor_write_scope',default=False)
touched_works: ContextVar[frozenset[str]]=ContextVar('editor_touched_works',default=frozenset())


def principal():
    value=current.get()
    if value is None:raise HTTPException(401,'Oturum gerekli')
    return value


def actor_id():return principal().user_id


def idempotency_actor():
    p=principal()
    return p.user_id+(':'+p.key_id if p.key_id else '')


def admin():
    p=principal()
    if p.role!='ADMIN' or p.system_role!='ADMIN' or p.work_ids is not None:
        raise HTTPException(403,'Yönetici yetkisi gerekli')
    return p


def require_write():
    if principal().role not in ('ADMIN','EDITOR'):raise HTTPException(403,'Yazma yetkisi gerekli')


def resolve(authorization):
    if not authorization.startswith('Bearer '):raise HTTPException(401,'Oturum gerekli')
    token=authorization[7:]
    bootstrap=hmac.compare_digest(token,secret('api_token'))
    with connection() as db:
        if bootstrap:
            user=db.execute("SELECT * FROM editor.users WHERE id='installation-operator' AND enabled").fetchone()
            if user:return Principal(user['id'],user['display_name'],'ADMIN',user['system_role'])
        elif 32<=len(token)<=256:
            row=db.execute('''SELECT k.id,k.user_id,k.role,k.work_ids,u.display_name,u.system_role
              FROM editor.access_keys k JOIN editor.users u ON u.id=k.user_id
              WHERE k.token_hash=%s AND k.revoked_at IS NULL AND u.enabled''',
              (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            if row:
                return Principal(row['user_id'],row['display_name'],row['role'],row['system_role'],
                                 str(row['id']),tuple(map(str,row['work_ids'])) if row['work_ids'] is not None else None)
    raise HTTPException(401,'Oturum doğrulanamadı',headers={'WWW-Authenticate':'Bearer'})


async def authorize(authorization:str=Header(default='')):
    current.set(await asyncio.to_thread(resolve,authorization))


def visible_works(db):
    p=principal()
    return [r['id'] for r in db.execute('''SELECT w.id FROM editor.works w
      WHERE (%s OR w.owner_id=%s OR EXISTS(SELECT 1 FROM editor.book_access a WHERE a.work_id=w.id AND a.user_id=%s))
      AND (%s::uuid[] IS NULL OR w.id=ANY(%s::uuid[]))''',
      (p.role=='ADMIN' and p.system_role=='ADMIN',p.user_id,p.user_id,
       list(p.work_ids) if p.work_ids is not None else None,list(p.work_ids) if p.work_ids is not None else None)).fetchall()]


def ensure_work(db,work,write=None):
    p=principal();writing=write_scope.get() if write is None else write
    touched_works.set(touched_works.get()|{str(work)})
    if writing:require_write()
    if p.work_ids is not None and str(work) not in p.work_ids:raise HTTPException(404,'Kayıt bulunamadı')
    row=db.execute('''SELECT w.owner_id,a.role FROM editor.works w LEFT JOIN editor.book_access a
        ON a.work_id=w.id AND a.user_id=%s WHERE w.id=%s''',(p.user_id,work)).fetchone()
    if not row:raise HTTPException(404,'Kayıt bulunamadı')
    if p.role=='ADMIN' and p.system_role=='ADMIN':return
    if row['owner_id']==p.user_id:return
    if row['role'] is None:raise HTTPException(404,'Kayıt bulunamadı')
    if writing and row['role']!='EDITOR':raise HTTPException(403,'Bu kitap için yazma yetkisi gerekli')
