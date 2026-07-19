/** Faz 4 environment + feature flags */

export type ApiMode = 'NANOBASE' | 'LEGACY';

export type FeatureFlags = {
  useNanobaseBackend: boolean;
  enableSchemaExplorer: boolean;
  enableSqlPanel: boolean;
  enableTestExecution: boolean;
  enableFeedback: boolean;
  enableExports: boolean;
  enableSemanticCatalog: boolean;
};

function envFlag(name: string, defaultValue: boolean): boolean {
  const raw = import.meta.env[name as keyof ImportMetaEnv];
  if (raw === undefined || raw === '') return defaultValue;
  return String(raw).toLowerCase() === 'true' || String(raw) === '1';
}

export function getApiMode(): ApiMode {
  const mode = String(import.meta.env.VITE_API_MODE || 'NANOBASE').toUpperCase();
  return mode === 'LEGACY' ? 'LEGACY' : 'NANOBASE';
}

export function getDefaultApiBase(): string {
  return String(import.meta.env.VITE_API_BASE || '/bi-api').replace(/\/$/, '');
}

export function getFeatureFlags(): FeatureFlags {
  const nanobase = getApiMode() === 'NANOBASE';
  return {
    useNanobaseBackend: envFlag('VITE_USE_NANOBASE_BACKEND', nanobase),
    enableSchemaExplorer: envFlag('VITE_ENABLE_SCHEMA_EXPLORER', true),
    enableSqlPanel: envFlag('VITE_ENABLE_SQL_PANEL', true),
    enableTestExecution: envFlag('VITE_ENABLE_TEST_EXECUTION', false),
    enableFeedback: envFlag('VITE_ENABLE_FEEDBACK', true),
    enableExports: envFlag('VITE_ENABLE_EXPORTS', true),
    enableSemanticCatalog: envFlag('VITE_ENABLE_SEMANTIC_CATALOG', false),
  };
}
