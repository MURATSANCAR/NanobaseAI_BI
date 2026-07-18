import { request, type ApiConfig } from './http';
import type { PortalUserPrefs, PortalUserRecord, PortalUserUpsert } from './portal-users';

export function createPortalApi() {
  return {
    login: (c: ApiConfig, body: { username: string; password: string }) =>
      request<{ token: string; user: PortalUserRecord }>(c, '/api/v1/portal/auth/login', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    logout: (c: ApiConfig) =>
      request<void>(c, '/api/v1/portal/auth/logout', { method: 'POST' }),
    me: (c: ApiConfig) => request<PortalUserRecord>(c, '/api/v1/portal/auth/me'),
    updateMe: (c: ApiConfig, body: PortalUserPrefs) =>
      request<PortalUserRecord>(c, '/api/v1/portal/auth/me', {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    listUsers: (c: ApiConfig) => request<PortalUserRecord[]>(c, '/api/v1/portal/users'),
    createUser: (c: ApiConfig, body: PortalUserUpsert) =>
      request<PortalUserRecord>(c, '/api/v1/portal/users', { method: 'POST', body: JSON.stringify(body) }),
    updateUser: (c: ApiConfig, userId: string, body: Partial<PortalUserUpsert> & { active?: boolean }) =>
      request<PortalUserRecord>(c, `/api/v1/portal/users/${userId}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      }),
    deleteUser: (c: ApiConfig, userId: string) =>
      request<void>(c, `/api/v1/portal/users/${userId}`, { method: 'DELETE' }),
  };
}
