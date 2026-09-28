import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, TableWrap, errText, field, td, th } from '../../admin/ui';
import { Pager, Panel, useDebounced } from '../../editorial/kit';
import { fmtInt, fmtPct } from '../../budget/api';
import { Tabs } from '../../budget/parts';
import { BookCell, Chips, ExportLink, yesNo } from '../platformKit';
import { trendyolApi } from './api';
import { TrendyolData, TrendyolFrame, tl, useTrendyolMeta } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';

type Tab = 'stok' | 'fiyat' | 'hepsi';

function StockDiff({ q, canExport }: { q: string; canExport: boolean }) {
  const [fark, setFark] = useState('');
  const [page, setPage] = useState(0);
  const r = useQuery({ queryKey: ['trendyol', 'stock', fark, q, page], queryFn: () => trendyolApi.stockDiff({ fark, q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const d = r.data;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1"><Chips value={fark} onChange={(v) => { setFark(v); setPage(0); }}
          items={[{ key: '', label: 'Bütün farklar' }, ...Object.entries(d?.labels ?? {}).map(([k, v]) => ({ key: k, label: v, count: d?.counts[k] }))]} />
          <SqlInfo k={d?.kaynaklar} alan="items" label="Sekme sayıları" /></div>
        <ExportLink show={canExport} href={trendyolApi.exportUrl('stok-farki', { fark, q })} />
      </div>
      {r.error && <Note tone="err">{errText(r.error, 'Liste açılamadı.')}</Note>}
      {r.isLoading ? <Loading /> : d && (d.urunSayisi === 0 ? <Note tone="info">Ürün listesi yüklenmedi (Dosya yükle → Ürün listesi).</Note> : (
        <>
          <TableWrap>
            <thead><tr><th className={th}>Kitap</th><th className={th}>Fark</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Trendyol stoğu</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Depo stoğu</InfoLabel></th><th className={th}>Trendyol durumu</th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.barkod} className="border-t border-slate-100">
                  <td className={td}><BookCell name={x.ad} code={x.stokKodu} sub={x.barkod} /></td>
                  <td className={`${td} text-[12px] font-semibold`}>{x.fark ? d.labels[x.fark] : '—'}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.trendyolStok)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.depoStok)}</td>
                  <td className={td}>{x.durum ?? yesNo(x.satisaAcik)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
        </>
      ))}
    </Panel>
  );
}

