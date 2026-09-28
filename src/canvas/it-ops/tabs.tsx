import { useEffect, useMemo, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import {
  ENV_LABEL, SOURCE, fmtAt, fmtBytes, fmtMinutes, fmtMs, itOpsApi,
  type Incident, type Release, type SettingItem, type Status,
} from './api';

const nf = new Intl.NumberFormat('tr-TR');
const pct = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 0 });

/* ------------------------------------------------------------------ Olaylar */

export function IncidentsTab({ status, onOpen }: { status: Status | undefined; onOpen: (i: Incident) => void }) {
  const [state, setState] = useState<'all' | 'open' | 'closed'>('all');
  const q = useInfiniteQuery({
    queryKey: ['itops', 'incidents', state],
    queryFn: ({ pageParam }) => itOpsApi.incidents(state, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next,
  });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  const down = q.data?.pages[0]?.downtime30;
  const labels = Object.fromEntries((status?.rings ?? []).map((r) => [r.id, r.label])) as Record<string, string>;
  return (
    <div className="flex flex-col gap-3">
      {down && (
        <Panel>
          <h3 className="flex items-center gap-1 text-[13px] font-extrabold">
            Son 30 gün kesinti
            <SqlInfo k={kaynakOf(q.data?.pages[0])} alan="downtime30" label="Son 30 gün kesinti" />
          </h3>
          <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-7">
            {Object.entries(down).map(([ring, v]) => (
              <div key={ring} className="rounded-xl bg-slate-50 px-2.5 py-2">
                <div className="truncate text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{labels[ring] ?? ring}</div>
                <div className="font-mono text-[18px] font-bold tabular-nums">{fmtMinutes(v.minutes)}</div>
                <div className="text-[11px] text-canvas-muted">{nf.format(v.count)} kopma</div>
              </div>
            ))}
          </div>
        </Panel>
      )}
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Olay durumu">
        {(['all', 'open', 'closed'] as const).map((s) => (
          <button key={s} type="button" role="radio" aria-checked={state === s} onClick={() => setState(s)}
            className={`${btnGhost} ${state === s ? '!bg-canvas-violet !text-white' : ''}`}>
            {{ all: 'Hepsi', open: 'Açık', closed: 'Kapanmış' }[s]}
          </button>
        ))}
      </div>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Olaylar okunamadı.')}</Note>}
      {!q.isLoading && !items.length && <Note tone="info">Bu görünümde olay yok.</Note>}
      <ul className="flex flex-col gap-2">
        {items.map((i) => (
          <li key={i.id}>
            <button type="button" onClick={() => onOpen(i)}
              className="glass-panel flex w-full min-w-0 flex-col gap-1 rounded-2xl p-3 text-left shadow-glass-float transition-transform duration-150 ease-out active:scale-[0.99] sm:flex-row sm:items-center sm:gap-3">
              <span className="flex shrink-0 items-center gap-1.5">
                <Pill tone={i.open ? (i.kind === 'kopma' ? 'err' : 'warn') : 'ok'}>{i.open ? 'Açık' : 'Kapandı'}</Pill>
                <span className="text-[13px] font-extrabold">{i.ringLabel}</span>
              </span>
              <span className="min-w-0 flex-1 truncate text-[12px] text-canvas-muted">{i.kindLabel} · {i.lastError ?? i.firstError}</span>
              <span className="shrink-0 text-[12px] font-semibold tabular-nums">{fmtAt(i.openedAt)} · {fmtMinutes(i.minutes)}</span>
              {i.falseAlarm && <Pill tone="muted">Gerçek değil</Pill>}
              {i.postmortemStatus === 'yayında' && <Pill tone="violet">Değerlendirildi</Pill>}
            </button>
          </li>
        ))}
      </ul>
      {q.hasNextPage && (
        <button type="button" className={`${btnGhost} self-center`} disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>
          Daha eski olaylar
        </button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Zamanlanmış işler */

export function JobsTab() {
  const q = useQuery({ queryKey: ['itops', 'jobs'], queryFn: itOpsApi.jobs, refetchInterval: 60_000 });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'İşler okunamadı.')}</Note>;
  const items = q.data?.items ?? [];
  if (!items.length) return <Note tone="info">Henüz iş kaydı yok; ilk denetim turundan sonra dolar.</Note>;
  return (
    <Panel>
      <div className="-mx-1 overflow-x-auto px-1">
        <table className="w-full min-w-[640px] text-left text-[12.5px]">
          <thead className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
            <tr>
              <th className="py-2 pr-3">İş</th>
              <th className="py-2 pr-3"><InfoLabel k={kaynakOf(q.data)} alan="items">Sonuç</InfoLabel></th>
              <th className="py-2 pr-3">Son koşu</th>
              <th className="py-2 pr-3">Sıradaki</th>
              <th className="py-2">Hata</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((j) => (
              <tr key={j.job} className="align-top">
                <td className="py-2 pr-3">
                  <div className="font-semibold">{j.label}</div>
                  <div className="text-[11px] text-canvas-muted">{SOURCE[j.source] ?? j.source}{j.every ? ` · ${j.every}` : ''}</div>
                </td>
                <td className="py-2 pr-3">
                  <Pill tone={j.lastOk === false ? 'err' : j.lastOk ? 'ok' : 'muted'}>
                    {j.lastOk === false ? (j.failedCount ? `${nf.format(j.failedCount)} hatalı` : 'Başarısız') : j.lastOk ? 'Başarılı' : 'Bilinmiyor'}
                  </Pill>
                  {j.totalCount !== null && <div className="mt-0.5 text-[11px] text-canvas-muted tabular-nums">{nf.format(j.totalCount)} kayıt</div>}
                </td>
                <td className="py-2 pr-3 tabular-nums">{fmtAt(j.lastAt)}</td>
                <td className="py-2 pr-3 tabular-nums">{fmtAt(j.nextAt)}</td>
                <td className="max-w-[420px] break-words py-2 text-[12px]">{j.lastError ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

/* ------------------------------------------------------------------ Sürümler */

function ReleaseLine({ r }: { r: Release }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
      <span className="font-extrabold">{ENV_LABEL[r.env] ?? r.env}</span>
      <span className="font-mono tabular-nums">{r.codeSha ? r.codeSha.slice(0, 12) : 'sürüm bilinmiyor'}</span>
      {r.image && <span className="min-w-0 break-all text-canvas-muted">{r.image}</span>}
      <Pill tone={r.appledoubleCount === 0 ? 'ok' : r.appledoubleCount === null ? 'muted' : 'err'}>
        Mac artığı {r.appledoubleCount === null ? '?' : nf.format(r.appledoubleCount)}
      </Pill>
      <span className="text-canvas-muted tabular-nums">{fmtAt(r.at)} · {r.reportedBy}</span>
    </div>
  );
}

export function ReleasesTab() {
  const q = useInfiniteQuery({
    queryKey: ['itops', 'releases'],
    queryFn: ({ pageParam }) => itOpsApi.releases(pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next,
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Sürümler okunamadı.')}</Note>;
  const first = q.data?.pages[0];
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="flex flex-col gap-3">
      <Panel>
        <h3 className="flex items-center gap-1 text-[13px] font-extrabold">
          Ortamların son kurulumu
          <SqlInfo k={kaynakOf(first)} alan="_hepsi" label="Kurulumlar ve Mac artığı" />
        </h3>
        <div className="mt-2 flex flex-col gap-2">
          {(['test', 'vm', 'gpu'] as const).map((env) =>
            first?.latest[env] ? <ReleaseLine key={env} r={first.latest[env] as Release} /> : (
              <div key={env} className="text-[12.5px] text-canvas-muted"><strong className="text-canvas-ink">{ENV_LABEL[env]}</strong> · kurulum bildirilmedi</div>
            ),
          )}
        </div>
        {first?.parity !== null && first?.parity !== undefined && (
          <div className="mt-3">
            <Note tone={first.parity ? 'ok' : 'warn'}>
              {first.parity ? "Test sunucusu ve müşteri VM'i aynı kod sürümünde." : "Test sunucusu ile müşteri VM'i farklı kod sürümünde. VM'e geriye sarma yapılmaz; kurulacak sürüm VM'dekini içermeli."}
            </Note>
          </div>
        )}
      </Panel>
      {!items.length && <Note tone="info">Henüz sürüm kaydı yok. Kurulum betikleri her kurulumun sonunda bildirir.</Note>}
      <ul className="flex flex-col gap-2">
        {items.map((r) => (
          <li key={r.id} className="glass-panel rounded-2xl p-3 shadow-glass-float"><ReleaseLine r={r} />{r.note && <p className="mt-1 text-[12px] text-canvas-muted">{r.note}</p>}</li>
        ))}
      </ul>
      {q.hasNextPage && (
        <button type="button" className={`${btnGhost} self-center`} disabled={q.isFetchingNextPage} onClick={() => q.fetchNextPage()}>Daha eski</button>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ Kapasite (ilk sürüm: anlık; projeksiyon sonraki sürümde) */

export function CapacityTab() {
  const q = useQuery({ queryKey: ['itops', 'capacity'], queryFn: itOpsApi.capacity, staleTime: 60_000 });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <Note tone="err">{errText(q.error, 'Kapasite okunamadı.')}</Note>;
  const c = q.data;
  return (
    <div className="flex flex-col gap-3">
      <Panel>
        <h3 className="flex items-center gap-1 text-[13px] font-extrabold">
          Disk
          <SqlInfo k={kaynakOf(c)} alan="disks" label="Disk" />
        </h3>
        <div className="mt-2 flex flex-col gap-2">
          {c.disks.map((d) => (
            <div key={d.path} className="min-w-0">
              <div className="flex flex-wrap items-baseline justify-between gap-2 text-[12.5px]">
                <span className="break-all font-semibold">{d.path}</span>
                <span className="tabular-nums text-canvas-muted">
                  {d.error ? d.error : `${fmtBytes(d.used)} / ${fmtBytes(d.total)} · boş ${fmtBytes(d.free)}`}
                </span>
              </div>
              {d.ratio !== undefined && d.ratio !== null && (
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100" role="img" aria-label={`Doluluk ${pct.format(d.ratio)}`}>
                  <div className={`h-full rounded-full ${d.ratio > 0.9 ? 'bg-red-500' : d.ratio > 0.75 ? 'bg-amber-400' : 'bg-emerald-500'}`} style={{ width: `${Math.min(100, d.ratio * 100)}%` }} />
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>
      <Panel>
        <h3 className="flex items-center gap-1 text-[13px] font-extrabold">
          Zeki AI kapasitesi · son {c.days} gün
          <SqlInfo k={kaynakOf(c)} alan="_hepsi" label="Zeki AI kapasitesi" />
        </h3>
        <p className="mt-0.5 text-[11.5px] text-canvas-muted">Modül başına tamamlanan model işi; sırada bekleme ve modelin kendi süresi (ortanca).</p>
        <div className="-mx-1 mt-2 overflow-x-auto px-1">
          <table className="w-full min-w-[420px] text-left text-[12.5px]">
            <thead className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
              <tr><th className="py-1.5 pr-3">Modül</th><th className="py-1.5 pr-3 text-right">İş</th><th className="py-1.5 pr-3 text-right">Sırada bekleme</th><th className="py-1.5 text-right">Model süresi</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {c.modules.map((m) => (
                <tr key={m.module}>
                  <td className="py-1.5 pr-3 font-semibold">{m.module}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{nf.format(m.jobs)}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">{fmtMs(m.waitP50Ms)}</td>
                  <td className="py-1.5 text-right tabular-nums">{fmtMs(m.modelP50Ms)}</td>
                </tr>
              ))}
              {!c.modules.length && <tr><td colSpan={4} className="py-2 text-canvas-muted">Bu dönemde tamamlanan model işi yok.</td></tr>}
            </tbody>
          </table>
        </div>
      </Panel>
      <Panel>
        <h3 className="text-[13px] font-extrabold">Sorular · son {c.days} gün</h3>
        <div className="mt-2 grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-slate-50 p-2"><div className="font-mono text-[18px] font-bold tabular-nums">{nf.format(c.questions.count)}</div><div className="text-[11px] text-canvas-muted">soru</div></div>
          <div className="rounded-xl bg-slate-50 p-2"><div className="font-mono text-[18px] font-bold tabular-nums">{nf.format(c.questions.errors)}</div><div className="text-[11px] text-canvas-muted">hatalı</div></div>
          <div className="rounded-xl bg-slate-50 p-2"><div className="font-mono text-[18px] font-bold tabular-nums">{fmtMs(c.questions.latencyP50Ms)}</div><div className="text-[11px] text-canvas-muted">ortanca süre</div></div>
        </div>
        <p className="mt-2 text-[11.5px] text-canvas-muted">«Ne zaman dolar» tahmini ve bellek/işlemci trendi sonraki sürümde.</p>
      </Panel>
    </div>
  );
}

/* ------------------------------------------------------------------ Ayarlar */

export function SettingsTab({ status }: { status: Status | undefined }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['itops', 'settings'], queryFn: itOpsApi.settings });
  const [draft, setDraft] = useState<Record<string, string>>({});
  useEffect(() => {
    if (q.data) setDraft(Object.fromEntries(q.data.items.map((i) => [i.key, i.value ?? ''])));
  }, [q.data]);
  const changed = useMemo(() => {
    const out: Record<string, string> = {};
    for (const i of q.data?.items ?? []) if ((draft[i.key] ?? '') !== (i.value ?? '')) out[i.key] = draft[i.key] ?? '';
    return out;
  }, [draft, q.data]);
  const save = useMutation({
    mutationFn: () => itOpsApi.saveSettings(changed),
    onSuccess: (out) => {
      qc.setQueryData(['itops', 'settings'], out);
      qc.invalidateQueries({ queryKey: ['itops', 'status'] });
      toast.success('Ayarlar kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  if (q.isLoading) return <Loading />;
  if (q.error || !q.data) return <Note tone="err">{errText(q.error, 'Ayarlar okunamadı.')}</Note>;
  const edit = q.data.canEdit;
  return (
    <div className="flex flex-col gap-3">
      {status && (
        <Note tone={status.email.configured && status.email.recipients.length ? 'info' : 'warn'}>
          {!status.email.configured
            ? 'E-posta ayarı yok: olaylar açılıyor ama kimseye bildirim gitmiyor (Yönetim → Ayarlar → E-posta).'
            : status.email.recipients.length
              ? `Bildirim alıcıları: ${status.email.recipients.join(', ')}.`
              : 'Bildirim alıcısı yok: olaylar yalnız bu ekranda görünür.'}
          {status.email.rejected.length > 0 && ` İç alan adında olmadığı için gönderilmeyen: ${status.email.rejected.join(', ')}.`}
        </Note>
      )}
      {!edit && <Note tone="info">Ayarları görebilirsiniz; değiştirmek için «Sistem durumu ayarları» yetkisi gerekir.</Note>}
      <Panel>
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(min(100%,300px),1fr))]">
          {q.data.items.map((i: SettingItem) => (
            <label key={i.key} className="flex min-w-0 flex-col gap-1">
              <span className={labelCls}>{i.label}</span>
              <input className={field} value={draft[i.key] ?? ''} disabled={!edit} inputMode={i.type === 'int' ? 'numeric' : undefined}
                onChange={(e) => setDraft({ ...draft, [i.key]: e.target.value })} />
              {i.help && <span className="text-[11px] leading-snug text-canvas-muted">{i.help}</span>}
              {i.updatedBy && <span className="text-[10.5px] text-canvas-muted">{i.updatedBy} · {fmtAt(i.updatedAt)}</span>}
            </label>
          ))}
        </div>
        {edit && (
          <div className="mt-3 flex justify-end">
            <button type="button" className={btnPrimary} disabled={!Object.keys(changed).length || save.isPending} onClick={() => save.mutate()}>
              Kaydet{Object.keys(changed).length ? ` (${Object.keys(changed).length})` : ''}
            </button>
          </div>
        )}
      </Panel>
    </div>
  );
}
