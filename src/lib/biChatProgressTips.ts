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
 * Fixed checklist aligned to real stream phases.
 * Steps only advance when the backend phase changes — never by a fake timer.
 */
export function progressTipsForQuestion(question: string): string[] {
  const hint = hintFromQuestion(question);
  const kind = classifyQuestion(question);
  const core = [
    t('bi.chat.progressTip.understand', { hint }), // 0 preparing / thinking
    t('bi.chat.progressTip.schema'), // 1 schema_retrieval
    t('bi.chat.progressTip.plan', { hint }), // 2 planning / plan_ready
    t('bi.chat.progressTip.sql'), // 3 generating_sql
    t('bi.chat.progressTip.validate'), // 4 validating / repairing
    t('bi.chat.progressTip.run'), // 5 executing / querying
    t('bi.chat.progressTip.compose'), // 6 generating_answer
    t('bi.chat.progressTip.almost'), // 7 finalizing
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

/**
 * Map backend status phase → checklist index.
 * Returns null when the phase should not move the tip (unknown / skip noise).
 */
export function tipIndexForStreamPhase(phase: string | undefined, total: number): number | null {
  if (!phase || total <= 0) return null;

  // Core indices assume the 8-step base list; kind-prefix shifts by +1 when present.
  const prefix = total > 8 ? 1 : 0;
  const at = (coreIdx: number) => Math.min(total - 1, prefix + coreIdx);

  const map: Record<string, number> = {
    queued: 0,
    preparing: at(0),
    thinking: at(0),
    user_guidance: at(0),

    schema_retrieval: at(1),
    schema_retrieval_done: at(1),
    reading_schema: at(1),
    schema_expand: at(1),

    planning: at(2),
    plan_ready: at(2),
    semantic_shadow: at(2),
    semantic_metric_hit: at(2),
    verified_cache_hit: at(2),
    learned_cache_hit: at(2),

    generating_sql: at(3),
    scenario_hit: at(3),
    prepared_sql_hit: at(3),
    sql_generated: at(3),

    validating: at(4),
    validated: at(4),
    repairing_sql: at(4),
    sql_repaired: at(4),
    sql_shape_guard: at(4),

    executing: at(5),
    execute_retry: at(5),
    querying: at(5),
    gateway_explain: at(5),
    building: at(5),

    generating_answer: at(6),
    composing: at(6),

    finalizing: at(7),
  };

  if (phase in map) return map[phase]!;
  return null;
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
