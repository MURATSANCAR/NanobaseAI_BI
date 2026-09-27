import { useEffect, useRef, useState, type ReactNode } from 'react';
import { queryOptions, useQueryClient } from '@tanstack/react-query';
import { X } from 'lucide-react';
import { ENGINE_ENABLED, freelanceApi, type FlOverview, type FlPayoutHead, type FlRole, type FlTaskStatus } from '../../engine';
import { btnGhost, label as labelCls } from '../../admin/ui';

/** Serbest çalışanlar ekranının ortak parçaları: etiketler, biçimler, sekmeler, küçük form öğeleri. */

export const flOverviewOptions = () =>
  queryOptions({ queryKey: ['fl', 'overview'], queryFn: freelanceApi.overview, enabled: ENGINE_ENABLED, staleTime: 30_000 });

/** Bir değişiklikten sonra ekranın bütün serbest çalışan verisi tazelenir (sayılar birbirine bağlı). */
export function useFlRefresh() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ['fl'] });
}

const money2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qty = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
export const tl = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? '—' : `${money2.format(v)} ₺`);
/** Kullanıcının yazdığı sayı: virgül varsa Türkçe yazım (1.250,50), yoksa düz (1250.5). Boşsa NaN. */
export const parseNum = (raw: string | number | null | undefined): number => {
  const s = String(raw ?? '').trim().replace(/\s|₺/g, '');
  if (!s) return NaN;
  return Number(s.includes(',') ? s.replace(/\./g, '').replace(',', '.') : s);
};
/** Sayıyı düzenleme kutusuna Türkçe ondalıkla koyar (1250,5). */
export const editNum = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? '' : String(v).replace('.', ','));
export const pctText = (v: number | null | undefined) => (v == null ? '—' : `%${Math.round(v * 100)}`);
export const q2 = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? '—' : qty.format(v));

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', timeZone: 'UTC' });
const dayYearFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
/** "2026-10-09" → "9 Eki"; başka yıldaysa yılıyla. */
export const day = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return (d.getUTCFullYear() === new Date().getFullYear() ? dayFmt : dayYearFmt).format(d);
};
const stampFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });
export const stamp = (iso: string | null | undefined) => (iso ? stampFmt.format(new Date(iso)) : '—');

/** İstanbul'a göre bugünün tarihi (YYYY-AA-GG). */
export const todayIso = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul' }).format(new Date());

export const TASK_STATUS: Record<FlTaskStatus, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  atanmadi: { label: 'Atanmadı', tone: 'muted' },
  atandi: { label: 'Atandı', tone: 'violet' },
  calisiyor: { label: 'Çalışıyor', tone: 'violet' },
  teslim: { label: 'İnceleme bekliyor', tone: 'warn' },
  revizyon: { label: 'Revizyonda', tone: 'warn' },
  onaylandi: { label: 'Kabul edildi', tone: 'ok' },
  iptal: { label: 'İptal', tone: 'err' },
};

export const PAYOUT_STATUS: Record<FlPayoutHead['status'], { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  taslak: { label: 'Taslak', tone: 'muted' },
  onay: { label: 'Onay bekliyor', tone: 'warn' },
  onaylandi: { label: 'Onaylandı', tone: 'violet' },
  odendi: { label: 'Ödendi', tone: 'ok' },
};

export const roleLabel = (roles: FlRole[] | undefined, key: string) => roles?.find((r) => r.key === key)?.label ?? key;

export type FlCtx = { ov: FlOverview; roles: FlRole[]; units: string[]; canManage: boolean; canApprove: boolean };

