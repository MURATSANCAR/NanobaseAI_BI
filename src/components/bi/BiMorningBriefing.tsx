import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  ChevronDown,
  Lightbulb,
  MessageSquare,
  Sparkles,
  TrendingUp,
  X,
} from 'lucide-react';
import clsx from 'clsx';
import { Link } from 'react-router-dom';
import { api, isRunnerConfigured, type ApiConfig } from '@/api/client';
import { getLocale, t } from '@/i18n';

type AttentionItem = {
  id: string;
  kind: string;
  tone?: string;
  title?: string;
  title_key?: string;
  body?: string | null;
  body_key?: string;
  body_vars?: Record<string, string | number>;
  /** Legacy alias — prefer body_vars */
  body_params?: Record<string, string | number>;
  delta_pct?: number | null;
  today?: number | null;
  value_label?: string | null;
  table?: string | null;
  period?: string | null;
  ask_prompt?: string;
  href?: string | null;
};

type Props = {
  config: ApiConfig;
  boardId?: string;
  onAskInChat?: (prompt?: string) => void;
  compact?: boolean;
  /** When false, start collapsed so analytics canvas keeps the viewport. */
  defaultOpen?: boolean;
  /** Skip extra status fetches — use briefing pulse + parent analytics status cache. */
  light?: boolean;
};

function itemVars(item: AttentionItem): Record<string, string | number> | undefined {
  return item.body_vars || item.body_params;
}

function itemTitle(item: AttentionItem): string {
  if (item.title_key) {
    const tr = t(item.title_key, itemVars(item));
    if (tr && tr !== item.title_key) return tr;
  }
  return item.title || t('bi.wow.actionGeneric');
}

function itemBody(item: AttentionItem): string {
  if (item.body_key) {
    const tr = t(item.body_key, itemVars(item) || {});
    if (tr && tr !== item.body_key && !tr.includes('{')) return tr;
  }
  return item.body || '';
}

function toneClasses(tone?: string): string {
  if (tone === 'negative') return 'bi-pulse-card bi-pulse-card--neg';
  if (tone === 'positive') return 'bi-pulse-card bi-pulse-card--pos';
  if (tone === 'attention') return 'bi-pulse-card bi-pulse-card--attn';
  return 'bi-pulse-card bi-pulse-card--neutral';
}

