/** QA portal module helpers. */

export type PortalModule = 'bi' | 'test' | 'contracts';

export function normalizePortalModule(raw: string): PortalModule | null {
  const m = raw.trim().toLowerCase();
  if (m === 'bi' || m === 'test' || m === 'contracts') return m;
  return null;
}

export function normalizeUserModules(modules: string[]): PortalModule[] {
  const out = new Set<PortalModule>();
  for (const m of modules) {
    const n = normalizePortalModule(m);
    if (n) out.add(n);
  }
  return [...out];
}

export function firstInAppModulePath(
  hasModule: (m: PortalModule) => boolean,
  moduleHome: Record<PortalModule, string>,
): string {
  for (const module of ['contracts', 'bi', 'test'] as PortalModule[]) {
    if (hasModule(module)) return moduleHome[module];
  }
  return '/settings';
}
