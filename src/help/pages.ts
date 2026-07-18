export const HELP_PAGE_IDS = [
  'bi',
  'biSchema',
  'biSchedules',
  'biQueries',
  'biTemplates',
  'biGlossary',
  'biAlerts',
  'biBudget',
  'biConnection',
  'biChat',
  'biSettings',
  'biShares',
  'biAudit',
  'settings',
  'login',
] as const;

export type HelpPageId = (typeof HELP_PAGE_IDS)[number];

export function helpPageFromPath(pathname: string): HelpPageId {
  if (pathname.startsWith('/bi/audit')) return 'biAudit';
  if (pathname.startsWith('/bi/shares')) return 'biShares';
  if (pathname.startsWith('/bi/chat')) return 'biChat';
  if (pathname.startsWith('/bi/alerts')) return 'biAlerts';
  if (pathname.startsWith('/bi/budget')) return 'biBudget';
  if (pathname.startsWith('/bi/glossary')) return 'biGlossary';
  if (pathname.startsWith('/bi/queries')) return 'biQueries';
  if (pathname.startsWith('/bi/templates')) return 'biTemplates';
  if (pathname.startsWith('/bi/schedules')) return 'biSchedules';
  if (pathname.startsWith('/bi/schema')) return 'biSchema';
  if (pathname.startsWith('/bi/settings')) return 'biSettings';
  if (pathname.startsWith('/bi/sources') || pathname.startsWith('/bi/connection')) return 'biConnection';
  if (pathname.startsWith('/bi')) return 'bi';
  if (pathname.startsWith('/settings')) return 'settings';
  return 'bi';
}

export function helpKey(pageId: HelpPageId): string {
  return `help.${pageId}`;
}
