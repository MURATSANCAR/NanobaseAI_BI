import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, Link } from 'react-router-dom';
import { CheckCircle2, ChevronDown, Database, Loader2, RefreshCw, Table2, Trash2, Wifi, XCircle } from 'lucide-react';
import clsx from 'clsx';
import { PageShell } from '@/components/PageShell';
import BiSourceSwitcher from '@/components/bi/BiSourceSwitcher';
import { api, isRunnerConfigured } from '@/api/client';
import { createDatasourceService } from '@/api/services';
import { useApiConfig } from '@/context/ApiContext';
import { useAuth } from '@/context/AuthContext';
import type { BiConnectionProfile, BiConnectionUpsert } from '@/api/types';
import type { SchemaScan } from '@/api/contracts/datasource';
import { formatBackendErrorText, localizeUserMessage } from '@/utils/backendLabels';
import { t } from '@/i18n';
import { getFeatureFlags } from '@/config/environment';

const dsService = createDatasourceService();

const DRIVERS = ['postgresql', 'mysql', 'oracle', 'hana', 'odata', 'sqlite', 'supabase'] as const;

const DRIVER_LABEL_KEYS: Record<(typeof DRIVERS)[number], string> = {
  postgresql: 'bi.driver.postgresql',
  mysql: 'bi.driver.mysql',
  oracle: 'bi.driver.oracle',
  hana: 'bi.driver.hana',
  odata: 'bi.driver.odata',
  sqlite: 'bi.driver.sqlite',
  supabase: 'bi.driver.supabase',
};

const PRESETS: Record<string, Partial<BiConnectionUpsert>> = {
  supabase: {
    driver: 'supabase',
    deployment: 'cloud',
    port: 5432,
    database: 'postgres',
    username: 'postgres',
    ssl: true,
  },
  postgresql_local: {
    driver: 'postgresql',
    deployment: 'local',
    host: '127.0.0.1',
    port: 5432,
    ssl: false,
  },
  mysql_local: {
    driver: 'mysql',
    deployment: 'local',
    host: '127.0.0.1',
    port: 3306,
    ssl: false,
  },
  oracle_adb_ssb: {
    driver: 'oracle',
    deployment: 'cloud',
    host: '',
    port: 1522,
    database: '',
    username: 'ADMIN',
    ssl: true,
    connection_url: '',
  },
  sap_hana_ro: {
    driver: 'hana',
    deployment: 'local',
    host: '',
    port: 30015,
    database: 'PRD',
    username: 'NANOBASE_HANA_RO',
    ssl: true,
  },
  sap_s4_odata: {
    driver: 'odata',
    deployment: 'cloud',
    host: '',
    port: 443,
    database: '',
    username: 'NANOBASE_ODATA_RO',
    ssl: true,
  },
};

function formFromProfile(p: BiConnectionProfile): BiConnectionUpsert & { source_id: string } {
  return {
    source_id: p.id || '',
    label: p.label || t('bi.connection.primaryLabel'),
    deployment: p.deployment || 'cloud',
    driver: p.driver || 'postgresql',
    host: p.host || '',
    port: p.port || 5432,
    database: p.database || '',
    username: p.username || '',
    password: '',
    ssl: p.ssl ?? true,
    sqlite_path: p.sqlite_path || '',
    supabase_url: p.supabase_url || '',
    supabase_api_key: '',
    connection_url: '',
  };
}

const emptyForm = (): BiConnectionUpsert & { source_id: string } => ({
  source_id: '',
  label: '',
  deployment: 'cloud',
  driver: 'supabase',
  host: '',
  port: 5432,
  database: 'postgres',
  username: 'postgres',
  password: '',
  ssl: true,
  sqlite_path: '',
  supabase_url: '',
  supabase_api_key: '',
  connection_url: '',
});

