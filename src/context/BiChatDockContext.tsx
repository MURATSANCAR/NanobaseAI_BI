import {
  createContext,
  lazy,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { createPortal } from 'react-dom';
import { useLocation, useSearchParams } from 'react-router-dom';
import { MessageSquare, Sparkles } from 'lucide-react';
import BiNotifyOptIn from '@/components/bi/BiNotifyOptIn';
import type { BiChatResponse } from '@/api/types';
import { ALERT_CREATE_INTENT } from '@/lib/alertChatIntent';
import { t } from '@/i18n';

// Heavy dock (BiChatPanel → charts) stays out of the entry bundle: it is
// fetched + mounted only after the operator opens the chat for the first time.
const BiAnalyticsChatDock = lazy(() => import('@/components/bi/BiAnalyticsChatDock'));

/** Lightweight launcher shown before the dock chunk is ever needed. Must stay
 *  visually identical to the FAB rendered inside BiAnalyticsChatDock. */
function BiChatDockFab({ onOpen }: { onOpen: () => void }) {
  if (typeof document === 'undefined') return null;
  return createPortal(
    <button
      type="button"
      onClick={onOpen}
      className="bi-chat-fab relative fixed z-[80] flex items-center gap-2 rounded-full bg-gradient-to-br from-violet-600 to-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-600/30 transition-all duration-300 hover:scale-[1.02] hover:shadow-xl active:scale-[0.98] bottom-[max(0.75rem,env(safe-area-inset-bottom))] right-[max(0.75rem,env(safe-area-inset-right))]"
      aria-label={t('bi.analytics.openChat')}
      data-testid="bi-analytics-chat-fab"
    >
      <span className="relative inline-flex">
        <MessageSquare className="h-5 w-5" />
        <span className="bi-chat-fab-ping" aria-hidden />
      </span>
      <span className="hidden sm:inline">{t('bi.analytics.openChat')}</span>
      <span className="bi-chat-fab-spark" aria-hidden>
        <Sparkles className="h-3 w-3" />
      </span>
    </button>,
    document.body,
  );
}

export type OpenBiChatOptions = {
  /** Prefill the composer (user can edit before send). */
  prompt?: string;
  /** Hidden model hint — e.g. create_alert keeps SQL setup off-screen. */
  intent?: typeof ALERT_CREATE_INTENT | string;
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
  /** Once true the dock chunk stays mounted so chat state survives close. */
  const [everOpened, setEverOpened] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pendingPrompt, setPendingPrompt] = useState<string | undefined>();
  const [pendingIntent, setPendingIntent] = useState<string | undefined>();
  const [dashboardId, setDashboardIdState] = useState<string | undefined>();
  const [sessionId] = useState(() => `bi-dock-${Date.now().toString(36)}`);
  const listenersRef = useRef(new Set<(resp: BiChatResponse) => void>());

  const openChat = useCallback((opts?: OpenBiChatOptions) => {
    if (opts?.prompt) setPendingPrompt(opts.prompt);
    setPendingIntent(opts?.intent);
    setEverOpened(true);
    setOpen(true);
  }, []);

  const handleOpenChange = useCallback((next: boolean) => {
    if (next) setEverOpened(true);
    setOpen(next);
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
        <>
          <BiNotifyOptIn />
          {everOpened ? (
            <Suspense fallback={null}>
              <BiAnalyticsChatDock
                open={open}
                onOpenChange={handleOpenChange}
                pinned={pinned}
                onPinnedChange={setPinned}
                sessionId={sessionId}
                dashboardId={dashboardId}
                initialMessage={pendingPrompt}
                initialIntent={pendingIntent}
                onResponse={handleResponse}
              />
            </Suspense>
          ) : (
            <BiChatDockFab onOpen={() => openChat()} />
          )}
        </>
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
