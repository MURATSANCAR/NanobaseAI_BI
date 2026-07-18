import { Link, useLocation } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';
import { helpPageFromPath } from '@/help/pages';
import { moduleFromPath } from '@/lib/moduleRoutes';
import { t } from '@/i18n';

const PAGE_LABEL_KEYS: Record<string, string> = {
  home: 'nav.allModules',
  dashboard: 'nav.commandCenter',
  setup: 'nav.setup',
  process: 'nav.process',
  results: 'nav.resultsHub',
  qualityMap: 'nav.qualityMap',
  projects: 'nav.projects',
  environment: 'nav.environment',
  repos: 'nav.repositories',
  analysis: 'nav.analysis',
  run: 'nav.run',
  suites: 'nav.suites',
  suiteDetail: 'nav.suites',
  registry: 'nav.registry',
  reports: 'nav.reports',
  settings: 'nav.settings',
  users: 'nav.users',
  bi: 'nav.bi',
  biChat: 'nav.biChat',
  biReports: 'nav.biReports',
  biSchema: 'nav.biSchema',
  biSchedules: 'nav.biSchedules',
  biQueries: 'nav.biQueries',
  biTemplates: 'nav.biTemplates',
  biGlossary: 'nav.biGlossary',
  biAlerts: 'nav.biAlerts',
  biConnection: 'nav.biConnection',
  biShares: 'nav.biShares',
  biAudit: 'nav.biAudit',
};

function moduleHomePath(module: ReturnType<typeof moduleFromPath>): string | null {
  if (module === 'test') return '/test';
  if (module === 'bi') return '/bi';
  return null;
}

export default function Breadcrumbs() {
  const { pathname } = useLocation();
  const pageId = helpPageFromPath(pathname);
  const module = moduleFromPath(pathname);
  const moduleHome = moduleHomePath(module);
  const pageLabelKey = PAGE_LABEL_KEYS[pageId];
  const isModuleHome =
    (module === 'test' && pathname === '/test') || (module === 'bi' && pathname === '/bi');

  if (!module && !pathname.startsWith('/settings') && !pathname.startsWith('/users')) {
    return null;
  }

  const moduleLabel =
    module === 'bi' ? t('nav.section.bi') : module === 'test' ? t('nav.section.test') : null;

  return (
    <nav className="breadcrumbs" aria-label={t('ux.breadcrumbs.label')}>
      <Link to="/" className="breadcrumb-link breadcrumb-home" title={t('ux.breadcrumbs.home')}>
        <Home className="h-3.5 w-3.5" />
        <span className="sr-only sm:not-sr-only sm:inline">{t('ux.breadcrumbs.home')}</span>
      </Link>

      {moduleLabel && moduleHome && (
        <>
          <ChevronRight className="breadcrumb-sep h-3.5 w-3.5" aria-hidden />
          <Link to={moduleHome} className="breadcrumb-link">
            {moduleLabel}
          </Link>
        </>
      )}

      {pathname.startsWith('/settings') && (
        <>
          <ChevronRight className="breadcrumb-sep h-3.5 w-3.5" aria-hidden />
          <span className="breadcrumb-current">{t('nav.settings')}</span>
        </>
      )}

      {pathname.startsWith('/users') && (
        <>
          <ChevronRight className="breadcrumb-sep h-3.5 w-3.5" aria-hidden />
          <span className="breadcrumb-current">{t('nav.users')}</span>
        </>
      )}

      {pageLabelKey && module && !isModuleHome && (
        <>
          <ChevronRight className="breadcrumb-sep h-3.5 w-3.5" aria-hidden />
          <span className="breadcrumb-current">{t(pageLabelKey)}</span>
        </>
      )}
    </nav>
  );
}
