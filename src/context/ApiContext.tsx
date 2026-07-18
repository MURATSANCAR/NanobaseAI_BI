import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  COOKIE_AUTH_SENTINEL,
  loadApiConfig,
  saveApiConfig,
  type ApiConfig,
} from '@/api/client';
import { resolvePortalBranding, type PortalBranding } from '@/utils/portalBranding';

type ApiContextValue = {
  config: ApiConfig;
  setConfig: (next: ApiConfig) => void;
  refreshRuntimeConfig: () => Promise<ApiConfig>;
  ready: boolean;
  authRequired: boolean;
  portalUsersEnabled: boolean;
  portalAutoLogin: boolean;
  httponlyApiKey: boolean;
  portalBranding: PortalBranding;
  refreshPortalBranding: () => Promise<void>;
};

const ApiContext = createContext<ApiContextValue | null>(null);

type PortalRuntimeConfig = {
  apiKey?: string;
  baseUrl?: string;
  role?: string;
  authMode?: 'cookie' | 'bearer';
  apiKeyConfigured?: boolean;
  authenticated?: boolean;
  portalAutoLogin?: boolean;
  brandName?: string;
  showPoweredBy?: boolean;
};

type PortalBootstrapConfig = {
  auth_required: boolean;
  portal_users_enabled?: boolean;
  portal_auto_login?: boolean;
  httponly_api_key?: boolean;
  portal_brand_name?: string | null;
  portal_show_powered_by?: boolean;
};

function portalApiRoot(): string {
  return String(import.meta.env.VITE_API_BASE || '')
    .trim()
    .replace(/\/$/, '');
}

async function loadRuntimeConfig(): Promise<PortalRuntimeConfig | null> {
  const root = portalApiRoot();
  const sources = [`${root}/api/v1/portal/runtime-config`, `${root}/config.json`, '/config.json'];
  const stored = loadApiConfig();
  const session =
    (typeof localStorage !== 'undefined' && localStorage.getItem('nanobase_qa_session')) ||
    stored.sessionToken ||
    '';
  const headers: Record<string, string> = {};
  if (session) headers['X-Portal-Session'] = session;

  for (const url of sources) {
    try {
      const res = await fetch(url, { cache: 'no-store', credentials: 'include', headers });
      if (!res.ok) continue;
      const text = await res.text();
      if (!text.trim()) continue;
      const parsed = JSON.parse(text) as PortalRuntimeConfig;
      if (parsed.authMode === 'cookie' || parsed.apiKey || parsed.apiKeyConfigured) return parsed;
    } catch {
      /* try next source */
    }
  }
  return null;
}

async function loadBootstrap(): Promise<PortalBootstrapConfig> {
  try {
    const root = portalApiRoot();
    const res = await fetch(`${root}/api/v1/portal/bootstrap`, {
      cache: 'no-store',
      credentials: 'include',
    });
    if (!res.ok) return { auth_required: true };
    const data = (await res.json()) as PortalBootstrapConfig;
    return {
      auth_required: data.auth_required !== false,
      portal_users_enabled: data.portal_users_enabled,
      portal_auto_login: data.portal_auto_login,
      httponly_api_key: data.httponly_api_key,
      portal_brand_name: data.portal_brand_name,
      portal_show_powered_by: data.portal_show_powered_by,
    };
  } catch {
    return { auth_required: true };
  }
}

