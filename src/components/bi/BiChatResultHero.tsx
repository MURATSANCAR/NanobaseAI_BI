import { useState } from 'react';
import clsx from 'clsx';
import { ChevronDown, ChevronUp, Sparkles } from 'lucide-react';
import DynamicResultTable from '@/components/DynamicResultTable';
import { formatPbiNumber } from '@/components/bi/biVisualTheme';
import type { BiChatResponse } from '@/api/types';
import { t } from '@/i18n';
import { biFieldLabel } from '@/utils/biFieldLabel';
import {
  normalizeResultColumns,
  sanitizeChatDisplayValue,
  sanitizeChatRows,
} from '@/utils/biChatSanitize';

function humanCol(name: string): string {
  const cleaned = String(name || '')
    .replace(/_count$/i, '')
    .replace(/_total$/i, '')
    .replace(/_/g, ' ')
    .trim();
  return biFieldLabel(cleaned || String(name || ''));
}

function extractCells(meta: BiChatResponse): {
  cols: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
} | null {
  const qr = meta.query_result;
  if (!qr) return null;
  const normalized = normalizeResultColumns(qr.columns);
  const cols = normalized.length
    ? normalized
    : Object.keys((qr.rows?.[0] as Record<string, unknown>) ?? {});
  const rows = sanitizeChatRows((qr.rows ?? []) as Record<string, unknown>[]);
  return { cols, rows, rowCount: qr.row_count ?? rows.length };
}

const HERO_PALETTES = [
  {
    shell: 'from-sky-500/15 via-white to-cyan-400/20',
    orb: 'from-sky-400 to-cyan-500',
    label: 'text-sky-800/80',
    value: 'text-slate-900',
    chip: 'bg-sky-100 text-sky-800 ring-sky-200',
  },
  {
    shell: 'from-violet-500/15 via-white to-fuchsia-400/20',
    orb: 'from-violet-500 to-fuchsia-500',
    label: 'text-violet-800/80',
    value: 'text-slate-900',
    chip: 'bg-violet-100 text-violet-800 ring-violet-200',
  },
  {
    shell: 'from-emerald-500/15 via-white to-teal-400/20',
    orb: 'from-emerald-500 to-teal-500',
    label: 'text-emerald-800/80',
    value: 'text-slate-900',
    chip: 'bg-emerald-100 text-emerald-800 ring-emerald-200',
  },
  {
    shell: 'from-amber-500/15 via-white to-orange-400/20',
    orb: 'from-amber-500 to-orange-500',
    label: 'text-amber-900/80',
    value: 'text-slate-900',
    chip: 'bg-amber-100 text-amber-900 ring-amber-200',
  },
] as const;

