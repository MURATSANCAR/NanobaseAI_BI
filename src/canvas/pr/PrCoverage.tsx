import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ExternalLink, Plus, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Pager, useDebounced } from '../editorial/kit';
import { TONE_TONE, fmtDay, prApi, type Coverage, type Meta } from './api';
import { Block, Empty, PrFrame } from './parts';
import CoverageForm from './CoverageForm';

/** Yansımalar: portalda kayıtlı haberler + CRM haber arşivi (salt okunur) tek listede; Basın ve web taramasının
 *  adayları («aday» sekmesi, yalnız taramanın açık olduğu ortamda dolar) kabul ya da red edilir. */
const STATES = [
  { v: 'kayitli', l: 'Kayıtlı' },
  { v: 'aday', l: 'Adaylar' },
  { v: 'reddedildi', l: 'Reddedilen' },
] as const;

export default function PrCoverage() {
  const [params, setParams] = useSearchParams();
  const qc = useQueryClient();
  const durum = params.get('durum') ?? 'kayitli';
  const kaynak = params.get('kaynak') ?? '';
  const ton = params.get('ton') ?? '';
  const kitap = params.get('kitap') ?? '';
  const frm = params.get('bas') ?? '';
  const to = params.get('bit') ?? '';
  const [q, setQ] = useState(params.get('q') ?? '');
  const dq = useDebounced(q.trim(), 300);
  const [page, setPage] = useState(0);
  const [adding, setAdding] = useState(params.get('ekle') === '1');
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    p.delete('ekle');
    setParams(p, { replace: true });
    setPage(0);
  };
  const meta = useQuery({ queryKey: ['pr', 'meta'], queryFn: prApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({
    queryKey: ['pr', 'coverage', durum, kaynak, ton, kitap, frm, to, dq, page],
    queryFn: () => prApi.coverage({ durum, kaynak, ton, kitap, frm, to, q: dq, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const m = meta.data;
  const d = list.data;
  const done = () => {
    qc.invalidateQueries({ queryKey: ['pr', 'coverage'] });
    qc.invalidateQueries({ queryKey: ['pr', 'home'] });
  };

  return (
    <PrFrame
      crumb="Yansımalar"
      title="Yansımalar"
      lead="Çıkan haberin bağlantısını yapıştırın: başlık, tarih ve mecra okunur, kitap ve kişi eşleşir; gönderim satırı kendiliğinden «haber çıktı» olur. Haber metni kopyalanmaz; başlık, kısa özet ve bağlantı tutulur."
      source={d?.webWatch ? 'Portal + CRM arşivi + Basın ve web taraması' : 'Portal + CRM arşivi · web taraması bu ortamda kapalı'}
      presence={d ? `${d.total.toLocaleString('tr-TR')} kayıt` : '…'}
      aside={m?.me.canEdit ? (
        <button type="button" className={`${btnPrimary} w-full`} onClick={() => setAdding(true)}>
          <Plus aria-hidden className="h-4 w-4" /> Yansıma ekle
        </button>
      ) : undefined}
    >
      {d && !d.webWatch && <Note tone="info">Bu ortamda web taraması kapalı: yansımalar elle girilir, bağlantıdan başlık okunmaz.</Note>}
      {d?.note && <Note tone="warn">{d.note}</Note>}
      <Block title="Liste">
        <div className="mb-2 flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Durum">
          {STATES.map((s) => (
            <button key={s.v} type="button" role="radio" aria-checked={durum === s.v}
              className={`min-h-11 flex-1 rounded-lg text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${durum === s.v ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}
              onClick={() => set('durum', s.v === 'kayitli' ? '' : s.v)}>
              {s.l}{d?.counts[s.v] ? ` (${d.counts[s.v]})` : ''}
            </button>
          ))}
        </div>
        <div className="mb-3 grid grid-cols-2 gap-2 lg:grid-cols-[1fr_150px_150px_170px_150px] lg:items-end">
          <label className="relative col-span-2 flex items-center lg:col-span-1">
            <span className="sr-only">Ara</span>
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={q} placeholder="Başlık, mecra, kitap, yazar" onChange={(e) => { setQ(e.target.value); setPage(0); }} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Başlangıç</span>
            <input type="date" className={field} value={frm} onChange={(e) => set('bas', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Bitiş</span>
            <input type="date" className={field} value={to} onChange={(e) => set('bit', e.target.value)} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kaynak</span>
            <select className={field} value={kaynak} onChange={(e) => set('kaynak', e.target.value)}>
              <option value="">Hepsi</option>
              {Object.entries(m?.coverageSources ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ton</span>
            <select className={field} value={ton} onChange={(e) => set('ton', e.target.value)}>
              <option value="">Hepsi</option>
              {Object.entries(m?.tones ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
        </div>
        {kitap && (
          <div className="mb-2 flex items-center gap-2 text-[12px]">
            <Pill tone="violet">Tek kitap</Pill>
            <button type="button" className="font-bold text-canvas-violet hover:underline" onClick={() => set('kitap', '')}>Süzgeci kaldır</button>
          </div>
        )}
        {list.isLoading && <Loading />}
        {list.error && <Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note>}
        {d && d.items.length === 0 && (
          <Empty>{durum === 'aday' ? (d.webWatch ? 'Onay bekleyen aday yok.' : 'Web taraması kapalı olduğundan aday gelmez.') : 'Bu süzgeçle yansıma yok.'}</Empty>
        )}
        <ul className="flex flex-col gap-2">
          {d?.items.map((c) => m && <CoverageRow key={c.id} c={c} meta={m} onChange={done} />)}
        </ul>
        {d && d.total > 0 && <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />}
      </Block>
      {m && adding && <CoverageForm meta={m} bookId={kitap} onClose={() => setAdding(false)} onSaved={done} />}
    </PrFrame>
  );
}

function CoverageRow({ c, meta, onChange }: { c: Coverage; meta: Meta; onChange: () => void }) {
  const canEdit = meta.me.canEdit && !c.readOnly;
  const [confirming, setConfirming] = useState(false);
  const upd = useMutation({
    mutationFn: (b: Record<string, unknown>) => prApi.updateCoverage(c.id, b),
    onSuccess: () => { onChange(); toast.success('Kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const del = useMutation({
    mutationFn: () => prApi.deleteCoverage(c.id),
    onSuccess: () => { onChange(); toast.success('Silindi.'); },
    onError: (e) => toast.error(errText(e, 'Silinemedi.') ?? ''),
  });
  const toneNote = c.toneSource === 'zeki' ? (c.tone ? 'Zeki AI sınıflaması' : 'Zeki AI emin değil; siz seçin') : c.toneSource === 'web' ? 'Tarama sınıflaması' : null;
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="break-words text-[13.5px] font-extrabold leading-snug">
            {c.url ? (
              <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1 hover:underline">
                {c.title} <ExternalLink aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-canvas-muted" />
              </a>
            ) : c.title}
          </div>
          <div className="text-[11.5px] text-canvas-muted">
            {[fmtDay(c.publishedAt), c.outlet, c.bookTitle, c.authorName].filter((x) => x && x !== '—').join(' · ')}
          </div>
          {c.summary && <p className="mt-1 text-[12px] leading-snug text-canvas-ink/80">{c.summary}</p>}
          {c.note && <p className="mt-1 text-[11.5px] text-canvas-muted">{c.note}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Pill tone={c.source === 'crm-arsiv' ? 'muted' : c.source === 'web' ? 'violet' : 'ok'}>{c.sourceLabel}</Pill>
          {c.tone && <Pill tone={TONE_TONE[c.tone]}>{c.toneLabel}</Pill>}
        </div>
      </div>
      {canEdit && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <label className="flex items-center gap-1.5 text-[11.5px]">
            <span className={labelCls}>Ton</span>
            <select className={`${field} !w-auto`} value={c.tone ?? ''} onChange={(e) => upd.mutate({ tone: e.target.value || null })}>
              <option value="">—</option>
              {Object.entries(meta.tones).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </label>
          {toneNote && <span className="text-[11px] text-canvas-muted">{toneNote}</span>}
          <span className="ml-auto flex gap-1.5">
            {c.state === 'aday' && (
              <>
                <button type="button" className={btnPrimary} disabled={upd.isPending} onClick={() => upd.mutate({ state: 'kayitli' })}>Kabul et</button>
                <button type="button" className={btnGhost} disabled={upd.isPending} onClick={() => upd.mutate({ state: 'reddedildi' })}>Reddet</button>
              </>
            )}
            {c.state === 'reddedildi' && <button type="button" className={btnGhost} disabled={upd.isPending} onClick={() => upd.mutate({ state: 'aday' })}>Adaya geri al</button>}
            {c.source === 'elle' && (confirming
              ? <button type="button" className={`${btnPrimary} !bg-red-600`} disabled={del.isPending} onClick={() => del.mutate()}>Evet, sil</button>
              : <button type="button" className={btnGhost} onClick={() => setConfirming(true)}>Sil</button>)}
          </span>
        </div>
      )}
    </li>
  );
}
