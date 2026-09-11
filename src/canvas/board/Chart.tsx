import { useMemo } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
} from 'recharts';
import type { ChartKind } from './store';

/** Kanvas paleti. Seriler bu sırayla renklenir. */
export const SERIES = ['#7C5CFF', '#FF6B4A', '#10B981', '#F59E0B', '#38BDF8', '#EC4899', '#84CC16', '#A855F7'];

export type Row = Record<string, unknown>;
export type Col = { name: string; type: string };

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const nf = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });

/** Kısa eksen etiketi: 1.240.000 → 1,2 Mn */
export function shortNum(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e9) return `${nf.format(v / 1e9)} Mr`;
  if (a >= 1e6) return `${nf.format(v / 1e6)} Mn`;
  if (a >= 1e3) return `${nf.format(v / 1e3)} B`;
  return nf.format(v);
}

export function numericCols(cols: Col[], rows: Row[]): string[] {
  return cols.filter((c) => rows.some((r) => isNum(r[c.name]))).map((c) => c.name);
}

export function labelCol(cols: Col[], rows: Row[]): string {
  const nums = new Set(numericCols(cols, rows));
  return cols.find((c) => !nums.has(c.name))?.name ?? cols[0]?.name ?? '';
}

/** Veri şekline bakıp uygun grafiği seçer; kullanıcı sonra değiştirebilir. */
export function suggestChart(cols: Col[], rows: Row[]): ChartKind {
  const nums = numericCols(cols, rows);
  if (!rows.length) return 'table';
  if (rows.length === 1 && nums.length === 1) return 'kpi';
  if (cols.length > 4 || rows.length > 40) return 'table';
  const label = labelCol(cols, rows);
  const looksTemporal = /ay|tarih|date|month|yil|yıl|donem|dönem/i.test(label);
  if (looksTemporal) return 'area';
  if (nums.length >= 2 && rows.length > 8) return 'scatter';
  if (rows.length <= 6) return 'donut';
  return 'column';
}

export const CHART_LABEL: Record<ChartKind, string> = {
  column: 'Sütun',
  bar: 'Çubuk',
  line: 'Çizgi',
  area: 'Alan',
  pie: 'Pasta',
  donut: 'Halka',
  scatter: 'Dağılım',
  treemap: 'Ağaç haritası',
  kpi: 'Tek değer',
  table: 'Tablo',
};

/** Verinin izin verdiği tipler; olmayanı teklif etmiyoruz. */
export function allowedCharts(cols: Col[], rows: Row[]): ChartKind[] {
  const nums = numericCols(cols, rows);
  const out: ChartKind[] = ['table'];
  if (!rows.length || !nums.length) return out;
  if (rows.length === 1 && nums.length >= 1) out.unshift('kpi');
  out.unshift('column', 'bar', 'line', 'area');
  const positive = rows.every((r) => nums.every((n) => !isNum(r[n]) || (r[n] as number) >= 0));
  if (positive && rows.length <= 12) out.push('pie', 'donut', 'treemap');
  if (nums.length >= 2) out.push('scatter');
  return [...new Set(out)];
}

const tooltipStyle = {
  borderRadius: 12,
  border: '1px solid rgba(255,255,255,.9)',
  background: 'rgba(255,255,255,.96)',
  boxShadow: '0 12px 36px rgba(20,30,60,.14)',
  fontSize: 12,
  fontWeight: 600,
};

/**
 * Pano kartının grafiği. Derinlik seçeneği sütun, çubuk ve pasta için
 * hafif bir 3B görünüm verir; veriyi değiştirmez, yalnız gölge ve eğim ekler.
 */
