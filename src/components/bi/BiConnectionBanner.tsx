import { AlertTriangle } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { BiStatus } from '@/api/types';
import { t } from '@/i18n';
import { formatBiCode, localizeUserMessage } from '@/utils/backendLabels';

type Props = {
  status?: BiStatus & { warnings?: Array<{ code: string; message: string }> };
};

export default function BiConnectionBanner({ status }: Props) {
  const warnings = status?.warnings ?? [];
  const connOk = status?.connection?.ok;

  if (connOk && warnings.length === 0) return null;

  return (
    <div className="card-static flex flex-col gap-2 border-amber-300/60 bg-amber-50/90 p-4 text-sm text-amber-950">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div className="flex-1">
          <p className="font-semibold">{t('bi.connectionBannerTitle')}</p>
          {!connOk && (
            <p className="mt-1 text-amber-900">
              {localizeUserMessage(status?.connection?.message) || t('bi.notConnected')}
            </p>
          )}
          {warnings.map((w) => (
            <p key={w.code} className="mt-1 text-amber-900">
              {localizeUserMessage(w.message) || formatBiCode(w.code)}
            </p>
          ))}
          <div className="mt-2 flex flex-wrap gap-3">
            <Link to="/bi/connection" className="inline-flex items-center gap-1 text-violet-700 hover:underline">
              {t('nav.biConnection')} →
            </Link>
            <span className="text-amber-900">{t('bi.connectionAutoRepairHint')}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
