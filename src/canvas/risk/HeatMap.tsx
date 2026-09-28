import { LEVEL_STYLE, type HeatCell, type Level } from './api';

/** 5×5 risk matrisi: dikeyde olasılık (5 üstte), yatayda etki. Her hücrede risk sayısı ve olasılık × etki puanı yazılı
 *  (renk tek başına anlam taşımaz). Dokununca o hücrenin riskleri açılır. */
export default function HeatMap({ grid, selected, onSelect, levels }: {
  grid: HeatCell[][];
  selected: string | null;
  onSelect: (key: string | null) => void;
  levels: Record<Level, string>;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="grid grid-cols-[18px_repeat(5,minmax(0,1fr))] gap-1 sm:grid-cols-[22px_repeat(5,minmax(0,1fr))] sm:gap-1.5">
        <div className="row-span-5 flex items-center justify-center">
          <span className="-rotate-90 whitespace-nowrap text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Olasılık</span>
        </div>
        {[5, 4, 3, 2, 1].map((o) =>
          [1, 2, 3, 4, 5].map((e) => {
            const c = grid[o - 1]?.[e - 1];
            if (!c) return <div key={`${o}x${e}`} />;
            const key = `${o}x${e}`;
            const on = selected === key;
            return (
              <button
                key={key}
                type="button"
                disabled={!c.sayi}
                aria-pressed={on}
                aria-label={`Olasılık ${o}, etki ${e}, puan ${c.puan} (${levels[c.seviye]}): ${c.sayi} risk`}
                onClick={() => onSelect(on ? null : key)}
                className={`relative flex aspect-square min-h-11 flex-col items-center justify-center rounded-lg text-center transition-transform duration-150 ease-out enabled:active:scale-[0.96] sm:rounded-xl ${
                  LEVEL_STYLE[c.seviye].cell
                } ${on ? 'ring-2 ring-canvas-ink ring-offset-1' : ''} ${c.sayi ? '' : 'opacity-60'}`}
              >
                <span className="font-mono text-[17px] font-extrabold leading-none tabular-nums sm:text-[20px]">{c.sayi || ''}</span>
                <span className="absolute bottom-0.5 right-1 font-mono text-[9px] font-bold tabular-nums opacity-70 sm:text-[10px]">{c.puan}</span>
              </button>
            );
          }),
        )}
        <div />
        {[1, 2, 3, 4, 5].map((e) => (
          <div key={e} className="text-center font-mono text-[11px] font-bold tabular-nums text-canvas-muted">{e}</div>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 pl-6">
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Etki →</span>
        <div className="flex flex-wrap gap-1.5">
          {(Object.keys(LEVEL_STYLE) as Level[]).map((l) => (
            <span key={l} className={`rounded-md px-1.5 py-0.5 text-[10.5px] font-bold ${LEVEL_STYLE[l].pill}`}>{levels[l]}</span>
          ))}
        </div>
      </div>
    </div>
  );
}
