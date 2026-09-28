import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, errText } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { fmtDay } from '../budget/api';
import { stockApi, type DiffClass } from './api';
import SqlInfo from '../components/SqlInfo';
import ItemList from './ItemList';
import { Chips, DataDay, Empty, ExportLink, Loading, SourcesButton, StockFrame } from './parts';
import { RULES } from './rules';

/** Logo–CRM farkı (/stok/fark): kitap başına CRM raf kalanı − Logo stok ve kök neden. Tek sayı gösterilmez; iki kaynak
 *  yan yana, fark gizlenmez. Açıklanamayan fark döngüsel sayım listesine alınır (Excel). */

export default function StockDiff() {
  const [params, setParams] = useSearchParams();
  const sinif = (params.get('sinif') ?? '') as '' | DiffClass;
  const sayfa = Number(params.get('sayfa') ?? 0) || 0;
  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'sayfa') p.delete('sayfa');
    setParams(p, { replace: true });
  };
  const meta = useQuery({ queryKey: ['stock', 'meta'], queryFn: stockApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['stock', 'diff', sinif, sayfa], queryFn: () => stockApi.diff({ sinif, sayfa }), enabled: ENGINE_ENABLED, placeholderData: (p) => p });
  const d = q.data;
  const all = d?.siniflar.reduce((a, s) => a + s.adet, 0) ?? null;

  return (
    <StockFrame
      crumb="Logo–CRM farkı"
      title="Logo–CRM stok farkı"
      lead="Logo’daki finansal stok ile CRM’deki raf stoğu kitap bazında yan yana. Logo’ya aktarılmamış hareket farkı açıklıyorsa neden odur; açıklanamayan fark sayım adayıdır."
      source={d?.veriSonu ? `Logo · ${fmtDay(d.veriSonu)} · CRM canlı` : 'Logo + CRM'}
      aside={
        <>
          <SourcesButton rules={RULES} />
          <ExportLink show={!!meta.data?.me.canExport} href={stockApi.exportUrl('fark', { sinif })} />
        </>
      }
    >
      <DataDay day={d?.veriSonu} extra={d?.not} />
      <Panel>
        <div className="mb-3 flex items-center gap-1">
          <div className="min-w-0 flex-1">
          <Chips<'' | DiffClass>
            label="Kök neden"
            items={[{ key: '', label: 'Hepsi', count: all }, ...(d?.siniflar ?? []).map((s) => ({ key: s.key, label: s.label, count: s.adet }))]}
            value={sinif}
            onChange={(k) => set('sinif', k || null)}
          />
          </div>
          <SqlInfo k={d?.kaynaklar} alan="siniflar" label="Kök neden sayaçları" />
        </div>
        {q.error && <Note tone="err">{errText(q.error, 'Fark okunamadı.')}</Note>}
        {q.isLoading && <Loading what="Logo ve CRM stoğu" />}
        {d && !d.items.length && <Empty>Bu sınıfta farklı kitap yok.</Empty>}
        {!!d?.items.length && <ItemList k={d.kaynaklar} items={d.items} cols={['bakiye', 'crmRaf', 'fark', 'aktarim']} />}
        {d && <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={(p) => set('sayfa', String(p))} />}
      </Panel>
    </StockFrame>
  );
}
