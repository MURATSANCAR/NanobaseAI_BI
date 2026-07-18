import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useLocation, useSearchParams } from 'react-router-dom';
import BiAnalyticsChatDock from '@/components/bi/BiAnalyticsChatDock';
import type { BiChatResponse } from '@/api/types';

export type OpenBiChatOptions = {
  /** Prefill the composer (user can edit before send). */
  prompt?: string;
};

type BiChatDockContextValue = {
  open: boolean;
  openChat: (opts?: OpenBiChatOptions) => void;
  closeChat: () => void;
  setDashboardId: (id?: string) => void;
  /** Subscribe to chat responses (e.g. analytics canvas refresh). Returns unsubscribe. */
  registerOnResponse: (fn: (resp: BiChatResponse) => void) => () => void;
};

const BiChatDockContext = createContext<BiChatDockContextValue | null>(null);

function isBiDockPath(pathname: string): boolean {
  if (!pathname.startsWith('/bi')) return false;
  if (pathname.startsWith('/bi/chat')) return false;
  if (pathname.startsWith('/bi/public')) return false;
  return true;
}

export function BiChatDockProvider({ children }: { children: ReactNode }) {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const showDock = isBiDockPath(location.pathname);

  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pendingPrompt, setPendingPrompt] = useState<string | undefined>();
  const [dashboardId, setDashboardIdState] = useState<string | undefined>();
  const [sessionId] = useState(() => `bi-dock-${Date.now().toString(36)}`);
  const listenersRef = useRef(new Set<(resp: BiChatResponse) => void>());

  const openChat = useCallback((opts?: OpenBiChatOptions) => {
    if (opts?.prompt) setPendingPrompt(opts.prompt);
    setOpen(true);
  }, []);

  const closeChat = useCallback(() => {
    setOpen(false);
  }, []);

  const setDashboardId = useCallback((id?: string) => {
    setDashboardIdState(id);
  }, []);

  const registerOnResponse = useCallback((fn: (resp: BiChatResponse) => void) => {
    listenersRef.current.add(fn);
    return () => {
      listenersRef.current.delete(fn);
    };
  }, []);

  const handleResponse = useCallback((resp: BiChatResponse) => {
    for (const fn of listenersRef.current) {
      try {
        fn(resp);
      } catch {
        /* ignore listener errors */
      }
    }
  }, []);

  // Deep-link: ?chat=1 and/or ?ask=… open the in-page dock on any BI screen.
  const consumedDeepLink = useRef<string | null>(null);
  useEffect(() => {
    if (!showDock) return;
    const ask = searchParams.get('ask') ?? searchParams.get('q') ?? undefined;
    const wantChat = searchParams.get('chat') === '1' || Boolean(ask);
    if (!wantChat) return;
    const key = `${location.pathname}?${searchParams.toString()}`;
    if (consumedDeepLink.current === key) return;
    consumedDeepLink.current = key;
    openChat({ prompt: ask || undefined });
    const next = new URLSearchParams(searchParams);
    next.delete('ask');
    next.delete('q');
    next.delete('chat');
    setSearchParams(next, { replace: true });
  }, [showDock, location.pathname, searchParams, setSearchParams, openChat]);

  const value = useMemo(
    () => ({
      open,
      openChat,
      closeChat,
      setDashboardId,
      registerOnResponse,
    }),
    [open, openChat, closeChat, setDashboardId, registerOnResponse],
  );

  return (
    <BiChatDockContext.Provider value={value}>
      {children}
      {showDock ? (
        <BiAnalyticsChatDock
          open={open}
          onOpenChange={setOpen}
          pinned={pinned}
          onPinnedChange={setPinned}
          sessionId={sessionId}
          dashboardId={dashboardId}
          initialMessage={pendingPrompt}
          onResponse={handleResponse}
        />
      ) : null}
    </BiChatDockContext.Provider>
  );
}

export function useBiChatDock(): BiChatDockContextValue {
  const ctx = useContext(BiChatDockContext);
  if (!ctx) {
    throw new Error('useBiChatDock must be used within BiChatDockProvider');
  }
  return ctx;
}

/** Safe hook when the provider may be absent (non-BI routes). */
export function useBiChatDockOptional(): BiChatDockContextValue | null {
  return useContext(BiChatDockContext);
}
