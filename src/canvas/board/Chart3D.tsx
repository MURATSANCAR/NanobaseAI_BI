/**
 * Gerçek 3B grafikler: Apache ECharts + ECharts-GL (WebGL). Sütun/çubuk için
 * ışıklı, gölgeli `bar3D`; pasta/halka için dilim başına parametrik yüzey.
 * Fare ile döndürülür, tekerlekle yaklaşılır. Ayrı parça olarak yüklenir;
 * 3B kapalıyken bu dosya hiç inmez.
 */
import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { Grid3DComponent } from 'echarts-gl/components';
import { Bar3DChart, SurfaceChart } from 'echarts-gl/charts';
import type { ChartKind } from './store';
import { SERIES, labelCol, numericCols, prettyLabel, shortNum, type Col, type Row } from './Chart';

// Yalnız kullanılan parçalar paketlenir; tam ECharts + GL 1,7 MB'tı.
echarts.use([TooltipComponent, CanvasRenderer, Grid3DComponent, Bar3DChart, SurfaceChart]);

const nf = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);

/** Dilimin yüzeyi: u açı (yan duvarlar için -π…3π), v kalınlık/iç yarıçap. */
function slice(start: number, end: number, k: number, h: number) {
  const a0 = start * Math.PI * 2;
  const a1 = end * Math.PI * 2;
  const clampU = (u: number) => (u < a0 ? a0 : u > a1 ? a1 : u);
  return {
    u: { min: -Math.PI, max: Math.PI * 3, step: Math.PI / 32 },
    v: { min: 0, max: Math.PI * 2, step: Math.PI / 20 },
    x: (u: number, v: number) => Math.cos(clampU(u)) * (1 + Math.cos(v) * k),
    y: (u: number, v: number) => Math.sin(clampU(u)) * (1 + Math.cos(v) * k),
    z: (u: number, v: number) => {
      if (u < -Math.PI * 0.5) return Math.sin(u);
      if (u > Math.PI * 2.5) return Math.sin(u) * h * 0.1;
      return Math.sin(v) > 0 ? h * 0.1 : -1;
    },
  };
}

function pieOption(kind: ChartKind, labels: string[], values: number[]): echarts.EChartsCoreOption {
  const total = values.reduce((a, b) => a + b, 0) || 1;
  const k = kind === 'donut' ? 1 / 3 : 1;
  let acc = 0;
  const series = values.map((v, i) => {
    const start = acc / total;
    acc += v;
    const end = acc / total;
    return {
      name: labels[i],
      type: 'surface',
      parametric: true,
      wireframe: { show: false },
      shading: 'realistic',
      realisticMaterial: { roughness: 0.55, metalness: 0.05 },
      itemStyle: { color: SERIES[i % SERIES.length], opacity: 1 },
      parametricEquation: slice(start, end, k, 14),
      pieValue: v,
      pieShare: v / total,
    };
  });
  return {
    tooltip: {
      formatter: (p: { seriesName: string; seriesIndex: number }) => {
        const s = series[p.seriesIndex];
        return `<b>${p.seriesName}</b><br/>${nf.format(s.pieValue)} · %${nf.format(s.pieShare * 100)}`;
      },
    },
    xAxis3D: { min: -1.6, max: 1.6 },
    yAxis3D: { min: -1.6, max: 1.6 },
    zAxis3D: { min: -1, max: 1.8 },
    grid3D: {
      show: false,
      boxHeight: 32,
      top: 'middle',
      viewControl: { alpha: 30, beta: 30, distance: 105, minDistance: 50, maxDistance: 300, autoRotate: false, damping: 0.85, zoomSensitivity: 0.6 },
      light: { main: { intensity: 1.6, shadow: true, alpha: 60, beta: 40 }, ambient: { intensity: 0.5 } },
      postEffect: { enable: true, SSAO: { enable: true, radius: 2, intensity: 0.9 } },
      temporalSuperSampling: { enable: true },
    },
    series,
  };
}

