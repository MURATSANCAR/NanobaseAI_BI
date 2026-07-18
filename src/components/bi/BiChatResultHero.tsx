import { useState } from 'react';
import clsx from 'clsx';
import { ChevronDown, ChevronUp } from 'lucide-react';
import DynamicResultTable from '@/components/DynamicResultTable';
import { formatPbiNumber } from '@/components/bi/biVisualTheme';
import type { BiChatResponse } from '@/api/types';
import { t } from '@/i18n';
import { biFieldLabel } from '@/utils/biFieldLabel';
import { sanitizeChatDisplayValue, sanitizeChatRows } from '@/utils/biChatSanitize';

function humanCol(name: string): string {
  const cleaned = name.replace(/_count$/i, '').replace(/_total$/i, '').replace(/_/g, ' ').trim();
  return biFieldLabel(cleaned || name);
}

function extractCells(meta: BiChatResponse): {
  cols: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
} | null {
  const qr = meta.query_result;
  if (!qr) return null;
  const cols = qr.columns ?? Object.keys((qr.rows?.[0] as Record<string, unknown>) ?? {});
  const rows = sanitizeChatRows((qr.rows ?? []) as Record<string, unknown>[]);
  return { cols, rows, rowCount: qr.row_count ?? rows.length };
}

/** Single scalar → hero KPI; few columns on one row → mini KPI strip; else compact table. */
export default function BiChatResultHero({ meta }: { meta: BiChatResponse }) {
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

  return (
    <div className="mt-3 space-y-2">
      {singleScalar ? (
        <div className="bi-chat-result-hero relative overflow-hidden rounded-2xl border border-sky-200/70 bg-gradient-to-br from-sky-50 via-white to-violet-50 px-5 py-6 text-center shadow-sm">
          <p className="bi-pbi-kpi-label text-sky-800/80">{humanCol(cols[0]!)}</p>
          <p className="bi-chat-result-hero-value mt-2 font-light tabular-nums tracking-tight text-slate-900">
            {formatPbiNumber(sanitizeChatDisplayValue(rows[0]![cols[0]!]))}
          </p>
          <p className="mt-2 text-[11px] font-medium text-slate-500">{t('bi.result.heroReady')}</p>
        </div>
      ) : null}

      {singleRowKpis ? (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {cols.map((c, i) => (
            <div key={c} className="bi-pbi-mini-kpi" data-accent={i % 6}>
              <div className="bi-pbi-mini-kpi-label">{humanCol(c)}</div>
              <div className="bi-pbi-mini-kpi-value text-lg font-semibold tabular-nums text-slate-900">
                {formatPbiNumber(sanitizeChatDisplayValue(rows[0]![c]))}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {!singleScalar && !singleRowKpis ? (
        <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white">
          <div className="border-b border-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600">
            {t('bi.queryPreview', { count: String(rowCount) })}
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

      {singleScalar || singleRowKpis ? (
        <p className={clsx('text-[10px] text-slate-400', !detailsOpen && 'sr-only')}>
          {t('bi.queryPreview', { count: String(rowCount) })}
        </p>
      ) : null}
    </div>
  );
}

export function isHeroScalarResult(meta?: BiChatResponse | null): boolean {
  if (!meta?.query_result) return false;
  const cols = meta.query_result.columns ?? Object.keys((meta.query_result.rows?.[0] as Record<string, unknown>) ?? {});
  const rows = meta.query_result.rows ?? [];
  return rows.length === 1 && cols.length === 1;
}
