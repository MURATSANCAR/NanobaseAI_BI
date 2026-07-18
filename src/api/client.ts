import { createBiApi } from './bi-api';
import { createPortalApi } from './portal-api';
import {
  apiBase,
  buildRunnerHeaders,
  COOKIE_AUTH_SENTINEL,
  isRunnerConfigured,
  loadApiConfig,
  request,
  requestText,
  runnerFetch,
  saveApiConfig,
  withSessionConfig,
  type ApiConfig,
} from './http';

export type { ApiConfig } from './http';
export type { PortalUserRecord, PortalUserUpsert, PortalUserPrefs } from './portal-users';
export type * from './bi-types';
export type * from './types';

export {
  apiBase,
  buildRunnerHeaders,
  COOKIE_AUTH_SENTINEL,
  isRunnerConfigured,
  loadApiConfig,
  request,
  requestText,
  runnerFetch,
  saveApiConfig,
  withSessionConfig,
};

const bi = createBiApi();

export const api = {
  bi,
  portal: createPortalApi(),
  llm: {
    status: (c: ApiConfig) =>
      request<{
        llm_configured?: boolean;
        busy?: boolean;
        stopping?: boolean;
        slot?: {
          id?: number;
          id_task?: number;
          n_prompt_tokens?: number;
          n_prompt_tokens_processed?: number;
          is_processing?: boolean;
        } | null;
        slot_reachable?: boolean;
        leases?: Array<{
          lease_id: string;
          app?: string;
          purpose?: string;
          job_ref?: string | null;
          started_at?: string;
          status?: string;
        }>;
        primary_lease_id?: string | null;
      }>(c, '/api/v1/llm/status'),
    cancel: (c: ApiConfig, body?: { lease_id?: string; cancel_all?: boolean }) =>
      request<{
        ok?: boolean;
        code?: string;
        message?: string;
        cancelled?: unknown[];
        stopping?: boolean;
        slot_still_busy?: boolean;
      }>(c, '/api/v1/llm/cancel', {
        method: 'POST',
        body: JSON.stringify(body || {}),
      }),
  },
  bootstrap: () =>
    fetch('/api/v1/portal/bootstrap').then(
      (r) =>
        r.json() as Promise<{
          auth_required: boolean;
          portal_users_enabled?: boolean;
          supported_locales?: string[];
          portal_modules?: string[];
          portal_brand_name?: string | null;
          portal_show_powered_by?: boolean;
        }>,
    ),
};

export type BiApi = typeof api.bi;
