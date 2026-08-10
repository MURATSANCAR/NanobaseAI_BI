import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  BarChart3,
  Bell,
  BellOff,
  Bot,
  CalendarClock,
  FileBarChart,
  LayoutDashboard,
  Loader2,
  MessageSquareText,
  Minus,
  RotateCcw,
  Search,
  Send,
  Sparkles,
  Square,
  Check,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  User,
} from 'lucide-react';
import clsx from 'clsx';
import { api, isRunnerConfigured, type ApiConfig } from '@/api/client';
import { submitQueryFeedback } from '@/api/services';
import { getFeatureFlags } from '@/config/environment';
import type { ChatExecutionState } from '@/api/contracts/datasource';
import { useApiConfig } from '@/context/ApiContext';
import { useAuth } from '@/context/AuthContext';
import { t } from '@/i18n';
import { brandText } from '@/utils/brand';
import { stripSqlFromChatText } from '@/utils/biChatSanitize';
import { mapPhaseToChatState } from '@/lib/biChatStream';
import { localizeUserMessage } from '@/utils/backendLabels';
import {
  abortBiChatJob,
  biChatJobCount,
  getBiChatJobsSettled,
  isBiChatJobPending,
  runBiChatJob,
} from '@/lib/biChatRunner';
import {
  progressTipsForQuestion,
  STREAMING_STEP_COLORS,
  streamingStepProgress,
  tipIndexForStreamPhase,
} from '@/lib/biChatProgressTips';
import { ensureChatWidgets } from '@/lib/biChatWidgets';
import {
  ensureNotifyPermission,
  getNotifyPermission,
  showWebNotification,
  type NotifyPermission,
} from '@/lib/webNotifications';
import {
  ALERT_CREATE_INTENT,
  stripAlertCreateHint,
  withAlertCreateHint,
} from '@/lib/alertChatIntent';
import { BiAnswerBlocks } from '@/components/BiWidgets';
import BiChatWidgetPreview from '@/components/bi/BiChatWidgetPreview';
import BiPinToDashboardControl from '@/components/bi/BiPinToDashboardControl';
import BiChatResultHero, { isChatKpiAnswer, isHeroScalarResult } from '@/components/bi/BiChatResultHero';
import BiExportMenu from '@/components/bi/BiExportMenu';
import BiLineageDrawer from '@/components/bi/BiLineageDrawer';
import BiScenarioSliders from '@/components/bi/BiScenarioSliders';
import BiQueryTemplateGrid from '@/components/bi/BiQueryTemplateGrid';
import BiVoiceInput from '@/components/bi/BiVoiceInput';
import type { BiChatResponse, BiQueryTemplate } from '@/api/types';
import { getTemplateWarm, warmTemplatesInBackground } from '@/lib/biTemplateWarm';

type ChatMessage = {
  /** Stable identity for list rendering (uuid, or `${sessionId}-idx-N` for hydrated history). */
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** User question this assistant answer belongs to — stored at creation so
   *  rows never back-scan the timeline per render. */
  questionTitle?: string;
  meta?: BiChatResponse;
  failed?: boolean;
  streaming?: boolean;
  /** Ties an assistant placeholder to an in-flight/queued job. */
  jobId?: string;
  streamPhase?: string;
  queuePosition?: number;
  queueMessage?: string;
  elapsedSec?: number;
  /** True once live tokens arrived — skip fake reveal on done. */
  liveTokens?: boolean;
  chatState?: ChatExecutionState;
  draftSql?: string;
  draftTables?: string[];
  draftColumns?: string[];
  draftAssumptions?: string[];
  draftWarnings?: string[];
  draftDialect?: string;
  draftConfidence?: number;
  executionMode?: string;
  feedbackRating?: -1 | 0 | 1;
  /** Precompiled scenario route badge */
  scenarioSource?: boolean;
  scenarioCode?: string;
  followUps?: string[];
};

type FeedbackDraft = {
  msgKey: string;
  rating: -1 | 0 | 1;
  comment: string;
};

