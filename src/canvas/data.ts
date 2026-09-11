import { useQuery } from '@tanstack/react-query';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import type { BiSchedule } from '@/api/types';
import { ENGINE_ENABLED, alertsApi, type AlertEmail, type AlertRule } from './engine';

/** Kanvasın tüm sorguları buradan geçer; anahtarlar mevcut sayfalarla aynı
 *  ki bir yerde yapılan değişiklik ötekini de tazelesin. */
export function useCanvasQueries() {
  const { config } = useApiConfig();
  const on = isRunnerConfigured(config);

  const schedules = useQuery({
    queryKey: ['bi-schedules', config],
    queryFn: () => api.bi.schedules(config),
    enabled: on,
  });

  // Uyarılar motorun kendi kurallarıdır; kontrolü sunucu yapar, ekran yalnız durumu okur.
  const alerts = useQuery({
    queryKey: ['zeki-uyarilar'],
    queryFn: alertsApi.list,
    enabled: ENGINE_ENABLED,
    refetchInterval: 60_000,
    retry: false,
  });

  const analyticsStatus = useQuery({
    queryKey: ['bi-analytics-status', config],
    queryFn: () => api.bi.analytics.status(config),
    enabled: on,
    staleTime: 90_000,
  });

  const dashboards = useQuery({
    queryKey: ['bi-analytics-dashboards', config],
    queryFn: () => api.bi.analytics.dashboards(config),
    enabled: on,
  });

  return { config, on, schedules, alerts, analyticsStatus, dashboards };
}

/* ------------------------------------------------------------------ */
/* Türetilmiş özetler — ekranlar ham diziyle değil, bu özetlerle çalışır */
/* ------------------------------------------------------------------ */

const lower = (s: string | undefined) => (s || '').toLowerCase();

export type ScheduleSummary = {
  items: BiSchedule[];
  total: number;
  active: number;
  paused: number;
  failed: number;
  sent: number;
  /** En yakın gönderim: yalnız `pending` olanlar arasında en erken `run_at`. */
  next: BiSchedule | null;
  /** Alıcısı boş olanlar — sessizce hiçbir yere gitmeyen raporlar. */
  recipientless: BiSchedule[];
  /** Eski arayüzde hiç gösterilmeyen `error` alanını taşıyan son başarısız iş. */
  lastFailure: BiSchedule | null;
  withAlerts: number;
  withNarrative: number;
  upcoming: BiSchedule[];
};

export function summarizeSchedules(items: BiSchedule[]): ScheduleSummary {
  const by = (s: string) => items.filter((i) => lower(i.status) === s).length;
  const pending = items.filter((i) => lower(i.status) === 'pending' && i.run_at);
  const upcoming = [...pending].sort((a, b) => (a.run_at > b.run_at ? 1 : -1));
  const failed = items
    .filter((i) => lower(i.status) === 'failed' || i.error)
    .sort((a, b) => ((a.sent_at ?? a.run_at) < (b.sent_at ?? b.run_at) ? 1 : -1));
  return {
    items,
    total: items.length,
    active: by('pending'),
    paused: by('paused'),
    failed: items.filter((i) => lower(i.status) === 'failed').length,
    sent: items.filter((i) => ['sent', 'completed'].includes(lower(i.status))).length,
    next: upcoming[0] ?? null,
    recipientless: items.filter((i) => !i.recipient?.trim()),
    lastFailure: failed[0] ?? null,
    withAlerts: items.filter((i) => i.include_alerts !== false).length,
    withNarrative: items.filter((i) => Boolean(i.include_narrative)).length,
    upcoming: upcoming.slice(0, 5),
  };
}

export type AlertSummary = {
  items: AlertRule[];
  total: number;
  active: number;
  paused: number;
  /** Şu an eşiği aşanlar: son kontrolde koşul sağlandı. */
  triggered: AlertRule[];
  /** Son kontrolde ölçülemeyenler: soru tek değer döndürmedi ya da sorgu hata verdi. */
  errored: AlertRule[];
  /** Henüz hiç ölçülmemişler. */
  neverChecked: AlertRule[];
  /** Alıcısı olmayanlar: tetiklenince kimseye e-posta gitmez. */
  noRecipient: AlertRule[];
  /** Eşiğe yakınlık: son değer ile eşik arasındaki mesafe, %100 = eşikte ya da aşmış. */
  proximity: Array<{ rule: AlertRule; pct: number; distance: number | null }>;
  lastCheckedAt: string | null;
  email: AlertEmail;
};

export function summarizeAlerts(
  items: AlertRule[],
  email: AlertEmail = { configured: false, sender: null },
): AlertSummary {
  const active = items.filter((r) => r.status !== 'paused');
  const checked = items
    .map((r) => r.last_checked_at)
    .filter((v): v is string => Boolean(v))
    .sort();
  return {
    items,
    total: items.length,
    active: active.length,
    paused: items.filter((r) => r.status === 'paused').length,
    triggered: active.filter((r) => r.state === 'triggered'),
    errored: active.filter((r) => r.state === 'error'),
    neverChecked: items.filter((r) => !r.last_checked_at),
    noRecipient: items.filter((r) => !(r.recipients ?? []).length),
    proximity: active
      .filter((r) => r.state !== 'error')
      .map((r) => {
        if (r.last_value == null || !Number.isFinite(r.threshold)) {
          return { rule: r, pct: 0, distance: null };
        }
        const span = Math.abs(r.threshold) || 1;
        const distance = r.last_value - r.threshold;
        const pct = Math.max(0, Math.min(100, 100 - (Math.abs(distance) / span) * 100));
        return { rule: r, pct: r.state === 'triggered' ? 100 : pct, distance };
      })
      .sort((a, b) => b.pct - a.pct)
      .slice(0, 4),
    lastCheckedAt: checked.length ? checked[checked.length - 1] : null,
    email,
  };
}

