import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft } from 'lucide-react';
import { Note, field } from '../../admin/ui';
import { Kpi, KpiRow, ModuleFrame, Panel } from '../kit';
import { contractApi, metaOptions, type Payment } from './api';
import { PaidSheet, PaymentRow } from './PaymentsTab';
import { errMsg, money } from './ui';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';

/** Bütün sözleşmelerin ödeme takvimi: vadesi gelen avans, tek ödeme ve hakedişler. */
export default function PaymentsScreen() {
  const [status, setStatus] = useState('planlandi');
  const [within, setWithin] = useState('90');
  const [kind, setKind] = useState('');
  const [paying, setPaying] = useState<Payment | null>(null);
  const meta = useQuery(metaOptions());
  const q = useQuery({
    queryKey: ['contracts', 'due', status, within, kind],
    queryFn: () => contractApi.due({ status, within: status === 'planlandi' && within ? Number(within) : undefined, kind }),
  });
  const data = q.data;
  const items = data?.items ?? [];
  const overdue = items.filter((p) => p.overdue);
  const totals = Object.entries(data?.totals ?? {});
  return (
    <ModuleFrame route="/telif-sozlesme" crumb="Sözleşmeler" title="Ödeme takvimi" lead="Portalda izlenen sözleşmelerin avans, tek ödeme ve hakediş ödemeleri. Ödendi bilgisi portalda tutulur; Logo'ya yazılmaz." source="Portal">
      <div className="px-1">
        <Link to="/telif-sozlesme" className="inline-flex min-h-11 items-center gap-1 text-[12px] font-bold text-canvas-violet hover:underline sm:min-h-0">
          <ChevronLeft aria-hidden className="h-4 w-4" />
          Bütün sözleşmeler
        </Link>
      </div>
      {q.error && <Note tone="err">{errMsg(q.error)}</Note>}
      {data && status === 'planlandi' && (
        <KpiRow>
          <Kpi label="Bekleyen ödeme" value={String(items.length)} help={within ? `${within} gün içinde vadesi gelen ve vadesiz` : 'Bütün vadeler'}
            info={<SqlInfo k={data.kaynaklar} alan="sayac.bekleyen" label="Bekleyen ödeme" />} />
          <Kpi label="Vadesi geçen" value={String(overdue.length)} help={overdue.length ? 'Ödendi işaretlenmemiş' : 'Yok'}
            info={<SqlInfo k={data.kaynaklar} alan="sayac.vadesiGecen" label="Vadesi geçen" />} />
          {totals.slice(0, 2).map(([cur, t]) => (
            <Kpi key={cur} label={`Toplam (${cur})`} value={money(t.amount, cur)} help={t.overdue ? `${money(t.overdue, cur)} vadesi geçmiş` : 'Vadesi geçen yok'}
              info={<SqlInfo k={data.kaynaklar} alan="totals" label={`Toplam (${cur})`} />} />
          ))}
        </KpiRow>
      )}
      <Panel>
        <div className="grid gap-2 sm:grid-cols-3">
          <select aria-label="Durum" value={status} onChange={(e) => setStatus(e.target.value)} className={field}>
            <option value="planlandi">Bekleyen</option>
            <option value="odendi">Ödenen</option>
            <option value="iptal">İptal</option>
            <option value="">Hepsi</option>
          </select>
          <select aria-label="Vade" value={within} disabled={status !== 'planlandi'} onChange={(e) => setWithin(e.target.value)} className={field}>
            <option value="30">30 gün içinde</option>
            <option value="90">90 gün içinde</option>
            <option value="365">Bir yıl içinde</option>
            <option value="">Bütün vadeler</option>
          </select>
          <select aria-label="Tür" value={kind} onChange={(e) => setKind(e.target.value)} className={field}>
            <option value="">Bütün türler</option>
            {Object.entries(meta.data?.paymentKinds ?? {}).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
        {q.isLoading && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Okunuyor…</p>}
        {data && !items.length && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan ödeme yok.</p>}
        {data && items.length > 0 && (
          <div className="mt-3 text-[11.5px] font-semibold text-canvas-muted">
            <InfoLabel k={data.kaynaklar} alan="items[]" label="Ödemeler (tutar, vade, ödenen)">{`${items.length} ödeme`}</InfoLabel>
          </div>
        )}
        <ul className="mt-3 space-y-2">
          {items.map((p) => (
            <PaymentRow
              key={p.id}
              p={p}
              canEdit={false}
              canPay={!!data?.can.finance}
              onPay={() => setPaying(p)}
              contract={
                <Link to={`/telif-sozlesme/${p.contractKey}?sekme=odeme`} className="text-[12px] font-bold text-canvas-violet hover:underline">
                  {p.contractNo} · {p.contractTitle}
                </Link>
              }
            />
          ))}
        </ul>
      </Panel>
      {paying && <PaidSheet p={paying} onClose={() => setPaying(null)} />}
    </ModuleFrame>
  );
}
