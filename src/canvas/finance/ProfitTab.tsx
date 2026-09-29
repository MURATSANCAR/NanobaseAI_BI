import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, FileSpreadsheet, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { Tabs } from '../budget/parts';
import { financeApi, fmtNum, fmtPct, fmtShort, type Meta, type ProfitBy, type ProfitRow } from './api';
import { Approx, DataEnd, Money, SumCard } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { xlsxUrl } from '../components/excel';

/** Kârlılık: kitap · seri · yayınevi · kanal · cari. Kesin katkı yalnız maliyeti işlenmiş satırlardan; yaklaşık katkı
 *  M9 birim maliyeti ve sözleşme oranından telifle, kapsamıyla birlikte. */

const SORTS: Array<[string, string]> = [['net', 'Net satış'], ['katki', 'Yaklaşık katkı'], ['marj', 'En düşük marj'], ['iskonto', 'İskonto oranı'], ['ad', 'Ad']];

function Row({ r, royalty, total }: { r: ProfitRow; royalty: boolean; total?: boolean }) {
  const cls = total ? 'border-t-2 border-slate-200 bg-slate-50/70 font-bold' : 'border-t border-slate-100';
  return (
    <tr className={cls}>
      <td className={td}>
        <div className="max-w-[36ch] truncate font-semibold" title={r.ad}>{r.ad}</div>
        {!total && r.key !== r.ad && <div className="font-mono text-[11px] text-canvas-muted">{r.key}</div>}
      </td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(r.adet)}</td>
      <td className={`${td} text-right`}><Money v={r.net} /></td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.iskontoOrani)}</td>
      <td className={`${td} text-right`}><Money v={r.katkiKesin} /></td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.marjKesin)}</td>
      <td className={`${td} text-right`}><Money v={r.maliyetsizNet} /></td>
      <td className={`${td} text-right`}><Money v={r.maliyetTahmini} /></td>
      {royalty && <td className={`${td} text-right`}>{r.telifsizNet && r.net && Math.abs(r.telifsizNet - r.net) < 0.01 ? <span className="text-[11px] text-canvas-muted">telif verisi yok</span> : <Money v={r.telif} />}</td>}
      <td className={`${td} text-right`}>
        <div className="flex items-center justify-end gap-1.5"><Money v={r.katkiYaklasik} strong />{r.yaklasik && <Approx />}</div>
      </td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.marjYaklasik)}</td>
      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.kapsam)}</td>
    </tr>
  );
}

export default function ProfitTab({ meta, year }: { meta: Meta; year: number }) {
  const [by, setBy] = useState<ProfitBy>('kitap');
  const [frm, setFrm] = useState(1);
  const [to, setTo] = useState(12);
  const [sort, setSort] = useState('net');
  const [text, setText] = useState('');
  const [page, setPage] = useState(0);
  const qtext = useDebounced(text, 300);
  const params = { by, year, frm, to: Math.max(frm, to), q: qtext, sort };
  const q = useQuery({ queryKey: ['finance', 'profit', params, page], queryFn: () => financeApi.profit({ ...params, page }), enabled: ENGINE_ENABLED });
  const d = q.data;
  const royalty = !!d?.telif.hesaplandi;
  const tabs = (Object.entries(meta.profitBy) as Array<[ProfitBy, string]>).map(([key, label]) => ({ key, label }));
  return (
    <div className="flex flex-col gap-3">
      <Tabs tabs={tabs} value={by} onChange={(k) => { setBy(k); setPage(0); }} />
      <Panel>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-[110px_110px_180px_1fr_auto] sm:items-end">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>İlk ay</span>
            <select className={field} value={frm} onChange={(e) => { setFrm(Number(e.target.value)); setPage(0); }}>
              {meta.months.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Son ay</span>
            <select className={field} value={to} onChange={(e) => { setTo(Number(e.target.value)); setPage(0); }}>
              {meta.months.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sıra</span>
            <select className={field} value={sort} onChange={(e) => { setSort(e.target.value); setPage(0); }}>
              {SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={text} onChange={(e) => { setText(e.target.value); setPage(0); }} placeholder="Ad ya da kod" />
            </span>
          </label>
          {meta.me.canExport && (
            <>
              <a className={`${btnGhost} col-span-2 sm:col-span-1`} href={financeApi.profitExportUrl(params)} download>
                <Download aria-hidden className="h-4 w-4" /> CSV
              </a>
              <a className={`${btnGhost} col-span-2 sm:col-span-1`} href={xlsxUrl(financeApi.profitExportUrl(params))} download>
                <FileSpreadsheet aria-hidden className="h-4 w-4" /> Excel
              </a>
            </>
          )}
        </div>
      </Panel>
      {q.isLoading ? <Loading /> : q.error ? <Note tone="err">{errText(q.error, 'Kârlılık okunamadı.')}</Note> : d && (
        <>
          <DataEnd data={d} extra={<span>Dönem {d.donem}</span>} />
          <Note tone="info">
            <strong>Kesin katkı</strong> = maliyeti Logo'da işlenmiş satışların net tutarı − Logo maliyeti. <strong>Yaklaşık katkı</strong> = maliyeti bilinen satış − Logo maliyeti −
            maliyeti işlenmemiş satışın fiyatlama ekranındaki birim maliyetiyle tahmini{royalty ? ' − telif' : ''}; kapsam, maliyeti (tahminle de olsa) bilinen satışın payıdır. Birim maliyeti de
            bilinmeyen satış hesaba katılmaz, uydurulmaz. {d.telif.kaynak}
            {royalty && <> Sözleşme oranı olan {fmtNum(d.telif.sozlesmeli)} kitap, olmayan {fmtNum(d.telif.sozlesmesiz)} kitap.<SqlInfo k={d.kaynaklar} alan="telif" label="Telif sözleşmesi sayıları" className="ml-0.5" /></>}
          </Note>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            <SumCard label="Net satış" value={fmtShort(d.toplam.net)} info={<SqlInfo k={d.kaynaklar} alan="toplam.net" label="Net satış (toplam)" />} />
            <SumCard label="Kesin marj" value={fmtPct(d.toplam.marjKesin)} info={<SqlInfo k={d.kaynaklar} alan="toplam.marjKesin" label="Kesin marj (toplam)" />} />
            <SumCard label={<>Yaklaşık marj <Approx /></>} value={fmtPct(d.toplam.marjYaklasik)} info={<SqlInfo k={d.kaynaklar} alan="toplam.marjYaklasik" label="Yaklaşık marj (toplam)" />} />
            <SumCard label="Maliyeti bilinmeyen satış" value={fmtShort(d.toplam.maliyetBilinmeyenNet)} info={<SqlInfo k={d.kaynaklar} alan="toplam.maliyetBilinmeyenNet" label="Maliyeti bilinmeyen satış" />} />
          </div>
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>{d.byLabel}</th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].adet">Net adet</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].net">Net satış</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].iskonto">İskonto</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].katkiKesin">Kesin katkı</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].marjKesin">Kesin marj</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].maliyetsizNet">Maliyetsiz satış</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].maliyetTahmini">Tahmini maliyet</InfoLabel></th>
                {royalty && <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].telif">Telif</InfoLabel></th>}
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].katkiYaklasik">Yaklaşık katkı</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].marjYaklasik">Yaklaşık marj</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="items[].kapsam">Kapsam</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((r) => <Row key={r.key} r={r} royalty={royalty} />)}
              <Row r={d.toplam} royalty={royalty} total />
            </tbody>
          </TableWrap>
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
        </>
      )}
    </div>
  );
}
