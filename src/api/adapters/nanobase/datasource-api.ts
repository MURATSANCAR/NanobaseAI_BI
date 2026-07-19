import { request } from '@/api/http';
import type { DatasourceService } from '@/api/contracts/service';
import type {
  CreateDatasourceRequest,
  DatasourceTestResult,
  SchemaScan,
} from '@/api/contracts/datasource';
import type { BiConnectionUpsert, BiSourcesList } from '@/api/types';

function toUpsertBody(req: CreateDatasourceRequest | BiConnectionUpsert): BiConnectionUpsert {
  const r = req as CreateDatasourceRequest & BiConnectionUpsert;
  return {
    label: r.label || r.name || '',
    driver: (r.driver || (r.databaseType === 'ORACLE' ? 'oracle' : 'postgresql')) as BiConnectionUpsert['driver'],
    host: r.host,
    port: r.port,
    database: r.database,
    username: r.username,
    password: r.password,
    ssl: r.ssl ?? r.sslMode === 'REQUIRE',
  };
}

export function createNanobaseDatasourceService(): DatasourceService {
  return {
    listDatasources: (c) => request<BiSourcesList>(c, '/api/v1/bi/sources'),

    createDatasource: (c, id, req) =>
      request(c, `/api/v1/bi/sources/${encodeURIComponent(id)}`, {
        method: 'PUT',
        body: JSON.stringify(toUpsertBody(req)),
      }),

    deleteDatasource: (c, id) =>
      request(c, `/api/v1/bi/sources/${encodeURIComponent(id)}`, { method: 'DELETE' }),

    testDatasource: async (c, id) => {
      const raw = await request<Record<string, unknown>>(
        c,
        `/api/v1/bi/sources/${encodeURIComponent(id)}/test`,
        { method: 'POST', body: '{}' },
      );
      const ok = Boolean(raw.success ?? raw.ok);
      return {
        success: ok,
        ok,
        databaseType: raw.databaseType ? String(raw.databaseType) : undefined,
        databaseVersion: raw.databaseVersion ? String(raw.databaseVersion) : undefined,
        latencyMs: typeof raw.latencyMs === 'number' ? raw.latencyMs : undefined,
        message: raw.message ? String(raw.message) : undefined,
        via: raw.via ? String(raw.via) : undefined,
      } satisfies DatasourceTestResult;
    },

    startScan: async (c, id) => {
      const raw = await request<Record<string, unknown>>(
        c,
        `/api/v1/bi/sources/${encodeURIComponent(id)}/scan`,
        { method: 'POST', body: '{}' },
      );
      return {
        scanId: String(raw.scanId || raw.scan_id || ''),
        status: String(raw.status || 'QUEUED') as SchemaScan['status'],
      };
    },

    getScan: async (c, scanId) => {
      const raw = await request<Record<string, unknown>>(
        c,
        `/api/v1/bi/schema-scans/${encodeURIComponent(scanId)}`,
      );
      return {
        scanId: String(raw.scanId || scanId),
        status: String(raw.status || 'QUEUED') as SchemaScan['status'],
        datasourceId: raw.datasourceId ? String(raw.datasourceId) : undefined,
        schemaCount: (raw.schemaCount as number | null) ?? null,
        tableCount: (raw.tableCount as number | null) ?? null,
        columnCount: (raw.columnCount as number | null) ?? null,
        relationshipCount: (raw.relationshipCount as number | null) ?? null,
        indexedDocumentCount: (raw.indexedDocumentCount as number | null) ?? null,
        skippedDocumentCount: (raw.skippedDocumentCount as number | null) ?? null,
        error: raw.error ? String(raw.error) : null,
        startedAt: raw.startedAt ? String(raw.startedAt) : null,
        completedAt: raw.completedAt ? String(raw.completedAt) : null,
      };
    },

    activate: (c, id) =>
      request(c, `/api/v1/bi/sources/${encodeURIComponent(id)}/activate`, { method: 'POST' }),
  };
}
