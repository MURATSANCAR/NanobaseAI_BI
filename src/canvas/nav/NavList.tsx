import { Fragment } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRight } from 'lucide-react';
import { badgeLabel, type NavCounts, type NavItem } from './navModel';

/** Bir çalışma alanının ekranları: alt başlıklar («Günlük», «Yayına hazırlık»), etkin öğe, sayı rozeti.
 *  Telefon menü sayfasında kullanılır; satırlar yüksek ve oklu. */
export function NavList({
  items,
  activeId,
  alertCount,
  counts,
  mailOverdue = 0,
  onPick,
  variant = 'panel',
}: {
  items: NavItem[];
  activeId?: string;
  alertCount: number;
  counts?: NavCounts;
  mailOverdue?: number;
  onPick?: () => void;
  variant?: 'panel' | 'sheet';
}) {
  const sheet = variant === 'sheet';
  return (
    <ul className="flex flex-col gap-0.5">
      {items.map((item, i) => {
        const Icon = item.icon;
        const active = item.id === activeId;
        const heading = item.section && item.section !== items[i - 1]?.section ? item.section : null;
        const count = item.badge === 'alerts' ? alertCount : item.badge ? (counts?.[item.badge] ?? 0) : 0;
        return (
          <Fragment key={item.id}>
            {heading && (
              <li aria-hidden className={`px-3 pb-1 ${i === 0 ? 'pt-1' : 'pt-3'} text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-muted/80`}>
                {heading}
              </li>
            )}
            <li>
              <Link
                to={item.to}
                onClick={onPick}
                data-active={active ? '1' : '0'}
                aria-current={active ? 'page' : undefined}
                className={
                  'nav-row relative flex items-center gap-2.5 rounded-xl pr-2.5 ' +
                  (sheet ? 'min-h-12 text-[15px] ' : 'min-h-10 text-[13.5px] ') +
                  (item.parent ? 'pl-8 ' : 'pl-3 ') +
                  (active
                    ? 'bg-gradient-to-r from-coral to-violet font-bold text-white shadow-[0_8px_20px_-8px_rgba(124,92,255,0.6)]'
                    : 'font-semibold text-ink/80')
                }
              >
                <Icon aria-hidden className={`h-4 w-4 shrink-0 ${active ? 'text-white' : 'text-muted'}`} strokeWidth={2} />
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {count > 0 && (
                  <span
                    className={`shrink-0 rounded-full px-1.5 text-[11px] font-extrabold tabular-nums leading-5 ${active ? 'bg-white/25 text-white' : 'bg-amberWarn/20 text-amber-700'}`}
                    aria-label={badgeLabel(item.badge ?? 'alerts', count, mailOverdue)}
                  >
                    {count}
                  </span>
                )}
                {sheet && <ChevronRight aria-hidden className={`h-4 w-4 shrink-0 ${active ? 'text-white' : 'text-muted/60'}`} />}
              </Link>
            </li>
          </Fragment>
        );
      })}
    </ul>
  );
}
