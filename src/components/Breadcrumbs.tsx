import { Link, useLocation } from 'react-router-dom';
import { ChevronRight, Home } from 'lucide-react';
import { helpPageFromPath } from '@/help/pages';
import { moduleFromPath } from '@/lib/moduleRoutes';
import { t } from '@/i18n';

const PAGE_LABEL_KEYS: Record<string, string> = {
  bi: 'nav.bi',
  biChat: 'nav.biChat',
  biSchema: 'nav.biSchema',
  biSchedules: 'nav.biSchedules',
  biQueries: 'nav.biQueries',
  biTemplates: 'nav.biTemplates',
  biGlossary: 'nav.biGlossary',
  biSemanticCatalog: 'nav.biSemanticCatalog',
  biAlerts: 'nav.biAlerts',
  biBudget: 'nav.biBudget',
  biConnection: 'nav.biConnection',
  biShares: 'nav.biShares',
  biAudit: 'nav.biAudit',
  biSettings: 'nav.biSettings',
};

export default function Breadcrumbs() {
  const { pathname } = useLocation();
  const pageId = helpPageFromPath(pathname);
  const module = moduleFromPath(pathname);
  const pageLabelKey = PAGE_LABEL_KEYS[pageId];
  const isModuleHome = module === 'bi' && pathname === '/bi';

  if (!module) {
    return null;
  }

  const moduleLabel = module === 'bi' ? t('nav.section.bi') : null;

  return (
    <nav className="breadcrumbs" aria-label={t('ux.breadcrumbs.label')}>
      <Link to="/" className="breadcrumb-link breadcrumb-home" title={t('ux.breadcrumbs.home')}>
        <Home className="h-3.5 w-3.5" />
        <span className="sr-only sm:not-sr-only sm:inline">{t('ux.breadcrumbs.home')}</span>
      </Link>

      {moduleLabel && (
        <>
          <ChevronRight className="breadcrumb-sep h-3.5 w-3.5" aria-hidden />
          <Link to="/bi" className="breadcrumb-link">
            {moduleLabel}
          </Link>
        </>
      )}

      {pageLabelKey && !isModuleHome && (
        <>
          <ChevronRight className="breadcrumb-sep h-3.5 w-3.5" aria-hidden />
          <span className="breadcrumb-current">{t(pageLabelKey)}</span>
        </>
      )}
    </nav>
  );
}
