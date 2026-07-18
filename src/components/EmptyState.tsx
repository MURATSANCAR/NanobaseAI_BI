import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import clsx from 'clsx';
import { t } from '@/i18n';

type EmptyStateProps = {
  emoji?: string;
  titleKey: string;
  descriptionKey: string;
  ctaLabelKey?: string;
  ctaTo?: string;
  onCtaClick?: () => void;
  children?: ReactNode;
  className?: string;
};

export default function EmptyState({
  emoji = '📭',
  titleKey,
  descriptionKey,
  ctaLabelKey,
  ctaTo,
  onCtaClick,
  children,
  className,
}: EmptyStateProps) {
  const title = t(titleKey);
  const description = t(descriptionKey);

  return (
    <div className={clsx('empty-state-card', className)}>
      <div className="empty-state-emoji" aria-hidden>
        {emoji}
      </div>
      <h3 className="empty-state-title">{title}</h3>
      <p className="empty-state-desc">{description}</p>
      {children}
      {ctaLabelKey && ctaTo && (
        <Link to={ctaTo} className="btn-primary mt-4 inline-flex items-center gap-2">
          {t(ctaLabelKey)}
          <ArrowRight className="h-4 w-4" />
        </Link>
      )}
      {ctaLabelKey && onCtaClick && !ctaTo && (
        <button type="button" className="btn-primary mt-4 inline-flex items-center gap-2" onClick={onCtaClick}>
          {t(ctaLabelKey)}
          <ArrowRight className="h-4 w-4" />
        </button>
      )}
    </div>
  );
}
