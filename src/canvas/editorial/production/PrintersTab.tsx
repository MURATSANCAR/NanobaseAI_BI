import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, TableWrap, errText, nf, td, th } from '../../admin/ui';
import { Panel } from '../kit';
import { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, Explain } from '../../components/Explain';
import { productionApi, type PrinterStat } from './api';
import { fmtDay, fmtPct, fmtUnit } from './shared';

/** Matbaa performans analizi: geçmiş penceresindeki üretim kartlarından. Puan = zamanında teslim (50) + fiyat (30) +
 *  kalite (20); ölçülemeyen parça yarım puan alır ve «ölçülemedi» yazar. */

function Trend({ v }: { v: number | null }) {
  if (v === null) return <span className="text-canvas-muted">—</span>;
  const up = v > 0;
  return (
    <span className={`font-mono tabular-nums ${up ? 'text-rose-700' : 'text-emerald-700'}`}>
      {up ? '+' : ''}
      {Math.round(v * 100)}%
    </span>
  );
}

function ScoreBar({ p }: { p: PrinterStat }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-8 shrink-0 text-right font-mono text-[13px] font-bold tabular-nums">{p.score}</span>
      <span className="flex h-2 w-24 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <span className="bg-emerald-500" style={{ width: `${p.scoreParts.onTime}%` }} />
        <span className="bg-sky-500" style={{ width: `${p.scoreParts.price}%` }} />
        <span className="bg-amber-400" style={{ width: `${p.scoreParts.quality}%` }} />
      </span>
    </div>
  );
}

export default function PrintersTab({ onPick }: { onPick: (printer: string) => void }) {
  const q = useQuery({ queryKey: ['production', 'printers'], queryFn: productionApi.printers, enabled: ENGINE_ENABLED });
  const err = errText(q.error, 'Matbaa performansı okunamadı.');
  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">Matbaa performansı</h2>
        <p className="max-w-[70ch] text-[11.5px] leading-snug text-canvas-muted">
          {q.data ? `${fmtDay(q.data.historyFrom)} sonrası üretim kartları. ` : ''}
          Zamanında teslim: baskı çıkışı (Logo'da matbaadan gelen ilk depo girişi) CRM'deki baskı ayının sonundan geç değil. Birim fiyat:
          Logo'daki matbaa baskı faturasında adet başı bedel (son 12 ay ortancası; eğilim önceki 12 aya göre). Süre: dosya matbaada → depo girişi.
          Puan çubuğu: <span className="font-bold text-emerald-700">teslim</span> · <span className="font-bold text-sky-700">fiyat</span> ·{' '}
          <span className="font-bold text-amber-700">kalite</span>.
        </p>
      </div>
      {err && <div className="mt-3"><Note tone="err">{err}</Note></div>}
      {q.isLoading && <Loading />}
      {q.data && q.data.items.length === 0 && (
        <div className="mt-3">
          <EmptyHint title="Matbaası girilmiş üretim kartı yok" why="Matbaa, CRM üretim kartında ya da kartın ayrıntısında seçilince performansı burada ölçülür." />
        </div>
      )}
      {q.data && q.data.items.length > 0 && (
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Matbaa</th>
                <th className={th}>
                  <span className="inline-flex items-center gap-1">
                    <InfoLabel k={q.data.kaynaklar} alan="items[].score">Puan</InfoLabel>
                    <Explain label="Matbaa puanı">
                      0–100: zamanında teslim en çok 50, birim fiyat en çok 30 (bütün matbaaların ortancasından ucuzsa tam puan), kalite en çok 20. Ölçülemeyen parça yarım
                      puan alır ve adın altında «ölçülemedi» yazar.
                    </Explain>
                  </span>
                </th>
                <th className={`${th} text-right`}>
                  <InfoLabel k={q.data.kaynaklar} alan="items[].jobs">İş</InfoLabel>
                </th>
                <th className={`${th} text-right`}>
                  <InfoLabel k={q.data.kaynaklar} alan="items[].open">Süren iş</InfoLabel>
                </th>
                <th className={`${th} text-right`}>
                  <InfoLabel k={q.data.kaynaklar} alan="items[].onTimeRate">Zamanında</InfoLabel>
                </th>
                <th className={`${th} text-right`}>
                  <InfoLabel k={q.data.kaynaklar} alan="items[].leadDays">Dosya → depo</InfoLabel>
                </th>
                <th className={`${th} text-right`}>
                  <InfoLabel k={q.data.kaynaklar} alan="items[].unitRecent">Birim fiyat</InfoLabel>
                </th>
                <th className={`${th} text-right`}>
                  <span className="inline-flex items-center gap-1">
                    <InfoLabel k={q.data.kaynaklar} alan="items[].unitTrend">12 ay eğilim</InfoLabel>
                    <Explain label="12 ay eğilim">Son 12 ayın birim fiyatının önceki 12 aya göre değişimi. Kırmızı artı pahalanma, yeşil eksi ucuzlama demektir.</Explain>
                  </span>
                </th>
                <th className={`${th} text-right`}>
                  <span className="inline-flex items-center gap-1">
                    <InfoLabel k={q.data.kaynaklar} alan="items[].qualityRate">Kalite</InfoLabel>
                    <Explain label="Kalite">Kalite kaydı girilmiş işlerden sorunsuz olanların oranı. Kalite, üretim kartının ayrıntısında işaretlenir.</Explain>
                  </span>
                </th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((p) => (
                <tr key={p.printer} className="border-b border-slate-50 last:border-0">
                  <td className={td}>
                    <button type="button" className="text-left font-bold text-canvas-violet underline-offset-2 hover:underline" onClick={() => onPick(p.printer)}>
                      {p.printer}
                    </button>
                    {p.scoreNotes.length > 0 && <div className="text-[10.5px] text-canvas-muted">{p.scoreNotes.join(' · ')}</div>}
                  </td>
                  <td className={td}>
                    <ScoreBar p={p} />
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(p.jobs)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{nf.format(p.open)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>
                    {fmtPct(p.onTimeRate)}
                    <div className="text-[10.5px] text-canvas-muted">{nf.format(p.measured)} ölçüm</div>
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{p.leadDays === null ? '—' : `${p.leadDays} gün`}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(p.unitRecent ?? p.unitPrice)}</td>
                  <td className={`${td} text-right`}>
                    <Trend v={p.unitTrend} />
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>
                    {fmtPct(p.qualityRate)}
                    <div className="text-[10.5px] text-canvas-muted">{nf.format(p.qualityMarked)} kayıt</div>
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
    </Panel>
  );
}
