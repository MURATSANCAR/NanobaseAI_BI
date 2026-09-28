import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { CalendarRow } from '../../engine';
import { Note, btnGhost, errText, nf } from '../../admin/ui';
import { Panel } from '../kit';
import { assignCalendarOptions } from '../queries';
import { addDays, day, daysBetween, shortDay, todayIso } from './parts';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';

/** 12 haftalık takvim: editör başına görev çubukları (başlangıç → termin), izinler ve çakışma aralıkları.
 *  Çakışma: eşzamanlı açık görev kapasiteyi aşıyor ya da izinli günde açık görev var. Termini olmayan görev
 *  pencerenin sonuna kadar uzar (kapasiteyi tutar). Geniş ızgara yalnız kendi kutusunda yatay kayar. */

const WEEKS = 12;
const DAY_PX = 11;

function monday(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  const wd = (d.getUTCDay() + 6) % 7;
  return addDays(iso, -wd);
}

type Bar = CalendarRow['tasks'][number] & { lane: number; x: number; w: number; open: boolean };

function lanes(row: CalendarRow, start: string, days: number): { bars: Bar[]; count: number } {
  const ends: number[] = [];
  const bars: Bar[] = [];
  const sorted = [...row.tasks].sort((a, b) => a.from.localeCompare(b.from));
  for (const t of sorted) {
    const x0 = Math.max(0, daysBetween(start, t.from));
    const x1 = t.to ? Math.min(days - 1, daysBetween(start, t.to)) : days - 1;
    let lane = ends.findIndex((e) => e < x0);
    if (lane < 0) {
      lane = ends.length;
      ends.push(x1);
    } else ends[lane] = x1;
    bars.push({ ...t, lane, x: x0 * DAY_PX, w: Math.max(1, x1 - x0 + 1) * DAY_PX, open: !t.to });
  }
  return { bars, count: Math.max(1, ends.length) };
}

function span(from: string, to: string, start: string, days: number) {
  const x0 = Math.max(0, daysBetween(start, from));
  const x1 = Math.min(days - 1, daysBetween(start, to));
  return { left: x0 * DAY_PX, width: Math.max(1, x1 - x0 + 1) * DAY_PX };
}

