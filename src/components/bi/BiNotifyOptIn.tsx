import { useEffect, useState } from 'react';
import { Bell, X } from 'lucide-react';
import {
  ensureNotifyPermission,
  getNotifyPermission,
  notificationSupport,
  type NotifyPermission,
} from '@/lib/webNotifications';
import { t } from '@/i18n';

const DISMISS_KEY = 'nanobase_bi_notify_optin_dismissed';

/**
 * Soft prompt on BI entry: ask for web/mobile browser push permission once.
 * Actual alert delivery uses Notification API while the portal (or PWA) is open.
 */
export default function BiNotifyOptIn() {
  const [perm, setPerm] = useState<NotifyPermission>(() => getNotifyPermission());
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!notificationSupport()) return;
    if (perm !== 'default') return;
    try {
      if (localStorage.getItem(DISMISS_KEY) === '1') return;
    } catch {
      /* ignore */
    }
    const id = window.setTimeout(() => setVisible(true), 800);
    return () => window.clearTimeout(id);
  }, [perm]);

  if (!visible || perm !== 'default') return null;

  return (
    <div
      className="fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-[80] w-[min(calc(100vw-1.5rem),28rem)] -translate-x-1/2 rounded-2xl border border-violet-200 bg-white/95 p-3 shadow-xl shadow-violet-900/15 backdrop-blur-md sm:left-auto sm:right-[max(1rem,env(safe-area-inset-right))] sm:translate-x-0"
      role="dialog"
      aria-label={t('bi.notify.optInTitle')}
    >
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-700">
          <Bell className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-slate-900">{t('bi.notify.optInTitle')}</p>
          <p className="mt-0.5 text-xs text-slate-600">{t('bi.notify.optInBody')}</p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary inline-flex min-h-9 items-center px-3 text-xs"
              onClick={() => {
                void ensureNotifyPermission().then((next) => {
                  setPerm(next);
                  setVisible(false);
                });
              }}
            >
              {t('bi.notify.optInAllow')}
            </button>
            <button
              type="button"
              className="btn-secondary inline-flex min-h-9 items-center px-3 text-xs"
              onClick={() => {
                try {
                  localStorage.setItem(DISMISS_KEY, '1');
                } catch {
                  /* ignore */
                }
                setVisible(false);
              }}
            >
              {t('bi.notify.optInLater')}
            </button>
          </div>
        </div>
        <button
          type="button"
          className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          aria-label={t('common.close')}
          onClick={() => {
            try {
              localStorage.setItem(DISMISS_KEY, '1');
            } catch {
              /* ignore */
            }
            setVisible(false);
          }}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