function AttentionCards({
  attention,
  insights,
  dbOk,
  reportsOk,
  tableCount,
  onAskInChat,
  runAsk,
}: {
  attention: AttentionItem[];
  insights: Array<{ title?: string; body?: string }>;
  dbOk: boolean;
  reportsOk: boolean;
  tableCount: number;
  onAskInChat?: (prompt?: string) => void;
  runAsk: (prompt?: string) => void;
}) {
  if (attention.length > 0) {
    const budget = attention.filter((i) => i.kind === 'budget');
    const kpis = attention.filter((i) => i.kind === 'kpi');
    const other = attention.filter((i) => i.kind !== 'budget' && i.kind !== 'kpi');

    return (
      <div className="grid gap-3">
        {budget.map((item) => {
          const body = itemBody(item);
          return (
            <button
              key={item.id}
              type="button"
              className={`group ${toneClasses(item.tone)} bi-pulse-card--budget`}
              onClick={() => {
                if (item.ask_prompt) runAsk(item.ask_prompt);
                else if (item.href) window.location.assign(item.href);
              }}
            >
              <div className="flex items-start gap-3">
                <span className="bi-pulse-card-icon" aria-hidden>
                  <AlertTriangle className="h-4 w-4" />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold leading-snug">{itemTitle(item)}</p>
                  {body ? <p className="mt-1 text-xs leading-relaxed opacity-90">{body}</p> : null}
                  <span className="bi-pulse-card-cta">{t('bi.wow.briefingDigIn')}</span>
                </div>
              </div>
            </button>
          );
        })}

        {kpis.length > 0 ? (
          <div className="grid gap-2.5 sm:grid-cols-2">
            {kpis.slice(0, 6).map((item) => {
              const value =
                item.value_label ||
                (item.body?.includes('(') ? item.body.split('(')[0].trim() : item.body) ||
                '—';
              const delta =
                item.delta_pct != null && !Number.isNaN(Number(item.delta_pct))
                  ? Number(item.delta_pct)
                  : null;
              const Icon =
                item.tone === 'positive' ? ArrowUpRight : item.tone === 'negative' ? ArrowDownRight : TrendingUp;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`group ${toneClasses(item.tone)} bi-pulse-card--kpi`}
                  onClick={() => {
                    if (item.ask_prompt) runAsk(item.ask_prompt);
                    else if (item.href) window.location.assign(item.href);
                  }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="min-w-0 text-[11px] font-semibold uppercase tracking-wide opacity-70">
                      {itemTitle(item)}
                    </p>
                    <Icon className="h-3.5 w-3.5 shrink-0 opacity-70" />
                  </div>
                  <p className="bi-pulse-card-value">{value}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] opacity-75">
                    {delta != null ? (
                      <span className={delta >= 0 ? 'text-emerald-700' : 'text-rose-700'}>
                        {delta > 0 ? '+' : ''}
                        {delta.toFixed(1)}%
                      </span>
                    ) : null}
                    {item.table ? <span className="truncate font-mono text-[10px]">{item.table}</span> : null}
                  </div>
                  <span className="bi-pulse-card-cta">{t('bi.wow.briefingDigIn')}</span>
                </button>
              );
            })}
          </div>
        ) : null}

        {other.slice(0, 4).map((item) => {
          const body = itemBody(item);
          const Icon =
            item.kind === 'insight'
              ? Lightbulb
              : item.kind === 'alert'
                ? AlertTriangle
                : TrendingUp;
          return (
            <button
              key={item.id}
              type="button"
              className={`group ${toneClasses(item.tone)}`}
              onClick={() => {
                if (item.ask_prompt) runAsk(item.ask_prompt);
                else if (item.href) window.location.assign(item.href);
              }}
            >
              <div className="mb-1 flex items-start gap-2">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 opacity-80" />
                <p className="min-w-0 flex-1 text-sm font-semibold leading-snug">{itemTitle(item)}</p>
              </div>
              {body ? <p className="pl-6 text-xs leading-relaxed opacity-90">{body}</p> : null}
              {(item.ask_prompt || item.href) && (
                <span className="bi-pulse-card-cta pl-6">{t('bi.wow.briefingDigIn')}</span>
              )}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-white/15 bg-white/10 px-3 py-3 text-sm text-sky-50/95">
      <p>{t('bi.wow.briefingExecEmptyHint')}</p>
      {insights[0]?.body ? <p className="mt-2 text-xs text-sky-100/80">{insights[0].body}</p> : null}
      <div className="mt-2 flex flex-wrap gap-2">
        {!dbOk ? (
          <Link
            to="/bi/sources"
            className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-sky-900"
          >
            {t('bi.wow.briefingConnectSource')}
          </Link>
        ) : null}
        {dbOk && tableCount > 0 ? (
          <Link
            to="/bi/schema"
            className="rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-sky-900"
          >
            {t('bi.schemaOpenCta')}
          </Link>
        ) : null}
        {!reportsOk ? (
          <span className="rounded-full bg-amber-400/20 px-3 py-1.5 text-xs font-medium text-amber-100 ring-1 ring-amber-300/30">
            {t('bi.wow.briefingReportsSoft')}
          </span>
        ) : null}
        {onAskInChat ? (
          <button
            type="button"
            className="rounded-full bg-white/15 px-3 py-1.5 text-xs font-semibold text-white ring-1 ring-white/25"
            onClick={() => runAsk(t('bi.wow.demoAskClaims'))}
          >
            {t('bi.wow.briefingAskCta')}
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** Executive morning briefing — compact strip + scrollable side drawer on canvas. */
export default function BiMorningBriefing({
  config,
  boardId = 'default',
  onAskInChat,
  compact = false,
  defaultOpen,
  light = false,
}: Props) {
  const enabled = isRunnerConfigured(config);
  const locale = getLocale();
  const [open, setOpen] = useState(() => {
    if (defaultOpen != null) return defaultOpen;
    return typeof window !== 'undefined' ? window.matchMedia('(min-width: 640px)').matches : false;
  });
  const [briefingReady, setBriefingReady] = useState(!light);

  useEffect(() => {
    if (!light || open) {
      setBriefingReady(true);
      return;
    }
    const timer = window.setTimeout(() => setBriefingReady(true), 2500);
    return () => window.clearTimeout(timer);
  }, [light, open]);

  useEffect(() => {
    if (!open || !compact) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, compact]);

  const biStatus = useQuery({
    queryKey: ['bi-status'],
    queryFn: () => api.bi.status(config),
    enabled: enabled && !light,
    staleTime: 120_000,
  });

  const analytics = useQuery({
    queryKey: ['bi-analytics-status'],
    queryFn: () => api.bi.analytics.status(config),
    enabled: enabled && !light,
    staleTime: 90_000,
  });

  const briefing = useQuery({
    queryKey: ['bi-briefing', boardId, locale],
    queryFn: () => api.bi.briefing(config, boardId, locale),
    enabled: enabled && Boolean(boardId) && (open || briefingReady),
    staleTime: 90_000,
    retry: false,
  });

  const attention = (briefing.data?.attention ?? []) as AttentionItem[];
  const insights = briefing.data?.insights ?? [];
  const deltaSummary = briefing.data?.delta_summary;
  const pulse = briefing.data?.data_pulse;
  const dbOk = Boolean(pulse?.db_ready ?? biStatus.data?.connection?.ok ?? (light && !briefing.isFetched));
  const reportsOk = Boolean(analytics.data?.health?.ok ?? analytics.data?.enabled ?? light);
  const tableCount = pulse?.table_count ?? biStatus.data?.table_count ?? 0;
  const sourceLabel = pulse?.source_label;

  const headline = useMemo(() => {
    if (attention[0]) {
      const top = attention[0];
      if (top.kind === 'alert') return t('bi.wow.briefingExecAlertHeadline', { title: itemTitle(top) });
      if (top.kind === 'anomaly' || top.kind === 'kpi') {
        return t('bi.wow.briefingExecMoverHeadline', {
          title: itemTitle(top),
          change: itemBody(top) || '',
        });
      }
      if (top.kind === 'insight') return itemTitle(top);
      if (top.kind === 'schema') return itemTitle(top);
    }
    if (insights[0]?.title) return insights[0].title;
    if (dbOk && (deltaSummary?.up || deltaSummary?.down)) {
      return t('bi.wow.briefingExecPulseHeadline', {
        up: String(deltaSummary?.up ?? 0),
        down: String(deltaSummary?.down ?? 0),
      });
    }
    if (dbOk) return t('bi.wow.briefingExecReady');
    return t('bi.wow.briefingExecNeedData');
  }, [attention, insights, dbOk, deltaSummary]);

  const subline = useMemo(() => {
    if (insights[0]?.body && attention[0]?.kind !== 'insight') return insights[0].body;
    if (attention[0]) {
      const body = itemBody(attention[0]);
      if (body) return body;
    }
    if (dbOk && sourceLabel) {
      return t('bi.wow.briefingPulseSubline', {
        source: sourceLabel,
        count: String(tableCount || 0),
      });
    }
    return '';
  }, [insights, attention, dbOk, sourceLabel, tableCount]);

  const runAsk = (prompt?: string) => {
    if (prompt && onAskInChat) onAskInChat(prompt);
    if (compact) setOpen(false);
  };

  if (!enabled) return null;

  const cardsProps = {
    attention,
    insights,
    dbOk,
    reportsOk,
    tableCount,
    onAskInChat,
    runAsk,
  };

  // Compact closed: thin bar only — never steal canvas height from the dashboard.
  if (compact && !open) {
    return (
      <button
        type="button"
        className="bi-morning-pulse bi-morning-pulse--rail flex w-full items-center gap-2 px-3 py-2 text-left text-white"
        onClick={() => setOpen(true)}
        aria-expanded={false}
      >
        <div className="bi-morning-pulse-glow" aria-hidden />
        <Sparkles className="relative z-[1] h-3.5 w-3.5 shrink-0 text-teal-100" aria-hidden />
        <span className="relative z-[1] min-w-0 flex-1 truncate text-xs font-semibold tracking-wide">
          {t('bi.wow.briefingPulseEyebrow')}
          {headline ? <span className="ml-2 font-normal text-white/80">{headline}</span> : null}
        </span>
        <span className="relative z-[1] shrink-0 text-[11px] font-medium text-teal-100/90">
          {t('bi.wow.briefingExpand')}
        </span>
        <ChevronDown className="relative z-[1] h-4 w-4 shrink-0 text-teal-100/90" aria-hidden />
      </button>
    );
  }

  return (
    <>
      <section
        className={clsx(
          'bi-morning-pulse shrink-0 text-white',
          compact ? 'bi-morning-pulse--compact' : 'bi-morning-pulse--full',
        )}
      >
        <div className="bi-morning-pulse-glow" aria-hidden />
        <div className="bi-morning-pulse-inner">
          <div className="flex flex-wrap items-center gap-3 sm:gap-4">
            <div className="bi-morning-pulse-orb" aria-hidden>
              <span className="bi-morning-pulse-orb-ring" />
              <Sparkles className="relative z-[1] h-4 w-4 text-white sm:h-5 sm:w-5" />
            </div>

            <div className="min-w-0 flex-1">
              <p className="bi-morning-pulse-eyebrow">
                {t('bi.wow.briefingPulseEyebrow')}
                {sourceLabel ? (
                  <span className="bi-morning-pulse-chip">
                    {sourceLabel}
                    {tableCount > 0 ? ` · ${t('bi.wow.briefingTables', { count: String(tableCount) })}` : ''}
                  </span>
                ) : null}
              </p>
              <h2 className={clsx('bi-morning-pulse-title', compact && 'bi-morning-pulse-title--compact')}>
                {headline}
              </h2>
              {subline ? (
                <p className={clsx('bi-morning-pulse-sub', compact && 'line-clamp-1 sm:line-clamp-2')}>
                  {subline}
                </p>
              ) : null}
            </div>

            <div className="flex w-full shrink-0 flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
              {deltaSummary && (deltaSummary.up || deltaSummary.down) ? (
                <div className="bi-morning-pulse-deltas hidden sm:flex">
                  <span className="bi-morning-pulse-delta bi-morning-pulse-delta--up">
                    <ArrowUpRight className="h-3.5 w-3.5" />
                    {deltaSummary.up ?? 0}
                  </span>
                  <span className="bi-morning-pulse-delta bi-morning-pulse-delta--down">
                    <ArrowDownRight className="h-3.5 w-3.5" />
                    {deltaSummary.down ?? 0}
                  </span>
                </div>
              ) : null}
              {onAskInChat ? (
                <button
                  type="button"
                  className="bi-morning-pulse-cta"
                  onClick={() =>
                    runAsk(
                      attention[0]?.ask_prompt || insights[0]?.title || t('bi.wow.demoAskTrend'),
                    )
                  }
                >
                  <MessageSquare className="h-3.5 w-3.5" />
                  <span className="hidden min-[380px]:inline">{t('bi.wow.briefingAskCta')}</span>
                </button>
              ) : null}
              <button
                type="button"
                className="bi-morning-pulse-toggle"
                onClick={() => setOpen((v) => !v)}
                aria-expanded={open}
              >
                {open ? t('bi.wow.briefingCollapse') : t('bi.wow.briefingExpand')}
              </button>
            </div>
          </div>

          {open && !compact ? (
            <div className="mt-3 max-h-[min(50vh,28rem)] overflow-y-auto overscroll-contain [-webkit-overflow-scrolling:touch]">
              <AttentionCards {...cardsProps} />
            </div>
          ) : null}
        </div>
      </section>

      {open && compact ? (
        <>
          <button
            type="button"
            className="fixed inset-0 z-[55] bg-slate-900/40 backdrop-blur-[2px] sm:bg-slate-900/25"
            aria-label={t('bi.wow.briefingCollapse')}
            onClick={() => setOpen(false)}
          />
          <aside
            className={clsx(
              'bi-morning-pulse-drawer fixed z-[56] flex flex-col overflow-hidden text-white shadow-2xl',
              'inset-x-0 bottom-0 max-h-[min(85dvh,36rem)] rounded-t-2xl',
              'sm:inset-y-3 sm:bottom-auto sm:left-3 sm:right-auto sm:max-h-none sm:w-[min(22rem,calc(100vw-1.5rem))] sm:rounded-2xl',
            )}
            style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
            role="dialog"
            aria-modal
            aria-label={t('bi.wow.briefingPulseEyebrow')}
          >
            <div className="mx-auto mt-2 h-1 w-10 shrink-0 rounded-full bg-white/25 sm:hidden" aria-hidden />
            <div className="flex shrink-0 items-center gap-2 border-b border-white/10 px-3 py-2.5">
              <Sparkles className="h-4 w-4 shrink-0 text-teal-200" />
              <p className="min-w-0 flex-1 truncate text-sm font-semibold">{t('bi.wow.briefingPulseEyebrow')}</p>
              <button
                type="button"
                className="min-h-10 min-w-10 rounded-lg p-1.5 text-sky-100/90 transition hover:bg-white/10"
                onClick={() => setOpen(false)}
                aria-label={t('bi.wow.briefingCollapse')}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3 [-webkit-overflow-scrolling:touch]">
              {sourceLabel ? (
                <p className="mb-3 text-[11px] text-teal-100/80">
                  {sourceLabel}
                  {tableCount > 0 ? ` · ${t('bi.wow.briefingTables', { count: String(tableCount) })}` : ''}
                </p>
              ) : null}
              <p className="mb-3 text-sm font-medium leading-snug text-white">{headline}</p>
              <AttentionCards {...cardsProps} />
            </div>
          </aside>
        </>
      ) : null}
    </>
  );
}
