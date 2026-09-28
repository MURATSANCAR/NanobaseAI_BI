import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, errText, td, th } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { cellShade, commerceApi, fmtDay, fmtInt, fmtRatio, fmtTl, type Segment } from './api';
import { ROOT, SegmentPill, useMeta } from './parts';

/** RFM matrisi (yenilik × sıklık), segment büyüklüğü ve geçişleri; tıklanınca maskeli müşteri listesi. */
export default function Customers() {
  const [params, setParams] = useSearchParams();
  const segment = (params.get('segment') ?? '') as Segment | '';
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState('son');
  const meta = useMeta();
  const rfm = useQuery({ queryKey: ['commerce', 'rfm'], queryFn: () => commerceApi.rfm(30), enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({
    queryKey: ['commerce', 'customers', segment, page, sort],
    queryFn: () => commerceApi.customers(segment, page, sort),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });

  if (rfm.isLoading) return <Loading />;
  if (rfm.error) return <Note tone="err">{errText(rfm.error, 'Müşteri segmentleri açılamadı.')}</Note>;
  const r = rfm.data;
  if (!r) return null;
  const max = Math.max(0, ...r.matrix.map((m) => m.musteri));
  const cell = (ri: number, fi: number) => r.matrix.find((m) => m.r === ri && m.f === fi);
  const labels = meta.data?.segments;

  const pick = (s: Segment | '') => {
    setPage(0);
    const next = new URLSearchParams(params);
    if (s) next.set('segment', s);
    else next.delete('segment');
    setParams(next, { replace: true });
  };

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <div className="grid gap-3 lg:grid-cols-[1.3fr_1fr] lg:gap-4">
        <Panel>
          <h2 className="text-[15px] font-extrabold">Yenilik × sıklık</h2>
          <p className="mt-0.5 text-[11.5px] text-canvas-muted">Satır: son geçerli siparişten bu yana geçen gün. Sütun: geçerli sipariş sayısı. Hücrede müşteri sayısı.</p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[520px] border-separate border-spacing-1 text-[12px]">
              <thead>
                <tr><th className="text-left text-[11px] font-bold text-canvas-muted">Son sipariş</th>{r.cols.map((c) => <th key={c} className="text-center text-[11px] font-bold text-canvas-muted">{c}</th>)}</tr>
              </thead>
              <tbody>
                {r.rows.map((row, ri) => (
                  <tr key={row}>
                    <th scope="row" className="whitespace-nowrap pr-2 text-left text-[11.5px] font-bold">{row}</th>
                    {r.cols.map((_c, fi) => {
                      const v = cell(ri, fi);
                      const a = cellShade(v?.musteri ?? 0, max);
                      return (
                        <td key={fi} className="rounded-lg p-2 text-center" style={{ backgroundColor: `rgba(109, 40, 217, ${a * 0.55})` }}>
                          <div className={`font-mono font-bold tabular-nums ${a > 0.6 ? 'text-white' : 'text-canvas-ink'}`}>{fmtInt(v?.musteri ?? 0)}</div>
                          <div className={`text-[10.5px] ${a > 0.6 ? 'text-white/80' : 'text-canvas-muted'}`}>{v ? fmtTl(v.ciro) : ''}</div>
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11.5px] text-canvas-muted">
            Kural: son sipariş {r.rules.activeDays} günden eskiyse kayıp; {r.rules.loyalOrders}+ sipariş
            {r.rules.loyalRevenue ? ` ya da ${fmtTl(r.rules.loyalRevenue)} ciro` : ''} sadık; tek sipariş ilk alıcı; diğerleri aktif.
          </p>
        </Panel>
        <div className="flex flex-col gap-3 lg:gap-4">
          <Panel>
            <h2 className="text-[15px] font-extrabold">Segmentler</h2>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <button type="button" onClick={() => pick('')} aria-pressed={!segment}
                className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${!segment ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}>
                Hepsi
              </button>
              {r.segments.map((s) => (
                <button key={s.segment} type="button" onClick={() => pick(s.segment)} aria-pressed={segment === s.segment}
                  className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${segment === s.segment ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}>
                  {s.label} <span className="font-mono tabular-nums opacity-80">{fmtInt(s.musteri)}</span>
                </button>
              ))}
            </div>
          </Panel>
          <Panel>
            <h2 className="text-[15px] font-extrabold">Son {r.moves.days} günde segment geçişleri</h2>
            {r.moves.items.length === 0 ? (
              <p className="mt-1 text-[12.5px] text-canvas-muted">Geçiş yok.</p>
            ) : (
              <ul className="mt-2 divide-y divide-slate-100 text-[12.5px]">
                {r.moves.items.map((m) => (
                  <li key={`${m.from}-${m.to}`} className="flex items-center justify-between gap-2 py-1.5">
                    <span>{m.fromLabel} → <strong>{m.toLabel}</strong></span>
                    <span className="font-mono tabular-nums">{fmtInt(m.musteri)}</span>
                  </li>
                ))}
              </ul>
            )}
            {r.moves.kaybettigi.sadik > 0 && (
              <p className="mt-2 text-[11.5px] text-amber-800">Sadık segment bu dönemde {fmtInt(r.moves.kaybettigi.sadik)} müşteri kaybetti.</p>
            )}
          </Panel>
        </div>
      </div>

      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[15px] font-extrabold">{segment && labels ? `${labels[segment]} müşteriler` : 'Bütün müşteriler'}</h2>
          <label className="flex items-center gap-2 text-[12px] font-bold text-canvas-muted">
            Sırala
            <select value={sort} onChange={(e) => { setSort(e.target.value); setPage(0); }}
              className="min-h-11 rounded-xl border border-slate-200 bg-white px-2 text-base font-semibold sm:min-h-8 sm:text-[12.5px]">
              <option value="son">Son sipariş</option>
              <option value="ciro">Ciro</option>
              <option value="siparis">Sipariş sayısı</option>
            </select>
          </label>
        </div>
        <p className="mt-0.5 text-[11.5px] text-canvas-muted">Müşteri adı yok; «MÜ-» etiketi site müşterisinin özetinden türer. Kartta sipariş geçmişi ve izin.</p>
        {list.error && <div className="mt-2"><Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note></div>}
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr><th className={th}>Müşteri</th><th className={th}>Segment</th><th className={`${th} text-right`}>Sipariş</th><th className={`${th} text-right`}>Ciro</th><th className={th}>Son sipariş</th><th className={th}>İl</th></tr>
            </thead>
            <tbody>
              {(list.data?.items ?? []).map((c) => (
                <tr key={c.key} className="border-t border-slate-100">
                  <td className={td}>
                    <Link to={`${ROOT}/musteri/${c.key}`} className="font-mono font-bold text-canvas-violet hover:underline">{c.etiket}</Link>
                    <div className="text-[11px] text-canvas-muted">{c.uye ? 'Üye' : c.misafir ? 'Misafir' : ''}</div>
                  </td>
                  <td className={td}><SegmentPill segment={c.segment} label={c.segmentLabel} /></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.siparis)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtTl(c.ciro)}</td>
                  <td className={`${td} whitespace-nowrap`}>{fmtDay(c.sonSiparis)}</td>
                  <td className={td}>{c.il ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={page} pageSize={list.data?.pageSize ?? 50} total={list.data?.total ?? 0} shown={list.data?.items.length ?? 0}
            loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        </div>
        <p className="mt-1 text-[11.5px] text-canvas-muted">Segment payları: {r.segments.map((s) => `${s.label} ${fmtRatio(s.pay, 0)}`).join(' · ')}</p>
      </Panel>
    </div>
  );
}
