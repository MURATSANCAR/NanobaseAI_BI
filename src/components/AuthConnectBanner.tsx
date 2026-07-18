import { Link } from 'react-router-dom';
import { KeyRound } from 'lucide-react';
import { isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';

export default function AuthConnectBanner() {
  const { config } = useApiConfig();

  if (isRunnerConfigured(config)) {
    return null;
  }

  return (
    <div className="border-b border-status-warn/30 bg-status-warn/10 px-3 py-3 sm:px-4 lg:px-6">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm text-status-warn">
          <KeyRound className="h-4 w-4 shrink-0" />
          <span>{t('auth.missingKey')}</span>
        </div>
        <Link to="/settings" className="btn-primary w-full py-2 text-xs sm:w-auto">
          {t('auth.openSettings')}
        </Link>
      </div>
    </div>
  );
}
