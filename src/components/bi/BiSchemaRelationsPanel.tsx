import { useMemo, useState } from 'react';
import clsx from 'clsx';
import { ArrowRight, GitBranch, MessageSquare, Table2, Unlink } from 'lucide-react';
import type { BiSchemaGraphEdge, BiSchemaGraphNode } from '@/api/types';
import {
  buildBiSchemaRelations,
  filterBiSchemaRelations,
  isolatedSchemaTables,
  shortSchemaTableName,
  type BiRelationRow,
} from '@/utils/biSchemaRelations';
import { useBiChatDockOptional } from '@/context/BiChatDockContext';
import { t } from '@/i18n';

type Props = {
  nodes: BiSchemaGraphNode[];
  edges: BiSchemaGraphEdge[];
  highlight?: string;
  onTableClick?: (table: string) => void;
};

function TablePill({
  name,
  label,
  onClick,
  tone = 'from',
}: {
  name: string;
  label: string;
  onClick?: (name: string) => void;
  tone?: 'from' | 'to' | 'neutral';
}) {
  const body = (
    <>
      <Table2 className="h-3.5 w-3.5 shrink-0 opacity-80" />
      <span className="truncate font-semibold">{label}</span>
      {name !== label ? <span className="truncate text-[10px] opacity-70">{name}</span> : null}
    </>
  );

  const className = clsx(
    'bi-schema-relation-table flex min-w-0 flex-col items-start gap-0.5 rounded-xl px-3 py-2 text-left text-sm text-white shadow-md',
    tone === 'from' && 'bi-schema-relation-table--from',
    tone === 'to' && 'bi-schema-relation-table--to',
    tone === 'neutral' && 'bi-schema-relation-table--neutral',
  );

  if (onClick) {
    return (
      <button type="button" className={className} onClick={() => onClick(name)} title={name}>
        {body}
      </button>
    );
  }
  return <div className={className}>{body}</div>;
}

function RelationCard({ row, onTableClick }: { row: BiRelationRow; onTableClick?: (table: string) => void }) {
  const via =
    row.sourceColumns.length && row.targetColumns.length
      ? row.sourceColumns.map((s, i) => `${s} → ${row.targetColumns[i] ?? '?'}`).join(', ')
      : row.sourceColumns.join(', ') || '—';

  return (
    <article className="bi-schema-relation-card">
      <div className="bi-schema-relation-flow">
        <TablePill name={row.fromId} label={row.fromLabel} tone="from" onClick={onTableClick} />
        <div className="bi-schema-relation-arrow" aria-hidden>
          <span className="bi-schema-relation-arrow-line" />
          <ArrowRight className="bi-schema-relation-arrow-icon h-5 w-5 shrink-0" />
          <code className="bi-schema-relation-via">{via}</code>
        </div>
        <TablePill name={row.toId} label={row.toLabel} tone="to" onClick={onTableClick} />
      </div>
      <p className="bi-schema-relation-summary">
        {t('bi.relationSummary', { from: row.fromLabel, to: row.toLabel })}
        <span className="text-slate-400"> · </span>
        {t('bi.relationVia', { columns: via })}
      </p>
      {onTableClick ? (
        <button type="button" className="bi-schema-relation-ask mt-2" onClick={() => onTableClick(row.fromId)}>
          <MessageSquare className="h-3.5 w-3.5" />
          {t('bi.relationAsk', { from: row.fromLabel, to: row.toLabel })}
        </button>
      ) : null}
    </article>
  );
}

