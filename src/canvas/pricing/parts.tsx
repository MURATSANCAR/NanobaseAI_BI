import { useEffect, useState, type ReactNode } from 'react';
import { field, label as labelCls } from '../admin/ui';
import { editNum, editPct, parseNum, parsePct } from './api';

/** Fiyatlama ekranının küçük form parçaları. */

/** Sayı kutusu: Türkçe yazım (1.250,50) kabul eder; odaktan çıkınca biçimlenir. `percent` ise 0,15 ↔ 15 gösterir. */
export function NumField({
  label,
  value,
  onChange,
  hint,
  suffix,
  percent,
  digits = 2,
  disabled,
  placeholder,
  info,
}: {
  label: string;
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  hint?: ReactNode;
  suffix?: string;
  percent?: boolean;
  digits?: number;
  disabled?: boolean;
  placeholder?: string;
  /** Kutuya gelen önerilen değerin sorgu bilgisi (`<SqlInfo …/>`); etiketin yanında. */
  info?: ReactNode;
}) {
  const show = (v: number | null | undefined) => (percent ? editPct(v) : editNum(v, digits));
  const [text, setText] = useState(show(value));
  const [focused, setFocused] = useState(false);
  useEffect(() => {
    if (!focused) setText(show(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, focused]);
  return (
    <label className="block min-w-0">
      {info ? <span className={`${labelCls} flex items-center gap-1`}>{label}{info}</span> : <span className={labelCls}>{label}</span>}
      <div className="relative mt-1">
        <input
          inputMode="decimal"
          className={`${field} tabular-nums ${suffix ? 'pr-9' : ''}`}
          value={text}
          disabled={disabled}
          placeholder={placeholder}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onChange={(e) => {
            setText(e.target.value);
            onChange(percent ? parsePct(e.target.value) : parseNum(e.target.value));
          }}
        />
        {suffix && <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] font-bold text-canvas-muted">{suffix}</span>}
      </div>
      {hint && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{hint}</span>}
    </label>
  );
}

export function Group({ title, help, children, step, info }: { title: string; help?: ReactNode; children: ReactNode; step?: number; info?: ReactNode }) {
  return (
    <fieldset className="min-w-0 rounded-2xl border border-slate-100 bg-white/70 p-3 sm:p-4">
      <legend className="flex items-center gap-1.5 px-1 text-[12px] font-extrabold uppercase tracking-wide text-canvas-ink">
        {step != null && (
          <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-canvas-violet text-[11px] font-extrabold text-white tabular-nums">{step}</span>
        )}
        {title}
        {info}
      </legend>
      {help && <p className="-mt-1 mb-2 text-[11.5px] leading-snug text-canvas-muted">{help}</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</div>
    </fieldset>
  );
}

/** Büyük sayı + küçük açıklama. */
/** `info`: rakamın sorgu bilgisi düğmesi (`<SqlInfo …/>`), etiketin yanında. */
export function Stat({ label, value, note, tone, info }: { label: string; value: ReactNode; note?: ReactNode; tone?: 'ok' | 'warn' | 'err'; info?: ReactNode }) {
  const color = tone === 'ok' ? 'text-emerald-700' : tone === 'warn' ? 'text-amber-700' : tone === 'err' ? 'text-red-600' : '';
  return (
    <div className="min-w-0 rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className={`${labelCls} flex items-center gap-1`}>{label}{info}</div>
      <div className={`mt-1 font-mono text-[20px] font-bold leading-tight tabular-nums sm:text-[22px] ${color}`}>{value}</div>
      {note && <div className="mt-1 text-[11.5px] leading-snug text-canvas-muted">{note}</div>}
    </div>
  );
}

/** Seçim kutusu (yerel select; telefonda sistem seçicisi açılır). `info`: etiketin yanındaki «i». */
export function Select<T extends string>({ label, value, onChange, options, hint, info, disabled }: {
  label: string;
  value: T;
  onChange: (v: T) => void;
  options: Array<{ value: T; label: string }>;
  hint?: ReactNode;
  info?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className="block min-w-0">
      {info ? <span className={`${labelCls} flex items-center gap-1`}>{label}{info}</span> : <span className={labelCls}>{label}</span>}
      <select className={`${field} mt-1`} value={value} disabled={disabled} onChange={(e) => onChange(e.target.value as T)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {hint && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{hint}</span>}
    </label>
  );
}

/** «1000, 2000, 3000» → [1000, 2000, 3000]; bozuk parça atlanır. */
export const parseQtys = (text: string): number[] =>
  [...new Set(text.split(/[;,\s]+/).map((t) => parseNum(t.replace(/\./g, ''))).filter((v): v is number => v != null && v > 0).map(Math.round))].sort(
    (a, b) => a - b,
  );

/** Aç/kapa kutusu (işaret kutusu; telefonda 44 px dokunma alanı). */
export function Toggle({ label, checked, onChange, info, hint, disabled }: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  info?: ReactNode;
  hint?: ReactNode;
  disabled?: boolean;
}) {
  return (
    <div className="min-w-0">
      <label className="flex min-h-11 cursor-pointer items-center gap-2.5 rounded-xl border border-slate-100 bg-white px-3 py-2 sm:min-h-10">
        <input
          type="checkbox"
          className="h-4 w-4 shrink-0 accent-canvas-violet"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span className="min-w-0 flex-1 text-[12.5px] font-bold leading-snug text-canvas-ink">{label}</span>
        {info}
      </label>
      {hint && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{hint}</span>}
    </div>
  );
}

/** Metin kutusu (seçenek listesiyle öneri: `list`). */
export function TextField({ label, value, onChange, info, hint, placeholder, list, disabled }: {
  label: string;
  value: string | null | undefined;
  onChange: (v: string) => void;
  info?: ReactNode;
  hint?: ReactNode;
  placeholder?: string;
  list?: string[];
  disabled?: boolean;
}) {
  const id = `dl-${label.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <label className="block min-w-0">
      {info ? <span className={`${labelCls} flex items-center gap-1`}>{label}{info}</span> : <span className={labelCls}>{label}</span>}
      <input className={`${field} mt-1`} value={value ?? ''} placeholder={placeholder} disabled={disabled} list={list ? id : undefined}
        onChange={(e) => onChange(e.target.value)} />
      {list && (
        <datalist id={id}>
          {list.map((o) => (
            <option key={o} value={o} />
          ))}
        </datalist>
      )}
      {hint && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{hint}</span>}
    </label>
  );
}