function PriceDiff({ q, canExport }: { q: string; canExport: boolean }) {
  const [isaret, setIsaret] = useState('');
  const [page, setPage] = useState(0);
  const r = useQuery({ queryKey: ['trendyol', 'price', isaret, q, page], queryFn: () => trendyolApi.priceDiff({ isaret, q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const d = r.data;
  const labels = Object.entries(d?.labels ?? {}).filter(([k]) => k !== 'maliyet-alti' || d?.maliyetBagli);
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1"><Chips value={isaret} onChange={(v) => { setIsaret(v); setPage(0); }}
          items={[{ key: '', label: 'Bütün işaretliler' }, ...labels.map(([k, v]) => ({ key: k, label: v, count: d?.counts[k] }))]} />
          <SqlInfo k={d?.kaynaklar} alan="items" label="Sekme sayıları" /></div>
        <ExportLink show={canExport} href={trendyolApi.exportUrl('fiyat-farki', { isaret, q })} />
      </div>
      {d && (
        <p className="mb-2 text-[12px] text-canvas-muted">
          Fiyatlar KDV dahil kıyaslanır. Eşik: liste fiyatının %{Math.round(d.esik * 100)}'inden fazla altı.
          {d.listeKdv ? ` KDV hariç liste fiyatı %${Math.round(d.listeKdv * 100)} ile brütlenir.` : ' KDV hariç liste fiyatı brütlenmez (oran Yönetim ayarında).'}
          {!d.maliyetBagli && ' Birim maliyet bu rolde ya da kurulumda görünmüyor.'}
        </p>
      )}
      {r.error && <Note tone="err">{errText(r.error, 'Liste açılamadı.')}</Note>}
      {r.isLoading ? <Loading /> : d && (
        <>
          <TableWrap>
            <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Trendyol</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Liste</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Site</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">İndirim</InfoLabel></th>{d.maliyetBagli && <th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Birim maliyet</InfoLabel></th>}<th className={th}>İşaret</th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.barkod} className="border-t border-slate-100">
                  <td className={td}><BookCell name={x.ad} code={x.stokKodu} sub={x.barkod} /></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{tl(x.trendyolFiyat)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{tl(x.listeFiyat)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{tl(x.siteFiyat)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(x.indirim)}</td>
                  {d.maliyetBagli && <td className={`${td} text-right font-mono tabular-nums`}>{tl(x.birimMaliyet)}</td>}
                  <td className={`${td} text-[12px]`}>{x.isaret.map((k) => d.labels[k]).join(' · ')}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
        </>
      )}
    </Panel>
  );
}

function AllProducts({ q, canExport }: { q: string; canExport: boolean }) {
  const [durum, setDurum] = useState('');
  const [page, setPage] = useState(0);
  const r = useQuery({ queryKey: ['trendyol', 'products', durum, q, page], queryFn: () => trendyolApi.products({ durum, q, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const d = r.data;
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1"><Chips value={durum} onChange={(v) => { setDurum(v); setPage(0); }} items={[{ key: '', label: 'Hepsi' }, { key: 'acik', label: 'Satışta' }, { key: 'kapali', label: 'Kapalı' }]} />
          <SqlInfo k={d?.kaynaklar} alan="items" label="Sekme sayıları" /></div>
        <ExportLink show={canExport} href={trendyolApi.exportUrl('urunler', { durum, q })} />
      </div>
      {r.isLoading ? <Loading /> : d && (
        <>
          <TableWrap>
            <thead><tr><th className={th}>Kitap</th><th className={th}>Satışta</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Trendyol stoğu</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Depo stoğu</InfoLabel></th></tr></thead>
            <tbody>
              {d.items.map((x) => (
                <tr key={x.barkod} className="border-t border-slate-100">
                  <td className={td}><BookCell name={x.ad} code={x.stokKodu} sub={x.barkod} /></td>
                  <td className={td}>{yesNo(x.satisaAcik)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.trendyolStok)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.depoStok)}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={r.isLoading} fetching={r.isFetching} onPage={setPage} />
        </>
      )}
    </Panel>
  );
}

export default function TrendyolProducts() {
  const meta = useTrendyolMeta();
  const m = meta.data;
  const [tab, setTab] = useState<Tab>('stok');
  const [text, setText] = useState('');
  const q = useDebounced(text, 300);
  const canExport = !!m?.me.canExport;
  return (
    <TrendyolFrame
      title="Ürün, stok ve fiyat"
      lead="Trendyol'da satışta görünüp depoda olmayan, depoda olup Trendyol'da kapalı kitaplar ve liste/site fiyatından sapan Trendyol fiyatları. Mağazada düzeltmeyi kişi yapar."
      aside={<label className="flex flex-col gap-1"><span className="sr-only">Ara</span><input className={field} placeholder="Kitap adı, barkod ya da stok kodu" value={text} onChange={(e) => setText(e.target.value)} /></label>}
    >
      <TrendyolData meta={m} />
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'stok', label: 'Stok farkı' }, { key: 'fiyat', label: 'Fiyat farkı' }, { key: 'hepsi', label: 'Bütün ürünler' }]} />
      {tab === 'stok' && <StockDiff q={q} canExport={canExport} />}
      {tab === 'fiyat' && <PriceDiff q={q} canExport={canExport} />}
      {tab === 'hepsi' && <AllProducts q={q} canExport={canExport} />}
    </TrendyolFrame>
  );
}
