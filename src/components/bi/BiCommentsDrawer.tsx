import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { MessageCircle } from 'lucide-react';
import { api, type ApiConfig } from '@/api/client';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type Props = {
  config: ApiConfig;
  targetType: string;
  targetId: string;
};

export default function BiCommentsDrawer({ config, targetType, targetId }: Props) {
  const qc = useQueryClient();
  const [body, setBody] = useState('');
  const [error, setError] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ['bi-comments', targetType, targetId],
    queryFn: () => api.bi.comments.list(config, targetType, targetId),
    enabled: Boolean(targetId),
  });

  const create = useMutation({
    mutationFn: () =>
      api.bi.comments.create(config, {
        target_type: targetType,
        target_id: targetId,
        body,
      }),
    onSuccess: () => {
      setBody('');
      void qc.invalidateQueries({ queryKey: ['bi-comments', targetType, targetId] });
    },
    onError: (e: Error) => setError(localizeUserMessage(e.message)),
  });

  return (
    <aside className="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-3">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-900">
        <MessageCircle className="h-4 w-4" />
        {t('bi.comments.title')}
      </div>
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto text-xs text-slate-700">
        {(list.data?.items || []).map((c) => (
          <div key={String(c.id)} className="rounded-lg border border-slate-100 bg-slate-50 p-2">
            <p>{String(c.body || '')}</p>
            <p className="mt-1 text-[10px] text-slate-400">
              {String(c.author_user_id || 'user')} · {String(c.created_at || '')}
            </p>
          </div>
        ))}
        {!list.data?.items?.length ? (
          <p className="text-slate-400">{t('bi.comments.empty')}</p>
        ) : null}
      </div>
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={3}
        className="mt-2 w-full rounded-lg border border-slate-200 p-2 text-xs"
        placeholder={t('bi.comments.placeholder')}
      />
      <button
        type="button"
        disabled={!body.trim() || create.isPending}
        onClick={() => create.mutate()}
        className="mt-2 rounded-lg bg-slate-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
      >
        {t('bi.comments.post')}
      </button>
      {error ? <p className="mt-1 text-xs text-rose-600">{error}</p> : null}
    </aside>
  );
}
