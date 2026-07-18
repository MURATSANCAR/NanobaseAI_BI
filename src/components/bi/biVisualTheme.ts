/** Executive-grade Power BI–inspired visual theme (Fluent 2). */

export const PBI_COLORS = [
  '#118DFF',
  '#00C2A8',
  '#FF8A3D',
  '#7C4DFF',
  '#E044A7',
  '#FF5C8A',
  '#F4C430',
  '#2ECC71',
  '#3498DB',
  '#E74C3C',
  '#9B59B6',
  '#1ABC9C',
  '#F39C12',
  '#5DADE2',
  '#AF7AC5',
  '#58D68D',
] as const;

/** ~10% more saturated palette for preview / vivid mode. */
export const PBI_COLORS_VIVID = [
  '#0A7FE8',
  '#00B89A',
  '#FF7A1F',
  '#6B3DF5',
  '#D42E96',
  '#FF3D7A',
  '#E6B800',
  '#22C55E',
  '#2B8FE6',
  '#EF4444',
  '#8B4FC8',
  '#14B8A6',
  '#F59E0B',
  '#3B9FE8',
  '#A855F7',
  '#34D399',
] as const;

export const PBI_COLOR_SCHEME_ID = 'nanobase_pbi';

export const PBI_POSITIVE = '#107C10';
export const PBI_NEGATIVE = '#D13438';
export const PBI_TEXT = '#252423';
export const PBI_TEXT_MUTED = '#605E5C';
export const PBI_SURFACE = '#FFFFFF';
export const PBI_CANVAS = '#F5F5F5';
export const PBI_BORDER = '#E1DFDD';
export const PBI_RADIUS = 8;
export const PBI_BAR_RADIUS = 4;

export const PBI_TILE_SHADOW = {
  resting:
    '0 1px 0 rgba(255, 255, 255, 0.9) inset, 0 4px 20px rgba(15, 23, 42, 0.06), 0 0 0 1px rgba(148, 163, 184, 0.08)',
  hover:
    '0 1px 0 rgba(255, 255, 255, 0.95) inset, 0 12px 40px rgba(17, 141, 255, 0.14), 0 0 0 1px rgba(17, 141, 255, 0.18)',
} as const;

export const PBI_AXIS = {
  stroke: '#C8C6C4',
  fontSize: 11,
  fill: PBI_TEXT_MUTED,
  tickLine: false,
  axisLine: { stroke: '#EDEBE9' },
};
export const PBI_GRID = { stroke: '#F0EEEC', strokeDasharray: '4 4', vertical: false };
export const PBI_CHART_MARGIN = { top: 12, right: 16, left: 4, bottom: 4 };
export const PBI_ANIMATION = { duration: 800, easing: 'ease-out' as const };
export const PBI_CHART_ANIMATION = { duration: 900, easing: 'ease-out' as const };

export const PBI_TOOLTIP = {
  contentStyle: {
    background: 'transparent',
    border: 'none',
    boxShadow: 'none',
    padding: 0,
  },
  cursor: { fill: 'rgba(17, 141, 255, 0.06)', stroke: '#118DFF', strokeWidth: 1, strokeDasharray: '4 4' },
};

export function pbiGradientId(widgetId: string, index = 0) {
  return `pbi-grad-${widgetId.replace(/[^a-zA-Z0-9]/g, '')}-${index}`;
}

export function pbiPalette(vivid = false): readonly string[] {
  return vivid ? PBI_COLORS_VIVID : PBI_COLORS;
}

export function formatPbiNumber(value: unknown, format?: string): string {
  const n = Number(value);
  if (Number.isNaN(n)) return String(value ?? '—');
  if (format === 'percent') return `${(n * 100).toFixed(1)}%`;
  if (format === 'currency') {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(n);
  }
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 10_000) return `${(n / 1_000).toFixed(1)}K`;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(n);
}
