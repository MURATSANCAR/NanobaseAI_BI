import { useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import AiAmbientShow from '@/components/AiAmbientShow';
import { BiVisualChart } from '@/components/bi/BiCharts';
import BiPbiTile from '@/components/bi/BiPbiTile';
import BiSupersetEmbed from '@/components/bi/BiSupersetEmbed';
import { isCompactVisual, widgetVisualType } from '@/components/bi/biVisualTypes';
import { loadApiConfig, api, isRunnerConfigured } from '@/api/client';
import type { BiWidget } from '@/api/types';
import { getLocale, t } from '@/i18n';
import { biWidgetTitle } from '@/lib/biWidgetTitle';
import { localizeUserMessage } from '@/utils/backendLabels';

function resolveAssetUrl(base: string, url?: string | null): string | undefined {
  if (!url) return undefined;
  if (/^https?:\/\//i.test(url) || url.startsWith('data:')) return url;
  const root = base.replace(/\/$/, '');
  return url.startsWith('/') ? `${root}${url}` : `${root}/${url}`;
}

type PublicResource = {
  title?: string;
  widgets?: BiWidget[];
  id?: number;
  token?: string;
  embed_uuid?: string;
  analytics_url?: string;
  branding?: { brand_name?: string; logo_url?: string; primary_color?: string; footer_text?: string };
};

export default function BiPublicPage() {
  const { token } = useParams();
  const config = loadApiConfig();
  const base = config.baseUrl || window.location.origin;
  const [password, setPassword] = useState('');
  const [unlocked, setUnlocked] = useState<Record<string, unknown> | null>(null);
  const [unlockPassword, setUnlockPassword] = useState<string | null>(null);
  const initialBumpDone = useRef(false);

  const settings = useQuery({
    queryKey: ['bi-public-settings', config],
    queryFn: () => api.bi.settings.get(config),
    enabled: isRunnerConfigured(config),
    retry: false,
  });

  const data = useQuery({
    queryKey: ['bi-public', token],
    queryFn: async () => {
      const live = initialBumpDone.current;
      const payload = await api.bi.publicShare(base, token!, { live });
      initialBumpDone.current = true;
      return payload;
    },
    enabled: Boolean(token) && !unlocked,
    refetchInterval: unlocked ? false : 30_000,
  });

  useEffect(() => {
    if (!unlocked || !unlockPassword || !token) return;
    const id = window.setInterval(() => {
      void api.bi
        .unlockPublicShare(base, token, unlockPassword, { live: true })
        .then((payload) => setUnlocked(payload))
        .catch(() => undefined);
    }, 30_000);
    return () => window.clearInterval(id);
  }, [unlocked, unlockPassword, token, base]);

  const unlockMut = useMutation({
    mutationFn: () => api.bi.unlockPublicShare(base, token!, password),
    onSuccess: (payload) => {
      setUnlockPassword(password);
      setUnlocked(payload);
    },
  });

  const payload = unlocked ?? data.data;
  const locked = Boolean(payload?.locked || payload?.requires_password);
  const shareType = String(payload?.type || '');
  const resource = payload?.resource as PublicResource | undefined;
  const branding = resource?.branding ?? settings.data;
  const primary = branding?.primary_color || '#6366f1';
  const footerText = branding?.footer_text;
  const shareMeta = payload?.share as { view_count?: number; expires_at?: string } | undefined;
  const logoSrc = resolveAssetUrl(base, branding?.logo_url);
  const isSuperset = shareType === 'superset_dashboard' && Boolean(resource?.embed_uuid && resource?.analytics_url);
  const answerMd = String((payload as { answer_md?: string } | undefined)?.answer_md || '');
  const isChatAnswer =
    ['chat_answer', 'query_result'].includes(String((payload as { resource_type?: string })?.resource_type || shareType))
    && Boolean(answerMd || (payload as { artifact?: unknown })?.artifact);
  const isBudgetPack =
    String((payload as { resource_type?: string })?.resource_type || shareType) === 'budget_pack';
  const widgets = (Array.isArray(resource?.widgets) ? resource!.widgets! : []) as BiWidget[];
  const isWidgetShare = widgets.length > 0;
  const budgetSummary = (payload as { summary?: { totals?: Record<string, number>; budget_watch_count?: number } })
    ?.summary;
  const budgetRows =
    ((payload as { rows?: Array<Record<string, unknown>> })?.rows as Array<Record<string, unknown>> | undefined) || [];
  const budgetTitle =
    String((payload as { title?: string })?.title || '') ||
    (isBudgetPack ? t('bi.budget.publicPackTitle') : '');
  const budgetReportCcy = String((payload as { reporting_currency?: string })?.reporting_currency || '').trim().toUpperCase();
  const budgetScenario = String((payload as { scenario?: string })?.scenario || 'base');
  const needsUnlock = locked && !unlocked;
  const isLive = (isWidgetShare || isSuperset || isChatAnswer || isBudgetPack) && !locked;
  const locale = getLocale();

  const money = (n: unknown, currency = 'TRY') => {
    const v = typeof n === 'number' ? n : Number(n);
    if (n == null || Number.isNaN(v)) return '—';
    try {
      return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(v);
    } catch {
      return String(n);
    }
  };

  return (
    <div className="relative flex min-h-[100dvh] flex-col bg-gradient-to-br from-sky-50 via-white to-indigo-50 px-3 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))] sm:px-4 sm:p-6">
      <AiAmbientShow variant="bi" intensity="subtle" />
      <div className="relative z-10 mx-auto flex w-full max-w-6xl flex-1 flex-col" style={{ ['--bi-primary' as string]: primary }}>
        <header className="mb-4 flex flex-col gap-3 rounded-2xl border border-white/70 bg-white/60 p-3 shadow-lg backdrop-blur-xl sm:mb-6 sm:flex-row sm:items-center sm:p-4">
          {logoSrc ? (
            <img src={logoSrc} alt="" className="h-10 w-auto object-contain" />
          ) : (
            <div className="flex h-10 w-10 items-center justify-center rounded-lg text-xs font-bold text-white" style={{ backgroundColor: primary }}>
              AI
            </div>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-bold text-slate-900">
                {budgetTitle || resource?.title || t('bi.publicShareTitle')}
              </h1>
              {isLive && (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-800">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                  {t('bi.shareLiveBadge')}
                </span>
              )}
            </div>
            <p className="text-sm text-slate-500">{branding?.brand_name || 'NanobaseAI'}</p>
            {shareMeta?.expires_at && (
              <p className="mt-1 text-xs text-slate-400">
                {t('bi.shareExpires')}: {shareMeta.expires_at.slice(0, 16)} · {t('bi.shareViews')}: {shareMeta.view_count ?? 0}
              </p>
            )}
          </div>
        </header>

        {needsUnlock && (
          <div className="card mx-auto max-w-md space-y-3 p-6">
            <h2 className="text-sm font-semibold text-slate-900">{t('bi.shareUnlockTitle')}</h2>
            <p className="text-xs text-slate-500">{t('bi.shareUnlockHint')}</p>
            <input
              className="input-field text-base sm:text-sm"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t('bi.sharePasswordPlaceholder')}
              onKeyDown={(e) => {
                if (e.key === 'Enter') unlockMut.mutate();
              }}
            />
            <button type="button" className="btn-primary min-h-11 w-full" disabled={unlockMut.isPending || !password} onClick={() => unlockMut.mutate()}>
              {t('bi.shareUnlockCta')}
            </button>
            {unlockMut.isError && (
              <p className="text-sm text-status-fail">
                {localizeUserMessage((unlockMut.error as Error).message) || t('bi.shareUnlockFailed')}
              </p>
            )}
          </div>
        )}

        {data.isError && !needsUnlock && (
          <p className="text-status-fail">
            {localizeUserMessage((data.error as Error).message) || t('bi.publicShareLoadFailed')}
          </p>
        )}
        {isWidgetShare && !locked && (
          <div className="bi-fluent-canvas grid grid-cols-1 gap-3 rounded-2xl border border-[#E1DFDD]/80 bg-white/70 p-3 sm:grid-cols-2 sm:p-4">
            {widgets.map((widget, index) => {
              const visual = widgetVisualType(widget);
              const compact = isCompactVisual(visual);
              const wide = visual === 'table' || visual === 'matrix';
              return (
                <BiPbiTile
                  key={widget.id || `${visual}-${index}`}
                  visualType={visual}
                  accentIndex={index}
                  title={biWidgetTitle(widget, locale)}
                  compact
                  kpi={compact}
                  className={wide ? 'sm:col-span-2' : undefined}
                  bodyClassName={compact ? 'p-2' : 'p-2 pt-1'}
                >
                  <BiVisualChart widget={widget} variant="preview" />
                </BiPbiTile>
              );
            })}
          </div>
        )}
        {isSuperset && !locked && resource?.embed_uuid && resource.analytics_url && resource.id != null && (
          <div className="bi-fluent-canvas bi-analytics-viewer min-h-0 flex-1 overflow-hidden rounded-2xl border border-[#E1DFDD] bg-[#F5F5F5] shadow-lg h-[min(72dvh,720px)] sm:h-[70vh] sm:min-h-[420px]">
            <BiSupersetEmbed
              config={config}
              embedUuid={String(resource.embed_uuid)}
              dashboardId={Number(resource.id)}
              analyticsUrl={String(resource.analytics_url)}
              guestToken={resource.token}
              className="h-full"
            />
          </div>
        )}
        {isChatAnswer && !locked && (
          <div className="card space-y-3 p-6">
            <h2 className="text-sm font-semibold text-slate-900">
              {(payload as { title?: string })?.title || t('bi.publicShareTitle')}
            </h2>
            <div className="whitespace-pre-wrap text-sm text-slate-800">{answerMd}</div>
            {(payload as { sql_fingerprint?: string })?.sql_fingerprint ? (
              <p className="text-xs text-slate-500">
                {t('bi.prove.fingerprint')}:{' '}
                <code>{String((payload as { sql_fingerprint?: string }).sql_fingerprint)}</code>
              </p>
            ) : null}
            <p className="text-xs text-slate-400">{t('bi.prove.sqlHidden')}</p>
          </div>
        )}
        {isBudgetPack && !locked && (
          <div className="space-y-4">
            <p className="text-xs text-slate-500">
              {t('bi.budget.publicPackMeta', {
                scenario: budgetScenario,
                currency: budgetReportCcy || t('bi.budget.reportingCurrencyNone'),
              })}
            </p>
            {(payload as { narrative?: string })?.narrative ? (
              <div className="card p-4 text-sm text-slate-700">
                {String((payload as { narrative?: string }).narrative)}
              </div>
            ) : null}
            <div className="grid gap-3 sm:grid-cols-4">
              <div className="card p-3">
                <p className="text-[11px] uppercase text-slate-500">{t('bi.budget.kpiAllocated')}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {money(budgetSummary?.totals?.allocated, budgetReportCcy || 'TRY')}
                </p>
              </div>
              <div className="card p-3">
                <p className="text-[11px] uppercase text-slate-500">{t('bi.budget.kpiActual')}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {money(budgetSummary?.totals?.actual, budgetReportCcy || 'TRY')}
                </p>
              </div>
              <div className="card p-3">
                <p className="text-[11px] uppercase text-slate-500">{t('bi.budget.kpiRemaining')}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {money(budgetSummary?.totals?.remaining, budgetReportCcy || 'TRY')}
                </p>
              </div>
              <div className="card p-3">
                <p className="text-[11px] uppercase text-slate-500">{t('bi.budget.kpiWatch')}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{budgetSummary?.budget_watch_count ?? 0}</p>
              </div>
            </div>
            <div className="card overflow-x-auto p-0">
              <table className="min-w-full text-left text-sm">
                <thead className="border-b border-slate-100 bg-slate-50 text-[11px] uppercase text-slate-500">
                  <tr>
                    <th className="px-3 py-2">{t('bi.budget.name')}</th>
                    <th className="px-3 py-2">{t('bi.budget.kind')}</th>
                    <th className="px-3 py-2">{t('bi.budget.allocated')}</th>
                    <th className="px-3 py-2">{t('bi.budget.committed')}</th>
                    <th className="px-3 py-2">{t('bi.budget.actual')}</th>
                    <th className="px-3 py-2">{t('bi.budget.remaining')}</th>
                    <th className="px-3 py-2">{t('bi.budget.usedPct')}</th>
                    <th className="px-3 py-2">{t('bi.budget.health')}</th>
                  </tr>
                </thead>
                <tbody>
                  {budgetRows.map((r) => (
                    <tr key={String(r.id || r.name)} className="border-b border-slate-50">
                      <td className="px-3 py-2 font-medium text-slate-900">{String(r.name || '—')}</td>
                      <td className="px-3 py-2 text-slate-600">{String(r.kind || '—')}</td>
                      <td className="px-3 py-2 tabular-nums">
                        {money(r.allocated, budgetReportCcy || String(r.currency || 'TRY'))}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {money(r.committed, budgetReportCcy || String(r.currency || 'TRY'))}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {money(r.actual, budgetReportCcy || String(r.currency || 'TRY'))}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {money(r.remaining, budgetReportCcy || String(r.currency || 'TRY'))}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {r.used_pct != null ? `${Number(r.used_pct).toFixed(2)}%` : '—'}
                      </td>
                      <td className="px-3 py-2 text-slate-600">{String(r.health || '—')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {footerText && (
          <footer className="mt-6 border-t border-surface-border pt-4 text-center text-xs text-slate-500 sm:mt-8">
            {footerText}
          </footer>
        )}
      </div>
    </div>
  );
}
