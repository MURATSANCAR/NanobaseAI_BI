import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { api, isRunnerConfigured, loadApiConfig, saveApiConfig, withSessionConfig, type ApiConfig, type PortalUserRecord } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import type { PortalLocale } from '@/i18n';
import { normalizeActiveLocale, setLocale, t } from '@/i18n';
import { hydrateActiveProjectFromUser } from '@/hooks/useActiveProjectId';
import { canBi, type BiCapability } from '@/lib/biCapabilities';
import { normalizeUserModules, type PortalModule } from '@/lib/portalModules';

export type { PortalModule };
export type { BiCapability };

export type PortalUser = {
  id: string;
  username: string;
  display_name: string;
  modules: PortalModule[];
  locale: PortalLocale;
  role: string;
  project_ids?: string[];
  default_project_id?: string | null;
  is_user_admin: boolean;
  active: boolean;
};

const SESSION_KEY = 'nanobase_qa_session';
const AUTO_LOGIN_USER = 'admin';
const AUTO_LOGIN_PASSWORD = 'admin';

type AuthContextValue = {
  user: PortalUser | null;
  sessionToken: string;
  ready: boolean;
  portalUsersEnabled: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  hasModule: (module: PortalModule) => boolean;
  canBi: (capability: BiCapability) => boolean;
  isUserAdmin: boolean;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function loadSessionToken(): string {
  return localStorage.getItem(SESSION_KEY) || '';
}

function saveSessionToken(token: string): void {
  if (token) localStorage.setItem(SESSION_KEY, token);
  else localStorage.removeItem(SESSION_KEY);
}

function apiWithSession(config: ApiConfig, sessionToken: string): ApiConfig {
  return withSessionConfig(config, sessionToken);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const {
    ready: apiReady,
    portalUsersEnabled: usersEnabledFromBootstrap,
    portalAutoLogin,
    refreshRuntimeConfig,
  } = useApiConfig();
  const [sessionToken, setSessionToken] = useState(loadSessionToken);
  const [user, setUser] = useState<PortalUser | null>(null);
  const [ready, setReady] = useState(false);
  const [portalUsersEnabled, setPortalUsersEnabled] = useState(false);

  const applyLogin = useCallback((res: { token: string; user: PortalUserRecord }) => {
    saveSessionToken(res.token);
    setSessionToken(res.token);
    setUser({ ...res.user, modules: normalizeUserModules(res.user.modules) });
    setLocale(normalizeActiveLocale(res.user.locale));
    hydrateActiveProjectFromUser(res.user.default_project_id);
    const current = loadApiConfig();
    const tenantIds = res.user.tenant_ids ?? [];
    const projectIds = res.user.project_ids ?? [];
    const preferredProject =
      (res.user.default_project_id || '').trim() ||
      (projectIds.length === 1 ? projectIds[0] : current.projectId);
    const isAdmin = res.user.role === 'admin' || Boolean(res.user.is_user_admin);
    const preferredTenant =
      tenantIds.length === 1
        ? tenantIds[0]
        : tenantIds.length === 0 && isAdmin
          ? current.tenantId || 'default'
          : current.tenantId;
    saveApiConfig({
      ...current,
      role: res.user.role,
      sessionToken: res.token,
      tenantId: preferredTenant,
      projectId: preferredProject,
    });
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    let activeConfig = loadApiConfig();
    try {
      const res = await api.portal.login(activeConfig, { username, password });
      applyLogin(res);
      try {
        await refreshRuntimeConfig();
      } catch {
        /* cookie already set by login response */
      }
      return;
    } catch (err) {
      const message = (err as Error).message || '';
      const staleKey =
        message.includes(t('auth.invalidApiKey')) ||
        message.includes('Invalid API key') ||
        message.includes('403');
      if (!staleKey) throw err;
      activeConfig = await refreshRuntimeConfig();
      const res = await api.portal.login(activeConfig, { username, password });
      applyLogin(res);
      try {
        await refreshRuntimeConfig();
      } catch {
        /* ignore */
      }
    }
  }, [applyLogin, refreshRuntimeConfig]);

  const refreshUser = useCallback(async () => {
    const token = loadSessionToken();
    if (!token) {
      setUser(null);
      return;
    }
    try {
      const me = await api.portal.me(apiWithSession(loadApiConfig(), token));
      setUser({ ...me, modules: normalizeUserModules(me.modules) });
      setLocale(normalizeActiveLocale(me.locale));
      hydrateActiveProjectFromUser(me.default_project_id);
    } catch {
      saveSessionToken('');
      setSessionToken('');
      setUser(null);
    }
  }, []);

  useEffect(() => {
    if (!apiReady) return;

    let cancelled = false;
    setPortalUsersEnabled(usersEnabledFromBootstrap);

    if (!usersEnabledFromBootstrap) {
      setReady(true);
      // Open gate: still mint runner cookie via runtime-config.
      void Promise.resolve(refreshRuntimeConfig()).catch(() => undefined);
      return;
    }

    (async () => {
      const token = loadSessionToken();
      if (token) {
        try {
          // Re-mint HttpOnly runner cookie from portal session before /me.
          await refreshRuntimeConfig();
          if (cancelled) return;
          const me = await api.portal.me(apiWithSession(loadApiConfig(), token));
          if (cancelled) return;
          setUser({ ...me, modules: normalizeUserModules(me.modules) });
          setLocale(normalizeActiveLocale(me.locale));
          hydrateActiveProjectFromUser(me.default_project_id);
          setReady(true);
          return;
        } catch {
          saveSessionToken('');
          setSessionToken('');
        }
      }

      // Never auto-login in production; only when bootstrap explicitly enables demo mode.
      // Use loadApiConfig() — do not depend on `config` state (refreshRuntimeConfig would re-trigger forever).
      const activeConfig = loadApiConfig();
      if (portalAutoLogin && isRunnerConfigured(activeConfig)) {
        try {
          const res = await api.portal.login(activeConfig, {
            username: AUTO_LOGIN_USER,
            password: AUTO_LOGIN_PASSWORD,
          });
          if (cancelled) return;
          applyLogin(res);
        } catch {
          try {
            const refreshed = await refreshRuntimeConfig();
            if (cancelled || !isRunnerConfigured(refreshed)) return;
            const res = await api.portal.login(refreshed, {
              username: AUTO_LOGIN_USER,
              password: AUTO_LOGIN_PASSWORD,
            });
            if (cancelled) return;
            applyLogin(res);
          } catch {
            /* portal stays on login screen if auto-login fails */
          }
        }
      }

      if (!cancelled) setReady(true);
    })();

    return () => {
      cancelled = true;
    };
    // Intentionally omit `config`: refreshRuntimeConfig updates it and would loop auth forever.
  }, [apiReady, applyLogin, usersEnabledFromBootstrap, portalAutoLogin, refreshRuntimeConfig]);

  const logout = useCallback(async () => {
    const token = loadSessionToken();
    if (token) {
      try {
        await api.portal.logout(apiWithSession(loadApiConfig(), token));
      } catch {
        /* ignore */
      }
    }
    saveSessionToken('');
    setSessionToken('');
    setUser(null);
    const current = loadApiConfig();
    saveApiConfig({ ...current, sessionToken: '', role: 'qa' });
  }, []);

  const hasModule = useCallback(
    (module: PortalModule) => {
      if (!portalUsersEnabled || !user) return true;
      if (user.role === 'admin' || user.is_user_admin) return true;
      return user.modules.includes(module);
    },
    [portalUsersEnabled, user],
  );

  const canBiCap = useCallback(
    (capability: BiCapability) => {
      if (!portalUsersEnabled) return true;
      if (!user) return canBi('qa', capability);
      if (user.is_user_admin) return canBi('admin', capability);
      return canBi(user.role, capability);
    },
    [portalUsersEnabled, user],
  );

  const value = useMemo(
    () => ({
      user,
      sessionToken,
      ready,
      portalUsersEnabled,
      login,
      logout,
      refreshUser,
      hasModule,
      canBi: canBiCap,
      isUserAdmin: Boolean(user?.is_user_admin),
    }),
    [user, sessionToken, ready, portalUsersEnabled, login, logout, refreshUser, hasModule, canBiCap],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside provider');
  return ctx;
}
