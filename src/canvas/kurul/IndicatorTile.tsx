import { MessageSquareText } from 'lucide-react';
import { fmtDay, fmtValue, styleOf, type Indicator } from './api';
import { ColorBadge, TrendMark } from './parts';

/** Tek gösterge kutusu. «Kaynak yok» gri ve sayısızdır (sıfır yazılmaz); renk yanında ad ve simge vardır; her kutuda veri
 *  son günü. Dokununca ayrıntı penceresi açılır. */
export default function IndicatorTile({ g, onOpen }: { g: Indicator; onOpen: (kod: string) => void }) {
  const s = styleOf(g);
  const ready = g.durum === 'ok';
  return (
    <button
      type="button"
      onClick={() => onOpen(g.kod)}
      className={`flex min-h-[112px] w-full min-w-0 flex-col gap-1.5 rounded-2xl bg-white/85 p-3 text-left ring-1 transition-transform duration-150 ease-out active:scale-[0.98] ${s.ring} ${ready ? '' : 'bg-slate-50/80'}`}
      aria-label={`${g.ad}: ${ready ? g.degerMetin : s.label}. Ayrıntı`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="min-w-0 break-words text-[12.5px] font-bold leading-snug">{g.ad}</span>
        <ColorBadge durum={g.durum} renk={g.renk} />
      </div>
      {ready ? (
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
          <span className="font-mono text-[22px] font-bold leading-none tabular-nums tracking-tight">{g.degerKisa}</span>
          <TrendMark t={g.egilim} label={g.oncekiEtiket ? `${g.oncekiEtiket}: ${fmtValue(g.onceki, g.birim)}` : null} />
        </div>
      ) : (
        <p className="text-[11.5px] leading-snug text-canvas-muted">{g.not || (g.durum === 'olculmedi' ? 'Henüz ölçülmedi.' : 'Kaynak yok.')}</p>
      )}
      <div className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10.5px] text-canvas-muted">
        {g.veriSonGunu && <span>Veri: {fmtDay(g.veriSonGunu)}</span>}
        {g.kaynak && <span className="truncate">{g.kaynak}</span>}
        {g.yorum ? (
          <span className="inline-flex items-center gap-0.5 font-bold text-canvas-violet">
            <MessageSquareText aria-hidden className="h-3 w-3" /> yorum var
          </span>
        ) : ready && (g.renk === 'kirmizi' || g.renk === 'sari') ? (
          <span className="font-bold text-red-700">yorum bekleniyor</span>
        ) : null}
      </div>
    </button>
  );
}
