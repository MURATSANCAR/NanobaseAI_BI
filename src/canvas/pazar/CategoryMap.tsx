import { useEffect, useRef, useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Loader2, Sparkles, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { STATUS_TONE, fmtInt, fmtPct, pazarApi, type MapRow, type MapStatus } from './api';
import { CategorySelect, Stat, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Kategori eşlemesi: rakip kaydındaki serbest metin kategori → TİMAŞ kategorisi. Önce ad eşleşmesi, sonra Zeki AI
 *  kapalı küme seçimi (olasılıkla) önerir; karar insanda. «Karşılığı yok» da bir karardır. */
const TABS: Array<{ key: string; label: string }> = [
  { key: 'oneri', label: 'Öneri' },
  { key: 'belirsiz', label: 'Emin değil' },
  { key: 'yeni', label: 'Öneri bekliyor' },
  { key: 'onaylandi', label: 'Onaylı' },
  { key: 'reddedildi', label: 'Karşılığı yok' },
  { key: '', label: 'Tümü' },
];

export default function CategoryMap() {
  const qc = useQueryClient();
  const meta = useMeta();
  const can = !!meta.data?.me.canMap;
  const [durum, setDurum] = useState('oneri');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 300);
  const list = useQuery({
    queryKey: ['pazar', 'map', durum, dq, page],
    queryFn: () => pazarApi.categoryMap({ durum, q: dq, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
    refetchInterval: (qq) => (qq.state.data?.job.running ? 5000 : false),
  });
  const running = !!list.data?.job.running;
  const was = useRef(false);
  useEffect(() => {
    if (was.current && !running) {
      const j = list.data?.job;
      if (j?.error) toast.error(j.error);
      else toast.success('Eşleme önerileri yazıldı.');
      qc.invalidateQueries({ queryKey: ['pazar'] });
    }
    was.current = running;
  }, [running, list.data?.job, qc]);

  const decide = useMutation({
    mutationFn: pazarApi.decideMap,
    onSuccess: (r) => {
      if (r.errors.length) toast.error(`${r.errors.length} karar yazılamadı: ${r.errors[0].neden}`);
      else toast.success(`${fmtInt(r.decided.length)} eşleme kaydedildi.`);
      qc.invalidateQueries({ queryKey: ['pazar'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  const suggest = useMutation({
    mutationFn: () => pazarApi.suggestMap(),
    onSuccess: (r) => {
      if (!r.queued) toast.message('Öneri bekleyen kategori yok.');
      else if (!r.started) toast.message('Öneri işi zaten sürüyor.');
      qc.invalidateQueries({ queryKey: ['pazar', 'map'] });
    },
    onError: (e) => toast.error(errText(e, 'Öneri başlatılamadı.') ?? ''),
  });

  const d = list.data;
  const byName = d?.items.filter((x) => x.durum === 'oneri' && x.yontem === 'ad') ?? [];
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      {d && (
        <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
          <Stat info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Onaylı kapsam" />} label="Onaylı kapsam" value={d.coverage.records ? fmtPct(d.coverage.approved / d.coverage.records, 0) : '—'} help={`${fmtInt(d.coverage.approved)} / ${fmtInt(d.coverage.records)} rakip kaydı`} />
          <Stat info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Onay bekleyen" />} label="Onay bekleyen" value={fmtInt((d.counts.oneri ?? 0) + (d.counts.belirsiz ?? 0))} help={`${fmtInt(d.counts.belirsiz ?? 0)} tanesinde Zeki AI emin değil`} />
          <Stat info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Öneri bekleyen" />} label="Öneri bekleyen" value={fmtInt(d.counts.yeni ?? 0)} help="Henüz önerisi yazılmamış ham kategori" />
          <Stat info={<SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Karşılığı yok" />} label="Karşılığı yok" value={fmtInt(d.coverage.noMatch)} help="TİMAŞ kategorisinde karşılığı olmadığı onaylanan kayıt" />
        </div>
      )}
      <Panel>
        <div className="flex flex-wrap items-center gap-2">
          <div role="tablist" aria-label="Durum" className="-mx-1 flex max-w-full gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1">
            {TABS.map((t) => (
              <button
                key={t.key || 'hepsi'}
                type="button"
                role="tab"
                aria-selected={durum === t.key}
                onClick={() => { setDurum(t.key); setPage(0); }}
                className={`min-h-11 shrink-0 whitespace-nowrap rounded-lg px-2.5 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${durum === t.key ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink'}`}
              >
                {t.label}
                {t.key && d?.counts[t.key as MapStatus] ? <span className="ml-1 font-mono tabular-nums">{fmtInt(d.counts[t.key as MapStatus])}</span> : null}
              </button>
            ))}
          </div>
          <input value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} className={`${field} min-w-0 flex-1 sm:max-w-xs`} placeholder="Ham kategori ara" />
          {can && (
            <div className="flex flex-wrap gap-2 sm:ml-auto">
              {byName.length > 0 && (
                <button
                  type="button"
                  className={btnGhost}
                  disabled={decide.isPending}
                  onClick={() => decide.mutate(byName.map((x) => ({ ham: x.ham, karar: 'onayla' as const })))}
                >
                  <Check aria-hidden className="h-4 w-4" /> Bu sayfadaki ad eşleşmelerini onayla ({byName.length})
                </button>
              )}
              <button type="button" className={btnPrimary} disabled={running || suggest.isPending || !meta.data?.modelVar} onClick={() => suggest.mutate()}>
                {running || suggest.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                Zeki AI önersin
              </button>
            </div>
          )}
        </div>
        {running && <p className="mt-2 text-[12px] font-semibold text-canvas-muted">Zeki AI öneri yazıyor; bitince liste tazelenir.</p>}
        {list.isLoading && <Loading />}
        {list.error && <Note tone="err">{errText(list.error, 'Eşleme listesi açılamadı.')}</Note>}
        {d && d.items.length === 0 && <p className="mt-3 text-[12.5px] text-canvas-muted">Bu durumda kategori yok.</p>}
        <ul className="mt-2 divide-y divide-slate-100">
          {d?.items.map((row) => <MapItem key={row.ham} row={row} can={can} categories={d.categories} busy={decide.isPending} onDecide={(items) => decide.mutate(items)} />)}
        </ul>
        {d && <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />}
      </Panel>
    </div>
  );
}

function MapItem({ row, can, categories, busy, onDecide }: {
  row: MapRow;
  can: boolean;
  categories: Array<{ id: string; yol: string; ad: string; ustId: string | null; kaynak: 'kitaplik' | 'agac' }>;
  busy: boolean;
  onDecide: (items: Array<{ ham: string; karar: 'onayla' | 'duzelt' | 'reddet'; kategoriId?: string | null }>) => void;
}) {
  const [pick, setPick] = useState(row.kategoriId ?? row.oneriId ?? '');
  return (
    <li className="flex flex-col gap-2 py-2.5 lg:flex-row lg:items-center lg:justify-between lg:gap-4">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[13px] font-bold">{row.ham}</span>
          <Pill tone={STATUS_TONE[row.durum]}>{row.durumAd}</Pill>
          <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{fmtInt(row.kayit)} kayıt</span>
        </div>
        {row.ornekler && row.ornekler.length > 0 && <div className="mt-0.5 truncate text-[11.5px] text-canvas-muted">Örnek: {row.ornekler.join(' · ')}</div>}
        <div className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">
          {row.kategoriYol ? <>Onaylı: <strong className="text-canvas-ink">{row.kategoriYol}</strong> ({row.onaylayan})</>
            : row.oneriYol ? <>Öneri: <strong className="text-canvas-ink">{row.oneriYol}</strong> · {row.yontem === 'ad' ? 'ad eşleşmesi' : `Zeki AI${row.olasilik !== null ? ` %${Math.round(row.olasilik * 100)}` : ''}`}</>
            : row.durum === 'reddedildi' ? <>TİMAŞ kategorisinde karşılığı yok ({row.onaylayan})</>
            : 'Henüz öneri yok.'}
          {row.not && <> · {row.not}</>}
        </div>
      </div>
      {can && (
        <div className="flex flex-wrap items-center gap-1.5 lg:shrink-0">
          {row.oneriId && row.durum !== 'onaylandi' && (
            <button type="button" className={btnPrimary} disabled={busy} onClick={() => onDecide([{ ham: row.ham, karar: 'onayla' }])}>
              <Check aria-hidden className="h-4 w-4" /> Onayla
            </button>
          )}
          <CategorySelect value={pick} onChange={setPick} categories={categories} empty="Kategori seç" className={`${field} w-full min-w-0 sm:w-64`} />
          <button type="button" className={btnGhost} disabled={busy || !pick || pick === row.kategoriId} onClick={() => onDecide([{ ham: row.ham, karar: 'duzelt', kategoriId: pick }])}>
            Bu kategoriye eşle
          </button>
          {row.durum !== 'reddedildi' && (
            <button type="button" className={btnGhost} disabled={busy} onClick={() => onDecide([{ ham: row.ham, karar: 'reddet' }])}>
              <X aria-hidden className="h-4 w-4" /> Karşılığı yok
            </button>
          )}
        </div>
      )}
    </li>
  );
}
