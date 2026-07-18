import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Package } from 'lucide-react';
import { api, type ApiConfig } from '@/api/client';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type Props = {
  config: ApiConfig;
  onApplied?: () => void;
  onSkip?: () => void;
};

export default function BiDomainPackWizard({ config, onApplied, onSkip }: Props) {
  const qc = useQueryClient();
  const [packId, setPackId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const packs = useQuery({
    queryKey: ['bi-domain-packs'],
    queryFn: () => api.bi.domainPacks.list(config),
  });

  const preview = useQuery({
    queryKey: ['bi-domain-pack-preview', packId],
    queryFn: () => api.bi.domainPacks.preview(config, packId!),
    enabled: Boolean(packId),
  });

  const apply = useMutation({
    mutationFn: () => api.bi.domainPacks.apply(config, packId!),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-briefing'] });
      onApplied?.();
    },
    onError: (e: Error) => setError(localizeUserMessage(e.message)),
  });

  const packList = packs.data?.packs ?? [];

  return (
    <div className="bi-schema-pack-wizard rounded-2xl border-2 border-indigo-300/70 bg-gradient-to-br from-indigo-50 via-white to-violet-50 p-4 shadow-lg shadow-indigo-200/40 sm:p-5">
      <div className="mb-1 flex items-center gap-2 text-base font-semibold text-slate-900">
        <Package className="h-5 w-5 text-indigo-600" />
        {t('bi.pack.title')}
      </div>
      <p className="mb-4 text-sm text-slate-600">{t('bi.pack.subtitle')}</p>

      {packs.isLoading ? (
        <p className="text-sm text-slate-500">{t('common.loading')}</p>
      ) : null}

      {packs.isError ? (
        <p className="text-sm text-rose-600">{localizeUserMessage((packs.error as Error).message)}</p>
      ) : null}

      {!packs.isLoading && !packs.isError && packList.length === 0 ? (
        <p className="text-sm text-slate-500">{t('bi.pack.empty')}</p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {packList.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => {
              setPackId(p.id);
              setError(null);
            }}
            className={
              packId === p.id
                ? 'rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow-sm'
                : 'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:border-indigo-300 hover:bg-indigo-50'
            }
          >
            {t(p.label_key || `bi.pack.${p.id}`)}
          </button>
        ))}
      </div>

      {preview.isLoading && packId ? (
        <p className="mt-3 text-xs text-slate-500">{t('common.loading')}</p>
      ) : null}

      {preview.data ? (
        <p className="mt-3 text-xs text-slate-600">
          {t('bi.pack.preview')}: score {String((preview.data as { score?: number }).score ?? '—')}
          {(preview.data as { missing?: string[] }).missing?.length
            ? ` · ${t('bi.pack.missingTables')}: ${((preview.data as { missing?: string[] }).missing || []).join(', ')}`
            : ''}
        </p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!packId || apply.isPending}
          onClick={() => apply.mutate()}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm disabled:opacity-50"
        >
          {apply.isPending ? t('common.loading') : t('bi.pack.apply')}
        </button>
        <button
          type="button"
          onClick={() => onSkip?.() ?? onApplied?.()}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
        >
          {t('bi.pack.skip')}
        </button>
      </div>
      {error ? <p className="mt-2 text-xs text-rose-600">{error}</p> : null}
    </div>
  );
}
