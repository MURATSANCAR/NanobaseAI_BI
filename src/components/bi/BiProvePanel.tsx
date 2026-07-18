import { useState } from 'react';
import { Link2, Shield } from 'lucide-react';
import { api, type ApiConfig } from '@/api/client';
import { getLocale, t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';
import BiFreshnessBadge from '@/components/bi/BiFreshnessBadge';

type Props = {
  config: ApiConfig;
  answerMd?: string;
  sql?: string;
  sqlFingerprint?: string;
  provenance?: Record<string, unknown>;
  chartSpec?: Record<string, unknown>;
  maskedColumns?: string[];
  refreshedAt?: string | null;
  onShared?: (url: string) => void;
};

/** Ask → Prove → Share proof panel for chat answers. */
export default function BiProvePanel({
  config,
  answerMd = '',
  sql,
  sqlFingerprint,
  provenance,
  chartSpec,
  maskedColumns = [],
  refreshedAt,
  onShared,
}: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  async function share() {
    setBusy(true);
    setError(null);
    try {
      const artifact = await api.bi.artifacts.create(config, {
        kind: 'chat_answer',
        answer_md: answerMd,
        sql,
        sql_fingerprint: sqlFingerprint,
        chart_spec: chartSpec,
        provenance,
        locale: getLocale(),
        masked_columns: maskedColumns,
      });
      const share = await api.bi.shares.create(config, {
        resource_type: 'chat_answer',
        resource_id: artifact.artifact_id,
        ttl_hours: 72,
      });
      const token = (share as { token?: string; public_token?: string }).token
        || (share as { public_url?: string }).public_url
        || artifact.artifact_id;
      const url = typeof token === 'string' && token.startsWith('http')
        ? token
        : `${window.location.origin}/bi/public/${token}`;
      setShareUrl(url);
      onShared?.(url);
      await navigator.clipboard?.writeText(url);
    } catch (e) {
      setError(localizeUserMessage(e instanceof Error ? e.message : String(e)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white/95 p-3 text-sm shadow-sm">
      <div className="mb-2 flex flex-wrap items-center gap-2 font-medium text-slate-900">
        <Shield className="h-4 w-4 text-sky-600" />
        {t('bi.prove.title')}
        {refreshedAt ? <BiFreshnessBadge refreshedAt={refreshedAt} /> : null}
      </div>
      {sqlFingerprint ? (
        <p className="text-xs text-slate-500">
          {t('bi.prove.fingerprint')}: <code>{sqlFingerprint}</code>
        </p>
      ) : null}
      {provenance?.metric ? (
        <p className="text-xs text-slate-600">
          {String(provenance.metric)}
          {provenance.metric_version != null ? ` @v${String(provenance.metric_version)}` : ''}
          {provenance.metric_status === 'certified' ? ` · ${t('bi.semantic.certified')}` : ''}
        </p>
      ) : null}
      {maskedColumns.length > 0 ? (
        <p className="mt-1 text-xs text-amber-700">
          {t('bi.prove.maskedColumns', { count: maskedColumns.length })}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => void share()}
          className="inline-flex items-center gap-1 rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-sky-700 disabled:opacity-60"
        >
          <Link2 className="h-3.5 w-3.5" />
          {t('bi.prove.share')}
        </button>
      </div>
      {shareUrl ? (
        <p className="mt-2 break-all text-xs text-emerald-700">
          {t('bi.prove.shareCopied')}: {shareUrl}
        </p>
      ) : null}
      {error ? <p className="mt-2 text-xs text-rose-600">{error}</p> : null}
    </div>
  );
}