/** Single scalar → hero KPI; few columns on one row → mini KPI strip; else compact table. */
export default function BiChatResultHero({
  meta,
  title,
}: {
  meta: BiChatResponse;
  /** User question or friendly title shown above the value. */
  title?: string;
}) {
  const [detailsOpen, setDetailsOpen] = useState(false);

  if (meta.sql_error) {
    return (
      <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-sm text-rose-800">
        {meta.sql_error}
      </div>
    );
  }

  const data = extractCells(meta);
  if (!data || (!data.rows.length && !data.rowCount)) {
    return (
      <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
        {t('bi.queryRunEmpty')}
      </div>
    );
  }

  const { cols, rows, rowCount } = data;
  const singleScalar = rows.length === 1 && cols.length === 1;
  const singleRowKpis = rows.length === 1 && cols.length >= 2 && cols.length <= 4;
  const palette = HERO_PALETTES[(cols[0]?.length || 0) % HERO_PALETTES.length]!;
  const headline =
    (title || '').replace(/\s+/g, ' ').trim() ||
    (meta.widgets?.[0]?.title || '').replace(/\s+/g, ' ').trim() ||
    humanCol(cols[0] || 'Sonuç');
  const rawValue = singleScalar ? rows[0]![cols[0]!] : null;
  const displayValue = singleScalar
    ? formatPbiNumber(sanitizeChatDisplayValue(rawValue))
    : null;

  return (
    <div className="mt-3 space-y-2">
      {singleScalar ? (
        <div
          className={clsx(
            'bi-chat-result-hero relative overflow-hidden rounded-3xl border border-white/80 bg-gradient-to-br px-5 py-6 shadow-sm sm:px-7 sm:py-8',
            palette.shell,
          )}
        >
          <div
            className={clsx(
              'pointer-events-none absolute -right-8 -top-10 h-36 w-36 rounded-full bg-gradient-to-br opacity-40 blur-2xl',
              palette.orb,
            )}
            aria-hidden
          />
          <div
            className={clsx(
              'pointer-events-none absolute -bottom-12 -left-10 h-40 w-40 rounded-full bg-gradient-to-tr opacity-30 blur-2xl',
              palette.orb,
            )}
            aria-hidden
          />

          <div className="relative z-[1] flex flex-col items-center text-center">
            <span
              className={clsx(
                'mb-3 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ring-1',
                palette.chip,
              )}
            >
              <Sparkles className="h-3 w-3" aria-hidden />
              {t('bi.result.answerBadge')}
            </span>
            <p className={clsx('max-w-full text-sm font-semibold leading-snug sm:text-base', palette.label)}>
              {headline}
            </p>
            <p
              className={clsx(
                'bi-chat-result-hero-value mt-3 font-semibold tabular-nums tracking-tight sm:mt-4',
                palette.value,
              )}
              style={{ fontSize: 'clamp(2.4rem, 7vw, 3.75rem)', lineHeight: 1.05 }}
            >
              {displayValue}
            </p>
            <p className="mt-3 text-[11px] font-medium text-slate-500">{t('bi.result.heroReady')}</p>
          </div>
        </div>
      ) : null}

      {singleRowKpis ? (
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          {cols.map((c, i) => {
            const tone = HERO_PALETTES[i % HERO_PALETTES.length]!;
            return (
              <div
                key={c}
                className={clsx(
                  'relative overflow-hidden rounded-2xl border border-white/80 bg-gradient-to-br px-3 py-3 shadow-sm',
                  tone.shell,
                )}
              >
                <div className={clsx('text-[10px] font-bold uppercase tracking-wide', tone.label)}>
                  {humanCol(c)}
                </div>
                <div className="mt-1 text-xl font-semibold tabular-nums text-slate-900 sm:text-2xl">
                  {formatPbiNumber(sanitizeChatDisplayValue(rows[0]![c]))}
                </div>
              </div>
            );
          })}
        </div>
      ) : null}

      {!singleScalar && !singleRowKpis ? (
        <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-sm">
          <div className="flex items-center justify-between gap-2 border-b border-slate-100 bg-gradient-to-r from-sky-50 to-violet-50 px-3 py-2">
            <span className="text-xs font-bold text-slate-700">{t('bi.result.answerBadge')}</span>
            <span className="text-[10px] font-medium text-slate-500">
              {t('bi.queryPreview', { count: String(rowCount) })}
            </span>
          </div>
          <DynamicResultTable columns={cols} rows={rows} maxCols={6} maxRows={8} compact />
        </div>
      ) : null}

      {meta.provenance ? (
        <div className="rounded-xl border border-slate-200/70 bg-slate-50/80">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-xs font-medium text-slate-600 hover:text-slate-900"
            onClick={() => setDetailsOpen((v) => !v)}
            aria-expanded={detailsOpen}
          >
            <span>{t('bi.result.detailsToggle')}</span>
            {detailsOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>
          {detailsOpen ? (
            <dl className="grid gap-1.5 border-t border-slate-200/80 px-3 py-2.5 text-xs text-slate-700 sm:grid-cols-2">
              {meta.provenance.confidence != null ? (
                <div>
                  <dt className="text-[10px] uppercase tracking-wide text-slate-500">{t('bi.provenance.confidence')}</dt>
                  <dd>{Math.round(Number(meta.provenance.confidence) * 100)}%</dd>
                </div>
              ) : null}
              {meta.provenance.selected_tables?.length ? (
                <div className="sm:col-span-2">
                  <dt className="text-[10px] uppercase tracking-wide text-slate-500">{t('bi.provenance.tables')}</dt>
                  <dd className="font-mono text-[11px]">{meta.provenance.selected_tables.join(', ')}</dd>
                </div>
              ) : null}
              {meta.provenance.sql_fingerprint ? (
                <div className="sm:col-span-2">
                  <dt className="text-[10px] uppercase tracking-wide text-slate-500">{t('bi.provenance.fingerprint')}</dt>
                  <dd className="break-all font-mono text-[11px]">{meta.provenance.sql_fingerprint}</dd>
                </div>
              ) : null}
            </dl>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function isHeroScalarResult(meta?: BiChatResponse | null): boolean {
  if (!meta?.query_result) return false;
  const cols = normalizeResultColumns(meta.query_result.columns);
  const resolved = cols.length
    ? cols
    : Object.keys((meta.query_result.rows?.[0] as Record<string, unknown>) ?? {});
  const rows = meta.query_result.rows ?? [];
  return rows.length === 1 && resolved.length === 1;
}

/** True when chat synthesized only KPI-style widgets (show answer hero, not tile preview). */
export function isChatKpiAnswer(meta?: BiChatResponse | null): boolean {
  if (!meta) return false;
  if (isHeroScalarResult(meta)) return true;
  const widgets = meta.widgets ?? [];
  if (!widgets.length) return false;
  return widgets.every((w) => {
    const type = String(w.type || '').toLowerCase();
    return type === 'kpi' || type === 'metric' || type === 'card' || type === 'gauge';
  });
}
