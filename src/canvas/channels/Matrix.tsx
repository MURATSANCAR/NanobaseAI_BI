import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, errText, field, td, th } from '../admin/ui';
import { Panel, Pager, useDebounced } from '../editorial/kit';
import { fmtInt } from '../budget/api';
import { channelsApi } from './api';
import { ChannelsFrame, DataBar, PeriodPicker, useChannelsMeta, usePeriod } from './parts';

/** M42 kitap × kanal matrisi (/kanallar/matris): satır kitap, sütun platform; hücrede net adet (kanala satış − iade), altında
 * alım ve iade. Sütun başlığına basınca o kanala göre sıralanır. */

export default function Matrix() {
  const meta = useChannelsMeta();
  const m = meta.data;
  const { yil, ay, set, params } = usePeriod(m);
  const [q, setQ] = useState(params.get('q') ?? '');
  const [page, setPage] = useState(0);
  const sort = params.get('sirala') ?? '';
  const dq = useDebounced(q, 300);
  const r = useQuery({
    queryKey: ['channels', 'matrix', yil, ay, dq, page, sort],
    queryFn: () => channelsApi.matrix({ yil, ay, q: dq, page, sort }),
    enabled: ENGINE_ENABLED && !!m && !!yil && !!m.years.length,
    placeholderData: keepPreviousData,
  });
  const d = r.data;
  return (
    <ChannelsFrame
      title="Kitap × kanal"
      lead="Hangi kanal hangi kitabı alıyor, hangisi iade ediyor. Net adet = kanala satış − kanaldan iade (Logo faturalı satırları); kanalın son tüketiciye sattığı değil."
      aside={
        <div className="flex flex-col gap-2">
          <PeriodPicker meta={m} yil={yil} ay={ay} onChange={set} />
          {m?.me.canExport && d && (
            <a className={btnGhost} href={channelsApi.exportUrl('matris', { yil, ay, q: dq || undefined })} download>
              <Download aria-hidden className="h-4 w-4" />
              Matrisi indir
            </a>
          )}
        </div>
      }
    >
      <DataBar meta={m} yil={yil} />
      <Panel>
        <input className={`${field} mb-3`} placeholder="Kitap adı ya da stok kodu" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} aria-label="Kitap ara" />
        {r.isLoading ? <Loading /> : r.error ? <Note tone="err">{errText(r.error, 'Matris hesaplanamadı.')}</Note> : !d?.items.length ? (
          <Note tone="info">Kayıt yok.</Note>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-slate-100 bg-white/80">
            <table className="w-full min-w-[720px] text-[12px]">
              <thead>
                <tr>
                  <th className={`${th} sticky left-0 z-10 bg-white`}>Kitap</th>
                  <th className={`${th} text-right`}>
                    <button type="button" className={`min-h-9 font-bold uppercase ${!sort ? 'text-canvas-violet' : ''}`} onClick={() => { set({ sirala: null }); setPage(0); }}>Toplam</button>
                  </th>
                  {d.columns.map((c) => (
                    <th key={c.platform} className={`${th} text-right`}>
                      <button type="button" className={`min-h-9 font-bold uppercase ${sort === c.platform ? 'text-canvas-violet' : ''}`}
                        onClick={() => { set({ sirala: c.platform }); setPage(0); }} title={`${c.label} net adedine göre sırala`}>
                        {c.label}
                      </button>
                      <div className="font-mono text-[10.5px] normal-case tabular-nums">{fmtInt(c.net)}</div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {d.items.map((row) => (
                  <tr key={row.stokKodu} className="border-t border-slate-100">
                    <td className={`${td} sticky left-0 z-10 max-w-[260px] bg-white`}>
                      <div className="font-semibold">{row.ad || row.stokKodu}</div>
                      <div className="font-mono text-[11px] text-canvas-muted">{row.stokKodu}</div>
                    </td>
                    <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtInt(row.toplam)}</td>
                    {d.columns.map((c) => {
                      const v = row.kanallar[c.platform];
                      return (
                        <td key={c.platform} className={`${td} text-right font-mono tabular-nums`}>
                          {v ? (
                            <>
                              <div className={v.net < 0 ? 'text-red-700' : ''}>{fmtInt(v.net)}</div>
                              {v.iade > 0 && <div className="text-[10.5px] text-canvas-muted">{fmtInt(v.alim)} − {fmtInt(v.iade)}</div>}
                            </>
                          ) : <span className="text-canvas-muted">—</span>}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {d && <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />}
        <p className="mt-2 text-[11.5px] text-canvas-muted">
          Kanal kartındaki ayrıntı için <Link to="/kanallar" className="font-bold text-canvas-violet underline-offset-2 hover:underline">Kanal karnesi</Link>. Eşlenmemiş e-ticaret carileri ayrı sütundur.
        </p>
      </Panel>
    </ChannelsFrame>
  );
}
