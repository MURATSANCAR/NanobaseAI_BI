import { NavLink } from 'react-router-dom';
import { BI_NAV_GROUPS } from '@/lib/navGroups';
import { t } from '@/i18n';

/** Menü tek kaynaktan gelir: src/lib/navGroups.ts. Kanvas kendi listesini tutmaz,
 *  böylece uygulamaya eklenen ekran raya kendiliğinden düşer. */
const FLAT = BI_NAV_GROUPS.flatMap((g) => g.links.map((l) => ({ ...l, group: g.titleKey })));
/** Son iki grup (teslimat kuyruğu + ayarlar) rayın alt kümesinde durur. */
const BOTTOM_GROUPS = new Set(['nav.group.settings']);
const BOTTOM_LINKS = new Set(['/bi/alerts', '/bi/audit']);

const isBottom = (l: (typeof FLAT)[number]) => BOTTOM_GROUPS.has(l.group) || BOTTOM_LINKS.has(l.to);

function RailItem({ link }: { link: (typeof FLAT)[number] }) {
  const Icon = link.icon;
  const label = t(link.labelKey);
  return (
    <div className="group relative flex w-full items-center justify-center">
      <NavLink
        to={link.to}
        end={link.to === '/bi'}
        aria-label={label}
        className={({ isActive }) =>
          [
            'flex h-10 w-10 items-center justify-center rounded-2xl transition',
            isActive
              ? 'bg-gradient-to-tr from-canvas-coral to-canvas-violet text-white shadow-md hover:scale-105'
              : 'text-canvas-muted hover:bg-white/80 hover:text-canvas-ink',
          ].join(' ')
        }
      >
        <Icon className="h-5 w-5" />
      </NavLink>
      <div className="pointer-events-none absolute left-14 z-50 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1 text-[11px] font-semibold text-white opacity-0 shadow-xl transition duration-150 group-hover:opacity-100">
        {label}
      </div>
    </div>
  );
}

export default function CanvasRail() {
  const top = FLAT.filter((l) => !isBottom(l));
  const bottom = FLAT.filter(isBottom);
  return (
    <aside className="cv-glass absolute bottom-24 left-6 top-24 z-30 flex w-[54px] flex-col items-center justify-between rounded-3xl px-2 py-4 shadow-glass-float">
      <div className="cv-scroll flex w-full flex-col items-center gap-2 overflow-y-auto">
        {top.map((l) => (
          <RailItem key={l.to} link={l} />
        ))}
      </div>
      <div className="flex w-full flex-col items-center gap-2 border-t border-white/70 pt-2">
        {bottom.map((l) => (
          <RailItem key={l.to} link={l} />
        ))}
      </div>
    </aside>
  );
}
