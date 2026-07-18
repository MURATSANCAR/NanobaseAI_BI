import { t } from '@/i18n';

type SuiteReadiness = {
  ready?: boolean;
  max_pipeline_step?: number;
  blockers?: string[];
};

export const READINESS_CHECK_LINKS: Record<string, string> = {
  db_connection_configured: '/bi/connection',
};

export function readinessCheckLabel(code: string, ok?: boolean): string {
  if (ok === false) {
    const pendingKey = `readiness.checkPending.${code}`;
    const pending = t(pendingKey);
    if (pending !== pendingKey) return pending;
  }
  const key = `readiness.check.${code}`;
  const label = t(key);
  return label !== key ? label : code;
}

export function pipelineActionStepIndex(data?: SuiteReadiness): number {
  if (!data) return 0;
  if (data.ready) return 5;
  return typeof data.max_pipeline_step === 'number' ? data.max_pipeline_step : 0;
}

export function readinessBlocksAnalysisContinue(
  data?: SuiteReadiness,
  _options: Record<string, boolean> = {},
): boolean {
  return Boolean(data?.blockers?.length);
}

export function readinessPrimaryBlockers(data?: SuiteReadiness, limit = 3): string[] {
  if (!data?.blockers?.length) return [];
  return data.blockers.slice(0, limit);
}

export function isSuiteReadinessBlockedMessage(message: string | null | undefined): boolean {
  const msg = String(message ?? '').trim();
  if (!msg) return false;
  const localized = t('error.suiteReadinessBlocked');
  if (msg.startsWith(localized) || msg.includes(localized)) return true;
  return /suite_readiness_blocked/i.test(msg);
}
