import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, errText, field, label as labelCls } from '../admin/ui';
import { Kpi, KpiRow, Panel, Pager, useDebounced } from '../editorial/kit';
import { ecomApi, fmtInt, fmtPct, type Item, type Meta } from './api';
import { EticaretFrame } from './parts';
import ItemDrawer from './ItemDrawer';

/** M34 Huni: sitedeki görüntülenme → satış. «Düşük dönüşüm» çok bakılıp az satan kitaplardır; kartı iyileştirilecek ilk
 *  kitaplar bunlar. Olası nedenler veriden kurallı okunur (kart doluluğu, yorum, stok, fiyat). */
export default function FunnelScreen() {
  const meta = useQuery({ queryKey: ['eticaret', 'meta'], queryFn: ecomApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  return (
    <EticaretFrame
      title="Huni: görüntülenme → satış"
      lead="Sitedeki ürün sayaçları (tüm zamanlar) ve Logo'daki son dönem satışı. Çok görüntülenip az satan kitabın kartı önce iyileştirilir: kitabı açın, eksik alanlara bakın, Zeki AI'dan kart önerisi isteyin."
      source="Kaynak: site ürün sayaçları · Logo (kesim tarihiyle)"
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {meta.data && <Body meta={meta.data} />}
    </EticaretFrame>
  );
}

const SORTS = [
  { key: 'goruntulenme', label: 'Görüntülenme' },
  { key: 'satis', label: 'Site satışı' },
  { key: 'donusum', label: 'Dönüşüm (düşükten)' },
  { key: 'logo', label: 'Logo son dönem satışı' },
] as const;

function Body({ meta }: { meta: Meta }) {
  const [params, setParams] = useSearchParams();
  const dusuk = params.get('dusuk') === '1';
  const sort = params.get('sira') ?? 'goruntulenme';
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q, 300);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
    setPage(0);
  };
  const f = useQuery({
    queryKey: ['eticaret', 'funnel', dusuk, dq, sort, page],
    queryFn: () => ecomApi.funnel({ dusuk, q: dq, sort, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: (prev) => prev,
  });
  const d = f.data;
  return (
    <>
      {d && (
        <KpiRow>
          <Kpi label="Görüntülenme" value={fmtInt(d.toplam.goruntulenme)} help="Sitede satıştaki ürünler, tüm zamanlar" />
          <Kpi label="Site satışı" value={fmtInt(d.toplam.satis)} help="Ürün sayacındaki toplam satış adedi" />
          <Kpi label="Ortanca dönüşüm" value={fmtPct(d.ortancaDonusum)} help="Satış ÷ görüntülenme, ürünlerin ortancası" />
          <Kpi label="Düşük dönüşüm" value={dusuk ? fmtInt(d.total) : '—'} active={dusuk} onClick={() => set('dusuk', dusuk ? null : '1')}
            help={`En az ${fmtInt(d.dusukEsik.enAzGoruntulenme)} görüntülenme, dönüşümü ortancanın %${Math.round(d.dusukEsik.oran * 100)}'inden az`} />
        </KpiRow>
      )}
      <Panel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-[1.4fr_1fr_auto] sm:items-end">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} placeholder="Kitap adı, barkod, stok kodu"
                onChange={(e) => { setQ(e.target.value); set('q', e.target.value || null); }} />
            </span>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Sıra</span>
            <select className={field} value={sort} onChange={(e) => set('sira', e.target.value)}>
              {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
          <label className="flex min-h-11 cursor-pointer items-center gap-2 text-[12.5px] font-bold">
            <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={dusuk} onChange={(e) => set('dusuk', e.target.checked ? '1' : null)} />
            Yalnız düşük dönüşüm
          </label>
        </div>
        {d?.not && <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">{d.not}</p>}
      </Panel>
      <Panel>
        {f.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
        {f.error && <Note tone="err">{errText(f.error, 'Huni okunamadı.')}</Note>}
        {d && !d.items.length && <p className="py-8 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte kitap yok.</p>}
        <div className="flex flex-col gap-2">
          {d?.items.map((x) => <Row key={x.productKey} x={x} median={d.ortancaDonusum} onOpen={setOpen} />)}
        </div>
        {d && <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={f.isLoading} fetching={f.isFetching} onPage={setPage} />}
      </Panel>
      <ItemDrawer itemKey={open} meta={meta} onClose={() => setOpen(null)} />
    </>
  );
}

function Row({ x, median, onOpen }: { x: Item; median: number | null; onOpen: (k: string) => void }) {
  const ratio = x.donusum;
  const width = ratio === null || !median ? 0 : Math.min(1, ratio / (median * 2));
  return (
    <button type="button" onClick={() => onOpen(x.productKey)}
      className="grid w-full grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 text-left transition-colors duration-150 hover:border-canvas-violet/40 md:grid-cols-[minmax(0,1fr)_110px_90px_150px_110px] md:items-center">
      <div className="min-w-0">
        <div className="break-words text-[13.5px] font-extrabold leading-snug">{x.ad || x.adSite || x.productKey}</div>
        <div className="font-mono text-[11px] text-canvas-muted">{x.productKey}{x.stokKodu ? ` · ${x.stokKodu}` : ''}</div>
        {!!x.olasiNedenler?.length && (
          <div className="mt-1 flex flex-wrap gap-1">
            {x.olasiNedenler.map((n) => <Pill key={n} tone="warn">{n}</Pill>)}
          </div>
        )}
      </div>
      <Cell label="Görüntülenme" value={fmtInt(x.goruntulenme)} />
      <Cell label="Site satışı" value={fmtInt(x.siteSatis)} />
      <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-1">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted md:hidden">Dönüşüm</span>
        <span className="font-mono text-[12px] font-bold tabular-nums">{fmtPct(ratio)}</span>
        <span className="relative h-1.5 w-24 overflow-hidden rounded-full bg-slate-100" aria-hidden>
          <span className={`absolute inset-y-0 left-0 rounded-full ${median !== null && ratio !== null && ratio < median ? 'bg-amber-400' : 'bg-emerald-500'}`}
            style={{ width: `${width * 100}%` }} />
        </span>
      </div>
      <Cell label="Logo son dönem" value={x.logoAdet === null ? '—' : `${fmtInt(x.logoAdet)} adet`} />
    </button>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-0.5">
      <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted md:hidden">{label}</span>
      <span className="font-mono text-[12px] font-bold tabular-nums">{value}</span>
    </div>
  );
}
