import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, FileDown, FolderPlus, Loader2, Wand2, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import SearchSelect from '../components/SearchSelect';
import { fmtDay, usePeopleOptions } from '../editorial/authors/shared';
import { STAGE_FLOW, fmtInt, fmtMoney, paApi, parseAmount, type ProjectBook, type ProjectDetail, type Stage } from './api';
import { BookPicker, PlacePicker } from './pickers';
import { Empty, PaFrame, StageBar, invalidatePa, usePaMeta } from './parts';

/** Kamu projeleri: fikir → ön görüşme → teklif → kurum onayı → uygulama → rapor → kapandı. Pano (telefonda yatay kayar),
 *  proje kartı (`?proje=`): aşama ve not, kitap listesi, hedef kurumlar, bütçe onayı, Zeki AI teklif dosyası taslağı,
 *  CRM'den erişim raporu. */

export default function PaProjects() {
  const meta = usePaMeta();
  const [params, setParams] = useSearchParams();
  const [closed, setClosed] = useState(false);
  const [create, setCreate] = useState(false);
  const open = params.get('proje');
  const setOpen = (id: string | null) => {
    const p = new URLSearchParams(params);
    if (id) p.set('proje', id);
    else p.delete('proje');
    setParams(p, { replace: true });
  };
  const list = useQuery({ queryKey: ['pa', 'projects', closed], queryFn: () => paApi.projects({ closed }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const cols: Stage[] = closed ? [...STAGE_FLOW, 'kapandi', 'vazgecildi'] : STAGE_FLOW;
  const all = list.data?.items ?? [];
  const stageLabel = (s: string) => meta.data?.stages.find((x) => x.key === s)?.label ?? s;

  return (
    <PaFrame
      title="Kamu projeleri"
      lead="MEB, belediye, üniversite, Diyanet ve kütüphanelerle okuma kampanyası, kütüphane bağışı, eğitim materyali. Her aşama değişikliği tarihli kayıttır; bütçesi olan proje onaysız uygulamaya geçmez. Teklif dosyasında sayılar CRM'den, mevzuat maddeleri resmî kaynaktan gelir."
      source={list.data ? `${fmtInt(list.data.total)} proje` : 'Portal + CRM'}
      aside={
        <div className="flex flex-wrap items-center gap-2 lg:justify-end">
          <label className="flex min-h-11 items-center gap-2 text-[12px] font-semibold">
            <input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} />
            Kapananlar
          </label>
          {meta.data?.me.canEdit && (
            <button type="button" className={btnPrimary} onClick={() => setCreate(true)}>
              <FolderPlus aria-hidden className="h-4 w-4" />
              Yeni proje
            </button>
          )}
        </div>
      }
    >
      {list.error && <Note tone="err">{errText(list.error, 'Projeler okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {list.data &&
        (list.data.items.length === 0 ? (
          <Empty title="Proje yok">«Yeni proje» ile bir kurumla yürütülecek projeyi fikir aşamasında açın.</Empty>
        ) : (
          <div className="-mx-1 overflow-x-auto overscroll-x-contain px-1 pb-2">
            <div className="grid auto-cols-[minmax(250px,1fr)] grid-flow-col gap-2">
              {cols.map((s) => {
                const items = all.filter((p) => p.stage === s);
                return (
                  <section key={s} className="flex min-w-0 flex-col gap-2 rounded-2xl bg-slate-100/80 p-2">
                    <h2 className="flex items-center justify-between px-1 text-[12px] font-extrabold uppercase tracking-wide text-canvas-muted">
                      {stageLabel(s)}
                      <span className="inline-flex items-center gap-1 font-mono tabular-nums">{items.length}<SqlInfo k={list.data?.kaynaklar} alan="stages" label={`${stageLabel(s)}: proje sayısı`} /></span>
                    </h2>
                    {items.map((p) => (
                      <button key={p.id} type="button" onClick={() => setOpen(p.id)} className="rounded-xl bg-white p-2.5 text-left shadow-sm transition-transform duration-150 ease-out active:scale-[0.98]">
                        <div className="break-words text-[13px] font-extrabold">{p.title}</div>
                        <div className="text-[11.5px] text-canvas-muted">{[p.orgName, p.kindLabel].filter(Boolean).join(' · ')}</div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {p.late && <Pill tone="err">Adım gecikti</Pill>}
                          {!p.late && p.quiet && <Pill tone="warn">30 gün hareketsiz</Pill>}
                          {p.budget ? <Pill tone={p.budgetApprovedBy ? 'ok' : 'warn'}>{p.budgetApprovedBy ? 'Bütçe onaylı' : 'Bütçe onay bekliyor'}</Pill> : null}
                          {p.proposalStatus === 'hazir' && <Pill tone="violet">Teklif taslağı</Pill>}
                        </div>
                        {p.nextStep && <div className="mt-1 text-[11.5px]">Sıradaki: {p.nextStep}{p.nextOn ? ` · ${fmtDay(p.nextOn)}` : ''}</div>}
                      </button>
                    ))}
                  </section>
                );
              })}
            </div>
          </div>
        ))}
      <CreateSheet open={create} onClose={() => setCreate(false)} onSaved={(id) => setOpen(id)} />
      {open && <ProjectSheet id={open} onClose={() => setOpen(null)} />}
    </PaFrame>
  );
}

function CreateSheet({ open, onClose, onSaved }: { open: boolean; onClose: () => void; onSaved: (id: string) => void }) {
  const qc = useQueryClient();
  const meta = usePaMeta();
  const orgs = useQuery({ queryKey: ['pa', 'orgs', 'all'], queryFn: () => paApi.orgs(), enabled: ENGINE_ENABLED && open, staleTime: 60_000 });
  const [f, setF] = useState({ title: '', kind: 'okuma', orgId: '', summary: '' });
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    if (open) {
      setF({ title: '', kind: 'okuma', orgId: '', summary: '' });
      setErr(null);
    }
  }, [open]);
  const save = useMutation({
    mutationFn: () => paApi.addProject({ ...f, orgId: f.orgId || null, summary: f.summary || null }),
    onSuccess: async (p) => {
      await invalidatePa(qc);
      toast.success('Proje açıldı (fikir).');
      onClose();
      onSaved(p.id);
    },
    onError: (e) => setErr(errText(e, 'Proje açılamadı.')),
  });
  return (
    <Sheet open={open} onClose={onClose} modal title="Yeni proje" subtitle="Fikir aşamasında açılır">
      <form
        className="space-y-3 text-[12.5px]"
        onSubmit={(e) => {
          e.preventDefault();
          setErr(null);
          save.mutate();
        }}
      >
        <label className="block">
          <span className={label}>Proje adı</span>
          <input required maxLength={300} autoFocus value={f.title} onChange={(e) => setF((p) => ({ ...p, title: e.target.value }))} placeholder="ör. İlçe okullarında okuma seferberliği" className={`${field} mt-1`} />
        </label>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="block">
            <span className={label}>Tür</span>
            <select value={f.kind} onChange={(e) => setF((p) => ({ ...p, kind: e.target.value }))} className={`${field} mt-1`}>
              {(meta.data?.projectKinds ?? []).map((k) => (
                <option key={k.key} value={k.key}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className={label}>Kurum</span>
            <select value={f.orgId} onChange={(e) => setF((p) => ({ ...p, orgId: e.target.value }))} className={`${field} mt-1`}>
              <option value="">Sonra seçilecek</option>
              {(orgs.data?.items ?? []).map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="block">
          <span className={label}>Özet</span>
          <textarea rows={3} maxLength={8000} value={f.summary} onChange={(e) => setF((p) => ({ ...p, summary: e.target.value }))} className={`${field} mt-1 resize-y`} />
        </label>
        {err && <Note tone="err">{err}</Note>}
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>
            Vazgeç
          </button>
          <button type="submit" className={btnPrimary} disabled={save.isPending || !f.title.trim()}>
            {save.isPending ? 'Açılıyor…' : 'Projeyi aç'}
          </button>
        </div>
      </form>
    </Sheet>
  );
}

type Draft = {
  title: string; kind: string; orgId: string; summary: string; owner: string; budget: string; nextStep: string; nextOn: string;
  reachSchools: string; reachStudents: string; reachBooks: string; reachParticipants: string; orders: string; press: string; proposalText: string;
};

function draftOf(p: ProjectDetail): Draft {
  const n = (v: number | null) => (v == null ? '' : String(v));
  return {
    title: p.title, kind: p.kind, orgId: p.orgId ?? '', summary: p.summary ?? '', owner: p.owner ?? '',
    budget: p.budget == null ? '' : String(p.budget).replace('.', ','), nextStep: p.nextStep ?? '', nextOn: p.nextOn ?? '',
    reachSchools: n(p.reachSchools), reachStudents: n(p.reachStudents), reachBooks: n(p.reachBooks), reachParticipants: n(p.reachParticipants),
    orders: p.orders.join(', '), press: p.press.join('\n'), proposalText: p.proposalText ?? '',
  };
}

function ProjectSheet({ id, onClose }: { id: string; onClose: () => void }) {
  const qc = useQueryClient();
  const meta = usePaMeta();
  const people = usePeopleOptions();
  const me = meta.data?.me;
  const canEdit = !!me?.canEdit;
  const q = useQuery({
    queryKey: ['pa', 'project', id],
    queryFn: () => paApi.project(id),
    enabled: ENGINE_ENABLED,
    refetchInterval: (s) => (s.state.data?.proposalStatus === 'hazirlaniyor' ? 4000 : false),
  });
  const orgs = useQuery({ queryKey: ['pa', 'orgs', 'all'], queryFn: () => paApi.orgs(), enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const p = q.data;
  const [f, setF] = useState<Draft | null>(null);
  const [books, setBooks] = useState<ProjectBook[]>([]);
  const [places, setPlaces] = useState<Array<{ id: string; name: string }>>([]);
  const [stageNote, setStageNote] = useState('');
  const [picker, setPicker] = useState<'book' | 'place' | null>(null);
  const [showReport, setShowReport] = useState(false);
  useEffect(() => {
    if (!p) return;
    setF(draftOf(p));
    setBooks(p.books);
    setPlaces((prev) => p.places.map((pid) => prev.find((x) => x.id === pid) ?? { id: pid, name: 'CRM kurumu' }));
  }, [p?.updatedAt, p?.proposalStatus, p?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const report = useQuery({
    queryKey: ['pa', 'project-report', id],
    queryFn: () => paApi.projectReport(id),
    enabled: ENGINE_ENABLED && (showReport || (p?.places.length ?? 0) > 0),
  });
  useEffect(() => {
    if (!report.data) return;
    const names = new Map(report.data.places.map((x) => [x.id, x.name ?? 'CRM kurumu']));
    setPlaces((prev) => prev.map((x) => ({ ...x, name: names.get(x.id) ?? x.name })));
  }, [report.data]);

  const done = async () => {
    await invalidatePa(qc);
  };
  const save = useMutation({
    mutationFn: (b: Record<string, unknown>) => paApi.updateProject(id, b),
    onSuccess: async () => {
      await done();
      setStageNote('');
      toast.success('Kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const approve = useMutation({
    mutationFn: ({ what, decision }: { what: 'budget' | 'proposal'; decision: 'onay' | 'geri' }) => paApi.approveProject(id, what, decision),
    onSuccess: async () => {
      await done();
      toast.success('Onay kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Onaylanamadı.') ?? ''),
  });
  const draft = useMutation({
    mutationFn: () => paApi.draftProposal(id),
    onSuccess: async (r) => {
      await done();
      toast.info(r.started ? 'Zeki AI teklif dosyasını hazırlıyor; bitince burada görünür.' : 'Taslak zaten hazırlanıyor.');
    },
    onError: (e) => toast.error(errText(e, 'Taslak başlatılamadı.') ?? ''),
  });

  if (!p || !f) {
    return (
      <Sheet open onClose={onClose} modal wide title="Proje">
        {q.isLoading ? <Loading /> : <Note tone="err">{errText(q.error, 'Proje okunamadı.')}</Note>}
      </Sheet>
    );
  }
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => setF((x) => (x ? { ...x, [k]: v } : x));
  const toInt = (s: string) => (s.trim() ? Number(s.replace(/\./g, '')) : null);
  const body = () => ({
    title: f.title, kind: f.kind, orgId: f.orgId || null, summary: f.summary || null, owner: f.owner || null,
    ownerDisplay: f.owner ? people.byUser.get(f.owner) ?? f.owner : null, budget: f.budget.trim() ? parseAmount(f.budget) : null,
    nextStep: f.nextStep || null, nextOn: f.nextOn || null, reachSchools: toInt(f.reachSchools), reachStudents: toInt(f.reachStudents),
    reachBooks: toInt(f.reachBooks), reachParticipants: toInt(f.reachParticipants),
    orders: f.orders.split(/[,\s]+/).map((x) => x.trim()).filter(Boolean), press: f.press.split('\n').map((x) => x.trim()).filter(Boolean),
    books: books.map((b) => ({ ...b, qty: b.qty ?? null })), places: places.map((x) => x.id),
    proposalText: p.proposalStatus === 'hazirlaniyor' ? undefined : f.proposalText || null,
  });
  const idx = STAGE_FLOW.indexOf(p.stage);
  const next = idx >= 0 && idx < STAGE_FLOW.length - 1 ? STAGE_FLOW[idx + 1] : p.stage === 'rapor' ? ('kapandi' as Stage) : null;
  const stageLabel = (s: string) => meta.data?.stages.find((x) => x.key === s)?.label ?? s;
  const facts = report.data?.facts;

  return (
    <Sheet open onClose={onClose} modal wide title={p.title} subtitle={[p.orgName, p.kindLabel].filter(Boolean).join(' · ')}>
      <div className="grid gap-4 text-[12.5px] lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-3">
          <div className="rounded-2xl border border-slate-100 bg-white/80 p-3">
            <StageBar stage={p.stage} label={p.stageLabel} />
            {canEdit && (
              <div className="mt-2 grid gap-2 sm:grid-cols-[1fr_auto]">
                <input value={stageNote} onChange={(e) => setStageNote(e.target.value)} maxLength={4000} placeholder="Aşama notu (ör. Teklif dosyası il müdürlüğüne verildi)" className={field} />
                <div className="flex flex-wrap gap-1.5">
                  {next && (
                    <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate({ stage: next, stageNote: stageNote || null })}>
                      {stageLabel(next)} aşamasına geç
                    </button>
                  )}
                  <select
                    aria-label="Başka aşama"
                    value=""
                    onChange={(e) => e.target.value && save.mutate({ stage: e.target.value, stageNote: stageNote || null })}
                    className={`${field} w-auto`}
                  >
                    <option value="">Başka aşama…</option>
                    {(meta.data?.stages ?? []).filter((s) => s.key !== p.stage).map((s) => (
                      <option key={s.key} value={s.key}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                  {stageNote.trim() && (
                    <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate({ stageNote })}>
                      Yalnız not
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          <fieldset disabled={!canEdit} className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block sm:col-span-2">
                <span className={label}>Proje adı</span>
                <input maxLength={300} value={f.title} onChange={(e) => set('title', e.target.value)} className={`${field} mt-1`} />
              </label>
              <label className="block">
                <span className={label}>Tür</span>
                <select value={f.kind} onChange={(e) => set('kind', e.target.value)} className={`${field} mt-1`}>
                  {(meta.data?.projectKinds ?? []).map((k) => (
                    <option key={k.key} value={k.key}>
                      {k.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className={label}>Kurum</span>
                <select value={f.orgId} onChange={(e) => set('orgId', e.target.value)} className={`${field} mt-1`}>
                  <option value="">Seçilmedi</option>
                  {(orgs.data?.items ?? []).map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="block">
              <span className={label}>Özet (teklif taslağına girer)</span>
              <textarea rows={3} maxLength={8000} value={f.summary} onChange={(e) => set('summary', e.target.value)} className={`${field} mt-1 resize-y`} />
            </label>
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <span className={label}>Sorumlu</span>
                <SearchSelect label="Sorumlu" placeholder="Seçilmedi" options={people.options} value={f.owner} onChange={(v) => set('owner', v)} className="mt-1" />
              </div>
              <label className="block">
                <span className={label}>Bütçe (₺)</span>
                <input inputMode="decimal" value={f.budget} onChange={(e) => set('budget', e.target.value)} placeholder="ör. 125.000" className={`${field} mt-1`} />
              </label>
              <label className="block">
                <span className={label}>Sıradaki adım</span>
                <input maxLength={500} value={f.nextStep} onChange={(e) => set('nextStep', e.target.value)} className={`${field} mt-1`} />
              </label>
              <label className="block">
                <span className={label}>Adım tarihi</span>
                <input type="date" value={f.nextOn} onChange={(e) => set('nextOn', e.target.value)} className={`${field} mt-1`} />
              </label>
            </div>

            <section className="rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-[13px] font-extrabold">Kitap listesi</h3>
                <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => setPicker('book')}>
                  Kitap ekle
                </button>
              </div>
              {books.length === 0 ? (
                <p className="text-canvas-muted">Kitap seçilmedi.</p>
              ) : (
                <ul className="divide-y divide-slate-100">
                  {books.map((b, i) => (
                    <li key={b.id} className="flex flex-wrap items-center gap-2 py-1.5">
                      <span className="min-w-0 flex-1 break-words font-semibold">{b.name ?? b.stockCode}</span>
                      <input
                        aria-label={`${b.name} adet`}
                        inputMode="numeric"
                        value={b.qty ?? ''}
                        onChange={(e) => setBooks((x) => x.map((y, j) => (j === i ? { ...y, qty: e.target.value ? Number(e.target.value.replace(/\D/g, '')) : null } : y)))}
                        placeholder="adet"
                        className={`${field} w-24`}
                      />
                      <button type="button" aria-label="Çıkar" className={`${btnGhost} !min-h-9 !px-2 !py-1`} onClick={() => setBooks((x) => x.filter((_, j) => j !== i))}>
                        <X aria-hidden className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-[13px] font-extrabold">Hedef kurumlar (CRM ziyaret yerleri)</h3>
                <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => setPicker('place')}>
                  Kurum ekle
                </button>
              </div>
              {places.length === 0 ? (
                <p className="text-canvas-muted">Hedef kurum seçilmedi; teklifte okul ve öğrenci sayısı buradan hesaplanır.</p>
              ) : (
                <ul className="flex flex-wrap gap-1.5">
                  {places.map((x) => (
                    <li key={x.id}>
                      <button type="button" className="rounded-lg bg-violet-50 px-2 py-1 text-[11.5px] font-bold text-violet-800" onClick={() => setPlaces((y) => y.filter((z) => z.id !== x.id))}>
                        {x.name} ×
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <div className="grid gap-2 sm:grid-cols-2">
              <label className="block">
                <span className={label}>CRM sipariş numaraları (dağıtılan kitap)</span>
                <input value={f.orders} onChange={(e) => set('orders', e.target.value)} placeholder="virgülle" className={`${field} mt-1`} />
              </label>
              <label className="block">
                <span className={label}>Basın yansıması (her satıra bir bağlantı)</span>
                <textarea rows={2} value={f.press} onChange={(e) => set('press', e.target.value)} className={`${field} mt-1 resize-y`} />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              {(
                [
                  ['reachSchools', 'Ulaşılan okul'],
                  ['reachStudents', 'Ulaşılan öğrenci'],
                  ['reachBooks', 'Dağıtılan kitap'],
                  ['reachParticipants', 'Katılımcı'],
                ] as const
              ).map(([k, l]) => (
                <label key={k} className="block">
                  <span className={label}>{l}</span>
                  <input inputMode="numeric" value={f[k]} onChange={(e) => set(k, e.target.value.replace(/[^\d.]/g, ''))} className={`${field} mt-1`} />
                </label>
              ))}
            </div>

            <section className="rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-[13px] font-extrabold">Teklif dosyası</h3>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Pill tone={p.proposalStatus === 'hazir' ? 'violet' : p.proposalStatus === 'hata' ? 'err' : 'muted'}>{p.proposalStatusLabel}</Pill>
                  {p.proposalApprovedBy && <Pill tone="ok">Onaylı · {p.proposalApprovedBy}</Pill>}
                </div>
              </div>
              {p.proposalStatus === 'hata' && <Note tone="err">{p.proposalError}</Note>}
              {p.proposalStatus === 'hazirlaniyor' ? (
                <p className="flex items-center gap-2 text-canvas-muted">
                  <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
                  Zeki AI bölümleri yazıyor; CRM'den kurum ve öğrenci sayıları ekleniyor.
                </p>
              ) : (
                <textarea rows={10} value={f.proposalText} onChange={(e) => set('proposalText', e.target.value)} placeholder="Taslak yok. «Zeki AI ile taslak» amaç, kapsam, fayda ve takvimi yazar; sayılar ve mevzuat maddeleri koddan eklenir." className={`${field} resize-y font-mono text-[12px] leading-snug`} />
              )}
              <div className="mt-2 flex flex-wrap gap-1.5">
                {canEdit && (
                  <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={draft.isPending || p.proposalStatus === 'hazirlaniyor'} onClick={() => draft.mutate()}>
                    <Wand2 aria-hidden className="h-3.5 w-3.5" />
                    {p.proposalText ? 'Yeniden taslak' : 'Zeki AI ile taslak'}
                  </button>
                )}
                {me?.canExport && p.proposalText && (
                  <a className={`${btnGhost} !min-h-9 !py-1`} href={paApi.proposalPdfUrl(p.id)} download>
                    <FileDown aria-hidden className="h-3.5 w-3.5" />
                    PDF
                  </a>
                )}
              </div>
            </section>
          </fieldset>

          {canEdit && (
            <div className="sticky bottom-0 flex justify-end bg-white/95 py-2">
              <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate(body())}>
                {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
              </button>
            </div>
          )}
        </div>

        <aside className="min-w-0 space-y-3">
          <section className="rounded-2xl border border-slate-100 bg-white/80 p-3">
            <h3 className="flex items-center gap-1 text-[13px] font-extrabold">Onaylar<SqlInfo k={p.kaynaklar} alan="budget" label="Bütçe" /></h3>
            <dl className="mt-1 space-y-1.5">
              <div className="flex justify-between gap-2">
                <dt className="text-canvas-muted">Bütçe</dt>
                <dd className="text-right font-semibold">
                  {fmtMoney(p.budget)} {p.budget ? (p.budgetApprovedBy ? `· onaylı (${p.budgetApprovedBy})` : '· onay bekliyor') : ''}
                </dd>
              </div>
            </dl>
            {me?.canApprove && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {p.budget ? (
                  <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={approve.isPending} onClick={() => approve.mutate({ what: 'budget', decision: p.budgetApprovedBy ? 'geri' : 'onay' })}>
                    <Check aria-hidden className="h-3.5 w-3.5" />
                    {p.budgetApprovedBy ? 'Bütçe onayını geri al' : 'Bütçeyi onayla'}
                  </button>
                ) : null}
                {p.proposalText ? (
                  <button type="button" className={`${btnGhost} !min-h-9 !py-1`} disabled={approve.isPending} onClick={() => approve.mutate({ what: 'proposal', decision: p.proposalApprovedBy ? 'geri' : 'onay' })}>
                    <Check aria-hidden className="h-3.5 w-3.5" />
                    {p.proposalApprovedBy ? 'Teklif onayını geri al' : 'Teklif metnini onayla'}
                  </button>
                ) : null}
              </div>
            )}
          </section>

          <section className="rounded-2xl border border-slate-100 bg-white/80 p-3">
            <div className="flex items-center justify-between gap-2">
              <h3 className="flex items-center gap-1 text-[13px] font-extrabold">Erişim (CRM)<SqlInfo k={report.data?.kaynaklar} alan="facts" label="Proje erişimi" /></h3>
              {!showReport && !report.data && (
                <button type="button" className={`${btnGhost} !min-h-9 !py-1`} onClick={() => setShowReport(true)}>
                  CRM'den oku
                </button>
              )}
            </div>
            {report.isFetching && <p className="mt-1 text-canvas-muted">Okunuyor…</p>}
            {report.data?.crmError && <Note tone="warn">CRM şu an okunamıyor.</Note>}
            {report.data?.missingOrders?.length ? <Note tone="warn">CRM'de bulunamayan sipariş: {report.data.missingOrders.join(', ')}</Note> : null}
            {facts && (
              <dl className="mt-2 space-y-1">
                {[
                  ['Hedef kurum', fmtInt(facts.places)],
                  ['Öğrenci', `${fmtInt(facts.students)}${facts.studentsUnknown ? ` (${fmtInt(facts.studentsUnknown)} kurumda yazılı değil)` : ''}`],
                  ['Öğretmen', `${fmtInt(facts.teachers)}${facts.teachersUnknown ? ` (${fmtInt(facts.teachersUnknown)} kurumda yazılı değil)` : ''}`],
                  ['Kitap (başlık)', fmtInt(facts.bookTitles)],
                  ['Planlanan adet', fmtInt(facts.booksPlanned)],
                  ['CRM siparişiyle dağıtılan', facts.booksDelivered == null ? 'sipariş yazılmadı' : fmtInt(facts.booksDelivered)],
                ].map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2">
                    <dt className="text-canvas-muted">{k}</dt>
                    <dd className="text-right font-semibold">{v}</dd>
                  </div>
                ))}
              </dl>
            )}
          </section>

          <section className="rounded-2xl border border-slate-100 bg-white/80 p-3">
            <h3 className="text-[13px] font-extrabold">Geçmiş</h3>
            <ol className="mt-1 space-y-1.5">
              {p.events.map((e) => (
                <li key={e.id} className="text-[12px]">
                  <div className="font-semibold">
                    {e.stageFrom && e.stageFrom !== e.stageTo ? `${e.stageFromLabel} → ${e.stageToLabel}` : e.stageToLabel}
                  </div>
                  <div className="text-[11px] text-canvas-muted">
                    {fmtDay(e.at)} · {e.userDisplay ?? e.user}
                  </div>
                  {e.note && <p className="break-words">{e.note}</p>}
                </li>
              ))}
            </ol>
          </section>
        </aside>
      </div>

      <Sheet open={picker === 'book'} onClose={() => setPicker(null)} modal title="Kitap ekle" subtitle="Kaydet'e basınca listeye yazılır">
        <BookPicker picked={books.map((b) => b.id)} action="Ekle" onPick={(b) => b.id && setBooks((x) => [...x, { id: b.id as string, name: b.name, stockCode: b.stockCode, qty: null }])} />
      </Sheet>
      <Sheet open={picker === 'place'} onClose={() => setPicker(null)} modal title="Hedef kurum ekle" subtitle="CRM ziyaret yerleri">
        <PlacePicker picked={places.map((x) => x.id)} onPick={(x) => x.id && setPlaces((y) => [...y, { id: x.id as string, name: x.name ?? 'CRM kurumu' }])} />
      </Sheet>
    </Sheet>
  );
}
