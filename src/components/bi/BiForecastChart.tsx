import { useMemo } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { t } from '@/i18n';

export type BiForecastPayload = {
  metric: string;
  unit?: string | null;
  frequency: string;
  engine?: string;
  history: Array<{ period: string; value: number }>;
  forecast: Array<{ period: string; p10: number; p50: number; p90: number }>;
};

function fmtPeriod(iso: string, frequency: string): string {
  if (frequency === 'M') return iso.slice(0, 7);
  if (frequency === 'Q') {
    const d = new Date(iso);
    return `${d.getFullYear()}-Q${Math.floor(d.getMonth() / 3) + 1}`;
  }
  if (frequency === 'Y') return iso.slice(0, 4);
  return iso.slice(0, 10);
}

const fmtNum = (v: number) => new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 }).format(v);

export default function BiForecastChart({ data, height = 260 }: { data: BiForecastPayload; height?: number }) {
  const rows = useMemo(() => {
    const hist = data.history.map((h) => ({
      period: fmtPeriod(h.period, data.frequency),
      actual: h.value,
      kind: 'history' as const,
    }));
    const last = data.history[data.history.length - 1];
    const fc = data.forecast.map((f) => ({
      period: fmtPeriod(f.period, data.frequency),
      p10: f.p10,
      p50: f.p50,
      p90: f.p90,
      band: [f.p10, f.p90] as [number, number],
      kind: 'forecast' as const,
    }));
    // Bridge point so the forecast line starts where history ends.
    if (last && fc.length) {
      fc.unshift({
        period: fmtPeriod(last.period, data.frequency),
        p10: last.value,
        p50: last.value,
        p90: last.value,
        band: [last.value, last.value],
        kind: 'forecast' as const,
      });
    }
    const byPeriod = new Map<string, Record<string, unknown>>();
    for (const r of [...hist, ...fc]) {
      byPeriod.set(r.period, { ...(byPeriod.get(r.period) || {}), ...r });
    }
    return Array.from(byPeriod.values());
  }, [data]);

  const unit = data.unit ? ` ${data.unit}` : '';

  return (
    <div className="w-full" style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 4, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E1DFDD" />
          <XAxis dataKey="period" tick={{ fontSize: 11 }} minTickGap={16} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => fmtNum(v)} width={64} />
          <Tooltip
            formatter={(value: number | [number, number], name: string) => {
              if (Array.isArray(value)) return [`${fmtNum(value[0])} – ${fmtNum(value[1])}${unit}`, name];
              return [`${fmtNum(value)}${unit}`, name];
            }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Area
            type="monotone"
            dataKey="band"
            name={t('bi.forecast.band')}
            stroke="none"
            fill="#0F6CBD"
            fillOpacity={0.14}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="actual"
            name={t('bi.forecast.history')}
            stroke="#323130"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
          <Line
            type="monotone"
            dataKey="p50"
            name={t('bi.forecast.p50')}
            stroke="#0F6CBD"
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={{ r: 3 }}
            isAnimationActive={false}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
