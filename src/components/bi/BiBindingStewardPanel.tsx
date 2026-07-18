import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

/**
 * Project Binding steward — operators only.
 * End users never see this; chat stays business-language only.
 */
export default function BiBindingStewardPanel() {
  const { config } = useApiConfig();
  const runnerOk = isRunnerConfigured(config);
  const qc = useQueryClient();
  const [notes, setNotes] = useState('');
  const [msg, setMsg] = useState<string | null>(null);

  const statusQ = useQuery({
    queryKey: ['bi', 'sqp', 'status'],
    queryFn: () => api.bi.semantic.binding.status(config),
    enabled: runnerOk,
  });
  const viewsQ = useQuery({
    queryKey: ['bi', 'sqp', 'approval-views'],
    queryFn: () => api.bi.semantic.binding.approvalViews(config),
    enabled: runnerOk,
    retry: false,
  });
  const graphQ = useQuery({
    queryKey: ['bi', 'sqp', 'graph'],
    queryFn: () => api.bi.semantic.graph.list(config),
    enabled: runnerOk,
  });
  const templatesQ = useQuery({
    queryKey: ['bi', 'sqp', 'templates'],
    queryFn: () => api.bi.semantic.templates.list(config),
    enabled: runnerOk,
    retry: false,
  });
  const [proposeQ, setProposeQ] = useState('Son 3 aydaki fatura toplamı nedir?');

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['bi', 'sqp'] });
  };

  const installMut = useMutation({
    mutationFn: () => api.bi.semantic.binding.installFixture(config, { fixture_name: 'binding_erp_tr_a' }),
    onSuccess: () => {
      invalidate();
      setMsg(t('bi.bindingSteward.installed'));
    },
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const enrichMut = useMutation({
    mutationFn: () => api.bi.semantic.binding.enrich(config),
    onSuccess: () => {
      invalidate();
      setMsg(t('bi.bindingSteward.enriched'));
    },
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const approveMut = useMutation({
    mutationFn: () =>
      api.bi.semantic.binding.approve(config, {
        approved_by: 'finance_steward',
        notes: notes.trim() || t('bi.bindingSteward.defaultNotes'),
      }),
    onSuccess: (res) => {
      invalidate();
      setMsg(t('bi.bindingSteward.approved', { fingerprint: String(res.fingerprint || '') }));
    },
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const promoteMut = useMutation({
    mutationFn: (body: {
      from_entity: string;
      to_entity: string;
      role: string;
      decision: 'approved' | 'rejected';
    }) => api.bi.semantic.graph.promote(config, { ...body, steward: 'finance_ops' }),
    onSuccess: () => invalidate(),
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const proposeTplMut = useMutation({
    mutationFn: () =>
      api.bi.semantic.templates.propose(config, { question: proposeQ.trim(), enrich_qwen: true }),
    onSuccess: (res) => {
      invalidate();
      setMsg(
        res.ok
          ? t('bi.bindingSteward.templateProposed', {
              id: String(res.candidate?.template?.template_id || res.candidate?.candidate_id || ''),
            })
          : localizeUserMessage(String(res.code || 'propose_failed')),
      );
    },
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  const promoteTplMut = useMutation({
    mutationFn: (body: {
      candidate_id: string;
      decision: 'approved' | 'rejected';
      rejection_reason?: string;
    }) => api.bi.semantic.templates.promote(config, { ...body, steward: 'finance_ops' }),
    onSuccess: (res, vars) => {
      invalidate();
      if (!res.ok) {
        setMsg(localizeUserMessage(String(res.code || 'promote_failed')));
        return;
      }
      setMsg(
        vars.decision === 'rejected'
          ? t('bi.bindingSteward.templateRejected')
          : t('bi.bindingSteward.templatePromoted', { id: String(res.template_id || '') }),
      );
    },
    onError: (err) => setMsg(localizeUserMessage(String(err))),
  });

  if (!runnerOk) return null;

  const views = viewsQ.data?.views || [];
  const edges = graphQ.data?.edges || [];
  const candidates = edges.filter((e) => e.status === 'candidate');
  const tplCandidates = (templatesQ.data?.ready_for_approval || templatesQ.data?.candidates || []).filter(
    (c) => c.status === 'ready_for_approval' || c.gate === 'passed',
  );
  const tplPending = (templatesQ.data?.candidates || []).filter((c) => c.status === 'candidate');
  const busy =
    installMut.isPending ||
    enrichMut.isPending ||
    approveMut.isPending ||
    promoteMut.isPending ||
    proposeTplMut.isPending ||
    promoteTplMut.isPending;

  return (
    <section className="rounded-2xl border border-[#E1DFDD] bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold text-[#252423]">{t('bi.bindingSteward.title')}</h2>
      <p className="mt-1 text-xs text-slate-600">{t('bi.bindingSteward.subtitle')}</p>
      <p className="mt-1 text-[11px] text-slate-500">{t('bi.bindingSteward.endUserNote')}</p>
      <p className="mt-1 text-[11px] text-emerald-800">{t('bi.bindingSteward.autoHint')}</p>

      {statusQ.data ? (
        <p className="mt-2 text-xs text-slate-700">
          {t('bi.bindingSteward.source')}: <span className="font-mono">{statusQ.data.active_source_id}</span>
          {' · '}
          {t('bi.bindingSteward.status')}: {statusQ.data.binding_status || statusQ.data.binding_error || '—'}
        </p>
      ) : null}

      {msg ? <p className="mt-2 text-xs text-slate-700">{msg}</p> : null}
      {viewsQ.isError ? (
        <p className="mt-2 text-xs text-amber-800">{t('bi.bindingSteward.missingBinding')}</p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn-secondary text-xs" disabled={busy} onClick={() => installMut.mutate()}>
          {installMut.isPending ? <Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" /> : null}
          {t('bi.bindingSteward.installFixture')}
        </button>
        <button type="button" className="btn-secondary text-xs" disabled={busy} onClick={() => enrichMut.mutate()}>
          {enrichMut.isPending ? <Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" /> : null}
          {t('bi.bindingSteward.enrich')}
        </button>
      </div>

      {viewsQ.data?.instruction ? (
        <p className="mt-3 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-950">
          {viewsQ.data.instruction}
        </p>
      ) : null}

      <div className="mt-4 space-y-3">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {t('bi.bindingSteward.approvalViews')}
        </h3>
        {views.length === 0 ? (
          <p className="text-xs text-slate-500">{t('bi.bindingSteward.emptyViews')}</p>
        ) : (
          views.map((v) => (
            <article key={v.logical_concept} className="rounded-xl border border-slate-100 p-3">
              <p className="text-sm font-medium text-slate-900">{v.logical_concept}</p>
              <p className="mt-1 text-xs text-slate-600">{v.description}</p>
              <dl className="mt-2 grid gap-1 text-[11px] text-slate-600 sm:grid-cols-2">
                <div>
                  <dt className="font-semibold text-slate-500">{t('bi.bindingSteward.physical')}</dt>
                  <dd className="font-mono">
                    {v.physical_table}.{v.physical_field}
                  </dd>
                </div>
                <div>
                  <dt className="font-semibold text-slate-500">{t('bi.bindingSteward.aggExample')}</dt>
                  <dd className="font-mono">{v.aggregation_example}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-slate-500">{t('bi.bindingSteward.comment')}</dt>
                  <dd>{v.comment || '—'}</dd>
                </div>
                <div>
                  <dt className="font-semibold text-slate-500">{t('bi.bindingSteward.profile')}</dt>
                  <dd>
                    null={v.null_ratio ?? '—'} · min={String(v.min_value ?? '—')} · max={String(v.max_value ?? '—')}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="font-semibold text-slate-500">{t('bi.bindingSteward.samples')}</dt>
                  <dd className="font-mono">{(v.sample_values || []).slice(0, 5).map(String).join(', ') || '—'}</dd>
                </div>
              </dl>
              <div className="mt-2">
                <p className="text-[11px] font-semibold uppercase text-amber-800">
                  {t('bi.bindingSteward.alternatives')}
                </p>
                <ul className="mt-1 space-y-1">
                  {(v.alternative_candidates || []).map((a) => (
                    <li key={a.field} className="rounded-lg bg-slate-50 px-2 py-1.5 text-[11px] text-slate-700">
                      <span className="font-mono font-medium">{a.field}</span>
                      {a.reason ? <span className="text-slate-500"> — {a.reason}</span> : null}
                    </li>
                  ))}
                </ul>
              </div>
            </article>
          ))
        )}
      </div>

      {views.length > 0 ? (
        <div className="mt-4 space-y-2 border-t border-slate-100 pt-3">
          <label className="block text-xs font-medium text-slate-700" htmlFor="binding-notes">
            {t('bi.bindingSteward.notes')}
          </label>
          <textarea
            id="binding-notes"
            className="input-field min-h-[64px] text-xs"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder={t('bi.bindingSteward.notesPlaceholder')}
          />
          <button type="button" className="btn-primary text-xs" disabled={busy} onClick={() => approveMut.mutate()}>
            {approveMut.isPending ? <Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" /> : null}
            {t('bi.bindingSteward.approve')}
          </button>
        </div>
      ) : null}

      <div className="mt-5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {t('bi.bindingSteward.templateCandidates')}
        </h3>
        <p className="mt-1 text-[11px] text-slate-500">{t('bi.bindingSteward.templateHint')}</p>
        <div className="mt-2 flex flex-wrap gap-2">
          <input
            className="input-field min-w-[240px] flex-1 text-xs"
            value={proposeQ}
            onChange={(e) => setProposeQ(e.target.value)}
            placeholder={t('bi.bindingSteward.templateProposePlaceholder')}
          />
          <button
            type="button"
            className="btn-secondary text-xs"
            disabled={busy || !proposeQ.trim()}
            onClick={() => proposeTplMut.mutate()}
          >
            {proposeTplMut.isPending ? <Loader2 className="mr-1 inline h-3.5 w-3.5 animate-spin" /> : null}
            {t('bi.bindingSteward.templatePropose')}
          </button>
        </div>
        {tplPending.length > 0 ? (
          <p className="mt-2 text-[11px] text-amber-800">
            {t('bi.bindingSteward.templatePending', { count: String(tplPending.length) })}
          </p>
        ) : null}
        {tplCandidates.length === 0 ? (
          <p className="mt-2 text-xs text-slate-500">{t('bi.bindingSteward.noTemplateCandidates')}</p>
        ) : (
          <ul className="mt-2 space-y-3">
            {tplCandidates.map((c) => {
              const preview = c.preview;
              const boundMeasures = preview?.bound?.measures
                ? Object.entries(preview.bound.measures)
                : [];
              const boundEntities = preview?.bound?.entities
                ? Object.entries(preview.bound.entities)
                : [];
              const similar = preview?.similar_templates || [];
              const sample = preview?.sample_result;
              return (
                <li
                  key={c.candidate_id}
                  className="rounded-lg border border-emerald-100 bg-emerald-50/40 px-3 py-2 text-xs"
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <span className="font-mono font-medium">
                        {c.template?.template_id || c.candidate_id}
                      </span>
                      {c.question ? <p className="mt-0.5 text-slate-600">{c.question}</p> : null}
                      {c.quality?.confidence != null ? (
                        <p className="mt-0.5 text-[10px] text-slate-500">
                          conf={Number(c.quality.confidence).toFixed(2)}
                          {c.quality.repeat_count != null ? ` · n=${c.quality.repeat_count}` : ''}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-emerald-800"
                        disabled={busy}
                        onClick={() =>
                          promoteTplMut.mutate({ candidate_id: c.candidate_id, decision: 'approved' })
                        }
                      >
                        {t('bi.bindingSteward.promote')}
                      </button>
                      <button
                        type="button"
                        className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-slate-700"
                        disabled={busy}
                        onClick={() =>
                          promoteTplMut.mutate({
                            candidate_id: c.candidate_id,
                            decision: 'rejected',
                            rejection_reason: 'steward_semantic_reject',
                          })
                        }
                      >
                        {t('bi.bindingSteward.reject')}
                      </button>
                    </div>
                  </div>
                  {preview ? (
                    <div className="mt-2 space-y-1.5 border-t border-emerald-100/80 pt-2 text-[11px] text-slate-700">
                      {preview.normalized_question ? (
                        <p>
                          <span className="font-medium text-slate-500">
                            {t('bi.bindingSteward.previewNormalized')}:{' '}
                          </span>
                          {preview.normalized_question}
                        </p>
                      ) : null}
                      {boundEntities.length > 0 || boundMeasures.length > 0 ? (
                        <p>
                          <span className="font-medium text-slate-500">
                            {t('bi.bindingSteward.previewBound')}:{' '}
                          </span>
                          {boundEntities
                            .map(([id, e]) => `${id}→${e.table || '?'}`)
                            .concat(
                              boundMeasures.map(
                                ([id, m]) => `${id}→${m.entity || '?'}.${m.field || '?'}(${m.aggregation || ''})`,
                              ),
                            )
                            .join(' · ')}
                        </p>
                      ) : null}
                      {preview.date_filter != null ? (
                        <p>
                          <span className="font-medium text-slate-500">
                            {t('bi.bindingSteward.previewDateFilter')}:{' '}
                          </span>
                          <span className="font-mono">
                            {typeof preview.date_filter === 'string'
                              ? preview.date_filter
                              : JSON.stringify(preview.date_filter)}
                          </span>
                        </p>
                      ) : null}
                      {preview.binding_fingerprint ? (
                        <p>
                          <span className="font-medium text-slate-500">
                            {t('bi.bindingSteward.previewFingerprint')}:{' '}
                          </span>
                          <span className="font-mono break-all">{preview.binding_fingerprint}</span>
                        </p>
                      ) : null}
                      {preview.compiled_sql ? (
                        <pre className="max-h-28 overflow-auto rounded bg-slate-900/90 p-2 font-mono text-[10px] text-emerald-100 whitespace-pre-wrap">
                          {preview.compiled_sql}
                        </pre>
                      ) : null}
                      {sample?.ok && (sample.rows?.length || 0) > 0 ? (
                        <div>
                          <p className="font-medium text-slate-500">
                            {t('bi.bindingSteward.previewSample')}
                          </p>
                          <pre className="mt-0.5 max-h-20 overflow-auto rounded bg-white/70 p-1.5 font-mono text-[10px] text-slate-700">
                            {JSON.stringify(sample.rows?.slice(0, 3), null, 0)}
                          </pre>
                        </div>
                      ) : sample && sample.ok === false && sample.error ? (
                        <p className="text-amber-800">
                          {t('bi.bindingSteward.previewSampleUnavailable')}: {sample.error}
                        </p>
                      ) : null}
                      {similar.length > 0 ? (
                        <p>
                          <span className="font-medium text-slate-500">
                            {t('bi.bindingSteward.previewSimilar')}:{' '}
                          </span>
                          {similar
                            .map((s) => `${s.template_id}(${Number(s.score ?? 0).toFixed(2)})`)
                            .join(', ')}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
        {templatesQ.data?.metrics?.steward_rejection_rate != null ? (
          <p className="mt-2 text-[11px] text-slate-500">
            {t('bi.bindingSteward.rejectionRate', {
              rate: String(
                Math.round(Number(templatesQ.data.metrics.steward_rejection_rate) * 100),
              ),
              rejected: String(templatesQ.data.metrics.ready_rejected ?? 0),
              approved: String(templatesQ.data.metrics.ready_approved ?? 0),
            })}
          </p>
        ) : null}
      </div>

      <div className="mt-5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {t('bi.bindingSteward.graphCandidates')}
        </h3>
        {candidates.length === 0 ? (
          <p className="mt-2 text-xs text-slate-500">{t('bi.bindingSteward.noCandidates')}</p>
        ) : (
          <ul className="mt-2 space-y-2">
            {candidates.map((e) => (
              <li
                key={`${e.from}-${e.role}-${e.to}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-100 px-3 py-2 text-xs"
              >
                <span className="font-mono">
                  {e.from} —{e.role}→ {e.to}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-emerald-800"
                    disabled={busy}
                    onClick={() =>
                      promoteMut.mutate({
                        from_entity: e.from,
                        to_entity: e.to,
                        role: e.role,
                        decision: 'approved',
                      })
                    }
                  >
                    {t('bi.bindingSteward.promote')}
                  </button>
                  <button
                    type="button"
                    className="rounded-lg border border-slate-200 bg-slate-50 px-2 py-1 text-slate-700"
                    disabled={busy}
                    onClick={() =>
                      promoteMut.mutate({
                        from_entity: e.from,
                        to_entity: e.to,
                        role: e.role,
                        decision: 'rejected',
                      })
                    }
                  >
                    {t('bi.bindingSteward.reject')}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
