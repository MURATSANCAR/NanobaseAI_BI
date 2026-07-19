import type { TooltipProps } from 'recharts';
import { formatPbiNumber } from '@/components/bi/biVisualTheme';
import { biFieldLabel } from '@/utils/biFieldLabel';

type PayloadItem = { name?: string; value?: unknown; color?: string; dataKey?: string };

function seriesLabel(entry: PayloadItem): string {
  const raw = String(entry.name ?? entry.dataKey ?? '').trim();
  if (!raw) return '';
  // Category slice names (e.g. "Açık") stay as-is; column keys get localized.
  if (/^[a-z][a-z0-9_]*$/i.test(raw) && raw.length <= 32) return biFieldLabel(raw);
  return raw;
}

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
          const name = seriesLabel(entry);
          const display =
            typeof formatter === 'function'
              ? formatter(Number(raw), name, entry as never, i, payload)
              : formatPbiNumber(raw);
          const text = Array.isArray(display) ? display[0] : display;
          return (
            <div key={i} className="bi-pbi-tooltip-row">
              <span className="bi-pbi-tooltip-dot" style={{ background: entry.color ?? '#118DFF' }} />
              <span className="bi-pbi-tooltip-name">{name}</span>
              <span className="bi-pbi-tooltip-value">{String(text ?? '—')}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
