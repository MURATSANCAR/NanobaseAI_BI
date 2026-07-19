import { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { MessageSquare, Pin, PinOff, Sparkles, X } from 'lucide-react';
import clsx from 'clsx';
import BiChatPanel from '@/components/BiChatPanel';
import type { BiChatResponse } from '@/api/types';
import { t } from '@/i18n';

type BiAnalyticsChatDockProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pinned: boolean;
  onPinnedChange: (pinned: boolean) => void;
  sessionId: string;
  dashboardId?: string;
  initialMessage?: string;
  initialIntent?: string;
  onResponse?: (resp: BiChatResponse) => void;
};

export default function BiAnalyticsChatDock({
  open,
  onOpenChange,
  pinned,
  onPinnedChange,
  sessionId,
  dashboardId,
  initialMessage,
  initialIntent,
  onResponse,
}: BiAnalyticsChatDockProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleResponse = useCallback(
    (resp: BiChatResponse) => {
      onResponse?.(resp);
    },
    [onResponse],
  );

  const openChat = useCallback(() => {
    onOpenChange(true);
  }, [onOpenChange]);

  const closeChat = useCallback(() => {
    onOpenChange(false);
  }, [onOpenChange]);

  const handleBackdropClick = useCallback(() => {
    if (pinned) return;
    closeChat();
  }, [closeChat, pinned]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !pinned) closeChat();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [closeChat, open, pinned]);

  useEffect(() => {
    if (!open || typeof document === 'undefined') return;
    const prev = document.body.style.overflow;
    const isMobile = window.matchMedia('(max-width: 639px)').matches;
    if (isMobile) document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!mounted) return null;

  return createPortal(
    <>
      {open && (
        <button
          type="button"
          aria-label={t('bi.analytics.closeChat')}
          className="fixed inset-0 z-[60] bg-slate-900/40 backdrop-blur-[2px] sm:bg-slate-900/20 sm:backdrop-blur-[1px] md:bg-transparent md:backdrop-blur-none"
          onClick={handleBackdropClick}
        />
      )}

      <div
        ref={panelRef}
        className={clsx(
          'bi-pbi-tile bi-pbi-tile--dock fixed z-[70] flex flex-col overflow-hidden border border-white/80 bg-white/95 shadow-2xl shadow-violet-900/20 backdrop-blur-xl transition-all duration-300 ease-out',
          // Mobile: full-width bottom sheet
          'inset-x-0 bottom-0 max-sm:rounded-t-2xl max-sm:rounded-b-none max-sm:border-b-0',
          // Desktop / tablet: floating dock
          'sm:inset-x-auto sm:bottom-[max(0.75rem,env(safe-area-inset-bottom))] sm:right-[max(0.75rem,env(safe-area-inset-right))] sm:w-[min(calc(100vw-1.5rem),26rem)] sm:rounded-2xl',
          'md:w-[28rem]',
          open
            ? 'pointer-events-auto translate-y-0 scale-100 opacity-100'
            : 'pointer-events-none translate-y-6 scale-[0.98] opacity-0 sm:translate-y-3',
        )}
        style={{
          height: 'min(92dvh, 44rem)',
          maxHeight: 'calc(100dvh - env(safe-area-inset-top) - 0.5rem)',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
        role="dialog"
        aria-modal={open}
        aria-hidden={!open}
        aria-label={t('bi.analytics.chatDockTitle')}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bi-pbi-tile-accent" data-visual="card" aria-hidden />
        <div className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-slate-200 sm:hidden" aria-hidden />
        <div className="relative z-[1] flex shrink-0 items-center gap-2 border-b border-[#E1DFDD]/80 bg-gradient-to-r from-[#F8F7F6] to-white px-3 py-2.5">
          <MessageSquare className="h-4 w-4 shrink-0 text-violet-600" />
          <p className="min-w-0 flex-1 truncate text-sm font-semibold text-slate-800">
            {t('bi.analytics.chatDockTitle')}
          </p>
          <button
            type="button"
            className={clsx(
              'hidden rounded-lg p-1.5 transition sm:inline-flex',
              pinned ? 'bg-violet-100 text-violet-700' : 'text-slate-500 hover:bg-slate-100',
            )}
            onClick={() => onPinnedChange(!pinned)}
            title={pinned ? t('bi.analytics.unpinChat') : t('bi.analytics.pinChat')}
            aria-pressed={pinned}
          >
            {pinned ? <Pin className="h-4 w-4" /> : <PinOff className="h-4 w-4" />}
          </button>
          <button
            type="button"
            className="min-h-10 min-w-10 rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100"
            onClick={closeChat}
            aria-label={t('bi.analytics.closeChat')}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
          <BiChatPanel
            key={sessionId}
            sessionId={sessionId}
            dashboardId={dashboardId}
            embedded
            autoFocus={open}
            fullHeight
            initialMessage={initialMessage}
            initialIntent={initialIntent}
            className="h-full min-h-0"
            onResponse={handleResponse}
          />
        </div>
      </div>

      <button
        type="button"
        onClick={open ? closeChat : openChat}
        className={clsx(
          'bi-chat-fab relative fixed z-[80] flex items-center gap-2 rounded-full bg-gradient-to-br from-violet-600 to-blue-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-violet-600/30 transition-all duration-300 hover:scale-[1.02] hover:shadow-xl active:scale-[0.98]',
          'bottom-[max(0.75rem,env(safe-area-inset-bottom))] right-[max(0.75rem,env(safe-area-inset-right))]',
          open && 'pointer-events-none scale-90 opacity-0',
        )}
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
      </button>
    </>,
    document.body,
  );
}
