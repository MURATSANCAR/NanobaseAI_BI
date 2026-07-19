import { ApiError } from '@/api/api-error';
import { parseApiErrorBody } from '@/utils/backendLabels';

const STORAGE_KEY = 'nanobase_qa_api';

/** In-memory only — never persisted; cookie carries the real runner key. */
export const COOKIE_AUTH_SENTINEL = '__cookie_auth__';

export type ApiConfig = {
  baseUrl: string;
  apiKey: string;
  role: string;
  authMode?: 'cookie' | 'bearer';
  sessionToken?: string;
  tenantId?: string;
  projectId?: string;
  /** Contract Intelligence API (default: runner host :8791). */
  contractsBaseUrl?: string;
  /** Dedicated API key for contract-api (not the QA runner key). */
  contractsApiKey?: string;
};

export function isRunnerConfigured(config: ApiConfig): boolean {
  if (config.authMode === 'cookie') return true;
  const key = (config.apiKey || '').trim();
  return Boolean(key) && key !== COOKIE_AUTH_SENTINEL;
}

export function buildRunnerHeaders(
  config: ApiConfig,
  extra: Record<string, string> = {},
): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (config.apiKey && config.apiKey !== COOKIE_AUTH_SENTINEL) {
    headers.Authorization = `Bearer ${config.apiKey}`;
  }
  if (config.sessionToken) {
    headers['X-Portal-Session'] = config.sessionToken;
  }
  if (config.role) {
    headers['X-Nanobase-Role'] = config.role;
  }
  if (config.tenantId) {
    headers['X-Tenant-ID'] = config.tenantId;
  }
  if (config.projectId) {
    headers['X-Project-ID'] = config.projectId;
  }
  return headers;
}

export async function runnerFetch(
  config: ApiConfig,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const headers = buildRunnerHeaders(config, (init.headers as Record<string, string>) || {});
  const url = `${apiBase(config) || ''}${path}`;
  return fetch(url, { ...init, headers, credentials: 'include' });
}

function hydrateStoredConfig(raw: ApiConfig): ApiConfig {
  if (raw.authMode === 'cookie') {
    return { ...raw, apiKey: COOKIE_AUTH_SENTINEL };
  }
  return raw;
}

export function withSessionConfig(config: ApiConfig, sessionToken?: string): ApiConfig {
  return { ...config, sessionToken: sessionToken || config.sessionToken || '' };
}

export function loadApiConfig(): ApiConfig {
  const envBase = String(import.meta.env.VITE_API_BASE || '')
    .trim()
    .replace(/\/$/, '');
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const stored = hydrateStoredConfig(JSON.parse(raw) as ApiConfig);
      // Prefer build-time BI API prefix when stored base is empty
      if (!stored.baseUrl && envBase) return { ...stored, baseUrl: envBase };
      return stored;
    }
  } catch {
    /* ignore */
  }
  return { baseUrl: envBase, apiKey: '', role: 'admin', authMode: 'bearer' };
}

export function saveApiConfig(config: ApiConfig): void {
  const toStore: ApiConfig = {
    ...config,
    apiKey: config.authMode === 'cookie' || config.apiKey === COOKIE_AUTH_SENTINEL ? '' : config.apiKey,
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore));
}

export function apiBase(config: ApiConfig): string {
  return (config.baseUrl || '').replace(/\/$/, '');
}

export function parseApiError(text: string, status: number): string {
  return parseApiErrorBody(text, status);
}

export async function request<T>(
  config: ApiConfig,
  path: string,
  init: RequestInit = {},
  timeoutMs = 120_000,
): Promise<T> {
  const headers = buildRunnerHeaders(config, {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>),
  });

  const url = `${apiBase(config) || ''}${path}`;
  const res = await fetch(url, {
    ...init,
    headers,
    credentials: 'include',
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) {
    const text = await res.text();
    let body: Record<string, unknown> | null = null;
    try {
      body = JSON.parse(text) as Record<string, unknown>;
    } catch {
      body = null;
    }
    if (body && (body.code || body.traceId || body.trace_id)) {
      const err = new ApiError({
        code: String(body.code || 'INTERNAL_ERROR'),
        message: String(body.message || body.error || `HTTP ${res.status}`),
        traceId: String(body.traceId || body.trace_id || ''),
        status: res.status,
        details: Array.isArray(body.details) ? (body.details as ApiError['details']) : [],
      });
      throw new Error(err.userMessage());
    }
    throw new Error(parseApiError(text, res.status));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export async function requestText(config: ApiConfig, path: string, timeoutMs = 120_000): Promise<string> {
  const headers = buildRunnerHeaders(config);
  const url = `${apiBase(config) || ''}${path}`;
  const res = await fetch(url, { headers, credentials: 'include', signal: AbortSignal.timeout(timeoutMs) });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseApiError(text, res.status));
  }
  return res.text();
}
