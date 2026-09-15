import { Suspense, lazy, useMemo, useState } from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
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

/** WebGL 3B grafikler (ECharts-GL) ayrı parçadır; yalnız 3B açıkken iner. */
const Chart3D = lazy(() => import('./Chart3D'));
const THREE_D: ChartKind[] = ['column', 'bar', 'pie', 'donut'];

/** Kolon adını okunur yapar: gecen_yila_net_ciro → Gecen yila net ciro */
export const humanize = (s: string) => {
  const t = s.replace(/^d(?=\d{4})/, '').replace(/_/g, ' ').trim();
  return t.charAt(0).toLocaleUpperCase('tr-TR') + t.slice(1);
};

/** Power BI'ın varsayılan teması. Seriler bu sırayla renklenir. */
export const SERIES = ['#118DFF', '#12239E', '#E66C37', '#6B007B', '#E044A7', '#744EC2', '#D9B300', '#D64550'];

const INK = '#252423';
const MUTED = '#605E5C';
const GRID = '#E1DFDD';
/** Kategori adı boş gelen satır: Power BI "(Boş)" yazar, boş hücre bırakmaz. */
export const BLANK = '(Boş)';

export type Row = Record<string, unknown>;
export type Col = { name: string; type: string };

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const nf = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });

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

const AY = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];

/** Eksen etiketi: ISO tarih "Oca 2026" olur (ayın 1'i ise ay, değilse gün ay yıl). */
export function prettyLabel(v: unknown): string {
  if (v == null || v === '') return BLANK;
  const s = String(v);
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ]00:00(?::00(?:\.0+)?)?Z?)?$/.exec(s);
  if (!m) return s;
  const [, y, mo, d] = m;
  const ay = AY[Number(mo) - 1] ?? mo;
  return d === '01' ? `${ay} ${y}` : `${Number(d)} ${ay} ${y}`;
}

/** Uzun kategori adı eksene sığmaz; kısaltılır, tam adı ipucunda kalır. */
export const clip = (s: string, n = 14): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** Değer etiketi ancak okunabilecek kadar az nokta varsa çizilir; üst üste binen sayı bilgi değildir. */
export const LABEL_MAX = 24;

const VALUE_LABEL = { fontSize: 11, fontWeight: 600, fill: INK } as const;

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

/** Sayı kolonunda küsurat varsa iki hane, yoksa tam sayı: bir kolonda karışık biçim olmaz. */
function formatterFor(rows: Row[], key: string): (v: number) => string {
  return rows.some((r) => isNum(r[key]) && !Number.isInteger(r[key])) ? (v) => nf2.format(v) : (v) => nf0.format(v);
}

type TipPayload = { name?: string; value?: unknown; color?: string; dataKey?: unknown; payload?: Row & { fill?: string } };

/** Power BI ipucu: başlıkta kategori, altında her seri adı ve tam sayı. */
function PbiTip({ active, payload, label }: { active?: boolean; payload?: TipPayload[]; label?: unknown }) {
  if (!active || !payload?.length) return null;
  const head = label ?? payload[0]?.payload?.__label;
  return (
    <div className="min-w-[160px] rounded-md border border-[#E1DFDD] bg-white px-3 py-2 text-[12px] shadow-[0_4px_16px_rgba(0,0,0,.12)]">
      {head != null && head !== '' && <div className="mb-1 font-semibold text-[#252423]">{String(head)}</div>}
      {payload.map((p, i) => (
        <div key={i} className="flex items-center justify-between gap-4 py-0.5">
          <span className="flex min-w-0 items-center gap-1.5 text-[#605E5C]">
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: p.color ?? p.payload?.fill }} />
            <span className="truncate">{humanize(String(p.name ?? p.dataKey ?? ''))}</span>
          </span>
          <span className="font-semibold tabular-nums text-[#252423]">
            {isNum(p.value) ? (Number.isInteger(p.value) ? nf0.format(p.value) : nf2.format(p.value)) : String(p.value ?? '')}
          </span>
        </div>
      ))}
    </div>
  );
}

const legendProps = {
  verticalAlign: 'top' as const,
  align: 'left' as const,
  iconType: 'circle' as const,
  iconSize: 8,
  wrapperStyle: { fontSize: 11, color: MUTED, paddingBottom: 8 },
  formatter: (v: string) => <span style={{ color: MUTED }}>{humanize(String(v))}</span>,
};

