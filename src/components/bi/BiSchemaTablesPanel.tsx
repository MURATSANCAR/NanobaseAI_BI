import { useState } from 'react';
import clsx from 'clsx';
import { ChevronDown, ChevronUp, KeyRound, Link2, MessageSquare, Table2 } from 'lucide-react';
import type { BiSchemaTable } from '@/api/types';
import { useBiChatDockOptional } from '@/context/BiChatDockContext';
import { t } from '@/i18n';
import { formatSchemaColumnType, schemaColumnSizeHint } from '@/utils/biSchemaColumnType';

type Props = {
  tables: BiSchemaTable[];
};

function accentIndex(name: string) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h + name.charCodeAt(i) * (i + 1)) % 6;
  return h;
}

function ColumnBadges({ table, columnName }: { table: BiSchemaTable; columnName: string }) {
  const isPk = (table.primary_key ?? []).includes(columnName);
  const isFk = (table.foreign_keys ?? []).some((fk) => {
    const cols = fk.columns ?? fk.constrained_columns;
    return Array.isArray(cols) && cols.includes(columnName);
  });
  if (!isPk && !isFk) return null;
  return (
    <span className="inline-flex items-center gap-0.5">
      {isPk ? <KeyRound className="h-3 w-3 text-amber-600" aria-label={t('bi.schemaPk')} /> : null}
      {isFk ? <Link2 className="h-3 w-3 text-violet-600" aria-label={t('bi.schemaFk')} /> : null}
    </span>
  );
}

export default function BiSchemaTablesPanel({ tables }: Props) {
  const dock = useBiChatDockOptional();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const toggle = (fullName: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(fullName)) next.delete(fullName);
      else next.add(fullName);
      return next;
    });
  };

  return (
    <section className="bi-schema-panel">
      <div className="bi-schema-panel-header">
        <h2 className="text-sm font-semibold text-slate-800">{t('bi.schemaTablesTitle')}</h2>
        <p className="mt-0.5 text-xs text-slate-500">{t('bi.schemaTablesSubtitleSized')}</p>
      </div>

      <div className="bi-schema-table-grid">
        {tables.map((table) => {
          const columns = table.columns ?? [];
          const open = expanded.has(table.full_name);
          const shortName = table.full_name.split('.').pop() || table.full_name;
          const accent = accentIndex(table.full_name);

          return (
            <article
              key={table.full_name}
              data-accent={accent}
              className={clsx('bi-schema-table-card', open && 'is-open')}
            >
              <span className="bi-pbi-tile-glow" aria-hidden />
              <span className="bi-pbi-tile-accent" data-accent={accent} aria-hidden />

              <button
                type="button"
                className="bi-schema-table-card-header w-full text-left"
                onClick={() => toggle(table.full_name)}
                aria-expanded={open}
              >
                <div className="bi-schema-table-icon">
                  <Table2 className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-sm font-semibold text-slate-800">{shortName}</div>
                  <div className="truncate text-[11px] text-slate-500">{table.schema || table.full_name}</div>
                </div>
                <span className="bi-schema-col-badge">{columns.length}</span>
                {open ? (
                  <ChevronUp className="h-4 w-4 shrink-0 text-slate-400" />
                ) : (
                  <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" />
                )}
              </button>

              {open ? (
                <div className="bi-schema-columns max-h-64 overflow-y-auto">
                  {columns.map((col, idx) => {
                    const isPk = (table.primary_key ?? []).includes(col.name);
                    const isFk = (table.foreign_keys ?? []).some((fk) => {
                      const cols = fk.columns ?? fk.constrained_columns;
                      return Array.isArray(cols) && cols.includes(col.name);
                    });
                    const typeLabel = formatSchemaColumnType(col);
                    const sizeHint = schemaColumnSizeHint(col);
                    return (
                      <div
                        key={`${table.full_name}-${col.name}`}
                        className={clsx('bi-schema-col-row', isPk && 'is-pk', isFk && !isPk && 'is-fk')}
                        title={`${col.name}: ${typeLabel}`}
                      >
                        <span className="bi-schema-col-order">{idx + 1}</span>
                        <span className="min-w-0 flex-1 truncate font-mono text-xs text-slate-800">{col.name}</span>
                        <span className="bi-schema-type-pill" title={typeLabel}>
                          {typeLabel}
                        </span>
                        {sizeHint ? (
                          <span className="bi-schema-size-chip" title={typeLabel}>
                            {sizeHint}
                          </span>
                        ) : null}
                        <span className="hidden text-[10px] text-slate-400 sm:inline">
                          {col.nullable == null ? '' : col.nullable ? t('bi.nullableYes') : t('bi.nullableNo')}
                        </span>
                        <ColumnBadges table={table} columnName={col.name} />
                      </div>
                    );
                  })}
                </div>
              ) : null}

              <div className="border-t border-slate-100/80 p-3">
                <button
                  type="button"
                  className="bi-schema-ask-btn"
                  onClick={() =>
                    dock?.openChat({
                      prompt: t('bi.askAboutTable', { table: table.full_name }),
                    })
                  }
                >
                  <MessageSquare className="h-4 w-4" />
                  {t('bi.askAboutTable', { table: shortName })}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
