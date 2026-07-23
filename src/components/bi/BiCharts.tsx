import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  LabelList,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  RadialBar,
  RadialBarChart,
  ReferenceLine,
  ResponsiveContainer as RechartsResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  Treemap,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts';
import { TrendingDown, TrendingUp } from 'lucide-react';
import clsx from 'clsx';
import type { ComponentProps, ReactNode } from 'react';
import type { BiWidget } from '@/api/types';
import BiPbiTooltip from '@/components/bi/BiPbiTooltip';
import DynamicResultTable from '@/components/DynamicResultTable';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import {
  formatPbiNumber,
  PBI_ANIMATION,
  PBI_AXIS,
  PBI_BAR_RADIUS,
  PBI_CHART_ANIMATION,
  PBI_CHART_MARGIN,
  PBI_COLORS,
  PBI_GRID,
  PBI_NEGATIVE,
  PBI_POSITIVE,
  PBI_TOOLTIP,
  pbiPalette,
} from '@/components/bi/biVisualTheme';
import { isHorizontalBar, isStacked, normalizeVisualType } from '@/components/bi/biVisualTypes';
import { t } from '@/i18n';
import { biFieldLabel } from '@/utils/biFieldLabel';

const CHART_H_DEFAULT = 220;

/** Guard Recharts size probe — empty parents used to throw reading `width`. */
function ResponsiveContainer({
  children,
  width = '100%',
  height = '100%',
  ...rest
}: ComponentProps<typeof RechartsResponsiveContainer>) {
  const numericH = typeof height === 'number' ? height : CHART_H_DEFAULT;
  return (
    <RechartsResponsiveContainer
      width={width}
      height={height}
      minWidth={1}
      minHeight={1}
      debounce={50}
      initialDimension={{ width: 320, height: numericH > 0 ? numericH : CHART_H_DEFAULT }}
      {...rest}
    >
      {children}
    </RechartsResponsiveContainer>
  );
}

export type BiChartVariant = 'tile' | 'preview' | 'immersive';

export function resolveChartHeight(
  variant: BiChartVariant | undefined,
  narrow: boolean,
  medium: boolean,
  containerHeight?: number,
): number {
  if (containerHeight && containerHeight > 48) {
    return Math.max(100, containerHeight - 4);
  }
  if (variant === 'preview') return narrow ? 128 : 156;
  if (variant === 'immersive') return narrow ? 260 : medium ? 300 : 340;
  if (narrow) return 200;
  if (medium) return 232;
  return 260;
}

function cols(widget: BiWidget) {
  return widget.data?.columns ?? [];
}

function rows(widget: BiWidget) {
  return widget.data?.rows ?? [];
}

function rowCount(widget: BiWidget) {
  return rows(widget).length;
}

