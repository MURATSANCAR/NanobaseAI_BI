import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Outlet } from 'react-router-dom';
import SessionGate from './stitch/SessionGate';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError } from './engine';

/**
 * Timaş oturum kapısı. Giriş yalnız Timaş giriş servisindedir (`/timas/auth/`); eski portal servisi
 * artık sorulmaz. Oturum yoksa giriş formu açılır, varsa ekran. Giriş servisine hiç ulaşılamazsa
 * ekran yine açılır: her ekran kendi verisinde oturumu ayrıca denetler, kişi boş sayfada kalmaz.
 */
export function useTimasSession() {
  return useQuery({
    queryKey: ['timas-session'],
    queryFn: async () => {
      const res = await fetch(`${ENGINE_BASE}/auth/session`, { credentials: 'include' });
      if (res.status === 401 || res.status === 403) throw new EngineAuthError();
      if (!res.ok) throw new Error(`Oturum servisi ${res.status}`);
      return (await res.json()) as { username: string };
    },
    enabled: ENGINE_ENABLED,
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export default function RequireTimasSession() {
  const qc = useQueryClient();
  const q = useTimasSession();
  if (!ENGINE_ENABLED) return <Outlet />;
  if (q.isLoading) {
    return <div className="flex min-h-[40vh] items-center justify-center text-slate-500">Yükleniyor…</div>;
  }
  if (q.error instanceof EngineAuthError) {
    return <SessionGate onDone={() => void qc.invalidateQueries()} />;
  }
  return <Outlet />;
}
