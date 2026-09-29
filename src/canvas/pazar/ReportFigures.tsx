import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, ChevronLeft, Download, Loader2, Plus, RotateCcw, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { STATUS_TONE, fmtInt, fmtNum, pazarApi, type Category, type Figure, type FigureStatus } from './api';
import { CategorySelect, ROOT, useMeta } from './parts';
import { ReadingBadge } from '../components/ReadingBadge';
import SqlInfo from '../components/SqlInfo';
import { EmptyHint } from '../components/Explain';
import { kaynakOf } from '../components/kaynakOf';

/** Bir raporun rakamları: Zeki AI önerisi → insan kararı (onayla, düzelt, reddet). Her rakam sayfa numarası ve kısa
 *  alıntıyla; düzeltmede modelin değeri korunur. */
export default function ReportFigures({ id }: { id: string }) {
  const qc = useQueryClient();
  const meta = useMeta();
  const can = !!meta.data?.me.canFigure;
  const [filter, setFilter] = useState<'' | FigureStatus>('oneri');
  const q = useQuery({
    queryKey: ['pazar', 'figures', id],
    queryFn: () => pazarApi.figures(id),
    enabled: ENGINE_ENABLED && !!id,
    refetchInterval: (qq) => (qq.state.data?.report.durum === 'cikariliyor' ? 4000 : false),
  });
  const decide = useMutation({
    mutationFn: ({ fid, body }: { fid: string; body: Parameters<typeof pazarApi.decideFigure>[1] }) => pazarApi.decideFigure(fid, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['pazar', 'figures', id] });
      qc.invalidateQueries({ queryKey: ['pazar', 'reports'] });
      qc.invalidateQueries({ queryKey: ['pazar', 'overview'] });
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Rapor açılamadı.')}</Note>;
  const d = q.data;
  if (!d) return null;
  const r = d.report;
  const items = filter ? d.items.filter((f) => f.durum === filter || (filter === 'onaylandi' && f.durum === 'duzeltildi')) : d.items;
  const count = (s: FigureStatus) => d.items.filter((f) => f.durum === s).length;
  const tabs: Array<['' | FigureStatus, string, number]> = [
    ['oneri', 'Onay bekleyen', count('oneri')],
    ['onaylandi', 'Onaylı', count('onaylandi') + count('duzeltildi')],
    ['reddedildi', 'Reddedilen', count('reddedildi')],
    ['', 'Tümü', d.items.length],
  ];
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <Panel>
        <Link to={`${ROOT}/raporlar`} className="inline-flex min-h-11 items-center gap-1 text-[11.5px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
          <ChevronLeft aria-hidden className="h-3.5 w-3.5" /> Raporlar
        </Link>
        <div className="mt-1 flex flex-wrap items-center gap-2">
          <h2 className="flex min-w-0 items-center gap-1 text-[17px] font-extrabold">
            {r.baslik}
            <SqlInfo k={kaynakOf(q.data)} alan="_hepsi" label="Raporun rakamları" />
          </h2>
          <Pill tone={STATUS_TONE[r.durum]}>{r.durumAd}</Pill>
          <a href={pazarApi.reportFileUrl(r.id)} className={`${btnGhost} ml-auto`}>
            <Download aria-hidden className="h-4 w-4" /> Dosyayı aç
          </a>
        </div>
        <p className="mt-0.5 text-[12px] text-canvas-muted">
          {r.kaynak}{r.yil ? ` · ${r.yil}` : ''} · {fmtInt(r.sayfaSayisi)} sayfa
          {r.durum === 'cikariliyor' && <> · <Loader2 aria-hidden className="inline h-3.5 w-3.5 animate-spin" /> sayfa {fmtInt(r.ilerleme?.sayfa ?? 0)} / {fmtInt(r.ilerleme?.toplam ?? r.sayfaSayisi ?? 0)}</>}
          {r.ilerleme?.hata && <span className="text-red-700"> · {r.ilerleme.hata}</span>}
        </p>
        <div role="tablist" aria-label="Durum" className="mt-3 flex max-w-full gap-1 overflow-x-auto rounded-xl bg-slate-100 p-1">
          {tabs.map(([k, l, n]) => (
            <button
              key={k || 'hepsi'}
              type="button"
              role="tab"
              aria-selected={filter === k}
              onClick={() => setFilter(k)}
              className={`min-h-11 shrink-0 whitespace-nowrap rounded-lg px-2.5 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${filter === k ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink'}`}
            >
              {l} <span className="font-mono tabular-nums">{fmtInt(n)}</span>
            </button>
          ))}
        </div>
        {items.length === 0 && <div className="mt-3"><EmptyHint title="Bu durumda rakam yok" why="Başka bir durum seçin. Yetkiniz varsa Zeki AI'ın kaçırdığı rakamı aşağıdaki «Elle rakam ekle» ile sayfa numarasıyla girebilirsiniz." /></div>}
        <ul className="mt-2 divide-y divide-slate-100">
          {items.map((f) => (
            <FigureItem
              key={f.id}
              f={f}
              can={can}
              olcu={d.olcu}
              categories={d.categories}
              busy={decide.isPending}
              onDecide={(body) => decide.mutate({ fid: f.id, body })}
            />
          ))}
        </ul>
      </Panel>
      {can && <ManualFigure reportId={r.id} olcu={d.olcu} categories={d.categories} />}
    </div>
  );
}

