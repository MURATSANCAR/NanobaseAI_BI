import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { Database, GitBranch, Network, RefreshCw, Search, Table2 } from 'lucide-react';
import ApiErrorBanner from '@/components/ApiErrorBanner';
import { PageShell } from '@/components/PageShell';
import BiDomainPackWizard from '@/components/bi/BiDomainPackWizard';
import BiRecentOperations from '@/components/bi/BiRecentOperations';
import BiSchemaEmptyGate from '@/components/bi/BiSchemaEmptyGate';
import BiSchemaGraph from '@/components/bi/BiSchemaGraph';
import BiSchemaRelationsPanel from '@/components/bi/BiSchemaRelationsPanel';
import BiSchemaTablesPanel from '@/components/bi/BiSchemaTablesPanel';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import {
  isSchemaCacheMissingError,
  parseSchemaViewParam,
  buildGraphPayloadFromSchema,
  type SchemaView,
} from '@/utils/biSchemaRelations';
import { t } from '@/i18n';
import { getFeatureFlags } from '@/config/environment';

const VIEW_META: Array<{
  id: SchemaView;
  icon: typeof GitBranch;
  titleKey: string;
  descKey: string;
}> = [
  {
    id: 'relations',
    icon: GitBranch,
    titleKey: 'bi.schemaViewRelations',
    descKey: 'bi.schemaViewRelationsDesc',
  },
  {
    id: 'graph',
    icon: Network,
    titleKey: 'bi.schemaViewGraph',
    descKey: 'bi.schemaViewGraphDesc',
  },
  {
    id: 'tables',
    icon: Table2,
    titleKey: 'bi.schemaViewTables',
    descKey: 'bi.schemaViewTablesDesc',
  },
];