function truncateAxisLabel(value: unknown, max = 14): string {
  const s = String(value ?? '');
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

function BiChartFrame({
  height,
  children,
  empty,
}: {
  height: number;
  children?: ReactNode;
  empty?: boolean;
}) {
  if (empty) {
    return (
      <div className="bi-chart-empty bi-chart-frame--well" style={{ height, minHeight: height }}>
        <p>{t('bi.chartNotEnoughData')}</p>
      </div>
    );
  }
  return (
    <div
      className="bi-chart-frame bi-chart-frame--well"
      style={{ height, minHeight: height, width: '100%' }}
    >
      {children}
    </div>
  );
}

function key(widget: BiWidget, primary: 'x' | 'y' | 'value' | 'label' | 'series' | 'y2' | 'row' | 'col') {
  const c = cols(widget);
  const map = {
    x: widget.x_key ?? c[0] ?? 'x',
    y: widget.y_key ?? c[1] ?? 'y',
    value: widget.value_key ?? c[1] ?? c[0] ?? 'value',
    label: widget.label_key ?? widget.x_key ?? c[0] ?? 'name',
    series: widget.series_key ?? c[2],
    y2: widget.y2_key ?? c[2],
    row: widget.row_key ?? c[0] ?? 'row',
    col: widget.col_key ?? c[1] ?? 'col',
  };
  return map[primary];
}

function chartRows(widget: BiWidget, limit = 24) {
  const xk = key(widget, 'x');
  const yk = key(widget, 'y');
  return rows(widget).slice(0, limit).map((r) => ({
    ...r,
    name: String(r[xk] ?? ''),
    value: coerceNumber(r[yk]),
    [xk]: r[xk],
    [yk]: coerceNumber(r[yk]),
  }));
}

function coerceNumber(value: unknown): number {
  if (value == null || value === '') return 0;
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function stackedSeries(widget: BiWidget): string[] {
  const sk = key(widget, 'series');
  const c = cols(widget);
  if (sk && c.includes(sk)) {
    const set = new Set<string>();
    rows(widget).forEach((r) => set.add(String(r[sk] ?? '')));
    return [...set].slice(0, 6);
  }
  if (c.length >= 3) return c.slice(2, 6);
  return [];
}

function stackedData(widget: BiWidget) {
  const xk = key(widget, 'x');
  const yk = key(widget, 'y');
  const sk = key(widget, 'series');
  const grouped = new Map<string, Record<string, unknown>>();
  rows(widget)
    .slice(0, 48)
    .forEach((r) => {
      const x = String(r[xk] ?? '');
      const series = String(r[sk] ?? yk);
      const val = Number(r[yk]) || 0;
      if (!grouped.has(x)) grouped.set(x, { [xk]: x, name: x });
      const row = grouped.get(x)!;
      row[series] = (Number(row[series]) || 0) + val;
    });
  return [...grouped.values()];
}

type ChartProps = {
  widget: BiWidget;
  targetValue?: number;
  onDatumClick?: (column: string, value: string) => void;
  height?: number;
  variant?: BiChartVariant;
  containerHeight?: number;
};

function chartAnimationDuration(variant?: BiChartVariant) {
  return variant === 'preview' ? PBI_CHART_ANIMATION.duration : PBI_ANIMATION.duration;
}

function chartVivid(variant?: BiChartVariant) {
  return variant === 'preview' || variant === 'tile';
}

function paletteColor(variant: BiChartVariant | undefined, index = 0): string {
  const colors = pbiPalette(chartVivid(variant));
  return colors[index % colors.length] ?? PBI_COLORS[0];
}

/** Show numeric values on chart marks when there is room (avoid clutter). */
function showChartDataLabels(height: number, pointCount: number, variant?: BiChartVariant): boolean {
  if (pointCount <= 0) return false;
  if (pointCount > 16) return false;
  if (variant === 'preview' && height < 120) return pointCount <= 5;
  return height >= 120;
}

function formatChartDataLabel(value: unknown): string {
  const n = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(n)) return '';
  return formatPbiNumber(n);
}

const CHART_LABEL_STYLE = {
  fontSize: 10,
  fill: '#252423',
  fontWeight: 600 as const,
};

function ChartValueLabels({
  dataKey,
  position,
  fill,
}: {
  dataKey: string;
  position: 'top' | 'right' | 'center' | 'insideTop';
  fill?: string;
}) {
  return (
    <LabelList
      dataKey={dataKey}
      position={position}
      formatter={formatChartDataLabel as never}
      style={{ ...CHART_LABEL_STYLE, fill: fill ?? CHART_LABEL_STYLE.fill }}
    />
  );
}

function chartMarginWithLabels(withLabels: boolean) {
  return withLabels ? { ...PBI_CHART_MARGIN, top: 28 } : PBI_CHART_MARGIN;
}


export function BiBarChartWidget({ widget, targetValue, onDatumClick, height = CHART_H_DEFAULT, variant }: ChartProps) {
  const vtype = normalizeVisualType(widget.type);
  const horizontal = isHorizontalBar(vtype);
  const stacked = isStacked(vtype);
  const xk = key(widget, 'x');
  const yk = key(widget, 'y');
  const animDuration = chartAnimationDuration(variant);
  const barRadius = PBI_BAR_RADIUS;
  // Solid fills only — CSS transform on 3D tiles breaks SVG url(#gradient) paint.

  if (!rowCount(widget)) {
    return <BiChartFrame height={height} empty />;
  }

  if (stacked) {
    const data = stackedData(widget);
    const series = stackedSeries(widget);
    const layout = horizontal ? 'vertical' : 'horizontal';
    const showLabels = showChartDataLabels(height, data.length, variant) && series.length <= 4;
    const lastSeries = series[series.length - 1];
    return (
      <BiChartFrame height={height}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout={layout as 'horizontal' | 'vertical'} margin={chartMarginWithLabels(showLabels)}>
          <CartesianGrid {...PBI_GRID} />
          {horizontal ? (
            <>
              <XAxis type="number" tick={PBI_AXIS} />
              <YAxis type="category" dataKey="name" tick={PBI_AXIS} width={88} />
            </>
          ) : (
            <>
              <XAxis dataKey="name" tick={PBI_AXIS} interval={0} angle={-18} textAnchor="end" height={48} />
              <YAxis tick={PBI_AXIS} />
            </>
          )}
          <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} iconType="circle" iconSize={8} />
          {series.map((s, i) => (
            <Bar
              key={s}
              dataKey={s}
              stackId="a"
              fill={paletteColor(variant, i)}
              radius={i === series.length - 1 ? [barRadius, barRadius, 0, 0] : undefined}
              animationDuration={animDuration}
            >
              {showLabels && s === lastSeries ? (
                <ChartValueLabels dataKey={s} position={horizontal ? 'right' : 'top'} />
              ) : null}
            </Bar>
          ))}
          </BarChart>
        </ResponsiveContainer>
      </BiChartFrame>
    );
  }

  const data = chartRows(widget);
  const showLabels = showChartDataLabels(height, data.length, variant);
  if (horizontal) {
    return (
      <BiChartFrame height={height}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} layout="vertical" margin={chartMarginWithLabels(showLabels)}>
          <CartesianGrid {...PBI_GRID} />
          <XAxis type="number" tick={PBI_AXIS} />
          <YAxis type="category" dataKey="name" tick={PBI_AXIS} width={96} />
          <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
          {targetValue != null && <ReferenceLine x={targetValue} stroke="#E66C37" strokeDasharray="5 5" strokeWidth={1.5} />}
          <Bar
            dataKey={yk}
            fill={paletteColor(variant, 0)}
            radius={[0, barRadius, barRadius, 0]}
            animationDuration={animDuration}
            onClick={(d) => {
              const payload = d?.payload as Record<string, unknown> | undefined;
              if (payload && onDatumClick) onDatumClick(String(xk), String(payload[xk] ?? ''));
            }}
            style={{ cursor: onDatumClick ? 'pointer' : 'default' }}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={paletteColor(variant, i)} />
            ))}
            {showLabels ? <ChartValueLabels dataKey={yk} position="right" /> : null}
          </Bar>
          </BarChart>
        </ResponsiveContainer>
      </BiChartFrame>
    );
  }

  return (
    <BiChartFrame height={height}>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={chartMarginWithLabels(showLabels)}>
        <CartesianGrid {...PBI_GRID} />
        <XAxis dataKey={xk} tick={PBI_AXIS} interval={0} angle={-16} textAnchor="end" height={48} tickFormatter={(v) => truncateAxisLabel(v)} />
        <YAxis tick={PBI_AXIS} width={44} />
        <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
        {targetValue != null && <ReferenceLine y={targetValue} stroke="#E66C37" strokeDasharray="5 5" strokeWidth={1.5} />}
        <Bar
          dataKey={yk}
          fill={paletteColor(variant, 0)}
          radius={[barRadius, barRadius, 0, 0]}
          animationDuration={animDuration}
          onClick={(d) => {
            const payload = d?.payload as Record<string, unknown> | undefined;
            if (payload && onDatumClick) onDatumClick(String(xk), String(payload[xk] ?? ''));
          }}
          style={{ cursor: onDatumClick ? 'pointer' : 'default' }}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={paletteColor(variant, i)} />
          ))}
          {showLabels ? <ChartValueLabels dataKey={yk} position="top" /> : null}
        </Bar>
        </BarChart>
      </ResponsiveContainer>
    </BiChartFrame>
  );
}