function FigureItem({ f, can, olcu, categories, busy, onDecide }: {
  f: Figure;
  can: boolean;
  olcu: Record<string, string>;
  categories: Category[];
  busy: boolean;
  onDecide: (body: Parameters<typeof pazarApi.decideFigure>[1]) => void;
}) {
  const [edit, setEdit] = useState(false);
  const [deger, setDeger] = useState(f.degerMetin ?? String(f.deger));
  const [ol, setOl] = useState(f.olcu);
  const [kat, setKat] = useState(f.kategoriId ?? '');
  const extra = { olcu: ol, kategoriId: kat || null };
  return (
    <li className="py-2.5">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[13px] font-bold">{f.gosterge}</span>
            <Pill tone={STATUS_TONE[f.durum]}>{f.durumAd}</Pill>
            <span className="text-[11px] font-semibold text-canvas-muted">s. {f.sayfa}{f.donem ? ` · ${f.donem}` : ''} · {f.yontem === 'elle' ? 'elle girildi' : 'Zeki AI'}</span>
            {f.okuma === 'ocr' && <ReadingBadge okuma="ocr" guven={f.guven} />}
          </div>
          {f.alinti && <blockquote className="mt-1 border-l-2 border-slate-200 pl-2 text-[11.5px] leading-snug text-canvas-muted">{f.alinti}</blockquote>}
          {f.durum === 'duzeltildi' && f.degerOneri !== null && <div className="mt-0.5 text-[11px] text-canvas-muted">Zeki AI'ın okuduğu: {fmtNum(f.degerOneri)}</div>}
        </div>
        <div className="shrink-0 font-mono text-[15px] font-bold tabular-nums sm:text-right">
          {fmtNum(f.deger)} <span className="text-[11.5px] font-semibold text-canvas-muted">{f.birim}</span>
        </div>
      </div>
      {can && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <select aria-label="Ölçü türü" value={ol} onChange={(e) => setOl(e.target.value)} className={`${field} w-full min-w-0 sm:w-56`}>
            {Object.entries(olcu).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <CategorySelect value={kat} onChange={setKat} categories={categories} empty="Kategori (bütün pazar)" className={`${field} w-full min-w-0 sm:w-56`} />
          {edit ? (
            <>
              <input aria-label="Düzeltilen değer" value={deger} onChange={(e) => setDeger(e.target.value)} className={`${field} w-32`} />
              <button type="button" className={btnPrimary} disabled={busy || !deger.trim()} onClick={() => { onDecide({ karar: 'duzeltildi', deger, ...extra }); setEdit(false); }}>
                <Check aria-hidden className="h-4 w-4" /> Kaydet
              </button>
              <button type="button" className={btnGhost} onClick={() => setEdit(false)}>Vazgeç</button>
            </>
          ) : f.durum === 'oneri' ? (
            <>
              <button type="button" className={btnPrimary} disabled={busy} onClick={() => onDecide({ karar: 'onaylandi', ...extra })}>
                <Check aria-hidden className="h-4 w-4" /> Onayla
              </button>
              <button type="button" className={btnGhost} disabled={busy} onClick={() => setEdit(true)}>Düzelt</button>
              <button type="button" className={btnGhost} disabled={busy} onClick={() => onDecide({ karar: 'reddedildi' })}>
                <X aria-hidden className="h-4 w-4" /> Reddet
              </button>
            </>
          ) : (
            <>
              {(ol !== f.olcu || (kat || null) !== f.kategoriId) && f.durum !== 'reddedildi' && (
                <button type="button" className={btnPrimary} disabled={busy} onClick={() => onDecide({ karar: f.durum, ...extra, ...(f.durum === 'duzeltildi' ? { deger: f.deger } : {}) })}>
                  <Check aria-hidden className="h-4 w-4" /> Kaydet
                </button>
              )}
              {f.yontem === 'zeki' && (
                <button type="button" className={btnGhost} disabled={busy} onClick={() => onDecide({ karar: 'oneri' })}>
                  <RotateCcw aria-hidden className="h-4 w-4" /> Kararı geri al
                </button>
              )}
            </>
          )}
        </div>
      )}
    </li>
  );
}

function ManualFigure({ reportId, olcu, categories }: { reportId: string; olcu: Record<string, string>; categories: Category[] }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [v, setV] = useState({ gosterge: '', deger: '', birim: '', donem: '', sayfa: '', olcu: 'diger', kategoriId: '', alinti: '' });
  const add = useMutation({
    mutationFn: () => pazarApi.addFigure(reportId, { ...v, kategoriId: v.kategoriId || null }),
    onSuccess: () => {
      toast.success('Rakam eklendi ve onaylandı.');
      setV({ gosterge: '', deger: '', birim: '', donem: '', sayfa: '', olcu: 'diger', kategoriId: '', alinti: '' });
      qc.invalidateQueries({ queryKey: ['pazar', 'figures', reportId] });
      qc.invalidateQueries({ queryKey: ['pazar', 'reports'] });
    },
    onError: (e) => toast.error(errText(e, 'Rakam eklenemedi.') ?? ''),
  });
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value }));
  if (!open) {
    return (
      <button type="button" className={`${btnGhost} self-start`} onClick={() => setOpen(true)}>
        <Plus aria-hidden className="h-4 w-4" /> Elle rakam ekle
      </button>
    );
  }
  return (
    <Panel>
      <h2 className="text-[15px] font-extrabold">Elle rakam</h2>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">Zeki AI'ın kaçırdığı ya da taranmış sayfadaki rakam. Sayfa numarası şart; giren kişinin onayıyla kaydedilir.</p>
      <form
        className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (v.gosterge.trim() && v.deger.trim() && v.sayfa.trim()) add.mutate();
        }}
      >
        <label className="flex min-w-0 flex-col gap-1 lg:col-span-2"><span className={labelCls}>Gösterge</span><input value={v.gosterge} onChange={set('gosterge')} className={field} required /></label>
        <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>Değer</span><input value={v.deger} onChange={set('deger')} className={field} placeholder="örn. 1.234,5" required /></label>
        <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>Birim</span><input value={v.birim} onChange={set('birim')} className={field} placeholder="adet, ₺, %" /></label>
        <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>Sayfa</span><input value={v.sayfa} onChange={set('sayfa')} className={field} required /></label>
        <label className="flex min-w-0 flex-col gap-1"><span className={labelCls}>Dönem</span><input value={v.donem} onChange={set('donem')} className={field} placeholder="2025" /></label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className={labelCls}>Ölçü</span>
          <select value={v.olcu} onChange={set('olcu')} className={field}>
            {Object.entries(olcu).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className={labelCls}>Kategori</span>
          <CategorySelect value={v.kategoriId} onChange={(x) => setV((o) => ({ ...o, kategoriId: x }))} categories={categories} empty="Bütün pazar" className={field} />
        </label>
        <label className="flex min-w-0 flex-col gap-1 sm:col-span-2 lg:col-span-4"><span className={labelCls}>Kısa alıntı (isteğe bağlı)</span><input value={v.alinti} onChange={set('alinti')} className={field} maxLength={300} /></label>
        <div className="flex gap-2 sm:col-span-2 lg:col-span-4">
          <button type="submit" className={btnPrimary} disabled={add.isPending}>{add.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Plus aria-hidden className="h-4 w-4" />} Ekle</button>
          <button type="button" className={btnGhost} onClick={() => setOpen(false)}>Kapat</button>
        </div>
      </form>
    </Panel>
  );
}
