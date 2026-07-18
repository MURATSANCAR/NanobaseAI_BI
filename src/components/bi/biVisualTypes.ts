import type { BiWidget } from '@/api/types';

/** Power BI–aligned visual types supported for dynamic NanobaseAI + SQL widgets. */
export const BI_VISUAL_TYPES = [
  'card',
  'metric',
  'kpi',
  'gauge',
  'multi_card',
  'period_compare',
  'scenario_compare',
  'bar',
  'column',
  'stacked_bar',
  'stacked_column',
  'line',
  'area',
  'combo',
  'pie',
  'donut',
  'table',
  'matrix',
  'scatter',
  'bubble',
  'waterfall',
  'funnel',
  'treemap',
] as const;

export type BiVisualType = (typeof BI_VISUAL_TYPES)[number];

/** Viz types the pin-to-dashboard flow can reliably create on Analytics. */
export const BI_PIN_VIZ_OPTIONS = [
  'table',
  'bar',
  'column',
  'line',
  'area',
  'pie',
  'donut',
  'kpi',
  'card',
] as const;

export type BiPinVizType = (typeof BI_PIN_VIZ_OPTIONS)[number];

export function isPinVizType(type?: string): type is BiPinVizType {
  return Boolean(type && (BI_PIN_VIZ_OPTIONS as readonly string[]).includes(type));
}

const ALIASES: Record<string, BiVisualType> = {
  metric: 'card',
  card: 'card',
  kpi: 'kpi',
  gauge: 'gauge',
  multi_card: 'multi_card',
  period_compare: 'period_compare',
  scenario_compare: 'scenario_compare',
  pop: 'period_compare',
  compare: 'period_compare',
  scenario: 'scenario_compare',
  bar: 'bar',
  column: 'column',
  stacked_bar: 'stacked_bar',
  stacked_column: 'stacked_column',
  line: 'line',
  area: 'area',
  combo: 'combo',
  pie: 'pie',
  donut: 'donut',
  table: 'table',
  matrix: 'matrix',
  scatter: 'scatter',
  bubble: 'bubble',
  waterfall: 'waterfall',
  funnel: 'funnel',
  treemap: 'treemap',
  ribbon: 'stacked_column',
};

export function normalizeVisualType(type?: string): BiVisualType {
  const key = (type || 'table').toLowerCase().trim();
  return ALIASES[key] ?? 'table';
}

export function widgetVisualType(widget: BiWidget): BiVisualType {
  return normalizeVisualType(widget.type);
}

export function defaultGridSize(type: BiVisualType): { w: number; h: number; minW: number; minH: number } {
  switch (type) {
    case 'card':
    case 'kpi':
      return { w: 3, h: 3, minW: 2, minH: 3 };
    case 'gauge':
      return { w: 3, h: 4, minW: 3, minH: 4 };
    case 'multi_card':
    case 'period_compare':
    case 'scenario_compare':
      return { w: 6, h: 3, minW: 4, minH: 3 };
    case 'table':
    case 'matrix':
      return { w: 12, h: 6, minW: 6, minH: 4 };
    case 'treemap':
    case 'funnel':
    case 'waterfall':
      return { w: 6, h: 5, minW: 4, minH: 4 };
    case 'pie':
    case 'donut':
      return { w: 4, h: 5, minW: 3, minH: 4 };
    case 'line':
    case 'area':
    case 'combo':
      return { w: 6, h: 5, minW: 4, minH: 4 };
    default:
      return { w: 6, h: 5, minW: 4, minH: 4 };
  }
}

/** Prefer the longest localized title — used to widen/taller tiles for long TR/RU labels. */
export function widgetTitleLength(widget: BiWidget): number {
  const titles = widget.titles;
  const candidates = [
    titles?.tr,
    titles?.en,
    titles?.ru,
    titles?.uz,
    widget.title,
  ].filter((s): s is string => typeof s === 'string' && s.trim().length > 0);
  if (!candidates.length) return 0;
  return Math.max(...candidates.map((s) => s.trim().length));
}

/** Grid size for a widget, widened/taller when the title is long. */
export function defaultGridSizeForWidget(widget: BiWidget): {
  w: number;
  h: number;
  minW: number;
  minH: number;
} {
  const type = widgetVisualType(widget);
  const base = defaultGridSize(type);
  const len = widgetTitleLength(widget);
  let { w, h, minW, minH } = base;

  if (isCompactVisual(type)) {
    if (len > 48) {
      w = 6;
      h = Math.max(h, 3);
      minW = 4;
    } else if (len > 32) {
      w = Math.max(w, 4);
      minW = 3;
    }
  } else if (type === 'table' || type === 'matrix') {
    if (len > 40) h = Math.max(h, 6);
  } else if (len > 52) {
    w = Math.max(w, 6);
    h = Math.max(h, 5);
    minW = Math.max(minW, 4);
  } else if (len > 36) {
    w = Math.max(w, 6);
  }

  return { w: Math.min(12, w), h, minW, minH };
}

export function isHorizontalBar(type: BiVisualType): boolean {
  return type === 'bar' || type === 'stacked_bar';
}

export function isStacked(type: BiVisualType): boolean {
  return type === 'stacked_bar' || type === 'stacked_column';
}

/** KPI-style visuals use integrated chrome (title inside the tile body). */
export function isCompactVisual(type: BiVisualType): boolean {
  return type === 'card' || type === 'kpi' || type === 'gauge' || type === 'multi_card' || type === 'metric';
}
