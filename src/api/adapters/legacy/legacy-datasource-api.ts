import { request } from '@/api/http';
import type { DatasourceService } from '@/api/contracts/service';
import type { CreateDatasourceRequest, SchemaScan } from '@/api/contracts/datasource';
import type { BiConnectionUpsert, BiSourcesList } from '@/api/types';

/** Rollback stub — same paths (bridge was cut over); kept for VITE_API_MODE=LEGACY. */
export function createLegacyDatasourceService(): DatasourceService {
  return {
    listDatasources: (c) => request<BiSourcesList>(c, '/api/v1/bi/sources'),
    createDatasource: (c, id, req) => {
      const r = req as CreateDatasourceRequest & BiConnectionUpsert;
      return request(c, `/api/v1/bi/sources/${encodeURIComponent(id)}`, {
        method: 'PUT',
        body: JSON.stringify({
          label: r.label || r.name,
          driver: r.driver || 'postgresql',
          host: r.host,
          port: r.port,
          database: r.database,
          username: r.username,
          password: r.password,
          ssl: r.ssl,
        }),
      });
    },
    deleteDatasource: async () => ({ ok: false }),
    testDatasource: async (c, id) => {
      const raw = await request<{ ok?: boolean; message?: string }>(c, '/api/v1/bi/connection/test', {
        method: 'POST',
        body: JSON.stringify({ id }),
      });
      return { success: Boolean(raw.ok), ok: Boolean(raw.ok), message: raw.message };
    },
    startScan: async (): Promise<SchemaScan> => ({
      scanId: '',
      status: 'FAILED',
      error: 'Schema scan not available in LEGACY mode',
    }),
    getScan: async (): Promise<SchemaScan> => ({
      scanId: '',
      status: 'FAILED',
      error: 'Schema scan not available in LEGACY mode',
    }),
    activate: (c, id) =>
      request(c, `/api/v1/bi/sources/${encodeURIComponent(id)}/activate`, { method: 'POST' }),
  };
}