function mergeConfig(stored: ApiConfig, runtime: PortalRuntimeConfig | null): ApiConfig {
  const envBase = portalApiRoot();
  if (!runtime) {
    return envBase && !stored.baseUrl ? { ...stored, baseUrl: envBase } : stored;
  }
  const role = runtime.role ?? stored.role ?? 'admin';
  if (runtime.authMode === 'cookie') {
    return {
      baseUrl: runtime.baseUrl ?? stored.baseUrl ?? envBase ?? '',
      apiKey: COOKIE_AUTH_SENTINEL,
      role,
      authMode: 'cookie',
      sessionToken: stored.sessionToken,
      tenantId: stored.tenantId,
      projectId: stored.projectId,
    };
  }
  return {
    baseUrl: runtime.baseUrl ?? stored.baseUrl ?? envBase ?? '',
    apiKey: runtime.apiKey ?? stored.apiKey ?? '',
    role,
    authMode: runtime.authMode ?? stored.authMode ?? 'bearer',
    sessionToken: stored.sessionToken,
    tenantId: stored.tenantId,
    projectId: stored.projectId,
  };
}

export async function fetchRuntimeApiConfig(): Promise<PortalRuntimeConfig | null> {
  return loadRuntimeConfig();
}

export async function establishRunnerSession(apiKey: string): Promise<void> {
  const root = portalApiRoot();
  const res = await fetch(`${root}/api/v1/portal/session`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
}

export async function clearRunnerSession(): Promise<void> {
  const root = portalApiRoot();
  await fetch(`${root}/api/v1/portal/session`, { method: 'DELETE', credentials: 'include' });
}

export function ApiProvider({ children }: { children: ReactNode }) {
  const [config, setConfigState] = useState<ApiConfig>(() => loadApiConfig());
  const [ready, setReady] = useState(false);
  const [authRequired, setAuthRequired] = useState(true);
  const [portalUsersEnabled, setPortalUsersEnabled] = useState(false);
  const [portalAutoLogin, setPortalAutoLogin] = useState(false);
  const [httponlyApiKey, setHttponlyApiKey] = useState(false);
  const [portalBranding, setPortalBranding] = useState<PortalBranding>(() =>
    resolvePortalBranding({}),
  );

  const refreshRuntimeConfig = useCallback(async (): Promise<ApiConfig> => {
    const runtime = await loadRuntimeConfig();
    const stored = loadApiConfig();
    const merged = mergeConfig(stored, runtime);
    saveApiConfig(merged);
    setConfigState(merged);
    return merged;
  }, []);

  const refreshPortalBranding = useCallback(async () => {
    const bootstrap = await loadBootstrap();
    setPortalBranding(
      resolvePortalBranding({
        portal_brand_name: bootstrap.portal_brand_name,
        portal_show_powered_by: bootstrap.portal_show_powered_by,
      }),
    );
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const [runtime, bootstrap] = await Promise.all([loadRuntimeConfig(), loadBootstrap()]);
      if (cancelled) return;

      const stored = loadApiConfig();
      const merged = mergeConfig(stored, runtime);
      saveApiConfig(merged);
      setConfigState(merged);
      setAuthRequired(Boolean(bootstrap.auth_required));
      setPortalUsersEnabled(Boolean(bootstrap.portal_users_enabled));
      setPortalAutoLogin(Boolean(bootstrap.portal_auto_login));
      setHttponlyApiKey(Boolean(bootstrap.httponly_api_key));
      setPortalBranding(
        resolvePortalBranding({
          portal_brand_name: bootstrap.portal_brand_name,
          portal_show_powered_by: bootstrap.portal_show_powered_by,
          brandName: runtime?.brandName,
          showPoweredBy: runtime?.showPoweredBy,
        }),
      );
      setReady(true);
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo(
    () => ({
      config,
      setConfig: (next: ApiConfig) => {
        saveApiConfig(next);
        setConfigState(next);
      },
      refreshRuntimeConfig,
      ready,
      authRequired,
      portalUsersEnabled,
      portalAutoLogin,
      httponlyApiKey,
      portalBranding,
      refreshPortalBranding,
    }),
    [
      config,
      ready,
      authRequired,
      portalUsersEnabled,
      portalAutoLogin,
      httponlyApiKey,
      portalBranding,
      refreshRuntimeConfig,
      refreshPortalBranding,
    ],
  );

  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

export function useApiConfig() {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error('useApiConfig outside provider');
  return ctx;
}
