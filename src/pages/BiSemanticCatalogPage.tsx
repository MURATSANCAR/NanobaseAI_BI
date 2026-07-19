import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import ApiErrorBanner from '@/components/ApiErrorBanner';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useAuth } from '@/context/AuthContext';
import { getFeatureFlags } from '@/config/environment';
import { Navigate } from 'react-router-dom';

export default function BiSemanticCatalogPage() {
  const flags = getFeatureFlags();
  const { config } = useApiConfig();
  const { canBi } = useAuth();
  const qc = useQueryClient();
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [reviewRole, setReviewRole] = useState<'BUSINESS_REVIEWER' | 'TECHNICAL_REVIEWER'>(
    'BUSINESS_REVIEWER',
  );
  const canReview = canBi('semantic.review');
  const canPublish = canBi('semantic.publish');

  if (!flags.enableSemanticCatalog) {
    return <Navigate to="/bi/glossary" replace />;
  }

  const statusQ = useQuery({
    queryKey: ['bi-catalog-gov-status', config],
    queryFn: () => api.bi.catalogGov.status(config),
    enabled: isRunnerConfigured(config),
  });
  const metricsQ = useQuery({
    queryKey: ['bi-catalog-gov-metrics', config],
    queryFn: () => api.bi.catalogGov.metrics(config),
    enabled: isRunnerConfigured(config),
  });
  const promosQ = useQuery({
    queryKey: ['bi-catalog-gov-promos', config],
    queryFn: () => api.bi.catalogGov.promotions(config),
    enabled: isRunnerConfigured(config),
  });
  const versionsQ = useQuery({
    queryKey: ['bi-catalog-gov-versions', config],
    queryFn: () => api.bi.catalogGov.versions(config),
    enabled: isRunnerConfigured(config),
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['bi-catalog-gov'] });
    void statusQ.refetch();
    void metricsQ.refetch();
    void promosQ.refetch();
    void versionsQ.refetch();
  };

  const bootstrapMut = useMutation({
    mutationFn: () => api.bi.catalogGov.bootstrapSlice(config, { datasourceId: 'default' }),
    onSuccess: (r) => {
      setMsg(`Slice seeded: metric=${r.metric_id}`);
      setErr(null);
      invalidate();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const validateMut = useMutation({
    mutationFn: (metricId: string) => api.bi.catalogGov.validateMetric(config, metricId),
    onSuccess: (r) => {
      setMsg(`Validate: ${JSON.stringify(r).slice(0, 200)}`);
      invalidate();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const submitMut = useMutation({
    mutationFn: (metricId: string) => api.bi.catalogGov.submitReview(config, metricId),
    onSuccess: () => {
      setMsg('Promotion request opened');
      invalidate();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const reviewMut = useMutation({
    mutationFn: (promotionId: string) =>
      api.bi.catalogGov.review(config, promotionId, {
        decision: 'APPROVE',
        role: reviewRole,
        comment: 'UI review',
      }),
    onSuccess: () => {
      setMsg(`Reviewed as ${reviewRole}`);
      invalidate();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const publishMut = useMutation({
    mutationFn: (promotionId: string) =>
      api.bi.catalogGov.publish(config, promotionId, { semanticVersion: '7.0.0' }),
    onSuccess: (r) => {
      setMsg(`Published: ${JSON.stringify(r).slice(0, 240)}`);
      invalidate();
    },
    onError: (e: Error) => setErr(e.message),
  });

  const compileMut = useMutation({
    mutationFn: () =>
      api.bi.catalogGov.compile(config, {
        metric: 'unpaid_invoice_amount',
        period: { from: '2026-01-01', to: '2027-01-01' },
      }),
    onSuccess: (r) => {
      setMsg(r.sql || JSON.stringify(r));
      setErr(null);
    },
    onError: (e: Error) => setErr(e.message),
  });

  const metrics = metricsQ.data?.metrics || [];
  const promos = promosQ.data?.promotionRequests || [];
  const versions = versionsQ.data?.versions || [];

  return (
    <PageShell title="Semantic Catalog (Governance)" subtitle="Faz 7 — metric governance, dual review, versioning">
      {(err || statusQ.error) && (
        <ApiErrorBanner error={(err || String(statusQ.error)) as string} />
      )}
      {msg && (
        <pre className="mb-4 max-h-40 overflow-auto rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">
          {msg}
        </pre>
      )}

      <div className="mb-6 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded bg-slate-900 px-3 py-2 text-sm text-white"
          onClick={() => bootstrapMut.mutate()}
        >
          Seed unpaid_invoice_amount slice
        </button>
        <button
          type="button"
          className="rounded border border-slate-300 px-3 py-2 text-sm"
          onClick={() => compileMut.mutate()}
        >
          Compile metric SQL
        </button>
        <label className="flex items-center gap-2 text-sm text-slate-600">
          Review role
          <select
            className="rounded border border-slate-300 px-2 py-1"
            value={reviewRole}
            onChange={(e) => setReviewRole(e.target.value as typeof reviewRole)}
          >
            <option value="BUSINESS_REVIEWER">Business</option>
            <option value="TECHNICAL_REVIEWER">Technical</option>
          </select>
        </label>
      </div>

      <section className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Status</h2>
        <pre className="rounded border border-slate-200 bg-white p-3 text-xs">
          {JSON.stringify(statusQ.data || {}, null, 2)}
        </pre>
      </section>

      <section className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">Metrics</h2>
        {metrics.length === 0 ? (
          <EmptyState title="No metrics" description="Seed the unpaid invoice vertical slice to begin." />
        ) : (
          <ul className="space-y-2">
            {metrics.map((m) => (
              <li
                key={String(m.id)}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-200 bg-white p-3"
              >
                <div>
                  <div className="font-medium">{String(m.code)}</div>
                  <div className="text-xs text-slate-500">
                    {String(m.status)} · v{String(m.version)} · {String(m.name)}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="rounded border px-2 py-1 text-xs"
                    onClick={() => validateMut.mutate(String(m.id))}
                  >
                    Validate
                  </button>
                  <button
                    type="button"
                    className="rounded border px-2 py-1 text-xs"
                    onClick={() => submitMut.mutate(String(m.id))}
                  >
                    Submit review
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Promotion queue
        </h2>
        {promos.length === 0 ? (
          <EmptyState title="No promotions" description="Validate a metric and submit for review." />
        ) : (
          <ul className="space-y-2">
            {promos.map((p) => (
              <li
                key={String(p.id)}
                className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-200 bg-white p-3"
              >
                <div className="text-sm">
                  <div className="font-medium">{String(p.id)}</div>
                  <div className="text-xs text-slate-500">
                    {String(p.phase)} · {String(p.assetType)} · dual={String(p.requiresDualApproval)}
                  </div>
                </div>
                <div className="flex gap-2">
                  {canReview ? (
                    <button
                      type="button"
                      className="rounded border px-2 py-1 text-xs"
                      onClick={() => reviewMut.mutate(String(p.id))}
                    >
                      Approve ({reviewRole})
                    </button>
                  ) : null}
                  {canPublish ? (
                    <button
                      type="button"
                      className="rounded bg-emerald-700 px-2 py-1 text-xs text-white"
                      onClick={() => publishMut.mutate(String(p.id))}
                    >
                      Publish
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-500">
          Semantic versions
        </h2>
        <pre className="rounded border border-slate-200 bg-white p-3 text-xs">
          {JSON.stringify({ active: versionsQ.data?.active, versions }, null, 2)}
        </pre>
      </section>
    </PageShell>
  );
}
