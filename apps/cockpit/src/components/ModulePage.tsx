import { useState } from 'react';
import { ZekiWelcome } from './ZekiWelcome';
import inventory from '../lib/modules.json';
import type { View } from './Sidebar';

export const moduleLabel = (title: string) => title.replace(/^M\d+\s*[:—–-]\s*/u, '').replace(/^[^\p{L}\p{N}]+/u, '');
export const groupLabel = (title: string) => moduleLabel(title).replace(/^[A-L] — /, '').replace(/\s*\(M.*\)$/, '').replace(/^M\d+\s*[:—–-]\s*/u, '');

export const moduleGroups = inventory.groups;
export const modules = moduleGroups.flatMap(g => g.modules);
export function ModulePage({ id, onView }: { id: string; onView: (view: View) => void }) {
  const [tab, setTab] = useState('scope');
  const item = modules.find(m => m.id === id);
  if (!item) return <div className="card p-6">Modül bulunamadı.</div>;
  if (id === 'home') return <div className="space-y-5">
    <ZekiWelcome onOpenDesk={() => onView('desk')} />
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{moduleGroups.filter(g => g.modules.some(m => !['home','map','roadmap'].includes(m.id))).map(g => <section key={groupLabel(g.title)} className="card p-5"><h2 className="font-display text-lg font-semibold">{groupLabel(g.title)}</h2><div className="mt-3 space-y-1">{g.modules.map(m => <button key={m.id} onClick={() => onView(`module:${m.id}`)} className="block w-full rounded-lg px-2 py-2 text-left text-sm text-ink-muted hover:bg-brand-soft hover:text-brand-deep">{moduleLabel(m.title)}</button>)}</div></section>)}</div>
  </div>;
  return <div className="space-y-4">
    <header className="card p-6"><button className="text-xs text-brand underline" onClick={() => onView('module:home')}>Tüm çalışma alanları</button><h1 className="mt-3 font-display text-2xl font-semibold">{moduleLabel(item.title)}</h1><p className="mt-3 inline-block rounded-full bg-brand-soft px-3 py-1 text-xs text-brand-deep">{['map','roadmap'].includes(id) ? 'Planlama görünümü' : 'Kapsam hazır · İşlevler geliştirme aşamasında'}</p><p className="mt-3 text-sm text-ink-muted">Bu sayfa planlanan kapsamı gösterir. Buradaki başlıklar, tamamlanmış veya veriyle çalışan özellikler anlamına gelmez.</p>{['M45','M46'].includes(id) && <button onClick={() => onView('desk')} className="mt-4 rounded-xl bg-brand px-4 py-2 text-sm text-white">Mevcut Finans & Bütçe Masası’nı aç</button>}</header>
    {id === 'map' ? <section className="card p-6"><h2 className="font-semibold">Belgelerde belirtilen bütçe hedefi akışı</h2><p className="mt-2 text-sm text-ink-muted">M46 bütçe ve satış hedefleri, yeni kitap pazarlaması (M15), backlist pazarlaması (M17) ve ilk dağılım (M29) için girdi sağlar. Bu gösterim tüm bağımlılık haritası değildir.</p><div className="mt-4 flex flex-wrap gap-3">{['M46','M15','M17','M29'].map(mid => <button className="rounded-xl border border-line p-3 text-sm" key={mid} onClick={() => onView(`module:${mid}`)}>{moduleLabel(modules.find(m => m.id === mid)?.title ?? '')}</button>)}</div></section>
      : id === 'roadmap' ? <section className="card p-6"><h2 className="font-semibold">Uygulama yol haritası</h2><p className="mt-2 text-sm text-ink-muted">Modül envanteri menüye aktarıldı. Modül bazlı teslim tarihi, sorumlu ve kabul ölçütleri henüz bu uygulamaya bağlanmadı.</p></section>
      : <section className="card p-5"><div className="flex flex-wrap gap-2" role="tablist" aria-label="Modül ayrıntıları">{[['scope','Alt başlıklar ve çıktılar'],['inputs','Girdiler ve kapsam'],['data','Veri kaynakları']].map(([key,label]) => <button key={key} role="tab" aria-selected={tab===key} onClick={() => setTab(key)} className={`rounded-xl px-4 py-2 text-sm ${tab===key?'bg-brand text-white':'bg-page text-ink-muted'}`}>{label}</button>)}</div><div role="tabpanel" className="mt-5 grid gap-3 sm:grid-cols-2">{(tab==='scope'?item.outputSections:tab==='inputs'?item.cards:item.dataSources).map((label,i) => <article key={`${i}-${label}`} className="rounded-xl border border-line p-4"><span className="text-xs text-ink-faint">{String(i+1).padStart(2,'0')}</span><h3 className="mt-2 text-sm font-semibold">{label}</h3></article>)}{(tab==='scope'?item.outputSections:tab==='inputs'?item.cards:item.dataSources).length===0 && <p className="text-sm text-ink-muted">Bu bölümün ayrıntıları henüz envantere işlenmedi.</p>}</div></section>}
  </div>;
}
