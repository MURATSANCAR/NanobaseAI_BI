import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
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
  RotateCcw,
  Search,
  Send,
  Sparkles,
  Trash2,
  User,
} from 'lucide-react';
import clsx from 'clsx';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';
import { brandText } from '@/utils/brand';
import { stripSqlFromChatText } from '@/utils/biChatSanitize';
import { revealText } from '@/lib/biChatStream';
import { localizeUserMessage } from '@/utils/backendLabels';
import {
  biChatJobCount,
  getBiChatJobsSettled,
  isBiChatJobPending,
  runBiChatJob,
} from '@/lib/biChatRunner';
import { progressTipsForQuestion, streamingStepProgress } from '@/lib/biChatProgressTips';
import {
  ensureNotifyPermission,
  getNotifyPermission,
  showWebNotification,
  type NotifyPermission,
} from '@/lib/webNotifications';
import { BiAnswerBlocks } from '@/components/BiWidgets';
import BiChatWidgetPreview from '@/components/bi/BiChatWidgetPreview';
import BiPinToDashboardControl from '@/components/bi/BiPinToDashboardControl';
import BiChatResultHero, { isHeroScalarResult } from '@/components/bi/BiChatResultHero';
import BiExportMenu from '@/components/bi/BiExportMenu';
import BiLineageDrawer from '@/components/bi/BiLineageDrawer';
import BiProvePanel from '@/components/bi/BiProvePanel';
import BiScenarioSliders from '@/components/bi/BiScenarioSliders';
import BiQueryTemplateGrid from '@/components/bi/BiQueryTemplateGrid';
import BiVoiceInput from '@/components/bi/BiVoiceInput';
import type { BiChatResponse, BiQueryTemplate } from '@/api/types';
import { getTemplateWarm, warmTemplatesInBackground } from '@/lib/biTemplateWarm';

type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
  meta?: BiChatResponse;
  failed?: boolean;
  streaming?: boolean;
  /** Ties an assistant placeholder to an in-flight/queued job. */
  jobId?: string;
  streamPhase?: string;
  queuePosition?: number;
  elapsedSec?: number;
  /** True once live tokens arrived — skip fake reveal on done. */
  liveTokens?: boolean;
};

