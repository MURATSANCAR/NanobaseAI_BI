import type { PortalModule } from '@/lib/portalModules';

export type { PortalModule };

export const MODULE_HOME: Record<PortalModule, string> = {
  bi: '/bi',
  test: '/test',
  contracts: '/contracts',
};

const LEGACY_TEST_PREFIXES = [
  '/projects',
  '/environment',
  '/repositories',
  '/analysis',
  '/run',
  '/suites',
  '/registry',
  '/reports',
] as const;

/** Active portal module from URL, or null on home/settings/users. */
export function moduleFromPath(pathname: string): PortalModule | null {
  if (pathname.startsWith('/bi')) return 'bi';
  if (pathname.startsWith('/test')) return 'test';
  if (pathname.startsWith('/contracts')) return 'contracts';
  if (LEGACY_TEST_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return 'test';
  }
  return null;
}

export function legacyTestPath(pathname: string): string | null {
  if (pathname.startsWith('/test')) return null;
  for (const prefix of LEGACY_TEST_PREFIXES) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) {
      return `/test${pathname}`;
    }
  }
  return null;
}

export function isModuleDashboard(path: string): boolean {
  return path === '/test' || path === '/bi' || path === '/contracts';
}
