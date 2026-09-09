import { useState } from 'react';
import { BookOpen, Menu, X, Search } from 'lucide-react';
import { moduleGroups } from './ModulePage';

export type View = 'desk' | 'catalog' | 'review' | `module:${string}`;
export function Sidebar({ engineOk, modelCount, view, onView, waiting = 0 }: { engineOk: boolean | null; modelCount: number | null; view: View; onView: (v: View) => void; waiting?: number }) {
  const [mobile, setMobile] = useState(false);
  const [search, setSearch] = useState('');
  const [open, setOpen] = useState<Record<string,boolean>>({});
  const choose = (v: View) => { onView(v); setMobile(false); };
  const button = (v: View, text: string) => <button key={v} type="button" aria-current={view===v?'page':undefined} onClick={() => choose(v)} className={`block w-full rounded-lg px-3 py-2 text-left text-[13px] leading-relaxed ${view===v?'bg-brand text-white':'text-ink-muted hover:bg-brand-soft hover:text-brand-deep'}`}>{text}</button>;
  return <>
    <button className="fixed right-3 top-3 z-40 rounded-xl border border-line bg-white p-3 shadow-card lg:hidden" aria-label="Modül menüsünü aç" onClick={() => setMobile(true)}><Menu size={20}/></button>
    {mobile && <button className="fixed inset-0 z-40 bg-black/30 lg:hidden" aria-label="Menüyü kapat" onClick={() => setMobile(false)}/>}
    <aside className={`${mobile?'fixed inset-y-0 left-0 z-50 flex':'hidden'} w-[290px] max-w-[90vw] shrink-0 flex-col border-r border-line bg-rail lg:sticky lg:top-0 lg:flex lg:h-screen`}>
      <header className="flex items-center gap-3 p-5"><span className="rounded-xl bg-brand p-3 text-white"><BookOpen size={22}/></span><div><strong className="font-display text-xl">TİMAŞ AI</strong><p className="text-[9px] tracking-widest text-ink-muted">KURUMSAL ÇALIŞMA PLATFORMU</p></div><button aria-label="Menüyü kapat" className="ml-auto lg:hidden" onClick={() => setMobile(false)}><X size={18}/></button></header>
      <label className="mx-4 mb-3 flex items-center gap-2 rounded-xl border border-line bg-white p-2"><Search size={15}/><input aria-label="Modül ara" placeholder="Modül veya kod ara…" value={search} onChange={e => setSearch(e.target.value)} className="min-w-0 w-full bg-transparent text-xs outline-none"/></label>
      <nav aria-label="Modüller" className="scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto px-3 pb-4">
        {moduleGroups.map(group => {
          const children=group.modules.filter(m => `${group.title} ${m.title}`.toLocaleLowerCase('tr-TR').includes(search.toLocaleLowerCase('tr-TR')));
          if (!children.length) return null;
          if (group.modules.length===1) return button(`module:${children[0].id}`,children[0].title.replace(/^[^\p{L}\p{N}]+/u,''));
          const expanded=search.length>0 || (open[group.title] ?? children.some(m => view===`module:${m.id}`));
          return <section key={group.title}><button type="button" aria-expanded={expanded} onClick={() => setOpen(prev => ({...prev,[group.title]:!expanded}))} className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs font-semibold text-ink"><span>{group.title.replace(/^[A-L] — /,'').replace(/\s*\(M.*\)$/,'')}</span><span className="ml-2 text-ink-faint">{expanded?'−':'+'}</span></button>{expanded && <div className="ml-2 space-y-1 border-l border-line pl-2">{children.map(m => button(`module:${m.id}`,m.title))}</div>}</section>;
        })}
        {search && !moduleGroups.some(g => g.modules.some(m => `${g.title} ${m.title}`.toLocaleLowerCase('tr-TR').includes(search.toLocaleLowerCase('tr-TR')))) && <p className="p-3 text-xs text-ink-muted">Eşleşen modül yok.</p>}
        <div className="border-t border-line pt-3"><p className="eyebrow px-3 pb-2">Mevcut araçlar</p>{button('desk','Finans & Bütçe Masası')}{button('catalog','Veri Sözlüğü')}{button('review',`İş Sözlüğünü Geliştir · ${waiting}`)}</div>
      </nav>
      <footer className="border-t border-line px-5 pb-14 pt-3 text-[11px] text-ink-muted"><span className={engineOk?'text-ok':'text-ink-faint'}>●</span> Semantik Motor {engineOk?'Aktif':engineOk===false?'Erişilemiyor':'Kontrol ediliyor'}<p className="mt-1">{modelCount ?? '—'} veri modeli</p></footer>
    </aside>
  </>;
}
