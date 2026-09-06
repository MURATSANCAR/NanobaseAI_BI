import clsx from 'clsx';
import DynamicResultTable from '@/components/DynamicResultTable';
import type { BiAnswerBlock } from '@/api/types';
import { t } from '@/i18n';
import { sanitizeChatDisplayValue, stripSqlFromChatText } from '@/utils/biChatSanitize';

export function BiAnswerBlocks({ blocks }: { blocks: BiAnswerBlock[] }) {
  if (!blocks.length) return null;
  const hide = '—';

  return (
    <div className="space-y-3">
      {blocks.map((block, i) => (
        <div key={i} className="rounded-xl border border-surface-border bg-surface-overlay/30 p-4">
          {block.title && <h4 className="mb-2 font-medium text-slate-900">{stripSqlFromChatText(block.title)}</h4>}
          {block.type === 'text' && block.content && (
            <p className="whitespace-pre-wrap text-sm text-slate-700">{stripSqlFromChatText(block.content)}</p>
          )}
          {block.type === 'highlight' && block.content && (
            <p className="rounded-md bg-accent/10 px-3 py-2 text-sm text-accent">{stripSqlFromChatText(block.content)}</p>
          )}
          {block.type === 'decision' && (
            <div className="space-y-3 text-sm text-slate-700">
              {block.content && (
                <div>
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t('bi.decisionWhat')}</p>
                  <p className="whitespace-pre-wrap">{stripSqlFromChatText(block.content)}</p>
                </div>
              )}
              {block.items && block.items.length > 0 && (
                <div>
                  <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">{t('bi.decisionWhyDo')}</p>
                  <ol className="list-inside list-decimal space-y-1">
                    {block.items.map((item, j) => (
                      <li key={j}>{stripSqlFromChatText(item)}</li>
                    ))}
                  </ol>
                </div>
              )}
              {block.metrics && (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {block.metrics.map((m, j) => (
                    <div key={j} className="bi-pbi-mini-kpi" data-accent={j % 6}>
                      <div className="bi-pbi-mini-kpi-label">{stripSqlFromChatText(m.label)}</div>
                      <div className="font-semibold text-slate-900">
                        {String(sanitizeChatDisplayValue(m.value, hide))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {block.type === 'list' && block.items && (
            <ul className="list-inside list-disc space-y-1 text-sm text-slate-700">
              {block.items.map((item, j) => (
                <li key={j}>{stripSqlFromChatText(item)}</li>
              ))}
            </ul>
          )}
          {block.type === 'metric' && block.metrics && (
            <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-3">
              {block.metrics.map((m, j) => (
                <div key={j} className="bi-pbi-mini-kpi" data-accent={j % 6}>
                  <div className="bi-pbi-mini-kpi-label">{stripSqlFromChatText(m.label)}</div>
                  <div
                    className={clsx(
                      'bi-pbi-mini-kpi-value',
                      m.tone === 'positive' && '!text-[#107C10]',
                      m.tone === 'negative' && '!text-[#D13438]',
                    )}
                  >
                    {String(sanitizeChatDisplayValue(m.value, hide))}
                  </div>
                </div>
              ))}
            </div>
          )}
          {block.type === 'table' && block.columns && block.rows && (
            <div className="bi-pbi-matrix overflow-auto rounded-lg border border-[#E1DFDD]">
            <DynamicResultTable
              columns={block.columns}
              rows={block.rows.map((row) =>
                Object.fromEntries(
                  block.columns!.map((c, idx) => [c, sanitizeChatDisplayValue(row[idx], hide)]),
                ),
              )}
              maxRows={30}
            />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