export default function BiConnectionPage() {
  const { config } = useApiConfig();
  const { canBi } = useAuth();
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const enabled = isRunnerConfigured(config);
  const canWrite = canBi('sources.write');
  const canScan = canBi('schema.scan');

  const sourcesQ = useQuery({
    queryKey: ['bi-sources', config],
    queryFn: () => api.bi.sources.list(config),
    enabled,
  });

  const biStatus = useQuery({
    queryKey: ['bi-status'],
    queryFn: () => api.bi.status(config),
    enabled,
    staleTime: 120_000,
  });

  useEffect(() => {
    if (searchParams.get('tour') !== '1') return;
    const el = document.getElementById('bi-first-value');
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }, [searchParams, biStatus.data]);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<BiConnectionUpsert & { source_id: string }>(emptyForm());
  const [formOpen, setFormOpen] = useState(false);
  const [scanId, setScanId] = useState<string | null>(null);
  const [scenarioBuildId, setScenarioBuildId] = useState<string | null>(null);
  const [scenarioToast, setScenarioToast] = useState<string | null>(null);
  const [testState, setTestState] = useState<'IDLE' | 'TESTING' | 'SUCCESS' | 'FAILED'>('IDLE');
  const flags = getFeatureFlags();

  const sources = sourcesQ.data?.sources ?? [];
  const activeId = sourcesQ.data?.active_id ?? null;

  const scanQ = useQuery({
    queryKey: ['bi-schema-scan', scanId],
    queryFn: () => dsService.getScan(config, scanId!),
    enabled: Boolean(enabled && scanId),
    refetchInterval: (q) => {
      const st = (q.state.data as SchemaScan | undefined)?.status;
      return st === 'COMPLETED' || st === 'FAILED' ? false : 2500;
    },
  });

  useEffect(() => {
    if (scanQ.data?.status !== 'COMPLETED') return;
    void qc.invalidateQueries({ queryKey: ['bi-schema'] });
    void qc.invalidateQueries({ queryKey: ['bi-schema-graph'] });
    void qc.invalidateQueries({ queryKey: ['bi-status'] });
    const ds = scanQ.data.datasourceId || selectedId;
    if (!ds || !enabled) return;
    const expectedId = `build-scan-${ds}`.slice(0, 64);
    let cancelled = false;
    setScenarioToast(t('bi.scenarioBuildPreparing'));
    void (async () => {
      try {
        const existing = await api.bi.scenarios.buildStatus(config, ds, expectedId);
        if (cancelled) return;
        if (existing.status && existing.error !== 'NOT_FOUND') {
          setScenarioBuildId(expectedId);
          return;
        }
        const created = await api.bi.scenarios.startBuild(config, ds, {
          async: true,
          autoPublish: true,
        });
        if (cancelled) return;
        setScenarioBuildId(String(created.buildId || created.id || expectedId));
      } catch {
        if (cancelled) return;
        try {
          const created = await api.bi.scenarios.startBuild(config, ds, {
            async: true,
            autoPublish: true,
          });
          if (!cancelled) setScenarioBuildId(String(created.buildId || created.id || expectedId));
        } catch {
          if (!cancelled) {
            setScenarioBuildId(expectedId);
            setScenarioToast(t('bi.scenarioBuildFailed'));
          }
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [qc, scanQ.data?.status, scanQ.data?.datasourceId, selectedId, enabled, config]);

  const scenarioBuildQ = useQuery({
    queryKey: ['scenario-build', scenarioBuildId, selectedId, config],
    queryFn: () => {
      const ds = selectedId || activeId || 'bi_reporting';
      return api.bi.scenarios.buildStatus(config, ds, scenarioBuildId!);
    },
    enabled: Boolean(enabled && scenarioBuildId),
    refetchInterval: (q) => {
      const st = (q.state.data as { status?: string } | undefined)?.status;
      return st === 'COMPLETED' || st === 'FAILED' ? false : 2500;
    },
  });

  useEffect(() => {
    const st = scenarioBuildQ.data?.status;
    if (st === 'COMPLETED') {
      setScenarioToast(t('bi.scenarioBuildReady'));
      void qc.invalidateQueries({ queryKey: ['bi-chat-suggestions'] });
      void qc.invalidateQueries({ queryKey: ['scenario-reviews'] });
    } else if (st === 'FAILED') {
      setScenarioToast(t('bi.scenarioBuildFailed'));
    } else if (scenarioBuildId && (!st || st === 'RUNNING' || st === 'QUEUED')) {
      setScenarioToast(t('bi.scenarioBuildPreparing'));
    }
  }, [scenarioBuildQ.data?.status, scenarioBuildId, qc]);

  const scenarioRebuildMut = useMutation({
    mutationFn: async () => {
      const ds = selectedId || activeId;
      if (!ds) throw new Error(t('bi.scanSelectSource'));
      const created = await api.bi.scenarios.startBuild(config, ds, {
        async: true,
        autoPublish: true,
      });
      return { ds, buildId: String(created.buildId || created.id || `build-scan-${ds}`.slice(0, 64)) };
    },
    onSuccess: ({ buildId }) => {
      setScenarioBuildId(buildId);
      setScenarioToast(t('bi.scenarioBuildPreparing'));
    },
  });

  useEffect(() => {
    if (!sources.length) return;
    const pick =
      (selectedId && sources.find((s) => s.id === selectedId)) ||
      sources.find((s) => s.id === activeId) ||
      sources[0];
    if (pick && pick.id !== selectedId) {
      setSelectedId(pick.id || null);
      setForm(formFromProfile(pick));
    }
  }, [sources, activeId, selectedId]);

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['bi-sources'] });
    void qc.invalidateQueries({ queryKey: ['bi-connection'] });
    void qc.invalidateQueries({ queryKey: ['bi-status'] });
    void qc.invalidateQueries({ queryKey: ['bi-schema'] });
    void qc.invalidateQueries({ queryKey: ['bi-schema-graph'] });
    void qc.invalidateQueries({ queryKey: ['bi-audit-recent'] });
    void qc.invalidateQueries({ queryKey: ['bi-briefing'] });
  };

  const testMut = useMutation({
    mutationFn: async () => {
      const sid = selectedId || form.source_id;
      if (!sid) throw new Error('Önce bir kaynak seçin veya kaydedin.');
      setTestState('TESTING');
      return dsService.testDatasource(config, sid);
    },
    onSuccess: (res) => {
      setTestState(res.ok || res.success ? 'SUCCESS' : 'FAILED');
      invalidate();
    },
    onError: () => setTestState('FAILED'),
  });

  const saveMut = useMutation({
    mutationFn: async () => {
      const sid = (form.source_id || form.label || 'primary')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_-]+/g, '_')
        .replace(/^_+|_+$/g, '') || 'primary';
      const { source_id: _sid, ...body } = form;
      return dsService.createDatasource(config, sid, { ...body, label: form.label || sid, name: form.label || sid });
    },
    onSuccess: (res) => {
      invalidate();
      const id = (res as { source?: { id?: string }; id?: string }).source?.id || (res as { id?: string }).id || form.source_id;
      setSelectedId(id || null);
      setForm((f) => ({ ...f, source_id: id || f.source_id, password: '', supabase_api_key: '', connection_url: '' }));
    },
  });

  const activateMut = useMutation({
    mutationFn: (id: string) => dsService.activate(config, id),
    onSuccess: invalidate,
  });

  const scanMut = useMutation({
    mutationFn: async () => {
      const sid = selectedId || form.source_id;
      if (!sid) throw new Error(t('bi.scanSelectSource'));
      return dsService.startScan(config, sid);
    },
    onSuccess: (scan) => {
      if (scan.scanId) setScanId(scan.scanId);
    },
  });

  const deleteMut = useMutation({
    mutationFn: async () => {
      const sid = selectedId;
      if (!sid) throw new Error(t('bi.deleteNoSource'));
      const src = sources.find((s) => s.id === sid);
      if (src?.protected || src?.managed) {
        throw new Error(t('bi.deleteSystemSourceBlocked'));
      }
      return dsService.deleteDatasource(config, sid);
    },
    onSuccess: () => {
      setSelectedId(null);
      setForm(emptyForm());
      invalidate();
    },
  });

  const isSqlite = form.driver === 'sqlite';
  const isSupabase = form.driver === 'supabase';
  const isOracle = form.driver === 'oracle';
  const selected = sources.find((s) => s.id === selectedId);
  const lastOk = selected?.last_test_ok;
  const lastMsg = selected?.last_test_message;

  const applyPreset = (key: string) => {
    const preset = PRESETS[key];
    if (!preset) return;
    setForm((f) => ({
      ...f,
      ...preset,
      ...(key === 'oracle_adb_ssb' ? { label: t('bi.connection.oracleAdbSsbLabel') } : {}),
    }));
  };

  return (
    <PageShell pageId="biConnection" titleKey="bi.sources.title" subtitleKey="bi.sources.subtitle" maxWidth="max-w-[1400px]">
      <div className="flex w-full flex-col gap-4 pb-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <BiSourceSwitcher config={config} />
        <button
          type="button"
          className="btn-secondary min-h-11 w-full text-sm sm:w-auto"
          onClick={() => {
            setSelectedId(null);
            setForm(emptyForm());
            setFormOpen(true);
          }}
        >
          {t('bi.sources.add')}
        </button>
      </div>

      {sources.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {sources.map((s) => {
            const id = s.id || '';
            const active = id === activeId;
            return (
              <button
                key={id}
                type="button"
                onClick={() => {
                  setSelectedId(id);
                  setForm(formFromProfile(s));
                }}
                className={clsx(
                  'rounded-xl border px-4 py-3 text-left transition',
                  selectedId === id ? 'border-violet-400 bg-violet-50/60' : 'border-slate-200 bg-white hover:border-slate-300',
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-semibold text-slate-900">{s.label || id}</p>
                  <div className="flex shrink-0 flex-wrap justify-end gap-1">
                    {active && (
                      <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-800">
                        {t('bi.sources.activeBadge')}
                      </span>
                    )}
                    {(s.managed || s.protected) && (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-600">
                        {t('bi.sources.managedBadge')}
                      </span>
                    )}
                  </div>
                </div>
                <p className="mt-1 truncate font-mono text-[11px] text-slate-500">{s.supabase_url || s.host || id}</p>
                {!active && (
                  <button
                    type="button"
                    className="mt-2 text-xs font-medium text-violet-700 hover:underline"
                    disabled={activateMut.isPending}
                    onClick={(e) => {
                      e.stopPropagation();
                      activateMut.mutate(id);
                    }}
                  >
                    {t('bi.sources.activate')}
                  </button>
                )}
              </button>
            );
          })}
        </div>
      )}

      {biStatus.data?.schema_cached ? (
        <Link
          to="/bi/schema"
          className="bi-schema-panel mb-4 flex items-center gap-3 p-4 transition-colors hover:border-violet-200"
        >
          <div className="bi-schema-table-icon !h-10 !w-10">
            <Table2 className="h-5 w-5" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-slate-800">{t('bi.schemaOpenCta')}</p>
            <p className="text-xs text-slate-500">{t('bi.schemaOpenHint')}</p>
          </div>
          <span className="text-sm font-medium text-violet-700">{t('common.next')} →</span>
        </Link>
      ) : null}

      {selected?.configured && (
        <div
          className={clsx(
            'card mb-4 flex items-center gap-3 p-4 text-sm',
            lastOk === true && 'border-status-ok/30 text-status-ok',
            lastOk === false && 'border-status-fail/30 text-slate-700',
            lastOk == null && 'border-slate-200 text-slate-700',
          )}
        >
          {lastOk === true ? (
            <CheckCircle2 className="h-5 w-5 shrink-0" />
          ) : lastOk === false ? (
            <XCircle className="h-5 w-5 shrink-0 text-status-fail" />
          ) : (
            <Wifi className="h-5 w-5 shrink-0 text-slate-400" />
          )}
          <div>
            <div className="font-medium">
              {lastOk === true
                ? t('bi.connectionOk')
                : lastOk === false
                  ? t('bi.connectionFailed')
                  : t('bi.connectionUntested')}
            </div>
            {lastMsg && lastOk === false && <div className="text-xs text-slate-500">{lastMsg}</div>}
            {lastOk == null && (
              <div className="text-xs text-slate-500">{t('bi.connectionUntestedHint')}</div>
            )}
          </div>
        </div>
      )}

      <div className="card overflow-hidden">
        <button
          type="button"
          className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition hover:bg-slate-50/80 sm:px-6"
          aria-expanded={formOpen}
          aria-controls="bi-source-connection-form"
          onClick={() => setFormOpen((v) => !v)}
        >
          <Database className="h-4 w-4 shrink-0 text-slate-500" aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold text-slate-900">{t('bi.sources.formTitle')}</p>
            <p className="truncate text-xs text-slate-500">
              {formOpen
                ? t('bi.sources.formCollapseHint')
                : selected?.label
                  ? t('bi.sources.formExpandHintSelected', { name: selected.label })
                  : t('bi.sources.formExpandHint')}
            </p>
          </div>
          <ChevronDown
            className={clsx('h-4 w-4 shrink-0 text-slate-400 transition-transform duration-200', formOpen && 'rotate-180')}
            aria-hidden
          />
        </button>

        {formOpen && (
          <div id="bi-source-connection-form" className="space-y-4 border-t border-surface-border px-4 py-4 sm:px-6 sm:pb-6">
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn-secondary text-xs" onClick={() => applyPreset('supabase')}>
                {t('bi.presetCloud')}
              </button>
              <button type="button" className="btn-secondary text-xs" onClick={() => applyPreset('oracle_adb_ssb')}>
                {t('bi.presetOracleAdb')}
              </button>
              <button type="button" className="btn-secondary text-xs" onClick={() => applyPreset('postgresql_local')}>
                {t('bi.presetLocalSql')}
              </button>
              <button type="button" className="btn-secondary text-xs" onClick={() => applyPreset('mysql_local')}>
                {t('bi.presetLocalMysql')}
              </button>
            </div>
            {isOracle && (
              <p className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">{t('bi.oracleAdbHint')}</p>
            )}

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="label-text">{t('bi.sources.id')}</label>
                <input
                  className="input-field font-mono text-sm"
                  value={form.source_id}
                  disabled={Boolean(selectedId)}
                  placeholder={t('bi.sources.idPlaceholder')}
                  onChange={(e) => setForm({ ...form, source_id: e.target.value })}
                />
              </div>
              <div>
                <label className="label-text">{t('bi.connectionLabel')}</label>
                <input className="input-field" value={form.label || ''} onChange={(e) => setForm({ ...form, label: e.target.value })} />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">{t('bi.deployment')}</label>
                <select
                  className="input-field"
                  value={form.deployment}
                  onChange={(e) => setForm({ ...form, deployment: e.target.value as 'local' | 'cloud' })}
                >
                  <option value="cloud">{t('bi.deploymentCloud')}</option>
                  <option value="local">{t('bi.deploymentLocal')}</option>
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-500">{t('bi.driver')}</label>
                <select
                  className="input-field"
                  value={form.driver}
                  onChange={(e) => setForm({ ...form, driver: e.target.value as BiConnectionUpsert['driver'] })}
                >
                  {DRIVERS.map((d) => (
                    <option key={d} value={d}>
                      {t(DRIVER_LABEL_KEYS[d])}
                    </option>
                  ))}
                </select>
                <p className="mt-1 text-[11px] text-slate-500">{t('bi.driverHint')}</p>
              </div>
            </div>

            {isSqlite ? (
              <div>
                <label className="mb-1 block text-xs text-slate-500">{t('bi.sqlitePath')}</label>
                <input
                  className="input-field font-mono text-sm"
                  placeholder={t('bi.sqlitePathPlaceholder')}
                  value={form.sqlite_path || ''}
                  onChange={(e) => setForm({ ...form, sqlite_path: e.target.value })}
                />
              </div>
            ) : isSupabase ? (
              <>
                <div>
                  <label className="label-text">{t('bi.cloudUrl')}</label>
                  <input
                    className="input-field font-mono text-sm"
                    placeholder={t('bi.cloudUrlPlaceholder')}
                    value={form.supabase_url || ''}
                    onChange={(e) => setForm({ ...form, supabase_url: e.target.value })}
                  />
                  <p className="mt-1 text-[11px] text-slate-500">{t('bi.cloudUrlHint')}</p>
                </div>
                <div>
                  <label className="label-text">{t('bi.cloudKey')}</label>
                  <input
                    type="password"
                    className="input-field font-mono text-sm"
                    placeholder={selected?.supabase_api_key_configured ? selected.supabase_api_key_masked : '••••••••'}
                    value={form.supabase_api_key || ''}
                    onChange={(e) => setForm({ ...form, supabase_api_key: e.target.value })}
                  />
                  <p className="mt-1 text-[11px] text-slate-500">{t('bi.cloudKeyHint')}</p>
                </div>
                <details className="text-sm text-slate-600">
                  <summary className="cursor-pointer text-accent">{t('bi.directSqlOptional')}</summary>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <input
                      className="input-field"
                      placeholder={t('bi.host')}
                      value={form.host || ''}
                      onChange={(e) => setForm({ ...form, host: e.target.value })}
                    />
                    <input
                      className="input-field"
                      type="password"
                      placeholder={t('bi.postgresPassword')}
                      value={form.password || ''}
                      onChange={(e) => setForm({ ...form, password: e.target.value })}
                    />
                  </div>
                </details>
              </>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs text-slate-500">{t('bi.host')}</label>
                  <input
                    className="input-field"
                    value={form.host || ''}
                    placeholder={isOracle ? t('bi.oracleHostPlaceholder') : undefined}
                    onChange={(e) => setForm({ ...form, host: e.target.value })}
                  />
                  <p className="mt-1 text-[11px] text-slate-500">{isOracle ? t('bi.oracleHostHint') : t('bi.hostHint')}</p>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">{t('bi.port')}</label>
                  <input
                    type="number"
                    className="input-field"
                    value={form.port ?? ''}
                    onChange={(e) => setForm({ ...form, port: Number(e.target.value) || undefined })}
                  />
                  {isOracle && <p className="mt-1 text-[11px] text-slate-500">{t('bi.oraclePortHint')}</p>}
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">
                    {isOracle ? t('bi.oracleServiceName') : t('bi.database')}
                  </label>
                  <input
                    className="input-field"
                    value={form.database || ''}
                    placeholder={isOracle ? t('bi.oracleServicePlaceholder') : undefined}
                    onChange={(e) => setForm({ ...form, database: e.target.value })}
                  />
                  {isOracle && <p className="mt-1 text-[11px] text-slate-500">{t('bi.oracleServiceHint')}</p>}
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">{t('bi.username')}</label>
                  <input className="input-field" value={form.username || ''} onChange={(e) => setForm({ ...form, username: e.target.value })} />
                </div>
                <div className="sm:col-span-2">
                  <label className="mb-1 block text-xs text-slate-500">{t('bi.password')}</label>
                  <input
                    type="password"
                    className="input-field"
                    placeholder={selected?.password_configured ? selected.password_masked : ''}
                    value={form.password || ''}
                    onChange={(e) => setForm({ ...form, password: e.target.value })}
                  />
                </div>
                {isOracle && (
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs text-slate-500">{t('bi.oracleDsn')}</label>
                    <textarea
                      className="input-field min-h-[88px] font-mono text-xs"
                      placeholder={
                        selected?.connection_url_configured
                          ? t('bi.oracleDsnConfigured')
                          : '(description=(address=(protocol=tcps)(port=1522)(host=…))(connect_data=(service_name=…))(security=(ssl_server_dn_match=yes)))'
                      }
                      value={form.connection_url || ''}
                      onChange={(e) => setForm({ ...form, connection_url: e.target.value })}
                    />
                    <p className="mt-1 text-[11px] text-slate-500">{t('bi.oracleDsnHint')}</p>
                  </div>
                )}
                <label className="flex items-center gap-2 text-sm text-slate-700 sm:col-span-2">
                  <input type="checkbox" checked={form.ssl ?? true} onChange={(e) => setForm({ ...form, ssl: e.target.checked })} />
                  {t('bi.useSsl')}
                </label>
              </div>
            )}

            <div className="flex flex-col gap-3 border-t border-surface-border pt-4 sm:flex-row sm:flex-wrap">
              {canWrite ? (
                <>
                  <button
                    type="button"
                    className="btn-secondary flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
                    disabled={testMut.isPending || !selectedId}
                    onClick={() => testMut.mutate()}
                  >
                    {testMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wifi className="h-4 w-4" />}
                    {t('bi.testConnection')}
                  </button>
                  <button
                    type="button"
                    className="btn-primary flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
                    disabled={saveMut.isPending}
                    onClick={() => saveMut.mutate()}
                  >
                    {saveMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Database className="h-4 w-4" />}
                    {t('bi.saveConnection')}
                  </button>
                </>
              ) : (
                <p className="text-xs text-slate-500">{t('api.error.bi_source_admin_required')}</p>
              )}
              {canScan && flags.useNanobaseBackend && (
                <button
                  type="button"
                  className="btn-secondary flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
                  disabled={scanMut.isPending || !selectedId}
                  onClick={() => scanMut.mutate()}
                >
                  {scanMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  {t('bi.scanSchema')}
                </button>
              )}
              {canScan && flags.useNanobaseBackend && selectedId && (
                <button
                  type="button"
                  className="btn-secondary flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
                  disabled={scenarioRebuildMut.isPending}
                  onClick={() => scenarioRebuildMut.mutate()}
                >
                  {scenarioRebuildMut.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  {t('bi.scenarioRebuild')}
                </button>
              )}
              {canScan && !flags.useNanobaseBackend && (
                <p className="w-full text-xs text-slate-500 sm:w-auto">{t('bi.scanLegacyUnavailable')}</p>
              )}
              {canWrite &&
                selectedId &&
                selected &&
                !selected.protected &&
                !selected.managed && (
                <button
                  type="button"
                  className="btn-secondary flex min-h-11 w-full items-center justify-center gap-2 text-rose-700 sm:w-auto"
                  disabled={deleteMut.isPending}
                  onClick={() => {
                    if (window.confirm(t('bi.deleteDatasourceConfirm'))) deleteMut.mutate();
                  }}
                >
                  {deleteMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                  {t('common.delete')}
                </button>
              )}
            </div>

            {testState === 'TESTING' && (
              <div className="text-sm text-slate-600">{t('bi.testingConnection')}</div>
            )}
            {testMut.isSuccess && (
              <div className={clsx('text-sm', testMut.data.ok || testMut.data.success ? 'text-status-ok' : 'text-status-fail')}>
                {testMut.data.ok || testMut.data.success
                  ? t('bi.connectionTestOk', {
                      version: testMut.data.databaseVersion ? ` — ${testMut.data.databaseVersion}` : '',
                      latency:
                        testMut.data.latencyMs != null ? ` (${testMut.data.latencyMs} ms)` : '',
                    })
                  : t('bi.connectionTestFail')}
              </div>
            )}
            {(testMut.isError ||
              saveMut.isError ||
              scanMut.isError ||
              deleteMut.isError ||
              scenarioRebuildMut.isError) && (
              <div className="text-sm text-status-fail">
                {localizeUserMessage((testMut.error as Error)?.message) ||
                  localizeUserMessage((saveMut.error as Error)?.message) ||
                  localizeUserMessage((scanMut.error as Error)?.message) ||
                  localizeUserMessage((deleteMut.error as Error)?.message) ||
                  localizeUserMessage((scenarioRebuildMut.error as Error)?.message)}
              </div>
            )}
            {saveMut.isSuccess && <div className="text-sm text-status-ok">{t('bi.saveSuccess')}</div>}

            {scenarioToast && (
              <div
                className={clsx(
                  'rounded-lg px-3 py-2 text-sm',
                  scenarioBuildQ.data?.status === 'FAILED'
                    ? 'bg-rose-50 text-rose-800'
                    : scenarioBuildQ.data?.status === 'COMPLETED'
                      ? 'bg-emerald-50 text-emerald-800'
                      : 'bg-amber-50 text-amber-900',
                )}
                role="status"
              >
                {scenarioToast}
              </div>
            )}

            {scanId && scanQ.data && (
              <div className="rounded-xl border border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-700">
                <p className="font-semibold text-slate-900">
                  {t('bi.scanTitle', { status: scanQ.data.status })}
                  {(scanQ.data.status === 'QUEUED' || scanQ.data.status === 'RUNNING') && (
                    <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin" />
                  )}
                </p>
                {scanQ.data.status === 'COMPLETED' && (
                  <ul className="mt-2 list-inside list-disc text-xs text-slate-600">
                    <li>{t('bi.scanTables', { count: String(scanQ.data.tableCount ?? '—') })}</li>
                    <li>{t('bi.scanColumns', { count: String(scanQ.data.columnCount ?? '—') })}</li>
                    <li>{t('bi.scanRelationships', { count: String(scanQ.data.relationshipCount ?? '—') })}</li>
                    <li>{t('bi.scanIndexed', { count: String(scanQ.data.indexedDocumentCount ?? '—') })}</li>
                    <li>{t('bi.scanSkipped', { count: String(scanQ.data.skippedDocumentCount ?? '—') })}</li>
                  </ul>
                )}
                {scanQ.data.status === 'FAILED' && (
                  <p className="mt-2 text-status-fail">
                    {t('bi.scanFailed')}
                    {scanQ.data.error ? ` (${formatBackendErrorText(scanQ.data.error)})` : ''}
                  </p>
                )}
                {flags.enableSchemaExplorer && scanQ.data.status === 'COMPLETED' && (
                  <Link to="/bi/schema" className="mt-3 inline-block text-sm font-medium text-violet-700 hover:underline">
                    {t('bi.openSchemaExplorer')}
                  </Link>
                )}
              </div>
            )}
          </div>
        )}
      </div>
      </div>
    </PageShell>
  );
}
