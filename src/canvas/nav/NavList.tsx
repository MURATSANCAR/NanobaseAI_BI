import { Fragment } from 'react';
import { Link } from 'react-router-dom';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { NavItem, VisibleGroup } from './navModel';

/** Bir çalışma alanının ekranları: alt başlıklar («Günlük», «Yayına hazırlık»), etkin öğe, sayı rozeti.
 *  Masaüstü panelde ve telefon menü sayfasında aynı liste; telefonda satırlar daha yüksek ve oklu. */
export function NavList({
  items,
  activeId,
  alertCount,
  onPick,
  variant = 'panel',
}: {
  items: NavItem[];
  activeId?: string;
  alertCount: number;
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
        const count = item.badge === 'alerts' ? alertCount : 0;
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
                    aria-label={`${count} uyarı eşiği aşmış`}
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

/** Bütün çalışma alanları tek listede, grup grup açılıp kapanır (Kampüs'teki panel). Açık/kapalı kişinin
 *  tercihidir; seçmediyse rolün varsayılanı (editörde Analiz ve Finans kapalı gelir). */
export function NavTree({
  groups,
  activeId,
  alertCount,
  open,
  onToggle,
  onPick,
}: {
  groups: VisibleGroup[];
  activeId?: string;
  alertCount: number;
  open: Partial<Record<string, boolean>>;
  onToggle: (id: string, next: boolean) => void;
  onPick?: () => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      {groups.map((g) => {
        const isOpen = open[g.id] ?? g.defaultOpen;
        const panelId = `nav-tree-${g.id}`;
        return (
          <section key={g.id}>
            <button
              type="button"
              aria-expanded={isOpen}
              aria-controls={panelId}
              onClick={() => onToggle(g.id, !isOpen)}
              className="nav-ghost flex min-h-9 w-full items-center gap-2 rounded-xl px-3 text-left text-[10.5px] font-extrabold uppercase tracking-[0.08em] text-muted"
            >
              <span className="min-w-0 truncate">{g.label}</span>
              {g.tag && (
                <span className="shrink-0 rounded-full bg-mintSuccess/10px-1.5 py-px text-[10px] font-bold normal-case tracking-normal text-emerald-700 ring-1 ring-mintSuccess/30">
                  {g.tag}
                </span>
              )}
              <ChevronDown aria-hidden className={`ml-auto h-3.5 w-3.5 shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
            </button>
            {isOpen && (
              <div id={panelId} className="pb-1">
                <NavList items={g.items} activeId={activeId} alertCount={alertCount} onPick={onPick} />
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
