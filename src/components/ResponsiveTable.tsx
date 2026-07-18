import type { ReactNode } from 'react';

export type TableColumn<T> = {
  id: string;
  header: ReactNode;
  cell: (row: T) => ReactNode;
  /** Label in mobile card rows; string headers auto-fill when omitted */
  mobileLabel?: string;
  /** Primary row in mobile card header */
  mobilePrimary?: boolean;
  /** Hide this column entirely on mobile cards */
  mobileHide?: boolean;
  className?: string;
  headerClassName?: string;
};

type ResponsiveTableProps<T> = {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  emptyMessage?: string;
};

function headerToLabel(header: ReactNode): string | undefined {
  if (typeof header === 'string' || typeof header === 'number') return String(header);
  return undefined;
}

export default function ResponsiveTable<T>({
  columns,
  rows,
  rowKey,
  emptyMessage,
}: ResponsiveTableProps<T>) {
  const primaryCol = columns.find((c) => c.mobilePrimary) ?? columns[0];
  const mobileCols = columns.filter((c) => {
    if (c.mobileHide || c.id === primaryCol?.id) return false;
    return Boolean(c.mobileLabel ?? headerToLabel(c.header));
  });

  if (!rows.length && emptyMessage) {
    return <p className="p-6 text-center text-sm text-slate-500 sm:p-8">{emptyMessage}</p>;
  }

  return (
    <>
      {/* Desktop / large tablet — allow horizontal scroll when columns exceed viewport */}
      <div className="hidden overflow-x-auto overscroll-x-contain rounded-xl border border-surface-border/70 bg-white/70 shadow-sm lg:block">
        <table className="w-max min-w-full text-left text-sm">
          <thead className="border-b border-surface-border bg-surface-overlay/50 text-xs uppercase text-slate-500">
            <tr>
              {columns.map((col) => (
                <th
                  key={col.id}
                  className={['whitespace-nowrap px-4 py-3', col.headerClassName].filter(Boolean).join(' ')}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                className="border-b border-surface-border/60 hover:bg-surface-overlay/30"
              >
                {columns.map((col) => (
                  <td
                    key={col.id}
                    className={['px-4 py-3 align-top', col.className].filter(Boolean).join(' ')}
                  >
                    {col.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Phone + small tablet: stacked cards */}
      <ul className="divide-y divide-surface-border lg:hidden">
        {rows.map((row) => (
          <li key={rowKey(row)} className="space-y-3 p-3 sm:p-4">
            {primaryCol && (
              <div className="min-w-0 break-words text-sm font-medium text-slate-900">{primaryCol.cell(row)}</div>
            )}
            <dl className="space-y-2">
              {mobileCols.map((col) => {
                const label = col.mobileLabel ?? headerToLabel(col.header) ?? col.id;
                const isActions = col.id === 'actions';
                return (
                  <div
                    key={col.id}
                    className={
                      isActions
                        ? 'flex flex-col gap-1.5 border-t border-surface-border/60 pt-2'
                        : 'grid grid-cols-[minmax(5.5rem,38%)_1fr] items-start gap-2 text-sm'
                    }
                  >
                    {!isActions && (
                      <dt className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</dt>
                    )}
                    <dd className={isActions ? 'w-full min-w-0' : 'min-w-0 break-words text-right text-slate-800'}>
                      {col.cell(row)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </li>
        ))}
      </ul>
    </>
  );
}
