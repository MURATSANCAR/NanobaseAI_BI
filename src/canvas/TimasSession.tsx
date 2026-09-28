import { useEffect, useRef } from 'react';
import { prefetchEditorialLists } from './editorial/queries';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Outlet } from 'react-router-dom';
import SessionGate from './stitch/SessionGate';
import GreetingsInbox from './kampus/GreetingsInbox';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, clearAuthBlock } from './engine';
import { canSeePage, usePageAccess } from './useAdmin';
import { httpErrorText } from './httpError';

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
      if (!res.ok) throw new Error(httpErrorText(res.status));
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
  const pages = usePageAccess();
  // Editoryal ön yüklemesi yalnız Masam'ı görebilen kişi için: ötekinde köprü 403 verir.
  const editorial = canSeePage(pages, 'editoryal');
  useEffect(() => {
    if (q.data?.username && !q.error && editorial) {
      void prefetchEditorialLists(qc, q.data.username);
      void import('./editorial/EditorialHome').catch(() => undefined);
    }
  }, [qc, q.data?.username, q.error, editorial]);
  // Son sonuç akılda tutulur: hata almış sorgu yeniden sorulurken «bekliyor»a döner ve hatası silinir.
  // Kapı o an «Yükleniyor»a geçerse ekran sökülür, yeniden kurulan kabuk sorguyu tekrar sordurur ve
  // döngü saniyede onlarca istek atar. «Yükleniyor» yalnız ilk cevaptan önce gösterilir.
  const authFailed = useRef(false);
  if (q.status === 'error') authFailed.current = q.error instanceof EngineAuthError;
  else if (q.status === 'success') authFailed.current = false;
  if (!ENGINE_ENABLED) return <Outlet />;
  if (q.isPending && q.errorUpdateCount === 0) {
    return <div className="flex min-h-[40vh] items-center justify-center text-slate-500">Yükleniyor…</div>;
  }
  if (authFailed.current) {
    return <SessionGate onDone={() => void qc.invalidateQueries()} />;
  }
  return (
    <>
      <GreetingsInbox />
      <Outlet />
    </>
  );
}
