import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Note, TableWrap, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Pager, useDebounced } from '../../editorial/kit';
import { fmtInt, fmtShort } from '../../budget/api';
import { setsApi } from './api';
import { Tone } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';

/** Promosyon ürünleri: Logo'da 157 önekli ticari ürünler + CRM promosyon / pazarlama materyali kartları; stok ve satış. */
export default function PromoItemsTab() {
  const [stok, setStok] = useState('');
  const [tur, setTur] = useState('');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q.trim(), 300);
  const res = useQuery({
    queryKey: ['sets', 'promo', stok, tur, dq, page],
    queryFn: () => setsApi.promo({ stok, tur, q: dq, page }),
    placeholderData: keepPreviousData,
  });
  const s = res.data?.summary;
  return (
    <>
      {s && (
        <KpiRow>
          <Kpi label="Ürün" value={fmtInt(s.toplam)} help="Ticari ürünler ve CRM promosyon kartları" active={!stok && !tur}
            onClick={() => { setStok(''); setTur(''); setPage(0); }} info={<SqlInfo k={res.data?.kaynaklar} alan="summary" label="Ürün" />}
            explain="Kitap dışındaki tanıtım ve hediye ürünleri: Logo'daki ticari ürünler ile CRM'deki promosyon ve pazarlama materyali kartları." />
          <Kpi label="Stoğu yok" value={fmtInt(s.stokYok)} help="Logo stok bakiyesi sıfır ya da altı" active={stok === '0'}
            onClick={() => { setStok('0'); setPage(0); }} info={<SqlInfo k={res.data?.kaynaklar} alan="summary" label="Stoğu yok" />} />
          <Kpi label="Ticari ürün" value={fmtInt(s['157'])} help="Kitap satış raporlarına girmeyen ürünler" active={tur === '157'}
            onClick={() => { setTur('157'); setPage(0); }} info={<SqlInfo k={res.data?.kaynaklar} alan="summary" label="Ticari ürün" />}
            explain="Logo'da stok kodu 157 ile başlayan, kitap olmayan ürünler. Kitap satışı raporlarından ayrı tutulur." />
          <Kpi label="Ticari ürün cirosu (12 ay)" value={fmtShort(s.son12Ciro)} help="Faturalı satış, iade düşülmüş" info={<SqlInfo k={res.data?.kaynaklar} alan="summary" label="Ticari ürün cirosu (12 ay)" />} />
        </KpiRow>
      )}
      <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_180px_220px]">
          <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
            <span className={labelCls}>Ara</span>
            <input className={field} value={q} placeholder="Ürün adı ya da stok kodu" onChange={(e) => { setQ(e.target.value); setPage(0); }} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Stok</span>
            <select className={field} value={stok} onChange={(e) => { setStok(e.target.value); setPage(0); }}>
              <option value="">Hepsi</option>
              <option value="0">Stoğu yok</option>
              <option value="1">Stokta</option>
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Tür</span>
            <select className={field} value={tur} onChange={(e) => { setTur(e.target.value); setPage(0); }}>
              <option value="">Hepsi</option>
              <option value="157">Ticari ürün (Logo)</option>
              <option value="crm-promosyon">CRM promosyon kartı</option>
              <option value="crm-pazarlama-materyali">CRM pazarlama materyali</option>
            </select>
          </label>
        </div>
      </section>
      {res.error && <Note tone="err">{errText(res.error, 'Promosyon ürünleri okunamadı.')}</Note>}
      {res.data && (
        <section>
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Ürün</th>
                <th className={th}>Tür</th>
                <th className={`${th} text-right`}><InfoLabel k={res.data?.kaynaklar} alan="items[]">Logo stoku</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={res.data?.kaynaklar} alan="items[]">12 ay adet</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={res.data?.kaynaklar} alan="items[]">12 ay ciro</InfoLabel></th>
              </tr>
            </thead>
            <tbody>
              {res.data.items.map((r) => (
                <tr key={r.stok} className="border-b border-slate-50 last:border-0">
                  <td className={td}><span className="font-semibold">{r.ad ?? r.stok}</span><div className="text-[11px] text-canvas-muted">{r.stok}{r.promosyonTipi ? ` · ${r.promosyonTipi}` : ''}</div></td>
                  <td className={td}><Tone tone={r.tur === '157' ? 'muted' : 'violet'}>{r.turAdi}</Tone></td>
                  <td className={`${td} text-right font-mono tabular-nums ${(r.stokAdet ?? 0) <= 0 ? 'font-bold text-red-700' : ''}`}>
                    {r.stokAdet === null ? 'Logo kartı yok' : fmtInt(r.stokAdet)}
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.son12Adet)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtShort(r.son12Ciro)}</td>
                </tr>
              ))}
              {!res.data.items.length && <tr><td className={`${td} text-canvas-muted`} colSpan={5}>Bu süzgeçte ürün yok. Aramayı temizleyin ya da stok ve tür süzgeçlerini «Hepsi» yapın.</td></tr>}
            </tbody>
          </TableWrap>
          <Pager page={res.data.page} pageSize={res.data.pageSize} total={res.data.total} shown={res.data.items.length}
            loading={res.isLoading} fetching={res.isFetching} onPage={setPage} />
          <p className="mt-2 px-1 text-[11.5px] text-canvas-muted">
            Satış penceresi {res.data.window[0]} – {res.data.window[1]}. Bedelsiz çıkış (tanıtım gönderimi) ölçüm yöntemi belirlenince eklenecek.
          </p>
        </section>
      )}
    </>
  );
}