const RAD = Math.PI / 180;
/** Pasta dilimi etiketi: dışarıda, çizgiyle; %4'ten küçük dilimler yalnız ipucunda. */
function pieLabel(props: { cx: number; cy: number; midAngle: number; outerRadius: number; percent: number; value: number }) {
  const { cx, cy, midAngle, outerRadius, percent, value } = props;
  if (!Number.isFinite(percent) || percent < 0.04) return null;
  const r = outerRadius + 14;
  const x = cx + r * Math.cos(-midAngle * RAD);
  const y = cy + r * Math.sin(-midAngle * RAD);
  return (
    <text x={x} y={y} textAnchor={x > cx ? 'start' : 'end'} dominantBaseline="central" {...VALUE_LABEL}>
      {shortNum(value)} ({nf.format(percent * 100)}%)
    </text>
  );
}

/** Ağaç haritası hücresi: kutu sığdırıyorsa ad ve değer, sığdırmıyorsa yalnız renk. */
function TreeCell(props: { x?: number; y?: number; width?: number; height?: number; name?: string; value?: number; index?: number }) {
  const { x = 0, y = 0, width = 0, height = 0, name = '', value, index = 0 } = props;
  const fits = width > 56 && height > 30;
  const chars = Math.max(3, Math.floor(width / 6.5));
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={SERIES[index % SERIES.length]} stroke="#fff" strokeWidth={2} />
      {fits && (
        <>
          <text x={x + 6} y={y + 16} fontSize={11} fontWeight={600} fill="#fff">
            {clip(String(name), chars)}
          </text>
          {isNum(value) && (
            <text x={x + 6} y={y + 30} fontSize={11} fill="rgba(255,255,255,.9)">
              {shortNum(value)}
            </text>
          )}
        </>
      )}
    </g>
  );
}

