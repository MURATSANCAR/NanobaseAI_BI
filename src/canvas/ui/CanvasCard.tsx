import type { ReactNode } from 'react';
import type { CanvasAccent } from '../types';

const ACCENT_CHIP: Record<CanvasAccent, string> = {
  coral: 'bg-canvas-coral/10 text-canvas-coral',
  violet: 'bg-canvas-violet/10 text-canvas-violet',
  mint: 'bg-emerald-50 text-canvas-mint',
  amber: 'bg-amber-50 text-canvas-amber',
  slate: 'bg-slate-100 text-slate-700',
};

export type BadgeTone = 'ok' | 'warn' | 'fail' | 'info' | 'muted';

const BADGE: Record<BadgeTone, string> = {
  ok: 'bg-emerald-50 text-emerald-600 border-emerald-100',
  warn: 'bg-amber-50 text-amber-700 border-amber-200/60',
  fail: 'bg-red-50 text-red-600 border-red-100',
  info: 'bg-canvas-violet/10 text-canvas-violet border-canvas-violet/20',
  muted: 'bg-slate-100 text-slate-500 border-slate-200',
};

export function CardBadge({ tone = 'muted', children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span className={['rounded-full border px-2 py-0.5 text-[10px] font-bold', BADGE[tone]].join(' ')}>{children}</span>
  );
}

type Props = {
  title: string;
  icon: ReactNode;
  accent?: CanvasAccent;
  badge?: ReactNode;
  /** Başlığın sağındaki küçük gri not (rozet yerine). */
  note?: string;
  children: ReactNode;
  /** Yığın kipinde eğim uygulanmaz. */
  stacked?: boolean;
};

/**
 * Kanvasın tek kart gövdesi. Başlık şeridi + ince ayraç + içerik.
 * Her ekran bunu kullanır; kart tipi yalnız `children` ile değişir.
 */
export default function CanvasCard({ title, icon, accent = 'slate', badge, note, children, stacked }: Props) {
  return (
    <div
      className={[
        'cv-card cv-card-hover rounded-[24px] p-4 shadow-canvas-card',
        stacked ? 'w-full' : '',
      ].join(' ')}
    >
      <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className={['flex h-6 w-6 shrink-0 items-center justify-center rounded-lg', ACCENT_CHIP[accent]].join(' ')}>
            {icon}
          </span>
          <span className="truncate text-xs font-extrabold tracking-tight text-canvas-ink">{title}</span>
        </div>
        {badge ?? (note ? <span className="shrink-0 text-[10px] font-bold text-canvas-muted">{note}</span> : null)}
      </div>
      <div className="mt-3">{children}</div>
    </div>
  );
}

/** Kart altındaki ince ayraçlı bilgi satırı. */
export function CardFootRow({ label, value, tone }: { label: string; value: ReactNode; tone?: 'ok' | 'warn' | 'plain' }) {
  const cls = tone === 'ok' ? 'text-canvas-mint' : tone === 'warn' ? 'text-amber-700' : 'text-canvas-ink';
  return (
    <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2 text-[11px] text-canvas-muted">
      <span>{label}</span>
      <span className={['font-bold', cls].join(' ')}>{value}</span>
    </div>
  );
}
