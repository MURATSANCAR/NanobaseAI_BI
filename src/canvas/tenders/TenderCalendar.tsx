import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CalendarClock, FileCheck2, Landmark, ShieldCheck } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay, tendersApi, type CalendarEvent } from './api';
import { LeftPill } from './parts';
import SqlInfo from '../components/SqlInfo';

/** Son teklif tarihleri, belge geçerlilik bitişleri ve teminat iadeleri tek takvimde (tarihe göre). Süresi geçmiş
 *  ama hâlâ açık olanlar da görünür. */

const KIND: Record<CalendarEvent['tur'], { label: string; icon: typeof Landmark }> = {
  son_teklif: { label: 'Son teklif', icon: Landmark },
  belge: { label: 'Belge geçerliliği', icon: FileCheck2 },
  ihale_belgesi: { label: 'İhale belgesi', icon: FileCheck2 },
  teminat_iade: { label: 'Teminat iadesi', icon: ShieldCheck },
};

export default function TenderCalendar() {
  const [gun, setGun] = useState(90);
  const cal = useQuery({ queryKey: ['tenders', 'calendar', gun], queryFn: () => tendersApi.calendar(gun), enabled: ENGINE_ENABLED });
  const items = cal.data?.items ?? [];
  const groups = new Map<string, CalendarEvent[]>();
  for (const e of items) {
    const key = e.tarih.slice(0, 7);
    groups.set(key, [...(groups.get(key) ?? []), e]);
  }
  const monthFmt = new Intl.DateTimeFormat('tr-TR', { month: 'long', year: 'numeric' });
  return (
    <Panel>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[16px] font-extrabold tracking-tight">Takvim</h2>
          <p className="text-[12px] text-canvas-muted">Hatırlatmalar her sabah iç ekibe tek e-postayla gider (son teklife 7 ve 2 gün kala, belge bitişine 30 gün kala).</p>
        </div>
        <label className="flex w-40 flex-col gap-1">
          <span className={labelCls}>Önümüzdeki</span>
          <select className={field} value={gun} onChange={(e) => setGun(Number(e.target.value))}>
            {[30, 60, 90, 180, 365].map((d) => <option key={d} value={d}>{d} gün</option>)}
          </select>
        </label>
      </div>
      {cal.error && <div className="mt-3"><Note tone="err">{errText(cal.error, 'Takvim okunamadı.')}</Note></div>}
      {cal.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
      {cal.data && !items.length && <div className="py-8 text-center text-[12.5px] text-canvas-muted">Bu aralıkta tarih yok.</div>}
      <div className="mt-3 flex flex-col gap-4">
        {[...groups.entries()].map(([month, evs]) => (
          <section key={month}>
            <h3 className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{monthFmt.format(new Date(`${month}-01T00:00:00`))}</h3>
            <ul className="flex flex-col gap-1.5">
              {evs.map((e, i) => {
                const K = KIND[e.tur];
                const body = (
                  <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1">
                    <span className="w-28 shrink-0 font-mono text-[12px] font-bold tabular-nums">{fmtDay(e.tarih)}</span>
                    <span className="inline-flex shrink-0 items-center gap-1 text-[11px] font-bold text-canvas-muted">
                      <K.icon aria-hidden className="h-3.5 w-3.5" />
                      {K.label}
                    </span>
                    <span className="min-w-0 flex-1 break-words text-[12.5px] font-semibold">{e.baslik}</span>
                    {e.onayBekliyor && <Pill tone="warn">Onay bekliyor</Pill>}
                    <LeftPill days={e.kalanGun} />
                  </div>
                );
                return (
                  <li key={`${e.tur}-${e.tarih}-${i}`}>
                    {e.ihaleId ? (
                      <Link to={`/ihale/${e.ihaleId}`} className="flex items-center gap-2 rounded-xl border border-slate-100 bg-white/80 px-3 py-2 transition-colors duration-150 hover:border-canvas-violet/40">
                        {body}
                      </Link>
                    ) : (
                      <div className="flex items-center gap-2 rounded-xl border border-slate-100 bg-white/80 px-3 py-2">{body}</div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
      {cal.data && (
        <div className="mt-3 flex items-center gap-1.5 text-[11.5px] text-canvas-muted">
          <CalendarClock aria-hidden className="h-3.5 w-3.5" />
          {items.length} tarih · bugün {fmtDay(cal.data.bugun)}
          <SqlInfo k={cal.data.kaynaklar} alan="items[]" label="Takvim tarihleri ve kalan gün" />
        </div>
      )}
    </Panel>
  );
}
