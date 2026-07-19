/** Shared FE contracts (mapped onto /api/v1/bi/*). */

export type DatabaseType = 'POSTGRESQL' | 'MYSQL' | 'SQLSERVER' | 'ORACLE' | 'SAP_HANA';

export type DatasourceStatus =
  | 'CREATED'
  | 'TESTING'
  | 'READY'
  | 'SCAN_PENDING'
  | 'SCANNING'
  | 'FAILED'
  | 'DISABLED';

export type Datasource = {
  id: string;
  name: string;
  databaseType: DatabaseType;
  host: string;
  port: number;
  database: string;
  username: string;
  status: DatasourceStatus;
  allowedSchemas: string[];
  lastConnectionTestAt?: string;
  lastScanAt?: string;
  createdAt?: string;
  /** Raw profile fields for existing UI */
  raw?: Record<string, unknown>;
};

export type DatasourceTestResult = {
  success: boolean;
  ok: boolean;
  databaseType?: string;
  databaseVersion?: string;
  latencyMs?: number;
  message?: string;
  via?: string;
};

export type SchemaScanStatus = 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED';

export type SchemaScan = {
  scanId: string;
  status: SchemaScanStatus;
  datasourceId?: string;
  schemaCount?: number | null;
  tableCount?: number | null;
  columnCount?: number | null;
  relationshipCount?: number | null;
  indexedDocumentCount?: number | null;
  skippedDocumentCount?: number | null;
  error?: string | null;
  startedAt?: string | null;
  completedAt?: string | null;
};

export type CreateDatasourceRequest = {
  name: string;
  databaseType?: DatabaseType;
  host: string;
  port: number;
  database: string;
  username: string;
  password?: string;
  sslMode?: 'DISABLE' | 'PREFER' | 'REQUIRE';
  allowedSchemas?: string[];
  /** Pass-through for existing BiConnectionUpsert fields */
  driver?: string;
  label?: string;
  ssl?: boolean;
  dialect?: string;
};

export type ChatExecutionState =
  | 'IDLE'
  | 'SUBMITTING'
  | 'RETRIEVING_CONTEXT'
  | 'GENERATING_SQL'
  | 'VALIDATING'
  | 'EXECUTING'
  | 'GENERATING_ANSWER'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED';
