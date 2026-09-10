import type { ReactNode } from 'react';
import { Minus, Plus, Send, Share2 } from 'lucide-react';
import type { CanvasQuestion } from '../types';
import { ZOOM_MAX, ZOOM_MIN } from '../stage/CanvasStage';

/** Üst sol kırıntı yolu + sağda motor durumu ve yakınlaştırma. */
export function CanvasTopBar({
  crumb,
  source,
  engineOk,
  engineLabel,
  zoom,
  onZoom,
  stacked,
}: {
  crumb: string;
  source: string;
  engineOk: boolean;
  engineLabel: string;
  zoom: number;
  onZoom: (z: number) => void;
  stacked: boolean;
}) {
  const step = (d: number) => onZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Number((zoom + d).toFixed(2)))));
  return (
    <header className="pointer-events-none absolute left-4 right-4 top-5 z-40 flex items-center justify-between gap-3 sm:left-7 sm:right-7">
      <div className="cv-glass pointer-events-auto flex min-w-0 items-center gap-3 rounded-full px-4 py-2 shadow-glass-float">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-tr from-canvas-coral to-canvas-violet text-xs font-black text-white shadow-sm">
          N
        </div>
        <div className="flex min-w-0 items-center text-xs font-semibold tracking-tight">
          <span className="hidden font-bold text-canvas-ink sm:inline">NanobaseAI</span>
          <span className="mx-1.5 hidden text-canvas-muted/60 sm:inline">›</span>
          <span className="flex items-center gap-1.5 truncate rounded-full bg-canvas-violet/10 px-2 py-0.5 font-bold text-canvas-violet">
            <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-canvas-violet" />
            <span className="truncate">{crumb}</span>
          </span>
        </div>
        <span className="hidden shrink-0 border-l border-slate-200/80 pl-2.5 text-[10px] font-medium text-canvas-muted/70 lg:inline">
          {source}
        </span>
      </div>

      <div className="pointer-events-auto flex shrink-0 items-center gap-2 sm:gap-3">
        <div className="cv-glass flex items-center gap-2 rounded-full px-3.5 py-2 text-[11px] font-semibold shadow-glass-float">
          <span className={['h-2 w-2 rounded-full', engineOk ? 'bg-canvas-mint' : 'bg-red-400'].join(' ')} />
          <span className="hidden sm:inline">{engineLabel}</span>
        </div>
        <button
          type="button"
          className="cv-glass hidden items-center gap-1.5 rounded-full px-4 py-2 text-xs font-bold shadow-glass-float transition hover:text-canvas-violet lg:flex"
        >
          <Share2 className="h-3.5 w-3.5" />
          Paylaş
        </button>
        {!stacked && (
          <div className="cv-glass flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold shadow-glass-float">
            <button type="button" aria-label="Uzaklaştır" onClick={() => step(-0.1)} className="h-5 w-5 rounded-full font-bold text-canvas-muted hover:bg-slate-100">
              <Minus className="mx-auto h-3 w-3" />
            </button>
            <span className="w-9 text-center font-mono font-bold tabular-nums">%{Math.round(zoom * 100)}</span>
            <button type="button" aria-label="Yakınlaştır" onClick={() => step(0.1)} className="h-5 w-5 rounded-full font-bold text-canvas-muted hover:bg-slate-100">
              <Plus className="mx-auto h-3 w-3" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

/** Sahnenin tepesindeki soru balonu — kanvasın anlatısını başlatır. */
export function QuestionBubble({ q, stacked }: { q: CanvasQuestion; stacked?: boolean }) {
  return (
    <div
      className={
        stacked
          ? 'cv-glass rounded-3xl px-4 py-3 shadow-canvas-card'
          : 'cv-float absolute left-1/2 top-16 z-30 -translate-x-1/2'
      }
    >
      <div
        className={
          stacked
            ? 'flex items-center gap-3'
            : 'cv-glass flex items-center gap-3.5 rounded-full px-6 py-3.5 shadow-canvas-card ring-4 ring-white/40'
        }
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-tr from-amber-400 via-orange-400 to-rose-500 text-sm font-bold text-white shadow-md">
          {q.who}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="truncate text-[11px] font-bold uppercase tracking-wider text-canvas-muted">{q.role}</span>
            <span className="shrink-0 text-[10px] text-canvas-muted/60">{q.at}</span>
          </div>
          <h1 className="flex items-center gap-2 text-base font-extrabold tracking-tight text-canvas-ink">{q.text}</h1>
        </div>
        {q.answered !== false && (
          <span className="ml-2 hidden h-2.5 w-2.5 shrink-0 rounded-full bg-canvas-mint ring-4 ring-canvas-mint/20 sm:block" />
        )}
      </div>
    </div>
  );
}

/** Alt yüzen dock: hızlı geçişler + soru kutusu. */
export function CanvasDock({
  chips,
  placeholder,
  value,
  onChange,
  onSubmit,
}: {
  chips: ReactNode;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
}) {
  return (
    <div className="pointer-events-none absolute bottom-6 left-0 right-0 z-40 flex justify-center px-4">
      <form
        className="cv-dock pointer-events-auto flex w-full max-w-[940px] items-center gap-3 rounded-3xl p-2.5 shadow-dock-shadow"
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
      >
        <div className="hidden shrink-0 items-center gap-1.5 border-r border-slate-200/80 pl-1 pr-3 md:flex">{chips}</div>
        <div className="flex min-w-0 flex-1 items-center rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-2 shadow-inner transition focus-within:bg-white">
          <input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder={placeholder}
            className="w-full min-w-0 bg-transparent text-xs font-semibold text-canvas-ink outline-none placeholder:text-canvas-muted/70"
          />
        </div>
        <button
          type="submit"
          aria-label="Sor"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-tr from-canvas-coral to-canvas-violet text-white shadow-md transition-transform hover:scale-105 active:scale-95"
        >
          <Send className="h-4 w-4" />
        </button>
      </form>
    </div>
  );
}

/** Sağ alttaki tuval haritası; kartların sahnedeki dağılımını gösterir. */
export function CanvasMinimap({
  dots,
  zoom,
}: {
  dots: Array<{ id: string; x: number; y: number; w: number; accent: string }>;
  zoom: number;
}) {
  return (
    <div className="cv-glass absolute bottom-6 right-7 z-30 hidden w-[150px] rounded-2xl border border-white p-2.5 shadow-glass-float xl:block">
      <div className="mb-1.5 flex items-center justify-between text-[9px] font-extrabold uppercase tracking-wider text-canvas-muted">
        <span>Tuval haritası</span>
        <span className="text-canvas-ink">%{Math.round(zoom * 100)}</span>
      </div>
      <div className="relative h-20 w-full overflow-hidden rounded-xl border border-slate-200/60 bg-slate-100/90">
        {dots.map((d) => (
          <div
            key={d.id}
            className="absolute rounded-sm opacity-70"
            style={{
              left: `${(d.x / 1440) * 100}%`,
              top: `${(d.y / 1000) * 100}%`,
              width: `${Math.max(4, (d.w / 1440) * 100)}%`,
              height: '10%',
              background: d.accent,
            }}
          />
        ))}
      </div>
    </div>
  );
}
