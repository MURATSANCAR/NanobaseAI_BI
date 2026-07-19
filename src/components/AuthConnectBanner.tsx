import { useState } from 'react';
import { KeyRound, RefreshCw } from 'lucide-react';
import { isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';

export default function AuthConnectBanner() {
  const { config, refreshRuntimeConfig } = useApiConfig();
  const [pending, setPending] = useState(false);

  if (isRunnerConfigured(config)) {
    return null;
  }

  const handleRetry = async () => {
    setPending(true);
    try {
      await refreshRuntimeConfig();
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="border-b border-status-warn/30 bg-status-warn/10 px-3 py-3 sm:px-4 lg:px-6">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm text-status-warn">
          <KeyRound className="h-4 w-4 shrink-0" />
          <span>{t('auth.missingKey')}</span>
        </div>
        <button
          type="button"
          className="btn-primary inline-flex w-full items-center justify-center gap-2 py-2 text-xs sm:w-auto"
          onClick={() => void handleRetry()}
          disabled={pending}
        >
          <RefreshCw className={`h-3.5 w-3.5 ${pending ? 'animate-spin' : ''}`} />
          {pending ? t('common.loading') : t('auth.resetConnection')}
        </button>
      </div>
    </div>
  );
}