export default function BiSchemaPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const { openChat } = useBiChatDock();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [view, setView] = useState<SchemaView>(() => parseSchemaViewParam(searchParams.get('view')));
  const showPack = searchParams.get('pack') === '1';
  const panelRef = useRef<HTMLDivElement>(null);
  const packRef = useRef<HTMLDivElement>(null);
  const flags = getFeatureFlags();

  const sourcesQ = useQuery({
    queryKey: ['bi-sources', config],
    queryFn: () => api.bi.sources.list(config),
    enabled: isRunnerConfigured(config),
    staleTime: 30_000,
  });
  const activeSourceId = sourcesQ.data?.active_id || undefined;

  const schema = useQuery({
    queryKey: ['bi-schema', activeSourceId],
    queryFn: () => api.bi.schema(config, activeSourceId),
    enabled: isRunnerConfigured(config) && flags.enableSchemaExplorer,
    retry: false,
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });

  const graph = useQuery({
    queryKey: ['bi-schema-graph', activeSourceId],
    queryFn: () => api.bi.schemaGraph(config, activeSourceId),
    enabled: isRunnerConfigured(config) && Boolean(schema.data?.tables?.length),
    staleTime: 60_000,
    retry: 1,
  });

  const refresh = useMutation({
    mutationFn: () => api.bi.refreshSchema(config, activeSourceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-schema'] });
      void qc.invalidateQueries({ queryKey: ['bi-schema-graph'] });
      void qc.invalidateQueries({ queryKey: ['bi-audit-recent'] });
      void qc.invalidateQueries({ queryKey: ['bi-status'] });
    },
  });

  useEffect(() => {
    const next = parseSchemaViewParam(searchParams.get('view'));
    setView((current) => (current === next ? current : next));
  }, [searchParams]);

  useEffect(() => {
    if (!showPack) return;
    window.requestAnimationFrame(() => {
      packRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }, [showPack]);

  const dismissPack = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('pack');
    setSearchParams(next, { replace: true });
  };

  const setSchemaView = (next: SchemaView) => {
    setView(next);
    const params = new URLSearchParams(searchParams);
    if (next === 'relations') params.delete('view');
    else params.set('view', next);
    // Switching schema views exits pack step so URL stays coherent.
    params.delete('pack');
    setSearchParams(params, { replace: true });
    window.requestAnimationFrame(() => {
      panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  };

  const graphPayload = useMemo(() => {
    if (graph.data?.nodes?.length) return graph.data;
    if (schema.data) return buildGraphPayloadFromSchema(schema.data);
    return null;
  }, [graph.data, schema.data]);

  const tables = useMemo(() => {
    const all = schema.data?.tables ?? [];
    const q = search.trim().toLowerCase();
    if (!q) return all;
    return all.filter(
      (tbl) =>
        tbl.full_name.toLowerCase().includes(q) ||
        (tbl.columns ?? []).some((c) => c.name.toLowerCase().includes(q)),
    );
  }, [schema.data, search]);

  const totalColumns = useMemo(
    () => (schema.data?.tables ?? []).reduce((sum, tbl) => sum + (tbl.columns?.length ?? 0), 0),
    [schema.data],
  );

  const hasSchema = Boolean(schema.data?.tables?.length);
  const schemaMissing = schema.isError && isSchemaCacheMissingError(schema.error);
  const schemaLoadFailed = schema.isError && !schemaMissing;
  const showEmpty = !schema.isLoading && !hasSchema && !schemaLoadFailed;
  const graphNodes = graphPayload?.nodes ?? [];
  const graphEdges = graphPayload?.edges ?? [];

  const onTableClick = (table: string) => {
    openChat({ prompt: t('bi.askAboutTable', { table }) });
  };

  const packWizard = showPack ? (
    <div ref={packRef} className="bi-schema-pack-focus scroll-mt-4">
      {hasSchema ? (
        <BiDomainPackWizard
          config={config}
          onApplied={() => {
            dismissPack();
            void qc.invalidateQueries({ queryKey: ['bi-schema'] });
            openChat();
          }}
          onSkip={dismissPack}
        />
      ) : (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 shadow-sm">
          <p className="font-medium">{t('bi.pack.needSchemaTitle')}</p>
          <p className="mt-1 text-amber-800/90">{t('bi.pack.needSchemaBody')}</p>
          <button
            type="button"
            className="btn-primary mt-3 inline-flex items-center gap-2"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            <RefreshCw className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
            {t('bi.refreshSchema')}
          </button>
        </div>
      )}
    </div>
  ) : null;

  return (
    <PageShell pageId="biSchema" titleKey="bi.schemaTitle" subtitleKey="bi.schemaSubtitle" maxWidth="max-w-[1600px]">
      <div className="bi-schema-stage">
        <ApiErrorBanner error={schemaLoadFailed ? (schema.error as Error) : null} />
        <ApiErrorBanner error={graph.isError ? (graph.error as Error) : null} />
        <ApiErrorBanner error={refresh.isError ? (refresh.error as Error) : null} />

        <div className="bi-schema-toolbar">
          <div className="bi-schema-search">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              placeholder={t('bi.searchSchema')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              disabled={!hasSchema}
            />
          </div>
          <button
            type="button"
            className="btn-primary flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
            disabled={refresh.isPending}
            onClick={() => refresh.mutate()}
          >
            <RefreshCw className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
            {t('bi.refreshSchema')}
          </button>
        </div>

        {refresh.isSuccess ? (
          <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-800">
            {t('bi.schemaRefreshed')}
          </p>
        ) : null}

        {packWizard}

        {schema.isLoading ? (
          <div className="bi-schema-panel flex items-center justify-center gap-2 p-12 text-sm text-slate-500">
            <Table2 className="h-5 w-5 animate-pulse text-violet-500" />
            {t('common.loading')}
          </div>
        ) : null}

        {showEmpty && !showPack ? (
          <BiSchemaEmptyGate ctaTo="/bi/sources">
            <button
              type="button"
              className="btn-primary mt-3 inline-flex items-center gap-2"
              disabled={refresh.isPending}
              onClick={() => refresh.mutate()}
            >
              <RefreshCw className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
              {t('bi.refreshSchema')}
            </button>
          </BiSchemaEmptyGate>
        ) : null}

        {hasSchema && search.trim() && tables.length === 0 ? (
          <div className="bi-schema-panel p-6 text-center text-sm text-slate-500">
            {t('bi.schemaSearchEmpty', { query: search.trim() })}
          </div>
        ) : null}

        {hasSchema ? (
          <>
            {!showPack ? (
              <div className="bi-schema-view-tabs" role="tablist" aria-label={t('bi.schemaViewTabs')}>
                {VIEW_META.map(({ id, icon: Icon, titleKey, descKey }) => (
                  <button
                    key={id}
                    type="button"
                    role="tab"
                    aria-selected={view === id}
                    className={clsx('bi-schema-view-tab', view === id && 'is-active')}
                    onClick={() => setSchemaView(id)}
                  >
                    <span className="bi-schema-view-tab-title">
                      <Icon className="h-4 w-4 shrink-0 sm:h-5 sm:w-5" />
                      {t(titleKey)}
                    </span>
                    <span className="bi-schema-view-tab-desc">{t(descKey)}</span>
                  </button>
                ))}
              </div>
            ) : null}

            {!showPack ? (
              <div ref={panelRef} className="bi-schema-view-panel">
                {view === 'relations' ? (
                  <BiSchemaRelationsPanel
                    nodes={graphNodes}
                    edges={graphEdges}
                    highlight={search}
                    onTableClick={onTableClick}
                  />
                ) : null}

                {view === 'graph' ? (
                  graph.isLoading && !graphNodes.length ? (
                    <div className="bi-schema-panel flex items-center justify-center gap-2 p-12 text-sm text-slate-500">
                      <Network className="h-5 w-5 animate-pulse text-indigo-500" />
                      {t('common.loading')}
                    </div>
                  ) : (
                    <BiSchemaGraph
                      nodes={graphNodes}
                      edges={graphEdges}
                      highlight={search}
                      onTableClick={onTableClick}
                    />
                  )
                ) : null}

                {view === 'tables' ? (
                  tables.length ? (
                    <BiSchemaTablesPanel tables={tables} />
                  ) : (
                    <div className="bi-schema-panel p-8 text-center text-sm text-slate-500">{t('common.noData')}</div>
                  )
                ) : null}
              </div>
            ) : null}

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="bi-schema-stat" data-accent="0">
                <span className="bi-pbi-tile-glow" aria-hidden />
                <span className="bi-schema-stat-value">{schema.data?.table_count ?? tables.length}</span>
                <span className="bi-schema-stat-label">{t('bi.tables')}</span>
              </div>
              <div className="bi-schema-stat" data-accent="1">
                <span className="bi-pbi-tile-glow" aria-hidden />
                <span className="bi-schema-stat-value">{totalColumns}</span>
                <span className="bi-schema-stat-label">{t('bi.columnCount')}</span>
              </div>
              <div className="bi-schema-stat" data-accent="3">
                <span className="bi-pbi-tile-glow" aria-hidden />
                <span className="bi-schema-stat-value">
                  {graph.data?.stats?.relations ?? graphEdges.length}
                </span>
                <span className="bi-schema-stat-label">{t('bi.schemaGraphRelations')}</span>
              </div>
            </div>

            <p className="flex items-center gap-2 text-xs text-slate-500">
              <Database className="h-3.5 w-3.5 shrink-0" />
              {t('bi.schemaAutoRefreshHint')}
              {schema.data?.introspected_at ? (
                <span className="text-slate-400">· {schema.data.introspected_at.slice(0, 19)}</span>
              ) : null}
            </p>

            {!showPack ? <BiRecentOperations limit={10} /> : null}
          </>
        ) : null}
      </div>
    </PageShell>
  );
}
