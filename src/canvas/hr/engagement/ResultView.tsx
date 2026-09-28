import type { ReactNode } from 'react';
import { Note, Pill } from '../../admin/ui';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';
import { fmtNum, type Item, type Result } from './engApi';

/** Anket sonucu gösterimi: eNPS, bağlılık endeksi, madde sonuçları. Gizlenmiş sonuçta nedeni açık yazar (eşik, açık anket,
 *  kırılım kapalı). Rakamlar köprüden; burada hesap yok. */
/**
 * `k` + `base` + `row`: sorgu bilgisi. Şirket sonucunda `base` boş; «Birimimin sonucu» listesinde `base="results[]"` ve
 * `row="<anket>:<birim>"`. Eşik altı sonuç ve birim «gizli» hesabına bağlıdır (sayı yok).
 */
export default function ResultView({ r, onUnit, k, base = '', row }: {
  r: Result; onUnit?: (unitId: string) => void; k?: Kaynaklar; base?: string; row?: string;
}) {
  const p = (a: string) => (base ? `${base}.${a}` : a);
  if (r.suppressed) {
    return (
      <Note tone="info">
        {r.message ?? 'Sonuç gösterilmiyor.'}
        {k && <SqlInfo k={k} alan={base || 'suppressed'} row={row} label="Gizli sonuç (eşik)" className="ml-0.5" />}
      </Note>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-3 gap-2">
        <Big label="Yanıt" value={fmtNum(r.n, 0)} info={k && <SqlInfo k={k} alan={p('n')} row={row} label="Yanıt sayısı" />} />
        <Big label="eNPS" value={r.enps !== null && r.enps !== undefined ? `${r.enps > 0 ? '+' : ''}${fmtNum(r.enps)}` : '—'} help="9–10 verenler − 0–6 verenler"
          info={k && <SqlInfo k={k} alan={p('enps')} row={row} label="eNPS" />} />
        <Big label="Bağlılık endeksi" value={fmtNum(r.index)} help="0–100; Likert maddelerinden" info={k && <SqlInfo k={k} alan={p('index')} row={row} label="Bağlılık endeksi" />} />
      </div>
      {k && (r.items ?? []).length > 0 && (
        <div className="text-[11px] font-semibold text-canvas-muted">
          <InfoLabel k={k} alan={p('items')} row={row} label="Madde sonuçları">Madde ortalaması, olumlu % ve yanıt</InfoLabel>
        </div>
      )}
      <ul className="flex flex-col gap-1.5">
        {(r.items ?? []).map((it) => <li key={it.key}><ItemRow it={it} /></li>)}
      </ul>
      {r.units && (
        <div>
          <div className="mb-1 flex items-center gap-1 text-[12px] font-bold uppercase tracking-wide text-canvas-muted">
            Birimler (gösterim eşiği {r.minGroup}){k && <SqlInfo k={k} alan={p('units')} row={row} label="Birim yanıt sayıları" />}
          </div>
          <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {r.units.map((u) => (
              <li key={u.unitId}>
                {u.shown && onUnit ? (
                  <button type="button" onClick={() => onUnit(u.unitId)} className="flex min-h-11 w-full items-center gap-2 rounded-xl bg-white/80 px-3 py-2 text-left text-[12.5px] transition-colors duration-150 hover:bg-white">
                    <span className="min-w-0 flex-1 break-words font-bold">{u.unitName}</span><Pill tone="violet">{u.n} yanıt</Pill>
                  </button>
                ) : (
                  <div className="flex min-h-11 items-center gap-2 rounded-xl bg-slate-50 px-3 py-2 text-[12.5px]">
                    <span className="min-w-0 flex-1 break-words font-bold">{u.unitName}</span>
                    {u.shown ? <Pill tone="violet">{u.n} yanıt</Pill> : <span className="text-canvas-muted">«{u.mergedInto}» ile birlikte</span>}
                    {!u.shown && k && <SqlInfo k={k} alan={p('units[]')} row={u.unitId} label={`${u.unitName ?? 'Birim'} · gizli`} />}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Big({ label, value, help, info }: { label: string; value: string; help?: string; info?: ReactNode }) {
  return (
    <div className="rounded-2xl bg-white/80 px-3 py-2">
      <div className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}{info}</div>
      <div className="text-[22px] font-extrabold tabular-nums">{value}</div>
      {help && <div className="text-[10.5px] leading-tight text-canvas-muted">{help}</div>}
    </div>
  );
}

function ItemRow({ it }: { it: Item }) {
  if (it.type === 'likert5') {
    const total = it.dist.reduce((a, b) => a + b, 0) || 1;
    const tones = ['bg-red-300', 'bg-orange-200', 'bg-slate-200', 'bg-emerald-200', 'bg-emerald-400'];
    return (
      <div className="rounded-xl bg-white/80 p-2.5">
        <div className="flex flex-wrap items-baseline gap-2">
          <span className="min-w-0 flex-1 break-words text-[12.5px] font-semibold">{it.text}</span>
          <span className="font-mono text-[12px] tabular-nums">ort. {fmtNum(it.mean, 2)} · olumlu %{fmtNum(it.favorable, 0)} · {it.n}</span>
        </div>
        <div className="mt-1 flex h-2 overflow-hidden rounded-full" aria-hidden>
          {it.dist.map((c, i) => <div key={i} className={tones[i]} style={{ width: `${(c / total) * 100}%` }} />)}
        </div>
      </div>
    );
  }
  if (it.type === 'enps') {
    return (
      <div className="rounded-xl bg-white/80 p-2.5 text-[12.5px]">
        <div className="font-semibold">{it.text}</div>
        <div className="font-mono text-[12px]">0–6: {it.dist.slice(0, 7).reduce((a, b) => a + b, 0)} · 7–8: {it.dist[7] + it.dist[8]} · 9–10: {it.dist[9] + it.dist[10]} · {it.n} yanıt</div>
      </div>
    );
  }
  return (
    <div className="rounded-xl bg-white/80 p-2.5 text-[12.5px]">
      <div className="font-semibold">{it.text}</div>
      <div className="flex flex-wrap gap-1.5">{Object.entries(it.counts).map(([o, c]) => <Pill key={o} tone="muted">{o}: {c}</Pill>)}</div>
    </div>
  );
}
