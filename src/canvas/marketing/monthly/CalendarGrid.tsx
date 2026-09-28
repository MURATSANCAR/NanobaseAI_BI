import { AlertTriangle } from 'lucide-react';
import { fmtShortDay } from '../api';
import { TYPE_TONE, type MonthItem, type MonthView } from './api';

/** Hafta × kanal ızgarası. Masaüstünde tablo (ilk sütun yapışık, tablo kendi içinde kayar); telefonda hafta hafta
 *  liste. Çakışan kalem kırmızı çerçeveli; birden çok haftaya yayılan kampanya her haftasında görünür. */

const ROW_LAUNCH = '_lansman';
const ROW_DAY = '_ozel-gun';

const rowOf = (x: MonthItem) => x.kanal ?? (x.tur === 'ozel-gun' ? ROW_DAY : ROW_LAUNCH);
const inWeek = (x: MonthItem, w: { baslangic: string; bitis: string }) =>
  !!x.baslangic && x.baslangic <= w.bitis && (x.bitis ?? x.baslangic) >= w.baslangic;

function Chip({ x, onPick }: { x: MonthItem; onPick: (x: MonthItem) => void }) {
  const hot = x.cakisma.length > 0;
  return (
    <button
      type="button"
      onClick={() => onPick(x)}
      title={hot ? x.cakisma.map((c) => `${c.neden}: ${c.ileAd.join(', ')}`).join(' · ') : x.kaynakAdi}
      className={`flex min-h-9 w-full items-start gap-1 rounded-lg px-2 py-1 text-left text-[11.5px] font-bold leading-snug transition-transform duration-150 ease-out active:scale-[0.97] ${TYPE_TONE[x.tur]} ${hot ? 'ring-2 ring-red-500' : ''}`}
    >
      {hot && <AlertTriangle aria-label="Çakışma" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" />}
      <span className="min-w-0 break-words">
        {x.baslik}
        {x.tur === 'yeni' && x.kaynak === 'crm-kitap' && x.baslangic && <span className="ml-1 font-mono font-semibold opacity-70">{fmtShortDay(x.baslangic).slice(0, 5)}</span>}
        {x.detay.sapma && <span className="ml-1 rounded bg-red-100 px-1 text-[10px] text-red-700">hedef altı</span>}
        {x.elle && <span className="ml-1 text-[10px] font-semibold opacity-70">· elle</span>}
      </span>
    </button>
  );
}

export default function CalendarGrid({ view, channels, onPick }: { view: MonthView; channels: Record<string, string>; onPick: (x: MonthItem) => void }) {
  const rowsPresent = new Set(view.items.map(rowOf));
  const order = [ROW_LAUNCH, ...Object.keys(channels), ROW_DAY].filter((k) => rowsPresent.has(k));
  const rowLabel = (k: string) => (k === ROW_LAUNCH ? 'Yeni kitap lansmanı' : k === ROW_DAY ? 'Özel gün' : channels[k] ?? k);

  if (view.items.length === 0) {
    return <p className="py-6 text-[12.5px] text-canvas-muted">Bu ayın takviminde kalem yok. Taslak kurulunca CRM yayın tarihleri, onaylı planlar, özel günler ve CRM kampanyaları buraya gelir.</p>;
  }

  return (
    <>
      <div className="hidden overflow-x-auto rounded-2xl border border-slate-100 bg-white/80 md:block">
        <table className="w-full min-w-[860px] border-collapse text-[12px]">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 w-[150px] bg-white px-3 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kanal</th>
              {view.weeks.map((w) => (
                <th key={w.hafta} className="px-2 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                  {fmtShortDay(w.baslangic).slice(0, 5)}–{fmtShortDay(w.bitis).slice(0, 5)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {order.map((k) => (
              <tr key={k} className="border-t border-slate-100 align-top">
                <th scope="row" className="sticky left-0 z-10 bg-white px-3 py-2 text-left text-[12px] font-extrabold">{rowLabel(k)}</th>
                {view.weeks.map((w) => (
                  <td key={w.hafta} className="px-1.5 py-1.5">
                    <div className="flex flex-col gap-1">
                      {view.items.filter((x) => rowOf(x) === k && inWeek(x, w)).map((x) => <Chip key={x.id} x={x} onPick={onPick} />)}
                    </div>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-col gap-3 md:hidden">
        {view.weeks.map((w) => {
          const xs = view.items.filter((x) => inWeek(x, w));
          return (
            <section key={w.hafta}>
              <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
                {fmtShortDay(w.baslangic).slice(0, 5)}–{fmtShortDay(w.bitis).slice(0, 5)} · {xs.length} kalem
              </h3>
              {xs.length === 0 ? (
                <p className="text-[12px] text-canvas-muted">Kalem yok.</p>
              ) : (
                <div className="flex flex-col gap-1">
                  {xs.map((x) => (
                    <div key={x.id} className="flex flex-col gap-0.5">
                      <span className="text-[10.5px] font-semibold text-canvas-muted">{rowLabel(rowOf(x))}</span>
                      <Chip x={x} onPick={onPick} />
                    </div>
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
