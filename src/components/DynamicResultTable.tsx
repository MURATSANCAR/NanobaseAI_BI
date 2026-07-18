import clsx from 'clsx';

type Props = {
  columns: string[];
  rows: Array<Record<string, unknown> | unknown[]>;
  maxCols?: number;
  maxRows?: number;
  className?: string;
  /** denser chat preview */
  compact?: boolean;
};

function cellValue(row: Record<string, unknown> | unknown[], col: string, colIndex: number): string {
  if (Array.isArray(row)) return String(row[colIndex] ?? '');
  return String((row as Record<string, unknown>)[col] ?? '');
}

/** Dynamic SQL/query result table: horizontal scroll on desktop, cards on phone. */
export default function DynamicResultTable({
  columns,
  rows,
  maxCols = 8,
  maxRows = 50,
  className,
  compact,
}: Props) {
  const cols = columns.slice(0, maxCols);
  const data = rows.slice(0, maxRows);
  if (!cols.length || !data.length) return null;

  const primary = cols[0];
  const rest = cols.slice(1);

  return (
    <div className={clsx(className)}>
      <div className={clsx('hidden overflow-x-auto lg:block', compact && 'max-h-48')}>
        <table className={clsx('w-full text-left', compact ? 'text-xs' : 'text-sm')}>
          <thead
            className={clsx(
              'sticky top-0 text-[10px] uppercase text-slate-500',
              compact ? 'bg-violet-50/90' : 'bg-surface-overlay/50',
            )}
          >
            <tr>
              {cols.map((c) => (
                <th key={c} className={clsx('whitespace-nowrap font-medium', compact ? 'px-2 py-1.5' : 'px-3 py-2')}>
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((row, i) => (
              <tr key={i} className="border-t border-surface-border/50">
                {cols.map((c, ci) => (
                  <td
                    key={c}
                    className={clsx(
                      'max-w-[10rem] truncate text-slate-700',
                      compact ? 'px-2 py-1.5' : 'px-3 py-2',
                    )}
                  >
                    {cellValue(row, c, ci)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className={clsx('divide-y divide-surface-border lg:hidden', compact && 'max-h-56 overflow-y-auto')}>
        {data.map((row, i) => (
          <li key={i} className={clsx('space-y-1.5', compact ? 'px-2 py-2' : 'px-3 py-3')}>
            <p className={clsx('break-words font-medium text-slate-900', compact ? 'text-xs' : 'text-sm')}>
              {cellValue(row, primary, 0) || `—`}
            </p>
            {rest.length > 0 && (
              <dl className="space-y-1">
                {rest.map((c, ci) => (
                  <div key={c} className="grid grid-cols-[minmax(4.5rem,36%)_1fr] gap-2 text-xs">
                    <dt className="truncate text-[10px] font-medium uppercase tracking-wide text-slate-500">{c}</dt>
                    <dd className="min-w-0 break-words text-right text-slate-700">{cellValue(row, c, ci + 1)}</dd>
                  </div>
                ))}
              </dl>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
