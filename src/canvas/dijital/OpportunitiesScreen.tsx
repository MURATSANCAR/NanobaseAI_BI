import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Download, FileSpreadsheet, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { Panel, Pager, useDebounced } from '../editorial/kit';
import { dijitalApi, fmtInt, type Format, type Opportunity } from './api';
import { Chips, DigitalFrame, ListHead, RightPill, Tabs } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import DigitalTitleDrawer from './DigitalTitleDrawer';
import { xlsxUrl } from '../components/excel';

/** Fırsatlar: hakkı olan, basılıda iyi satan, dijital sürümü olmayan kitaplar (e-kitap) ve sesli kitap adayları.
 *  Rakamlar Logo faturalı satırdan; sıra son 12 ay basılı net adede göre. Liste tek tıkla CSV olarak iner. */

const TABS = [
  { key: 'ekitap', label: 'E-kitap fırsatları' },
  { key: 'sesli', label: 'Sesli kitap adayları' },
] as const;

export default function OpportunitiesScreen() {
  const [params, setParams] = useSearchParams();
  const tur: Format = params.get('tur') === 'sesli' ? 'sesli' : 'ekitap';
  const page = Number(params.get('sayfa') ?? 0) || 0;
  const [q, setQ] = useState(params.get('q') ?? '');
  const [open, setOpen] = useState<string | null>(null);
  const dq = useDebounced(q, 300);
  const meta = useQuery({ queryKey: ['dijital', 'meta'], queryFn: dijitalApi.meta, enabled: ENGINE_ENABLED, staleTime: 30_000 });
  const list = useQuery({
    queryKey: ['dijital', 'opportunities', tur, dq, page],
    queryFn: () => dijitalApi.opportunities({ tur, q: dq, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  const st = meta.data?.ayarlar;
  const items = list.data?.items ?? [];
  return (
    <DigitalFrame
      crumb="Dijital yayın"
      me={meta.data?.me}
      title="Dijital fırsatlar"
      lead="Hakkı olan (hak notu yok ya da telif birimi karar vermiş), dijital sürümü olmayan ve son 12 ayda basılıda iyi satan kitaplar. Hakkı eksik, yok ya da incelenmeli olan kitap bu listeye girmez."
      aside={
        meta.data?.me.canExport ? (
          <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
            <a className={btnGhost} href={dijitalApi.opportunitiesCsv(tur, dq)}>
              <Download aria-hidden className="h-4 w-4" />
              Listeyi indir (CSV)
            </a>
            <a className={btnGhost} href={xlsxUrl(dijitalApi.opportunitiesCsv(tur, dq))}>
              <FileSpreadsheet aria-hidden className="h-4 w-4" />
              Listeyi indir (Excel)
            </a>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      <Tabs tabs={TABS} value={tur} onChange={(t) => update({ tur: t === 'ekitap' ? null : t, sayfa: null })} />
      {st && (
        <Note tone="info">
          Eşik: son 12 ayda en az {fmtInt(tur === 'sesli' ? st.audioMinQty : st.oppMinQty)} adet basılı satış
          {tur === 'sesli' && (st.audioGenres.length ? `; türler: ${st.audioGenres.join(', ')}` : '; bütün türler')}. Puan, kitabın basılı
          satışta kaçıncı yüzdelikte olduğudur. Eşik ve türler yönetim ekranında (Dijital yayın ve e-kitap) değişir.
          <SqlInfo k={list.data?.kaynaklar} alan="esik" label="Fırsat eşiği" className="ml-0.5" />
        </Note>
      )}
      <Panel>
        <label className="flex max-w-[520px] flex-col gap-1">
          <span className={labelCls}>Ara</span>
          <span className="relative flex items-center">
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} placeholder="Kitap, yazar, stok kodu"
              onChange={(e) => { setQ(e.target.value); update({ q: e.target.value || null, sayfa: null }); }} />
          </span>
        </label>
        {list.data && (
          <ListHead>
            <InfoLabel k={list.data.kaynaklar} alan="total" label="Fırsat sayısı">{`${fmtInt(list.data.total)} kitap`}</InfoLabel>
            <InfoLabel k={list.data.kaynaklar} alan="items[].basili12Adet" label="Basılı adet, son 12 ay">Sağdaki sayı: basılı adet, 12 ay</InfoLabel>
            <InfoLabel k={list.data.kaynaklar} alan="items[].puan" label="Fırsat puanı">Puan</InfoLabel>
          </ListHead>
        )}
        <div className="mt-2 flex flex-col gap-2">
          {list.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>}
          {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
          {list.data && !items.length && <div className="py-8 text-center text-[12.5px] text-canvas-muted">Bu eşikte fırsat yok.</div>}
          {items.map((o) => <OppCard key={o.kitapId} o={o} tur={tur} onOpen={setOpen} />)}
        </div>
        {list.data && (
          <Pager page={page} pageSize={list.data.pageSize} total={list.data.total} shown={items.length} loading={list.isLoading}
            fetching={list.isFetching} onPage={(p) => update({ sayfa: p ? String(p) : null })} />
        )}
      </Panel>
      {meta.data && <DigitalTitleDrawer id={open} meta={meta.data} onClose={() => setOpen(null)} />}
    </DigitalFrame>
  );
}

function OppCard({ o, tur, onOpen }: { o: Opportunity; tur: Format; onOpen: (id: string) => void }) {
  return (
    <button type="button" onClick={() => onOpen(o.kitapId)}
      className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 text-left transition-colors duration-150 hover:border-canvas-violet/40 md:grid-cols-[minmax(0,1.2fr)_minmax(0,1.6fr)_110px] md:items-center">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <RightPill value={tur === 'sesli' ? o.hakSesli : o.hakEkitap} label={tur === 'sesli' ? o.hakSesliAdi : o.hakEkitapAdi} />
          <span className="text-[11px] font-semibold text-canvas-muted">{[o.stokKodu, o.hedefKitle].filter(Boolean).join(' · ')}</span>
        </div>
        <div className="mt-1 break-words text-[13.5px] font-extrabold leading-snug">{o.ad}</div>
        <div className="truncate text-[12px] text-canvas-muted">{o.yazar}</div>
      </div>
      <div className="min-w-0 text-[12px] leading-snug">
        <div>{o.gerekce}</div>
        <div className="mt-1"><Chips items={o.platformlar} empty="" /></div>
      </div>
      <div className="flex items-center gap-2 md:flex-col md:items-end md:gap-0.5">
        <span className="font-mono text-[13px] font-bold tabular-nums">{fmtInt(o.basili12Adet)}</span>
        <span className="text-[10.5px] text-canvas-muted">adet · puan {o.puan !== null ? Math.round(o.puan) : '—'}</span>
      </div>
    </button>
  );
}
