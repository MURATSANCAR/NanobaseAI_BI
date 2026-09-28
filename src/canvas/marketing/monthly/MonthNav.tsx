import { ChevronLeft, ChevronRight } from 'lucide-react';
import { monthLabel, shiftMonth } from './api';

/** Ay seçici: önceki / sonraki ay ve ay alanı (telefonda da 44 px dokunma alanı). */
export default function MonthNav({ value, onChange }: { value: string; onChange: (ay: string) => void }) {
  const btn = 'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-canvas-ink transition-transform duration-150 ease-out hover:bg-slate-200 active:scale-[0.97] sm:h-9 sm:w-9';
  return (
    <div className="flex items-center gap-2">
      <button type="button" className={btn} aria-label="Önceki ay" onClick={() => onChange(shiftMonth(value, -1))}>
        <ChevronLeft aria-hidden className="h-4 w-4" />
      </button>
      <label className="relative flex min-w-0 flex-1 items-center">
        <span className="sr-only">Ay</span>
        <input
          type="month"
          className="h-11 w-full rounded-xl border border-slate-200 bg-white/90 px-3 text-base font-extrabold outline-none focus:border-canvas-violet sm:h-9 sm:text-[13px]"
          value={value}
          onChange={(e) => e.target.value && onChange(e.target.value)}
          aria-label={`Seçili ay: ${monthLabel(value)}`}
        />
      </label>
      <button type="button" className={btn} aria-label="Sonraki ay" onClick={() => onChange(shiftMonth(value, 1))}>
        <ChevronRight aria-hidden className="h-4 w-4" />
      </button>
    </div>
  );
}