export default function BiSchemaRelationsPanel({ nodes, edges, highlight = '', onTableClick }: Props) {
  const dock = useBiChatDockOptional();
  const [view, setView] = useState<'list' | 'byTable'>('list');
  const [selectedTable, setSelectedTable] = useState('');

  const allRelations = useMemo(() => buildBiSchemaRelations(nodes, edges), [nodes, edges]);
  const filteredRelations = useMemo(() => filterBiSchemaRelations(allRelations, highlight), [allRelations, highlight]);

  const tablesWithRelations = useMemo(() => {
    const ids = new Set<string>();
    for (const r of allRelations) {
      ids.add(r.fromId);
      ids.add(r.toId);
    }
    return nodes
      .filter((n) => ids.has(n.full_name))
      .map((n) => ({ id: n.full_name, label: n.label || shortSchemaTableName(n.full_name) }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [allRelations, nodes]);

  const activeTable = selectedTable || tablesWithRelations[0]?.id || '';

  const outgoing = useMemo(
    () => filteredRelations.filter((r) => r.fromId === activeTable),
    [filteredRelations, activeTable],
  );
  const incoming = useMemo(
    () => filteredRelations.filter((r) => r.toId === activeTable),
    [filteredRelations, activeTable],
  );

  const isolatedTables = useMemo(() => {
    const q = highlight.trim().toLowerCase();
    return isolatedSchemaTables(nodes, allRelations)
      .filter((n) => !q || n.label.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [allRelations, nodes, highlight]);

  if (!nodes.length) {
    return (
      <section className="bi-schema-panel p-8 text-center">
        <Unlink className="mx-auto mb-2 h-8 w-8 text-slate-300" />
        <p className="text-sm text-slate-600">{t('bi.noSchema')}</p>
      </section>
    );
  }

  return (
    <section className="bi-schema-panel">
      <div className="bi-schema-panel-header">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="bi-schema-table-icon !h-9 !w-9">
              <GitBranch className="h-4 w-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-800">{t('bi.relationsTitle')}</h2>
              <p className="text-xs text-slate-500">{t('bi.relationsSubtitle')}</p>
            </div>
          </div>
          <div className="flex rounded-xl border border-slate-200/80 bg-white/80 p-1 shadow-sm">
            <button
              type="button"
              className={clsx('rounded-lg px-3 py-1.5 text-xs font-medium transition-colors', view === 'list' && 'bg-violet-100 text-violet-800')}
              onClick={() => setView('list')}
            >
              {t('bi.relationsViewList')}
            </button>
            <button
              type="button"
              className={clsx('rounded-lg px-3 py-1.5 text-xs font-medium transition-colors', view === 'byTable' && 'bg-violet-100 text-violet-800')}
              onClick={() => setView('byTable')}
            >
              {t('bi.relationsViewByTable')}
            </button>
          </div>
        </div>
      </div>

      {!allRelations.length ? (
        <div className="flex flex-col items-center gap-2 p-8 text-center">
          <Unlink className="h-8 w-8 text-slate-300" />
          <p className="text-sm text-slate-600">{t('bi.relationsNone')}</p>
        </div>
      ) : view === 'list' ? (
        <div className="bi-schema-relations-grid p-4 sm:p-5">
          {filteredRelations.length ? (
            filteredRelations.map((row) => <RelationCard key={row.id} row={row} onTableClick={onTableClick} />)
          ) : (
            <p className="col-span-full text-center text-sm text-slate-500">{t('bi.relationsSearchEmpty')}</p>
          )}
        </div>
      ) : (
        <div className="space-y-4 p-4 sm:p-5">
          <label className="block text-xs font-medium text-slate-600">
            {t('bi.relationsPickTable')}
            <select
              className="input-field mt-1 w-full max-w-md text-sm"
              value={activeTable}
              onChange={(e) => setSelectedTable(e.target.value)}
            >
              {tablesWithRelations.map((tbl) => (
                <option key={tbl.id} value={tbl.id}>
                  {tbl.label}
                </option>
              ))}
            </select>
          </label>

          {activeTable ? (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="bi-schema-relation-group">
                <h3 className="bi-schema-relation-group-title">{t('bi.relationsOutgoing')}</h3>
                {outgoing.length ? (
                  <div className="space-y-3">
                    {outgoing.map((row) => (
                      <RelationCard key={row.id} row={row} onTableClick={onTableClick} />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">{t('bi.relationsOutgoingEmpty')}</p>
                )}
              </div>
              <div className="bi-schema-relation-group">
                <h3 className="bi-schema-relation-group-title">{t('bi.relationsIncoming')}</h3>
                {incoming.length ? (
                  <div className="space-y-3">
                    {incoming.map((row) => (
                      <RelationCard key={row.id} row={row} onTableClick={onTableClick} />
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">{t('bi.relationsIncomingEmpty')}</p>
                )}
              </div>
            </div>
          ) : null}
        </div>
      )}

      {isolatedTables.length ? (
        <div className="border-t border-slate-100/80 px-4 py-3 sm:px-5">
          <p className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">{t('bi.relationsIsolated')}</p>
          <div className="flex flex-wrap gap-2">
            {isolatedTables.map((tbl) => (
              <button
                key={tbl.id}
                type="button"
                className="bi-schema-relation-isolated"
                onClick={() => onTableClick?.(tbl.id)}
              >
                {tbl.label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {onTableClick ? (
        <div className="border-t border-slate-100/80 px-4 py-3 text-center sm:px-5">
          <button
            type="button"
            className="text-xs font-medium text-violet-700 hover:text-violet-900"
            onClick={() => (dock ? dock.openChat() : onTableClick(''))}
          >
            {t('bi.relationsChatHint')}
          </button>
        </div>
      ) : null}
    </section>
  );
}
