import { t } from '@/i18n';

function hintFromQuestion(question: string, max = 48): string {
  const cleaned = question.replace(/\s+/g, ' ').trim();
  if (!cleaned) return '…';
  if (cleaned.length <= max) return cleaned;
  return `${cleaned.slice(0, max - 1)}…`;
}

type TipKind = 'chart' | 'metric' | 'why' | 'generic';

function classifyQuestion(question: string): TipKind {
  const q = question.toLowerCase();
  if (/\b(chart|graph|widget|dashboard|grafik|widget|pano|görsel)\b/i.test(q)) return 'chart';
  if (/\b(why|neden|sebep|sapma|variance|karşılaştır|compare)\b/i.test(q)) return 'why';
  if (/\b(kaç|toplam|sum|count|ortalama|average|metric|kpi|oran|rate)\b/i.test(q)) return 'metric';
  return 'generic';
}

/**
 * Ordered, user-facing progress steps while the assistant works.
 * Never expose technical internals (SQL, schema engines, etc.).
 */
export function progressTipsForQuestion(question: string): string[] {
  const hint = hintFromQuestion(question);
  const kind = classifyQuestion(question);
  const steps = [
    t('bi.chat.progressTip.understand', { hint }),
    t('bi.chat.progressTip.schema'),
    t('bi.chat.progressTip.plan', { hint }),
    t('bi.chat.progressTip.run'),
    t('bi.chat.progressTip.compose'),
  ];
  if (kind === 'chart') {
    return [t('bi.chat.progressTip.chart'), ...steps];
  }
  if (kind === 'why') {
    return [t('bi.chat.progressTip.why', { hint }), ...steps];
  }
  if (kind === 'metric') {
    return [t('bi.chat.progressTip.metric', { hint }), ...steps];
  }
  return steps;
}

/** Map backend phases to a friendly step index (never expose phase names). */
export function tipIndexForStreamPhase(phase: string | undefined, total: number): number | null {
  if (!phase || total <= 0) return null;
  const order = [
    'queued',
    'preparing',
    'thinking',
    'reading_schema',
    'planning',
    'generating_sql',
    'querying',
    'building',
    'composing',
    'finalizing',
  ];
  const idx = order.indexOf(phase);
  if (idx < 0) return null;
  // Skip queued (handled separately); spread remaining across steps.
  if (phase === 'queued') return 0;
  const workIdx = Math.max(0, idx - 1);
  const maxWork = Math.max(1, order.length - 2);
  return Math.min(total - 1, Math.round((workIdx / maxWork) * (total - 1)));
}

/** How far through the step list we are (does not wrap backward). */
export function streamingStepProgress(tipIndex: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(total - 1, Math.max(0, tipIndex));
}
