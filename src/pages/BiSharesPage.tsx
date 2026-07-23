import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Copy, Eye, Link2, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import ResponsiveTable from '@/components/ResponsiveTable';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import type { BiShareLink } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

/** 1 day / 1 week / 1 month / unlimited (0). */
const TTL_OPTIONS = [
  { value: 24, labelKey: 'bi.shareTtl.day' as const },
  { value: 168, labelKey: 'bi.shareTtl.week' as const },
  { value: 720, labelKey: 'bi.shareTtl.month' as const },
  { value: 0, labelKey: 'bi.shareTtl.unlimited' as const },
] as const;

type ShareView = { at: string; ip?: string; user_agent?: string };

function shareToken(r: BiShareLink & { token_hash?: string }): string | undefined {
  return r.token || undefined;
}

function shareKey(r: BiShareLink & { token_hash?: string }): string {
  return r.token || r.token_hash || r.resource_id || String(r.created_at || Math.random());
}

export default function BiSharesPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const [copiedToken, setCopiedToken] = useState<string | null>(null);
  const [ttlHours, setTtlHours] = useState<number>(168);
  const [password, setPassword] = useState('');
  const [selectedDashId, setSelectedDashId] = useState<number | null>(null);
  const [lastCreated, setLastCreated] = useState<BiShareLink | null>(null);
  const [viewsToken, setViewsToken] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const statusQ = useQuery({
    queryKey: ['bi-status', config],
    queryFn: () => api.bi.status(config),
    enabled: isRunnerConfigured(config),
    staleTime: 60_000,
  });
  const shareEnabled = statusQ.data?.capabilities?.share !== false;

  const analyticsBoards = useQuery({
    queryKey: ['bi-analytics-dashboards'],
    queryFn: () => api.bi.analytics.dashboards(config),
    enabled: isRunnerConfigured(config),
    staleTime: 60_000,
  });
  const shares = useQuery({
    queryKey: ['bi-shares', config],
    queryFn: () => api.bi.shares.list(config),
    enabled: isRunnerConfigured(config),
  });
  const views = useQuery({
    queryKey: ['bi-share-views', config, viewsToken],
    queryFn: () => api.bi.shares.views(config, viewsToken!),
    enabled: isRunnerConfigured(config) && Boolean(viewsToken),
  });

  const dashboards = analyticsBoards.data?.dashboards ?? [];
  const activeDashId = useMemo(() => {
    if (selectedDashId != null) return selectedDashId;
    return dashboards[0]?.id ?? null;
  }, [selectedDashId, dashboards]);

  const createMut = useMutation({
    mutationFn: (dashboardId: number) =>
      api.bi.shares.create(config, {
        resource_type: 'superset_dashboard',
        resource_id: String(dashboardId),
        ttl_hours: ttlHours === 0 ? 0 : ttlHours,
        password: password.trim() || undefined,
      }),
    onSuccess: (link) => {
      setCreateError(null);
      setLastCreated(link);
      setPassword('');
      void qc.invalidateQueries({ queryKey: ['bi-shares'] });
    },
    onError: (err) => {
      setCreateError(localizeUserMessage((err as Error).message) || (err as Error).message);
    },
  });

  const delMut = useMutation({
    mutationFn: (token: string) => api.bi.shares.delete(config, token),
    onSuccess: () => {
      if (viewsToken) setViewsToken(null);
      qc.invalidateQueries({ queryKey: ['bi-shares'] });
    },
  });

  const publicBase = `${window.location.origin}/bi/public/`;
  const shareRows = (shares.data?.shares ?? []) as Array<BiShareLink & { token_hash?: string }>;
  const viewRows: ShareView[] = views.data?.views ?? [];

  const copy = async (token: string) => {
    try {
      await navigator.clipboard.writeText(`${publicBase}${token}`);
      setCopiedToken(token);
      window.setTimeout(() => setCopiedToken(null), 2500);
    } catch {
      window.prompt(t('bi.copyLink'), `${publicBase}${token}`);
    }
  };

  const createShare = () => {
    if (!shareEnabled) {
      setCreateError(t('bi.sharesDisabledTitle'));
      return;
    }
    if (activeDashId == null) {
      setCreateError(t('bi.shareNoDashboards'));
      return;
    }
    setCreateError(null);
    createMut.mutate(activeDashId);
  };

  return (
    <PageShell pageId="biShares" titleKey="bi.sharesTitle" subtitleKey="bi.sharesSubtitle">
      {!shareEnabled && statusQ.isFetched ? (
        <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <p className="font-medium">{t('bi.sharesDisabledTitle')}</p>
          <p className="mt-1 text-amber-900/90">{t('bi.sharesDisabledBody')}</p>
        </div>
      ) : null}
      {createError ? <p className="mb-3 text-sm text-status-fail">{createError}</p> : null}
      {copiedToken && <p className="mb-3 text-sm text-status-ok">{t('bi.linkCopied')}</p>}
      {lastCreated?.token && (
        <div className="mb-3 flex flex-col gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-950 sm:flex-row sm:items-center sm:justify-between">
          <p>
            {t('bi.shareCreatedMeta', {
              views: String(lastCreated.view_count ?? 0),
              expires: lastCreated.expires_at?.slice(0, 16) ?? t('bi.shareTtl.unlimited'),
            })}
          </p>
          <button
            type="button"
            className="btn-primary inline-flex min-h-10 items-center justify-center gap-1.5 px-3 text-xs"
            onClick={() => void copy(lastCreated.token!)}
          >
            <Copy className="h-3.5 w-3.5" /> {t('bi.copyLink')}
          </button>
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <div className="w-full min-w-0 sm:w-auto sm:min-w-[12rem]">
          <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.shareDashboard')}</label>
          <select
            className="input-field"
            value={activeDashId ?? ''}
            onChange={(e) => setSelectedDashId(Number(e.target.value) || null)}
            disabled={!dashboards.length || !shareEnabled}
          >
            {!dashboards.length && <option value="">{t('bi.shareNoDashboards')}</option>}
            {dashboards.map((d) => (
              <option key={d.id} value={d.id}>
                {d.title || `Dashboard ${d.id}`}
              </option>
            ))}
          </select>
        </div>
        <div className="w-full min-w-0 sm:w-auto">
          <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.shareTtl')}</label>
          <select
            className="input-field"
            value={ttlHours}
            disabled={!shareEnabled}
            onChange={(e) => setTtlHours(Number(e.target.value))}
          >
            {TTL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.labelKey)}
              </option>
            ))}
          </select>
        </div>
        <div className="w-full min-w-0 flex-1">
          <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.sharePasswordOptional')}</label>
          <input
            className="input-field text-base sm:text-sm"
            type="password"
            value={password}
            disabled={!shareEnabled}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t('bi.sharePasswordPlaceholder')}
            autoComplete="new-password"
          />
        </div>
        <button
          type="button"
          className="btn-primary flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
          onClick={createShare}
          disabled={!shareEnabled || createMut.isPending}
          title={
            !shareEnabled
              ? t('bi.sharesDisabledTitle')
              : activeDashId == null
                ? t('bi.shareNoDashboards')
                : undefined
          }
        >
          <Link2 className="h-4 w-4" /> {t('bi.createShare')}
        </button>
      </div>

      {!shareRows.length && !shares.isLoading ? (
        <EmptyState
          emoji="🔗"
          titleKey={
            !shareEnabled
              ? 'bi.sharesDisabledTitle'
              : !dashboards.length
                ? 'bi.shareNoDashboards'
                : 'empty.bi.shares.title'
          }
          descriptionKey={shareEnabled ? 'empty.bi.shares.description' : 'bi.sharesDisabledBody'}
          ctaLabelKey={
            !shareEnabled
              ? undefined
              : dashboards.length
                ? 'empty.bi.shares.cta'
                : 'nav.biDashboard'
          }
          ctaTo={!shareEnabled ? undefined : dashboards.length ? undefined : '/bi'}
          onCtaClick={shareEnabled && dashboards.length ? createShare : undefined}
        />
      ) : (
        <ResponsiveTable<BiShareLink & { token_hash?: string }>
          columns={[
            { id: 'type', header: t('bi.shareLink'), mobilePrimary: true, cell: (r) => `${r.resource_type}: ${r.resource_id}` },
            {
              id: 'exp',
              header: t('bi.shareExpires'),
              mobileLabel: t('bi.shareExpires'),
              cell: (r) => (r.expires_at ? r.expires_at.slice(0, 16) : t('bi.shareTtl.unlimited')),
            },
            { id: 'views', header: t('bi.shareViews'), mobileLabel: t('bi.shareViews'), cell: (r) => String(r.view_count ?? 0) },
            {
              id: 'lock',
              header: t('bi.sharePassword'),
              mobileLabel: t('bi.sharePassword'),
              cell: (r) => (r.password_protected ? t('bi.shareLocked') : t('bi.shareOpen')),
            },
            {
              id: 'actions',
              header: t('common.actions'),
              mobileLabel: t('common.actions'),
              cell: (r) => {
                const token = shareToken(r);
                const manageId = token || r.token_hash;
                return (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      className="inline-flex min-h-10 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-accent hover:bg-violet-50 disabled:opacity-40"
                      disabled={!token}
                      title={!token ? t('bi.shareTokenMissing') : t('bi.copyLink')}
                      onClick={() => token && void copy(token)}
                    >
                      <Copy className="h-4 w-4" /> {t('bi.copyLink')}
                    </button>
                    <button
                      type="button"
                      className="inline-flex min-h-10 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40"
                      disabled={!manageId}
                      title={!manageId ? t('bi.shareTokenMissing') : t('bi.shareViews')}
                      onClick={() => manageId && setViewsToken(manageId)}
                    >
                      <Eye className="h-4 w-4" /> {t('bi.shareViews')}
                    </button>
                    <button
                      type="button"
                      className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-status-fail hover:bg-red-50 disabled:opacity-40"
                      title={t('common.delete')}
                      disabled={!manageId}
                      onClick={() => {
                        if (manageId && window.confirm(t('bi.deleteShareConfirm'))) delMut.mutate(manageId);
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                );
              },
            },
          ]}
          rows={shareRows}
          rowKey={(r) => shareKey(r)}
        />
      )}

      {viewsToken && (
        <div className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold text-slate-800">{t('bi.shareViewLogTitle')}</h3>
            <button type="button" className="inline-flex min-h-10 items-center rounded-lg px-2 text-sm text-slate-500 hover:bg-slate-50 hover:underline" onClick={() => setViewsToken(null)}>
              {t('common.close')}
            </button>
          </div>
          <p className="mb-3 text-xs text-slate-500">
            {t('bi.shareViewLogCount', { count: String(views.data?.view_count ?? 0) })}
          </p>
          {!viewRows.length && !views.isLoading ? (
            <p className="text-sm text-slate-500">{t('bi.shareViewLogEmpty')}</p>
          ) : (
            <ul className="max-h-64 space-y-2 overflow-y-auto text-xs text-slate-700">
              {viewRows.map((v, idx) => (
                <li key={`${v.at}-${idx}`} className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2">
                  <p className="font-medium">{v.at?.slice(0, 19)?.replace('T', ' ') ?? '—'}</p>
                  <p className="mt-0.5 text-slate-500">{t('bi.shareViewLogIp', { ip: v.ip || '—' })}</p>
                  {v.user_agent ? <p className="mt-0.5 truncate text-slate-400">{v.user_agent}</p> : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </PageShell>
  );
}
