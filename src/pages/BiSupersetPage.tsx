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
import BiLineageDrawer from '@/components/bi/BiLineageDrawer';
import BiMorningBriefing from '@/components/bi/BiMorningBriefing';
import BiNarrativeStrip from '@/components/bi/BiNarrativeStrip';
import BiSourceAnalyticsCanvas from '@/components/bi/BiSourceAnalyticsCanvas';
import BiSourceSwitcher from '@/components/bi/BiSourceSwitcher';
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

/** One Superset board per BI datasource (ERP / Sigorta / …). */
function sourceBoardTitle(sourceId: string, label?: string): string {
  const name = (label || sourceId || 'default').trim();
  return `NanobaseAI · ${name}`;
}

function findSourceBoard(
  dashboards: Array<{ id: number; title?: string }>,
  sourceId: string,
  label?: string,
) {
  const needles = [
    `nanobaseai · ${(label || '').toLowerCase()}`,
    `nanobaseai · ${sourceId.toLowerCase()}`,
    sourceId.toLowerCase(),
  ].filter((n) => n.length > 2);
  return dashboards.find((d) => {
    const title = String(d.title || '').toLowerCase();
    return needles.some((n) => title.includes(n));
  });
}

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
  const [sidePanel, setSidePanel] = useState<'comments' | 'widgets' | 'none'>(() => {
    if (searchParams.get('comments') === '1') return 'comments';
    if (searchParams.get('widgets') === '1') return 'widgets';
    return 'none';
  });
  const [lineageOpen, setLineageOpen] = useState(() => Boolean(searchParams.get('metric')));
  const [artifactBanner, setArtifactBanner] = useState<string | null>(null);
  const [anomalyBanner, setAnomalyBanner] = useState<string | null>(
    () => (anomalyFromUrl ? anomalyFromUrl : null),
  );
  const narrow = useMediaQuery('(max-width: 639px)');
  const hideBriefing = narrow && chatOpen;
  const runnerReady = isRunnerConfigured(config);

  const sourcesQ = useQuery({
    queryKey: ['bi-sources', config],
    queryFn: () => api.bi.sources.list(config),
    enabled: runnerReady,
    staleTime: 15_000,
  });
  const activeSourceId = sourcesQ.data?.active_id || '';
  const activeSourceLabel =
    sourcesQ.data?.sources?.find((s) => s.id === activeSourceId)?.label || activeSourceId;

  const statusQ = useQuery({
    queryKey: ['bi-analytics-status'],
    queryFn: () => api.bi.analytics.status(config),
    enabled: runnerReady,
    staleTime: 90_000,
  });

  const dashboardsQ = useQuery({
    queryKey: ['bi-analytics-dashboards', activeSourceId],
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
        qc.invalidateQueries({ queryKey: ['bi-analytics-source-widgets'] });
        // Force embed remount so newly pinned charts appear without manual refresh.
        if (resp.intent === 'pin' || resp.intent === 'pin_dashboard' || resp.analytics?.guest) {
          if (embed?.dashboardId) void refreshEmbed();
        }
      }
    },
    [dashboardsQ.data?.dashboards, embed?.dashboardId, openDashboard, qc, refreshEmbed, setEmbedFromGuest],
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
  const sourceDashboards = activeSourceId
    ? dashboards.filter((d) => findSourceBoard([d], activeSourceId, activeSourceLabel))
    : dashboards;
  const pickerDashboards = sourceDashboards.length ? sourceDashboards : dashboards;

  useEffect(() => {
    if (!dashboardFromUrl || !enabled) return;
    const id = Number(dashboardFromUrl);
    if (!Number.isFinite(id) || id <= 0) return;
    const dash = dashboards.find((d) => Number(d.id) === id);
    void openDashboard(id, dash?.title);
  }, [dashboardFromUrl, enabled, dashboards, openDashboard]);

  // Ensure a Superset board exists for the active datasource and open it.
  useEffect(() => {
    if (!enabled || !activeSourceId || dashboardFromUrl || dashboardsQ.isLoading) return;
    let cancelled = false;
    const wantedTitle = sourceBoardTitle(activeSourceId, activeSourceLabel);
    const existing = findSourceBoard(dashboards, activeSourceId, activeSourceLabel);

    const run = async () => {
      try {
        if (existing?.id) {
          if (embed?.dashboardId === Number(existing.id)) return;
          await openDashboard(Number(existing.id), existing.title || wantedTitle);
          return;
        }
        const created = await api.bi.analytics.createDashboard(config, { title: wantedTitle });
        if (cancelled) return;
        await qc.invalidateQueries({ queryKey: ['bi-analytics-dashboards'] });
        const guest = created.guest;
        if (
          guest?.token &&
          guest.dashboard_id != null &&
          guest.embed_uuid &&
          guest.analytics_url
        ) {
          setEmbedFromGuest(
            {
              token: guest.token,
              dashboard_id: Number(guest.dashboard_id),
              embed_uuid: String(guest.embed_uuid),
              analytics_url: String(guest.analytics_url),
            },
            created.title || wantedTitle,
          );
        } else if (created.id) {
          await openDashboard(Number(created.id), created.title || wantedTitle);
        }
      } catch (exc) {
        if (!cancelled) {
          setOpenError(exc instanceof Error ? exc.message : String(exc));
        }
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [
    enabled,
    activeSourceId,
    activeSourceLabel,
    dashboards,
    dashboardsQ.isLoading,
    dashboardFromUrl,
    embed?.dashboardId,
    openDashboard,
    config,
    qc,
    setEmbedFromGuest,
  ]);

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
        <div className="flex min-w-0 flex-1 items-center gap-2 overflow-hidden">
          <Sparkles className="hidden h-4 w-4 shrink-0 text-violet-600 sm:block" />
          <div className="min-w-0 max-w-[10rem] sm:max-w-[14rem] lg:max-w-none">
            <p className="truncate text-sm font-semibold text-slate-900">{t('bi.analytics.title')}</p>
            <p className="truncate text-[11px] text-slate-500">
              {embed?.title || t('bi.analytics.subtitle')}
            </p>
          </div>
          <BiSourceSwitcher config={config} compact className="hidden min-w-0 md:flex" />
        </div>

        <div className="relative min-w-[12rem] max-w-[min(100%,22rem)] shrink-0 sm:min-w-[16rem] sm:max-w-md md:max-w-lg">
          <button
            type="button"
            className="inline-flex w-full max-w-full items-center gap-1.5 rounded-xl border border-[#E1DFDD] bg-white/90 px-2.5 py-2 text-xs font-medium text-slate-700 shadow-sm transition hover:border-[#118DFF]/40 hover:bg-[#118DFF]/5 sm:px-3 sm:py-1.5 sm:text-sm"
            onClick={() => setPickerOpen((v) => !v)}
            aria-expanded={pickerOpen}
            title={embed?.title || t('bi.analytics.selectDashboard')}
          >
            <LayoutDashboard className="h-3.5 w-3.5 shrink-0 text-violet-600" />
            <span className="min-w-0 flex-1 truncate text-left">
              {embed?.title || t('bi.analytics.selectDashboard')}
            </span>
            {pickerDashboards.length > 0 && (
              <span className="shrink-0 rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                {pickerDashboards.length}
              </span>
            )}
            <ChevronDown className={clsx('h-3.5 w-3.5 shrink-0 transition', pickerOpen && 'rotate-180')} />
          </button>

          {pickerOpen && (
            <>
              <button type="button" className="fixed inset-0 z-30" aria-label={t('bi.analytics.closeChat')} onClick={() => setPickerOpen(false)} />
              <div className="absolute right-0 z-40 mt-2 w-[min(calc(100vw-1.5rem),24rem)] overflow-hidden rounded-xl border border-slate-200/90 bg-white shadow-xl sm:w-[min(100vw-2rem,28rem)]">
                <div className="flex items-center justify-between gap-2 border-b border-slate-100 px-3 py-2">
                  <span className="min-w-0 truncate text-xs font-semibold text-slate-700">
                    {activeSourceLabel || t('bi.analytics.dashboards')}
                  </span>
                  <button
                    type="button"
                    className="shrink-0 rounded p-1 text-slate-500 hover:bg-slate-100"
                    onClick={() => qc.invalidateQueries({ queryKey: ['bi-analytics-dashboards'] })}
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                </div>
                <ul className="max-h-72 overflow-y-auto py-1 text-sm">
                  {pickerDashboards.map((d) => (
                    <li key={d.id}>
                      <button
                        type="button"
                        className={clsx(
                          'w-full px-3 py-2.5 text-left transition hover:bg-violet-50',
                          embed?.dashboardId === Number(d.id) && 'bg-violet-50/80 font-medium text-violet-900',
                        )}
                        onClick={() => openDashboard(Number(d.id), d.title)}
                        title={d.title}
                      >
                        <span className="block truncate">{d.title || `Dashboard ${d.id}`}</span>
                        <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-slate-400">
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
                  {!pickerDashboards.length && (
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
              className={clsx(
                'min-h-10 min-w-10 rounded-xl p-2 transition hover:bg-slate-100',
                lineageOpen ? 'bg-violet-50 text-violet-700' : 'text-slate-600',
              )}
              onClick={() => setLineageOpen((v) => !v)}
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
            {/* Primary surface: filled KPIs/charts from the selected database */}
            {activeSourceId ? (
              <BiSourceAnalyticsCanvas
                config={config}
                datasourceId={activeSourceId}
                sourceLabel={activeSourceLabel}
                className="min-h-0 flex-1"
              />
            ) : null}
            {!activeSourceId ? (
              <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
                <div className="bi-pbi-tile bi-pbi-tile--3d bi-pbi-tile--vivid bi-pbi-tile--pro max-w-sm p-8 text-center" data-accent={0}>
                  <div className="bi-pbi-tile-depth" aria-hidden />
                  <div className="bi-pbi-tile-rim bi-pbi-tile-rim--x" aria-hidden />
                  <div className="bi-pbi-tile-rim bi-pbi-tile-rim--y" aria-hidden />
                  <div className="bi-pbi-tile-bevel" aria-hidden />
                  <div className="bi-pbi-tile-glow" aria-hidden />
                  <div className="bi-pbi-tile-shine" aria-hidden />
                  <div className="bi-pbi-tile-specular" aria-hidden />
                  <div className="bi-pbi-tile-face relative z-[1]">
                    <Sparkles className="mx-auto mb-3 h-10 w-10 text-[#118DFF]/80" />
                    <p className="text-sm text-[#605E5C]">
                      {sourcesQ.isLoading || statusQ.isLoading
                        ? t('bi.analytics.loading')
                        : t('bi.analytics.emptyEmbed')}
                    </p>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
          {sidePanel === 'comments' && !narrow && (
            <div className="w-72 shrink-0 border-l border-slate-200 bg-white p-2">
              <BiCommentsDrawer
                config={config}
                targetType="dashboard"
                targetId={embed ? String(embed.dashboardId) : 'default'}
              />
            </div>
          )}
          {sidePanel === 'widgets' && !narrow ? (
            <div className="w-80 shrink-0 border-l border-slate-200 bg-white">
              <BiDashboardWidgetsPanel
                config={config}
                dashboardId={embed?.dashboardId ?? 0}
                onClose={() => setSidePanel('none')}
                onChanged={() => void refreshEmbed()}
              />
            </div>
          ) : null}
          {lineageOpen && metricFromUrl && !narrow ? (
            <div className="w-80 shrink-0 overflow-y-auto border-l border-slate-200 bg-white p-2">
              <BiLineageDrawer
                config={config}
                metricId={metricFromUrl}
                onClose={() => setLineageOpen(false)}
              />
            </div>
          ) : null}
        </div>
        {narrow && (sidePanel !== 'none' || (lineageOpen && metricFromUrl)) ? (
          <div className="absolute inset-0 z-30 flex flex-col bg-black/40" role="dialog" aria-modal>
            <button
              type="button"
              className="min-h-[20%] flex-1 cursor-default"
              aria-label={t('common.close')}
              onClick={() => {
                setSidePanel('none');
                setLineageOpen(false);
              }}
            />
            <div className="max-h-[80%] overflow-y-auto rounded-t-2xl bg-white p-3 shadow-2xl">
              <div className="mb-2 flex justify-end">
                <button
                  type="button"
                  className="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100"
                  onClick={() => {
                    setSidePanel('none');
                    setLineageOpen(false);
                  }}
                >
                  {t('common.close')}
                </button>
              </div>
              {sidePanel === 'comments' ? (
                <BiCommentsDrawer
                  config={config}
                  targetType="dashboard"
                  targetId={embed ? String(embed.dashboardId) : 'default'}
                />
              ) : null}
              {sidePanel === 'widgets' ? (
                <BiDashboardWidgetsPanel
                  config={config}
                  dashboardId={embed?.dashboardId ?? 0}
                  onClose={() => setSidePanel('none')}
                  onChanged={() => void refreshEmbed()}
                />
              ) : null}
              {lineageOpen && metricFromUrl ? (
                <BiLineageDrawer
                  config={config}
                  metricId={metricFromUrl}
                  onClose={() => setLineageOpen(false)}
                />
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
