import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type SemanticMetric = {
  metric_id: string;
  label?: string;
  expression?: string;
  status?: string;
  source_table?: string;
  grain?: string;
};

type SemanticJoin = {
  join_id?: string;
  left_table?: string;
  right_table?: string;
  left_key?: string;
  right_key?: string;
  cardinality?: string;
  causes_fanout?: boolean;
};

/** Semantic steward — approve/certify/deprecate/golden-test + join upsert. */
export default function BiSemanticStewardPanel() {
  const { config } = useApiConfig();
  const runnerOk = isRunnerConfigured(config);
  const qc = useQueryClient();
  const [joinForm, setJoinForm] = useState({
    left_table: '',
    right_table: '',
    left_key: '',
    right_key: '',
    cardinality: 'many_to_one',
  });
  const [msg, setMsg] = useState<string | null>(null);

  const metricsQ = useQuery({
    queryKey: ['bi', 'semantic', 'metrics'],
    queryFn: () => api.bi.semantic.metrics.list(config),
    enabled: runnerOk,
  });
  const joinsQ = useQuery({
    queryKey: ['bi', 'semantic', 'joins'],
    queryFn: () => api.bi.semantic.joins.list(config),
    enabled: runnerOk,
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['bi', 'semantic'] });
  };

  const upsertMetric = useMutation({
    mutationFn: (body: {
      metric_id: string;
      expression: string;
      status: string;
      label?: string;
      source_table?: string;
      grain?: string;
    }) => api.bi.semantic.metrics.upsert(config, body),
    onSuccess: () => {
      invalidate();
      setMsg(null);
    },
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const certifyMetric = useMutation({
    mutationFn: (metricId: string) => api.bi.semantic.metrics.certify(config, metricId),
    onSuccess: () => invalidate(),
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const deprecateMetric = useMutation({
    mutationFn: (metricId: string) => api.bi.semantic.metrics.deprecate(config, metricId),
    onSuccess: () => invalidate(),
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const goldenMut = useMutation({
    mutationFn: (metricId: string) => api.bi.semantic.metrics.goldenTest(config, metricId),
    onSuccess: (res) => {
      invalidate();
      const ok = res.ok !== false && res.passed !== false;
      setMsg(ok ? t('bi.steward.goldenOk') : t('bi.semantic.goldenFailed'));
    },
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const upsertJoin = useMutation({
    mutationFn: () =>
      api.bi.semantic.joins.upsert(config, {
        left_table: joinForm.left_table.trim(),
        right_table: joinForm.right_table.trim(),
        left_key: joinForm.left_key.trim(),
        right_key: joinForm.right_key.trim(),
        cardinality: joinForm.cardinality,
      }),
    onSuccess: () => {
      invalidate();
      setJoinForm({
        left_table: '',
        right_table: '',
        left_key: '',
        right_key: '',
        cardinality: 'many_to_one',
      });
      setMsg(null);
    },
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  if (!runnerOk) return null;

  const metrics = (metricsQ.data?.metrics || []) as SemanticMetric[];
  const joins = (joinsQ.data?.joins || []) as SemanticJoin[];
  const busy =
    upsertMetric.isPending ||
    certifyMetric.isPending ||
    deprecateMetric.isPending ||
    goldenMut.isPending ||
    upsertJoin.isPending;

  return (
    <section className="rounded-2xl border border-[#E1DFDD] bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-[#252423]">{t('bi.steward.title')}</h2>
      <p className="mt-1 text-xs text-slate-600">{t('bi.steward.subtitle')}</p>
      {msg ? <p className="mt-2 text-xs text-slate-700">{msg}</p> : null}

      <div className="mt-4">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t('bi.steward.metrics')}</h3>
        {metrics.length === 0 ? (
          <p className="mt-2 text-xs text-slate-500">{t('bi.steward.emptyMetrics')}</p>
        ) : (
          <ul className="mt-2 divide-y divide-slate-100">
            {metrics.map((m) => (
              <li key={m.metric_id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-900">{m.label || m.metric_id}</p>
                  <p className="truncate font-mono text-[11px] text-slate-500">
                    {t('bi.steward.expression')}: {String(m.expression || '—')}
                  </p>
                  <p className="text-[11px] text-slate-500">
                    {t('bi.steward.status')}: {m.status || 'draft'}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-800 hover:bg-violet-100 disabled:opacity-50"
                    disabled={busy || !m.expression}
                    onClick={() =>
                      upsertMetric.mutate({
                        metric_id: m.metric_id,
                        expression: String(m.expression || ''),
                        label: m.label,
                        source_table: m.source_table,
                        grain: m.grain,
                        status: m.status === 'approved' || m.status === 'certified' ? 'draft' : 'approved',
                      })
                    }
                  >
                    {m.status === 'approved' || m.status === 'certified'
                      ? t('bi.steward.draft')
                      : t('bi.steward.approve')}
                  </button>
                  {(m.status === 'approved' || m.status === 'certified') && (
                    <button
                      type="button"
                      className="rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
                      disabled={busy}
                      onClick={() => certifyMetric.mutate(m.metric_id)}
                    >
                      {m.status === 'certified' ? t('bi.semantic.certified') : t('bi.semantic.certify')}
                    </button>
                  )}
                  <button
                    type="button"
                    className="rounded-lg border border-sky-200 bg-sky-50 px-2.5 py-1 text-xs font-medium text-sky-800 hover:bg-sky-100 disabled:opacity-50"
                    disabled={busy}
                    onClick={() => goldenMut.mutate(m.metric_id)}
                  >
                    {goldenMut.isPending ? <Loader2 className="inline h-3 w-3 animate-spin" /> : null}{' '}
                    {t('bi.semantic.goldenRun')}
                  </button>
                  {m.status !== 'deprecated' ? (
                    <button
                      type="button"
                      className="rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:opacity-50"
                      disabled={busy}
                      onClick={() => deprecateMetric.mutate(m.metric_id)}
                    >
                      {t('bi.steward.deprecate')}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="mt-5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t('bi.steward.joins')}</h3>
        {joins.length === 0 ? (
          <p className="mt-2 text-xs text-slate-500">{t('bi.steward.emptyJoins')}</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {joins.map((j) => (
              <li
                key={j.join_id || `${j.left_table}-${j.right_table}`}
                className="rounded-lg border border-slate-100 px-3 py-2 text-xs"
              >
                <span className="font-mono">
                  {j.left_table}.{j.left_key}
                </span>
                <span className="mx-1 text-slate-400">→</span>
                <span className="font-mono">
                  {j.right_table}.{j.right_key}
                </span>
                {j.cardinality ? <span className="ml-2 text-slate-500">({j.cardinality})</span> : null}
                {j.causes_fanout ? <span className="ml-2 text-amber-700">fanout</span> : null}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-3 space-y-2 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-3">
          <p className="text-xs font-medium text-slate-700">{t('bi.steward.joinNew')}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input
              className="input-field font-mono text-xs"
              placeholder="left_table"
              value={joinForm.left_table}
              onChange={(e) => setJoinForm((f) => ({ ...f, left_table: e.target.value }))}
            />
            <input
              className="input-field font-mono text-xs"
              placeholder="left_key"
              value={joinForm.left_key}
              onChange={(e) => setJoinForm((f) => ({ ...f, left_key: e.target.value }))}
            />
            <input
              className="input-field font-mono text-xs"
              placeholder="right_table"
              value={joinForm.right_table}
              onChange={(e) => setJoinForm((f) => ({ ...f, right_table: e.target.value }))}
            />
            <input
              className="input-field font-mono text-xs"
              placeholder="right_key"
              value={joinForm.right_key}
              onChange={(e) => setJoinForm((f) => ({ ...f, right_key: e.target.value }))}
            />
          </div>
          <button
            type="button"
            className="btn-secondary inline-flex items-center gap-1.5 text-xs"
            disabled={
              busy ||
              !joinForm.left_table.trim() ||
              !joinForm.right_table.trim() ||
              !joinForm.left_key.trim() ||
              !joinForm.right_key.trim()
            }
            onClick={() => upsertJoin.mutate()}
          >
            {upsertJoin.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {t('bi.steward.joinSave')}
          </button>
        </div>
      </div>
    </section>
  );
}
