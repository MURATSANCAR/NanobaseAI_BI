import { useEffect, useId, useState, type ReactNode } from 'react';
import { Check } from 'lucide-react';
import { press } from '../shared';
import type { Swatch } from './model';

/** Panellerin ortak denetimleri. Hepsi dokunmaya uygun (≥ 40 px hedef), etiketli ve klavyeyle kullanılır.
 *  Hareket yalnız basışta 0,97 küçülme (shared.press) ve küçük resmin yüklenince belirmesi. */

export const sectionTitle = 'text-[11px] font-bold uppercase tracking-wide text-canvas-muted';

export function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t border-slate-200/70 pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between gap-2">
        <h3 className={sectionTitle}>{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[12px] font-bold text-canvas-ink">{label}</span>
      {children}
    </div>
  );
}

/** Paletten renk seçimi. `auto` verilirse ilk düğme «otomatik» (değer null) olur ve rolün rengini gösterir. */
export function ColorChips({
  label, value, onChange, swatches, auto,
}: {
  label: string;
  value: string | null | undefined;
  onChange: (hex: string | null) => void;
  swatches: Swatch[];
  auto?: { hex: string; name: string };
}) {
  const cur = value ? value.toUpperCase() : null;
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {auto && (
        <button type="button" role="radio" aria-checked={cur === null} onClick={() => onChange(null)}
          title={`Otomatik: ${auto.name}`}
          className={`inline-flex min-h-10 items-center gap-1.5 rounded-full border bg-white/80 py-1 pl-1 pr-2.5 text-[11.5px] font-bold ${press} ${cur === null ? 'border-canvas-violet ring-2 ring-canvas-violet/30' : 'border-slate-200'}`}>
          <span className="h-6 w-6 rounded-full border border-black/10" style={{ background: auto.hex }} aria-hidden />
          Otomatik
        </button>
      )}
      {swatches.map((s) => {
        const on = cur === s.hex.toUpperCase();
        return (
          <button key={s.hex} type="button" role="radio" aria-checked={on} onClick={() => onChange(s.hex)}
            aria-label={`${s.name} (${s.hex})`} title={`${s.name} · ${s.hex}`}
            className={`relative flex h-10 w-10 items-center justify-center rounded-full ${press} ${on ? 'ring-2 ring-canvas-violet ring-offset-2' : ''}`}>
            <span className="h-8 w-8 rounded-full border border-black/10 shadow-sm" style={{ background: s.hex }} aria-hidden />
            {on && <Check className="absolute h-4 w-4 text-white mix-blend-difference" aria-hidden />}
          </button>
        );
      })}
    </div>
  );
}

/** Birden çok renk, sırası önemli (harf harf dönen renkler). */
export function ColorList({ label, value, onChange, swatches }: { label: string; value: string[]; onChange: (v: string[]) => void; swatches: Swatch[] }) {
  const up = value.map((v) => v.toUpperCase());
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-1.5">
      {swatches.map((s) => {
        const i = up.indexOf(s.hex.toUpperCase());
        return (
          <button key={s.hex} type="button" aria-pressed={i >= 0}
            onClick={() => onChange(i >= 0 ? value.filter((_, j) => j !== i) : [...value, s.hex])}
            aria-label={`${s.name} (${s.hex})${i >= 0 ? `, ${i + 1}. sırada` : ''}`} title={s.name}
            className={`relative flex h-10 w-10 items-center justify-center rounded-full ${press} ${i >= 0 ? 'ring-2 ring-canvas-violet ring-offset-2' : 'opacity-70'}`}>
            <span className="h-8 w-8 rounded-full border border-black/10 shadow-sm" style={{ background: s.hex }} aria-hidden />
            {i >= 0 && <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-canvas-violet px-1 font-mono text-[9.5px] font-bold text-white">{i + 1}</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Kaydırıcı + sayı kutusu. Kaydırıcının aralığı yalnız kolaylık; sayı kutusu `hardMin`/`hardMax` dışında sınır koymaz. */
export function Slider({
  label, value, onChange, min, max, step, unit, hardMin, hardMax, format,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  unit?: string;
  hardMin?: number;
  hardMax?: number;
  format?: (v: number) => string;
}) {
  const id = useId();
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const commit = (s: string) => {
    const n = Number(s.replace(',', '.'));
    if (!Number.isFinite(n)) return setDraft(String(value));
    let v = n;
    if (hardMin !== undefined) v = Math.max(hardMin, v);
    if (hardMax !== undefined) v = Math.min(hardMax, v);
    onChange(v);
    setDraft(String(v));
  };
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <label htmlFor={id} className="text-[12px] font-bold text-canvas-ink">{label}</label>
        <span className="flex items-center gap-1">
          <input aria-label={`${label} değeri`} inputMode="decimal" value={draft} onChange={(e) => setDraft(e.target.value)}
            onBlur={(e) => commit(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && commit((e.target as HTMLInputElement).value)}
            className="h-8 w-16 rounded-lg border border-slate-200 bg-white/90 px-2 text-right font-mono text-base tabular-nums outline-none focus:border-canvas-violet sm:text-[12px]" />
          {unit && <span className="w-6 text-[11px] text-canvas-muted">{unit}</span>}
        </span>
      </div>
      <input id={id} type="range" min={min} max={max} step={step} value={Math.min(max, Math.max(min, value))}
        aria-valuetext={format ? format(value) : `${value}${unit ? ` ${unit}` : ''}`}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-10 w-full cursor-pointer accent-canvas-violet" />
    </div>
  );
}

/** Tek seçimli düğme grubu (biçim, font, kalınlık). Dar ekranda alt satıra kayar. */
export function Segmented<T extends string | number>({
  label, value, options, onChange,
}: { label: string; value: T | null | undefined; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button key={String(o.value)} type="button" role="radio" aria-checked={on} onClick={() => onChange(o.value)}
            className={`min-h-10 rounded-xl border px-3 text-[12px] font-bold ${press} ${on ? 'border-canvas-violet bg-violet-50/70 text-canvas-violet ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/80 text-canvas-ink'}`}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      className={`inline-flex min-h-10 items-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-3 text-[12px] font-bold ${press}`}>
      <span className={`relative h-5 w-9 rounded-full transition-colors duration-150 ease-out ${checked ? 'bg-canvas-violet' : 'bg-slate-300'}`} aria-hidden>
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform duration-150 ease-out motion-reduce:transition-none ${checked ? 'translate-x-[18px]' : 'translate-x-0.5'}`} />
      </span>
      {label}
    </button>
  );
}

/** Önizleme küçük resmi: tembel yüklenir, gelince belirir (opaklık 150 ms); gelmezse adı yazar. */
export function Thumb({ src, alt, className = '', fallback }: { src: string; alt: string; className?: string; fallback: string }) {
  const [state, setState] = useState<'loading' | 'ok' | 'fail'>('loading');
  useEffect(() => setState('loading'), [src]);
  return (
    <span className={`relative block overflow-hidden bg-slate-100/80 ${className}`}>
      {state === 'fail' ? (
        <span className="absolute inset-0 flex items-center justify-center p-1 text-center text-[10.5px] leading-tight text-canvas-muted">{fallback}</span>
      ) : (
        <img src={src} alt={alt} loading="lazy" decoding="async" draggable={false}
          onLoad={() => setState('ok')} onError={() => setState('fail')}
          className={`absolute inset-0 h-full w-full object-contain transition-opacity duration-150 ease-out ${state === 'ok' ? 'opacity-100' : 'opacity-0'}`} />
      )}
    </span>
  );
}

/** Yazı değişince önizleme adresi her tuşta değişmesin. */
export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}
