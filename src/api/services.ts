import { getApiMode } from '@/config/environment';
import type { DatasourceService } from '@/api/contracts/service';
import { createNanobaseDatasourceService } from '@/api/adapters/nanobase/datasource-api';
import { createLegacyDatasourceService } from '@/api/adapters/legacy/legacy-datasource-api';
import { request, type ApiConfig } from '@/api/http';

let _ds: DatasourceService | null = null;

export function createDatasourceService(): DatasourceService {
  if (!_ds) {
    _ds = getApiMode() === 'LEGACY' ? createLegacyDatasourceService() : createNanobaseDatasourceService();
  }
  return _ds;
}

/** Reset factory (tests). */
export function resetDatasourceService(): void {
  _ds = null;
}

export type FeedbackPayload = {
  question: string;
  rating: -1 | 1;
  sql?: string;
  session_id?: string;
  comment?: string;
  datasource_id?: string;
  promote_verified?: boolean;
};

export function submitQueryFeedback(config: ApiConfig, body: FeedbackPayload) {
  return request<{ ok?: boolean }>(config, '/api/v1/bi/query/feedback', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export { createNanobaseDatasourceService, createLegacyDatasourceService };