function newMessageId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    /* fall through */
  }
  return `m-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

const messagePinKey = (msg: ChatMessage) =>
  msg.jobId || `${msg.role}-${(msg.meta?.sql || msg.content || '').slice(0, 48)}`;

const msgFeedbackKey = (m: ChatMessage, index: number) => m.jobId || `idx-${index}`;

function mapHistoryMessages(raw: unknown[], sessionId: string): ChatMessage[] {
  let lastUserContent: string | undefined;
  return raw.map((m, index) => {
    const msg = m as { role: string; content: string; meta?: BiChatResponse };
    const role = msg.role === 'user' ? 'user' : 'assistant';
    const content = role === 'user' ? stripAlertCreateHint(msg.content) : msg.content;
    const questionTitle = role === 'assistant' ? lastUserContent : undefined;
    if (role === 'user') lastUserContent = content;
    return {
      // Stable across refetches so React reuses row DOM/state.
      id: `${sessionId}-idx-${index}`,
      role,
      content,
      meta: msg.meta,
      questionTitle,
    };
  });
}

function ensureStreamingBubble(prev: ChatMessage[], jobId?: string): ChatMessage[] {
  if (jobId) {
    if (prev.some((m) => m.jobId === jobId && m.streaming)) return prev;
  } else if (prev.some((m) => m.streaming)) {
    return prev;
  }
  const last = prev[prev.length - 1];
  if (last?.role === 'user') {
    return [
      ...prev,
      {
        id: jobId ? `job-${jobId}` : newMessageId(),
        role: 'assistant',
        content: '',
        streaming: true,
        jobId,
        streamPhase: 'thinking',
        questionTitle: last.content,
      },
    ];
  }
  return prev;
}

function applyAssistantResult(
  prev: ChatMessage[],
  result: BiChatResponse,
  jobId?: string,
): ChatMessage[] {
  const normalized = ensureChatWidgets(result);
  const content = localizeUserMessage(normalized.reply || '');
  const next = [...prev];
  const idx = jobId
    ? next.findIndex((m) => m.jobId === jobId && m.role === 'assistant')
    : next.findIndex((m) => m.streaming);
  if (idx >= 0) {
    const prevMsg = next[idx]!;
    const prov = normalized.provenance;
    const plan = normalized.workflows?.plan;
    next[idx] = {
      id: prevMsg.id,
      role: 'assistant',
      content,
      meta: normalized,
      jobId,
      questionTitle: prevMsg.questionTitle,
      draftSql: normalized.sql || prevMsg.draftSql,
      draftTables: prov?.selected_tables || plan?.tables || prevMsg.draftTables,
      draftColumns: prov?.columns || plan?.columns || prevMsg.draftColumns,
      draftAssumptions: prov?.assumptions || plan?.assumptions || prevMsg.draftAssumptions,
      draftWarnings: prov?.warnings || normalized.warnings || plan?.warnings || prevMsg.draftWarnings,
      draftDialect: prov?.dialect || plan?.dialect || prevMsg.draftDialect,
      draftConfidence:
        prov?.confidence ?? plan?.confidence ?? prevMsg.draftConfidence,
      chatState: 'COMPLETED',
      executionMode:
        normalized.execution_mode || prov?.execution_mode || prevMsg.executionMode,
      scenarioSource: prevMsg.scenarioSource,
      scenarioCode: prevMsg.scenarioCode,
      followUps: prevMsg.followUps,
    };
    return next;
  }
  return [
    ...next,
    { id: newMessageId(), role: 'assistant', content, meta: normalized, chatState: 'COMPLETED' },
  ];
}

function statusLabelForMessage(m: ChatMessage): string {
  const phase = m.streamPhase || 'thinking';
  if (phase === 'queued') {
    if (m.queueMessage && m.queueMessage.trim()) return m.queueMessage;
    const pos = Math.max(1, m.queuePosition ?? 1);
    return t('bi.streamingQueued', { position: String(pos) });
  }
  // Friendly operator copy only — never surface SQL / engine internals.
  const phaseKey: Record<string, string> = {
    preparing: 'bi.streamingPreparing',
    reading_schema: 'bi.streamingReadingSchema',
    planning: 'bi.streamingPlanning',
    generating_sql: 'bi.streamingWorkingOnAnswer',
    composing: 'bi.streamingComposing',
    thinking: 'bi.streamingThinking',
    querying: 'bi.streamingQuerying',
    building: 'bi.streamingBuilding',
    finalizing: 'bi.streamingFinalizing',
    scenario_hit: 'bi.streamingWorkingOnAnswer',
  };
  const key = phaseKey[phase] || 'bi.streamingThinking';
  return t(key);
}

function BiChatStreamingSteps({
  question,
  tipIndex,
  phase,
  queuePosition,
  queueMessage,
  elapsedSec,
}: {
  question: string;
  tipIndex: number;
  phase?: string;
  queuePosition?: number;
  queueMessage?: string;
  elapsedSec?: number;
}) {
  const steps = progressTipsForQuestion(question);
  const active = streamingStepProgress(tipIndex, steps.length);
  const queued = phase === 'queued';
  const label = queued
    ? queueMessage?.trim() ||
      t('bi.streamingQueued', { position: String(Math.max(1, queuePosition ?? 1)) })
    : steps[active] || t('bi.streamingThinking');
  const accent = STREAMING_STEP_COLORS[active % STREAMING_STEP_COLORS.length]!;
  const pct = Math.round(((active + (queued ? 0 : 0.2)) / Math.max(1, steps.length - 1 || 1)) * 100);
  const visible = steps.map((text, i) => ({ text, i }));

  return (
    <div
      className="bi-chat-streaming-steps space-y-3 rounded-2xl border border-white/70 bg-gradient-to-br from-sky-50 via-violet-50 to-amber-50 p-3.5 shadow-sm"
      aria-live="polite"
      aria-busy="true"
    >
      <div className="flex items-start justify-between gap-3">
        <p
          key={`${queued ? 'q' : 's'}-${active}-${label.slice(0, 32)}`}
          className={clsx(
            'bi-chat-status-line flex min-w-0 flex-1 items-start gap-2 text-sm font-semibold leading-snug',
            accent.text,
          )}
        >
          <span
            className={clsx(
              'mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-white',
              accent.dot,
            )}
          >
            <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
          </span>
          <span className="min-w-0">{label}</span>
        </p>
        <span className="shrink-0 rounded-full bg-white/80 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-slate-600 ring-1 ring-slate-200/80">
          {t('bi.chat.progressTip.stepOf', {
            current: String(Math.min(steps.length, active + 1)),
            total: String(steps.length),
          })}
          {typeof elapsedSec === 'number' && elapsedSec > 0 ? ` · ${Math.round(elapsedSec)}s` : ''}
        </span>
      </div>

      <div className="h-1.5 overflow-hidden rounded-full bg-white/80 ring-1 ring-slate-200/70" aria-hidden>
        <div
          className="h-full rounded-full bg-gradient-to-r from-sky-500 via-violet-500 to-amber-400 transition-all duration-700 ease-out"
          style={{ width: `${Math.min(96, Math.max(8, pct))}%` }}
        />
      </div>

      {!queued ? (
        <ol className="space-y-1.5" aria-hidden>
          {visible.map(({ text, i }) => {
            const color = STREAMING_STEP_COLORS[i % STREAMING_STEP_COLORS.length]!;
            const done = i < active;
            const current = i === active;
            return (
              <li
                key={i}
                className={clsx(
                  'flex items-start gap-2 rounded-xl px-2 py-1.5 text-xs leading-snug transition-all duration-300',
                  current && clsx(color.soft, 'ring-1', color.ring, 'font-semibold', color.text),
                  done && 'text-emerald-700',
                  !done && !current && 'text-slate-400',
                )}
              >
                <span
                  className={clsx(
                    'mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full',
                    done && 'bg-emerald-500 text-white',
                    current && clsx(color.dot, 'text-white'),
                    !done && !current && 'bg-slate-200 text-slate-500',
                  )}
                >
                  {done ? (
                    <Check className="h-2.5 w-2.5" strokeWidth={3} />
                  ) : current ? (
                    <Loader2 className="h-2.5 w-2.5 animate-spin" />
                  ) : (
                    <span className="text-[9px] font-bold">{i + 1}</span>
                  )}
                </span>
                <span className="min-w-0">{text}</span>
              </li>
            );
          })}
        </ol>
      ) : null}

      <p className="text-[11px] leading-snug text-slate-500">{t('bi.chat.progressTip.readySoon')}</p>
    </div>
  );
}

type BiChatPanelProps = {
  sessionId: string;
  dashboardId?: string;
  onResponse?: (resp: BiChatResponse) => void;
  className?: string;
  initialMessage?: string;
  /** Hidden send-time intent (e.g. create_alert) — never shown in the composer. */
  initialIntent?: string;
  fullHeight?: boolean;
  /** Hide duplicate chrome when rendered inside BiAnalyticsChatDock */
  embedded?: boolean;
  /** Focus the text field (e.g. when analytics chat opens) */
  autoFocus?: boolean;
};

const FALLBACK_SUGGESTION_KEYS = [
  'bi.chatSuggestionWidget1',
  'bi.chatSuggestionWidget2',
  'bi.chatSuggestionWidget3',
  'bi.chatSuggestion1',
  'bi.chatSuggestion2',
  'bi.chatSuggestion4',
] as const;

type ChatSuggestionItem = {
  text: string;
  source: string;
  count: number;
  category?: string;
  scenarioCode?: string;
  sql_hint?: string;
  bind_params?: Record<string, unknown>;
};

function intentIcon(intent: string) {
  switch (intent) {
    case 'query':
      return Search;
    case 'dashboard':
    case 'pin':
      return LayoutDashboard;
    case 'report':
      return FileBarChart;
    case 'schedule':
      return CalendarClock;
    case 'analytics':
    case 'superset':
      return BarChart3;
    case 'compare':
      return Sparkles;
    default:
      return MessageSquareText;
  }
}

function intentLabel(intent: string) {
  const normalized = intent === 'superset' ? 'analytics' : intent;
  const key = `bi.intent.${normalized}` as 'bi.intent.query';
  const label = t(key);
  return label !== key ? label : brandText(intent);
}

/** Prefer top-level executed SQL, then saved query, then widget SQL. */
function pickExportSql(meta?: BiChatResponse | null): string | undefined {
  if (!meta) return undefined;
  const top = meta.sql?.trim();
  if (top) return top;
  const saved = meta.saved_query?.sql?.trim();
  if (saved) return saved;
  for (const w of meta.widgets ?? []) {
    const sql = w.sql?.trim() || w.drill_sql?.trim();
    if (sql) return sql;
  }
  return undefined;
}

function assistantDisplayText(raw: string | null | undefined, streaming?: boolean): string {
  if (!raw) return '';
  const branded = brandText(raw);
  // Keep status lines (Thinking…) intact while streaming short status.
  if (streaming && branded.length < 80 && !isSqlLookingQuick(branded)) return branded;
  return stripSqlFromChatText(branded);
}

function isSqlLookingQuick(text: string): boolean {
  return /\bSELECT\b/i.test(text) && /\bFROM\b/i.test(text);
}

type JobProgressEntry = { question: string; tipIndex: number; startedAt: number; phase?: string };

type MessageRowProps = {
  message: ChatMessage;
  index: number;
  /** Progress entry for this message's job (streaming placeholders only). */
  job?: JobProgressEntry;
  dashboardId?: string;
  fullHeight?: boolean;
  showSqlPanel: boolean;
  enableFeedback: boolean;
  enableTestExecution: boolean;
  pinning: boolean;
  pinned: boolean;
  pinnedBoardId: number | null;
  confirming: boolean;
  feedbackBusy: boolean;
  /** Non-null only when the draft targets this row. */
  feedbackDraft: FeedbackDraft | null;
  config: ApiConfig;
  onSend: (text: string) => void;
  onPin: (msg: ChatMessage, target?: { dashboardId?: number; vizType?: string } | number) => void;
  onConfirm: (msg: ChatMessage) => void;
  onDismissConfirm: (msg: ChatMessage) => void;
  onBeginFeedback: (msg: ChatMessage, index: number, rating: -1 | 0 | 1) => void;
  onSubmitFeedback: (msg: ChatMessage, index: number) => void;
  onFeedbackComment: (comment: string) => void;
  onCancelFeedback: () => void;
};

/** One transcript row. Memoized so streaming/typing only re-renders the rows
 *  whose message object (or targeted UI state) actually changed. */
const MessageRow = memo(function MessageRow({
  message: m,
  index,
  job,
  dashboardId,
  fullHeight,
  showSqlPanel,
  enableFeedback,
  enableTestExecution,
  pinning,
  pinned,
  pinnedBoardId,
  confirming,
  feedbackBusy,
  feedbackDraft,
  config,
  onSend,
  onPin,
  onConfirm,
  onDismissConfirm,
  onBeginFeedback,
  onSubmitFeedback,
  onFeedbackComment,
  onCancelFeedback,
}: MessageRowProps) {
  // Heavy derivations (31 brand regexes + SQL strip) run once per content
  // change instead of on every parent render.
  const exportSql = useMemo(() => pickExportSql(m.meta), [m.meta]);
  const heroScalar = useMemo(
    () => Boolean(m.meta && !m.streaming && isHeroScalarResult(m.meta)),
    [m.meta, m.streaming],
  );
  const kpiAnswer = useMemo(() => Boolean(m.meta && isChatKpiAnswer(m.meta)), [m.meta]);
  const displayText = useMemo(
    () => (m.role === 'assistant' ? assistantDisplayText(m.content, m.streaming) : m.content || ''),
    [m.content, m.role, m.streaming],
  );
  const questionTitle = m.questionTitle;

  return (
    <div className={clsx('flex gap-2.5 animate-slide-up sm:gap-3', m.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
      <div className={clsx('flex h-8 w-8 shrink-0 items-center justify-center rounded-full', m.role === 'user' ? 'bg-gradient-to-br from-violet-600 to-blue-600 text-white' : 'bg-violet-100 text-violet-600')}>
        {m.role === 'user' ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={clsx(
          'min-w-0 w-full max-w-[min(100%,40rem)] rounded-2xl px-3.5 py-2.5 text-sm shadow-sm sm:max-w-[min(92%,42rem)] sm:px-4 lg:max-w-[min(88%,48rem)]',
          m.role === 'user'
            ? 'rounded-tr-md bg-gradient-to-br from-violet-600 to-blue-600 text-white'
            : 'rounded-tl-md border border-[#E1DFDD] bg-white/95 text-[#252423] shadow-[inset_0_1px_0_rgba(255,255,255,0.9),0_2px_8px_rgba(15,23,42,0.06)]',
          m.failed && m.role === 'user' && 'ring-2 ring-status-fail/40',
          fullHeight && 'sm:max-w-[min(94%,52rem)] lg:max-w-[min(90%,56rem)]',
        )}
      >
        {m.role === 'assistant' && (m.scenarioSource || (m.meta?.intent && !m.streaming)) && (
          <div className="mb-2 flex flex-wrap items-center gap-1.5">
            {m.scenarioSource ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-800 ring-1 ring-emerald-200/80">
                Hazır senaryo
                {m.scenarioCode ? (
                  <span className="font-normal text-emerald-700/80">· {m.scenarioCode}</span>
                ) : null}
              </span>
            ) : null}
            {m.meta?.intent && !m.streaming
              ? (() => {
                  const Icon = intentIcon(m.meta.intent);
                  return (
                    <span className="bi-pbi-type-chip bi-pbi-type-chip--compact">
                      <Icon className="h-3 w-3" />
                      {intentLabel(m.meta.intent)}
                    </span>
                  );
                })()
              : null}
          </div>
        )}
        <div className="min-w-0">
          {(() => {
            if (m.streaming && !m.content && job) {
              return (
                <BiChatStreamingSteps
                  question={job.question}
                  tipIndex={job.tipIndex}
                  phase={m.streamPhase}
                  queuePosition={m.queuePosition}
                  queueMessage={m.queueMessage}
                  elapsedSec={m.elapsedSec}
                />
              );
            }
            if (m.streaming && !m.content) {
              return (
                <p className="whitespace-pre-wrap break-anywhere leading-relaxed">
                  {statusLabelForMessage(m)}
                  <Loader2 className="ml-1 inline h-3.5 w-3.5 animate-spin" />
                </p>
              );
            }
            if (!m.content) return null;
            // Hero KPI owns the answer — hide redundant status / SQL chatter.
            if (m.role === 'assistant' && heroScalar) {
              return null;
            }
            if (!displayText.trim()) return null;
            return (
              <p className="whitespace-pre-wrap break-anywhere leading-relaxed">
                {displayText}
                {m.streaming && !!m.content && (
                  <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse rounded-sm bg-violet-500 align-text-bottom" aria-hidden />
                )}
              </p>
            );
          })()}
        </div>
        {m.meta?.answer_blocks &&
          m.meta.answer_blocks.length > 0 &&
          !m.meta.query_result &&
          !m.streaming && (
          <div className="mt-3"><BiAnswerBlocks blocks={m.meta.answer_blocks} /></div>
        )}
        {(() => {
          if (!m.meta || m.streaming) return null;
          if (kpiAnswer && m.meta.query_result) {
            return (
              <>
                <BiChatResultHero meta={m.meta} title={questionTitle} />
                <div className="mt-2 flex w-full justify-end">
                  <BiPinToDashboardControl
                    compact
                    pinning={pinning}
                    pinned={pinned}
                    pinnedDashboardId={pinnedBoardId}
                    preferredDashboardId={dashboardId}
                    preferredVizType="kpi"
                    onPin={(sel) => onPin(m, sel)}
                  />
                </div>
              </>
            );
          }
          if (m.meta.widgets && m.meta.widgets.length > 0) {
            return (
              <BiChatWidgetPreview
                widgets={m.meta.widgets}
                dashboardId={dashboardId}
                pinned={pinned}
                pinnedDashboardId={pinnedBoardId}
                pinning={pinning}
                onPin={(sel) => onPin(m, sel)}
              />
            );
          }
          if (m.meta.query_result) {
            return (
              <>
                <BiChatResultHero meta={m.meta} title={questionTitle} />
                {exportSql ? (
                  <div className="mt-2 flex w-full justify-end">
                    <BiPinToDashboardControl
                      pinning={pinning}
                      pinned={pinned}
                      pinnedDashboardId={pinnedBoardId}
                      preferredDashboardId={dashboardId}
                      preferredVizType="table"
                      onPin={(sel) => onPin(m, sel)}
                    />
                  </div>
                ) : null}
              </>
            );
          }
          return null;
        })()}
        {m.role === 'assistant' && !m.streaming && (m.followUps?.length ?? 0) > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {m.followUps!.slice(0, 5).map((q) => (
              <button
                key={q}
                type="button"
                className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-700 hover:border-violet-300 hover:bg-violet-50"
                onClick={() => onSend(q)}
              >
                {q}
              </button>
            ))}
          </div>
        )}
        {m.meta?.action_preview?.preview?.requires_confirm &&
          m.meta.action_preview.status === 'preview' &&
          !m.streaming &&
          !m.meta.action_preview.confirmed && (
            <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/90 px-3 py-2.5 text-xs text-slate-800">
              <p className="font-semibold text-amber-950">{t('bi.confirm.title')}</p>
              <p className="mt-1 text-slate-600">
                {t('bi.confirm.body', {
                  action: String(m.meta.action_preview.preview.action || ''),
                })}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-primary h-8 px-3 text-xs"
                  disabled={confirming}
                  onClick={() => onConfirm(m)}
                >
                  {confirming ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    t('bi.confirm.approve')
                  )}
                </button>
                <button
                  type="button"
                  className="btn-secondary h-8 px-3 text-xs"
                  disabled={confirming}
                  onClick={() => onDismissConfirm(m)}
                >
                  {t('bi.confirm.dismiss')}
                </button>
              </div>
            </div>
          )}
        {showSqlPanel && (m.draftSql || exportSql) && (
            <details className="mt-3 rounded-lg border border-slate-200 bg-slate-50/90 px-3 py-2 text-xs text-slate-700">
              <summary className="cursor-pointer font-semibold text-slate-800">
                SQL
                {m.draftDialect ? ` · ${m.draftDialect}` : ''}
                {m.executionMode ? ` · ${m.executionMode}` : ''}
              </summary>
              <div className="mt-2 space-y-1.5 text-[11px] text-slate-600">
                {m.draftDialect || m.meta?.provenance?.dialect ? (
                  <p>
                    <span className="font-medium text-slate-700">{t('bi.provenance.dialect')}: </span>
                    {m.draftDialect || m.meta?.provenance?.dialect}
                  </p>
                ) : null}
                {m.draftConfidence != null || m.meta?.provenance?.confidence != null ? (
                  <p>
                    <span className="font-medium text-slate-700">{t('bi.provenance.confidence')}: </span>
                    {(m.draftConfidence ?? m.meta?.provenance?.confidence ?? 0).toFixed(2)}
                  </p>
                ) : null}
                <p>
                  <span className="font-medium text-slate-700">
                    {m.meta?.provenance?.executed ||
                    (m.executionMode &&
                      !String(m.executionMode).includes('PLAN_ONLY') &&
                      m.executionMode !== 'PLAN_ONLY')
                      ? t('bi.provenance.executed')
                      : t('bi.provenance.notExecuted')}
                  </span>
                </p>
                {(m.draftTables?.length || m.meta?.provenance?.selected_tables?.length) ? (
                  <p>
                    <span className="font-medium text-slate-700">{t('bi.provenance.tables')}: </span>
                    {(m.draftTables || m.meta?.provenance?.selected_tables || []).join(', ')}
                  </p>
                ) : null}
                {(m.draftColumns?.length || m.meta?.provenance?.columns?.length) ? (
                  <p>
                    <span className="font-medium text-slate-700">{t('bi.provenance.columns')}: </span>
                    {(m.draftColumns || m.meta?.provenance?.columns || []).join(', ')}
                  </p>
                ) : null}
                {(m.draftAssumptions?.length || m.meta?.provenance?.assumptions?.length) ? (
                  <div>
                    <p className="font-medium text-slate-700">{t('bi.provenance.assumptions')}</p>
                    <ul className="mt-0.5 list-disc pl-4">
                      {(m.draftAssumptions || m.meta?.provenance?.assumptions || []).map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(m.draftWarnings?.length ||
                  m.meta?.provenance?.warnings?.length ||
                  m.meta?.warnings?.length) ? (
                  <div>
                    <p className="font-medium text-amber-800">{t('bi.provenance.warnings')}</p>
                    <ul className="mt-0.5 list-disc pl-4 text-amber-800">
                      {(
                        m.draftWarnings ||
                        m.meta?.provenance?.warnings ||
                        m.meta?.warnings ||
                        []
                      ).map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
              <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] text-slate-800">
                {m.draftSql || exportSql}
              </pre>
              {enableTestExecution ? (
                <p className="mt-2 text-[11px] text-amber-700">
                  Test çalıştırma bu ortamda açıktır (prod’da kapalı).
                </p>
              ) : null}
            </details>
          )}
        {m.role === 'assistant' && !m.streaming && enableFeedback && m.meta && (
          <div className="mt-2 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className={clsx(
                  'inline-flex h-8 items-center gap-1.5 rounded-lg border px-2 text-[11px] text-slate-600 hover:bg-emerald-50',
                  m.feedbackRating === 1 && 'border-emerald-400 bg-emerald-50 text-emerald-700',
                  feedbackDraft?.rating === 1 && 'border-emerald-400 bg-emerald-50',
                )}
                aria-label={t('bi.feedback.correct')}
                disabled={m.feedbackRating != null || feedbackBusy}
                onClick={() => onBeginFeedback(m, index, 1)}
              >
                <ThumbsUp className="h-3.5 w-3.5" />
                {t('bi.feedback.correct')}
              </button>
              <button
                type="button"
                className={clsx(
                  'inline-flex h-8 items-center gap-1.5 rounded-lg border px-2 text-[11px] text-slate-600 hover:bg-amber-50',
                  m.feedbackRating === 0 && 'border-amber-400 bg-amber-50 text-amber-800',
                  feedbackDraft?.rating === 0 && 'border-amber-400 bg-amber-50',
                )}
                aria-label={t('bi.feedback.partial')}
                disabled={m.feedbackRating != null || feedbackBusy}
                onClick={() => onBeginFeedback(m, index, 0)}
              >
                <Minus className="h-3.5 w-3.5" />
                {t('bi.feedback.partial')}
              </button>
              <button
                type="button"
                className={clsx(
                  'inline-flex h-8 items-center gap-1.5 rounded-lg border px-2 text-[11px] text-slate-600 hover:bg-rose-50',
                  m.feedbackRating === -1 && 'border-rose-400 bg-rose-50 text-rose-700',
                  feedbackDraft?.rating === -1 && 'border-rose-400 bg-rose-50',
                )}
                aria-label={t('bi.feedback.wrong')}
                disabled={m.feedbackRating != null || feedbackBusy}
                onClick={() => onBeginFeedback(m, index, -1)}
              >
                <ThumbsDown className="h-3.5 w-3.5" />
                {t('bi.feedback.wrong')}
              </button>
              {m.feedbackRating != null ? (
                <span className="text-[11px] text-slate-500">{t('bi.feedback.saved')}</span>
              ) : null}
            </div>
            {feedbackDraft && m.feedbackRating == null ? (
              <div className="rounded-lg border border-slate-200 bg-slate-50/80 p-2">
                <label className="mb-1 block text-[11px] font-medium text-slate-600">
                  {feedbackDraft.rating === 1
                    ? t('bi.feedback.commentOptional')
                    : t('bi.feedback.commentRequired')}
                </label>
                <textarea
                  className="w-full rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-800"
                  rows={2}
                  value={feedbackDraft.comment}
                  onChange={(e) => onFeedbackComment(e.target.value)}
                  placeholder={t('bi.feedback.commentPlaceholder')}
                  disabled={feedbackBusy}
                />
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="btn-primary text-xs"
                    disabled={feedbackBusy}
                    onClick={() => onSubmitFeedback(m, index)}
                  >
                    {t('bi.feedback.submit')}
                  </button>
                  <button
                    type="button"
                    className="btn-secondary text-xs"
                    disabled={feedbackBusy}
                    onClick={onCancelFeedback}
                  >
                    {t('bi.feedback.cancel')}
                  </button>
                </div>
              </div>
            ) : null}
          </div>
        )}
        {m.role === 'assistant' && !m.streaming && exportSql && (
          <div className="mt-2 flex w-full max-w-lg flex-col items-stretch gap-2 self-end sm:max-w-md">
            <div className="flex flex-wrap justify-end gap-2">
              <BiExportMenu sql={exportSql} />
            </div>
            {m.meta?.provenance?.metric ? (
              <>
                <BiLineageDrawer config={config} metricId={String(m.meta.provenance.metric)} />
                <BiScenarioSliders
                  config={config}
                  metricId={String(m.meta.provenance.metric)}
                />
              </>
            ) : null}
          </div>
        )}
        {m.meta?.schedule && !m.streaming && (
          <div className="mt-3 rounded-xl border border-violet-200 bg-violet-50/80 px-3 py-2.5 text-xs text-slate-700">
            <p className="font-semibold text-violet-900">{t('bi.scheduleCreated')}</p>
            <p className="mt-1">{m.meta.schedule.subject}</p>
            <p className="mt-1 font-mono text-[11px] text-slate-500">
              {m.meta.schedule.run_at?.slice(0, 16)?.replace('T', ' ')}
              {m.meta.schedule.local_time ? ` · ${m.meta.schedule.local_time}` : ''}
              {' · '}
              {m.meta.schedule.recurrence === 'daily'
                ? t('bi.scheduleRecurrenceDaily')
                : m.meta.schedule.recurrence === 'weekly'
                  ? t('bi.scheduleRecurrenceWeekly')
                  : t('bi.scheduleRecurrenceOnce')}
            </p>
            {m.meta.schedule.recipient && (
              <p className="mt-1 text-slate-600">{m.meta.schedule.recipient}</p>
            )}
            <Link
              to="/bi/schedules"
              className="mt-2 inline-block font-medium text-violet-700 hover:underline"
            >
              {t('bi.wow.manageSchedules')}
            </Link>
          </div>
        )}
        {m.meta?.alert && !m.streaming && (
          <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/80 px-3 py-2.5 text-xs text-slate-700">
            <p className="font-semibold text-amber-900">{t('bi.alertCreated')}</p>
            <p className="mt-1">{m.meta.alert.title}</p>
            <p className="mt-1 font-mono text-[11px] text-slate-500">
              {m.meta.alert.column} {m.meta.alert.condition} {m.meta.alert.threshold}
              {m.meta.alert.last_value != null ? ` · last ${m.meta.alert.last_value}` : ''}
            </p>
            <div className="mt-2 flex flex-wrap gap-3">
              <Link to="/bi/alerts" className="font-medium text-amber-800 hover:underline">
                {t('bi.wow.alertStripManage')}
              </Link>
              <Link to="/bi/schedules" className="font-medium text-amber-800 hover:underline">
                {t('bi.alertIncludeInMorningMail')}
              </Link>
            </div>
          </div>
        )}
      </div>
    </div>
  );
});

type BiChatComposerProps = {
  pending: boolean;
  embedded?: boolean;
  autoFocus?: boolean;
  sessionId: string;
  /** Prefill from openChat({prompt}) — applied once per session+text. */
  prefill?: string;
  showEmptyHint: boolean;
  /** Increment to clear the draft (e.g. chat cleared). */
  resetSignal: number;
  onSend: (text: string) => void;
  onStop: () => void;
};

/** Composer owns the draft text so typing never re-renders the transcript. */
const BiChatComposer = memo(function BiChatComposer({
  pending,
  embedded,
  autoFocus,
  sessionId,
  prefill,
  showEmptyHint,
  resetSignal,
  onSend,
  onStop,
}: BiChatComposerProps) {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const prefilledRef = useRef<string | null>(null);

  useEffect(() => {
    if (prefill && prefilledRef.current !== `${sessionId}:${prefill}`) {
      prefilledRef.current = `${sessionId}:${prefill}`;
      setInput(prefill);
    }
  }, [prefill, sessionId]);

  useEffect(() => {
    if (resetSignal > 0) setInput('');
  }, [resetSignal]);

  useEffect(() => {
    if (!autoFocus) return;
    const id = window.setTimeout(() => textareaRef.current?.focus(), 80);
    return () => window.clearTimeout(id);
  }, [autoFocus, sessionId]);

  const submit = () => {
    const text = input.trim();
    if (!text) return;
    setInput('');
    onSend(text);
  };

  return (
    <div
      className={clsx(
        'relative z-20 shrink-0 border-t border-violet-200/80 bg-white p-3 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] sm:p-3',
        embedded && 'pb-[max(0.75rem,env(safe-area-inset-bottom))]',
      )}
    >
      {showEmptyHint && (
        <p className="mb-2 text-center text-[11px] font-medium text-violet-700">{t('bi.analytics.typeBelow')}</p>
      )}
      <div className="flex items-end gap-2 rounded-xl border border-violet-300/80 bg-white p-2 shadow-sm focus-within:border-violet-500 focus-within:ring-2 focus-within:ring-violet-400/25">
        <BiVoiceInput
          onTranscript={(text) => {
            const trimmed = text.trim();
            if (!trimmed) return;
            setInput('');
            onSend(trimmed);
          }}
        />
        <span className="sr-only" aria-live="polite">
          {pending ? t('bi.voiceSentHint') : ''}
        </span>
        <textarea
          ref={textareaRef}
          className="max-h-[100px] min-h-[44px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-base text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-0 sm:text-sm"
          rows={1}
          placeholder={embedded ? t('bi.analytics.chatPlaceholder') : t('bi.chatPlaceholder')}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        {pending ? (
          <button
            type="button"
            className="btn-secondary h-11 w-11 shrink-0 rounded-lg p-0 text-rose-700 sm:h-10 sm:w-10"
            aria-label="Durdur"
            title="Durdur"
            onClick={onStop}
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            className="btn-primary h-11 w-11 shrink-0 rounded-lg p-0 sm:h-10 sm:w-10"
            disabled={!input.trim()}
            onClick={submit}
          >
            <Send className="h-4 w-4" />
          </button>
        )}
      </div>
      {!embedded && <p className="mt-2 hidden text-center text-[11px] text-slate-400 sm:block">{t('bi.chatSendHint')}</p>}
    </div>
  );
});

export default function BiChatPanel({
  sessionId,
  dashboardId,
  onResponse,
  className,
  initialMessage,
  initialIntent,
  fullHeight,
  embedded,
  autoFocus,
}: BiChatPanelProps) {
  const { config } = useApiConfig();
  const queryClient = useQueryClient();
  const flags = getFeatureFlags();
  const { canBi } = useAuth();
  const showSqlPanel = flags.enableSqlPanel && canBi('sql.panel');
  const templates = useQuery({
    queryKey: ['bi-templates', config],
    queryFn: () => api.bi.templates(config),
    enabled: isRunnerConfigured(config),
  });
  const sourcesQ = useQuery({
    queryKey: ['bi-sources', config],
    queryFn: () => api.bi.sources.list(config),
    enabled: isRunnerConfigured(config),
    staleTime: 60_000,
  });
  const activeDbName = sourcesQ.data?.active_id || undefined;
  const suggestionLimit = embedded ? 3 : 6;
  const suggestionsQ = useQuery({
    queryKey: ['bi-chat-suggestions', config, activeDbName, suggestionLimit],
    queryFn: () =>
      api.bi.chatSuggestions(config, {
        datasourceId: activeDbName,
        limit: suggestionLimit,
      }),
    enabled: isRunnerConfigured(config) && Boolean(activeDbName),
    staleTime: 30_000,
  });

  const [warmTick, setWarmTick] = useState(0);
  useEffect(() => {
    const list = templates.data?.templates ?? [];
    if (!isRunnerConfigured(config) || !list.length) return;
    const limit = embedded ? 3 : 6;
    void warmTemplatesInBackground(config, list, limit).then(() => {
      setWarmTick((n) => n + 1);
    });
  }, [config, embedded, templates.data?.templates]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [lastFailedText, setLastFailedText] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notifyPerm, setNotifyPerm] = useState<NotifyPermission>(() => getNotifyPermission());
  const [jobProgress, setJobProgress] = useState<Record<string, JobProgressEntry>>({});
  const [feedbackDraft, setFeedbackDraft] = useState<FeedbackDraft | null>(null);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  /** Incremented to clear the composer draft (chat cleared). */
  const [composerReset, setComposerReset] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const prefilledRef = useRef<string | null>(null);
  const sendIntentRef = useRef<string | undefined>(undefined);
  /** Mirror so submit handlers stay referentially stable while typing. */
  const feedbackDraftRef = useRef<FeedbackDraft | null>(null);
  feedbackDraftRef.current = feedbackDraft;
  /** This mount owns the live send UI — remount reattach must not steal it. */
  const drivingSendRef = useRef(false);
  /** After local clear, ignore server history until the next send / session change. */
  const suppressHistoryRef = useRef(false);
  const pending = pendingCount > 0;
  const activeJobIds = Object.keys(jobProgress);
  const showWaitBanner = activeJobIds.length > 0;
  const primaryJob = activeJobIds.length
    ? jobProgress[activeJobIds[activeJobIds.length - 1]!]
    : null;

  const history = useQuery({
    queryKey: ['bi-chat-history', config, sessionId],
    queryFn: () => api.bi.chatHistory(config, sessionId),
    enabled: isRunnerConfigured(config) && Boolean(sessionId),
    refetchOnMount: 'always',
  });

  // Reset local timeline when the session changes so empty history cannot keep
  // the previous conversation on screen.
  useEffect(() => {
    suppressHistoryRef.current = false;
    setMessages([]);
    setError(null);
    setLastFailedText(null);
  }, [sessionId]);

  useEffect(() => {
    // Live/background job owns the timeline until it settles.
    if (pending || isBiChatJobPending(sessionId) || drivingSendRef.current) return;
    if (suppressHistoryRef.current) return;
    const raw = history.data?.messages ?? [];
    // Bridge/DB-GPT history is often empty while nanobase already rendered the
    // answer locally — never wipe a live timeline just because history is empty.
    if (!raw.length) return;
    setMessages((prev) => {
      const mapped = mapHistoryMessages(raw, sessionId);
      const localRich = prev.some(
        (m) =>
          Boolean(m.meta?.query_result) ||
          (m.meta?.widgets?.length ?? 0) > 0 ||
          Boolean(m.streaming),
      );
      const histRich = mapped.some(
        (m) => Boolean(m.meta?.query_result) || (m.meta?.widgets?.length ?? 0) > 0,
      );
      // Prefer the just-rendered local answer over text-only server history.
      if (localRich && !histRich) return prev;
      return mapped;
    });
  }, [history.data, sessionId, pending]);

  useEffect(() => {
    if (initialMessage && prefilledRef.current !== `${sessionId}:${initialMessage}`) {
      prefilledRef.current = `${sessionId}:${initialMessage}`;
      // Composer applies the text prefill; keep the hidden intent here.
      sendIntentRef.current = initialIntent;
    }
  }, [initialIntent, initialMessage, sessionId]);

  useEffect(() => {
    if (initialIntent) sendIntentRef.current = initialIntent;
  }, [initialIntent]);

  /** Only auto-follow the stream while the operator is already near the bottom. */
  const nearBottomRef = useRef(true);
  const lastAutoScrollRef = useRef(0);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    };
    onScroll();
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);

  const scrollToBottom = useCallback((force = false) => {
    if (!force && !nearBottomRef.current) return;
    const now = Date.now();
    if (!force && now - lastAutoScrollRef.current < 100) return;
    lastAutoScrollRef.current = now;
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, pending, scrollToBottom]);

  // Tip index advances only from real stream phase events (see status handler).
  // No fake timer — stuck on the current step until the backend moves on.

  // Reattach after navigation: client job(s) still running, or server still processing.
  useEffect(() => {
    if (!isRunnerConfigured(config) || !sessionId || drivingSendRef.current) return;

    const settled = getBiChatJobsSettled(sessionId);
    if (settled) {
      setPendingCount((n) => Math.max(n, biChatJobCount(sessionId)));
      setMessages((prev) =>
        ensureStreamingBubble(
          prev.length ? prev : mapHistoryMessages(history.data?.messages ?? [], sessionId),
        ),
      );
      let cancelled = false;
      void settled.finally(async () => {
        if (cancelled) return;
        try {
          const snap = await api.bi.chatHistory(config, sessionId);
          const mapped = mapHistoryMessages(snap.messages ?? [], sessionId);
          // Keep local timeline when server history is empty/stubbed.
          if (mapped.length) {
            setMessages(mapped);
          }
          const lastAssistant = [...(snap.messages ?? [])]
            .reverse()
            .find((m) => (m as { role?: string }).role === 'assistant' && (m as { meta?: BiChatResponse }).meta);
          if (lastAssistant && (lastAssistant as { meta?: BiChatResponse }).meta) {
            onResponse?.((lastAssistant as { meta: BiChatResponse }).meta);
          }
        } catch {
          /* ignore */
        }
        setPendingCount(0);
        void history.refetch();
      });
      return () => {
        cancelled = true;
      };
    }

    if (!history.data?.pending) return;

    setPendingCount((n) => Math.max(n, 1));
    setMessages((prev) =>
      ensureStreamingBubble(
        prev.length ? prev : mapHistoryMessages(history.data?.messages ?? [], sessionId),
      ),
    );

    let cancelled = false;
    const poll = window.setInterval(() => {
      void (async () => {
        try {
          const snap = await api.bi.chatHistory(config, sessionId);
          if (cancelled) return;
          if (snap.pending) {
            const mappedPending = mapHistoryMessages(snap.messages ?? [], sessionId);
            setMessages((prev) =>
              ensureStreamingBubble(mappedPending.length ? mappedPending : prev),
            );
            return;
          }
          window.clearInterval(poll);
          const mapped = mapHistoryMessages(snap.messages ?? [], sessionId);
          if (mapped.length) setMessages(mapped);
          const lastAssistant = [...mapped].reverse().find((m) => m.role === 'assistant' && m.meta);
          if (lastAssistant?.meta) onResponse?.(lastAssistant.meta);
          setPendingCount(0);
          void history.refetch();
        } catch {
          /* keep polling */
        }
      })();
    }, 1200);

    return () => {
      cancelled = true;
      window.clearInterval(poll);
    };
    // history.data?.messages intentionally omitted — used only as initial seed when effect starts
  }, [config, sessionId, history.data?.pending, history.refetch, onResponse]);

  const [confirmingJobId, setConfirmingJobId] = useState<string | null>(null);
  const [pinningKey, setPinningKey] = useState<string | null>(null);
  const [pinnedKeys, setPinnedKeys] = useState<Record<string, boolean>>({});
  const [pinnedBoardByKey, setPinnedBoardByKey] = useState<Record<string, number>>({});

  const pinToDashboard = useCallback(
    async (
      msg: ChatMessage,
      target?: { dashboardId?: number; vizType?: string } | number,
    ) => {
      const sql = pickExportSql(msg.meta);
      if (!sql || msg.streaming) return;
      const key = messagePinKey(msg);
      setPinningKey(key);
      setError(null);
      try {
        const selection =
          typeof target === 'number'
            ? { dashboardId: target, vizType: undefined as string | undefined }
            : target || {};
        let dashId = Number(selection.dashboardId || 0);
        if (!Number.isFinite(dashId) || dashId <= 0) {
          dashId = dashboardId ? Number(dashboardId) : 0;
        }
        const title =
          (msg.meta?.widgets?.[0]?.title as string | undefined) ||
          (msg.content || '').replace(/\s+/g, ' ').trim().slice(0, 80) ||
          t('bi.pinToDashboard');
        // Native canvas pin works without Superset boards.
        if (!Number.isFinite(dashId) || dashId <= 0) {
          try {
            const boards = await api.bi.analytics.dashboards(config);
            const needle = title.trim().toLowerCase();
            const match = (boards.dashboards || []).find(
              (d) => String(d.title || '').trim().toLowerCase() === needle,
            );
            if (match?.id) {
              dashId = Number(match.id);
            } else if ((boards.dashboards || []).length > 0) {
              const created = await api.bi.analytics.createDashboard(config, { title });
              dashId = Number(created.id || 0);
            }
          } catch {
            dashId = 0;
          }
        }
        const vizType = (selection.vizType || '').trim() || undefined;
        const widgets = (msg.meta?.widgets || [])
          .filter((w) => w.sql || sql)
          .map((w) => ({
            title: w.title || t('bi.pinToDashboard'),
            type: vizType || w.type || 'table',
            sql: w.sql || w.drill_sql || sql,
            x_key: w.x_key,
            y_key: w.y_key,
            value_key: w.value_key,
            label_key: w.label_key,
            id: w.id,
          }));
        const pinDashId = Number.isFinite(dashId) && dashId > 0 ? dashId : 0;
        const out = await api.bi.analytics.pin(config, pinDashId, {
          sql,
          title,
          viz_type: vizType || widgets[0]?.type || 'table',
          widgets: widgets.length ? widgets : undefined,
        });
        const resolvedDash = Number(out.dashboard_id || pinDashId);
        setPinnedKeys((prev) => ({ ...prev, [key]: true }));
        if (Number.isFinite(resolvedDash) && resolvedDash > 0) {
          setPinnedBoardByKey((prev) => ({ ...prev, [key]: resolvedDash }));
        }
        void queryClient.invalidateQueries({ queryKey: ['bi-analytics-source-widgets'] });
        void queryClient.invalidateQueries({ queryKey: ['bi-analytics-dashboards'] });
        void queryClient.invalidateQueries({ queryKey: ['bi-analytics-charts'] });
        const nextMeta: BiChatResponse = {
          session_id: msg.meta?.session_id || sessionId,
          reply: msg.meta?.reply || msg.content,
          intent: 'pin',
          widgets: msg.meta?.widgets || [],
          answer_blocks: msg.meta?.answer_blocks || [],
          ...(msg.meta || {}),
          analytics: {
            ...(msg.meta?.analytics || {}),
            dashboard_id: resolvedDash > 0 ? resolvedDash : undefined,
            embed_uuid: out.embed_uuid,
            ...(out.guest?.token &&
            out.guest.dashboard_id &&
            out.guest.embed_uuid &&
            out.guest.analytics_url
              ? {
                  guest: {
                    token: String(out.guest.token),
                    dashboard_id: Number(out.guest.dashboard_id),
                    embed_uuid: String(out.guest.embed_uuid),
                    analytics_url: String(out.guest.analytics_url),
                  },
                }
              : {}),
          },
        };
        setMessages((prev) =>
          prev.map((m) => {
            if (m !== msg && !(msg.jobId && m.jobId === msg.jobId)) return m;
            return { ...m, meta: nextMeta };
          }),
        );
        onResponse?.(nextMeta);
      } catch (err) {
        setError(localizeUserMessage((err as Error).message) || t('bi.pinFailed'));
      } finally {
        setPinningKey(null);
      }
    },
    [config, dashboardId, onResponse, queryClient, sessionId],
  );

  const confirmAction = useCallback(
    async (msg: ChatMessage) => {
      const preview = msg.meta?.action_preview?.preview;
      if (!preview?.action) return;
      setConfirmingJobId(msg.jobId || 'confirm');
      setError(null);
      try {
        const out = await api.bi.actions.confirm(config, {
          action: String(preview.action),
          payload: (preview.payload as Record<string, unknown>) || {},
          confirm: true,
          idempotency_key: preview.idempotency_key
            ? String(preview.idempotency_key)
            : undefined,
        });
        setMessages((prev) =>
          prev.map((m) => {
            if (m !== msg && !(msg.jobId && m.jobId === msg.jobId)) return m;
            const ap = {
              ...(m.meta?.action_preview || {}),
              status: 'executed',
              confirmed: true,
              result: out,
            };
            const nextMeta: BiChatResponse = {
              session_id: m.meta?.session_id || sessionId,
              reply: localizeUserMessage(String(out.message || out.status || t('bi.confirm.done'))),
              intent: m.meta?.intent || String(preview.action),
              widgets: m.meta?.widgets || [],
              answer_blocks: m.meta?.answer_blocks || [],
              ...(m.meta || {}),
              action_preview: ap,
              alert: (out.alert as BiChatResponse['alert']) || m.meta?.alert,
              schedule: (out.schedule as BiChatResponse['schedule']) || m.meta?.schedule,
              report: (out.report as BiChatResponse['report']) || m.meta?.report,
              saved_query: (out.saved_query as BiChatResponse['saved_query']) || m.meta?.saved_query,
              analytics: (out.analytics as BiChatResponse['analytics']) || m.meta?.analytics,
            };
            return {
              ...m,
              content: nextMeta.reply,
              meta: nextMeta,
            };
          }),
        );
        onResponse?.({
          session_id: sessionId,
          reply: String(out.message || out.status || ''),
          intent: String(preview.action),
          widgets: [],
          answer_blocks: [],
          action_preview: { status: 'executed', confirmed: true, result: out },
        } as BiChatResponse);
      } catch (err) {
        setError(localizeUserMessage((err as Error).message));
      } finally {
        setConfirmingJobId(null);
      }
    },
    [config, onResponse, sessionId],
  );

  const dismissConfirm = useCallback((msg: ChatMessage) => {
    setMessages((prev) =>
      prev.map((m) => {
        if (m !== msg && !(msg.jobId && m.jobId === msg.jobId)) return m;
        return {
          ...m,
          meta: m.meta
            ? {
                ...m.meta,
                action_preview: {
                  ...(m.meta.action_preview || {}),
                  status: 'dismissed',
                  confirmed: false,
                },
              }
            : m.meta,
        };
      }),
    );
  }, []);

  const refetchHistory = history.refetch;

  const sendMessage = useCallback(
    async (
      text: string,
      opts?: {
        prepared_sql?: string | null;
        prepared_params?: Record<string, unknown> | null;
        template_id?: string;
        optimistic?: BiChatResponse;
      },
    ) => {
      const payload = text.trim();
      // Allow consecutive prompts — server FIFO queue + separate stream per message.
      if (!payload) return;
      setError(null);
      setLastFailedText(null);
      suppressHistoryRef.current = false;
      drivingSendRef.current = true;
      setPendingCount((n) => n + 1);

      const perm = await ensureNotifyPermission();
      setNotifyPerm(perm);

      const intent = sendIntentRef.current;
      sendIntentRef.current = undefined;
      const apiMessage =
        intent === ALERT_CREATE_INTENT ? withAlertCreateHint(payload) : payload;

      const context: Record<string, unknown> | undefined = opts?.prepared_sql
        ? {
            prepared_sql: opts.prepared_sql,
            ...(opts.prepared_params ? { prepared_params: opts.prepared_params } : {}),
            ...(opts.template_id ? { template_id: opts.template_id } : {}),
            ...(intent ? { intent } : {}),
          }
        : intent
          ? { intent }
          : undefined;
      const optimistic = opts?.optimistic;

      const jobRef = { id: '' as string };
      // Streaming deltas are buffered and flushed once per animation frame:
      // one setMessages touching ONLY the streaming bubble instead of a full
      // timeline rebuild per token.
      let deltaBuffer = '';
      let deltaReset = false;
      let deltaFlushScheduled = false;
      const flushDeltas = () => {
        deltaFlushScheduled = false;
        const id = jobRef.id;
        if (!id || (!deltaBuffer && !deltaReset)) return;
        const chunk = deltaBuffer;
        const reset = deltaReset;
        deltaBuffer = '';
        deltaReset = false;
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.jobId === id && m.streaming);
          if (idx < 0) return prev;
          const msg = prev[idx]!;
          const next = [...prev];
          next[idx] = {
            ...msg,
            content: reset ? chunk : `${msg.content || ''}${chunk}`,
            liveTokens: true,
            streamPhase: 'composing',
            chatState: 'GENERATING_ANSWER',
          };
          return next;
        });
        setJobProgress((prev) => {
          const job = prev[id];
          // Bail out when the phase is unchanged — no state churn per token.
          if (!job || job.phase === 'composing') return prev;
          const tips = progressTipsForQuestion(job.question);
          const mapped = tipIndexForStreamPhase('composing', tips.length);
          const tipIndex = mapped == null ? job.tipIndex : Math.max(job.tipIndex, mapped);
          return { ...prev, [id]: { ...job, phase: 'composing', tipIndex } };
        });
      };
      const scheduleDeltaFlush = () => {
        if (deltaFlushScheduled) return;
        deltaFlushScheduled = true;
        if (typeof requestAnimationFrame === 'function') {
          requestAnimationFrame(flushDeltas);
        } else {
          window.setTimeout(flushDeltas, 50);
        }
      };
      const { jobId, promise, unsubscribe } = runBiChatJob(
        config,
        {
          message: apiMessage,
          session_id: sessionId,
          dashboard_id: dashboardId,
          db_name: activeDbName,
          context,
        },
        (ev) => {
          const id = jobRef.id;
          if (!id) return;
          if (ev.type === 'status') {
            const chatState = mapPhaseToChatState(ev.phase);
            const plan =
              ev.payload?.plan && typeof ev.payload.plan === 'object'
                ? (ev.payload.plan as Record<string, unknown>)
                : null;
            const followUps = Array.isArray(ev.payload?.followUps)
              ? (ev.payload!.followUps as string[]).filter((x) => typeof x === 'string')
              : undefined;
            setMessages((prev) =>
              prev.map((m) =>
                m.jobId === id && m.streaming
                  ? {
                      ...m,
                      streamPhase: ev.phase,
                      chatState,
                      queuePosition: typeof ev.position === 'number' ? ev.position : m.queuePosition,
                      queueMessage:
                        typeof ev.message === 'string' && ev.message
                          ? ev.message
                          : m.queueMessage,
                      elapsedSec: typeof ev.elapsed_sec === 'number' ? ev.elapsed_sec : m.elapsedSec,
                      draftSql:
                        typeof ev.payload?.sql === 'string'
                          ? String(ev.payload.sql)
                          : typeof plan?.sql === 'string'
                            ? String(plan.sql)
                            : m.draftSql,
                      scenarioSource:
                        ev.phase === 'scenario_hit' || ev.payload?.sql_source === 'precompiled_scenario'
                          ? true
                          : m.scenarioSource,
                      scenarioCode:
                        typeof ev.payload?.scenario_code === 'string'
                          ? String(ev.payload.scenario_code)
                          : m.scenarioCode,
                      followUps: followUps?.length ? followUps : m.followUps,
                      ...(plan
                        ? {
                            draftTables: Array.isArray(plan.tables)
                              ? (plan.tables as string[])
                              : m.draftTables,
                            draftColumns: Array.isArray(plan.columns)
                              ? (plan.columns as string[])
                              : m.draftColumns,
                            draftAssumptions: Array.isArray(plan.assumptions)
                              ? (plan.assumptions as string[])
                              : m.draftAssumptions,
                            draftWarnings: Array.isArray(plan.warnings)
                              ? (plan.warnings as string[])
                              : m.draftWarnings,
                            draftDialect:
                              typeof plan.dialect === 'string' ? plan.dialect : m.draftDialect,
                            draftConfidence:
                              typeof plan.confidence === 'number'
                                ? plan.confidence
                                : m.draftConfidence,
                          }
                        : {}),
                    }
                  : m,
              ),
            );
            // Track phase + jump tip index forward so long SQL work lands mid-checklist.
            setJobProgress((prev) => {
              const job = prev[id];
              if (!job) return prev;
              if (job.phase === ev.phase) return prev;
              const tips = progressTipsForQuestion(job.question);
              const mapped = tipIndexForStreamPhase(ev.phase, tips.length);
              const tipIndex =
                mapped == null ? job.tipIndex : Math.max(job.tipIndex, mapped);
              return { ...prev, [id]: { ...job, phase: ev.phase, tipIndex } };
            });
            return;
          }
          if (ev.type === 'schema_context') {
            setMessages((prev) =>
              prev.map((m) =>
                m.jobId === id && m.streaming
                  ? { ...m, draftTables: ev.tables, chatState: 'RETRIEVING_CONTEXT' }
                  : m,
              ),
            );
            return;
          }
          if (ev.type === 'sql_generated') {
            setMessages((prev) =>
              prev.map((m) =>
                m.jobId === id && m.streaming
                  ? {
                      ...m,
                      draftSql: ev.sql,
                      streamPhase: 'generating_sql',
                      chatState: 'GENERATING_SQL',
                    }
                  : m,
              ),
            );
            setJobProgress((prev) => {
              const job = prev[id];
              if (!job || job.phase === 'generating_sql') return prev;
              const tips = progressTipsForQuestion(job.question);
              const mapped = tipIndexForStreamPhase('generating_sql', tips.length);
              const tipIndex =
                mapped == null ? job.tipIndex : Math.max(job.tipIndex, mapped);
              return {
                ...prev,
                [id]: { ...job, phase: 'generating_sql', tipIndex },
              };
            });
            return;
          }
          if (ev.type === 'answer_delta') {
            deltaBuffer += ev.text;
            scheduleDeltaFlush();
            return;
          }
          if (ev.type === 'completed') {
            const p = ev.payload || {};
            setMessages((prev) =>
              prev.map((m) =>
                m.jobId === id && m.streaming
                  ? {
                      ...m,
                      chatState: 'COMPLETED',
                      draftSql: typeof p.sql === 'string' ? String(p.sql) : m.draftSql,
                      executionMode:
                        typeof p.execution_mode === 'string'
                          ? String(p.execution_mode)
                          : m.executionMode,
                    }
                  : m,
              ),
            );
            return;
          }
          if (ev.type === 'token') {
            if (ev.reset) {
              deltaBuffer = ev.t;
              deltaReset = true;
            } else {
              deltaBuffer += ev.t;
            }
            scheduleDeltaFlush();
          }
        },
        { fastPath: Boolean(opts?.prepared_sql) },
      );
      jobRef.id = jobId;

      if (!optimistic) {
        setJobProgress((prev) => ({
          ...prev,
          [jobId]: {
            question: payload,
            tipIndex: 0,
            startedAt: Date.now(),
            phase: context?.prepared_sql ? 'querying' : 'queued',
          },
        }));
      }

      setMessages((prev) => [
        ...prev,
        { id: newMessageId(), role: 'user', content: payload },
        optimistic
          ? {
              id: `job-${jobId}`,
              role: 'assistant',
              content: localizeUserMessage(optimistic.reply || t('bi.result.heroReady')),
              meta: optimistic,
              jobId,
              questionTitle: payload,
            }
          : {
              id: `job-${jobId}`,
              role: 'assistant',
              content: '',
              streaming: true,
              jobId,
              streamPhase: context?.prepared_sql ? 'querying' : 'queued',
              queuePosition: Math.max(1, biChatJobCount(sessionId)),
              questionTitle: payload,
            },
      ]);
      scrollToBottom(true);

      try {
        const result = await promise;

        // No fake typewriter — the full reply lands in one paint.
        setMessages((prev) => applyAssistantResult(prev, result, jobId));
        onResponse?.(result);
        void refetchHistory();
        void queryClient.invalidateQueries({ queryKey: ['bi-chat-suggestions'] });
        showWebNotification({
          title: t('bi.chat.notifyDoneTitle'),
          body: t('bi.chat.notifyDoneBody', { question: payload }),
          tag: `bi-chat-done-${jobId}`,
        });
      } catch (err) {
        const msg = localizeUserMessage((err as Error).message);
        setError(msg);
        setLastFailedText(payload);
        setMessages((prev) => {
          const next = prev.filter((m) => !(m.streaming && m.jobId === jobId) && !(optimistic && m.jobId === jobId && m.role === 'assistant'));
          // Keep optimistic bubble only if we already replaced it; on error remove job assistant
          const cleaned = next.filter((m) => !(m.jobId === jobId && m.role === 'assistant' && !m.streaming));
          const lastUser = [...cleaned]
            .map((m, i) => ({ m, i }))
            .reverse()
            .find(({ m }) => m.role === 'user' && m.content === payload);
          if (lastUser) {
            cleaned[lastUser.i] = { ...cleaned[lastUser.i], failed: true };
          }
          return cleaned;
        });
        showWebNotification({
          title: t('bi.chat.notifyFailedTitle'),
          body: t('bi.chat.notifyFailedBody', { question: payload }),
          tag: `bi-chat-fail-${jobId}`,
        });
      } finally {
        unsubscribe();
        setJobProgress((prev) => {
          const next = { ...prev };
          delete next[jobId];
          return next;
        });
        setPendingCount((n) => Math.max(0, n - 1));
        if (!isBiChatJobPending(sessionId)) {
          drivingSendRef.current = false;
        }
      }
    },
    [activeDbName, config, dashboardId, refetchHistory, onResponse, queryClient, scrollToBottom, sessionId],
  );

  const stopStreaming = useCallback(() => {
    abortBiChatJob(sessionId);
    setMessages((prev) =>
      prev.map((m) =>
        m.streaming ? { ...m, streaming: false, chatState: 'CANCELLED', content: m.content || 'İstek durduruldu.' } : m,
      ),
    );
    setPendingCount(0);
    drivingSendRef.current = false;
  }, [sessionId]);

  const beginFeedback = useCallback(
    (msg: ChatMessage, index: number, rating: -1 | 0 | 1) => {
      if (!flags.enableFeedback || msg.feedbackRating != null) return;
      setFeedbackDraft({ msgKey: msgFeedbackKey(msg, index), rating, comment: '' });
      setError(null);
    },
    [flags.enableFeedback],
  );

  const submitFeedbackDraft = useCallback(
    async (msg: ChatMessage, index: number) => {
      const draft = feedbackDraftRef.current;
      if (!flags.enableFeedback || !draft || msg.feedbackRating != null) return;
      if (draft.msgKey !== msgFeedbackKey(msg, index)) return;
      const { rating, comment } = draft;
      if (rating !== 1 && comment.trim().length < 5) {
        setError(t('bi.feedback.commentRequired'));
        return;
      }
      const question = msg.questionTitle || '';
      setFeedbackBusy(true);
      try {
        await submitQueryFeedback(config, {
          question,
          rating,
          comment: comment.trim() || undefined,
          sql: pickExportSql(msg.meta) || msg.draftSql,
          session_id: sessionId,
          datasource_id: activeDbName,
        });
        setMessages((prev) =>
          prev.map((m, i) =>
            i === index || (msg.jobId && m.jobId === msg.jobId) ? { ...m, feedbackRating: rating } : m,
          ),
        );
        setFeedbackDraft(null);
      } catch (err) {
        setError(localizeUserMessage((err as Error).message));
      } finally {
        setFeedbackBusy(false);
      }
    },
    [activeDbName, config, flags.enableFeedback, sessionId],
  );

  const sendTemplate = useCallback(
    (prompt: string, template: BiQueryTemplate) => {
      const sql = template.sql_hint?.trim() || null;
      const warm = sql ? getTemplateWarm(template.id) : undefined;
      const optimistic: BiChatResponse | undefined =
        warm?.ready && warm.result
          ? {
              session_id: sessionId,
              reply: 'ready',
              intent: 'query',
              sql: warm.sql,
              widgets: [],
              answer_blocks: [],
              query_result: warm.result,
              provenance: {
                type: 'prepared',
                selected_tables: template.table_name ? [template.table_name] : undefined,
                confidence: 0.95,
              },
            }
          : undefined;
      void sendMessage(prompt, {
        prepared_sql: sql,
        prepared_params: template.bind_params ?? null,
        template_id: template.id,
        optimistic,
      });
    },
    [sendMessage, sessionId],
  );

  const sendSuggestion = useCallback(
    (item: ChatSuggestionItem) => {
      const sql = item.sql_hint?.trim() || null;
      if (sql) {
        void sendMessage(item.text, {
          prepared_sql: sql,
          prepared_params: item.bind_params ?? null,
          template_id: item.scenarioCode || `suggestion:${item.source}`,
        });
        return;
      }
      void sendMessage(item.text);
    },
    [sendMessage],
  );

  // Stable handlers so memoized rows / the composer skip re-renders.
  const handleComposerSend = useCallback(
    (text: string) => {
      void sendMessage(text);
    },
    [sendMessage],
  );

  const handlePin = useCallback(
    (msg: ChatMessage, target?: { dashboardId?: number; vizType?: string } | number) => {
      void pinToDashboard(msg, target);
    },
    [pinToDashboard],
  );

  const handleConfirm = useCallback(
    (msg: ChatMessage) => {
      void confirmAction(msg);
    },
    [confirmAction],
  );

  const handleSubmitFeedback = useCallback(
    (msg: ChatMessage, index: number) => {
      void submitFeedbackDraft(msg, index);
    },
    [submitFeedbackDraft],
  );

  const handleFeedbackComment = useCallback((comment: string) => {
    setFeedbackDraft((d) => (d ? { ...d, comment } : d));
  }, []);

  const handleCancelFeedback = useCallback(() => {
    setFeedbackDraft(null);
  }, []);

  const clearChat = () => {
    abortBiChatJob(sessionId);
    setJobProgress({});
    suppressHistoryRef.current = true;
    setMessages([]);
    setComposerReset((n) => n + 1);
    setLastFailedText(null);
    setError(null);
  };

  const learnedSuggestions: ChatSuggestionItem[] = (suggestionsQ.data?.suggestions ?? []).filter(
    (s) => Boolean(s?.text?.trim()),
  );
  const suggestionKeys = embedded ? FALLBACK_SUGGESTION_KEYS.slice(0, 3) : FALLBACK_SUGGESTION_KEYS;
  const showLearnedSuggestions = learnedSuggestions.length > 0;

  return (
    <div
      className={clsx(
        embedded
          ? 'grid h-full min-h-0 max-h-full grid-rows-[minmax(0,1fr)_auto] overflow-hidden bg-transparent'
          : 'card grid h-full min-h-0 max-h-full grid-rows-[auto_minmax(0,1fr)_auto] overflow-hidden',
        className,
      )}
    >
      {!embedded && (
      <div className="bi-chat-panel-header relative z-10 flex shrink-0 items-center justify-between gap-2 border-b border-violet-200/50 bg-white/40 px-4 py-3 backdrop-blur-sm">
        <div className="flex min-w-0 items-center gap-2.5">
          <div
            className={clsx(
              'flex shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-blue-600 text-white shadow-md',
              fullHeight ? 'h-8 w-8' : 'h-9 w-9',
            )}
          >
            <Sparkles className={fullHeight ? 'h-3.5 w-3.5' : 'h-4 w-4'} />
          </div>
          <div className="min-w-0">
            <h3 className={clsx('truncate font-semibold text-slate-900', fullHeight && 'text-sm')}>
              {t('bi.chatTitle')}
            </h3>
            <p className="truncate text-xs text-slate-500">
              {history.isLoading ? t('bi.loadSession') : t('bi.chatWelcome')}
            </p>
          </div>
        </div>
        {messages.length > 0 && (
          <button
            type="button"
            className="btn-secondary inline-flex min-h-9 min-w-9 shrink-0 items-center justify-center px-2.5 py-1.5 text-xs"
            onClick={clearChat}
            aria-label={t('bi.chatClear')}
            title={t('bi.chatClear')}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      )}

      <div ref={scrollRef} className="relative z-10 min-h-0 overflow-y-auto overscroll-contain px-3 py-3 sm:px-4">
        {showWaitBanner && primaryJob ? (
          <div
            className="sticky top-0 z-20 mb-3 rounded-xl border border-violet-200/80 bg-gradient-to-r from-violet-50 to-sky-50 px-3 py-2.5 shadow-sm"
            role="status"
            aria-live="polite"
          >
            <div className="flex items-start gap-2.5">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-100 text-violet-700">
                {notifyPerm === 'granted' ? <Bell className="h-4 w-4" /> : <BellOff className="h-4 w-4" />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-violet-950">{t('bi.chat.notifyBanner')}</p>
                <p className="mt-0.5 line-clamp-2 text-xs text-violet-800/90">
                  {t('bi.chat.notifyAbout', { question: primaryJob.question })}
                </p>
                {notifyPerm === 'default' || notifyPerm === 'denied' || notifyPerm === 'unsupported' ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <p className="text-[11px] text-slate-600">{t('bi.chat.notifyPermissionHint')}</p>
                    {notifyPerm === 'default' ? (
                      <button
                        type="button"
                        className="inline-flex min-h-8 items-center rounded-lg bg-violet-600 px-2.5 py-1 text-[11px] font-semibold text-white"
                        onClick={() => {
                          void ensureNotifyPermission().then(setNotifyPerm);
                        }}
                      >
                        {t('bi.chat.notifyEnable')}
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              <Loader2 className="mt-1 h-4 w-4 shrink-0 animate-spin text-violet-600" />
            </div>
          </div>
        ) : null}

        {messages.length === 0 && !pending && (
          <div
            className={clsx(
              embedded
                ? 'space-y-2 text-left'
                : 'flex flex-col items-center justify-center px-2 text-center',
              !embedded && (fullHeight ? 'py-4' : 'py-6'),
            )}
          >
            {!embedded && (
              <>
                <div
                  className={clsx(
                    'mb-3 flex items-center justify-center rounded-2xl bg-violet-100/80 text-violet-600',
                    fullHeight ? 'h-11 w-11' : 'mb-4 h-14 w-14',
                  )}
                >
                  <MessageSquareText className={fullHeight ? 'h-5 w-5' : 'h-7 w-7'} />
                </div>
                <h4 className={clsx('mb-1 font-semibold text-slate-900', fullHeight ? 'text-sm' : 'text-base')}>
                  {t('bi.chatEmptyTitle')}
                </h4>
                <p className={clsx('mb-4 max-w-xs text-slate-500', fullHeight ? 'text-xs' : 'mb-5 text-sm')}>
                  {t('bi.chatHint')}
                </p>
              </>
            )}
            {embedded && (
              <p className="text-xs font-medium text-slate-600">
                {showLearnedSuggestions && (suggestionsQ.data?.learned_count ?? 0) > 0
                  ? t('bi.analytics.chatSuggestionsLearned')
                  : t('bi.analytics.chatSuggestions')}
              </p>
            )}
            {showLearnedSuggestions ? (
              <div className={clsx('flex flex-col gap-2', embedded ? 'w-full' : 'w-full max-w-md')}>
                {learnedSuggestions.some((s) => s.source === 'scenario') && (
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    {learnedSuggestions.find((s) => s.source === 'scenario' && s.category)?.category ||
                      t('bi.scenario.suggestionsCategory')}
                  </p>
                )}
                {learnedSuggestions.slice(0, suggestionLimit).map((item) => {
                  const ready = Boolean(item.sql_hint?.trim());
                  return (
                  <button
                    key={`${item.source}:${item.text}`}
                    type="button"
                    className="ai-pill w-full justify-start px-3 py-2 text-left text-sm normal-case tracking-normal"
                    onClick={() => sendSuggestion(item)}
                  >
                    <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-500" />
                    <span className="line-clamp-2">{item.text}</span>
                    {ready ? (
                      <span className="ml-auto shrink-0 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800">
                        {t('bi.scenario.readyBadge')}
                      </span>
                    ) : null}
                  </button>
                  );
                })}
              </div>
            ) : (templates.data?.templates ?? []).length > 0 ? (
              <BiQueryTemplateGrid
                compact
                limit={suggestionLimit}
                templates={templates.data?.templates ?? []}
                loading={templates.isLoading}
                warmReadyIds={
                  // warmTick forces re-render when background warm finishes
                  (() => {
                    void warmTick;
                    return new Set(
                      (templates.data?.templates ?? [])
                        .filter((tpl) => getTemplateWarm(tpl.id)?.ready)
                        .map((tpl) => tpl.id),
                    );
                  })()
                }
                onSelect={(prompt, tpl) => sendTemplate(prompt, tpl)}
              />
            ) : (
              <div className={clsx('flex flex-col gap-2', embedded ? 'w-full' : 'w-full max-w-md')}>
                {suggestionKeys.map((key) => (
                  <button key={key} type="button" className="ai-pill w-full justify-start px-3 py-2 text-left text-sm normal-case tracking-normal" onClick={() => sendMessage(t(key))}>
                    <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-500" />
                    <span className="line-clamp-2">{t(key)}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="space-y-4">
        {messages.map((m, i) => {
          const pinKey = messagePinKey(m);
          const fbKey = msgFeedbackKey(m, i);
          return (
            <MessageRow
              key={m.id}
              message={m}
              index={i}
              job={m.jobId ? jobProgress[m.jobId] : undefined}
              dashboardId={dashboardId}
              fullHeight={fullHeight}
              showSqlPanel={Boolean(showSqlPanel)}
              enableFeedback={Boolean(flags.enableFeedback)}
              enableTestExecution={Boolean(flags.enableTestExecution)}
              pinning={pinningKey === pinKey}
              pinned={Boolean(pinnedKeys[pinKey])}
              pinnedBoardId={
                pinnedBoardByKey[pinKey] || Number(m.meta?.analytics?.dashboard_id || 0) || null
              }
              confirming={confirmingJobId === (m.jobId || 'confirm')}
              feedbackBusy={feedbackBusy}
              feedbackDraft={feedbackDraft?.msgKey === fbKey ? feedbackDraft : null}
              config={config}
              onSend={handleComposerSend}
              onPin={handlePin}
              onConfirm={handleConfirm}
              onDismissConfirm={dismissConfirm}
              onBeginFeedback={beginFeedback}
              onSubmitFeedback={handleSubmitFeedback}
              onFeedbackComment={handleFeedbackComment}
              onCancelFeedback={handleCancelFeedback}
            />
          );
        })}

        {error && (
          <div className="mx-1 rounded-xl border border-status-fail/30 bg-red-50/80 px-4 py-3 text-sm">
            <p className="font-medium text-status-fail">{error}</p>
            {lastFailedText && (
              <button type="button" className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-violet-700 hover:underline" onClick={() => sendMessage(lastFailedText)}>
                <RotateCcw className="h-3.5 w-3.5" /> {t('bi.chatRetry')}
              </button>
            )}
          </div>
        )}
        </div>
      </div>

      <BiChatComposer
        pending={pending}
        embedded={embedded}
        autoFocus={autoFocus}
        sessionId={sessionId}
        prefill={initialMessage}
        showEmptyHint={Boolean(embedded && messages.length === 0 && !pending)}
        resetSignal={composerReset}
        onSend={handleComposerSend}
        onStop={stopStreaming}
      />
    </div>
  );
}
