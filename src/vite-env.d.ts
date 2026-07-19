/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly VITE_API_MODE?: string;
  readonly VITE_BI_APP_ORIGIN?: string;
  readonly VITE_USE_NANOBASE_BACKEND?: string;
  readonly VITE_ENABLE_SCHEMA_EXPLORER?: string;
  readonly VITE_ENABLE_SQL_PANEL?: string;
  readonly VITE_ENABLE_TEST_EXECUTION?: string;
  readonly VITE_ENABLE_FEEDBACK?: string;
  readonly VITE_ENABLE_EXPORTS?: string;
  readonly VITE_ENABLE_SEMANTIC_CATALOG?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
