import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import { freelanceApi } from '../../engine';
import { Loading, Note, Pill, btnGhost, errText, field, nf } from '../../admin/ui';
import { Panel } from '../kit';
import { Empty, TASK_STATUS, day, loadTone, q2, roleLabel, type FlCtx } from './shared';

/**
 * Haftalık kapasite: her kişinin haftalık saatine karşı elindeki işin yükü. Görevin tahmini saati başlangıç–termin
 * arasındaki iş günlerine eşit yayılır; müsait olmadığı günler kapasiteden düşer; termini geçmiş iş bu haftaya yazılır.
 */

const addWeeks = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 7 * n);
  return d.toISOString().slice(0, 10);
};

export default function CapacityPane({ ctx }: { ctx: FlCtx }) {
  const [, setParams] = useSearchParams();
  const [role, setRole] = useState('');
  const [weeks, setWeeks] = useState(8);
  const [start, setStart] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const cap = useQuery({
    queryKey: ['fl', 'capacity', role, weeks, start],
    queryFn: () => freelanceApi.capacity({ role, weeks, start: start ?? undefined }),
    placeholderData: (p) => p,
  });
  const d = cap.data;
  const thisWeek = d && !start ? d.weeks[0] : null;
  const over = d?.people.filter((p) => p.weeks.some((w) => (w.ratio ?? 0) > 1)).length ?? 0;

  return (
    <Panel>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="grid grid-cols-2 gap-2 sm:flex">
          <select aria-label="Rol" value={role} onChange={(e) => setRole(e.target.value)} className={`${field} sm:w-52`}>
            <option value="">Bütün roller</option>
            {ctx.roles.map((r) => (
              <option key={r.key} value={r.key}>
                {r.label}
              </option>
            ))}
          </select>
          <select aria-label="Hafta sayısı" value={weeks} onChange={(e) => setWeeks(Number(e.target.value))} className={`${field} sm:w-32`}>
            {[4, 8, 12, 26].map((n) => (
              <option key={n} value={n}>
                {n} hafta
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-1.5">
          {cap.isFetching && <Loader2 aria-hidden className="h-4 w-4 animate-spin text-canvas-muted" />}
          <button type="button" className={`${btnGhost} px-2.5`} aria-label="Önceki hafta" onClick={() => d && setStart(addWeeks(d.weeks[0], -1))} disabled={!d || !start}>
            <ChevronLeft aria-hidden className="h-4 w-4" />
          </button>
          <button type="button" className={btnGhost} onClick={() => setStart(null)} disabled={!start}>
            Bu hafta
          </button>
          <button type="button" className={`${btnGhost} px-2.5`} aria-label="Sonraki hafta" onClick={() => d && setStart(addWeeks(d.weeks[0], 1))} disabled={!d}>
            <ChevronRight aria-hidden className="h-4 w-4" />
          </button>
        </div>
      </div>

      {cap.error && <Note tone="err">{errText(cap.error, 'Kapasite okunamadı.')}</Note>}
      {!d && !cap.error && <Loading />}
      {d && (
        <>
          <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11.5px] text-canvas-muted">
            <span>
              <b className="text-canvas-ink">{nf.format(d.people.length)}</b> aktif kişi
            </span>
            {over > 0 && (
              <span className="font-bold text-red-700">
                {nf.format(over)} kişi en az bir hafta kapasitesinin üstünde
              </span>
            )}
            {d.unassigned.tasks > 0 && (
              <button type="button" className="font-bold text-canvas-violet hover:underline" onClick={() => setParams({ bolum: 'paketler' })}>
                {nf.format(d.unassigned.tasks)} görev ({q2(d.unassigned.hours)} saat) atanmayı bekliyor
              </button>
            )}
            <span className="ml-auto flex flex-wrap items-center gap-2">
              <Legend cls={loadTone(0.4)} text="rahat" />
              <Legend cls={loadTone(0.9)} text="%85+" />
              <Legend cls={loadTone(1.2)} text="aşırı" />
              <Legend cls="bg-[repeating-linear-gradient(135deg,#e2e8f0_0_4px,#f8fafc_4px_8px)]" text="müsait değil" />
            </span>
          </div>

          {!d.people.length ? (
            <Empty>{role ? 'Bu rolde aktif kişi yok.' : 'Aktif serbest çalışan yok.'}</Empty>
          ) : (
            <div className="mt-3 overflow-x-auto rounded-2xl border border-slate-100 bg-white/80">
              <table className="w-full min-w-[640px] border-separate border-spacing-0 text-[12px]">
                <thead>
                  <tr>
                    <th className="sticky left-0 z-10 bg-white px-3 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kişi</th>
                    {d.weeks.map((w) => (
                      <th key={w} className={`whitespace-nowrap px-1 py-2 text-center text-[11px] font-bold text-canvas-muted ${w === thisWeek ? 'text-canvas-violet' : ''}`}>
                        {w === thisWeek ? 'Bu hafta' : day(w)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.people.map((p) => (
                    <Fragment key={p.id}>
                      <tr>
                        <th scope="row" className="sticky left-0 z-10 max-w-[200px] border-t border-slate-100 bg-white px-3 py-1.5 text-left font-normal">
                          <button type="button" onClick={() => setOpen(open === p.id ? null : p.id)} aria-expanded={open === p.id} className="block w-full text-left">
                            <span className="block truncate font-bold">{p.name}</span>
                            <span className="block truncate text-[10.5px] text-canvas-muted">
                              {q2(p.weeklyHours)} sa/hafta · {p.active} iş{p.late ? ` · ${p.late} gecikmiş` : ''}
                            </span>
                          </button>
                        </th>
                        {p.weeks.map((w) => (
                          <td key={w.week} className="border-t border-slate-100 p-0.5">
                            <div
                              title={`${day(w.week)} haftası: ${q2(w.load)} / ${q2(w.capacity)} saat${w.away ? ' · müsait olmadığı gün var' : ''}`}
                              className={`flex h-10 flex-col items-center justify-center rounded-lg font-mono tabular-nums leading-tight ${
                                w.capacity === 0 && w.away ? 'bg-[repeating-linear-gradient(135deg,#e2e8f0_0_4px,#f8fafc_4px_8px)] text-canvas-muted' : loadTone(w.ratio)
                              }`}
                            >
                              <span className="text-[12px] font-bold">{w.load ? q2(w.load) : '·'}</span>
                              <span className="text-[9.5px] opacity-80">/{q2(w.capacity)}</span>
                            </div>
                          </td>
                        ))}
                      </tr>
                      {open === p.id && (
                        <tr>
                          <td colSpan={d.weeks.length + 1} className="border-t border-slate-100 bg-slate-50 px-3 py-2">
                            {!p.tasks.length ? (
                              <p className="text-[12px] text-canvas-muted">Elinde iş yok.</p>
                            ) : (
                              <ul className="space-y-1">
                                {p.tasks.map((t) => (
                                  <li key={t.id}>
                                    <button type="button" onClick={() => setParams({ bolum: 'paketler', paket: t.packageId })} className="flex w-full flex-wrap items-center gap-x-2 text-left text-[12px] hover:underline">
                                      <span className="font-bold">{t.title}</span>
                                      <span className="text-canvas-muted">{t.packageTitle}</span>
                                      <span className="font-mono text-[11px] text-canvas-muted">
                                        {day(t.start)} – {day(t.due)} · {q2(t.effortHours)} sa
                                      </span>
                                      <Pill tone={t.late ? 'err' : TASK_STATUS[t.status].tone}>{t.late ? 'Gecikti' : TASK_STATUS[t.status].label}</Pill>
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            )}
                            <p className="mt-1.5 text-[11px] text-canvas-muted">Roller: {p.roles.map((r) => roleLabel(ctx.roles, r)).join(', ')}</p>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
            Hücre: haftadaki iş yükü / kapasite (saat). Görevin tahmini saati başlangıç ile termin arasındaki iş günlerine eşit dağıtılır; resmî tatiller düşülmez.
          </p>
        </>
      )}
    </Panel>
  );
}

function Legend({ cls, text }: { cls: string; text: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block h-3 w-3 rounded ${cls}`} aria-hidden />
      {text}
    </span>
  );
}
