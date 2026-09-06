import type { LucideIcon } from 'lucide-react';
import clsx from 'clsx';
import { InfoTip } from './InfoTip';
import type { InfoKey } from '../lib/definitions';

export function KpiCard({
  label,
  value,
  sub,
  icon: Icon,
  tone = 'neutral',
  progress,
  info,
}: {
  label: string;
  value: string;
  sub: string;
  icon: LucideIcon;
  tone?: 'neutral' | 'good' | 'bad' | 'brand';
  /** 0..1 — kartın altındaki ince çubuk */
  progress?: number | null;
  /** Nasıl hesaplandığı — (i) düğmesi */
  info?: InfoKey;
}) {
  return (
    <div className="card relative p-4">
      <div className="flex items-start justify-between">
        <div className="flex min-w-0 flex-1 items-start gap-1.5">
          <div className="eyebrow leading-[1.3] tracking-[0.1em]">{label}</div>
          {info && <InfoTip k={info} className="mt-px" />}
        </div>
        <Icon size={16} className="ml-2 shrink-0 text-ink-faint" />
      </div>
      <div
        className={clsx(
          'mt-3 font-display text-[30px] font-semibold leading-none tracking-tight',
          tone === 'bad' && 'text-brand-accent',
          tone === 'good' && 'text-ok',
          tone === 'brand' && 'text-brand-deep',
        )}
      >
        {value}
      </div>
      <div className="mt-2 break-words text-[11px] leading-snug text-ink-muted">{sub}</div>
      <div className="mt-3 h-1 w-full rounded-full bg-page">
        <div
          className={clsx('h-1 rounded-full', tone === 'bad' ? 'bg-brand-accent' : tone === 'good' ? 'bg-ok' : 'bg-brand')}
          style={{ width: `${Math.round(Math.min(Math.max(progress ?? 0, 0), 1) * 100)}%` }}
        />
      </div>
    </div>
  );
}
