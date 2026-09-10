import { ACCENT_HEX, type CanvasAccent } from '../types';

/** Küçük alan grafiği — tasarımdaki 210×50 kutucuk. */
export function Sparkline({
  values,
  accent = 'violet',
  height = 64,
}: {
  values: Array<number | null>;
  accent?: CanvasAccent;
  height?: number;
}) {
  const nums = values.filter((v): v is number => v != null);
  if (nums.length < 2) {
    return <div className="flex h-16 items-center text-[11px] text-canvas-muted">Grafik için yeterli nokta yok</div>;
  }
  const hex = ACCENT_HEX[accent];
  const max = Math.max(...nums) * 1.08;
  const min = Math.min(0, ...nums);
  const W = 210;
  const H = 50;
  const pts = values
    .map((v, i) => (v == null ? null : ([(i * W) / (values.length - 1), H - 4 - ((v - min) / (max - min || 1)) * (H - 12)] as const)))
    .filter((p): p is readonly [number, number] => p != null);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const last = pts[pts.length - 1];
  const gid = `cv-spark-${accent}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full overflow-visible" style={{ height }} preserveAspectRatio="none">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={hex} stopOpacity="0.35" />
          <stop offset="100%" stopColor={hex} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d} L ${last[0].toFixed(1)} ${H} L ${pts[0][0].toFixed(1)} ${H} Z`} fill={`url(#${gid})`} />
      <path d={d} fill="none" stroke={hex} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      <circle cx={last[0]} cy={last[1]} r={3.5} fill={hex} stroke="#fff" strokeWidth={2} />
    </svg>
  );
}

export type DonutSlice = { label: string; value: number; accent: CanvasAccent };

/** Halka + açıklama. Paylar değerlerden hesaplanır, elle yazılmaz. */
export function Donut({ slices, center }: { slices: DonutSlice[]; center: string }) {
  const total = slices.reduce((a, s) => a + Math.max(0, s.value), 0);
  const C = 87.96; // 2πr, r = 14
  let offset = 0;
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-16 w-16 shrink-0">
        <svg viewBox="0 0 36 36" className="h-full w-full -rotate-90">
          <circle cx="18" cy="18" r="14" fill="none" stroke="#F1F5F9" strokeWidth="4.5" />
          {slices.map((s) => {
            const len = total > 0 ? (C * Math.max(0, s.value)) / total : 0;
            const el = (
              <circle
                key={s.label}
                cx="18"
                cy="18"
                r="14"
                fill="none"
                stroke={ACCENT_HEX[s.accent]}
                strokeWidth="4.5"
                strokeDasharray={`${len.toFixed(2)} ${C}`}
                strokeDashoffset={`${(-offset).toFixed(2)}`}
              />
            );
            offset += len;
            return el;
          })}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center text-[10px] font-black text-canvas-ink">
          {center}
        </div>
      </div>
      <div className="flex-1 space-y-1 text-[11px]">
        {slices.map((s) => (
          <div key={s.label} className="flex items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5 truncate text-canvas-muted">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: ACCENT_HEX[s.accent] }} />
              {s.label}
            </span>
            <span className="shrink-0 font-bold text-canvas-ink">
              {total > 0 ? `%${((100 * s.value) / total).toFixed(1).replace('.', ',')}` : '—'}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Tükenme/ilerleme çubuğu; iki uçta küçük etiketler. */
export function ProgressBar({
  pct,
  left,
  right,
  gradient = 'from-canvas-violet to-canvas-coral',
}: {
  pct: number;
  left?: string;
  right?: string;
  gradient?: string;
}) {
  const w = Math.max(0, Math.min(100, pct));
  return (
    <div className="space-y-1">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full border border-slate-200/60 bg-slate-100 p-0.5">
        <div className={['h-full rounded-full bg-gradient-to-r', gradient].join(' ')} style={{ width: `${w}%` }} />
      </div>
      {(left || right) && (
        <div className="flex justify-between pt-0.5 text-[10px] font-medium text-canvas-muted">
          <span>{left}</span>
          <span>{right}</span>
        </div>
      )}
    </div>
  );
}
