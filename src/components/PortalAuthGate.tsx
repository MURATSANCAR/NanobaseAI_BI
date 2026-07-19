import { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { isRunnerConfigured } from '@/api/client';
import NanobaseLogo from '@/components/NanobaseLogo';
import NvidiaInceptionBadge from '@/components/NvidiaInceptionBadge';
import { useAuth } from '@/context/AuthContext';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

const DEFAULT_USERNAME = 'admin';
const DEFAULT_PASSWORD = 'admin';

export default function PortalAuthGate() {
  const { login } = useAuth();
  const { config, refreshRuntimeConfig } = useApiConfig();
  const [username, setUsername] = useState(DEFAULT_USERNAME);
  const [password, setPassword] = useState(DEFAULT_PASSWORD);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    setPending(true);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(localizeUserMessage((err as Error).message) || t('auth.loginFailed'));
    } finally {
      setPending(false);
    }
  };

  const handleResetConnection = async () => {
    setError('');
    setPending(true);
    try {
      await refreshRuntimeConfig();
    } catch {
      setError(t('auth.invalidApiKey'));
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-gradient-to-br from-violet-100 via-white to-sky-100 px-4 py-8 pb-[max(2rem,env(safe-area-inset-bottom))] pt-[max(2rem,env(safe-area-inset-top))] sm:py-10">
      <div className="w-full max-w-md rounded-2xl border border-white/80 bg-white/70 p-5 shadow-xl backdrop-blur-xl sm:rounded-3xl sm:p-8">
        <div className="mb-5 text-center sm:mb-6">
          <div className="mx-auto mb-4 flex justify-center">
            <NanobaseLogo className="h-9 w-auto sm:h-11" />
          </div>
          <h1 className="text-lg font-bold text-violet-900 sm:text-xl">{t('auth.loginTitle')}</h1>
          <p className="mt-2 text-sm text-slate-600">{t('auth.loginSubtitle')}</p>
        </div>

        {!isRunnerConfigured(config) && (
          <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <div className="flex items-start gap-2">
              <KeyRound className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p>{t('auth.missingKey')}</p>
                <button
                  type="button"
                  className="mt-1 inline-block font-medium text-violet-700 underline disabled:opacity-50"
                  onClick={() => void handleResetConnection()}
                  disabled={pending}
                >
                  {t('auth.resetConnection')}
                </button>
              </div>
            </div>
          </div>
        )}

        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">{t('auth.username')}</label>
            <input
              className="input-field text-base sm:text-sm"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              inputMode="text"
              enterKeyHint="next"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-600">{t('auth.password')}</label>
            <input
              className="input-field text-base sm:text-sm"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              enterKeyHint="go"
              required
            />
          </div>
          {error && (
            <div className="space-y-2">
              <p className="text-sm text-status-fail">{error}</p>
              {error.includes(t('auth.invalidApiKey')) && (
                <button
                  type="button"
                  className="text-sm font-medium text-violet-700 underline"
                  onClick={handleResetConnection}
                  disabled={pending}
                >
                  {t('auth.resetConnection')}
                </button>
              )}
            </div>
          )}
          <button
            type="submit"
            className="btn-primary min-h-11 w-full"
            disabled={pending || !isRunnerConfigured(config)}
          >
            {pending ? t('common.loading') : t('auth.loginAction')}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-slate-500">{t('auth.defaultCredentials')}</p>

        <div className="mt-6 flex justify-center border-t border-slate-200/70 pt-5">
          <NvidiaInceptionBadge variant="pill" />
        </div>
      </div>
    </div>
  );
}
