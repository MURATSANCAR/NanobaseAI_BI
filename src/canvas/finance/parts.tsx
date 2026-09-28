import type { ReactNode } from 'react';
import { CalendarClock } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { fmtDay, fmtMoney2, type Freshness } from './api';

/** Finansal raporların ortak parçaları: kabuk, veri son günü şeridi, «yaklaşık» rozeti, tutar hücresi. */

export function FinanceFrame({ source, presence, aside, children }: { source: string; presence: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Finans ve risk', crumb: 'Finansal raporlar', source, presence }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Finans ve risk · Raporlama ve analiz</div>
                <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Finansal raporlar</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">
                  Logo muhasebesinden aylık gelir tablosu, bütçe–gerçekleşme, kitap ve kanal kârlılığı, 13 haftalık nakit ve vergi takvimi.
                  Her rakam Logo fişine iner; yaklaşık olan rakamın yanında yazar.
                </p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Her sekmenin üstünde: veri son günü. Donmuş kopyada «bugün» değil, bu tarih geçerlidir. */
export function DataEnd({ data, extra }: { data: Freshness | null | undefined; extra?: ReactNode }) {
  if (!data) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl bg-slate-50 px-3 py-2 text-[12px] font-semibold text-canvas-muted">
      <CalendarClock aria-hidden className="h-4 w-4 shrink-0 text-canvas-violet" />
      <span>
        Veri son günü <strong className="text-canvas-ink">{fmtDay(data.veriSonu)}</strong>
      </span>
      {data.maliyetSonu && <span>Maliyeti işlenmiş son satış {fmtDay(data.maliyetSonu)}</span>}
      {data.muhasebeSonu && <span>Son muhasebe kaydı {fmtDay(data.muhasebeSonu)}</span>}
      {extra}
    </div>
  );
}

export function Approx({ title }: { title?: string }) {
  return (
    <span title={title} className="inline-flex shrink-0 items-center rounded-md bg-amber-50 px-1.5 py-0.5 text-[10.5px] font-bold uppercase tracking-wide text-amber-800">
      yaklaşık
    </span>
  );
}

/** Tutar hücresi: eksi kırmızı, iki hane, tabular. */
export function Money({ v, strong }: { v: number | null | undefined; strong?: boolean }) {
  const neg = typeof v === 'number' && v < 0;
  return <span className={`font-mono tabular-nums ${neg ? 'text-red-700' : ''} ${strong ? 'font-bold' : ''}`}>{fmtMoney2(v)}</span>;
}

/** Tıklanabilir satır/hücre için ortak sınıf: dokunma hedefi ve basış geri bildirimi. */
export const pressable = 'transition-transform duration-150 ease-out active:scale-[0.98]';

/** Özet kutusu (tıklanmaz): etiket, değer, alt not; «i» sağ üstte (`info`). Kârlılık ve nakit özetleri. */
export function SumCard({ label, value, note, info, tone = '' }: { label: ReactNode; value: ReactNode; note?: ReactNode; info?: ReactNode; tone?: string }) {
  return (
    <div className="relative rounded-2xl bg-white/80 p-3">
      <div className={`flex items-center gap-1 text-[11px] font-bold uppercase text-canvas-muted ${info ? 'pr-6' : ''}`}>{label}</div>
      <div className={`mt-1 font-mono text-[20px] font-bold tabular-nums ${tone}`}>{value}</div>
      {note && <div className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{note}</div>}
      {info && <span className="absolute right-2.5 top-2.5">{info}</span>}
    </div>
  );
}