/** Ekran içi bölüm sekmeleri; telefonda yatay kayar. */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
}: {
  items: Array<{ key: T; label: string; badge?: number }>;
  value: T;
  onChange: (k: T) => void;
}) {
  return (
    <div className="-mx-1 overflow-x-auto px-1 [scrollbar-width:none]" role="tablist" aria-label="Bölüm">
      <div className="inline-flex min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
        {items.map((it) => (
          <button
            key={it.key}
            type="button"
            role="tab"
            aria-selected={value === it.key}
            onClick={() => onChange(it.key)}
            className={`inline-flex min-h-11 flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-[background-color,color,transform] duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${
              value === it.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
            }`}
          >
            {it.label}
            {!!it.badge && (
              <span
                className={`min-w-5 rounded-full px-1.5 font-mono text-[10.5px] tabular-nums leading-5 ${value === it.key ? 'bg-white/25' : 'bg-canvas-coral text-white'}`}
              >
                {it.badge}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

export function FieldBox({ label, hint, children, className = '' }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={`block min-w-0 ${className}`}>
      <span className={labelCls}>{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{hint}</span>}
    </label>
  );
}

/** Virgül ya da Enter ile etiket ekleme; Backspace son etiketi siler. */
export function TagInput({ value, onChange, placeholder, max = 20 }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; max?: number }) {
  const [text, setText] = useState('');
  const add = (raw: string) => {
    const t = raw.trim().replace(/\s+/g, ' ').slice(0, 40);
    if (!t || value.some((v) => v.toLocaleLowerCase('tr') === t.toLocaleLowerCase('tr')) || value.length >= max) return;
    onChange([...value, t]);
  };
  return (
    <div className="flex min-h-11 flex-wrap items-center gap-1.5 rounded-xl border border-slate-200 bg-white/90 px-2 py-1.5 focus-within:border-canvas-violet sm:min-h-9">
      {value.map((v) => (
        <span key={v} className="inline-flex items-center gap-1 rounded-lg bg-canvas-violet/10 py-0.5 pl-2 pr-1 text-[12px] font-bold text-canvas-violet">
          {v}
          <button type="button" aria-label={`${v} etiketini kaldır`} onClick={() => onChange(value.filter((x) => x !== v))} className="rounded p-0.5 hover:bg-canvas-violet/15">
            <X aria-hidden className="h-3 w-3" />
          </button>
        </span>
      ))}
      <input
        value={text}
        onChange={(e) => {
          const v = e.target.value;
          if (v.includes(',')) {
            v.split(',').slice(0, -1).forEach(add);
            setText(v.split(',').pop() ?? '');
          } else setText(v);
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            add(text);
            setText('');
          } else if (e.key === 'Backspace' && !text && value.length) onChange(value.slice(0, -1));
        }}
        onBlur={() => {
          add(text);
          setText('');
        }}
        placeholder={value.length ? '' : placeholder}
        className="min-w-[8rem] flex-1 bg-transparent px-1 text-base font-semibold outline-none sm:text-[12.5px]"
      />
    </div>
  );
}

/** Geri alınamayan işlem için iki adımlı düğme: ilk basış sorar, 4 sn içinde ikinci basış yapar. */
export function ConfirmButton({
  children,
  confirm,
  onConfirm,
  className = btnGhost,
  disabled,
}: {
  children: ReactNode;
  confirm: string;
  onConfirm: () => void;
  className?: string;
  disabled?: boolean;
}) {
  const [armed, setArmed] = useState(false);
  const timer = useRef<number>();
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return (
    <button
      type="button"
      disabled={disabled}
      className={`${className} ${armed ? '!bg-red-600 !text-white' : ''}`}
      onClick={() => {
        if (armed) {
          window.clearTimeout(timer.current);
          setArmed(false);
          onConfirm();
          return;
        }
        setArmed(true);
        timer.current = window.setTimeout(() => setArmed(false), 4000);
      }}
    >
      {armed ? confirm : children}
    </button>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-10 text-center text-[12.5px] leading-snug text-canvas-muted">{children}</p>;
}

/** Doluluk oranı → renk. 0,85'e kadar rahat, 1'e kadar dolu, üstü aşırı yük. */
export function loadTone(ratio: number | null | undefined): string {
  if (ratio == null) return 'bg-slate-100 text-canvas-muted';
  if (ratio > 1) return 'bg-red-500 text-white';
  if (ratio >= 0.85) return 'bg-amber-400 text-canvas-ink';
  if (ratio > 0) return 'bg-emerald-400/80 text-canvas-ink';
  return 'bg-emerald-50 text-emerald-700';
}
