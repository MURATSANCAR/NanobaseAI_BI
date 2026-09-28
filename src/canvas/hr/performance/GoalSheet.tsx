import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Sparkles } from 'lucide-react';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls, nf } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { fmtDateTime } from '../hrApi';
import { perfApi, STATE_TONE, type Goal, type GoalDetail, type Level, type PerfMeta } from './perfApi';

/** Hedef kartı: ayrıntı, düzenleme (taslakta), onaya gönderme/onay, check-in, revizyon talebi ve kararı, hizalama önerisi.
 *  Yeni hedef için `goal = null`; düzey ve sahibi `init` ile gelir. */

type Init = { level: Level; ownerEmployeeId?: string | null; unitId?: string | null; parentGoalId?: string | null; period?: string };

export default function GoalSheet({ goalId, init, meta, parents, onClose }: {
  goalId: string | null; init?: Init; meta: PerfMeta; parents: Goal[]; onClose: () => void;
}) {
  const qc = useQueryClient();
  const detail = useQuery({ queryKey: ['hr', 'perf', 'goal', goalId], queryFn: () => perfApi.goal(goalId as string), enabled: !!goalId });
  const g = detail.data;
  const refresh = (next?: GoalDetail) => {
    if (next) qc.setQueryData(['hr', 'perf', 'goal', next.id], next);
    void qc.invalidateQueries({ queryKey: ['hr', 'perf'] });
  };
  return (
    <Sheet open modal wide onClose={onClose} title={g ? g.title : 'Yeni hedef'} subtitle={g ? `${g.levelLabel} · ${g.period} · ${g.stateLabel}` : undefined}>
      {detail.error && <Note tone="err">{errText(detail.error, 'Hedef okunamadı.')}</Note>}
      {(!goalId || g) && (
        <div className="flex flex-col gap-4">
          {(!g || g.can.edit) && <Editor g={g ?? null} init={init} meta={meta} parents={parents} onSaved={(x) => { refresh(x); if (!g) onClose(); }} />}
          {g && !g.can.edit && <Summary g={g} />}
          {g && <Actions g={g} onDone={refresh} />}
          {g && g.measureKind === 'sistem' && <SystemProgress id={g.id} />}
          {g && g.can.checkin && <CheckinBox g={g} onDone={refresh} />}
          {g && (g.can.revise || g.openRevision) && <RevisionBox g={g} canDecide={meta.me.can.goalApprove} onDone={refresh} />}
          {g && g.level !== 'sirket' && (g.can.edit || g.can.revise) && meta.modelVar && <AlignBox g={g} />}
          {g && g.checkins.length > 0 && (
            <div>
              <div className={labelCls}>Check-in geçmişi</div>
              <ul className="mt-1 flex flex-col gap-1.5">
                {g.checkins.map((c, i) => (
                  <li key={c.id ?? i} className="rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">
                    <div className="flex flex-wrap items-center gap-2">
                      {c.progressPct !== null && <Pill tone="violet">%{c.progressPct}</Pill>}
                      {c.value !== null && <span className="font-mono tabular-nums">{nf.format(c.value)} {g.unitLabel}</span>}
                      <span className="text-[11.5px] text-canvas-muted">{c.author} · {fmtDateTime(c.at)}</span>
                    </div>
                    {c.note && <div className="mt-0.5 break-words">{c.note}</div>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {g && g.children.length > 0 && (
            <div>
              <div className={labelCls}>Bu hedefe bağlı hedefler</div>
              <ul className="mt-1 flex flex-col gap-1 text-[12.5px]">
                {g.children.map((c) => (
                  <li key={c.id} className="flex flex-wrap items-center gap-1.5">
                    <Pill tone={STATE_TONE[c.state]}>{meta.levels[c.level]}</Pill>
                    <span className="min-w-0 break-words font-semibold">{c.title}</span>
                    <span className="text-canvas-muted">{c.ownerName ?? c.unitName ?? ''}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}

function Summary({ g }: { g: GoalDetail }) {
  return (
    <div className="grid grid-cols-1 gap-2 text-[12.5px] sm:grid-cols-2">
      <div><span className={labelCls}>Sahibi</span><div className="font-semibold">{g.ownerName ?? g.unitName ?? 'Şirket'}</div></div>
      <div><span className={labelCls}>Bağlı olduğu hedef</span><div className="font-semibold">{g.parentTitle ?? (g.level === 'sirket' ? '—' : 'Bağlanmamış')}</div></div>
      <div><span className={labelCls}>Hedef değer</span><div className="font-semibold tabular-nums">{g.targetValue !== null ? `${nf.format(g.targetValue)} ${g.unitLabel}` : '—'}</div></div>
      <div><span className={labelCls}>Ağırlık</span><div className="font-semibold">{g.weight !== null ? `%${g.weight}` : '—'}</div></div>
      {g.description && <div className="sm:col-span-2"><span className={labelCls}>Açıklama</span><div className="whitespace-pre-wrap break-words">{g.description}</div></div>}
      {g.reviewNote && <div className="sm:col-span-2"><Note tone="warn">Onaylayanın notu: {g.reviewNote}</Note></div>}
    </div>
  );
}

function Editor({ g, init, meta, parents, onSaved }: { g: GoalDetail | null; init?: Init; meta: PerfMeta; parents: Goal[]; onSaved: (x: GoalDetail) => void }) {
  const level = g?.level ?? init?.level ?? 'kisi';
  const [f, setF] = useState({
    title: g?.title ?? '', description: g?.description ?? '', period: g?.period ?? init?.period ?? String(new Date().getFullYear()),
    parentGoalId: g?.parentGoalId ?? init?.parentGoalId ?? '', targetValue: g?.targetValue != null ? String(g.targetValue) : '', unitLabel: g?.unitLabel ?? '',
    weight: g?.weight != null ? String(g.weight) : '', measureKind: (g?.measureKind ?? 'beyan') as 'beyan' | 'sistem', measureRef: g?.measureRef ?? '', unitId: g?.unitId ?? init?.unitId ?? '',
  });
  const [drafts, setDrafts] = useState<{ title: string; measure: string; target: string }[]>([]);
  const save = useMutation({
    mutationFn: () => {
      const body: Record<string, unknown> = {
        title: f.title, description: f.description, period: f.period, parentGoalId: f.parentGoalId || null,
        targetValue: f.targetValue === '' ? null : f.targetValue, unitLabel: f.unitLabel, weight: f.weight === '' ? null : f.weight,
        measureKind: f.measureKind, systemMeasure: f.measureKind === 'sistem' ? 'logo_net_satis' : null, measureRef: f.measureRef,
      };
      if (!g) Object.assign(body, { level, ownerEmployeeId: init?.ownerEmployeeId ?? null, unitId: level === 'birim' ? f.unitId : null });
      return g ? perfApi.updateGoal(g.id, body) : perfApi.createGoal(body);
    },
    onSuccess: (x) => { toast.success('Hedef kaydedildi.'); onSaved(x); },
    onError: (e) => toast.error(errText(e, 'Hedef kaydedilemedi.')),
  });
  const draft = useMutation({
    mutationFn: () => perfApi.draft({ parentGoalId: f.parentGoalId || undefined, ownerEmployeeId: init?.ownerEmployeeId ?? undefined, unitId: f.unitId || undefined, hint: f.description }),
    onSuccess: (r) => setDrafts(r.items),
    onError: (e) => toast.error(errText(e, 'Zeki AI taslak yazamadı.')),
  });
  const parentOptions = parents.filter((p) => p.id !== g?.id && p.period.slice(0, 4) === f.period.slice(0, 4) && p.state !== 'kapandi'
    && (level === 'kisi' ? p.level !== 'kisi' : level === 'birim' ? p.level !== 'kisi' : false));
  return (
    <div className="flex flex-col gap-3">
      {level === 'birim' && !g && (
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Birim</span>
          <select className={field} value={f.unitId} onChange={(e) => setF({ ...f, unitId: e.target.value })}>
            <option value="">Seçin</option>
            {meta.units.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
          </select>
        </label>
      )}
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Hedef</span>
        <input className={field} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Kısa ve ölçülebilir" />
      </label>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Dönem</span>
          <input className={field} value={f.period} onChange={(e) => setF({ ...f, period: e.target.value })} placeholder="2026 ya da 2026-Q4" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Hedef değer</span>
          <input className={field} inputMode="decimal" value={f.targetValue} onChange={(e) => setF({ ...f, targetValue: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ağırlık (%)</span>
          <input className={field} inputMode="numeric" value={f.weight} onChange={(e) => setF({ ...f, weight: e.target.value })} />
        </label>
      </div>
      {level !== 'sirket' && (
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Bağlı olduğu hedef</span>
          <select className={field} value={f.parentGoalId} onChange={(e) => setF({ ...f, parentGoalId: e.target.value })}>
            <option value="">Bağlanmadı</option>
            {parentOptions.map((p) => <option key={p.id} value={p.id}>{p.levelLabel}{p.unitName ? ` · ${p.unitName}` : ''} — {p.title}</option>)}
          </select>
        </label>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ölçü</span>
          <select className={field} value={f.measureKind} onChange={(e) => setF({ ...f, measureKind: e.target.value as 'beyan' | 'sistem' })}>
            <option value="beyan">{meta.measureKinds.beyan}</option>
            {meta.settings.logoSales && <option value="sistem">{meta.systemMeasures.logo_net_satis?.label}</option>}
          </select>
        </label>
        {f.measureKind === 'sistem' ? (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Logo satış temsilcisi kodu</span>
            <input className={field} value={f.measureRef} onChange={(e) => setF({ ...f, measureRef: e.target.value })} />
          </label>
        ) : (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Birim (adet, ₺, %…)</span>
            <input className={field} value={f.unitLabel} onChange={(e) => setF({ ...f, unitLabel: e.target.value })} />
          </label>
        )}
      </div>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Açıklama / nasıl ölçülür</span>
        <textarea className={`${field} min-h-[80px]`} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
      </label>
      {drafts.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <div className={labelCls}>Zeki AI taslakları (birini seçip düzeltin)</div>
          {drafts.map((d, i) => (
            <button key={i} type="button" className="rounded-xl border border-slate-100 bg-white/80 p-2.5 text-left text-[12.5px] transition-colors duration-150 hover:border-canvas-violet/40"
              onClick={() => setF({ ...f, title: d.title, description: d.measure })}>
              <div className="font-bold">{d.title}</div>
              <div className="text-canvas-muted">{d.measure}{d.target ? ` · ${d.target}` : ''}</div>
            </button>
          ))}
        </div>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        {meta.modelVar && (
          <button type="button" className={btnGhost} disabled={draft.isPending} onClick={() => draft.mutate()}>
            <Sparkles aria-hidden className="h-4 w-4" />{draft.isPending ? 'Zeki AI yazıyor…' : 'Zeki AI taslak öner'}
          </button>
        )}
        <button type="button" className={btnPrimary} disabled={save.isPending || !f.title.trim()} onClick={() => save.mutate()}>Kaydet</button>
      </div>
    </div>
  );
}

function Actions({ g, onDone }: { g: GoalDetail; onDone: (x: GoalDetail) => void }) {
  const [note, setNote] = useState('');
  const act = useMutation({
    mutationFn: (a: 'submit' | 'withdraw' | 'approve' | 'reject' | 'close') => perfApi.goalAction(g.id, a, note),
    onSuccess: (x) => { toast.success(x.stateLabel); onDone(x); setNote(''); },
    onError: (e) => toast.error(errText(e, 'İşlem yapılamadı.')),
  });
  const any = g.can.submit || g.can.withdraw || g.can.approve || g.can.close;
  if (!any) return null;
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-slate-50 p-3">
      {g.can.approve && <input className={field} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (geri gönderirken zorunlu)" />}
      <div className="flex flex-wrap justify-end gap-2">
        {g.can.submit && <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate('submit')}>Onaya gönder</button>}
        {g.can.withdraw && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('withdraw')}>Geri çek</button>}
        {g.can.approve && <button type="button" className={btnGhost} disabled={act.isPending || !note.trim()} onClick={() => act.mutate('reject')}>Geri gönder</button>}
        {g.can.approve && <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate('approve')}>Onayla</button>}
        {g.can.close && <button type="button" className={btnGhost} disabled={act.isPending} onClick={() => act.mutate('close')}>Hedefi kapat</button>}
      </div>
    </div>
  );
}

function SystemProgress({ id }: { id: string }) {
  const q = useQuery({ queryKey: ['hr', 'perf', 'progress', id], queryFn: () => perfApi.progress(id), staleTime: 300_000 });
  if (q.error) return <Note tone="warn">{errText(q.error, 'Logo ilerlemesi okunamadı.')}</Note>;
  if (!q.data) return <div className="text-[12px] text-canvas-muted">Logo'dan faturalı net satış okunuyor…</div>;
  const d = q.data;
  return (
    <div className="rounded-2xl bg-emerald-50/60 p-3 text-[12.5px]">
      <div className={labelCls}>Logo faturalı net satış · {d.code}</div>
      <div className="mt-0.5 text-[18px] font-extrabold tabular-nums">{d.value !== null ? `${nf.format(d.value)} ₺` : '—'}
        {d.progressPct !== null && <span className="ml-2 text-[13px] text-emerald-700">hedefin %{nf.format(d.progressPct)}</span>}</div>
      <div className="text-canvas-muted">{d.invoices ?? 0} fatura · son fatura {d.lastDate ?? '—'} · {d.periodStart} – {d.periodEnd}</div>
      {d.note && <div className="mt-1 text-[11.5px] text-canvas-muted">{d.note}</div>}
    </div>
  );
}

function CheckinBox({ g, onDone }: { g: GoalDetail; onDone: (x: GoalDetail) => void }) {
  const [f, setF] = useState({ progressPct: '', value: '', note: '' });
  const save = useMutation({
    mutationFn: () => perfApi.checkin(g.id, { progressPct: f.progressPct === '' ? null : Number(f.progressPct), value: f.value === '' ? null : Number(f.value.replace(',', '.')), note: f.note }),
    onSuccess: (x) => { toast.success('Check-in kaydedildi.'); setF({ progressPct: '', value: '', note: '' }); onDone(x); },
    onError: (e) => toast.error(errText(e, 'Check-in kaydedilemedi.')),
  });
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="text-[13px] font-extrabold">Check-in</div>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>İlerleme %</span>
          <input className={field} inputMode="numeric" value={f.progressPct} onChange={(e) => setF({ ...f, progressPct: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Değer {g.unitLabel && `(${g.unitLabel})`}</span>
          <input className={field} inputMode="decimal" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} />
        </label>
      </div>
      <textarea className={`${field} min-h-[60px]`} value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} placeholder="Kısa not" />
      <div className="flex justify-end">
        <button type="button" className={btnPrimary} disabled={save.isPending || (!f.progressPct && !f.value && !f.note.trim())} onClick={() => save.mutate()}>Kaydet</button>
      </div>
    </div>
  );
}

function RevisionBox({ g, canDecide, onDone }: { g: GoalDetail; canDecide: boolean; onDone: (x: GoalDetail) => void }) {
  const [f, setF] = useState({ title: '', targetValue: '', weight: '', reason: '' });
  const [note, setNote] = useState('');
  const ask = useMutation({
    mutationFn: () => {
      const changes: Record<string, unknown> = {};
      if (f.title.trim()) changes.title = f.title;
      if (f.targetValue.trim()) changes.targetValue = f.targetValue;
      if (f.weight.trim()) changes.weight = f.weight;
      return perfApi.revise(g.id, { changes, reason: f.reason });
    },
    onSuccess: (x) => { toast.success('Revizyon talebi gönderildi.'); onDone(x); },
    onError: (e) => toast.error(errText(e, 'Talep gönderilemedi.')),
  });
  const decide = useMutation({
    mutationFn: (d: 'onay' | 'ret') => perfApi.decide(g.openRevision!.id, d, note),
    onSuccess: (x) => { toast.success('Karar kaydedildi.'); onDone(x); },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.')),
  });
  if (g.openRevision) {
    const r = g.openRevision;
    return (
      <div className="flex flex-col gap-2 rounded-2xl bg-amber-50/70 p-3 text-[12.5px]">
        <div className="font-extrabold">Karar bekleyen revizyon</div>
        <div>{r.requestedBy} · {fmtDateTime(r.requestedAt)}</div>
        <ul className="list-disc pl-5">
          {Object.entries(r.changes).map(([k, v]) => <li key={k}>{({ title: 'Başlık', targetValue: 'Hedef değer', weight: 'Ağırlık', parentGoalId: 'Bağlı hedef', description: 'Açıklama' } as Record<string, string>)[k] ?? k}: <b>{String(v)}</b></li>)}
        </ul>
        <div className="text-canvas-muted">Gerekçe: {r.reason}</div>
        {canDecide && (
          <>
            <input className={field} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (reddederken zorunlu)" />
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" className={btnGhost} disabled={decide.isPending || !note.trim()} onClick={() => decide.mutate('ret')}>Reddet</button>
              <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate('onay')}>Onayla</button>
            </div>
          </>
        )}
      </div>
    );
  }
  return (
    <details className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <summary className="cursor-pointer text-[13px] font-extrabold">Revizyon iste</summary>
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <input className={field} value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder="Yeni başlık" />
        <input className={field} inputMode="decimal" value={f.targetValue} onChange={(e) => setF({ ...f, targetValue: e.target.value })} placeholder="Yeni hedef değer" />
        <input className={field} inputMode="numeric" value={f.weight} onChange={(e) => setF({ ...f, weight: e.target.value })} placeholder="Yeni ağırlık" />
      </div>
      <textarea className={`${field} mt-2 min-h-[60px]`} value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} placeholder="Gerekçe" />
      <div className="mt-2 flex justify-end">
        <button type="button" className={btnPrimary} disabled={ask.isPending || !f.reason.trim()} onClick={() => ask.mutate()}>Gönder</button>
      </div>
    </details>
  );
}

function AlignBox({ g }: { g: GoalDetail }) {
  const run = useMutation({ mutationFn: () => perfApi.align(g.id), onError: (e) => toast.error(errText(e, 'Öneri alınamadı.')) });
  const s = run.data?.suggestion;
  return (
    <div className="rounded-2xl bg-canvas-violet/5 p-3 text-[12.5px]">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="font-extrabold">Hangi üst hedefe bağlı?</div>
        <button type="button" className={btnGhost} disabled={run.isPending} onClick={() => run.mutate()}>
          <Sparkles aria-hidden className="h-4 w-4" />{run.isPending ? 'Bakılıyor…' : 'Zeki AI öner'}
        </button>
      </div>
      {run.data && !s && <div className="mt-1 text-canvas-muted">{run.data.note ?? 'Zeki AI bir öneri çıkaramadı.'}</div>}
      {s && (
        <div className="mt-1">
          Öneri: <b>{s.title}</b>
          {s.probability !== null && <span className="ml-1 text-canvas-muted">(olasılık %{Math.round(s.probability * 100)})</span>}
          <div className="text-[11.5px] text-canvas-muted">Bağlamayı siz yaparsınız: taslakta «Bağlı olduğu hedef»ten, yürürlükte revizyonla.</div>
        </div>
      )}
    </div>
  );
}
