import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Link2, Search, Sparkles, Unlink } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import { LINK_TONE, adsApi, fmtInt, fmtMoney, fmtMoney2, fmtRatio, type Campaign, type LinkStatus } from './api';
import { AdsFrame, BookPicker, DataEnd, PeriodPicker, useAdsMeta, usePeriod } from './parts';

/** Kampanya ↔ kitap bağı. Zeki AI önerir (kampanya adından, aday listesiyle kapalı seçim), uzman onaylar ya da elle seçer.
 *  Bağ portalda tutulur; CRM'e yazılmaz. */
export default function AdsCampaigns() {
  const qc = useQueryClient();
  const meta = useAdsMeta();
  const m = meta.data;
  const [period, setPeriod] = usePeriod();
  const [params, setParams] = useSearchParams();
  const bag = (params.get('bag') ?? '') as LinkStatus | '';
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const [pick, setPick] = useState<Campaign | null>(null);
  const list = useQuery({
    queryKey: ['ads', 'campaigns', period, bag, dq],
    queryFn: () => adsApi.campaigns({ ...period, bag, q: dq }),
    enabled: ENGINE_ENABLED && !!m,
    placeholderData: keepPreviousData,
  });
  const done = (msg: string) => {
    toast.success(msg);
    qc.invalidateQueries({ queryKey: ['ads'] });
  };
  const link = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Parameters<typeof adsApi.link>[1] }) => adsApi.link(id, body),
    onSuccess: (c) => { done(c.bag === 'onayli' ? `Bağlandı: ${c.kitapAdi ?? c.stokKodu}` : 'Bağ kaldırıldı.'); setPick(null); },
    onError: (e) => toast.error(errText(e, 'Bağ kaydedilemedi.') ?? ''),
  });
  const rematch = useMutation({
    mutationFn: (id: string) => adsApi.rematch(id),
    onSuccess: (c) => done(c.bag === 'oneri' ? `Zeki AI önerdi: ${c.kitapAdi}` : c.bag === 'onayli' ? `Kodla bağlandı: ${c.kitapAdi}` : 'Zeki AI emin olamadı; aday listesinden seçin.'),
    onError: (e) => toast.error(errText(e, 'Eşleştirme koşulamadı.') ?? ''),
  });
  const d = list.data;
  const canEdit = !!m?.me.canEdit;
  const setBag = (v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set('bag', v);
    else p.delete('bag');
    setParams(p, { replace: true });
  };

  return (
    <AdsFrame
      title="Kampanyalar ve kitap bağı"
      lead="Kitap bazında getiriyi görmek için her kampanya bir kitaba bağlanır. Stok kodu ya da barkod kampanya adında geçiyorsa bağ kesindir; geçmiyorsa Zeki AI adaylar arasından önerir, siz onaylarsınız."
      meta={m}
      aside={m ? <PeriodPicker period={period} onChange={setPeriod} meta={m} /> : null}
    >
      <DataEnd meta={m} />
      <Panel>
        <div className="mb-3 flex flex-col gap-2 lg:flex-row lg:items-end">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <span className="relative flex items-center">
              <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
              <input className={`${field} pl-9`} value={q} placeholder="Kampanya, kitap ya da stok kodu" onChange={(e) => setQ(e.target.value)} />
            </span>
          </label>
          <div className="flex rounded-xl bg-slate-100 p-1" role="radiogroup" aria-label="Bağ durumu">
            {([['', 'Hepsi'], ['yok', 'Bağsız'], ['oneri', 'Öneri'], ['onayli', 'Bağlı']] as const).map(([v, l]) => (
              <button key={v} type="button" role="radio" aria-checked={bag === v} onClick={() => setBag(v)}
                className={`min-h-11 flex-1 whitespace-nowrap rounded-lg px-2.5 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${bag === v ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted'}`}>
                {l}{v && d ? ` ${d.bagSayilari[v as LinkStatus] ?? 0}` : ''}
              </button>
            ))}
          </div>
        </div>
        {list.error && <Note tone="err">{errText(list.error, 'Kampanyalar açılamadı.')}</Note>}
        {list.isLoading && <Loading />}
        {d && <p className="mb-2 flex items-center gap-1 text-[11.5px] text-canvas-muted">Harcama, tıklama, TBM, ROAS ve bağ sayıları<SqlInfo k={d.kaynaklar} alan="items" label="Kampanyalar" /></p>}
        {d && d.items.length === 0 && <p className="py-6 text-[12.5px] text-canvas-muted">Bu süzgeçle kampanya yok.</p>}
        <ul className="flex flex-col gap-2">
          {d?.items.map((c) => (
            <li key={c.id} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
              <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="break-words text-[13px] font-extrabold">{c.ad}</div>
                  <div className="text-[11.5px] text-canvas-muted">{c.platformAdi} · {c.hesap}{c.durum ? ` · ${c.durum}` : ''}{c.sonGun ? ` · son gün ${c.sonGun}` : ''}</div>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <Pill tone={LINK_TONE[c.bag]}>{c.bagAdi}</Pill>
                    {c.kitapAdi && <span className="text-[12px] font-bold">{c.kitapAdi}</span>}
                    {c.stokKodu && <span className="font-mono text-[11px] text-canvas-muted">{c.stokKodu}</span>}
                    {c.bagKaynakAdi && <span className="text-[11px] text-canvas-muted">({c.bagKaynakAdi}{c.bagGuven !== null && c.bagKaynak === 'zeki' ? `, olasılık ${Math.round(c.bagGuven * 100)}%` : ''})</span>}
                  </div>
                  {c.bag === 'yok' && c.bagAyrinti?.not && <p className="mt-1 text-[11.5px] text-canvas-muted">{c.bagAyrinti.not}</p>}
                </div>
                <dl className="grid shrink-0 grid-cols-4 gap-x-3 gap-y-0.5 text-right font-mono text-[12px] tabular-nums lg:w-[420px]">
                  <dt className="font-sans text-[10.5px] font-bold uppercase text-canvas-muted">Harcama</dt>
                  <dt className="font-sans text-[10.5px] font-bold uppercase text-canvas-muted">Tıklama</dt>
                  <dt className="font-sans text-[10.5px] font-bold uppercase text-canvas-muted">TBM</dt>
                  <dt className="font-sans text-[10.5px] font-bold uppercase text-canvas-muted">ROAS</dt>
                  <dd>{fmtMoney(c.harcama)}</dd><dd>{fmtInt(c.tiklama)}</dd><dd>{fmtMoney2(c.tbm)}</dd><dd>{fmtRatio(c.platformRoas)}</dd>
                </dl>
              </div>
              {canEdit && (
                <div className="mt-2 flex flex-col gap-1.5 sm:flex-row sm:flex-wrap">
                  {c.bag === 'oneri' && (
                    <button type="button" className={btnPrimary} disabled={link.isPending} onClick={() => link.mutate({ id: c.id, body: { onayla: true } })}>
                      <Check aria-hidden className="h-4 w-4" />Öneriyi onayla
                    </button>
                  )}
                  {c.bag !== 'onayli' && (c.bagAyrinti?.adaylar ?? []).slice(0, 3).map((a) => (
                    <button key={a.stokKodu} type="button" className={btnGhost} disabled={link.isPending}
                      onClick={() => link.mutate({ id: c.id, body: { stokKodu: a.stokKodu } })}>
                      <Link2 aria-hidden className="h-4 w-4" /><span className="max-w-[240px] truncate">{a.ad ?? a.stokKodu}</span>
                    </button>
                  ))}
                  <button type="button" className={btnGhost} onClick={() => setPick(c)}>
                    <Search aria-hidden className="h-4 w-4" />Kitap seç
                  </button>
                  {c.bag !== 'onayli' && (
                    <button type="button" className={btnGhost} disabled={rematch.isPending || !m?.modelReady} onClick={() => rematch.mutate(c.id)}>
                      <Sparkles aria-hidden className="h-4 w-4" />Zeki AI'a sor
                    </button>
                  )}
                  {c.bag === 'onayli' && (
                    <button type="button" className={btnGhost} disabled={link.isPending} onClick={() => link.mutate({ id: c.id, body: { kaldir: true } })}>
                      <Unlink aria-hidden className="h-4 w-4" />Bağı kaldır
                    </button>
                  )}
                </div>
              )}
            </li>
          ))}
        </ul>
      </Panel>
      <BookPicker campaign={pick} busy={link.isPending} onClose={() => setPick(null)}
        onPick={(stok) => pick && link.mutate({ id: pick.id, body: { stokKodu: stok } })} />
    </AdsFrame>
  );
}
