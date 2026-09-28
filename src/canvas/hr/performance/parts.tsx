import { Pill, nf } from '../../admin/ui';
import { STATE_TONE, type Goal } from './perfApi';

/** Hedef satırı: başlık, durum, bağlı üst hedef (bağlanmamışsa işaretli), ağırlık ve son ilerleme çubuğu. */
export function GoalRow({ g, onOpen, showOwner }: { g: Goal; onOpen: () => void; showOwner?: boolean }) {
  const pctVal = g.lastCheckin?.progressPct ?? null;
  return (
    <button type="button" onClick={onOpen}
      className="flex w-full flex-col gap-1 rounded-xl border border-slate-100 bg-white/80 p-2.5 text-left transition-colors duration-150 hover:border-canvas-violet/40">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="min-w-0 flex-1 break-words text-[13px] font-extrabold">{g.title}</span>
        <Pill tone={STATE_TONE[g.state]}>{g.stateLabel}</Pill>
        {g.openRevision && <Pill tone="warn">revizyon bekliyor</Pill>}
        {!g.aligned && <Pill tone="err">üst hedefe bağlı değil</Pill>}
      </div>
      <div className="text-[11.5px] text-canvas-muted">
        {showOwner && (g.ownerName ?? g.unitName) ? `${g.ownerName ?? g.unitName} · ` : ''}{g.period}
        {g.parentTitle ? ` · ↳ ${g.parentTitle}` : ''}
        {g.weight !== null ? ` · ağırlık %${g.weight}` : ''}
        {g.targetValue !== null ? ` · hedef ${nf.format(g.targetValue)} ${g.unitLabel}` : ''}
      </div>
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuemin={0} aria-valuemax={100}
          aria-valuenow={pctVal ?? undefined} aria-label="Son check-in ilerlemesi">
          <div className="h-full rounded-full bg-canvas-violet" style={{ width: `${Math.min(100, Math.max(0, pctVal ?? 0))}%` }} />
        </div>
        <span className="w-12 text-right font-mono text-[11px] tabular-nums text-canvas-muted">{pctVal !== null ? `%${pctVal}` : '—'}</span>
      </div>
    </button>
  );
}