export function BiLineChartWidget({ widget, targetValue, onDatumClick, height = CHART_H_DEFAULT, variant }: ChartProps) {
  const data = chartRows(widget);
  const xk = key(widget, 'x');
  const yk = key(widget, 'y');
  const animDuration = chartAnimationDuration(variant);
  const stroke = paletteColor(variant, 0);
  const barRadius = PBI_BAR_RADIUS;
  const showLabels = showChartDataLabels(height, data.length, variant);
  if (!data.length) return <BiChartFrame height={height} empty />;
  if (data.length === 1) {
    return (
      <BiChartFrame height={height}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={chartMarginWithLabels(true)}>
            <CartesianGrid {...PBI_GRID} />
            <XAxis dataKey={xk} tick={PBI_AXIS} tickFormatter={(v) => truncateAxisLabel(v)} />
            <YAxis tick={PBI_AXIS} width={44} />
            <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
            <Bar dataKey={yk} fill={stroke} radius={[barRadius, barRadius, 0, 0]} animationDuration={animDuration}>
              <ChartValueLabels dataKey={yk} position="top" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </BiChartFrame>
    );
  }
  return (
    <BiChartFrame height={height}>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={chartMarginWithLabels(showLabels)}>
        <CartesianGrid {...PBI_GRID} />
        <XAxis dataKey={xk} tick={PBI_AXIS} tickFormatter={(v) => truncateAxisLabel(v)} interval="preserveStartEnd" />
        <YAxis tick={PBI_AXIS} width={44} />
        <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
        {targetValue != null && <ReferenceLine y={targetValue} stroke="#E66C37" strokeDasharray="5 5" strokeWidth={1.5} />}
        <Line
          type="monotone"
          dataKey={yk}
          stroke={stroke}
          strokeWidth={2.5}
          dot={{ r: 3, fill: '#fff', stroke, strokeWidth: 2, cursor: onDatumClick ? 'pointer' : 'default' }}
          activeDot={{ r: 6, fill: stroke, stroke: '#fff', strokeWidth: 2 }}
          animationDuration={animDuration}
          onClick={(d) => {
            const payload = (d as { payload?: Record<string, unknown> })?.payload;
            if (payload && onDatumClick) onDatumClick(String(xk), String(payload[xk] ?? ''));
          }}
        >
          {showLabels ? <ChartValueLabels dataKey={yk} position="top" /> : null}
        </Line>
        </LineChart>
      </ResponsiveContainer>
    </BiChartFrame>
  );
}

export function BiAreaChartWidget({ widget, height = CHART_H_DEFAULT, variant }: ChartProps) {
  const data = chartRows(widget);
  const xk = key(widget, 'x');
  const yk = key(widget, 'y');
  const animDuration = chartAnimationDuration(variant);
  const stroke = paletteColor(variant, 0);
  const barRadius = PBI_BAR_RADIUS;
  const showLabels = showChartDataLabels(height, data.length, variant);
  if (!data.length) return <BiChartFrame height={height} empty />;
  if (data.length === 1) {
    return (
      <BiChartFrame height={height}>
        <ResponsiveContainer width="100%" height={height}>
          <BarChart data={data} margin={chartMarginWithLabels(true)}>
            <CartesianGrid {...PBI_GRID} />
            <XAxis dataKey={xk} tick={PBI_AXIS} tickFormatter={(v) => truncateAxisLabel(v)} />
            <YAxis tick={PBI_AXIS} width={44} />
            <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
            <Bar dataKey={yk} fill={stroke} radius={[barRadius, barRadius, 0, 0]} animationDuration={animDuration}>
              <ChartValueLabels dataKey={yk} position="top" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </BiChartFrame>
    );
  }
  return (
    <BiChartFrame height={height}>
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={chartMarginWithLabels(showLabels)}>
        <CartesianGrid {...PBI_GRID} />
        <XAxis dataKey={xk} tick={PBI_AXIS} tickFormatter={(v) => truncateAxisLabel(v)} interval="preserveStartEnd" />
        <YAxis tick={PBI_AXIS} width={44} />
        <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
        <Area
          type="monotone"
          dataKey={yk}
          stroke={stroke}
          strokeWidth={2}
          fill={stroke}
          fillOpacity={chartVivid(variant) ? 0.28 : 0.18}
          animationDuration={animDuration}
        >
          {showLabels ? <ChartValueLabels dataKey={yk} position="top" /> : null}
        </Area>
        </AreaChart>
      </ResponsiveContainer>
    </BiChartFrame>
  );
}

