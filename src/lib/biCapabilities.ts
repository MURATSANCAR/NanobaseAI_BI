/** Portal role → BI capability matrix (FE hide; backend JWT roles remain authoritative). */

export type PortalBiRole = 'admin' | 'manager' | 'developer' | 'qa' | string;

export type BiCapability =
  | 'sources.read'
  | 'sources.write'
  | 'schema.scan'
  | 'schema.read'
  | 'chat.use'
  | 'sql.panel'
  | 'semantic.review'
  | 'semantic.publish';

const MATRIX: Record<string, ReadonlySet<BiCapability>> = {
  admin: new Set([
    'sources.read',
    'sources.write',
    'schema.scan',
    'schema.read',
    'chat.use',
    'sql.panel',
    'semantic.review',
    'semantic.publish',
  ]),
  manager: new Set([
    'sources.read',
    'sources.write',
    'schema.scan',
    'schema.read',
    'chat.use',
    'sql.panel',
    'semantic.review',
  ]),
  developer: new Set(['sources.read', 'schema.read', 'chat.use', 'sql.panel']),
  qa: new Set(['sources.read', 'schema.read', 'chat.use']),
};

export function normalizePortalRole(role: string | null | undefined): string {
  return (role || 'qa').trim().toLowerCase();
}

export function canBi(role: string | null | undefined, capability: BiCapability): boolean {
  const r = normalizePortalRole(role);
  const caps = MATRIX[r] || MATRIX.qa;
  return caps.has(capability);
}

/** Nav paths that require a capability beyond bi module membership. */
export const NAV_CAPABILITY: Record<string, BiCapability | undefined> = {
  '/bi/connection': 'sources.read',
  '/bi/sources': 'sources.read',
  '/bi/schema': 'schema.read',
  '/bi/chat': 'chat.use',
  '/bi/semantic': 'semantic.review',
  '/bi/glossary': 'schema.read',
};
