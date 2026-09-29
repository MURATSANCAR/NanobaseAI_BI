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
import { EmptyHint, Explain } from '../../components/Explain';

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
          <Explain label="Stok farkı türleri" title="Farklar ne demek?">
            <span className="block"><b>Trendyol'da satışta, depoda yok:</b> ürün satışa açık, Trendyol'da stok var ama Logo depo stoğu bitmiş. Sipariş gelirse iptal etmek zorunda kalırsınız.</span>
            <span className="block"><b>Depoda var, Trendyol'da kapalı:</b> depoda yeterli stok var ama ürün Trendyol'da kapalı ya da stoğu 0; satış kaçıyor.</span>
            <span className="block"><b>Trendyol stoğu depodan fazla:</b> Trendyol'a girilen stok, depodaki adetten yüksek.</span>
            <span className="block"><b>Barkod Logo'da bulunamadı:</b> ürünün barkodu Logo'daki hiçbir kitaba bağlanamadı.</span>
          </Explain>
          <SqlInfo k={d?.kaynaklar} alan="items" label="Sekme sayıları" /></div>
        <ExportLink show={canExport} href={trendyolApi.exportUrl('stok-farki', { fark, q })} />
      </div>
      {r.error && <Note tone="err">{errText(r.error, 'Liste açılamadı.')}</Note>}
      {r.isLoading ? <Loading /> : d && (d.urunSayisi === 0 ? (
        <EmptyHint title="Ürün listesi yüklenmedi" why="Trendyol satıcı panelinden ürün listesini Excel olarak indirip «Dosya yükle» sekmesinde «Ürün listesi» türüyle yükleyin." />
      ) : !d.items.length ? (
        <EmptyHint title={fark || q ? 'Bu süzgeçte fark yok' : 'Stok farkı yok'} why={fark || q ? 'Başka bir fark türü seçin ya da aramayı temizleyin.' : 'Yüklenen ürün listesindeki bütün ürünlerin Trendyol stoğu depoyla uyumlu.'} />
      ) : (
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
          Trendyol satış fiyatı, Logo'daki liste fiyatı ve sitedeki fiyatla kıyaslanır; fiyatlar KDV dahildir. «Eşik altında»: Trendyol fiyatı liste fiyatının %{Math.round(d.esik * 100)}'inden fazla altında.
          {d.listeKdv ? ` KDV hariç liste fiyatı %${Math.round(d.listeKdv * 100)} ile brütlenir.` : ' KDV hariç liste fiyatı brütlenmez (oran Yönetim ayarında).'}
          {!d.maliyetBagli && ' Birim maliyet bu rolde ya da kurulumda görünmüyor.'}
        </p>
      )}
      {r.error && <Note tone="err">{errText(r.error, 'Liste açılamadı.')}</Note>}
      {r.isLoading ? <Loading /> : d && (!d.items.length ? (
        <EmptyHint title={isaret || q ? 'Bu süzgeçte ürün yok' : 'İşaretlenen fiyat yok'} why={isaret || q ? 'Başka bir işaret seçin ya da aramayı temizleyin.' : 'Ürün listesi yüklenmemiş olabilir ya da bütün Trendyol fiyatları liste ve site fiyatıyla uyumlu.'} />
      ) : (
        <>
          <TableWrap>
            <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Trendyol</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Liste</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Site</InfoLabel></th><th className={`${th} text-right`}><span className="inline-flex items-center gap-1"><InfoLabel k={d?.kaynaklar} alan="items">İndirim</InfoLabel><Explain label="İndirim">Trendyol fiyatının liste fiyatından ne kadar düşük olduğu: 1 − Trendyol fiyatı ÷ liste fiyatı. Eksi değer, Trendyol fiyatının listeden yüksek olduğunu gösterir.</Explain></span></th>{d.maliyetBagli && <th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items">Birim maliyet</InfoLabel></th>}<th className={th}>İşaret</th></tr></thead>
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
      ))}
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
      {r.error && <Note tone="err">{errText(r.error, 'Liste açılamadı.')}</Note>}
      {r.isLoading ? <Loading /> : d && (!d.items.length ? (
        <EmptyHint title={durum || q ? 'Bu süzgeçte ürün yok' : 'Ürün listesi yüklenmedi'} why={durum || q ? 'Başka bir durum seçin ya da aramayı temizleyin.' : 'Trendyol satıcı panelinden ürün listesini indirip «Dosya yükle» sekmesinde yükleyin.'} />
      ) : (
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
      ))}
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
      lead="Trendyol'da satışta görünüp depoda olmayan, depoda olup Trendyol'da kapalı kitaplar ve liste ya da site fiyatından sapan Trendyol fiyatları. Düzeltmeyi Trendyol panelinden siz yaparsınız; buradan mağazaya bir şey gönderilmez."
      aside={<label className="flex flex-col gap-1"><span className="sr-only">Ara</span><input className={field} placeholder="Ara: kitap adı, barkod ya da stok kodu" value={text} onChange={(e) => setText(e.target.value)} /></label>}
    >
      <TrendyolData meta={m} />
      <Tabs value={tab} onChange={setTab} tabs={[{ key: 'stok', label: 'Stok farkı' }, { key: 'fiyat', label: 'Fiyat farkı' }, { key: 'hepsi', label: 'Bütün ürünler' }]} />
      {tab === 'stok' && <StockDiff q={q} canExport={canExport} />}
      {tab === 'fiyat' && <PriceDiff q={q} canExport={canExport} />}
      {tab === 'hepsi' && <AllProducts q={q} canExport={canExport} />}
    </TrendyolFrame>
  );
}
