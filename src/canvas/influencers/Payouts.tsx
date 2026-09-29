import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtMoney, inflApi, today, type PayoutRow, type Payouts as Data } from './api';
import { AskSheet, InflFrame, useMeta } from './parts';

/** Muhasebe ödeme listesi: hazır (ödeme aşamasına giren ücretli iş) → onaylı → ödendi (Logo belge no ile). Açık
 *  satırlar her ay görünür; ödenenler seçilen ayın. Portal ödeme yapmaz; ödeme Logo'da yapılır. */
export default function Payouts() {
  const meta = useMeta();
  const [params, setParams] = useSearchParams();
  const month = params.get('ay') ?? today().slice(0, 7);
  const q = useQuery({ queryKey: ['influencers', 'payouts', month], queryFn: () => inflApi.payouts(month), enabled: ENGINE_ENABLED && !!meta.data?.me.canSeeFee });
  const d = q.data;
  return (
    <InflFrame
      title="İşbirliği ödemeleri"
      lead="Ücretli işbirliklerinin ödeme listesi: yalnız rapor aşamasını geçmiş ve yasal etiketi «var» işaretlenmiş işler girer. İşi açan ya da satırı hazırlayan onaylayamaz; ödeme Logo'da yapılır, burada Logo belge numarasıyla «ödendi» işaretlenir."
      aside={d?.me.canExport ? <a href={inflApi.payoutsUrl(month)} className={btnGhost}><Download aria-hidden className="h-4 w-4" /> Excel indir</a> : undefined}
    >
      {meta.data && !meta.data.me.canSeeFee && <Note tone="warn">Ödeme listesi işbirliği onay ya da ödeme yetkisi ister.</Note>}
      <Panel>
        <label className="flex w-full flex-col gap-1 sm:w-48">
          <span className={labelCls}>Ödeme ayı</span>
          <input type="month" className={field} value={month} onChange={(e) => setParams(e.target.value ? { ay: e.target.value } : {}, { replace: true })} />
        </label>
      </Panel>
      {q.error && <Note tone="err">{errText(q.error, 'Ödeme listesi okunamadı.')}</Note>}
      {d && <List d={d} />}
    </InflFrame>
  );
}

