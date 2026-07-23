import clsx from 'clsx';
import type { ReactNode } from 'react';
import type { BiVisualType } from '@/components/bi/biVisualTypes';
import { normalizeVisualType } from '@/components/bi/biVisualTypes';

export type BiPbiTileProps = {
  visualType?: string;
  accentIndex?: number;
  title?: string;
  subtitle?: string;
  compact?: boolean;
  kpi?: boolean;
  threeD?: boolean;
  className?: string;
  bodyClassName?: string;
  children?: ReactNode;
};

export default function BiPbiTile({
  visualType = 'card',
  accentIndex = 0,
  title,
  subtitle,
  compact = false,
  kpi = false,
  threeD = true,
  className,
  bodyClassName,
  children,
}: BiPbiTileProps) {
  const visual = normalizeVisualType(visualType) as BiVisualType;
  const accent = accentIndex % 6;

  return (
    <div
      className={clsx(
        'bi-pbi-tile p-0',
        threeD ? 'bi-pbi-tile--3d' : 'overflow-hidden',
        kpi && 'bi-pbi-tile--kpi',
        compact && 'bi-pbi-tile--compact',
        className,
      )}
      data-accent={accent}
    >
      {threeD ? <div className="bi-pbi-tile-depth" aria-hidden /> : null}
      <div className="bi-pbi-tile-glow" aria-hidden />
      <div className="bi-pbi-tile-shine" aria-hidden />
      <div className="bi-pbi-tile-accent" data-visual={visual} aria-hidden />
      <div className="relative z-[1] overflow-hidden rounded-2xl">
        {(title || subtitle) && (
          <div className={clsx('bi-pbi-tile-header', compact && 'px-3 py-2')}>
            <div className="min-w-0 flex-1">
              {title ? <p className="bi-pbi-tile-title">{title}</p> : null}
              {subtitle ? <p className="bi-pbi-tile-subtitle">{subtitle}</p> : null}
            </div>
          </div>
        )}
        <div className={clsx('bi-pbi-tile-body', compact ? 'p-2' : 'p-3', bodyClassName)}>{children}</div>
      </div>
    </div>
  );
}
