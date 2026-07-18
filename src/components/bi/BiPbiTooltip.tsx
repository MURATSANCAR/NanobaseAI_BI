import type { TooltipProps } from 'recharts';
import { formatPbiNumber } from '@/components/bi/biVisualTheme';

type PayloadItem = { name?: string; value?: unknown; color?: string; dataKey?: string };

export default function BiPbiTooltip({
  active,
  payload,
  label,
  formatter,
}: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const items = payload as PayloadItem[];

  return (
    <div className="bi-pbi-tooltip">
      {label != null && label !== '' && (
        <div className="bi-pbi-tooltip-label">{String(label)}</div>
      )}
      <div className="space-y-1">
        {items.map((entry, i) => {
          const raw = entry.value;
          const display =
            typeof formatter === 'function'
              ? formatter(Number(raw), entry.name ?? '', entry as never, i, payload)
              : formatPbiNumber(raw);
          const text = Array.isArray(display) ? display[0] : display;
          return (
            <div key={i} className="bi-pbi-tooltip-row">
              <span className="bi-pbi-tooltip-dot" style={{ background: entry.color ?? '#118DFF' }} />
              <span className="bi-pbi-tooltip-name">{entry.name ?? entry.dataKey}</span>
              <span className="bi-pbi-tooltip-value">{String(text ?? '—')}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
