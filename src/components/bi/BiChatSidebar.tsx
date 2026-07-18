import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { MessageSquare, Pencil, Plus, Trash2, X } from 'lucide-react';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';
import { sortByIsoDateDesc } from '@/utils/sort';

type Props = {
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  className?: string;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
};

function formatSessionMeta(count?: number, updatedAt?: string): string {
  const msgs = t('bi.chatSessionMsgCount', { count: String(count ?? 0) });
  if (!updatedAt) return msgs;
  try {
    const d = new Date(updatedAt);
    if (Number.isNaN(d.getTime())) return msgs;
    const when = d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    return `${msgs} · ${when}`;
  } catch {
    return msgs;
  }
}

export function BiChatSidebarContent({
  activeId,
  onSelect,
  onNew,
  dense = false,
}: Omit<Props, 'className' | 'mobileOpen' | 'onMobileClose'> & { dense?: boolean }) {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const sessions = useQuery({
    queryKey: ['bi-chat-sessions', config],
    queryFn: () => api.bi.chatSessions(config),
    enabled: isRunnerConfigured(config),
    refetchInterval: 15000,
  });
  const delMut = useMutation({
    mutationFn: (id: string) => api.bi.deleteChatSession(config, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-chat-sessions'] }),
  });
  const renameMut = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.bi.renameChatSession(config, id, title),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-chat-sessions'] }),
  });

  const items = sortByIsoDateDesc(sessions.data?.sessions ?? [], (s) => s.updated_at);

  const rename = (id: string, current?: string) => {
    const title = window.prompt(t('bi.renameSession'), current || '');
    if (title?.trim()) renameMut.mutate({ id, title: title.trim() });
  };

  const remove = (id: string) => {
    if (window.confirm(t('bi.deleteSessionConfirm'))) delMut.mutate(id);
  };

  return (
    <>
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-200/90 px-3 py-2 sm:px-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">{t('bi.chatSessions')}</p>
          <p className="hidden text-xs text-slate-500 xl:block">{t('bi.chatSessionsHint')}</p>
        </div>
        <button
          type="button"
          className="inline-flex h-9 min-w-[2.25rem] items-center justify-center gap-1.5 rounded-xl bg-violet-600 px-2.5 text-sm font-semibold text-white shadow-sm hover:bg-violet-700"
          onClick={onNew}
          title={t('bi.chatNewSession')}
        >
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">{t('bi.chatNewSessionShort')}</span>
        </button>
      </div>
      <div className={clsx('flex-1 overflow-y-auto overscroll-contain p-2 sm:p-3', dense && 'pb-6')}>
        {items.length === 0 && (
          <p className="rounded-xl bg-slate-50 px-3 py-4 text-sm leading-relaxed text-slate-500">
            {t('bi.chatSessionsEmpty')}
          </p>
        )}
        <ul className="space-y-1.5">
          {items.map((s) => {
            const active = activeId === s.session_id;
            const label = s.title || s.preview || s.session_id;
            return (
              <li key={s.session_id}>
                <div
                  className={clsx(
                    'group flex items-stretch gap-1 rounded-xl border transition-colors',
                    active
                      ? 'border-violet-300 bg-violet-50 shadow-sm'
                      : 'border-transparent bg-white hover:border-slate-200 hover:bg-slate-50',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(s.session_id)}
                    className={clsx(
                      'flex min-h-[3.25rem] min-w-0 flex-1 items-start gap-2.5 px-3 py-2.5 text-left',
                      active ? 'text-violet-950' : 'text-slate-800',
                    )}
                  >
                    <span
                      className={clsx(
                        'mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg',
                        active ? 'bg-violet-600 text-white' : 'bg-slate-100 text-slate-500',
                      )}
                    >
                      <MessageSquare className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="line-clamp-2 text-sm font-semibold leading-snug">{label}</span>
                      <span className="mt-0.5 block text-xs text-slate-500">
                        {formatSessionMeta(s.message_count, s.updated_at)}
                      </span>
                    </span>
                  </button>
                  <div className="flex shrink-0 flex-col justify-center gap-0.5 pr-1.5 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100">
                    <button
                      type="button"
                      className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-violet-100 hover:text-violet-700"
                      onClick={() => rename(s.session_id, s.title || s.preview)}
                      title={t('bi.renameSession')}
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 hover:bg-rose-50 hover:text-status-fail"
                      onClick={() => remove(s.session_id)}
                      title={t('bi.deleteSession')}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </>
  );
}

export default function BiChatSidebar({
  className,
  mobileOpen,
  onMobileClose,
  ...contentProps
}: Props) {
  return (
    <>
      {/* Desktop / tablet rail — className carries grid column spans from parent */}
      <aside className={clsx('bi-chat-sidebar card-static hidden min-h-0 flex-col overflow-hidden lg:flex', className)}>
        <BiChatSidebarContent {...contentProps} />
      </aside>

      {/* Mobile drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <button type="button" className="absolute inset-0 bg-slate-900/45" aria-label={t('common.close')} onClick={onMobileClose} />
          <div className="bi-chat-sidebar-drawer absolute inset-y-0 left-0 flex w-[min(100vw-2.5rem,22rem)] max-w-full flex-col bg-white shadow-2xl">
            <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
              <div>
                <p className="text-base font-semibold text-slate-900">{t('bi.chatHistoryMobile')}</p>
                <p className="text-xs text-slate-500">{t('bi.chatSessionsHint')}</p>
              </div>
              <button
                type="button"
                className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50"
                onClick={onMobileClose}
                aria-label={t('common.close')}
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col">
              <BiChatSidebarContent {...contentProps} dense />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
