import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, TableWrap, errText, field, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtDay, fmtInt } from '../../budget/api';
import { BookCell, ExportLink } from '../platformKit';
import { amazonApi } from './api';
import { AmazonData, AmazonFrame, tl, useAmazonMeta } from './parts';

export default function AmazonConsignment() {
  const meta = useAmazonMeta();
  const m = meta.data;
  const [page, setPage] = useState(0);
  const [text, setText] = useState('');
  const q = useDebounced(text, 300);
  const r = useQuery({ queryKey: ['amazon', 'consignment', q, page], queryFn: () => amazonApi.consignment({ q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData, retry: false });
  const d = r.data;
  return (
    <AmazonFrame
      title="Amazon konsinye"
      lead="Onaylı Amazon carilerine faturalanmamış satış irsaliyesi eksi faturalanmamış iade irsaliyesi: konsinyede kalan adet, kitap bazında. Faturalanan kısım kanal karnesindedir."
      aside={<input className={field} placeholder="Kitap ya da stok kodu" value={text} onChange={(e) => setText(e.target.value)} />}
    >
      <AmazonData meta={m} />
      {r.error && <Note tone="info">{errText(r.error, 'Konsinye açılamadı.')}</Note>}
      {r.isLoading && <Loading />}
      {d && (
        <>
          {!d.eslenenCariler.length && <Note tone="warn">Amazon'a onaylanmış cari yok; konsinye hesaplanamaz. Özet sayfasındaki Amazon carilerini eşleyin.</Note>}
          <KpiRow>
            <Kpi label="Konsinyede kalan" value={fmtInt(d.toplam?.kalan ?? 0)} help={`${fmtInt(d.toplam?.kitap ?? 0)} kitap`} />
            <Kpi label="Faturalanmamış sevk" value={fmtInt(d.toplam?.sevk ?? 0)} help={`İrsaliye tutarı ${tl(d.toplam?.sevkTutar ?? 0)}`} />
            <Kpi label="Faturalanmamış iade" value={fmtInt(d.toplam?.iade ?? 0)} help="Satış iade irsaliyesi (ayrıca gösterilir)" />
            <Kpi label="Kapsam" value={(d.yillar ?? []).join(', ') || '—'} help={`Onaylı cari: ${d.eslenenCariler.join(', ') || '—'}`} />
          </KpiRow>
          <Panel>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[12px] text-canvas-muted">«Bu yıl faturalanan» = aynı yıl Amazon carilerine faturalı net adet (kanal karnesi önbelleği{d.faturalananBagli ? '' : '; henüz okunmadı'}).</p>
              <ExportLink show={!!m?.me.canExport} href={amazonApi.exportUrl('konsinye', { q })} />
            </div>
            <TableWrap>
              <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}>Sevk</th><th className={`${th} text-right`}>İade</th><th className={`${th} text-right`}>Kalan</th><th className={`${th} text-right`}>Bu yıl faturalanan</th><th className={th}>İrsaliye aralığı</th></tr></thead>
              <tbody>
                {d.items.map((x) => (
                  <tr key={x.stokKodu} className="border-t border-slate-100">
                    <td className={td}><BookCell name={x.ad} code={x.stokKodu} /></td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.sevk)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.iade)}</td>
                    <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtInt(x.kalan)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.faturalanan)}</td>
                    <td className={`${td} text-[12px]`}>{fmtDay(x.ilk)} – {fmtDay(x.son)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
          </Panel>
        </>
      )}
    </AmazonFrame>
  );
}
