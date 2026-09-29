import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtInt, fmtMoney, tendersApi } from './api';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

/** Kamu kurumlarına geçmiş satış (Logo faturalı satış satırı, net ciro = LINENET, iade eksi). Kamu = CRM'de «Devlet
 *  Kurumu» ya da «Resmi» işaretli firma (Logo cari bağıyla) ∪ Logo satış kanalı KURUM. Kaynak her satırda yazılır. */

const SRC: Record<'crm' | 'kanal' | 'ikisi', string> = { crm: 'CRM kurum rolü', kanal: 'Logo kanalı', ikisi: 'İkisi' };

export default function PublicSalesTab() {
  const qc = useQueryClient();
  const now = new Date().getFullYear();
  const [yil, setYil] = useState(now);
  const [fresh, setFresh] = useState(false);
  const sales = useQuery({
    queryKey: ['tenders', 'public-sales', yil],
    queryFn: () => tendersApi.publicSales(yil, fresh),
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
  });
  const d = sales.data;
  const years = Array.from({ length: 6 }, (_, i) => now - i);
  return (
    <>
      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-[16px] font-extrabold tracking-tight">Kamu kurumlarına satış</h2>
            <p className="max-w-[80ch] text-[12px] text-canvas-muted">
              Kamu kurumlarına yaptığımız faturalı satışlar (Logo, iadeler düşülmüş). Kamu sayılanlar: CRM'de «Devlet Kurumu» ya da «Resmi» işaretli ve Logo carisine bağlı firmalar ile Logo'da satış kanalı {d?.kanal ?? 'KURUM'} olan cariler.
            </p>
          </div>
          <div className="flex items-end gap-2">
            <label className="flex w-28 flex-col gap-1">
              <span className={labelCls}>Yıl</span>
              <select className={field} value={yil} onChange={(e) => { setFresh(false); setYil(Number(e.target.value)); }}>
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <button
              type="button"
              className={btnGhost}
              disabled={sales.isFetching}
              onClick={() => { setFresh(true); qc.invalidateQueries({ queryKey: ['tenders', 'public-sales', yil] }); }}
            >
              {sales.isFetching ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
              Yenile
            </button>
          </div>
        </div>
        {sales.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Logo ve CRM okunuyor…</div>}
        {sales.error && <div className="mt-3"><Note tone="err">{errText(sales.error, 'Kamu satışı okunamadı.')}</Note></div>}
      </Panel>
      {d && (
        <>
          <KpiRow>
            <Kpi label="Net ciro" value={fmtMoney(d.toplamCiro)} help={`${d.year} · ${fmtInt(d.cariSayisi)} cari`} info={<SqlInfo k={d.kaynaklar} alan="toplamCiro" label="Kamu satışı net ciro" />} />
            <Kpi label="Net adet" value={fmtInt(d.toplamAdet)} help="Satış eksi iade" info={<SqlInfo k={d.kaynaklar} alan="toplamAdet" label="Kamu satışı net adet" />} />
            <Kpi label="CRM kamu kurumu" value={fmtInt(d.crmKurum)} info={<SqlInfo k={d.kaynaklar} alan="crmKurum" label="CRM kamu kurumu ve rol sayıları" />} help={`Devlet ${fmtInt(d.rolSayilari['2'] ?? 0)} · Resmi ${fmtInt(d.rolSayilari['3'] ?? 0)} · Özel STK ${fmtInt(d.rolSayilari['4'] ?? 0)}`} />
            <Kpi label="Logo bağı olmayan" value={fmtInt(d.crmLogoBagsiz)} help="CRM kamu kurumunda Logo cari numarası boş" info={<SqlInfo k={d.kaynaklar} alan="crmLogoBagsiz" label="Logo bağı olmayan kurum" />} />
          </KpiRow>
          {d.crmLogoBagsiz > 0 && (
            <Note tone="warn">{fmtInt(d.crmLogoBagsiz)} CRM kamu kurumunun Logo cari bağı yok; bu kurumlara satış yalnız Logo kanalı {d.kanal} ise sayılır.</Note>
          )}
          <Panel>
            <h3 className="flex items-center gap-1 text-[13px] font-extrabold">İllere göre<SqlInfo k={d.kaynaklar} alan="iller[]" label="İllere göre ciro ve cari" /></h3>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {d.iller.map((c) => (
                <span key={c.il} className="rounded-lg bg-white/80 px-2 py-1 text-[11.5px]">
                  <b>{c.il}</b> <span className="font-mono tabular-nums">{fmtMoney(c.ciro)}</span> <span className="text-canvas-muted">· {c.cari} cari</span>
                </span>
              ))}
            </div>
            <div className="mt-2 text-[11.5px] text-canvas-muted">
              Kaynağa göre: CRM kurum rolü {fmtMoney(d.kaynakCiro.crm)} · Logo kanalı {fmtMoney(d.kaynakCiro.kanal)} · ikisi {fmtMoney(d.kaynakCiro.ikisi)}
              <SqlInfo k={d.kaynaklar} alan="kaynakCiro" label="Kaynağa göre ciro" className="ml-0.5" />
            </div>
          </Panel>
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Cari</th>
                <th className={th}>İl</th>
                <th className={th}>Kaynak</th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[]" label="Cari net ciro">Net ciro</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[]" label="Cari net adet">Net adet</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="rows[]" label="Fatura sayısı">Fatura</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {d.rows.map((r) => (
                <tr key={r.ref} className="border-b border-slate-50 last:border-0">
                  <td className={td}><div className="font-semibold">{r.unvan ?? '—'}</div><div className="font-mono text-[11px] text-canvas-muted">{r.kod}</div></td>
                  <td className={td}>{r.il ?? '—'}</td>
                  <td className={td}><Pill tone={r.kaynak === 'ikisi' ? 'ok' : 'muted'}>{SRC[r.kaynak]}</Pill></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.ciro)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.adet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.fatura)}</td>
                </tr>
              ))}
              {!d.rows.length && (
                <tr><td className={`${td} text-center text-canvas-muted`} colSpan={6}>Bu yıl kamu kurumlarına faturalı satış yok.</td></tr>
              )}
            </tbody>
          </TableWrap>
        </>
      )}
    </>
  );
}
