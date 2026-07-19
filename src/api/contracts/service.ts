import type { ApiConfig } from '@/api/http';
import type {
  CreateDatasourceRequest,
  Datasource,
  DatasourceTestResult,
  SchemaScan,
} from '@/api/contracts/datasource';
import type { BiConnectionUpsert, BiSourcesList } from '@/api/types';

export interface DatasourceService {
  listDatasources(config: ApiConfig): Promise<BiSourcesList>;
  createDatasource(
    config: ApiConfig,
    id: string,
    request: CreateDatasourceRequest | BiConnectionUpsert,
  ): Promise<{ ok?: boolean; id?: string; source?: unknown }>;
  deleteDatasource(config: ApiConfig, id: string): Promise<{ ok: boolean }>;
  testDatasource(config: ApiConfig, id: string): Promise<DatasourceTestResult>;
  startScan(config: ApiConfig, id: string): Promise<SchemaScan>;
  getScan(config: ApiConfig, scanId: string): Promise<SchemaScan>;
  activate(config: ApiConfig, id: string): Promise<unknown>;
}

export type { Datasource };