function barOption(labels: string[], seriesNames: string[], rows: Row[], horizontal: boolean): echarts.EChartsCoreOption {
  const single = seriesNames.length === 1;
  const data: Array<[number, number, number]> = [];
  rows.forEach((r, xi) => seriesNames.forEach((n, yi) => data.push([xi, yi, isNum(r[n]) ? (r[n] as number) : 0])));
  const cat = {
    type: 'category',
    axisLabel: { fontSize: 11, color: '#475569', margin: 8 },
    axisLine: { lineStyle: { color: '#cbd5e1', width: 1 } },
    axisTick: { show: false },
    splitLine: { show: false },
  };
  return {
    tooltip: {
      formatter: (p: { value: [number, number, number] }) =>
        `<b>${labels[p.value[0]]}</b>${single ? '' : ` · ${seriesNames[p.value[1]]}`}<br/>${nf.format(p.value[2])}`,
    },
    xAxis3D: { ...cat, data: labels, name: '' },
    yAxis3D: { ...cat, data: seriesNames, name: '', axisLabel: { ...cat.axisLabel, show: !single } },
    zAxis3D: {
      type: 'value',
      name: '',
      splitNumber: 4,
      axisLabel: { fontSize: 10, color: '#94a3b8', formatter: (v: number) => shortNum(v) },
      axisLine: { lineStyle: { color: '#cbd5e1' } },
      splitLine: { lineStyle: { color: 'rgba(30,41,59,.12)' } },
    },
    grid3D: {
      boxWidth: Math.max(140, Math.min(300, labels.length * 30)),
      boxDepth: single ? 30 : Math.max(44, seriesNames.length * 28),
      boxHeight: 80,
      top: 'middle',
      axisPointer: { show: false },
      viewControl: {
        alpha: horizontal ? 10 : 18,
        beta: horizontal ? 75 : 12,
        distance: 135,
        minDistance: 60,
        maxDistance: 400,
        autoRotate: false,
        damping: 0.85,
        zoomSensitivity: 0.6,
      },
      light: { main: { intensity: 1.4, shadow: true, shadowQuality: 'high', alpha: 40, beta: -30 }, ambient: { intensity: 0.4 } },
      postEffect: { enable: true, SSAO: { enable: true, radius: 3, intensity: 0.8 }, FXAA: { enable: true } },
      temporalSuperSampling: { enable: true },
    },
    series: [
      {
        type: 'bar3D',
        data,
        barSize: single ? 16 : 10,
        bevelSize: 0.25,
        bevelSmoothness: 4,
        shading: 'realistic',
        realisticMaterial: { roughness: 0.4, metalness: 0.08 },
        itemStyle: {
          color: (p: { value: [number, number, number] }) => SERIES[(single ? p.value[0] : p.value[1]) % SERIES.length],
        },
        emphasis: { itemStyle: { color: '#1B1F2A' }, label: { show: true, fontSize: 11, formatter: (p: { value: [number, number, number] }) => nf.format(p.value[2]) } },
      },
    ],
  };
}

export default function Chart3D({ kind, cols, rows }: { kind: ChartKind; cols: Col[]; rows: Row[] }) {
  const host = useRef<HTMLDivElement | null>(null);
  const nums = useMemo(() => numericCols(cols, rows), [cols, rows]);
  const label = useMemo(() => labelCol(cols, rows), [cols, rows]);
  const labels = useMemo(() => rows.map((r) => prettyLabel(r[label])), [rows, label]);

  const option = useMemo(() => {
    if (kind === 'pie' || kind === 'donut') {
      const key = nums[0];
      const vals = rows.map((r) => (isNum(r[key]) && (r[key] as number) > 0 ? (r[key] as number) : 0));
      return pieOption(kind, labels, vals);
    }
    return barOption(labels, nums, rows, kind === 'bar');
  }, [kind, nums, rows, labels]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: 'canvas' });
    chart.setOption(option);
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.dispose();
    };
  }, [option]);

  const legend = kind === 'pie' || kind === 'donut' ? labels : nums.length > 1 ? nums : [];
  return (
    <div className="flex h-full flex-col">
      <div ref={host} data-nodrag className="min-h-0 flex-1" style={{ touchAction: 'none' }} />
      {legend.length > 0 && (
        <div className="flex flex-wrap justify-center gap-x-3 gap-y-0.5 pt-1 text-[11px] font-semibold text-canvas-muted">
          {legend.map((l, i) => (
            <span key={l} className="flex items-center gap-1">
              <span className="inline-block h-2 w-2 rounded-sm" style={{ background: SERIES[i % SERIES.length] }} />
              {l}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
