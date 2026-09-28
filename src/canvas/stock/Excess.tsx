import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, errText } from '../admin/ui';
import { Kpi, KpiRow, Pager, Panel } from '../editorial/kit';
import { fmtDay } from '../budget/api';
import { n0, stockApi, tl, type Item } from './api';
import ItemList from './ItemList';
import { Chips, DataDay, Empty, ExportLink, Loading, SourcesButton, StockFrame } from './parts';
import { RULES } from './rules';
import { SuggestionActions } from './decisions';

/** Fazla ve hareketsiz stok (/stok/fazla): Zeki AI eritme yönü (kampanya → M35/M17, set → M53, bekle) önerir; karar
 *  insanın. İmha/iade kararı bu ekranda verilmez. */

type Tur = '' | 'fazla' | 'olu' | 'satissiz';
const TABS: Array<{ key: Tur; label: string }> = [
  { key: '', label: 'Hepsi' },
  { key: 'fazla', label: 'Fazla stok' },
  { key: 'olu', label: 'Hareketsiz' },
  { key: 'satissiz', label: 'Satışı yok' },
];

export default function Excess() {
  const [params, setParams] = useSearchParams();
  const tur = (params.get('tur') ?? '') as Tur;
  const sayfa = Number(params.get('sayfa') ?? 0) || 0;
  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'sayfa') p.delete('sayfa');
    setParams(p, { replace: true });
  };
  const meta = useQuery({ queryKey: ['stock', 'meta'], queryFn: stockApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['stock', 'excess', tur, sayfa], queryFn: () => stockApi.excess({ tur, sayfa }), enabled: ENGINE_ENABLED, placeholderData: (p) => p });
  const d = q.data;
  const me = meta.data?.me;
  const action = (i: Item) =>
    i.oneri ? (
      <div className="max-w-[340px] text-left text-[11.5px]">
        <div className="font-bold">{i.oneri.hedefEtiket ?? 'Öneri'}</div>
        <div className="text-canvas-muted">{i.oneri.gerekce}</div>
        <SuggestionActions
          s={{ id: i.oneri.id, tur: 'fazla', turEtiket: '', stokKodu: i.stokKodu, veri: {}, gerekce: i.oneri.gerekce, durum: 'acik', durumEtiket: '',
            hedef: i.oneri.hedef, hedefEtiket: i.oneri.hedefEtiket, kararVeren: null, kararTarihi: null, kararNotu: null, olusturma: null }}
          canDecide={!!me?.canDecide}
        />
      </div>
    ) : (
      <span className="text-[11.5px] text-canvas-muted">Öneri gece üretilir</span>
    );

  return (
    <StockFrame
      crumb="Fazla stok"
      title="Fazla ve hareketsiz stok"
      lead="Stoğu çok uzun yetecek, pencerede hiç hareket görmeyen ya da satışı olmayan kitaplar. Zeki AI her kitap için eritme yönü önerir; kampanya ve set kararı ilgili ekiptedir."
      source={d?.veriSonu ? `Logo · ${fmtDay(d.veriSonu)}` : 'Logo + CRM'}
      aside={
        <>
          <SourcesButton rules={RULES} />
          <ExportLink show={!!me?.canExport} href={stockApi.exportUrl('fazla', { tur })} />
        </>
      }
    >
      <DataDay day={d?.veriSonu} extra={d?.hareketPenceresi ? `Hareket penceresi ${fmtDay(d.hareketPenceresi[0])} – ${fmtDay(d.hareketPenceresi[1])}.` : undefined} />
      {d && (
        <KpiRow>
          <Kpi label="Kitap" value={n0(d.total)} help="Seçili türde" />
          <Kpi label="Toplam adet" value={n0(d.toplamAdet)} help="Logo stoğu" />
          <Kpi label="Fazla stok eşiği" value={`${n0(d.fazlaGun)} gün`} help="Bundan uzun yeten stok" />
          {d.deger ? (
            <Kpi label="Stok değeri" value={tl(d.deger.toplam)} help={`${n0(d.deger.maliyetli)} kitap maliyetli · ${n0(d.deger.maliyetsiz)} kitapta maliyet yok`} />
          ) : (
            <Kpi label="Stok değeri" value="—" help="Maliyet yetkisiyle görünür" />
          )}
        </KpiRow>
      )}
      <Panel>
        <div className="mb-3">
          <Chips<Tur> label="Tür" items={TABS} value={tur} onChange={(k) => set('tur', k || null)} />
        </div>
        {q.error && <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>}
        {q.isLoading && <Loading what="Fazla stok" />}
        {d && !d.items.length && <Empty>Bu türde kitap yok.</Empty>}
        {!!d?.items.length && <ItemList items={d.items} cols={['bakiye', 'hiz', 'gun', 'devir', 'sonHareket', 'net12', 'durum', 'deger']} action={action} />}
        {d && <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={(p) => set('sayfa', String(p))} />}
      </Panel>
    </StockFrame>
  );
}
