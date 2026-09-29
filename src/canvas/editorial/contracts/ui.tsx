import { useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import { EngineAuthError, EngineForbiddenError } from '../../engine';
import type { Status } from './api';
import { Explain } from '../../components/Explain';
import { normalizeTrNumber } from '../../components/trNumber';

/** M6 Sözleşmeler ekranlarının ortak parçaları: biçimler, durum rengi, alttan açılan form kartı. */

const numFmt = (d: number) => new Intl.NumberFormat('tr-TR', { maximumFractionDigits: d, minimumFractionDigits: 0 });
export const num = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? '—' : numFmt(d).format(v));
const CUR: Record<string, string> = { TRY: '₺', USD: '$', EUR: '€', GBP: '£', CNY: '¥' };
export const money = (v: number | null | undefined, cur = 'TRY') => (v == null ? '—' : `${num(v, 2)} ${CUR[cur] ?? cur}`);

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
export const day = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : dayFmt.format(d);
};
const stampFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });
export const stamp = (iso: string | null | undefined) => (iso ? stampFmt.format(new Date(iso)) : '—');

export const today = () => new Date(Date.now() + 3 * 3600_000).toISOString().slice(0, 10);

export const statusTone = (s: Status | string): 'ok' | 'warn' | 'err' | 'muted' | 'violet' =>
  s === 'yururlukte' ? 'ok' : s === 'imzada' ? 'violet' : s === 'taslak' ? 'warn' : s === 'feshedildi' || s === 'iptal' ? 'err' : 'muted';

/** Hata cümlesi: yetki yoksa sunucunun cümlesi, oturum düştüyse «Oturum gerekli». */
export function errMsg(e: unknown, fallback = 'İşlem tamamlanamadı.'): string | null {
  if (!e) return null;
  if (e instanceof EngineForbiddenError) return e.message || 'Bu işlem rolünüzde yok.';
  if (e instanceof EngineAuthError) return 'Oturum gerekli.';
  return (e as Error).message || fallback;
}

/** Sayı alanı: boş = null; virgül ondalık kabul edilir. */
export const toNum = (s: string): number | null => {
  let t = s.trim();
  if (!t) return null;
  t = normalizeTrNumber(t); // 12.500,50 ve 7.500 binlikle
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
};

/** Form alanı. `explain` verilirse etiketin yanında «?» durur; «?» bir düğme olduğu için label'ın dışına
 *  konur (label içindeki düğme etiketi input yerine kendine bağlar), input ayrı bir label'la adlandırılır. */
export function Field({ label, hint, children, wide, explain }: { label: string; hint?: string; children: ReactNode; wide?: boolean; explain?: ReactNode }) {
  const cls = `block min-w-0 ${wide ? 'sm:col-span-2' : ''}`;
  const head = 'text-[11px] font-bold uppercase tracking-wide text-canvas-muted';
  if (explain)
    return (
      <div className={cls}>
        <span className={`flex items-center gap-1 ${head}`}>
          {label}
          <Explain label={label}>{explain}</Explain>
        </span>
        <label className="mt-1 block">
          <span className="sr-only">{label}</span>
          {children}
        </label>
        {hint && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{hint}</span>}
      </div>
    );
  return (
    <label className={cls}>
      <span className={head}>{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="mt-1 block text-[11px] leading-snug text-canvas-muted">{hint}</span>}
    </label>
  );
}

/** Tanım satırı; `explain` verilirse etiketin yanında «?». */
export function Row({ label, children, explain }: { label: string; children: ReactNode; explain?: ReactNode }) {
  return (
    <div className="grid grid-cols-[minmax(0,130px)_minmax(0,1fr)] gap-2 border-b border-slate-100 py-1.5 text-[12.5px] last:border-0 sm:grid-cols-[180px_minmax(0,1fr)]">
      <dt className="text-canvas-muted">
        {explain ? (
          <span className="inline-flex items-center gap-1">
            {label}
            <Explain label={label}>{explain}</Explain>
          </span>
        ) : (
          label
        )}
      </dt>
      <dd className="min-w-0 break-words font-semibold">{children}</dd>
    </div>
  );
}

function useEntered() {
  const [on, setOn] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setOn(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return on;
}

/**
 * Form kartı: telefonda alttan açılır, geniş ekranda ortada durur. Esc ve arka plan kapatır; odak karta gelir,
 * arkadaki sayfa kaymaz. Giriş 200 ms (opaklık + 8 px kayma), azaltılmış harekette yalnız opaklık.
 */
export function Sheet({ title, onClose, children, footer, wide }: { title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  const entered = useEntered();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prevFocus = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener('keydown', onKey);
      prevFocus?.focus?.();
    };
  }, [onClose]);
  return createPortal(
    <div
      className={`fixed inset-0 z-50 flex items-end justify-center bg-canvas-ink/40 transition-opacity duration-200 ease-out sm:items-center sm:p-6 ${entered ? 'opacity-100' : 'opacity-0'}`}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className={`flex max-h-[92dvh] w-full flex-col rounded-t-3xl bg-white shadow-2xl outline-none transition-[opacity,transform] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] motion-reduce:transition-opacity sm:rounded-3xl ${wide ? 'sm:max-w-3xl' : 'sm:max-w-xl'} ${entered ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0 motion-reduce:translate-y-0'}`}
      >
        <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h2 className="min-w-0 truncate text-[15px] font-extrabold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Kapat" className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-canvas-muted transition-transform duration-150 ease-out hover:bg-slate-100 active:scale-[0.97] sm:h-9 sm:w-9">
            <X aria-hidden className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-3">{children}</div>
        {footer && <div className="flex flex-wrap justify-end gap-2 border-t border-slate-100 px-4 py-3 pb-[max(12px,env(safe-area-inset-bottom))]">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

/** Sekme şeridi: telefonda kendi içinde yatay kayar. */
export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: Array<{ id: T; label: string; count?: number }> }) {
  return (
    <div role="tablist" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
      {items.map((t) => (
        <button
          key={t.id}
          role="tab"
          type="button"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-xl px-3 text-[12.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${
            value === t.id ? 'bg-canvas-violet text-white shadow-md' : 'bg-white/80 text-canvas-ink hover:bg-slate-100'
          }`}
        >
          {t.label}
          {t.count != null && t.count > 0 && (
            <span className={`rounded-md px-1.5 font-mono text-[11px] tabular-nums ${value === t.id ? 'bg-white/20' : 'bg-slate-100'}`}>{t.count}</span>
          )}
        </button>
      ))}
    </div>
  );
}