function mapHistoryMessages(raw: unknown[]): ChatMessage[] {
  return raw.map((m) => {
    const msg = m as { role: string; content: string; meta?: BiChatResponse };
    return {
      role: msg.role === 'user' ? 'user' : 'assistant',
      content: msg.content,
      meta: msg.meta,
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
        role: 'assistant',
        content: '',
        streaming: true,
        jobId,
        streamPhase: 'thinking',
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
  const content = localizeUserMessage(result.reply || '');
  const next = [...prev];
  const idx = jobId
    ? next.findIndex((m) => m.jobId === jobId && m.role === 'assistant')
    : next.findIndex((m) => m.streaming);
  if (idx >= 0) {
    next[idx] = { role: 'assistant', content, meta: result, jobId };
    return next;
  }
  return [...next, { role: 'assistant', content, meta: result }];
}

function statusLabelForMessage(m: ChatMessage): string {
  const phase = m.streamPhase || 'thinking';
  if (phase === 'queued') {
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
  };
  const key = phaseKey[phase] || 'bi.streamingThinking';
  return t(key);
}

function BiChatStreamingSteps({
  question,
  tipIndex,
  phase,
  queuePosition,
}: {
  question: string;
  tipIndex: number;
  phase?: string;
  queuePosition?: number;
}) {
  const steps = progressTipsForQuestion(question);
  const active = streamingStepProgress(tipIndex, steps.length);
  const queued = phase === 'queued';
  const label = queued
    ? t('bi.streamingQueued', { position: String(Math.max(1, queuePosition ?? 1)) })
    : steps[active] || t('bi.streamingThinking');

  return (
    <div className="space-y-3" aria-live="polite" aria-busy="true">
      <p
        key={`${queued ? 'q' : 's'}-${active}-${label.slice(0, 32)}`}
        className="bi-chat-status-line flex items-start gap-2 text-sm font-medium leading-snug text-violet-900"
      >
        <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin text-violet-600" aria-hidden />
        <span>{label}</span>
      </p>
      {!queued && steps.length > 1 ? (
        <div className="flex items-center gap-1.5 px-0.5" aria-hidden>
          {steps.map((_, i) => (
            <span
              key={i}
              className={clsx(
                'h-1 rounded-full transition-all duration-500',
                i < active && 'w-1 bg-emerald-400',
                i === active && 'w-4 bg-violet-500',
                i > active && 'w-1 bg-slate-200',
              )}
            />
          ))}
        </div>
      ) : null}
      <p className="text-xs leading-snug text-slate-500">{t('bi.chat.progressTip.readySoon')}</p>
    </div>
  );
}

type BiChatPanelProps = {
  sessionId: string;
  dashboardId?: string;
  onResponse?: (resp: BiChatResponse) => void;
  className?: string;
  initialMessage?: string;
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

export default function BiChatPanel({
  sessionId,
  dashboardId,
  onResponse,
  className,
  initialMessage,
  fullHeight,
  embedded,
  autoFocus,
}: BiChatPanelProps) {
  const { config } = useApiConfig();
  const templates = useQuery({
    queryKey: ['bi-templates', config],
    queryFn: () => api.bi.templates(config),
    enabled: isRunnerConfigured(config),
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

  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [lastFailedText, setLastFailedText] = useState<string | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [notifyPerm, setNotifyPerm] = useState<NotifyPermission>(() => getNotifyPermission());
  const [jobProgress, setJobProgress] = useState<
    Record<string, { question: string; tipIndex: number; startedAt: number; phase?: string }>
  >({});
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const prefilledRef = useRef<string | null>(null);
  /** This mount owns the live send UI — remount reattach must not steal it. */
  const drivingSendRef = useRef(false);
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

  useEffect(() => {
    // Live/background job owns the timeline until it settles.
    if (pending || isBiChatJobPending(sessionId) || drivingSendRef.current) return;
    const raw = history.data?.messages ?? [];
    if (!raw.length) {
      setMessages([]);
      return;
    }
    setMessages(mapHistoryMessages(raw));
  }, [history.data, sessionId, pending]);

  useEffect(() => {
    if (initialMessage && prefilledRef.current !== `${sessionId}:${initialMessage}`) {
      prefilledRef.current = `${sessionId}:${initialMessage}`;
      setInput(initialMessage);
    }
  }, [initialMessage, sessionId]);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, pending, scrollToBottom]);

  useEffect(() => {
    if (!autoFocus) return;
    const id = window.setTimeout(() => textareaRef.current?.focus(), 80);
    return () => window.clearTimeout(id);
  }, [autoFocus, sessionId]);

  /** Advance friendly progress steps one-at-a-time (ChatGPT-style cadence). */
  useEffect(() => {
    if (!showWaitBanner) return;
    const id = window.setInterval(() => {
      setJobProgress((prev) => {
        const next: typeof prev = {};
        let changed = false;
        for (const [jobId, job] of Object.entries(prev)) {
          if (job.phase === 'queued') {
            next[jobId] = job;
            continue;
          }
          const tips = progressTipsForQuestion(job.question);
          const maxIdx = Math.max(0, tips.length - 1);
          const advanced = Math.min(job.tipIndex + 1, maxIdx);
          next[jobId] = advanced === job.tipIndex ? job : { ...job, tipIndex: advanced };
          if (advanced !== job.tipIndex) changed = true;
        }
        return changed ? next : prev;
      });
    }, 1800);
    return () => window.clearInterval(id);
  }, [showWaitBanner]);

  // Reattach after navigation: client job(s) still running, or server still processing.
  useEffect(() => {
    if (!isRunnerConfigured(config) || !sessionId || drivingSendRef.current) return;

    const settled = getBiChatJobsSettled(sessionId);
    if (settled) {
      setPendingCount((n) => Math.max(n, biChatJobCount(sessionId)));
      setMessages((prev) =>
        ensureStreamingBubble(prev.length ? prev : mapHistoryMessages(history.data?.messages ?? [])),
      );
      let cancelled = false;
      void settled.finally(async () => {
        if (cancelled) return;
        try {
          const snap = await api.bi.chatHistory(config, sessionId);
          setMessages(mapHistoryMessages(snap.messages ?? []));
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
      ensureStreamingBubble(prev.length ? prev : mapHistoryMessages(history.data?.messages ?? [])),
    );

    let cancelled = false;
    const poll = window.setInterval(() => {
      void (async () => {
        try {
          const snap = await api.bi.chatHistory(config, sessionId);
          if (cancelled) return;
          if (snap.pending) {
            setMessages(ensureStreamingBubble(mapHistoryMessages(snap.messages ?? [])));
            return;
          }
          window.clearInterval(poll);
          const mapped = mapHistoryMessages(snap.messages ?? []);
          setMessages(mapped);
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

  const messagePinKey = (msg: ChatMessage) =>
    msg.jobId || `${msg.role}-${(msg.meta?.sql || msg.content || '').slice(0, 48)}`;

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
        if (!Number.isFinite(dashId) || dashId <= 0) {
          // Never create a second board with the same title — reuse if present.
          const boards = await api.bi.analytics.dashboards(config);
          const needle = title.trim().toLowerCase();
          const match = (boards.dashboards || []).find(
            (d) => String(d.title || '').trim().toLowerCase() === needle,
          );
          if (match?.id) {
            dashId = Number(match.id);
          } else {
            const created = await api.bi.analytics.createDashboard(config, { title });
            dashId = Number(created.id || 0);
          }
        }
        if (!Number.isFinite(dashId) || dashId <= 0) {
          throw new Error('analytics_not_configured');
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
          }));
        const out = await api.bi.analytics.pin(config, dashId, {
          sql,
          title,
          viz_type: vizType || widgets[0]?.type || 'table',
          widgets: widgets.length ? widgets : undefined,
        });
        const resolvedDash = Number(out.dashboard_id || dashId);
        setPinnedKeys((prev) => ({ ...prev, [key]: true }));
        if (Number.isFinite(resolvedDash) && resolvedDash > 0) {
          setPinnedBoardByKey((prev) => ({ ...prev, [key]: resolvedDash }));
        }
        const nextMeta: BiChatResponse = {
          session_id: msg.meta?.session_id || sessionId,
          reply: msg.meta?.reply || msg.content,
          intent: 'pin',
          widgets: msg.meta?.widgets || [],
          answer_blocks: msg.meta?.answer_blocks || [],
          ...(msg.meta || {}),
          analytics: {
            ...(msg.meta?.analytics || {}),
            dashboard_id: resolvedDash,
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
    [config, dashboardId, onResponse, sessionId],
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

  const sendMessage = useCallback(
    async (
      text?: string,
      opts?: { prepared_sql?: string | null; template_id?: string; optimistic?: BiChatResponse },
    ) => {
      const payload = (text ?? input).trim();
      // Allow consecutive prompts — server FIFO queue + separate stream per message.
      if (!payload) return;
      setInput('');
      setError(null);
      setLastFailedText(null);
      drivingSendRef.current = true;
      setPendingCount((n) => n + 1);

      const perm = await ensureNotifyPermission();
      setNotifyPerm(perm);

      const context: Record<string, unknown> | undefined = opts?.prepared_sql
        ? {
            prepared_sql: opts.prepared_sql,
            ...(opts.template_id ? { template_id: opts.template_id } : {}),
          }
        : undefined;
      const optimistic = opts?.optimistic;

      const jobRef = { id: '' as string };
      let sawLiveTokens = false;
      const { jobId, promise, unsubscribe } = runBiChatJob(
        config,
        { message: payload, session_id: sessionId, dashboard_id: dashboardId, context },
        (ev) => {
          const id = jobRef.id;
          if (!id) return;
          if (ev.type === 'status') {
            setMessages((prev) =>
              prev.map((m) =>
                m.jobId === id && m.streaming
                  ? {
                      ...m,
                      streamPhase: ev.phase,
                      queuePosition: typeof ev.position === 'number' ? ev.position : m.queuePosition,
                      elapsedSec: typeof ev.elapsed_sec === 'number' ? ev.elapsed_sec : m.elapsedSec,
                    }
                  : m,
              ),
            );
            // Tip cadence is timer-driven; only track phase so we pause while queued.
            setJobProgress((prev) => {
              const job = prev[id];
              if (!job || job.phase === ev.phase) return prev;
              return { ...prev, [id]: { ...job, phase: ev.phase } };
            });
            return;
          }
          if (ev.type === 'token') {
            sawLiveTokens = true;
            setMessages((prev) =>
              prev.map((m) => {
                if (!(m.jobId === id && m.streaming)) return m;
                const nextContent = ev.reset ? ev.t : `${m.content || ''}${ev.t}`;
                return {
                  ...m,
                  content: nextContent,
                  liveTokens: true,
                  streamPhase: 'composing',
                };
              }),
            );
          }
        },
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
        { role: 'user', content: payload },
        optimistic
          ? {
              role: 'assistant',
              content: localizeUserMessage(optimistic.reply || t('bi.result.heroReady')),
              meta: optimistic,
              jobId,
            }
          : {
              role: 'assistant',
              content: '',
              streaming: true,
              jobId,
              streamPhase: context?.prepared_sql ? 'querying' : 'queued',
              queuePosition: Math.max(1, biChatJobCount(sessionId)),
            },
      ]);

      try {
        const result = await promise;

        if (!sawLiveTokens && !optimistic) {
          await revealText(result.reply || '', (partial) => {
            setMessages((prev) => {
              const next = [...prev];
              const idx = next.findIndex((m) => m.streaming && m.jobId === jobId);
              if (idx < 0) return next;
              next[idx] = { role: 'assistant', content: partial, streaming: true, jobId };
              return next;
            });
          });
        }

        setMessages((prev) => applyAssistantResult(prev, result, jobId));
        onResponse?.(result);
        void history.refetch();
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
    [config, dashboardId, history, input, onResponse, sessionId],
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
        template_id: template.id,
        optimistic,
      });
    },
    [sendMessage, sessionId],
  );

  const clearChat = () => {
    setMessages([]);
    setInput('');
    setLastFailedText(null);
    setError(null);
  };

  const suggestionLimit = embedded ? 3 : 6;
  const suggestionKeys = embedded ? FALLBACK_SUGGESTION_KEYS.slice(0, 3) : FALLBACK_SUGGESTION_KEYS;

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
              <p className="text-xs font-medium text-slate-600">{t('bi.analytics.chatSuggestions')}</p>
            )}
            {(templates.data?.templates ?? []).length > 0 ? (
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
        {messages.map((m, i) => (
          <div key={i} className={clsx('flex gap-2.5 animate-slide-up sm:gap-3', m.role === 'user' ? 'flex-row-reverse' : 'flex-row')}>
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
              {m.role === 'assistant' && m.meta?.intent && !m.streaming && (
                <div className="mb-2 flex flex-wrap items-center gap-1.5">
                  {(() => {
                    const Icon = intentIcon(m.meta.intent);
                    return (
                      <span className="bi-pbi-type-chip bi-pbi-type-chip--compact">
                        <Icon className="h-3 w-3" />
                        {intentLabel(m.meta.intent)}
                      </span>
                    );
                  })()}
                </div>
              )}
              <div className="min-w-0">
                {(() => {
                  if (m.streaming && !m.content && m.jobId && jobProgress[m.jobId]) {
                    const job = jobProgress[m.jobId]!;
                    return (
                      <BiChatStreamingSteps
                        question={job.question}
                        tipIndex={job.tipIndex}
                        phase={m.streamPhase}
                        queuePosition={m.queuePosition}
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
                  const raw = m.content;
                  if (!raw) return null;
                  // Hero KPI owns the answer — skip weak "1 row / ready" chatter.
                  if (
                    m.role === 'assistant' &&
                    !m.streaming &&
                    m.meta &&
                    isHeroScalarResult(m.meta) &&
                    /^(ready|query_result_ready|\d+\s+satır|\d+\s+row)/i.test(raw.trim())
                  ) {
                    return null;
                  }
                  return (
                    <p className="whitespace-pre-wrap break-anywhere leading-relaxed">
                      {m.role === 'assistant' ? assistantDisplayText(raw, m.streaming) : raw}
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
              {m.meta?.query_result && !m.meta.widgets?.length && !m.streaming && (
                <BiChatResultHero meta={m.meta} />
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
                        disabled={confirmingJobId === (m.jobId || 'confirm')}
                        onClick={() => void confirmAction(m)}
                      >
                        {confirmingJobId === (m.jobId || 'confirm') ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          t('bi.confirm.approve')
                        )}
                      </button>
                      <button
                        type="button"
                        className="btn-secondary h-8 px-3 text-xs"
                        disabled={confirmingJobId === (m.jobId || 'confirm')}
                        onClick={() => dismissConfirm(m)}
                      >
                        {t('bi.confirm.dismiss')}
                      </button>
                    </div>
                  </div>
                )}
              {m.meta?.widgets && m.meta.widgets.length > 0 && !m.streaming && (
                <BiChatWidgetPreview
                  widgets={m.meta.widgets}
                  dashboardId={dashboardId}
                  pinned={Boolean(pinnedKeys[messagePinKey(m)])}
                  pinnedDashboardId={
                    pinnedBoardByKey[messagePinKey(m)] ||
                    Number(m.meta.analytics?.dashboard_id || 0) ||
                    null
                  }
                  pinning={pinningKey === messagePinKey(m)}
                  onPin={(sel) => void pinToDashboard(m, sel)}
                />
              )}
              {m.role === 'assistant' &&
                !m.streaming &&
                pickExportSql(m.meta) &&
                !(m.meta?.widgets && m.meta.widgets.length > 0) && (
                  <div className="mt-2 flex w-full justify-end">
                    <BiPinToDashboardControl
                      pinning={pinningKey === messagePinKey(m)}
                      pinned={Boolean(pinnedKeys[messagePinKey(m)])}
                      pinnedDashboardId={
                        pinnedBoardByKey[messagePinKey(m)] ||
                        Number(m.meta?.analytics?.dashboard_id || 0) ||
                        null
                      }
                      preferredDashboardId={dashboardId}
                      preferredVizType="table"
                      onPin={(sel) => void pinToDashboard(m, sel)}
                    />
                  </div>
                )}
              {m.role === 'assistant' && !m.streaming && pickExportSql(m.meta) && (
                <div className="mt-2 flex w-full max-w-lg flex-col items-stretch gap-2 self-end sm:max-w-md">
                  <div className="flex flex-wrap justify-end gap-2">
                    <BiExportMenu sql={pickExportSql(m.meta)} />
                  </div>
                  <BiProvePanel
                    config={config}
                    answerMd={String(m.content || '')}
                    sql={pickExportSql(m.meta) || undefined}
                    sqlFingerprint={m.meta?.provenance?.sql_fingerprint}
                    provenance={m.meta?.provenance as Record<string, unknown> | undefined}
                  />
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
        ))}

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

      <div
        className={clsx(
          'relative z-20 shrink-0 border-t border-violet-200/80 bg-white p-3 shadow-[0_-8px_24px_rgba(15,23,42,0.08)] sm:p-3',
          embedded && 'pb-[max(0.75rem,env(safe-area-inset-bottom))]',
        )}
      >
        {embedded && messages.length === 0 && !pending && (
          <p className="mb-2 text-center text-[11px] font-medium text-violet-700">{t('bi.analytics.typeBelow')}</p>
        )}
        <div className="flex items-end gap-2 rounded-xl border border-violet-300/80 bg-white p-2 shadow-sm focus-within:border-violet-500 focus-within:ring-2 focus-within:ring-violet-400/25">
          <BiVoiceInput
            onTranscript={(text) => {
              const trimmed = text.trim();
              if (!trimmed) return;
              setInput(trimmed);
              void sendMessage(trimmed);
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
                sendMessage();
              }
            }}
          />
          <button type="button" className="btn-primary h-11 w-11 shrink-0 rounded-lg p-0 sm:h-10 sm:w-10" disabled={!input.trim()} onClick={() => sendMessage()}>
            {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>
        {!embedded && <p className="mt-2 hidden text-center text-[11px] text-slate-400 sm:block">{t('bi.chatSendHint')}</p>}
      </div>
    </div>
  );
}