export default function CalendarTab() {
  const [start, setStart] = useState(() => monday(todayIso()));
  const days = WEEKS * 7;
  const end = addDays(start, days - 1);
  const q = useQuery(assignCalendarOptions(start, end));
  const d = q.data;
  const today = d?.today ?? todayIso();
  const todayX = daysBetween(start, today);
  const rows = useMemo(() => (d?.items ?? []).map((r) => ({ r, ...lanes(r, start, days) })), [d, start, days]);
  const conflicted = (d?.items ?? []).filter((r) => r.conflicts.length).length;
  const err = errText(q.error, 'Takvim okunamadı.');
  const width = days * DAY_PX;

  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 text-[13px] font-extrabold">
            Takvim ve çakışmalar
            <SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Takvim ve çakışmalar" />
          </h2>
          <p className="text-[11.5px] text-canvas-muted">
            {day(start)} – {day(end)}
            {d && ` · ${nf.format(d.items.length)} editör`}
            {conflicted > 0 && <span className="font-bold text-red-600"> · {nf.format(conflicted)} editörde çakışma</span>}
          </p>
        </div>
        <div className="flex gap-1.5">
          <button type="button" className={btnGhost} onClick={() => setStart(addDays(start, -28))} aria-label="Dört hafta geri">
            <ChevronLeft aria-hidden className="h-4 w-4" />
          </button>
          <button type="button" className={btnGhost} onClick={() => setStart(monday(todayIso()))}>
            Bu hafta
          </button>
          <button type="button" className={btnGhost} onClick={() => setStart(addDays(start, 28))} aria-label="Dört hafta ileri">
            <ChevronRight aria-hidden className="h-4 w-4" />
          </button>
        </div>
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 px-1 text-[11px] text-canvas-muted">
        <li className="flex items-center gap-1.5"><span aria-hidden className="h-2.5 w-4 rounded-sm bg-canvas-violet/70" />Görev</li>
        <li className="flex items-center gap-1.5"><span aria-hidden className="h-2.5 w-4 rounded-sm bg-red-500/80" />Gecikmiş</li>
        <li className="flex items-center gap-1.5"><span aria-hidden className="h-2.5 w-4 rounded-sm bg-amber-300" />İzin</li>
        <li className="flex items-center gap-1.5"><span aria-hidden className="h-2.5 w-4 rounded-sm bg-red-100 ring-1 ring-red-300" />Çakışma</li>
        <li>Terminsiz görev pencere sonuna uzar.</li>
      </ul>
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Takvim okunuyor…</p>}
      {d && !d.items.length && (
        <p className="py-10 text-center text-[12.5px] text-canvas-muted">Takvimde gösterilecek görev ya da izin yok. Atama yapıldıkça editörler burada görünür.</p>
      )}
      {rows.length > 0 && (
        <div className="mt-3 overflow-x-auto overscroll-x-contain rounded-2xl border border-slate-100 bg-white" role="region" aria-label="Editör takvimi" tabIndex={0}>
          <div className="grid" style={{ gridTemplateColumns: `minmax(120px,160px) ${width}px` }}>
            <div className="sticky left-0 z-10 border-b border-r border-slate-100 bg-white px-2 py-1.5 text-[11px] font-bold text-canvas-muted">Editör</div>
            <div className="relative h-8 border-b border-slate-100">
              {Array.from({ length: WEEKS }, (_, w) => (
                <div key={w} className="absolute top-0 h-full border-l border-slate-100 px-1 pt-1.5 text-[10.5px] font-semibold text-canvas-muted" style={{ left: w * 7 * DAY_PX, width: 7 * DAY_PX }}>
                  {shortDay(addDays(start, w * 7))}
                </div>
              ))}
            </div>
            {rows.map(({ r, bars, count }) => (
              <div key={r.id} className="contents">
                <div className="sticky left-0 z-10 border-b border-r border-slate-100 bg-white px-2 py-1.5 text-[12px]">
                  <div className="break-words font-extrabold leading-tight">{r.name || 'Adı kayıtlı değil'}</div>
                  <div className="text-[10.5px] text-canvas-muted">
                    {r.capacity ? `${nf.format(r.load.open)}/${nf.format(r.capacity)}` : `${nf.format(r.load.open)} görev`}
                  </div>
                </div>
                <div className="relative border-b border-slate-100" style={{ height: 10 + count * 22 }}>
                  {Array.from({ length: WEEKS }, (_, w) => (
                    <div key={w} aria-hidden className="absolute top-0 h-full border-l border-slate-50" style={{ left: w * 7 * DAY_PX }} />
                  ))}
                  {r.conflicts.map((c, i) => (
                    <div
                      key={`c${i}`}
                      className="absolute top-0 h-full bg-red-100/80 ring-1 ring-inset ring-red-300"
                      style={span(c.from, c.to, start, days)}
                      title={`${c.kind === 'kapasite' ? `Kapasite aşımı (en çok ${c.max} görev)` : 'İzinli günde açık görev'}: ${day(c.from)} – ${day(c.to)}`}
                    />
                  ))}
                  {r.absences.map((a) => (
                    <div
                      key={a.id}
                      className="absolute bottom-0 h-1.5 rounded-sm bg-amber-300"
                      style={span(a.start < start ? start : a.start, a.end > end ? end : a.end, start, days)}
                      title={`İzin ${day(a.start)} – ${day(a.end)}${a.reason ? ` · ${a.reason}` : ''}`}
                    />
                  ))}
                  {bars.map((b) => (
                    <div
                      key={b.id}
                      className={`absolute h-[18px] overflow-hidden whitespace-nowrap rounded-md px-1.5 text-[10.5px] font-bold leading-[18px] text-white ${b.overdue ? 'bg-red-500/85' : 'bg-canvas-violet/75'} ${b.open ? 'rounded-r-none' : ''}`}
                      style={{ left: b.x, width: b.w, top: 4 + b.lane * 22 }}
                      title={`${b.projectName ?? ''} · ${b.statusLabel} · ${day(b.start)} → ${b.due ? day(b.due) : 'termin yok'}`}
                    >
                      {b.projectName}
                    </div>
                  ))}
                  {todayX >= 0 && todayX < days && <div aria-hidden className="absolute top-0 h-full w-px bg-canvas-coral" style={{ left: todayX * DAY_PX + DAY_PX / 2 }} />}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {rows.some(({ r }) => r.conflicts.length) && (
        <ul className="mt-3 space-y-1 px-1 text-[12px]">
          {rows
            .filter(({ r }) => r.conflicts.length)
            .map(({ r }) => (
              <li key={r.id}>
                <span className="font-extrabold">{r.name}</span>:{' '}
                {r.conflicts
                  .map((c) => `${day(c.from)} – ${day(c.to)} ${c.kind === 'kapasite' ? `kapasite aşımı (${c.max}/${r.capacity})` : 'izinli günde açık görev'}`)
                  .join(' · ')}
              </li>
            ))}
        </ul>
      )}
    </Panel>
  );
}
