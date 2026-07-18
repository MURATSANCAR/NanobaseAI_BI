import clsx from 'clsx';
import { Clock } from 'lucide-react';
import BiPbiTile from '@/components/bi/BiPbiTile';
import { t } from '@/i18n';

function relativeTime(iso?: string): string | null {
  if (!iso) return null;
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return null;
  const mins = Math.floor((Date.now() - then) / 60000);
  if (mins < 1) return t('bi.freshnessJustNow');
  if (mins < 60) return t('bi.freshnessMinutes', { count: String(mins) });
  const hours = Math.floor(mins / 60);
  if (hours < 24) return t('bi.freshnessHours', { count: String(hours) });
  return t('bi.freshnessDays', { count: String(Math.floor(hours / 24)) });
}

type Props = {
  refreshedAt?: string;
  updatedAt?: string;
  className?: string;
};

export default function BiFreshnessBadge({ refreshedAt, updatedAt, className }: Props) {
  const label = relativeTime(refreshedAt || updatedAt);
  if (!label) return null;
  return (
    <span className={clsx('inline-flex items-center gap-1 text-[10px] text-slate-400', className)}>
      <Clock className="h-3 w-3" />
      {label}
    </span>
  );
}

export function BiWidgetSkeleton() {
  return (
    <BiPbiTile visualType="bar" accentIndex={0}>
      <div className="bi-pbi-skeleton h-36 rounded-xl" />
    </BiPbiTile>
  );
}
