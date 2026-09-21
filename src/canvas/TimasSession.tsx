import { useEffect } from 'react';
import { editorialHomeOptions } from './editorial/homeQuery';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Outlet } from 'react-router-dom';
import SessionGate from './stitch/SessionGate';
import GreetingsInbox from './kampus/GreetingsInbox';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, clearAuthBlock } from './engine';

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
      // Oturum geçerli: 401 yüzünden durmuş yoklamalar (uyarılar, CFO) yeniden başlar.
      clearAuthBlock();
      // username: hesap adı (pano anahtarı); displayName: AD'deki ad soyad.
      return (await res.json()) as { username: string; displayName?: string };
    },
    enabled: ENGINE_ENABLED,
    retry: false,
    staleTime: 5 * 60_000,
  });
}

export default function RequireTimasSession() {
  const qc = useQueryClient();
  const q = useTimasSession();
  useEffect(() => {
    if (q.data?.username && !q.error) {
      void qc.prefetchQuery(editorialHomeOptions(q.data.username));
      void import('./editorial/EditorialHome').catch(() => undefined);
    }
  }, [qc, q.data?.username, q.error]);
  if (!ENGINE_ENABLED) return <Outlet />;
  if (q.isLoading) {
    return <div className="flex min-h-[40vh] items-center justify-center text-slate-500">Yükleniyor…</div>;
  }
  if (q.error instanceof EngineAuthError) {
    return <SessionGate onDone={() => void qc.invalidateQueries()} />;
  }
  return (
    <>
      <GreetingsInbox />
      <Outlet />
    </>
  );
}
