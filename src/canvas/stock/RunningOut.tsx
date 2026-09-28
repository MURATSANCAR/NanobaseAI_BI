import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, errText, field, label as labelCls } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { fmtDay } from '../budget/api';
import { n0, stockApi } from './api';
import ItemList from './ItemList';
import { Chips, DataDay, Empty, ExportLink, Loading, SourcesButton, StockFrame } from './parts';
import { RULES } from './rules';
import { SuggestionActions } from './decisions';

/** Bitecekler (/stok/bitecekler): kaç gün yeter ≤ N (kişi seçer) ya da baskı süresi + güvenlik gününün altı; açık üretim
 *  kartı yanında. Gece üretilen «baskı tekrarı değerlendirilsin» önerileri (M12) aynı sayfada karara gelir. */

type Tab = 'liste' | 'oneri';

export default function RunningOut() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get('sekme') === 'oneri' ? 'oneri' : 'liste';
  const [gun, setGun] = useState(params.get('gun') ?? '');
  const dg = useDebounced(gun, 400);
  const kartsiz = params.get('kartsiz') === '1';
  const sayfa = Number(params.get('sayfa') ?? 0) || 0;
  const set = (k: string, v: string | null) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== 'sayfa') p.delete('sayfa');
    setParams(p, { replace: true });
  };
  const meta = useQuery({ queryKey: ['stock', 'meta'], queryFn: stockApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const days = Number(dg) > 0 ? Number(dg) : undefined;
  const q = useQuery({
    queryKey: ['stock', 'running-out', days, kartsiz, sayfa],
    queryFn: () => stockApi.runningOut({ gun: days, kartsiz, sayfa }),
    enabled: ENGINE_ENABLED && tab === 'liste',
    placeholderData: (prev) => prev,
  });
  const sug = useQuery({
    queryKey: ['stock', 'suggestions', 'bitecek', sayfa],
    queryFn: () => stockApi.suggestions({ tur: 'bitecek', sayfa }),
    enabled: ENGINE_ENABLED,
  });
  const d = q.data;
  const me = meta.data?.me;

  return (
    <StockFrame
      crumb="Bitecekler"
      title="Bitecekler"
      lead="Stoğu seçtiğiniz günden önce ya da baskı süresi + güvenlik günü dolmadan bitecek kitaplar. Açık üretim kartı olmayanlar baskı tekrarı için önce ele alınmalı."
      source={d?.veriSonu ? `Logo · ${fmtDay(d.veriSonu)}` : 'Logo + CRM'}
      aside={
        <>
          <SourcesButton rules={RULES} />
          <ExportLink show={!!me?.canExport} href={stockApi.exportUrl('bitecekler', { gun: days })} />
        </>
      }
    >
      <DataDay day={d?.veriSonu} extra={d ? `Baskı süresi ${d.baskiSuresi} gün (${d.baskiSuresiKaynak}); varsayılan güvenlik ${d.guvenlikGun} gün.` : undefined} />
      <Chips<Tab>
        label="Bölüm"
        items={[{ key: 'liste', label: 'Liste', count: d?.total ?? null }, { key: 'oneri', label: 'Üretime öneriler', count: sug.data?.total ?? null }]}
        value={tab}
        onChange={(k) => set('sekme', k === 'liste' ? null : k)}
      />
      {tab === 'liste' && (
        <Panel>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end">
            <label className="flex w-full flex-col gap-1 sm:w-40">
              <span className={labelCls}>Kaç gün içinde</span>
              <input className={field} inputMode="numeric" value={gun} placeholder={String(d?.gun ?? meta.data?.params.runoutDays ?? 30)}
                onChange={(e) => { setGun(e.target.value.replace(/\D/g, '')); set('gun', e.target.value.replace(/\D/g, '') || null); }} />
            </label>
            <label className="flex min-h-11 items-center gap-2 text-[12.5px] font-semibold sm:min-h-10">
              <input type="checkbox" className="h-4 w-4" checked={kartsiz} onChange={(e) => set('kartsiz', e.target.checked ? '1' : null)} />
              Yalnız açık üretim kartı olmayanlar
            </label>
          </div>
          {q.error && <Note tone="err">{errText(q.error, 'Liste okunamadı.')}</Note>}
          {q.isLoading && <Loading what="Bitecekler" />}
          {d && !d.items.length && <Empty>Bu sürede bitecek kitap yok. Satış hızı ve stok kaynağı ayrı ayrı okunuyor; boş liste bir okuma hatası değilse gerçekten bitecek kitap yoktur.</Empty>}
          {!!d?.items.length && <ItemList items={d.items} cols={['bakiye', 'hiz', 'gun', 'tukenme', 'tahmin90', 'kritik', 'bekleyen', 'uretim', 'deger']} />}
          {!!d?.items.some((i) => i.tahminAralik?.g90) && (
            <p className="mt-2 text-[11px] leading-snug text-canvas-muted">
              «Tahmin · 90 gün»: tahmin başlangıcından sonraki üç ayın beklenen satışı (temel); altındaki aralık muhafazakâr–iyimser
              (aylık tahmin aralıklarının toplamı). Aralığı olmayan kitapta yalnız temel tahmin yazar.
            </p>
          )}
          {d && <Pager page={d.page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={(p) => set('sayfa', String(p))} />}
        </Panel>
      )}
      {tab === 'oneri' && (
        <Panel>
          {sug.error && <Note tone="err">{errText(sug.error, 'Öneriler okunamadı.')}</Note>}
          {sug.data && !sug.data.items.length && <Empty>Karar bekleyen öneri yok. Öneriler her sabah 06:30’da üretilir.</Empty>}
          <ul className="flex flex-col gap-2">
            {sug.data?.items.map((s) => (
              <li key={s.id} className="rounded-2xl border border-slate-100 bg-white/80 p-3 text-[12.5px]">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <Link to={`/stok/${encodeURIComponent(s.stokKodu)}`} className="font-bold hover:text-canvas-violet hover:underline">
                    {(s.veri.ad as string | null) ?? s.stokKodu}
                  </Link>
                  <span className="font-mono text-[11px] text-canvas-muted">{s.stokKodu} · {s.hedefEtiket ?? '—'}</span>
                </div>
                <p className="mt-1 text-canvas-muted">{s.gerekce}</p>
                <SuggestionActions s={s} canDecide={!!me?.canDecide} />
              </li>
            ))}
          </ul>
          {sug.data && (
            <Pager page={sug.data.page} pageSize={sug.data.pageSize} total={sug.data.total} shown={sug.data.items.length} loading={sug.isLoading} fetching={sug.isFetching} onPage={(p) => set('sayfa', String(p))} />
          )}
          <p className="mt-2 text-[11px] text-canvas-muted">Kabul edilen öneri üretim modülünün okuyacağı kayıtta durur; CRM’e ve Logo’ya yazılmaz. Toplam {n0(sug.data?.total)} öneri.</p>
        </Panel>
      )}
    </StockFrame>
  );
}
