import { Loader2, RotateCw } from 'lucide-react';
import { Pill } from '../admin/ui';
import SqlInfo from '../components/SqlInfo';
import { Explain } from '../components/Explain';
import type { Kaynaklar } from '../components/sqlInfo';
import { STATE, fmtAt, fmtDay, fmtMinutes, fmtMs, type Incident, type Ring } from './api';

/** Tek halka: durum, son deneme, veri sonu, açık olay. Kopukken kart kırmızı kenarlı ve tarif bir tık uzakta. */
export default function RingCard({ ring, canCheck, busy, onCheck, onIncident, k }: {
  ring: Ring;
  /** Sorgu bilgisi (durum cevabı): halkanın sayıları ve veri sonunu okuyan SQL. */
  k?: Kaynaklar;
  canCheck: boolean;
  busy: boolean;
  onCheck: () => void;
  onIncident: (i: Incident) => void;
}) {
  const s = STATE[ring.state];
  const inc = ring.incident ?? ring.stale;
  const edge = ring.state === 'down' ? 'border-red-200' : ring.state === 'stale' || ring.state === 'fail' ? 'border-amber-200' : 'border-white/80';
  return (
    <article className={`glass-panel flex min-w-0 flex-col gap-2 rounded-2xl border p-3.5 shadow-glass-float sm:rounded-3xl sm:p-4 ${edge}`}>
      <header className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full ${s.dot}`} />
            <h3 className="truncate text-[15px] font-extrabold tracking-tight">{ring.label}</h3>
            <SqlInfo k={k} alan="rings[]" row={ring.id} label={`${ring.label}: denetim`} />
          </div>
          <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{ring.hint}</p>
        </div>
        <Pill tone={s.tone === 'muted' ? 'muted' : s.tone}>{s.label}</Pill>
      </header>

      {ring.dataEnd && (
        <div className={`rounded-xl px-2.5 py-1.5 text-[12px] font-semibold ${ring.stale ? 'bg-amber-50 text-amber-900' : 'bg-slate-50 text-canvas-ink'}`}>
          Veri sonu <strong>{ring.id === 'logo' ? fmtDay(ring.dataEnd) : fmtAt(ring.dataEnd)}</strong>
          {ring.dataEndAge && <span className="text-canvas-muted"> · {ring.dataEndAge}</span>}
          <SqlInfo k={k} alan="rings[]" row={ring.id} label={`${ring.label}: veri sonu`} className="ml-1" />
          <Explain label="Veri sonu" className="ml-0.5">Bu kaynaktaki en yeni kaydın tarihi. Bağlantı çalışsa bile bu tarih izin verilen süreden eskiyse «Veri eski» olayı açılır.</Explain>
        </div>
      )}

      <p className="line-clamp-3 break-words text-[12px] leading-snug text-canvas-ink/80" title={ring.detail ?? undefined}>
        {ring.detail ?? 'Henüz denenmedi.'}
      </p>

      <dl className="mt-auto grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px]">
        <dt className="text-canvas-muted">Son deneme</dt>
        <dd className="text-right font-semibold tabular-nums">{fmtAt(ring.at)}</dd>
        <dt className="text-canvas-muted">Son başarılı</dt>
        <dd className="text-right font-semibold tabular-nums">{fmtAt(ring.lastOkAt)}</dd>
        {ring.latencyMs !== null && (
          <>
            <dt className="text-canvas-muted">Süre</dt>
            <dd className="text-right font-semibold tabular-nums">{fmtMs(ring.latencyMs)}</dd>
          </>
        )}
      </dl>

      <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-2">
        {inc && (
          <button
            type="button"
            onClick={() => onIncident(inc)}
            className={`inline-flex min-h-11 flex-1 items-center justify-center rounded-xl px-3 text-[12px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${
              inc.kind === 'kopma' ? 'bg-red-50 text-red-700 hover:bg-red-100' : 'bg-amber-50 text-amber-900 hover:bg-amber-100'
            }`}
          >
            {inc.kind === 'kopma' ? `${fmtMinutes(inc.minutes)}'dır kopuk · ne yapmalı` : 'Veri eski · ne yapmalı'}
          </button>
        )}
        {canCheck && (
          <button
            type="button"
            onClick={onCheck}
            disabled={busy}
            aria-label={`${ring.label} bağlantısını şimdi dene`}
            className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl bg-slate-100 px-3 text-[12px] font-extrabold text-canvas-ink transition-transform duration-150 ease-out hover:bg-slate-200 active:scale-[0.97] disabled:opacity-50 sm:min-h-9"
          >
            {busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RotateCw aria-hidden className="h-4 w-4" />}
            Şimdi dene
          </button>
        )}
      </div>
    </article>
  );
}
