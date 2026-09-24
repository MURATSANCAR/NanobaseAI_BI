import { useState } from 'react';
import { AlertTriangle, Check, CircleDashed, Loader2, MinusCircle, X } from 'lucide-react';
import type { StudioStepStatus } from '../../engine';

/** Kitap Tasarım Stüdyosu'nun ortak parçaları. Hareket yalnız durum değişimini anlatmak için:
 *  basışta 0,97 küçülme, ilerleme çubuğu genişliği; ikisi de 160–240 ms ease-out. */

export const press = 'transition-transform duration-150 ease-out active:scale-[0.97]';
export const gradientBtn =
  `inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-canvas-coral to-canvas-violet px-4 text-[13px] font-bold text-white shadow-md disabled:cursor-not-allowed disabled:opacity-50 ${press}`;
export const ghostBtn =
  `inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white/80 px-3.5 text-[13px] font-bold text-canvas-ink hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 ${press}`;

export const STATUS_TEXT: Record<StudioStepStatus, string> = {
  waiting: 'Bekliyor', running: 'Sürüyor', done: 'Tamam', warn: 'Uyarı', fail: 'Hata', skipped: 'Atlandı',
};

export function StepIcon({ status }: { status: StudioStepStatus }) {
  const base = 'flex h-7 w-7 shrink-0 items-center justify-center rounded-full';
  if (status === 'done') return <span className={`${base} bg-emerald-500 text-white`}><Check className="h-4 w-4" aria-hidden /></span>;
  if (status === 'warn') return <span className={`${base} bg-amber-400 text-white`}><AlertTriangle className="h-4 w-4" aria-hidden /></span>;
  if (status === 'fail') return <span className={`${base} bg-rose-500 text-white`}><X className="h-4 w-4" aria-hidden /></span>;
  if (status === 'running') return <span className={`${base} bg-gradient-to-br from-canvas-coral to-canvas-violet text-white`}><Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /></span>;
  if (status === 'skipped') return <span className={`${base} bg-slate-200 text-slate-500`}><MinusCircle className="h-4 w-4" aria-hidden /></span>;
  return <span className={`${base} border border-slate-300 bg-white text-slate-400`}><CircleDashed className="h-4 w-4" aria-hidden /></span>;
}

export function Progress({ value, total }: { value: number; total: number }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200/80" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={total}>
      <div className="h-full rounded-full bg-gradient-to-r from-canvas-coral to-canvas-violet transition-[width] duration-200 ease-out" style={{ width: `${pct}%` }} />
    </div>
  );
}

/** Görsel: yüklenemezse sessizce yer tutucuya döner (sayfa henüz dizilmemiş olabilir). */
export function Img({ src, alt, className = '', fallback }: { src: string; alt: string; className?: string; fallback: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return <div className={`flex items-center justify-center bg-slate-100 text-[11px] text-canvas-muted ${className}`}>{fallback}</div>;
  }
  return <img src={src} alt={alt} loading="lazy" decoding="async" onError={() => setFailed(true)} className={className} />;
}

export const secs = (s: number | null | undefined) => {
  if (s == null) return '';
  const m = Math.floor(s / 60);
  return `${String(m).padStart(2, '0')}:${String(Math.round(s % 60)).padStart(2, '0')}`;
};

export const ago = (t: number) => new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(t * 1000));