export function BiComboChartWidget({ widget, onDatumClick, height = CHART_H_DEFAULT, variant }: ChartProps) {
  const data = chartRows(widget);
  const xk = key(widget, 'x');
  const yk = key(widget, 'y');
  const y2k = key(widget, 'y2');
  const animDuration = chartAnimationDuration(variant);
  const barFill = paletteColor(variant, 0);
  const lineStroke = paletteColor(variant, 2);
  const barRadius = PBI_BAR_RADIUS;
  const hasLine = cols(widget).includes(y2k) && data.some((r) => coerceNumber(r[y2k]) !== 0);
  const showLabels = showChartDataLabels(height, data.length, variant);
  if (!data.length) {
    return <BiChartFrame height={height} empty />;
  }
  const margin = { ...chartMarginWithLabels(showLabels), right: hasLine ? 48 : 16 };
  return (
    <BiChartFrame height={height}>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={margin}>
          <CartesianGrid {...PBI_GRID} />
          <XAxis dataKey={xk} tick={PBI_AXIS} tickFormatter={(v) => truncateAxisLabel(v)} interval={0} angle={-16} textAnchor="end" height={48} />
          <YAxis yAxisId="left" tick={PBI_AXIS} width={44} />
          {hasLine && <YAxis yAxisId="right" orientation="right" tick={PBI_AXIS} width={44} />}
          <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
          <Legend wrapperStyle={{ fontSize: 11, paddingTop: 8 }} iconType="circle" iconSize={8} />
          <Bar
            yAxisId="left"
            dataKey={yk}
            name={biFieldLabel(yk)}
            fill={barFill}
            radius={[barRadius, barRadius, 0, 0]}
            animationDuration={animDuration}
            onClick={(d) => {
              const payload = d?.payload as Record<string, unknown> | undefined;
              if (payload && onDatumClick) onDatumClick(String(xk), String(payload[xk] ?? ''));
            }}
          >
            {showLabels ? <ChartValueLabels dataKey={yk} position="top" /> : null}
          </Bar>
          {hasLine && (
            <Line
              yAxisId="right"
              type="monotone"
              dataKey={y2k}
              name={biFieldLabel(y2k)}
              stroke={lineStroke}
              strokeWidth={2.5}
              dot={{ r: 3, fill: '#fff', stroke: lineStroke, strokeWidth: 2 }}
              animationDuration={animDuration}
            >
              {showLabels ? <ChartValueLabels dataKey={y2k} position="top" /> : null}
            </Line>
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </BiChartFrame>
  );
}

export function BiPieChartWidget({ widget, onDatumClick, donut = false, height = CHART_H_DEFAULT, variant }: ChartProps & { donut?: boolean }) {
  const labelKey = key(widget, 'label');
  const valueKey = key(widget, 'value');
  const animDuration = chartAnimationDuration(variant);
  const data = rows(widget)
    .slice(0, 8)
    .map((r) => ({ name: String(r[labelKey] ?? ''), value: coerceNumber(r[valueKey]) }));
  const total = data.reduce((s, d) => s + d.value, 0);
  if (!data.length || total === 0) return <BiChartFrame height={height} empty />;
  const showSliceLabels = !donut && height >= 160;
  return (
    <BiChartFrame height={height}>
      <ResponsiveContainer width="100%" height={height}>
        <PieChart margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            cx="50%"
            cy={donut ? '46%' : '44%'}
            innerRadius={donut ? '52%' : 0}
            outerRadius={donut ? '72%' : '76%'}
            paddingAngle={donut ? 2 : 1}
            label={
              showSliceLabels
                ? ({ name, percent, value }) =>
                    `${truncateAxisLabel(String(name ?? ''), 10)} ${formatPbiNumber(Number(value) || 0)} (${((percent ?? 0) * 100).toFixed(0)}%)`
                : false
            }
            labelLine={showSliceLabels}
          onClick={(_, idx) => {
            const row = data[idx];
            if (row && onDatumClick) onDatumClick(String(labelKey), row.name);
          }}
          style={{ cursor: onDatumClick ? 'pointer' : 'default' }}
          animationDuration={animDuration}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={paletteColor(variant, i)} stroke="#fff" strokeWidth={2} />
          ))}
        </Pie>
        {donut && (
          <text x="50%" y="48%" textAnchor="middle" className="fill-[#252423] text-2xl font-semibold">
            {formatPbiNumber(total)}
          </text>
        )}
        <Tooltip content={<BiPbiTooltip />} />
        <Legend wrapperStyle={{ fontSize: 10, paddingTop: 2 }} iconType="circle" iconSize={8} formatter={(v) => truncateAxisLabel(v, 16)} />
        </PieChart>
      </ResponsiveContainer>
    </BiChartFrame>
  );
}

export function BiScatterChartWidget({ widget, bubble = false, height = CHART_H_DEFAULT, variant }: ChartProps & { bubble?: boolean }) {
  const xk = key(widget, 'x');
  const yk = key(widget, 'y');
  const zk = key(widget, 'value');
  const fill = paletteColor(variant, 0);
  const data = rows(widget).slice(0, 60).map((r, i) => ({
    x: coerceNumber(r[xk]) || i + 1,
    y: coerceNumber(r[yk]),
    z: bubble ? Math.max(20, coerceNumber(r[zk])) : 40,
    name: String(r[key(widget, 'label')] ?? i),
  }));
  if (!data.length) return <BiChartFrame height={height} empty />;
  return (
    <BiChartFrame height={height}>
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
          <CartesianGrid {...PBI_GRID} />
          <XAxis type="number" dataKey="x" name={biFieldLabel(xk)} tick={PBI_AXIS} />
          <YAxis type="number" dataKey="y" name={biFieldLabel(yk)} tick={PBI_AXIS} width={44} domain={['auto', 'auto']} />
          {bubble && <ZAxis type="number" dataKey="z" range={[60, 400]} />}
          <Tooltip content={<BiPbiTooltip />} cursor={{ strokeDasharray: '3 3' }} />
          <Scatter data={data} fill={fill} fillOpacity={0.85} />
        </ScatterChart>
      </ResponsiveContainer>
    </BiChartFrame>
  );
}

