import { useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, Link2, MessageSquare, Sparkles, X } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { api, type ApiConfig } from '@/api/client';
import type { BiStatus } from '@/api/types';
import { t } from '@/i18n';

const STORAGE_KEY = 'nanobase_bi_first_tour_v1';
const SHARE_STEP_KEY = 'nanobase_bi_first_tour_share_v1';

/** Steps live on the sources / connection flow screen. */
export const BI_FIRST_VALUE_ROUTE = '/bi/sources';

type Props = {
  config: ApiConfig;
  status?: BiStatus;
  /** `cue` = blinking chip. `panel` = full step actions. */
  variant?: 'cue' | 'panel';
  onAskDemo?: (prompt: string) => void;
};

function readDismissed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function writeDismissed(): void {
  try {
    localStorage.setItem(STORAGE_KEY, '1');
  } catch {
    /* ignore */
  }
}

function readShareDone(): boolean {
  try {
    return localStorage.getItem(SHARE_STEP_KEY) === '1';
  } catch {
    return false;
  }
}

function writeShareDone(): void {
  try {
    localStorage.setItem(SHARE_STEP_KEY, '1');
  } catch {
    /* ignore */
  }
}

function useTourState(status?: BiStatus) {
  const [dismissed, setDismissed] = useState(readDismissed);
  const [shareDone, setShareDone] = useState(readShareDone);

  const connOk = Boolean(status?.connection?.ok);
  const schemaOk = Boolean(status?.schema_cached);
  const analyticsOk = Boolean(status?.capabilities?.analytics ?? status?.engine_mode === 'superset');

  const step = useMemo(() => {
    if (!connOk) return 1;
    if (!schemaOk) return 2;
    if (!analyticsOk) return 3;
    if (!shareDone) return 4;
    return 0;
  }, [connOk, schemaOk, analyticsOk, shareDone]);

  const dismiss = () => {
    writeDismissed();
    setDismissed(true);
  };

  const completeShare = () => {
    writeShareDone();
    setShareDone(true);
  };

  return { dismissed, dismiss, completeShare, connOk, schemaOk, analyticsOk, shareDone, step };
}

export default function BiFirstValueTour({
  config,
  status,
  variant = 'panel',
  onAskDemo,
}: Props) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const tour = useTourState(status);

  if (tour.dismissed || tour.step === 0) return null;

  if (variant === 'cue') {
    return (
      <button
        type="button"
        className="bi-first-value-cue"
        onClick={() => navigate(`${BI_FIRST_VALUE_ROUTE}?tour=1`)}
        title={t('bi.wow.tourSubtitle')}
        aria-label={t('bi.wow.tourCueAria')}
      >
        <span className="bi-first-value-cue-glow" aria-hidden />
        <span className="bi-first-value-cue-dot" aria-hidden />
        <Sparkles className="bi-first-value-cue-icon" aria-hidden />
        <span className="bi-first-value-cue-copy">
          <span className="bi-first-value-cue-title">{t('bi.wow.tourCue')}</span>
          <span className="bi-first-value-cue-meta">
            {t('bi.wow.tourCueStep', { step: String(tour.step) })}
          </span>
        </span>
      </button>
    );
  }

  const { connOk, schemaOk, analyticsOk, shareDone, step, dismiss, completeShare } = tour;

  return (
    <section
      id="bi-first-value"
      className="relative overflow-hidden rounded-2xl border border-sky-300/60 bg-gradient-to-br from-sky-600 via-sky-600 to-teal-600 p-4 text-white shadow-lg sm:p-5"
    >
      <button
        type="button"
        className="absolute right-3 top-3 rounded-full bg-white/15 p-1 hover:bg-white/25"
        onClick={dismiss}
        aria-label={t('common.close')}
      >
        <X className="h-4 w-4" />
      </button>
      <h3 className="mb-1 flex items-center gap-2 text-base font-semibold">
        <Sparkles className="h-5 w-5" />
        {t('bi.wow.tourTitle')}
      </h3>
      <p className="mb-4 max-w-2xl text-sm text-white/90">{t('bi.wow.tourSubtitle')}</p>

      <ol className="mb-4 grid gap-2 sm:grid-cols-4">
        {[1, 2, 3, 4].map((n) => {
          const done =
            (n === 1 && connOk) ||
            (n === 2 && schemaOk) ||
            (n === 3 && analyticsOk) ||
            (n === 4 && shareDone);
          const active = step === n;
          return (
            <li
              key={n}
              className={`rounded-xl border px-3 py-2 text-sm ${
                active ? 'border-white bg-white/20' : 'border-white/20 bg-white/5'
              }`}
            >
              <span className="mb-1 flex items-center gap-2 font-medium">
                {done ? <CheckCircle2 className="h-4 w-4 text-emerald-200" /> : <span className="text-white/80">{n}</span>}
                {t(`bi.wow.tourStep${n}`)}
              </span>
            </li>
          );
        })}
      </ol>

      <div className="flex flex-wrap gap-2">
        {step === 1 && (
          <Link
            to="/bi/sources"
            className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-sky-800"
          >
            {t('bi.wow.tourConnectCta')}
          </Link>
        )}
        {step === 2 && (
          <>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-sky-800"
              onClick={() =>
                void api.bi.refreshSchema(config).then(() => {
                  void qc.invalidateQueries({ queryKey: ['bi-status'] });
                  void qc.invalidateQueries({ queryKey: ['bi-schema'] });
                  void qc.invalidateQueries({ queryKey: ['bi-schema-graph'] });
                })
              }
            >
              {t('bi.refreshSchema')}
            </button>
            <Link
              to="/bi/schema"
              className="inline-flex items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-white ring-1 ring-white/40"
            >
              {t('bi.schemaOpenCta')}
            </Link>
          </>
        )}
        {step === 3 && (
          <>
            <Link
              to="/bi"
              className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-sky-800"
            >
              {t('bi.analytics.openPanel')}
            </Link>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-white ring-1 ring-white/40"
              onClick={() => onAskDemo?.(t('bi.wow.demoAskClaims'))}
            >
              <MessageSquare className="h-4 w-4" />
              {t('bi.wow.tourAskCta')}
            </button>
          </>
        )}
        {step === 4 && (
          <>
            <Link
              to="/bi?chat=1"
              className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-sky-800"
              onClick={completeShare}
            >
              <MessageSquare className="h-4 w-4" />
              {t('bi.wow.tourProveCta')}
            </Link>
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-full bg-white/15 px-4 py-2 text-sm font-semibold text-white ring-1 ring-white/40"
              onClick={() => {
                void navigator.clipboard?.writeText(`${window.location.origin}/bi`);
                completeShare();
              }}
            >
              <Link2 className="h-4 w-4" />
              {t('bi.wow.tourShareCta')}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
