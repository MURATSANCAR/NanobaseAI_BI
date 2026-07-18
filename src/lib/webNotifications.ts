/** Browser Notification helpers for long-running BI chat jobs. */

export type NotifyPermission = NotificationPermission | 'unsupported';

export function notificationSupport(): boolean {
  return typeof window !== 'undefined' && 'Notification' in window;
}

export function getNotifyPermission(): NotifyPermission {
  if (!notificationSupport()) return 'unsupported';
  return Notification.permission;
}

/** Safe to call from a user gesture (e.g. Send). No-ops if already decided. */
export async function ensureNotifyPermission(): Promise<NotifyPermission> {
  if (!notificationSupport()) return 'unsupported';
  if (Notification.permission !== 'default') return Notification.permission;
  try {
    const result = await Notification.requestPermission();
    return result;
  } catch {
    return Notification.permission;
  }
}

function truncate(text: string, max = 120): string {
  const cleaned = text.replace(/\s+/g, ' ').trim();
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max - 1)}…`;
}

export function showWebNotification(opts: {
  title: string;
  body: string;
  tag?: string;
  onClick?: () => void;
}): Notification | null {
  if (!notificationSupport() || Notification.permission !== 'granted') return null;
  try {
    const options: NotificationOptions & { renotify?: boolean } = {
      body: truncate(opts.body, 180),
      tag: opts.tag,
      renotify: Boolean(opts.tag),
    };
    const n = new Notification(opts.title, options);
    if (opts.onClick) {
      n.onclick = () => {
        try {
          window.focus();
        } catch {
          /* ignore */
        }
        opts.onClick?.();
        n.close();
      };
    }
    return n;
  } catch {
    return null;
  }
}
