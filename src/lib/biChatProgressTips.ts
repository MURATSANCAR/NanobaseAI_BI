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
 * Many small steps keep long analyses from feeling frozen.
 * Never expose technical internals (SQL, schema engines, etc.).
 */
export function progressTipsForQuestion(question: string): string[] {
  const hint = hintFromQuestion(question);
  const kind = classifyQuestion(question);
  const core = [
    t('bi.chat.progressTip.understand', { hint }),
    t('bi.chat.progressTip.intent'),
    t('bi.chat.progressTip.schema'),
    t('bi.chat.progressTip.relate'),
    t('bi.chat.progressTip.plan', { hint }),
    t('bi.chat.progressTip.analyze'),
    t('bi.chat.progressTip.sql'),
    t('bi.chat.progressTip.refine'),
    t('bi.chat.progressTip.validate'),
    t('bi.chat.progressTip.run'),
    t('bi.chat.progressTip.verify'),
    t('bi.chat.progressTip.compose'),
    t('bi.chat.progressTip.polish'),
    t('bi.chat.progressTip.wait', { hint }),
    t('bi.chat.progressTip.almost'),
  ];
  if (kind === 'chart') {
    return [t('bi.chat.progressTip.chart'), ...core];
  }
  if (kind === 'why') {
    return [t('bi.chat.progressTip.why', { hint }), ...core];
  }
  if (kind === 'metric') {
    return [t('bi.chat.progressTip.metric', { hint }), ...core];
  }
  return core;
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
    'scenario_hit',
  ];
  const idx = order.indexOf(phase);
  if (idx < 0) return null;
  if (phase === 'queued') return 0;
  // Stretch long-running middle phases across more of the checklist.
  const phaseTarget: Record<string, number> = {
    preparing: 0.05,
    thinking: 0.12,
    reading_schema: 0.22,
    planning: 0.35,
    generating_sql: 0.55,
    scenario_hit: 0.45,
    querying: 0.72,
    building: 0.82,
    composing: 0.9,
    finalizing: 0.97,
  };
  const ratio = phaseTarget[phase];
  if (typeof ratio === 'number') {
    return Math.min(total - 1, Math.max(0, Math.round(ratio * (total - 1))));
  }
  const workIdx = Math.max(0, idx - 1);
  const maxWork = Math.max(1, order.length - 2);
  return Math.min(total - 1, Math.round((workIdx / maxWork) * (total - 1)));
}

/** How far through the step list we are (does not wrap backward). */
export function streamingStepProgress(tipIndex: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(total - 1, Math.max(0, tipIndex));
}

/** Accent palette for step dots / chips (cycles). */
export const STREAMING_STEP_COLORS = [
  { dot: 'bg-sky-500', ring: 'ring-sky-300', text: 'text-sky-800', soft: 'bg-sky-50' },
  { dot: 'bg-teal-500', ring: 'ring-teal-300', text: 'text-teal-800', soft: 'bg-teal-50' },
  { dot: 'bg-amber-500', ring: 'ring-amber-300', text: 'text-amber-900', soft: 'bg-amber-50' },
  { dot: 'bg-violet-500', ring: 'ring-violet-300', text: 'text-violet-900', soft: 'bg-violet-50' },
  { dot: 'bg-rose-500', ring: 'ring-rose-300', text: 'text-rose-800', soft: 'bg-rose-50' },
  { dot: 'bg-emerald-500', ring: 'ring-emerald-300', text: 'text-emerald-800', soft: 'bg-emerald-50' },
] as const;
