import clsx from 'clsx';
import { t } from '@/i18n';
import { formatStatus } from '@/utils/backendLabels';

type Tone = 'ok' | 'warn' | 'fail' | 'run' | 'neutral';

const toneMap: Record<Tone, string> = {
  ok: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  warn: 'bg-amber-50 text-amber-700 border-amber-200',
  fail: 'bg-red-50 text-red-700 border-red-200',
  run: 'bg-violet-50 text-violet-700 border-violet-200',
  neutral: 'bg-slate-50 text-slate-600 border-slate-200',
};

export function statusTone(status?: string): Tone {
  const s = (status || '').toLowerCase().trim();
  if (['ok', 'passed', 'complete', 'completed'].includes(s)) return 'ok';
  if (
    [
      'running',
      'started',
      'in_progress',
      'generating',
      'preflight',
      'pulling',
      'analyzing',
    ].includes(s)
  ) {
    return 'run';
  }
  if (['failed', 'error', 'rejected', 'blocked', 'login_blocked'].includes(s)) return 'fail';
  if (['interrupted', 'cancelled'].includes(s)) return 'warn';
  if (['queued', 'pending', 'pending_approval', 'warn', 'completed_with_failures'].includes(s)) {
    return 'warn';
  }
  return 'neutral';
}

function statusLabel(status?: string): string {
  if (!status) return t('common.noData');
  return formatStatus(status);
}

export default function StatusBadge({
  status,
  label,
}: {
  status?: string;
  label?: string;
}) {
  const tone = statusTone(status);
  const display = label || statusLabel(status);
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold',
        toneMap[tone],
      )}
    >
      {display}
    </span>
  );
}
