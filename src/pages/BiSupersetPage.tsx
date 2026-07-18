import { useCallback, useEffect, useRef, useState } from 'react';
import { useOutletContext, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronDown,
  GitBranch,
  LayoutDashboard,
  ListOrdered,
  Maximize2,
  Menu,
  MessageCircle,
  MessageSquare,
  Minimize2,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import clsx from 'clsx';
import BiCommentsDrawer from '@/components/bi/BiCommentsDrawer';
import BiDashboardWidgetsPanel from '@/components/bi/BiDashboardWidgetsPanel';
import BiMorningBriefing from '@/components/bi/BiMorningBriefing';
import BiNarrativeStrip from '@/components/bi/BiNarrativeStrip';
import BiSupersetEmbed from '@/components/bi/BiSupersetEmbed';
import type { LayoutOutletContext } from '@/components/Layout';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import type { BiChatResponse } from '@/api/types';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type EmbedState = {
  embedUuid: string;
  dashboardId: number;
  analyticsUrl: string;
  token?: string;
  title?: string;
};

export default function BiSupersetPage() {
  const { config } = useApiConfig();
  const { openMenu } = useOutletContext<LayoutOutletContext>();
  const { open: chatOpen, openChat, setDashboardId, registerOnResponse } = useBiChatDock();
  const qc = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const viewerRef = useRef<HTMLDivElement>(null);
  const dashboardFromUrl = searchParams.get('dashboard');
  const anomalyFromUrl = searchParams.get('anomaly');
  const artifactFromUrl = searchParams.get('artifact');
  const metricFromUrl = searchParams.get('metric');
  const [embed, setEmbed] = useState<EmbedState | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [browserFullscreen, setBrowserFullscreen] = useState(false);
  const [openError, setOpenError] = useState<string | null>(null);
  const [sidePanel, setSidePanel] = useState<'comments' | 'widgets' | 'none'>(() =>
    searchParams.get('comments') === '1' ? 'comments' : 'none',
  );
  const [embedNonce, setEmbedNonce] = useState(0);
  const [artifactBanner, setArtifactBanner] = useState<string | null>(null);
  const [anomalyBanner, setAnomalyBanner] = useState<string | null>(
    () => (anomalyFromUrl ? anomalyFromUrl : null),
  );
  const narrow = useMediaQuery('(max-width: 639px)');
  const hideBriefing = narrow && chatOpen;
  const runnerReady = isRunnerConfigured(config);

  const statusQ = useQuery({
    queryKey: ['bi-analytics-status'],
    queryFn: () => api.bi.analytics.status(config),
    enabled: runnerReady,
    staleTime: 90_000,
  });

  const dashboardsQ = useQuery({
    queryKey: ['bi-analytics-dashboards'],
    queryFn: () => api.bi.analytics.dashboards(config),
    enabled: runnerReady && Boolean(statusQ.data?.enabled),
    staleTime: 60_000,
  });

  const setEmbedFromGuest = useCallback(
    (guest: NonNullable<BiChatResponse['analytics']>['guest'], title?: string) => {
      if (!guest?.embed_uuid || !guest.dashboard_id || !guest.analytics_url) return;
      setEmbed({
        embedUuid: String(guest.embed_uuid),
        dashboardId: Number(guest.dashboard_id),
        analyticsUrl: String(guest.analytics_url),
        token: guest.token ? String(guest.token) : undefined,
        title,
      });
      setOpenError(null);
    },
    [],
  );

  const openDashboard = useCallback(
    async (id: number, title?: string) => {
      try {
        setOpenError(null);
        const guest = await api.bi.analytics.guestToken(config, id);
        setEmbedFromGuest(guest, title);
        setEmbedNonce((n) => n + 1);
        setPickerOpen(false);
      } catch (exc) {
        setOpenError(exc instanceof Error ? exc.message : String(exc));
      }
    },
    [config, setEmbedFromGuest],
  );

  const refreshEmbed = useCallback(async () => {
    if (!embed?.dashboardId) return;
    await openDashboard(embed.dashboardId, embed.title);
  }, [embed?.dashboardId, embed?.title, openDashboard]);

  const onChatResponse = useCallback(
    (resp: BiChatResponse) => {
      const guest = resp.analytics?.guest;
      if (guest) {
        const dash = dashboardsQ.data?.dashboards?.find((d) => Number(d.id) === Number(guest.dashboard_id));
        setEmbedFromGuest(guest, dash?.title);
        setEmbedNonce((n) => n + 1);
      } else if (resp.analytics?.dashboard_id) {
        const id = Number(resp.analytics.dashboard_id);
        const dash = dashboardsQ.data?.dashboards?.find((d) => Number(d.id) === id);
        void openDashboard(id, dash?.title);
      }
      if (
        resp.intent === 'analytics' ||
        resp.intent === 'superset' ||
        resp.intent === 'pin' ||
        resp.intent === 'pin_dashboard' ||
        resp.intent === 'dashboard'
      ) {
        qc.invalidateQueries({ queryKey: ['bi-analytics-dashboards'] });
        qc.invalidateQueries({ queryKey: ['bi-analytics-charts'] });
        qc.invalidateQueries({ queryKey: ['bi-analytics-datasets'] });
        qc.invalidateQueries({ queryKey: ['bi-analytics-dashboard-charts'] });
        // Force embed remount so newly pinned charts appear without manual refresh.
        if (resp.intent === 'pin' || resp.intent === 'pin_dashboard' || resp.analytics?.guest) {
          setEmbedNonce((n) => n + 1);
        }
      }
    },
    [dashboardsQ.data?.dashboards, openDashboard, qc, setEmbedFromGuest],
  );

  useEffect(() => registerOnResponse(onChatResponse), [registerOnResponse, onChatResponse]);

  useEffect(() => {
    setDashboardId(embed?.dashboardId ? String(embed.dashboardId) : undefined);
    return () => setDashboardId(undefined);
  }, [embed?.dashboardId, setDashboardId]);

  useEffect(() => {
    if (!anomalyFromUrl) return;
    openChat({ prompt: t('bi.anomaly.askPrompt', { key: anomalyFromUrl }) });
  }, [anomalyFromUrl, openChat]);

  const toggleBrowserFullscreen = async () => {
    const el = viewerRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      await el.requestFullscreen?.();
      setBrowserFullscreen(true);
    } else {
      await document.exitFullscreen?.();
      setBrowserFullscreen(false);
    }
  };

  useEffect(() => {
    const onFs = () => setBrowserFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener('fullscreenchange', onFs);
    return () => document.removeEventListener('fullscreenchange', onFs);
  }, []);

  useEffect(() => {
    if (
      !anomalyFromUrl &&
      !artifactFromUrl &&
      !dashboardFromUrl &&
      searchParams.get('comments') !== '1'
    ) {
      return;
    }
    const next = new URLSearchParams(searchParams);
    next.delete('anomaly');
    next.delete('artifact');
    next.delete('comments');
    next.delete('dashboard');
    setSearchParams(next, { replace: true });
  }, [anomalyFromUrl, artifactFromUrl, dashboardFromUrl, searchParams, setSearchParams]);

  useEffect(() => {
    if (!artifactFromUrl || !runnerReady) return;
    let cancelled = false;
    void api.bi.artifacts
      .get(config, artifactFromUrl)
      .then((art) => {
        if (cancelled) return;
        const md = String((art as { answer_md?: string }).answer_md || art.id || artifactFromUrl);
        setArtifactBanner(md.slice(0, 280));
        openChat();
      })
      .catch(() => {
        if (!cancelled) setArtifactBanner(artifactFromUrl);
      });
    return () => {
      cancelled = true;
    };
  }, [artifactFromUrl, config, runnerReady, openChat]);

  useEffect(() => {
    if (!anomalyFromUrl || !runnerReady) return;
    let cancelled = false;
    void api.bi.anomalies
      .get(config, anomalyFromUrl)
      .then((a) => {
        if (cancelled) return;
        const title = String((a as { title?: string; metric_id?: string }).title || anomalyFromUrl);
        setAnomalyBanner(title);
      })
      .catch(() => {
        /* banner already set from key */
      });
    return () => {
      cancelled = true;
    };
  }, [anomalyFromUrl, config, runnerReady]);

  const enabled = statusQ.data?.enabled === true;
  const healthOk = statusQ.data?.health?.ok;
  const statusError =
    statusQ.isError && statusQ.error instanceof Error
      ? localizeUserMessage(statusQ.error.message)
      : statusQ.isError
        ? t('bi.analytics.statusError')
        : null;
  const dashboards = dashboardsQ.data?.dashboards ?? [];

  useEffect(() => {
    if (!dashboardFromUrl || !enabled) return;
    const id = Number(dashboardFromUrl);
    if (!Number.isFinite(id) || id <= 0) return;
    const dash = dashboards.find((d) => Number(d.id) === id);
    void openDashboard(id, dash?.title);
  }, [dashboardFromUrl, enabled, dashboards, openDashboard]);

  useEffect(() => {
    if (embed || !enabled || dashboardsQ.isLoading || dashboardFromUrl) return;
    const first = dashboards[0];
    if (!first?.id) return;
    void openDashboard(Number(first.id), first.title);
  }, [embed, enabled, dashboards, dashboardsQ.isLoading, openDashboard, dashboardFromUrl]);

  return (
    <div className="bi-fluent-shell flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-[#F5F5F5]">
      {!hideBriefing && (
        <div className="shrink-0 space-y-1.5 border-b border-[#E1DFDD] bg-[#F5F5F5] px-2 py-1.5 sm:px-3 sm:py-2">
          <BiMorningBriefing
            config={config}
            boardId="default"
            compact
            defaultOpen={false}
            light
            onAskInChat={(prompt) => {
              openChat({ prompt: prompt || undefined });
            }}
          />
          <BiNarrativeStrip
            config={config}
            dashboardId="default"
            defaultOpen={false}
            onDriverAsk={(prompt) => {
              openChat({ prompt });
            }}
          />
        </div>
      )}

      <header className="bi-fluent-card flex shrink-0 items-center gap-1.5 border-b border-[#E1DFDD] bg-white/95 px-2 py-2 shadow-sm backdrop-blur-md sm:gap-3 sm:px-4">
        <button
          type="button"
          className="min-h-10 min-w-10 rounded-xl p-2 text-slate-600 transition hover:bg-slate-100 lg:hidden"
          onClick={openMenu}
          aria-label={t('nav.openMenu')}
        >
          <Menu className="h-4 w-4" />
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Sparkles className="hidden h-4 w-4 shrink-0 text-violet-600 sm:block" />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">{t('bi.analytics.title')}</p>
            <p className="truncate text-[11px] text-slate-500">
              {embed?.title || t('bi.analytics.subtitle')}
            </p>
          </div>
        </div>

        <div className="relative min-w-0">
          <button
            type="button"
            className="inline-flex max-w-[9.5rem] items-center gap-1.5 rounded-xl border border-[#E1DFDD] bg-white/90 px-2 py-2 text-xs font-medium text-slate-700 shadow-sm transition hover:border-[#118DFF]/40 hover:bg-[#118DFF]/5 sm:max-w-xs sm:px-3 sm:py-1.5 sm:text-sm"
            onClick={() => setPickerOpen((v) => !v)}
            aria-expanded={pickerOpen}
          >
            <LayoutDashboard className="h-3.5 w-3.5 shrink-0 text-violet-600" />
            <span className="truncate">{embed?.title || t('bi.analytics.selectDashboard')}</span>
            {dashboards.length > 1 && (
              <span className="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                {dashboards.length}
              </span>
            )}
            <ChevronDown className={clsx('h-3.5 w-3.5 shrink-0 transition', pickerOpen && 'rotate-180')} />
          </button>

          {pickerOpen && (
            <>
              <button type="button" className="fixed inset-0 z-30" aria-label={t('bi.analytics.closeChat')} onClick={() => setPickerOpen(false)} />
              <div className="absolute right-0 z-40 mt-2 w-[min(calc(100vw-2rem),16rem)] overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-xl sm:w-64">
                <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
                  <span className="text-xs font-semibold text-slate-700">{t('bi.analytics.dashboards')}</span>
                  <button
                    type="button"
                    className="rounded p-1 text-slate-500 hover:bg-slate-100"
                    onClick={() => qc.invalidateQueries({ queryKey: ['bi-analytics-dashboards'] })}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                </div>
                <ul className="max-h-56 overflow-y-auto py-1 text-sm">
                  {dashboards.map((d) => (
                    <li key={d.id}>
                      <button
                        type="button"
                        className={clsx(
                          'w-full px-3 py-2 text-left transition hover:bg-violet-50',
                          embed?.dashboardId === Number(d.id) && 'bg-violet-50/80 font-medium text-violet-900',
                        )}
                        onClick={() => openDashboard(Number(d.id), d.title)}
                      >
                        <span className="line-clamp-1">{d.title}</span>
                        <span className="mt-0.5 flex items-center gap-2 text-[10px] text-slate-400">
                          <span>#{d.id}</span>
                          <span>
                            {Number(d.chart_count || 0) > 0
                              ? t('bi.analytics.chartCount', { count: String(d.chart_count) })
                              : t('bi.analytics.emptyBoard')}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                  {!dashboards.length && (
                    <li className="px-3 py-4 text-center text-xs text-slate-500">{t('bi.analytics.emptyDashboards')}</li>
                  )}
                </ul>
              </div>
            </>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            className={clsx(
              'min-h-10 min-w-10 rounded-xl p-2 transition hover:bg-slate-100',
              sidePanel === 'widgets' ? 'bg-violet-50 text-violet-700' : 'text-slate-600',
            )}
            onClick={() => setSidePanel((p) => (p === 'widgets' ? 'none' : 'widgets'))}
            title={t('bi.analytics.manageWidgets')}
            aria-label={t('bi.analytics.manageWidgets')}
            disabled={!embed?.dashboardId}
          >
            <ListOrdered className="h-4 w-4" />
          </button>
          <button
            type="button"
            className={clsx(
              'min-h-10 min-w-10 rounded-xl p-2 transition hover:bg-slate-100',
              sidePanel === 'comments' ? 'bg-violet-50 text-violet-700' : 'text-slate-600',
            )}
            onClick={() => setSidePanel((p) => (p === 'comments' ? 'none' : 'comments'))}
            title={t('bi.comments.title')}
            aria-label={t('bi.comments.title')}
          >
            <MessageCircle className="h-4 w-4" />
          </button>
          {metricFromUrl ? (
            <button
              type="button"
              className="min-h-10 min-w-10 rounded-xl p-2 text-slate-600 transition hover:bg-slate-100"
              onClick={() => openChat()}
              title={t('bi.lineage.title')}
              aria-label={t('bi.lineage.title')}
            >
              <GitBranch className="h-4 w-4" />
            </button>
          ) : null}
          <button
            type="button"
            className={clsx(
              'relative min-h-10 min-w-10 rounded-xl p-2 transition hover:bg-slate-100',
              chatOpen ? 'bg-violet-50 text-violet-700' : 'text-slate-600',
            )}
            onClick={() => openChat()}
            title={t('bi.analytics.openChat')}
            aria-label={t('bi.analytics.openChat')}
          >
            <MessageSquare className="h-4 w-4" />
            {!chatOpen ? (
              <span className="bi-chat-icon-badge" aria-hidden>
                <Sparkles className="h-2.5 w-2.5" />
              </span>
            ) : null}
          </button>
          <button
            type="button"
            className="hidden min-h-10 min-w-10 rounded-xl p-2 text-slate-600 transition hover:bg-slate-100 sm:inline-flex"
            onClick={toggleBrowserFullscreen}
            title={browserFullscreen ? t('bi.analytics.exitFullscreen') : t('bi.analytics.fullscreen')}
          >
            {browserFullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
          </button>
        </div>
      </header>

      {statusError && (
        <div className="shrink-0 border-b border-rose-200 bg-rose-50 px-4 py-2 text-xs text-rose-800 sm:text-sm">
          {statusError}
        </div>
      )}
      {!statusError && statusQ.isFetched && statusQ.data?.enabled === false && (
        <div className="shrink-0 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900 sm:text-sm">
          {t('bi.analytics.notConfigured')}
        </div>
      )}
      {enabled && healthOk === false && (
        <div className="shrink-0 border-b border-rose-200 bg-rose-50 px-4 py-2 text-xs text-rose-800 sm:text-sm">
          {t('bi.analytics.unhealthy')}: {statusQ.data?.health?.message}
        </div>
      )}
      {openError && (
        <div className="shrink-0 border-b border-rose-200 bg-rose-50 px-4 py-2 text-xs text-rose-800 sm:text-sm">
          {t('bi.analytics.embedError')}: {openError}
        </div>
      )}
      {anomalyBanner && (
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-950 sm:text-sm">
          <span>
            {t('bi.anomaly.openBanner')}: {anomalyBanner}
          </span>
          <button type="button" className="text-amber-800 underline" onClick={() => setAnomalyBanner(null)}>
            {t('common.close')}
          </button>
        </div>
      )}
      {artifactBanner && (
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-sky-200 bg-sky-50 px-4 py-2 text-xs text-sky-950 sm:text-sm">
          <span className="line-clamp-2">
            {t('bi.artifact.openBanner')}: {artifactBanner}
          </span>
          <button type="button" className="shrink-0 text-sky-800 underline" onClick={() => setArtifactBanner(null)}>
            {t('common.close')}
          </button>
        </div>
      )}

      <div
        ref={viewerRef}
        className={clsx(
          'bi-fluent-canvas bi-analytics-viewer relative flex min-h-0 flex-1 flex-col overflow-hidden',
          browserFullscreen && 'bg-slate-950',
        )}
      >
        <div className="flex min-h-0 flex-1">
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
            {embed ? (
              <BiSupersetEmbed
                key={`${embed.dashboardId}-${embed.embedUuid}-${embedNonce}`}
                config={config}
                embedUuid={embed.embedUuid}
                dashboardId={embed.dashboardId}
                analyticsUrl={embed.analyticsUrl}
                guestToken={embed.token}
                className="min-h-0 flex-1"
              />
            ) : (
              <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
                <div className="bi-pbi-tile bi-pbi-tile--3d max-w-sm p-8 text-center">
                  <div className="bi-pbi-tile-glow" aria-hidden />
                  <div className="bi-pbi-tile-accent" data-visual="card" aria-hidden />
                  <div className="relative z-[1]">
                  <Sparkles className="mx-auto mb-3 h-10 w-10 text-[#118DFF]/80" />
                  <p className="text-sm text-[#605E5C]">
                    {dashboardsQ.isLoading || statusQ.isLoading
                      ? t('bi.analytics.loading')
                      : t('bi.analytics.emptyEmbed')}
                  </p>
                  <button
                    type="button"
                    className="mt-4 inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md transition hover:brightness-105"
                    onClick={() => openChat()}
                  >
                    <MessageSquare className="h-4 w-4" />
                    {t('bi.analytics.openChat')}
                  </button>
                  </div>
                </div>
              </div>
            )}
          </div>
          {sidePanel === 'comments' && (
            <div className="hidden w-72 shrink-0 border-l border-slate-200 bg-white p-2 sm:block">
              <BiCommentsDrawer
                config={config}
                targetType="dashboard"
                targetId={embed ? String(embed.dashboardId) : 'default'}
              />
            </div>
          )}
          {sidePanel === 'widgets' && embed?.dashboardId ? (
            <div className="hidden w-80 shrink-0 border-l border-slate-200 bg-white sm:block">
              <BiDashboardWidgetsPanel
                config={config}
                dashboardId={embed.dashboardId}
                onClose={() => setSidePanel('none')}
                onChanged={() => void refreshEmbed()}
              />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