function List({ d }: { d: Data }) {
  const qc = useQueryClient();
  const [ask, setAsk] = useState<null | { row: PayoutRow; action: 'geri' | 'iptal' }>(null);
  const [pay, setPay] = useState<PayoutRow | null>(null);
  const act = useMutation({
    mutationFn: (b: { id: string; action: 'onayla' | 'ode' | 'geri' | 'iptal'; note?: string; logoDocNo?: string; paidAt?: string }) =>
      inflApi.decidePayout(b.id, { action: b.action, note: b.note, logoDocNo: b.logoDocNo, paidAt: b.paidAt }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['influencers'] }); setAsk(null); setPay(null); toast.success('Kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <>
      <KpiRow>
        <Kpi label="Hazır" value={fmtMoney(d.totals.hazir)} help="Onay bekliyor" info={<SqlInfo k={d.kaynaklar} alan="totals" label="Hazır" />} />
        <Kpi label="Onaylı" value={fmtMoney(d.totals.onayli)} help="Ödeme bekliyor" info={<SqlInfo k={d.kaynaklar} alan="totals" label="Onaylı" />} />
        <Kpi label="Ödenen" value={fmtMoney(d.totals.odendi)} help={`${d.month} ayında`} info={<SqlInfo k={d.kaynaklar} alan="totals" label="Ödenen" />} />
      </KpiRow>
      <Panel>
        <div className="mb-2 flex items-center gap-1 text-[11.5px] text-canvas-muted">Ödeme satırları<SqlInfo k={d.kaynaklar} alan="items" label="Ödeme satırları" /></div>
        {d.items.length === 0 && <div className="py-6 text-center text-[12.5px] text-canvas-muted">Bu ay ödeme satırı yok. Ücretli bir işbirliği rapor aşamasını geçince satırı burada oluşur.</div>}
        <div className="flex flex-col gap-2">
          {d.items.map((r) => (
            <div key={r.id} className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 md:grid-cols-[minmax(0,1fr)_140px_auto] md:items-center">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-[11px] text-canvas-muted">#{r.no} · {r.collabCode}</span>
                  <Pill tone={r.status === 'odendi' ? 'ok' : r.status === 'onayli' ? 'violet' : 'warn'}>{r.statusLabel}</Pill>
                  {r.approvedBy && <span className="text-[11px] text-canvas-muted">onay {r.approvedBy}</span>}
                  {r.logoDocNo && <span className="text-[11px] text-canvas-muted">Logo {r.logoDocNo} · {fmtDay(r.paidAt)}</span>}
                </div>
                <div className="mt-0.5 break-words text-[13px] font-extrabold"><Link to={`/isbirlikleri/kisi/${r.personId}`} className="hover:underline">{r.personName}</Link></div>
                <div className="break-words text-[12px] text-canvas-muted">{r.bookTitle} · {r.kindLabel}{r.publishedUrl ? ' · ' : ''}{r.publishedUrl && <a href={r.publishedUrl} target="_blank" rel="noreferrer" className="text-canvas-violet hover:underline">paylaşım</a>}</div>
                {r.note && <div className="text-[11.5px] text-amber-700">{r.note}</div>}
              </div>
              <div className="font-mono text-[14px] font-extrabold tabular-nums md:text-right">{fmtMoney(r.amount)}</div>
              <div className="flex flex-wrap gap-2 md:justify-end">
                {r.status === 'hazir' && (d.me.canApprove || d.me.canPay) && (
                  <button type="button" className={btnPrimary} disabled={act.isPending} onClick={() => act.mutate({ id: r.id, action: 'onayla' })}>Onayla</button>
                )}
                {r.status === 'hazir' && <button type="button" className={btnGhost} onClick={() => setAsk({ row: r, action: 'iptal' })}>İptal</button>}
                {r.status === 'onayli' && d.me.canPay && <button type="button" className={btnPrimary} onClick={() => setPay(r)}>Ödendi</button>}
                {r.status === 'onayli' && <button type="button" className={btnGhost} onClick={() => setAsk({ row: r, action: 'geri' })}>Onayı geri al</button>}
              </div>
            </div>
          ))}
        </div>
      </Panel>
      <AskSheet
        open={!!ask}
        title={ask?.action === 'iptal' ? 'Ödeme satırını iptal et' : 'Onayı geri al'}
        message={ask?.action === 'iptal' ? 'İş «rapor» aşamasına döner; ücret düzeltilip yeniden ödemeye alınabilir.' : 'Satır «hazır»a döner.'}
        confirm={ask?.action === 'iptal' ? 'İptal et' : 'Geri al'}
        danger
        input="Neden"
        required
        busy={act.isPending}
        onClose={() => setAsk(null)}
        onConfirm={(note) => ask && act.mutate({ id: ask.row.id, action: ask.action, note })}
      />
      <PaySheet row={pay} busy={act.isPending} onClose={() => setPay(null)} onPay={(logoDocNo, paidAt) => pay && act.mutate({ id: pay.id, action: 'ode', logoDocNo, paidAt })} />
    </>
  );
}

function PaySheet({ row, busy, onClose, onPay }: { row: PayoutRow | null; busy: boolean; onClose: () => void; onPay: (doc: string, day: string) => void }) {
  const [doc, setDoc] = useState('');
  const [day, setDay] = useState(today());
  return (
    <Sheet open={!!row} modal onClose={onClose} title="Ödendi olarak işaretle" subtitle={row ? `${row.personName} · ${fmtMoney(row.amount)}` : undefined}>
      <div className="flex flex-col gap-3 text-[13px]">
        <label className="flex flex-col gap-1"><span className={labelCls}>Logo belge numarası *</span><input className={field} value={doc} onChange={(e) => setDoc(e.target.value)} /></label>
        <label className="flex flex-col gap-1"><span className={labelCls}>Ödeme günü</span><input type="date" className={field} value={day} max={today()} onChange={(e) => setDay(e.target.value)} /></label>
        <p className="text-[11.5px] text-canvas-muted">İşbirliği kapanır. Kesinti ve ödeme Logo'da yapılır; burada yalnız kayıt tutulur.</p>
        <div className="flex justify-end"><button type="button" className={btnPrimary} disabled={!doc.trim() || busy} onClick={() => onPay(doc.trim(), day)}>Kaydet</button></div>
      </div>
    </Sheet>
  );
}
