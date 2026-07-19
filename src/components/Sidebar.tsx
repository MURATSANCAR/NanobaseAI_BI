import { useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { ChevronDown, X } from 'lucide-react';
import clsx from 'clsx';
import AiOrb from './AiOrb';
import { useAuth } from '@/context/AuthContext';
import { useLocale } from '@/context/LocaleContext';
import { BI_NAV_GROUPS, type NavGroupDef, type NavLinkDef } from '@/lib/navGroups';
import { getFeatureFlags } from '@/config/environment';
import { isModuleDashboard } from '@/lib/moduleRoutes';
import { t, SUPPORTED_LOCALES, LOCALE_LABELS } from '@/i18n';

type SidebarProps = {
  open: boolean;
  onClose: () => void;
};

function isLinkActive(pathname: string, to: string): boolean {
  const path = to.split('?')[0];
  if (isModuleDashboard(path)) return pathname === path;
  return pathname === path || pathname.startsWith(`${path}/`);
}

function isGroupActive(pathname: string, links: NavLinkDef[]): boolean {
  return links.some((link) => isLinkActive(pathname, link.to));
}

function NavItem({
  to,
  icon: Icon,
  labelKey,
  hintKey,
  onClose,
  nested = false,
}: NavLinkDef & { onClose: () => void; nested?: boolean }) {
  const hint = t(hintKey);
  const hasHint = hint !== hintKey;
  const pathOnly = to.split('?')[0];

  return (
    <NavLink
      to={to}
      end={isModuleDashboard(pathOnly)}
      onClick={onClose}
      title={hasHint ? hint : undefined}
      className={({ isActive }) =>
        clsx(
          'nav-item group flex items-center gap-2.5 rounded-xl transition-all duration-200',
          nested ? 'px-2.5 py-2 pl-3' : 'px-3 py-2.5 text-sm font-medium',
          isActive ? 'nav-flat-item--active' : 'nav-flat-item--idle',
        )
      }
    >
      <Icon className={clsx('h-4 w-4 shrink-0', nested ? 'opacity-75' : 'opacity-80')} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{t(labelKey)}</span>
        {hasHint && !nested && (
          <span className="nav-item-hint block truncate text-[10px] leading-tight opacity-70 group-[.bg-violet-600]:text-violet-100">
            {hint}
          </span>
        )}
      </span>
    </NavLink>
  );
}

function NavSection({
  group,
  pathname,
  onClose,
}: {
  group: NavGroupDef;
  pathname: string;
  onClose: () => void;
}) {
  const active = isGroupActive(pathname, group.links);
  const collapsible = group.collapsible !== false && group.links.length > 1;
  const [sectionOpen, setSectionOpen] = useState(active);

  if (!collapsible) {
    return (
      <div className="space-y-0.5">
        {group.links.map((link) => (
          <NavItem key={link.to} {...link} onClose={onClose} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      <button
        type="button"
        onClick={() => setSectionOpen((v) => !v)}
        className={clsx(
          'flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 transition hover:bg-white/50',
          active && 'text-violet-700',
        )}
      >
        <group.icon className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
        <span className="flex-1 truncate">{t(group.titleKey)}</span>
        <ChevronDown className={clsx('h-4 w-4 transition', sectionOpen && 'rotate-180')} aria-hidden />
      </button>
      {sectionOpen && (
        <div className="space-y-0.5 border-l border-violet-200/60 pl-2">
          {group.links.map((link) => (
            <NavItem key={link.to} {...link} onClose={onClose} nested />
          ))}
        </div>
      )}
    </div>
  );
}

export default function Sidebar({ open, onClose }: SidebarProps) {
  const { pathname } = useLocation();
  const { locale, setAppLocale } = useLocale();
  const { user, logout, portalUsersEnabled } = useAuth();

  return (
    <>
      {open && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-slate-900/20 backdrop-blur-sm lg:hidden"
          aria-label={t('nav.closeMenu')}
          onClick={onClose}
        />
      )}

      <aside
        className={clsx(
          'nav-sidebar fixed z-50 flex h-[100dvh] w-[var(--nav-width,16rem)] flex-col border-r border-white/70 bg-white/75 shadow-xl backdrop-blur-xl transition-transform duration-300 lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex items-center justify-between gap-2 border-b border-white/60 px-4 py-4">
          <div className="flex min-w-0 items-center gap-2">
            <AiOrb size="sm" />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-slate-800">{t('nav.bi')}</p>
              <p className="truncate text-[10px] text-slate-500">{t('bi.hero.pipelineLabel')}</p>
            </div>
          </div>
          <button
            type="button"
            className="rounded-lg p-1 text-slate-500 hover:bg-white lg:hidden"
            onClick={onClose}
            aria-label={t('nav.closeMenu')}
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <nav className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
          {BI_NAV_GROUPS.map((group) => {
            const flags = getFeatureFlags();
            const links = group.links.filter(
              (l) => l.to !== '/bi/semantic-catalog' || flags.enableSemanticCatalog,
            );
            if (links.length === 0) return null;
            return (
              <NavSection
                key={group.titleKey}
                group={{ ...group, links }}
                pathname={pathname}
                onClose={onClose}
              />
            );
          })}
        </nav>

        <div className="space-y-2 border-t border-white/60 p-3">
          <div className="flex items-center gap-1 rounded-xl border border-white/70 bg-white/60 p-1">
            {SUPPORTED_LOCALES.map((loc) => (
              <button
                key={loc}
                type="button"
                onClick={() => setAppLocale(loc)}
                className={clsx(
                  'flex-1 rounded-lg px-2 py-1 text-xs font-medium transition',
                  locale === loc ? 'bg-violet-600 text-white' : 'text-slate-600 hover:bg-white',
                )}
              >
                {LOCALE_LABELS[loc]}
              </button>
            ))}
          </div>

          {portalUsersEnabled && user && (
            <div className="rounded-xl border border-white/70 bg-white/60 px-3 py-2 text-xs text-slate-600">
              <p className="truncate font-medium text-slate-800">{user.display_name || user.username}</p>
              <button type="button" className="mt-1 text-violet-700 hover:underline" onClick={() => logout()}>
                {t('auth.logout')}
              </button>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
