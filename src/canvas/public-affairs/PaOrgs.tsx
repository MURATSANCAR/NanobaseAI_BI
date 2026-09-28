import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Building2, NotebookPen, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { useDebounced } from '../editorial/kit';
import { HeatPill, daysAgo, fmtDay } from '../editorial/authors/shared';
import { fmtInt, paApi } from './api';
import { NoteForm, OrgForm } from './forms';
import { BASE, Block, Empty, PaFrame, StageBar, usePaMeta } from './parts';

/** Kurumlar: MEB, okul, üniversite, belediye, kaymakamlık, valilik (CRM ziyaret yerlerinden) ve Diyanet, kütüphane, STK
 *  (elle). Kurum kartında CRM'deki öğrenci/öğretmen/kitap sayısı, kurumdaki kişiler, projeler ve notlar. */

export default function PaOrgs() {
  const [params, setParams] = useSearchParams();
  const meta = usePaMeta();
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const [kind, setKind] = useState('');
  const [newOrg, setNewOrg] = useState(false);
  const open = params.get('kurum');
  const setOpen = (id: string | null) => {
    const p = new URLSearchParams(params);
    if (id) p.set('kurum', id);
    else p.delete('kurum');
    setParams(p, { replace: true });
  };
  const list = useQuery({ queryKey: ['pa', 'orgs', dq, kind], queryFn: () => paApi.orgs({ q: dq, kind }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });

  return (
    <PaFrame
      title="Kurumlar"
      lead="İlişki yürüttüğümüz kurumlar. Okul, üniversite, Milli Eğitim, belediye, kaymakamlık ve valilik CRM ziyaret yerlerinden bağlanır; Diyanet, kütüphane ve STK gibi CRM'de ayrı tipi olmayan kurumlar elle açılır."
      source={list.data ? `${fmtInt(list.data.total)} kurum kartı` : 'Portal + CRM'}
      aside={
        meta.data?.me.canEdit ? (
          <button type="button" className={`${btnPrimary} w-full lg:w-auto`} onClick={() => setNewOrg(true)}>
            <Building2 aria-hidden className="h-4 w-4" />
            Yeni kurum
          </button>
        ) : undefined
      }
    >
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_380px] lg:gap-4">
        <div className="flex min-w-0 flex-col gap-3">
          <div className="glass-panel flex flex-col gap-2 rounded-2xl p-3 shadow-glass-float sm:flex-row">
            <div className="relative min-w-0 flex-1">
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
              <input aria-label="Kurum ara" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kurum adı ya da il" className={`${field} pl-9`} />
            </div>
            <select aria-label="Tür" value={kind} onChange={(e) => setKind(e.target.value)} className={`${field} sm:w-52`}>
              <option value="">Bütün türler</option>
              {(meta.data?.orgKinds ?? []).map((k) => (
                <option key={k.key} value={k.key}>
                  {k.label}
                </option>
              ))}
            </select>
          </div>
          {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
          {list.isLoading && <Loading />}
          {list.data &&
            (list.data.items.length === 0 ? (
              <Empty title="Kurum kartı yok">«Yeni kurum» ile CRM ziyaret yerlerinden bir kurum alın.</Empty>
            ) : (
              <ul className="grid gap-2 md:grid-cols-2">
                <li className="flex items-center gap-1 text-[11.5px] text-canvas-muted md:col-span-2">Kurum başına kişi ve açık proje<SqlInfo k={list.data.kaynaklar} alan="items" label="Kurumlar" /></li>
                {list.data.items.map((o) => (
                  <li key={o.id}>
                    <button type="button" onClick={() => setOpen(o.id)} className="glass-panel flex h-full w-full flex-col gap-1 rounded-2xl p-3 text-left shadow-glass-float transition-transform duration-150 ease-out active:scale-[0.98]">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="min-w-0 break-words text-[14px] font-extrabold">{o.name}</span>
                        <Pill tone="muted">{o.kindLabel}</Pill>
                        {o.crmVisitPlaceId && <Pill tone="violet">CRM</Pill>}
                      </div>
                      <div className="text-[12px] text-canvas-muted">
                        {[o.city, `${fmtInt(o.people ?? 0)} kişi`, `${fmtInt(o.openProjects ?? 0)} açık proje`].filter(Boolean).join(' · ')}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            ))}
        </div>
        <CityStats />
      </div>
      <OrgForm open={newOrg} onClose={() => setNewOrg(false)} onSaved={(id) => setOpen(id)} />
      <OrgSheet id={open} onClose={() => setOpen(null)} />
    </PaFrame>
  );
}

/** İl × kurum tipi: CRM ziyaret yerlerindeki kurum sayısı ve öğrenci toplamı (öğrenci sayısı yazılmamış kurum ayrıca). */
function CityStats() {
  const meta = usePaMeta();
  const [il, setIl] = useState('');
  const [tip, setTip] = useState(1);
  const cities = useQuery({ queryKey: ['pa', 'crm-cities'], queryFn: paApi.crmCities, enabled: ENGINE_ENABLED, staleTime: 30 * 60_000 });
  const stats = useQuery({ queryKey: ['pa', 'city-stats', il, tip], queryFn: () => paApi.cityStats(il, tip), enabled: ENGINE_ENABLED && !!il });
  return (
    <Block title="İl istatistiği" info={<SqlInfo k={stats.data?.kaynaklar} alan="places" label="İl istatistiği" />} help="CRM ziyaret yerlerinden (yalnız okuma). Proje teklifinde hedef okul ve öğrenci sayısı buradan gelir.">
      <div className="grid gap-2 text-[12.5px]">
        <label className="block">
          <span className={label}>İl</span>
          <select value={il} onChange={(e) => setIl(e.target.value)} className={`${field} mt-1`}>
            <option value="">Seçin</option>
            {(cities.data?.items ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className={label}>Kurum tipi</span>
          <select value={tip} onChange={(e) => setTip(Number(e.target.value))} className={`${field} mt-1`}>
            {(meta.data?.kurumTipi ?? []).map((k) => (
              <option key={k.key} value={k.key}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {cities.error && <Note tone="err">{errText(cities.error, 'CRM okunamadı.')}</Note>}
      {stats.error && <Note tone="err">{errText(stats.error, 'CRM okunamadı.')}</Note>}
      {stats.data && (
        <dl className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-xl bg-white/70 p-2.5">
            <dt className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{stats.data.kurumTipiLabel ?? 'Kurum'}</dt>
            <dd className="font-mono text-[22px] font-bold tabular-nums">{fmtInt(stats.data.places)}</dd>
          </div>
          <div className="rounded-xl bg-white/70 p-2.5">
            <dt className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Öğrenci</dt>
            <dd className="font-mono text-[22px] font-bold tabular-nums">{fmtInt(stats.data.students)}</dd>
          </div>
          {stats.data.studentsUnknown > 0 && (
            <p className="col-span-2 text-[11.5px] leading-snug text-canvas-muted">
              {fmtInt(stats.data.studentsUnknown)} kurumda öğrenci sayısı CRM'de yazılı değil ya da sayı değil; toplama katılmadı.
            </p>
          )}
        </dl>
      )}
    </Block>
  );
}

function OrgSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const meta = usePaMeta();
  const q = useQuery({ queryKey: ['pa', 'org', id], queryFn: () => paApi.org(id as string), enabled: ENGINE_ENABLED && !!id });
  const [note, setNote] = useState(false);
  const o = q.data;
  const place = o?.crm?.place;
  return (
    <Sheet open={!!id} onClose={onClose} modal wide title={o?.name ?? 'Kurum'} subtitle={o ? [o.kindLabel, o.city].filter(Boolean).join(' · ') : undefined}>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Kurum okunamadı.')}</Note>}
      {o && (
        <div className="space-y-3 text-[12.5px]">
          {meta.data?.me.canEdit && (
            <button type="button" className={btnGhost} onClick={() => setNote(true)}>
              <NotebookPen aria-hidden className="h-4 w-4" />
              Kuruma not yaz
            </button>
          )}
          {o.crm?.error && <Note tone="warn">{o.crm.error}</Note>}
          {place && <p className="flex items-center gap-1 text-[11.5px] text-canvas-muted">CRM ziyaret yeri sayıları<SqlInfo k={o.kaynaklar} alan="crm" label="CRM ziyaret yeri" /></p>}
          {place && (
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {[
                ['Öğrenci', place.students],
                ['Öğretmen', place.teachers],
                ['Kütüphanedeki kitap', place.books],
                ['Toplam öğrenci (üniversite)', place.totalStudents],
              ].map(([k, v]) => (
                <div key={k as string} className="rounded-xl bg-slate-50 p-2.5">
                  <dt className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{k}</dt>
                  <dd className="font-mono text-[18px] font-bold tabular-nums">{v == null ? 'yazılı değil' : fmtInt(v as number)}</dd>
                </div>
              ))}
            </dl>
          )}
          {o.note && <p className="whitespace-pre-wrap break-words">{o.note}</p>}
          <section>
            <h3 className="mb-1 flex items-center gap-1 text-[13px] font-extrabold">Kişiler<SqlInfo k={o.kaynaklar} alan="people" label="Kurumun kişileri" /></h3>
            {o.people.length === 0 ? (
              <p className="text-canvas-muted">Bu kuruma bağlı kişi kartı yok.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {o.people.map((p) => (
                  <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                    <Link to={`${BASE}/kisi/${p.id}`} className="min-w-0 font-extrabold hover:underline">
                      {p.name}
                      <span className="ml-1 font-normal text-canvas-muted">{p.title}</span>
                    </Link>
                    <span className="flex items-center gap-1.5 text-[11.5px] text-canvas-muted">
                      <HeatPill heat={p.heat} compact />
                      {daysAgo(p.heat.daysSince)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section>
            <h3 className="mb-1 flex items-center gap-1 text-[13px] font-extrabold">Projeler<SqlInfo k={o.kaynaklar} alan="projects" label="Kurumun projeleri" /></h3>
            {o.projects.length === 0 ? (
              <p className="text-canvas-muted">Proje yok.</p>
            ) : (
              <ul className="divide-y divide-slate-100">
                {o.projects.map((p) => (
                  <li key={p.id} className="py-1.5">
                    <Link to={`${BASE}/projeler?proje=${p.id}`} className="font-extrabold hover:underline">
                      {p.title}
                    </Link>
                    <StageBar stage={p.stage} label={p.stageLabel} />
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section>
            <h3 className="mb-1 text-[13px] font-extrabold">Kurum notları</h3>
            {o.timeline.length === 0 ? (
              <p className="text-canvas-muted">Not yok.</p>
            ) : (
              <ul className="space-y-1.5">
                {o.timeline.map((n) => (
                  <li key={n.id} className="rounded-xl bg-slate-50 px-2.5 py-1.5">
                    <div className="font-extrabold">{n.topic}</div>
                    <div className="text-[11.5px] text-canvas-muted">
                      {fmtDay(n.date)} · {n.channelLabel} · {n.createdDisplay ?? n.createdBy}
                    </div>
                    {n.text && <p className="mt-0.5 whitespace-pre-wrap break-words">{n.text}</p>}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
      {o && <NoteForm open={note} onClose={() => setNote(false)} target={{ orgId: o.id, name: o.name }} />}
    </Sheet>
  );
}
