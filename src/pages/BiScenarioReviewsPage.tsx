import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Loader2, X } from 'lucide-react';
import { useState } from 'react';
import { PageShell } from '@/components/PageShell';
import ApiErrorBanner from '@/components/ApiErrorBanner';
import EmptyState from '@/components/EmptyState';
import { useApiConfig } from '@/context/ApiContext';
import { request } from '@/api/http';
type ReviewItem = {
  scenarioId: string;
  scenarioCode: string;
  family: string;
  riskTier: string;
  canonicalQuestion: string;
  status: string;
};

export default function BiScenarioReviewsPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const [datasourceId, setDatasourceId] = useState('bi_reporting');
  const [err, setErr] = useState<Error | null>(null);

  const reviewsQ = useQuery({
    queryKey: ['scenario-reviews', datasourceId, config],
    queryFn: async () => {
      const raw = await request<{ items?: ReviewItem[] }>(
        config,
        `/api/v1/query-scenarios/reviews?datasource_id=${encodeURIComponent(datasourceId)}`,
      );
      return raw.items ?? [];
    },
  });

  const reviewMut = useMutation({
    mutationFn: async ({ id, decision }: { id: string; decision: 'APPROVE' | 'REJECT' }) =>
      request(config, `/api/v1/query-scenarios/${encodeURIComponent(id)}/review`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      }),
    onSuccess: () => {
      setErr(null);
      void qc.invalidateQueries({ queryKey: ['scenario-reviews'] });
    },
    onError: (e: Error) => setErr(e),
  });

  const items = reviewsQ.data ?? [];

  return (
    <PageShell pageId="biSemanticCatalog" titleKey="nav.biScenarioReviews" subtitleKey="nav.hint.biScenarioReviews">
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm text-slate-600">
          Datasource
          <input
            className="mt-1 block w-56 rounded-md border border-slate-200 px-3 py-1.5 text-sm"
            value={datasourceId}
            onChange={(e) => setDatasourceId(e.target.value)}
          />
        </label>
      </div>
      <ApiErrorBanner error={err} />
      {reviewsQ.isLoading ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Yükleniyor…
        </div>
      ) : null}
      {!reviewsQ.isLoading && items.length === 0 ? (
        <EmptyState titleKey="bi.empty.noScenarioReviews" descriptionKey="bi.empty.noScenarioReviewsDesc" />
      ) : null}
      <ul className="space-y-3">
        {items.map((item) => (
          <li
            key={item.scenarioId}
            className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 py-3"
          >
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-slate-800">{item.canonicalQuestion}</div>
              <div className="mt-0.5 text-xs text-slate-500">
                {item.scenarioCode} · {item.family} · Tier {item.riskTier}
              </div>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1.5 text-xs font-medium text-white"
                disabled={reviewMut.isPending}
                onClick={() => reviewMut.mutate({ id: item.scenarioId, decision: 'APPROVE' })}
              >
                <Check className="h-3.5 w-3.5" /> Onayla
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-md bg-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-800"
                disabled={reviewMut.isPending}
                onClick={() => reviewMut.mutate({ id: item.scenarioId, decision: 'REJECT' })}
              >
                <X className="h-3.5 w-3.5" /> Reddet
              </button>
            </div>
          </li>
        ))}
      </ul>
    </PageShell>
  );
}
