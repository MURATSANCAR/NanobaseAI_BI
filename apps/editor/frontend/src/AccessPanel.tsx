import React, { useEffect, useRef, useState } from 'react';

export function AccessPanel({token,works}:{token:string;works:{id:string;title:string}[]}) {
  const [users,setUsers]=useState<any[]>([]),[keys,setKeys]=useState<any[]>([]);
  const [name,setName]=useState(''),[user,setUser]=useState(''),[label,setLabel]=useState('');
  const [role,setRole]=useState('READER'),[book,setBook]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[secret,setSecret]=useState('');
  const controller=useRef(new AbortController());
  useEffect(()=>()=>controller.current.abort(),[]);
  async function api(path:string,body?:object,key?:string) {
    const r=await fetch('/v1/access'+path,{method:body?'POST':'GET',signal:controller.current.signal,
      headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json','Idempotency-Key':key!}:{})},
      ...(body?{body:JSON.stringify(body)}:{})});
    const result=await r.json();if(!r.ok)throw new Error(`İşlem tamamlanamadı (${r.status}): ${result.detail??''}`);return result;
  }
  async function all(path:string) {
    let out:any[]=[];
    for(let offset=0;;offset+=100){const r=await api(path+`?offset=${offset}&limit=100`);out.push(...r.items);if(!r.has_more)return out;}
  }
  async function refresh(){const [u,k]=await Promise.all([all('/users'),all('/keys')]);setUsers(u);setKeys(k);setUser(previous=>previous||u[0]?.id||'');}
  useEffect(()=>{refresh().catch(e=>{if(!controller.current.signal.aborted)setError(e.message);});},[]);
  async function action(fn:()=>Promise<void>){setBusy(true);setError('');try{await fn();await refresh();}catch(e){if(!controller.current.signal.aborted)setError((e as Error).message);}finally{if(!controller.current.signal.aborted)setBusy(false);}}
  return <details className="upload-book access-panel">
    <summary>Kullanıcı ve kitap erişimi</summary>
    <p className="hint">Yalnız yönetici bu alanı kullanabilir. Anahtar kapsamı, kullanıcının kitap yetkisini genişletmez.</p>
    <form onSubmit={e=>{e.preventDefault();void action(async()=>{await api('/users',{display_name:name,system_role:'MEMBER'},crypto.randomUUID());setName('');});}}>
      <label>Kullanıcı adı<input required value={name} maxLength={200} onChange={e=>setName(e.target.value)} /></label>
      <button disabled={busy}>Kullanıcı oluştur</button>
    </form>
    <form onSubmit={e=>{e.preventDefault();void action(async()=>{const r=await api('/keys',{user_id:user,label,role,work_ids:book?[book]:null},crypto.randomUUID());setSecret(r.token??'');});}}>
      <label>Erişim verilecek kullanıcı<select value={user} onChange={e=>setUser(e.target.value)}>{users.filter(u=>u.enabled).map(u=><option key={u.id} value={u.id}>{u.display_name}</option>)}</select></label>
      <label>Anahtar açıklaması<input required maxLength={200} value={label} onChange={e=>setLabel(e.target.value)} /></label>
      <label>Erişim düzeyi<select value={role} onChange={e=>setRole(e.target.value)}><option value="READER">Okuyucu</option><option value="EDITOR">Editör</option></select></label>
      <label>Kitap kapsamı<select value={book} onChange={e=>setBook(e.target.value)}><option value="">Kullanıcının erişebildiği kitaplar</option>{works.map(w=><option key={w.id} value={w.id}>{w.title}</option>)}</select></label>
      <button disabled={busy||!user}>Erişim anahtarı oluştur</button>
    </form>
    {secret&&<div><p>Bu anahtar yalnız bu oluşturma cevabında gösterilir. Güvenli bir yerde saklayın.</p><label>Yeni erişim anahtarı<input type="password" readOnly value={secret} autoComplete="off" /></label><button onClick={()=>{navigator.clipboard.writeText(secret).catch(()=>setError('Kopyalanamadı; anahtar alanından kopyalayabilirsiniz.'));}}>Anahtarı kopyala</button><button onClick={()=>setSecret('')}>Anahtarı ekrandan kaldır</button></div>}
    {book&&<button disabled={busy||!user} onClick={()=>void action(async()=>{await api('/grants',{work_id:book,user_id:user,role},crypto.randomUUID());})}>Seçili kitap için yetki ver</button>}
    {book&&<button disabled={busy||!user} onClick={()=>void action(async()=>{await api('/grants',{work_id:book,user_id:user,role:'REVOKE'},crypto.randomUUID());})}>Seçili kitap yetkisini kaldır</button>}
    <div className="access-list">{keys.map(k=><article key={k.id}><p>{k.label} · {k.role==='READER'?'Okuyucu':k.role==='EDITOR'?'Editör':'Yönetici'} · {k.revoked_at?'İptal edilmiş':'Etkin'}</p>{!k.revoked_at&&<button disabled={busy} onClick={()=>void action(async()=>{await api('/keys/'+k.id+'/revoke',{reason:'Yönetici arayüzünden erişim kapatıldı'},crypto.randomUUID());})}>Anahtarı iptal et</button>}</article>)}</div>
    {error&&<p className="error" role="alert">{error}</p>}
  </details>;
}
