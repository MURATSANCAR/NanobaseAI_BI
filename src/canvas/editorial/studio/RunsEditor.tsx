import { useRef, useState, type MouseEvent } from 'react';
import { Bold, Eraser } from 'lucide-react';
import type { PlanPalette, PlanRun } from '../../engine';
import { editRuns, runsText, styleRange } from './planModel';

/** Renkli yazı düzenleyici. Metin düz bir alanda yazılır (telefonda da çalışsın, ekran okuyucu okusun);
 *  renk ve kalınlık seçili aralığa verilir ve o aralık `source:"editor"` olur — otomatik renk kuralları
 *  editörün verdiğine dokunmaz. Altındaki satır, sonucu renkleriyle gösterir. Renk düğmesine basınca
 *  metin alanının seçimi kaybolmasın diye düğmeler odak almaz. */

export function paletteChips(p: PlanPalette): { name: string; hex: string }[] {
  const out = new Map<string, string>();
  out.set(p.text.toUpperCase(), 'Metin rengi');
  for (const c of p.colors) if (!out.has(c.hex.toUpperCase())) out.set(c.hex.toUpperCase(), c.name);
  for (const [n, h] of Object.entries(p.characters)) if (!out.has(h.toUpperCase())) out.set(h.toUpperCase(), n);
  return [...out].map(([hex, name]) => ({ hex, name }));
}

export function RunsView({ runs, fallback }: { runs: PlanRun[]; fallback: string }) {
  return (
    <>
      {runs.map((r, i) => (
        <span key={i} style={{ color: r.color || fallback, fontWeight: r.weight ?? undefined }}>{r.text}</span>
      ))}
    </>
  );
}

export default function RunsEditor({ runs, onChange, palette, label, rows = 3, onCursor }: {
  runs: PlanRun[];
  onChange: (runs: PlanRun[], undoKey: string) => void;
  palette: PlanPalette;
  label: string;
  rows?: number;
  onCursor?: (pos: number) => void;
}) {
  const ta = useRef<HTMLTextAreaElement | null>(null);
  const [selLen, setSelLen] = useState(0);
  const text = runsText(runs);
  const chips = paletteChips(palette);

  const range = () => {
    const el = ta.current;
    if (!el) return null;
    const a = Math.min(el.selectionStart, el.selectionEnd);
    const b = Math.max(el.selectionStart, el.selectionEnd);
    return b > a ? [a, b] as const : null;
  };
  const apply = (patch: Partial<PlanRun>) => {
    const r = range();
    if (!r) return;
    onChange(styleRange(runs, r[0], r[1], patch), '');
  };
  const trackSel = () => {
    const el = ta.current;
    if (!el) return;
    setSelLen(Math.abs(el.selectionEnd - el.selectionStart));
    onCursor?.(el.selectionStart);
  };
  const keep = (e: MouseEvent) => e.preventDefault(); // seçim metin alanında kalsın

  return (
    <div className="flex flex-col gap-1.5">
      <label className="flex flex-col gap-1">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</span>
        <textarea
          ref={ta}
          value={text}
          rows={rows}
          onChange={(e) => onChange(editRuns(runs, e.target.value), `type:${label}`)}
          onSelect={trackSel}
          onKeyUp={trackSel}
          onMouseUp={trackSel}
          className="w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-base leading-snug outline-none focus:border-canvas-violet sm:text-[13px]"
        />
      </label>
      <div className="flex flex-wrap items-center gap-1" role="toolbar" aria-label="Seçili yazının rengi">
        {chips.map((c) => (
          <button key={c.hex} type="button" onMouseDown={keep} onClick={() => apply({ color: c.hex })} disabled={!selLen}
            title={`${c.name} (${c.hex})`} aria-label={`Seçili yazıyı ${c.name} yap`}
            className="h-7 w-7 rounded-full border-2 border-white shadow ring-1 ring-slate-200 transition-transform duration-150 ease-out active:scale-[0.94] disabled:opacity-40"
            style={{ background: c.hex }} />
        ))}
        <button type="button" onMouseDown={keep} onClick={() => apply({ weight: 700 })} disabled={!selLen}
          className="inline-flex h-7 items-center gap-1 rounded-lg bg-slate-100 px-2 text-[11.5px] font-bold disabled:opacity-40" aria-label="Seçili yazıyı kalın yap">
          <Bold className="h-3.5 w-3.5" aria-hidden />Kalın
        </button>
        <button type="button" onMouseDown={keep} onClick={() => apply({ color: null, weight: null })} disabled={!selLen}
          className="inline-flex h-7 items-center gap-1 rounded-lg bg-slate-100 px-2 text-[11.5px] font-bold disabled:opacity-40" aria-label="Seçili yazının rengini ve kalınlığını kaldır">
          <Eraser className="h-3.5 w-3.5" aria-hidden />Temizle
        </button>
        {!selLen && <span className="text-[11px] text-canvas-muted">Renk vermek için yazının bir kısmını seçin.</span>}
      </div>
      {runs.some((r) => r.color || r.weight) && (
        <p className="rounded-lg bg-white/70 px-2.5 py-1.5 text-[12.5px] leading-snug" aria-label="Renkli önizleme">
          <RunsView runs={runs} fallback={palette.text} />
        </p>
      )}
    </div>
  );
}
