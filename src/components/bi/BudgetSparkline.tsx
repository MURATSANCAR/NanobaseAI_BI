/** Tiny SVG sparkline for budget actuals history (oldest → newest). */

export function BudgetSparkline({
  values,
  className,
}: {
  values: Array<number | null | undefined>;
  className?: string;
}) {
  const nums = values.map((v) => (v == null || Number.isNaN(Number(v)) ? null : Number(v)));
  const known = nums.filter((v): v is number => v != null);
  if (known.length < 2) {
    return <span className={className || 'text-[11px] text-slate-400'}>—</span>;
  }
  const min = Math.min(...known);
  const max = Math.max(...known);
  const span = max - min || 1;
  const w = 72;
  const h = 22;
  const pts = nums
    .map((v, i) => {
      if (v == null) return null;
      const x = (i / Math.max(1, nums.length - 1)) * w;
      const y = h - 2 - ((v - min) / span) * (h - 4);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(' ');
  return (
    <svg
      className={className}
      width={w}
      height={h}
      viewBox={`0 0 ${w} ${h}`}
      aria-hidden
    >
      <polyline fill="none" stroke="currentColor" strokeWidth="1.5" points={pts} className="text-violet-600" />
    </svg>
  );
}