export default function Chart({
  kind,
  cols,
  rows,
  depth,
}: {
  kind: ChartKind;
  cols: Col[];
  rows: Row[];
  depth: boolean;
}) {
  const nums = useMemo(() => numericCols(cols, rows), [cols, rows]);
  const label = useMemo(() => labelCol(cols, rows), [cols, rows]);

  if (!rows.length) {
    return <div className="flex h-full items-center justify-center text-[12px] text-canvas-muted">Sonuç boş</div>;
  }

  if (kind === 'kpi') {
    const key = nums[0] ?? cols[0]?.name;
    const v = rows[0]?.[key];
    return (
      <div className="flex h-full flex-col items-center justify-center">
        <div className="font-mono text-4xl font-black tabular-nums tracking-tight text-canvas-ink">
          {isNum(v) ? shortNum(v) : String(v ?? '—')}
        </div>
        <div className="mt-1 text-[11px] font-semibold uppercase tracking-wide text-canvas-muted">{key}</div>
      </div>
    );
  }

  if (kind === 'table') {
    return (
      <div className="h-full overflow-auto">
        <table className="w-full border-collapse text-[11.5px]">
          <thead className="sticky top-0 bg-white/95">
            <tr>
              {cols.map((c) => (
                <th key={c.name} className="border-b border-slate-200 px-2 py-1.5 text-left font-bold text-canvas-muted">
                  {c.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 200).map((r, i) => (
              <tr key={i} className="odd:bg-slate-50/60">
                {cols.map((c) => (
                  <td key={c.name} className={['px-2 py-1', isNum(r[c.name]) ? 'text-right font-mono tabular-nums' : ''].join(' ')}>
                    {isNum(r[c.name]) ? nf.format(r[c.name] as number) : String(r[c.name] ?? '')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  const data = rows.map((r) => ({ ...r, __label: String(r[label] ?? '') }));
  const axis = { tick: { fontSize: 10, fill: '#94a3b8' }, tickLine: false, axisLine: false } as const;
  const depthFilter = depth ? 'drop-shadow(0 8px 10px rgba(20,30,60,.22))' : undefined;

  if (kind === 'pie' || kind === 'donut') {
    const key = nums[0];
    return (
      <div className="h-full" style={{ perspective: depth ? 900 : undefined }}>
        <div className="h-full" style={{ transform: depth ? 'rotateX(38deg)' : undefined, filter: depthFilter }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey={key}
                nameKey="__label"
                innerRadius={kind === 'donut' ? '52%' : 0}
                outerRadius="82%"
                paddingAngle={1}
                stroke="#fff"
                strokeWidth={2}
              >
                {data.map((_, i) => (
                  <Cell key={i} fill={SERIES[i % SERIES.length]} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => nf.format(v)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  if (kind === 'treemap') {
    const key = nums[0];
    return (
      <ResponsiveContainer width="100%" height="100%">
        <Treemap data={data} dataKey={key} nameKey="__label" stroke="#fff" fill={SERIES[0]}>
          <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => nf.format(v)} />
        </Treemap>
      </ResponsiveContainer>
    );
  }

  if (kind === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="rgba(30,41,59,.08)" />
          <XAxis dataKey={nums[0]} type="number" {...axis} tickFormatter={shortNum} />
          <YAxis dataKey={nums[1]} type="number" {...axis} tickFormatter={shortNum} width={48} />
          <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => nf.format(v)} />
          <Scatter data={data} fill={SERIES[0]} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  if (kind === 'line' || kind === 'area') {
    const Wrapper = kind === 'line' ? LineChart : AreaChart;
    return (
      <ResponsiveContainer width="100%" height="100%">
        <Wrapper data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
          <defs>
            {nums.map((n, i) => (
              <linearGradient key={n} id={`g-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SERIES[i % SERIES.length]} stopOpacity={0.32} />
                <stop offset="100%" stopColor={SERIES[i % SERIES.length]} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke="rgba(30,41,59,.08)" vertical={false} />
          <XAxis dataKey="__label" {...axis} />
          <YAxis {...axis} tickFormatter={shortNum} width={52} />
          <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => nf.format(v)} />
          {nums.map((n, i) =>
            kind === 'line' ? (
              <Line key={n} type="monotone" dataKey={n} stroke={SERIES[i % SERIES.length]} strokeWidth={2.5} dot={false} />
            ) : (
              <Area
                key={n}
                type="monotone"
                dataKey={n}
                stroke={SERIES[i % SERIES.length]}
                strokeWidth={2.5}
                fill={`url(#g-${i})`}
              />
            ),
          )}
          {nums.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
        </Wrapper>
      </ResponsiveContainer>
    );
  }

  const horizontal = kind === 'bar';
  return (
    <div className="h-full" style={{ perspective: depth ? 1100 : undefined }}>
      <div
        className="h-full"
        style={{ transform: depth ? 'rotateX(16deg) rotateY(-8deg)' : undefined, filter: depthFilter }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="rgba(30,41,59,.08)" vertical={horizontal} horizontal={!horizontal} />
            {horizontal ? (
              <>
                <XAxis type="number" {...axis} tickFormatter={shortNum} />
                <YAxis type="category" dataKey="__label" {...axis} width={110} />
              </>
            ) : (
              <>
                <XAxis dataKey="__label" {...axis} />
                <YAxis {...axis} tickFormatter={shortNum} width={52} />
              </>
            )}
            <Tooltip contentStyle={tooltipStyle} cursor={{ fill: 'rgba(124,92,255,.06)' }} formatter={(v: number) => nf.format(v)} />
            {nums.map((n, i) => (
              <Bar key={n} dataKey={n} fill={SERIES[i % SERIES.length]} radius={horizontal ? [0, 6, 6, 0] : [6, 6, 0, 0]} />
            ))}
            {nums.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