/** Power BI tablo görseli: okunur başlık, sağa yaslı sayılar, veri çubuğu ve alt toplam. */
function PbiTable({ cols, rows, nums }: { cols: Col[]; rows: Row[]; nums: string[] }) {
  const numSet = new Set(nums);
  const label = cols.find((c) => !numSet.has(c.name))?.name;
  const stats = useMemo(() => {
    const out: Record<string, { max: number; sum: number; fmt: (v: number) => string; bars: boolean }> = {};
    for (const n of nums) {
      let max = 0;
      let sum = 0;
      let neg = false;
      for (const r of rows) {
        const v = r[n];
        if (!isNum(v)) continue;
        sum += v;
        if (v < 0) neg = true;
        max = Math.max(max, Math.abs(v));
      }
      // Veri çubuğu yalnız toplanabilir, eksiz sayı kolonunda: "yıl" ya da "kod" gibi kolonlarda anlamsız.
      out[n] = { max, sum, fmt: formatterFor(rows, n), bars: !neg && rows.length > 1 && !/(^|_)(yil|yıl|ay|kod|id|no)$/i.test(n) };
    }
    return out;
  }, [rows, nums]);
  const showTotal = rows.length > 1 && nums.length > 0;

  return (
    <div data-nodrag className="pano-table h-full overflow-auto rounded-md">
      <table className="w-full border-collapse text-[12px] text-[#252423]">
        <thead className="sticky top-0 z-[1] bg-white">
          <tr>
            {cols.map((c) => (
              <th
                key={c.name}
                scope="col"
                className={[
                  'whitespace-nowrap border-b-2 border-[#252423]/80 px-2.5 py-2 font-semibold',
                  numSet.has(c.name) ? 'w-px text-right' : 'text-left',
                ].join(' ')}
              >
                {humanize(c.name)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-[#EDEBE9] transition-colors duration-100 hover:bg-[#F3F2F1]">
              {cols.map((c) => {
                const v = r[c.name];
                if (numSet.has(c.name)) {
                  const s = stats[c.name];
                  const pct = s?.bars && isNum(v) && s.max > 0 ? (v / s.max) * 100 : 0;
                  return (
                    <td
                      key={c.name}
                      className="whitespace-nowrap px-2.5 py-1.5 text-right tabular-nums"
                      style={pct ? { backgroundImage: `linear-gradient(to right, rgba(17,141,255,.14) ${pct}%, transparent ${pct}%)` } : undefined}
                    >
                      {isNum(v) ? s.fmt(v) : ''}
                    </td>
                  );
                }
                const blank = v == null || v === '';
                return (
                  <td key={c.name} className={['px-2.5 py-1.5', blank && c.name === label ? 'italic text-[#605E5C]' : ''].join(' ')}>
                    {blank ? (c.name === label ? BLANK : '') : prettyLabel(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
        {showTotal && (
          <tfoot className="sticky bottom-0 bg-white">
            <tr>
              {cols.map((c, j) => (
                <td
                  key={c.name}
                  className={[
                    'whitespace-nowrap border-t-2 border-[#252423]/80 px-2.5 py-2 font-semibold',
                    numSet.has(c.name) ? 'text-right tabular-nums' : '',
                  ].join(' ')}
                >
                  {numSet.has(c.name) && stats[c.name]?.bars ? stats[c.name].fmt(stats[c.name].sum) : j === 0 ? 'Toplam' : ''}
                </td>
              ))}
            </tr>
          </tfoot>
        )}
      </table>
    </div>
  );
}

/**
 * Pano kartının grafiği, Power BI görsel diliyle: tema paleti, ince kesik ızgara, eksen başlığı,
 * değer etiketi, üzerine gelinen kategori dışındakilerin sönmesi. `still` yazdırmada animasyonu kapatır.
 */
export default function Chart({
  kind,
  cols,
  rows,
  depth,
  still = false,
}: {
  kind: ChartKind;
  cols: Col[];
  rows: Row[];
  depth: boolean;
  still?: boolean;
}) {
  const nums = useMemo(() => numericCols(cols, rows), [cols, rows]);
  const label = useMemo(() => labelCol(cols, rows), [cols, rows]);
  const [hover, setHover] = useState<number | null>(null);

  if (!rows.length) {
    return <div className="flex h-full items-center justify-center text-[12px] text-canvas-muted">Sonuç boş</div>;
  }

  if (depth && THREE_D.includes(kind)) {
    return (
      <Suspense
        fallback={<div className="flex h-full items-center justify-center text-[11px] font-semibold text-canvas-muted">3B yükleniyor…</div>}
      >
        <Chart3D kind={kind} cols={cols} rows={rows} />
      </Suspense>
    );
  }

  if (kind === 'kpi') {
    const key = nums[0] ?? cols[0]?.name;
    const v = rows[0]?.[key];
    // İkinci sayı kolonu bir karşılaştırmadır ("geçen yıla göre"): fark rozeti çıkar.
    const prevKey = rows.length === 1 ? nums[1] : undefined;
    const prev = prevKey ? rows[0]?.[prevKey] : undefined;
    const delta = isNum(v) && isNum(prev) && prev !== 0 ? ((v - prev) / Math.abs(prev)) * 100 : null;
    return (
      <div className="flex h-full flex-col items-center justify-center">
        <div className="text-[40px] font-semibold leading-none tabular-nums tracking-tight text-[#252423]" title={isNum(v) ? nf2.format(v) : undefined}>
          {isNum(v) ? shortNum(v) : String(v ?? '—')}
        </div>
        <div className="mt-2 text-[12px] text-[#605E5C]">{humanize(String(key))}</div>
        {delta != null && (
          <div className="mt-2.5 flex items-center gap-1.5">
            <span
              className={[
                'rounded px-1.5 py-0.5 text-[12px] font-semibold tabular-nums',
                delta >= 0 ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700',
              ].join(' ')}
              title={`Önceki: ${nf.format(prev as number)}`}
            >
              {delta >= 0 ? '▲' : '▼'} %{nf.format(Math.abs(delta))}
            </span>
            <span className="text-[11px] text-[#605E5C]">
              {humanize(String(prevKey))}: {shortNum(prev as number)}
            </span>
          </div>
        )}
      </div>
    );
  }

  if (kind === 'table') return <PbiTable cols={cols} rows={rows} nums={nums} />;

  const anim = still ? false : undefined;
  const data = rows.map((r) => ({ ...r, __label: prettyLabel(r[label]) }));
  const series = nums.filter((n) => n !== label);
  const axis = { tick: { fontSize: 11, fill: MUTED }, tickLine: false, axisLine: false } as const;
  const axisTitle = (v: string, vertical = false) =>
    ({
      value: v,
      position: vertical ? 'insideLeft' : 'insideBottom',
      angle: vertical ? -90 : 0,
      offset: vertical ? 12 : 0,
      style: { fontSize: 11, fill: MUTED, textAnchor: 'middle' },
    }) as const;
  const showValues = rows.length * Math.max(1, series.length) <= LABEL_MAX;
  const crowded = rows.length > 8;
  const xTick = {
    ...axis,
    interval: (rows.length > LABEL_MAX ? 'preserveStartEnd' : 0) as 0 | 'preserveStartEnd',
    tickFormatter: (v: unknown) => clip(String(v), crowded ? 10 : 16),
  };
  // Recharts etiketi çubuk genişliğine sarar; "131,3 Mn" iki satıra bölünmesin diye boşluk kırılmaz.
  const fmt = (v: unknown) => (isNum(v) ? shortNum(v) : String(v ?? '')).replace(/ /g, ' ');
  const dim = (i: number) => (hover == null || hover === i ? 1 : 0.35);
  const single = series.length === 1;
  const valueTitle = single ? humanize(series[0]) : '';
  const labelTitle = humanize(label);
  const onMove = (s: { activeTooltipIndex?: number } | null) =>
    setHover(s && typeof s.activeTooltipIndex === 'number' ? s.activeTooltipIndex : null);

  if (kind === 'pie' || kind === 'donut') {
    const key = series[0] ?? nums[0];
    return (
      <div className="h-full" style={{ perspective: depth ? 900 : undefined }}>
        <div className="h-full" style={{ transform: depth ? 'rotateX(38deg)' : undefined }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                isAnimationActive={anim}
                animationDuration={500}
                data={data}
                dataKey={key}
                nameKey="__label"
                innerRadius={kind === 'donut' ? '55%' : 0}
                outerRadius="72%"
                cx="42%"
                paddingAngle={0}
                stroke="#fff"
                strokeWidth={1.5}
                label={pieLabel}
                labelLine={{ stroke: GRID, strokeWidth: 1 }}
                onMouseEnter={(_, i) => setHover(i)}
                onMouseLeave={() => setHover(null)}
              >
                {data.map((_, i) => (
                  <Cell key={i} fill={SERIES[i % SERIES.length]} fillOpacity={dim(i)} />
                ))}
              </Pie>
              <Tooltip content={<PbiTip />} />
              <Legend
                layout="vertical"
                verticalAlign="middle"
                align="right"
                iconType="circle"
                iconSize={8}
                wrapperStyle={{ fontSize: 11, lineHeight: '18px', maxWidth: '38%' }}
                formatter={(v: string) => <span style={{ color: MUTED }}>{clip(String(v), 22)}</span>}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  if (kind === 'treemap') {
    const key = series[0] ?? nums[0];
    return (
      <ResponsiveContainer width="100%" height="100%">
        <Treemap isAnimationActive={anim} data={data} dataKey={key} nameKey="__label" stroke="#fff" fill={SERIES[0]} content={<TreeCell />}>
          <Tooltip content={<PbiTip />} />
        </Treemap>
      </ResponsiveContainer>
    );
  }

  if (kind === 'scatter') {
    return (
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 16, bottom: 18, left: 8 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" />
          <XAxis dataKey={nums[0]} type="number" {...axis} tickFormatter={shortNum} label={axisTitle(humanize(nums[0]))} />
          <YAxis dataKey={nums[1]} type="number" {...axis} tickFormatter={shortNum} width={60} label={axisTitle(humanize(nums[1]), true)} />
          <Tooltip content={<PbiTip />} cursor={{ strokeDasharray: '3 3', stroke: GRID }} />
          <Scatter isAnimationActive={anim} data={data} fill={SERIES[0]} fillOpacity={0.85} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  if (kind === 'line' || kind === 'area') {
    const Wrapper = kind === 'line' ? LineChart : AreaChart;
    return (
      <ResponsiveContainer width="100%" height="100%">
        <Wrapper data={data} margin={{ top: showValues ? 20 : 8, right: 20, bottom: crowded ? 20 : 18, left: 8 }}>
          <defs>
            {series.map((n, i) => (
              <linearGradient key={n} id={`pbi-g-${i}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SERIES[i % SERIES.length]} stopOpacity={0.28} />
                <stop offset="100%" stopColor={SERIES[i % SERIES.length]} stopOpacity={0.02} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="__label"
            {...xTick}
            angle={crowded ? -35 : 0}
            textAnchor={crowded ? 'end' : 'middle'}
            height={crowded ? 62 : 36}
            padding={{ left: 12, right: 12 }}
            label={axisTitle(labelTitle)}
          />
          <YAxis {...axis} tickFormatter={shortNum} width={64} label={valueTitle ? axisTitle(valueTitle, true) : undefined} />
          <Tooltip content={<PbiTip />} cursor={{ stroke: MUTED, strokeDasharray: '3 3' }} />
          {!single && <Legend {...legendProps} />}
          {series.map((n, i) =>
            kind === 'line' ? (
              <Line
                key={n}
                isAnimationActive={anim}
                animationDuration={500}
                type="linear"
                dataKey={n}
                stroke={SERIES[i % SERIES.length]}
                strokeWidth={2.5}
                dot={showValues ? { r: 3.5, strokeWidth: 0, fill: SERIES[i % SERIES.length] } : false}
                activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
              >
                {showValues && <LabelList dataKey={n} position="top" offset={10} formatter={fmt} style={VALUE_LABEL} />}
              </Line>
            ) : (
              <Area
                key={n}
                isAnimationActive={anim}
                animationDuration={500}
                type="linear"
                dataKey={n}
                stroke={SERIES[i % SERIES.length]}
                strokeWidth={2.5}
                fill={`url(#pbi-g-${i})`}
                dot={showValues ? { r: 3.5, strokeWidth: 0, fill: SERIES[i % SERIES.length] } : false}
                activeDot={{ r: 5, strokeWidth: 2, stroke: '#fff' }}
              >
                {showValues && <LabelList dataKey={n} position="top" offset={10} formatter={fmt} style={VALUE_LABEL} />}
              </Area>
            ),
          )}
        </Wrapper>
      </ResponsiveContainer>
    );
  }

  const horizontal = kind === 'bar';
  // Yatay çubukta kategori ekseni en uzun ada göre genişler; sabit genişlik adı gereksiz keser.
  const catWidth = Math.min(180, Math.max(64, Math.max(...data.map((d) => Math.min(24, String(d.__label).length))) * 6.6 + 12));
  return (
    <div className="h-full" style={{ perspective: depth ? 1100 : undefined }}>
      <div className="h-full" style={{ transform: depth ? 'rotateX(16deg) rotateY(-8deg)' : undefined }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            layout={horizontal ? 'vertical' : 'horizontal'}
            barCategoryGap="22%"
            barGap={2}
            onMouseMove={onMove}
            onMouseLeave={() => setHover(null)}
            margin={{
              top: showValues && !horizontal ? 20 : 8,
              right: showValues && horizontal ? 56 : 16,
              bottom: horizontal ? 18 : crowded ? 20 : 18,
              left: 8,
            }}
          >
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={horizontal} horizontal={!horizontal} />
            {horizontal ? (
              <>
                <XAxis type="number" {...axis} tickFormatter={shortNum} label={valueTitle ? axisTitle(valueTitle) : undefined} />
                <YAxis
                  type="category"
                  dataKey="__label"
                  {...xTick}
                  tick={{ fontSize: 11, fill: INK }}
                  tickFormatter={(v: unknown) => clip(String(v), 24)}
                  width={catWidth}
                />
              </>
            ) : (
              <>
                <XAxis
                  dataKey="__label"
                  {...xTick}
                  tick={{ fontSize: 11, fill: INK }}
                  angle={crowded ? -35 : 0}
                  textAnchor={crowded ? 'end' : 'middle'}
                  height={crowded ? 62 : 36}
                  label={axisTitle(labelTitle)}
                />
                <YAxis {...axis} tickFormatter={shortNum} width={64} label={valueTitle ? axisTitle(valueTitle, true) : undefined} />
              </>
            )}
            <Tooltip content={<PbiTip />} cursor={{ fill: 'rgba(0,0,0,.04)' }} />
            {!single && <Legend {...legendProps} />}
            {series.map((n, i) => (
              <Bar
                key={n}
                isAnimationActive={anim}
                animationDuration={500}
                dataKey={n}
                fill={SERIES[i % SERIES.length]}
                maxBarSize={56}
                radius={horizontal ? [0, 2, 2, 0] : [2, 2, 0, 0]}
              >
                {data.map((_, k) => (
                  <Cell key={k} fillOpacity={dim(k)} style={{ transition: 'fill-opacity 120ms ease' }} />
                ))}
                {showValues && <LabelList dataKey={n} position={horizontal ? 'right' : 'top'} offset={6} formatter={fmt} style={VALUE_LABEL} />}
              </Bar>
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