export function BiWaterfallChartWidget({ widget, height = CHART_H_DEFAULT, variant }: ChartProps) {
  const xk = key(widget, 'x');
  const yk = key(widget, 'y');
  const animDuration = chartAnimationDuration(variant);
  const barRadius = PBI_BAR_RADIUS;
  let running = 0;
  const data = rows(widget).slice(0, 16).map((r) => {
    const delta = Number(r[yk]) || 0;
    const start = running;
    running += delta;
    const end = running;
    const base = Math.min(start, end);
    const rise = Math.abs(delta);
    return {
      name: String(r[xk] ?? ''),
      base,
      rise,
      delta,
      fill: delta >= 0 ? PBI_POSITIVE : PBI_NEGATIVE,
    };
  });
  // Closing total column
  if (data.length) {
    data.push({
      name: t('bi.chart.total'),
      base: 0,
      rise: Math.abs(running),
      delta: running,
      fill: paletteColor(variant, 0),
    });
  }
  const showLabels = showChartDataLabels(height, data.length, variant);
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={chartMarginWithLabels(showLabels)} stackOffset="none">
        <CartesianGrid {...PBI_GRID} />
        <XAxis dataKey="name" tick={PBI_AXIS} interval={0} angle={-18} textAnchor="end" height={52} />
        <YAxis tick={PBI_AXIS} width={48} />
        <Tooltip content={<BiPbiTooltip />} cursor={PBI_TOOLTIP.cursor} />
        <Bar dataKey="base" stackId="wf" fill="transparent" legendType="none" />
        <Bar dataKey="rise" stackId="wf" radius={[barRadius, barRadius, 0, 0]} animationDuration={animDuration}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.fill} />
          ))}
          {showLabels ? (
            <LabelList
              dataKey="delta"
              position="top"
              formatter={formatChartDataLabel as never}
              style={CHART_LABEL_STYLE}
            />
          ) : null}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function BiFunnelChartWidget({ widget, height = CHART_H_DEFAULT, onDatumClick, variant }: ChartProps) {
  const labelKey = key(widget, 'label');
  const valueKey = key(widget, 'value');
  const data = [...rows(widget)]
    .slice(0, 8)
    .map((r) => ({ name: String(r[labelKey] ?? ''), value: Number(r[valueKey]) || 0 }))
    .sort((a, b) => b.value - a.value);
  const max = data[0]?.value || 1;
  return (
    <div className="bi-pbi-funnel flex flex-col justify-center gap-1.5 px-1" style={{ minHeight: height, height: '100%' }}>
      {data.map((row, i) => {
        const pct = Math.max(18, (row.value / max) * 100);
        const inset = (100 - pct) / 2;
        const c0 = paletteColor(variant, i);
        const c1 = paletteColor(variant, i + 1);
        return (
          <button
            key={i}
            type="button"
            className="bi-pbi-funnel-row bi-pbi-funnel-row--taper"
            style={{ ['--funnel-inset' as string]: `${inset}%` }}
            onClick={() => onDatumClick?.(String(labelKey), row.name)}
          >
            <span className="bi-pbi-funnel-label" title={row.name}>{row.name}</span>
            <div className="bi-pbi-funnel-track">
              <div
                className="bi-pbi-funnel-bar bi-pbi-funnel-bar--taper"
                style={{
                  width: '100%',
                  background: `linear-gradient(90deg, ${c0}, ${c1}88)`,
                }}
              >
                <span className="bi-pbi-funnel-value">{formatPbiNumber(row.value)}</span>
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function makeTreemapCell(variant?: BiChartVariant) {
  return function TreemapCell(props?: {
    x?: number;
    y?: number;
    width?: number;
    height?: number;
    index?: number;
    name?: string;
    value?: number;
  }) {
    if (!props) return null;
    const { x = 0, y = 0, width = 0, height = 0, index = 0, name = '', value = 0 } = props;
    if (width < 2 || height < 2) return null;
    const fill = paletteColor(variant, index);
    return (
      <g>
        <rect x={x} y={y} width={width} height={height} fill={fill} stroke="#fff" strokeWidth={2} rx={4} />
        {width > 36 && height > 22 && (
          <text x={x + width / 2} y={y + height / 2 - 4} textAnchor="middle" fill="#fff" fontSize={10} fontWeight={600}>
            {truncateAxisLabel(name, 12)}
          </text>
        )}
        {width > 36 && height > 34 && (
          <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" fill="rgba(255,255,255,0.9)" fontSize={9}>
            {formatPbiNumber(value)}
          </text>
        )}
      </g>
    );
  };
}

export function BiTreemapChartWidget({ widget, height = CHART_H_DEFAULT, variant }: ChartProps) {
  const labelKey = key(widget, 'label');
  const valueKey = key(widget, 'value');
  const animDuration = chartAnimationDuration(variant);
  const data = rows(widget)
    .slice(0, 20)
    .map((r, i) => ({
      name: String(r[labelKey] ?? i),
      size: coerceNumber(r[valueKey]),
    }))
    .filter((d) => d.size > 0);
  if (!data.length) return <BiChartFrame height={height} empty />;
  const TreemapCell = makeTreemapCell(variant);
  return (
    <BiChartFrame height={height}>
      <ResponsiveContainer width="100%" height={height}>
        <Treemap data={data} dataKey="size" nameKey="name" stroke="#fff" content={<TreemapCell />} animationDuration={animDuration} />
      </ResponsiveContainer>
    </BiChartFrame>
  );
}

export function BiGaugeChartWidget({ widget, targetValue, height = 200, variant }: ChartProps & { height?: number }) {
  const valueKey = key(widget, 'value');
  const raw = rows(widget)[0]?.[valueKey];
  const value = Number(raw) || 0;
  const max = targetValue ?? widget.max_value ?? Math.max(value * 1.2, 100);
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const fill = paletteColor(variant, 0);
  const animDuration = chartAnimationDuration(variant);
  const data = [{ name: biFieldLabel('value'), value: pct }];
  const gaugeH = Math.max(140, Math.min(height, 220));
  return (
    <div className={clsx('bi-pbi-gauge flex h-full flex-col items-center justify-center py-1', chartVivid(variant) && 'bi-pbi-kpi-pulse')}>
      <ResponsiveContainer width="100%" height={gaugeH}>
        <RadialBarChart cx="50%" cy="72%" innerRadius="68%" outerRadius="100%" barSize={16} data={data} startAngle={200} endAngle={-20}>
          <RadialBar
            background={{ fill: '#F0EEEC' }}
            dataKey="value"
            fill={fill}
            cornerRadius={8}
            animationDuration={animDuration}
          />
        </RadialBarChart>
      </ResponsiveContainer>
      <div className="bi-pbi-gauge-value -mt-20 text-center">
        <div className="bi-pbi-kpi-number text-[2rem]">{formatPbiNumber(value, widget.format)}</div>
        {targetValue != null && (
          <div className="mt-1 text-xs text-[#605E5C]">
            {t('bi.vsTarget')} {formatPbiNumber(targetValue)}
          </div>
        )}
        <div className="mt-2 mx-auto h-1.5 w-32 overflow-hidden rounded-full bg-[#F0EEEC]">
          <div className="h-full rounded-full bg-gradient-to-r from-[#12239E] to-[#118DFF] transition-all duration-700" style={{ width: `${pct}%` }} />
        </div>
      </div>
    </div>
  );
}

function KpiSparkline({ widget, variant }: { widget: BiWidget; variant?: BiChartVariant }) {
  const yk = key(widget, 'y');
  const xk = key(widget, 'x');
  const stroke = paletteColor(variant, 0);
  const spark = rows(widget)
    .slice(0, 12)
    .map((r, i) => ({ i, v: Number(r[yk] ?? r[key(widget, 'value')]) || 0, name: String(r[xk] ?? i) }));
  if (spark.length < 2) return null;
  return (
    <div className="bi-pbi-sparkline mt-3 h-10 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={spark} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <Area
            type="monotone"
            dataKey="v"
            stroke={stroke}
            strokeWidth={1.5}
            fill={stroke}
            fillOpacity={chartVivid(variant) ? 0.28 : 0.18}
            dot={false}
            animationDuration={chartAnimationDuration(variant)}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function BiCardWidget({ widget, kpi = false, variant }: { widget: BiWidget; kpi?: boolean; variant?: BiChartVariant }) {
  const valueKey = key(widget, 'value');
  const trendKey = widget.trend_key ?? cols(widget)[1];
  const row0 = rows(widget)[0];
  const row1 = rows(widget)[1];
  const value = row0 ? row0[valueKey] : null;
  const trend = kpi && row1 ? Number(row1[trendKey ?? valueKey]) : null;
  const prev = kpi && row0 && trendKey ? Number(row0[trendKey]) : null;
  let delta: number | null = null;
  if (kpi && prev != null && trend != null && prev !== 0) delta = ((trend - prev) / Math.abs(prev)) * 100;
  else if (kpi && widget.target_value && value != null) {
    delta = ((Number(value) - widget.target_value) / widget.target_value) * 100;
  }
  const positive = delta != null && delta >= 0;
  const targetPct =
    kpi && widget.target_value && value != null
      ? Math.min(100, Math.max(0, (Number(value) / widget.target_value) * 100))
      : null;

  return (
    <div className={clsx('bi-pbi-kpi flex h-full min-h-0 flex-col justify-between px-1 py-0.5', kpi && 'bi-pbi-tile--kpi bi-pbi-kpi-pulse')}>
      <div className="min-w-0">
        {widget.description && widget.description !== widget.title && (
          <div className="bi-pbi-kpi-label">{widget.description}</div>
        )}
        <div className="bi-pbi-kpi-number mt-1">{formatPbiNumber(value, widget.format)}</div>
        {kpi && delta != null && (
          <div className={clsx('bi-pbi-trend-pill mt-3', positive ? 'bi-pbi-trend-pill--up' : 'bi-pbi-trend-pill--down')}>
            {positive ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
            <span>{Math.abs(delta).toFixed(1)}%</span>
            {widget.target_value != null && <span className="opacity-75">{t('bi.vsTarget')}</span>}
          </div>
        )}
        {targetPct != null && (
          <div className="mt-3">
            <div className="mb-1 flex justify-between text-[10px] text-[#605E5C]">
              <span>{t('bi.vsTarget')}</span>
              <span className="tabular-nums">{targetPct.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-[#F0EEEC]">
              <div
                className={clsx('h-full rounded-full transition-all duration-700', positive ? 'bg-gradient-to-r from-emerald-500 to-emerald-400' : 'bg-gradient-to-r from-rose-500 to-rose-400')}
                style={{ width: `${targetPct}%` }}
              />
            </div>
          </div>
        )}
      </div>
      {kpi && <KpiSparkline widget={widget} variant={variant} />}
    </div>
  );
}

export function BiMultiCardWidget({ widget }: { widget: BiWidget }) {
  const labelKey = key(widget, 'label');
  const valueKey = key(widget, 'value');
  const items = rows(widget).slice(0, 4);
  return (
    <div className="grid h-full grid-cols-1 gap-3 sm:grid-cols-2">
      {items.map((r, i) => (
        <div key={i} className="bi-pbi-mini-kpi" data-accent={i % 6}>
          <div className="bi-pbi-mini-kpi-label">{String(r[labelKey] ?? '')}</div>
          <div className="bi-pbi-mini-kpi-value">{formatPbiNumber(r[valueKey], widget.format)}</div>
        </div>
      ))}
    </div>
  );
}

export function BiScenarioCompareWidget({ widget }: { widget: BiWidget }) {
  const valueKey = key(widget, 'value');
  const labelKey = key(widget, 'label');
  const data = widget.data as { rows?: Record<string, unknown>[]; attainment_pct?: number | null } | undefined;
  const r = rows(widget);
  const actual = r[0];
  const target = r[1];
  const actualVal = actual ? Number(actual[valueKey]) : null;
  const targetVal = target != null ? Number(target[valueKey]) : widget.target_value ?? null;
  let attainment =
    data?.attainment_pct != null && Number.isFinite(Number(data.attainment_pct))
      ? Number(data.attainment_pct)
      : null;
  if (attainment == null && actualVal != null && targetVal != null && targetVal !== 0) {
    attainment = (actualVal / Math.abs(targetVal)) * 100;
  }
  const onTrack = attainment != null && attainment >= 100;

  return (
    <div className="flex h-full min-h-0 flex-col justify-between gap-3 px-1 py-0.5">
      <div className="grid grid-cols-2 gap-3">
        <div className="bi-pbi-mini-kpi" data-accent={0}>
          <div className="bi-pbi-mini-kpi-label">{String(actual?.[labelKey] ?? t('bi.scenarioActual'))}</div>
          <div className="bi-pbi-mini-kpi-value">{formatPbiNumber(actualVal, widget.format)}</div>
        </div>
        <div className="bi-pbi-mini-kpi" data-accent={1}>
          <div className="bi-pbi-mini-kpi-label">{String(target?.[labelKey] ?? t('bi.scenarioTarget'))}</div>
          <div className="bi-pbi-mini-kpi-value">{formatPbiNumber(targetVal, widget.format)}</div>
        </div>
      </div>
      {attainment != null && (
        <div className={clsx('bi-pbi-trend-pill self-start', onTrack ? 'bi-pbi-trend-pill--up' : 'bi-pbi-trend-pill--down')}>
          <span>{attainment.toFixed(1)}%</span>
          <span className="opacity-75">{t('bi.scenarioAttainment')}</span>
        </div>
      )}
    </div>
  );
}

export function BiPeriodCompareWidget({ widget }: { widget: BiWidget }) {
  const valueKey = key(widget, 'value');
  const labelKey = key(widget, 'label');
  const data = widget.data as { rows?: Record<string, unknown>[]; delta_pct?: number | null } | undefined;
  const r = rows(widget);
  const current = r[0];
  const prior = r[1];
  const currentVal = current ? Number(current[valueKey]) : null;
  const priorVal = prior ? Number(prior[valueKey]) : null;
  let delta =
    data?.delta_pct != null && Number.isFinite(Number(data.delta_pct))
      ? Number(data.delta_pct)
      : null;
  if (delta == null && currentVal != null && priorVal != null && priorVal !== 0) {
    delta = ((currentVal - priorVal) / Math.abs(priorVal)) * 100;
  }
  const positive = delta != null && delta >= 0;
  const currentLabel = String(current?.[labelKey] ?? widget.current_label ?? t('bi.compareCurrent'));
  const priorLabel = String(prior?.[labelKey] ?? widget.prior_label ?? t('bi.comparePrior'));

  return (
    <div className="flex h-full min-h-0 flex-col justify-between gap-3 px-1 py-0.5">
      <div className="grid grid-cols-2 gap-3">
        <div className="bi-pbi-mini-kpi" data-accent={0}>
          <div className="bi-pbi-mini-kpi-label">{currentLabel}</div>
          <div className="bi-pbi-mini-kpi-value">{formatPbiNumber(currentVal, widget.format)}</div>
        </div>
        <div className="bi-pbi-mini-kpi" data-accent={1}>
          <div className="bi-pbi-mini-kpi-label">{priorLabel}</div>
          <div className="bi-pbi-mini-kpi-value">{formatPbiNumber(priorVal, widget.format)}</div>
        </div>
      </div>
      {delta != null && (
        <div className={clsx('bi-pbi-trend-pill self-start', positive ? 'bi-pbi-trend-pill--up' : 'bi-pbi-trend-pill--down')}>
          {positive ? <TrendingUp className="h-3.5 w-3.5" /> : <TrendingDown className="h-3.5 w-3.5" />}
          <span>{Math.abs(delta).toFixed(1)}%</span>
          <span className="opacity-75">{t('bi.compareDelta')}</span>
        </div>
      )}
    </div>
  );
}

export function BiMatrixWidget({ widget, maxHeight, onDatumClick }: { widget: BiWidget; maxHeight?: number; onDatumClick?: (column: string, value: string) => void }) {
  const narrow = useMediaQuery('(max-width: 639px)');
  const rowKey = key(widget, 'row');
  const colKey = key(widget, 'col');
  const valueKey = key(widget, 'value');
  const rowSet = [...new Set(rows(widget).map((r) => String(r[rowKey] ?? '')))].slice(0, 12);
  const colSet = [...new Set(rows(widget).map((r) => String(r[colKey] ?? '')))].slice(0, 8);
  const lookup = new Map<string, number>();
  rows(widget).forEach((r) => {
    lookup.set(`${r[rowKey]}|${r[colKey]}`, Number(r[valueKey]) || 0);
  });
  const colTotals = colSet.map((col) => rowSet.reduce((s, row) => s + (lookup.get(`${row}|${col}`) || 0), 0));
  const grand = colTotals.reduce((a, b) => a + b, 0);

  if (narrow) {
    return (
      <div
        className="space-y-2 overflow-y-auto overscroll-contain [-webkit-overflow-scrolling:touch]"
        style={maxHeight ? { maxHeight } : undefined}
      >
        {rowSet.map((row) => {
          const rowTotal = colSet.reduce((s, col) => s + (lookup.get(`${row}|${col}`) || 0), 0);
          return (
            <div key={row} className="rounded-xl border border-[#E1DFDD] bg-white p-2.5 shadow-sm">
              <button
                type="button"
                className="min-h-10 w-full text-left text-sm font-semibold text-[#252423] hover:underline"
                onClick={() => onDatumClick?.(String(rowKey), row)}
              >
                {row || '—'}
              </button>
              <dl className="mt-1.5 grid grid-cols-2 gap-1.5">
                {colSet.map((col) => {
                  const v = lookup.get(`${row}|${col}`) || 0;
                  return (
                    <div key={col} className="rounded-lg bg-[#F3F2F1] px-2 py-1.5">
                      <dt className="truncate text-[10px] font-medium uppercase tracking-wide text-[#605E5C]">
                        {biFieldLabel(col)}
                      </dt>
                      <dd className="text-sm font-semibold tabular-nums text-[#252423]">{formatPbiNumber(v, widget.format)}</dd>
                    </div>
                  );
                })}
                <div className="col-span-2 rounded-lg bg-violet-50 px-2 py-1.5">
                  <dt className="text-[10px] font-medium uppercase tracking-wide text-violet-700">Σ</dt>
                  <dd className="text-sm font-bold tabular-nums text-violet-900">{formatPbiNumber(rowTotal, widget.format)}</dd>
                </div>
              </dl>
            </div>
          );
        })}
        <div className="rounded-xl border border-violet-200 bg-violet-50/80 px-2.5 py-2 text-sm">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-violet-700">Σ</p>
          <p className="font-bold tabular-nums text-violet-950">{formatPbiNumber(grand, widget.format)}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bi-table-scroll h-full overflow-auto" style={maxHeight ? { maxHeight } : undefined}>
      <table className="bi-pbi-matrix w-full text-left text-xs">
        <thead className="sticky top-0 z-[1] bg-[#F3F2F1]">
          <tr>
            <th className="bi-pbi-matrix-corner px-3 py-2">{biFieldLabel(rowKey)}</th>
            {colSet.map((c) => (
              <th key={c} className="px-3 py-2 text-right font-semibold text-[#605E5C]">
                {biFieldLabel(c)}
              </th>
            ))}
            <th className="px-3 py-2 text-right font-semibold text-[#252423]">{t('bi.chart.total')}</th>
          </tr>
        </thead>
        <tbody>
          {rowSet.map((row) => {
            const rowTotal = colSet.reduce((s, col) => s + (lookup.get(`${row}|${col}`) || 0), 0);
            return (
              <tr key={row}>
                <td className="px-3 py-2 font-medium text-[#252423]">
                  <button type="button" className="hover:underline" onClick={() => onDatumClick?.(String(rowKey), row)}>
                    {row}
                  </button>
                </td>
                {colSet.map((col) => {
                  const v = lookup.get(`${row}|${col}`) || 0;
                  const intensity = grand > 0 ? Math.min(1, Math.abs(v) / (Math.max(...colTotals, 1) || 1)) : 0;
                  return (
                    <td
                      key={col}
                      className="px-3 py-2 text-right tabular-nums text-[#252423]"
                      style={{ background: `rgba(17, 141, 255, ${0.06 + intensity * 0.22})` }}
                    >
                      {formatPbiNumber(v, widget.format)}
                    </td>
                  );
                })}
                <td className="px-3 py-2 text-right font-semibold tabular-nums">{formatPbiNumber(rowTotal, widget.format)}</td>
              </tr>
            );
          })}
          <tr className="border-t border-[#E1DFDD] bg-[#FAFAFA]">
            <td className="px-3 py-2 font-semibold">Σ</td>
            {colTotals.map((tot, i) => (
              <td key={i} className="px-3 py-2 text-right font-semibold tabular-nums">
                {formatPbiNumber(tot, widget.format)}
              </td>
            ))}
            <td className="px-3 py-2 text-right font-semibold tabular-nums">{formatPbiNumber(grand, widget.format)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function BiTableWidget({
  widget,
  maxHeight,
  maxRows = 25,
}: {
  widget: BiWidget;
  maxHeight?: number;
  maxRows?: number;
}) {
  const c = cols(widget);
  const limit = Math.max(1, maxRows);
  const r = rows(widget).slice(0, limit);
  return (
    <div className="bi-table-scroll h-full overflow-auto" style={maxHeight ? { maxHeight } : undefined}>
      {r.length === 0 ? (
        <p className="p-4 text-center text-sm text-[#605E5C]">{t('bi.noData')}</p>
      ) : (
        <DynamicResultTable columns={c} rows={r} maxRows={limit} compact />
      )}
    </div>
  );
}

/** Route widget to the correct Power BI–style visual. */
export function BiVisualChart({ widget, targetValue, onDatumClick, variant, height, containerHeight }: ChartProps) {
  const narrow = useMediaQuery('(max-width: 639px)');
  const medium = useMediaQuery('(max-width: 1023px)');
  const resolvedHeight = resolveChartHeight(variant, narrow, medium, containerHeight ?? height);
  const chartProps = { widget, targetValue, onDatumClick, height: resolvedHeight, variant, containerHeight: containerHeight ?? height };
  const type = normalizeVisualType(widget.type);
  switch (type) {
    case 'card':
      return <BiCardWidget widget={widget} variant={variant} />;
    case 'kpi':
      return <BiCardWidget widget={widget} kpi variant={variant} />;
    case 'gauge':
      return <BiGaugeChartWidget {...chartProps} widget={widget} targetValue={targetValue} height={resolvedHeight} />;
    case 'multi_card':
      return <BiMultiCardWidget widget={widget} />;
    case 'period_compare':
      return <BiPeriodCompareWidget widget={widget} />;
    case 'scenario_compare':
      return <BiScenarioCompareWidget widget={widget} />;
    case 'bar':
    case 'column':
    case 'stacked_bar':
    case 'stacked_column':
      return <BiBarChartWidget {...chartProps} widget={{ ...widget, type }} />;
    case 'line':
      return <BiLineChartWidget {...chartProps} />;
    case 'area':
      return <BiAreaChartWidget {...chartProps} />;
    case 'combo':
      return <BiComboChartWidget {...chartProps} />;
    case 'pie':
      return <BiPieChartWidget {...chartProps} />;
    case 'donut':
      return <BiPieChartWidget {...chartProps} donut />;
    case 'scatter':
      return <BiScatterChartWidget {...chartProps} />;
    case 'bubble':
      return <BiScatterChartWidget {...chartProps} bubble />;
    case 'waterfall':
      return <BiWaterfallChartWidget {...chartProps} />;
    case 'funnel':
      return <BiFunnelChartWidget {...chartProps} />;
    case 'treemap':
      return <BiTreemapChartWidget {...chartProps} />;
    case 'matrix':
      return <BiMatrixWidget widget={widget} maxHeight={resolvedHeight} onDatumClick={onDatumClick} />;
    case 'table':
    default:
      return <BiTableWidget widget={widget} maxHeight={resolvedHeight} />;
  }
}
