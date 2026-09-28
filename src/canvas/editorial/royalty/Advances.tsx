import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Note, Pill, btnGhost, btnPrimary, field } from '../../admin/ui';
import { Kpi, KpiRow, Panel, useDebounced } from '../kit';
import { NumInput } from '../contracts/TermsForm';
import { Field, Sheet, day, errMsg, money, num, stamp, today } from '../contracts/ui';
import { royaltyApi, type AdvanceItem, type Meta } from './api';
import SqlInfo from '../../components/SqlInfo';
import type { Kaynaklar } from '../../components/sqlInfo';

const STEP = 50;

/** Avans portföyü: son hesaplanan koşudan kalan (kazanılmamış) avans, açılışı girilmemiş olanlar ve geri dönmesi zor olanlar. */
export function Advances({ meta }: { meta: Meta }) {
  const [q, setQ] = useState('');
  const [only, setOnly] = useState('');
  const [shown, setShown] = useState(STEP);
  const [edit, setEdit] = useState<AdvanceItem | null>(null);
  const dq = useDebounced(q, 300);
  const list = useQuery({ queryKey: ['royalty', 'advances', dq, only], queryFn: () => royaltyApi.advances({ q: dq, only }), placeholderData: keepPreviousData });
  const d = list.data;
  const totals = Object.entries(d?.totals ?? {});
  return (
    <>
      {d && totals.length > 0 && (
        <KpiRow>
          {totals.slice(0, 2).map(([cur, t]) => (
            <Kpi key={cur} label={`Kalan avans (${cur})`} value={money(t.remaining, cur)} help={`Verilen ${money(t.advance, cur)}`}
              info={<SqlInfo k={d.kaynaklar} alan="totals" label={`Kalan avans (${cur})`} />} />
          ))}
          <Kpi label="Açılışı girilmemiş" value={num(totals.reduce((s, [, t]) => s + t.missing, 0), 0)} help="Bu sözleşmeler koşuda istisna"
            active={only === 'acilis-yok'} onClick={() => setOnly((v) => (v === 'acilis-yok' ? '' : 'acilis-yok'))}
            info={<SqlInfo k={d.kaynaklar} alan="totals" label="Açılışı girilmemiş" />} />
          <Kpi label="Geri dönmesi zor" value={num(totals.reduce((s, [, t]) => s + t.risk, 0), 0)} help={`Bugünkü hızla ${num(meta.riskYears)} yıldan uzun`}
            active={only === 'risk'} onClick={() => setOnly((v) => (v === 'risk' ? '' : 'risk'))}
            info={<SqlInfo k={d.kaynaklar} alan="riskYears" label="Geri dönmesi zor (risk yılı)" />} />
        </KpiRow>
      )}
      <Panel>
        <input value={q} onChange={(e) => { setQ(e.target.value); setShown(STEP); }} placeholder="Sözleşme, kitap ya da hak sahibi ara" aria-label="Ara" className={field} />
        {d?.run ? (
          <p className="mt-2 text-[11.5px] text-canvas-muted">
            Kaynak: {d.run.no} ({d.run.label}) koşusu. Kalan avans o dönemin mahsubundan sonraki tutardır.
            <SqlInfo k={d.kaynaklar} alan="items[]" label="Avanslı sözleşmeler (avans, kalan, dönem telifi, kapanma)" className="ml-0.5 align-middle" />
          </p>
        ) : d ? (
          <div className="mt-2"><Note tone="info">Henüz hesaplanmış bir dönem koşusu yok; avans portföyü koşudan okunur.</Note></div>
        ) : null}
        {list.error && <div className="mt-2"><Note tone="err">{errMsg(list.error)}</Note></div>}
        {list.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
        {d && d.run && !d.items.length && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan avanslı sözleşme yok.</p>}
        <ul className="mt-3 space-y-2">
          {d?.items.slice(0, shown).map((x) => (
            <li key={x.contractKey} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="min-w-0 truncate text-[12.5px] font-extrabold">{x.no}</span>
                {x.openingMissing && <Pill tone="err">Açılış girilmemiş</Pill>}
                {x.risk && <Pill tone="warn">Geri dönmesi zor</Pill>}
                {!x.recoupable && <Pill tone="muted">Mahsup edilmez</Pill>}
                {d.can.advance && (
                  <button type="button" className={`${btnGhost} ml-auto`} onClick={() => setEdit(x)}>
                    {x.opening ? 'Açılışı değiştir' : 'Açılış gir'}
                  </button>
                )}
              </div>
              <div className="mt-1 truncate text-[12px] text-canvas-muted">{x.title} · {x.parties.join(', ')}</div>
              <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
                <span>Avans <b className="font-mono tabular-nums">{money(x.advance, x.currency)}</b></span>
                <span>Kalan <b className="font-mono tabular-nums">{x.remaining != null ? money(x.remaining, x.currency) : '—'}</b></span>
                <span>Dönem telifi <b className="font-mono tabular-nums">{money(x.periodGross, x.currency)}</b></span>
                {x.yearsToRecoup != null && <span>Kapanma ≈ <b>{num(x.yearsToRecoup, 1)} yıl</b></span>}
                {x.opening && <span className="text-canvas-muted">Açılış {money(x.opening.amount, x.opening.currency)} · {day(x.opening.asOf)} · {x.opening.by}</span>}
              </div>
            </li>
          ))}
        </ul>
        {d && d.items.length > shown && (
          <div className="mt-3 flex items-center justify-between gap-2 text-[12px] text-canvas-muted">
            <span className="inline-flex items-center">{num(d.items.length, 0)} sözleşmenin {num(shown, 0)} tanesi gösteriliyor<SqlInfo k={d.kaynaklar} alan="items[]" label="Avanslı sözleşme sayısı" className="ml-0.5" /></span>
            <button type="button" className={btnGhost} onClick={() => setShown((n) => n + STEP)}>Daha fazla göster</button>
          </div>
        )}
      </Panel>
      {edit && <OpeningSheet item={edit} meta={meta} k={d?.kaynaklar} onClose={() => setEdit(null)} />}
    </>
  );
}

function OpeningSheet({ item, meta, k, onClose }: { item: AdvanceItem; meta: Meta; k?: Kaynaklar; onClose: () => void }) {
  const qc = useQueryClient();
  const [amount, setAmount] = useState<number | null>(item.opening?.amount ?? null);
  const [asOf, setAsOf] = useState(item.opening?.asOf ?? '');
  const [reason, setReason] = useState('');
  const hist = useQuery({ queryKey: ['royalty', 'advance', item.contractKey], queryFn: () => royaltyApi.advanceHistory(item.contractKey) });
  const save = useMutation({
    mutationFn: (remove: boolean) => royaltyApi.setAdvance(item.contractKey, remove ? { reason, remove, no: item.no } : { amount, currency: item.currency, asOf, reason, no: item.no }),
    onSuccess: () => {
      toast.success('Avans açılışı kaydedildi; koşuyu yeniden hesaplatınca geçerli olur.');
      qc.invalidateQueries({ queryKey: ['royalty'] });
      onClose();
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  return (
    <Sheet title={`Avans açılışı — ${item.no}`} onClose={onClose}
      footer={
        <>
          {item.opening && <button type="button" className={btnGhost} disabled={save.isPending || !reason.trim()} onClick={() => save.mutate(true)}>Açılışı kaldır</button>}
          <button type="button" className={btnPrimary} disabled={save.isPending || amount == null || !asOf || !reason.trim()} onClick={() => save.mutate(false)}>
            {save.isPending && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            Kaydet
          </button>
        </>
      }>
      <div className="space-y-3">
        <Note tone="info">
          Sözleşmedeki avans {money(item.advance, item.currency)}<SqlInfo k={k} alan="items[]" label="Sözleşmedeki avans" className="ml-0.5 align-middle" />. Girilen tutar, seçilen tarihte henüz telifle kapanmamış (kazanılmamış) kalan avanstır.
          Bilinmeyen avans sıfır sayılmaz; açılış girilene kadar sözleşme koşuda istisnadır.
        </Note>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={`Kalan avans (${meta.currencies[item.currency] ?? item.currency})`}>
            <NumInput value={amount} onChange={setAmount} />
          </Field>
          <Field label="Hangi tarihteki bakiye">
            <input type="date" value={asOf} max={today()} onChange={(e) => setAsOf(e.target.value)} className={field} />
          </Field>
        </div>
        <Field label="Kaynak / gerekçe" hint="Ör. «2025 sonu mutabakat dosyası». Kimin girdiği kaydedilir.">
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={field} />
        </Field>
        {(hist.data?.history.length ?? 0) > 0 && (
          <div>
            <div className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Geçmiş <SqlInfo k={hist.data?.kaynaklar} alan="history[]" label="Avans açılışı geçmişi" /></div>
            <ul className="mt-1 space-y-1 text-[12px]">
              {hist.data!.history.map((h, i) => (
                <li key={i} className={h.active ? 'font-semibold' : 'text-canvas-muted'}>
                  {h.amount != null ? money(h.amount, h.currency) : '—'} · {day(h.asOf)} · {h.reason} · {h.by}, {stamp(h.at)}{h.active ? ' (geçerli)' : ''}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </Sheet>
  );
}
