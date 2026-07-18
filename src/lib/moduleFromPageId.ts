import type { HelpPageId } from '@/help/pages';

export type PortalModuleTheme = 'bi' | 'settings';

export function moduleFromPageId(pageId: HelpPageId): PortalModuleTheme {
  if (pageId.startsWith('bi')) return 'bi';
  return 'settings';
}

export function isModuleDashboardPage(pageId: HelpPageId): boolean {
  return pageId === 'bi';
}
