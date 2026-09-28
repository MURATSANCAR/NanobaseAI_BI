import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ExternalLink, Plus } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, errText, field, label as labelCls } from '../admin/ui';
import { fmtDay, fmtInt, fmtShort, socialApi, todayIso } from './api';
import { Block, DaysLeft, SocialFrame } from './parts';
import NewPost, { type NewPostSeed } from './NewPost';

/** Fırsat kutusu: yaklaşan özel günler ve bağlı kitaplar, bu ay ve yakında çıkan kitaplar, uzun süredir paylaşılmayan
 *  çok satan backlist, basında çıkan haberler (yalnız web taraması açık kurulumda). Her satırdan tek dokunuşla gönderi. */

const WINDOWS = [14, 30, 60, 90];

export default function SocialOpportunities() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['social', 'meta'], queryFn: socialApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const accounts = useQuery({ queryKey: ['social', 'accounts'], queryFn: socialApi.accounts, enabled: ENGINE_ENABLED });
  const days = Number(params.get('gun')) || meta.data?.settings.opportunityDays || 30;
  const [bpage, setBpage] = useState(0);
  const opp = useQuery({
    queryKey: ['social', 'opportunities', days, bpage],
    queryFn: () => socialApi.opportunities(days, bpage),
    enabled: ENGINE_ENABLED && !!meta.data,
    placeholderData: keepPreviousData,
  });
  const [seed, setSeed] = useState<NewPostSeed | null>(null);
  const m = meta.data;
  const d = opp.data;
  const today = todayIso();
  const canEdit = !!m?.me.canEdit;

  const addBtn = (s: NewPostSeed, label = 'Gönderi aç') =>
    canEdit ? (
      <button type="button" className={btnGhost} onClick={() => setSeed(s)}>
        <Plus aria-hidden className="h-4 w-4" />
        {label}
      </button>
    ) : null;

  return (
    <SocialFrame
      crumb="Fırsatlar"
      title="İçerik fırsatları"
      lead="Özel günler (CRM'deki gün ve kitap bağı), yeni çıkan kitaplar ve uzun süredir paylaşılmayan çok satanlar. Satış rakamları Logo faturalı satıştır (iade düşülmüş); sayılar kaynağından hesaplanır."
      source="CRM + Logo"
      presence={d ? `${d.ozelGunler.length} özel gün` : '…'}
      aside={
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Pencere</span>
          <select className={field} value={days} onChange={(e) => { const p = new URLSearchParams(params); p.set('gun', e.target.value); setParams(p, { replace: true }); }}>
            {Array.from(new Set([...WINDOWS, days])).sort((a, b) => a - b).map((w) => <option key={w} value={w}>Önümüzdeki {w} gün</option>)}
          </select>
        </label>
      }
    >
      {opp.error && <Note tone="err">{errText(opp.error, 'Fırsatlar okunamadı.')}</Note>}
      {d?.hatalar.map((h) => <Note key={h} tone="warn">{h}</Note>)}
      {opp.isLoading && <Loading />}

      {d && m && (
        <div className="grid gap-3 xl:grid-cols-2 xl:gap-4">
          <Block title={`Özel günler (${d.ozelGunler.length})`}
            help={`Tarih yöntemi SEO sezon takvimiyle aynı. Güne ${m.settings.leadDays} gün ya da daha az kalıp bağlı kitaplardan hiçbiri takvimde değilse uyarı. «Takvimde»: güne bağlı ya da pencere içinde gönderisi olan kitap.`}>
            {d.ozelGunler.length === 0 && <p className="text-[12px] text-canvas-muted">Bu pencerede özel gün yok.</p>}
            <ul className="flex flex-col gap-2">
              {d.ozelGunler.map((o) => (
                <li key={o.key} id={o.key} className="rounded-xl bg-white/80 p-2.5">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[13px] font-extrabold">{o.ad}</span>
                        {o.uyari && <Pill tone="err">Takvimde kitap yok</Pill>}
                      </div>
                      <div className="text-[11.5px] text-canvas-muted">
                        {o.baslangic === o.bitis ? fmtDay(o.baslangic) : `${fmtShort(o.baslangic)} – ${fmtShort(o.bitis)}`} · {o.yontem}
                        {o.kesinlik === 'yaklasik' ? ' (±1 gün)' : ''}
                      </div>
                      <div className="text-[11.5px] font-semibold">{o.kitapSayisi} bağlı kitap · {o.takvimde} takvimde</div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <DaysLeft days={o.kalanGun} running={o.suruyor} />
                      {addBtn({ day: o.baslangic < today ? today : o.baslangic, occasion: { key: o.key, ad: o.ad }, kind: 'ozel-gun' }, 'Genel gönderi')}
                    </div>
                  </div>
                  {o.kitaplar.length > 0 && (
                    <details className="mt-1.5" open={o.uyari || undefined}>
                      <summary className="inline-flex min-h-8 cursor-pointer items-center text-[12px] font-bold text-canvas-violet">Bağlı kitaplar</summary>
                      <ul className="mt-1 flex flex-col divide-y divide-slate-100">
                        {o.kitaplar.map((b) => (
                          <li key={b.bookId} className="flex items-center justify-between gap-2 py-1.5">
                            <span className="min-w-0 text-[12px]">
                              <span className="block truncate font-semibold">{b.ad}</span>
                              <span className="font-mono text-[11px] text-canvas-muted">{b.stokKodu}</span>
                            </span>
                            {b.takvimde ? <Pill tone="ok">Takvimde</Pill>
                              : b.stokKodu && addBtn({ day: o.baslangic < today ? today : o.baslangic, occasion: { key: o.key, ad: o.ad }, kind: 'ozel-gun',
                                book: { stokKodu: b.stokKodu, ad: b.ad, kitapId: b.bookId } }, 'Takvime ekle')}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </Block>

          <div className="flex min-w-0 flex-col gap-3">
            <Block title={`Bu ay ve yakında çıkan kitaplar (${d.yeniKitaplar.items.length})`}
              help={`CRM ilk yayın tarihi ${fmtShort(d.yeniKitaplar.baslangic)} – ${fmtShort(d.yeniKitaplar.bitis)} arasında olan kitap kartları.`}>
              {d.yeniKitaplar.items.length === 0 && <p className="text-[12px] text-canvas-muted">Bu aralıkta yeni kitap yok.</p>}
              <ul className="flex flex-col divide-y divide-slate-100">
                {d.yeniKitaplar.items.map((b) => (
                  <li key={b.stokKodu} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                    <span className="min-w-0 text-[12px]">
                      <span className="block truncate font-semibold">{b.ad}</span>
                      <span className="text-[11px] text-canvas-muted">{[b.yazar, b.yayinevi, fmtShort(b.ilkYayin)].filter(Boolean).join(' · ')}</span>
                    </span>
                    {b.takvimde ? <Pill tone="ok">Takvimde</Pill> : addBtn({ day: b.ilkYayin && b.ilkYayin > today ? b.ilkYayin : today, book: b, kind: 'kapak' })}
                  </li>
                ))}
              </ul>
            </Block>

            <Block title={`Uzun süredir paylaşılmayan çok satanlar (${fmtInt(d.backlist.total)})`}
              help={d.backlist.pencere
                ? `Son 12 ay (${d.backlist.pencere.bas} – ${d.backlist.pencere.bit}, veri sonu ${fmtShort(d.backlist.veriSonu)}) net adet; ilk yayını ${m.settings.backlistMinAgeDays} günden eski ve ${m.settings.backlistQuietDays} gündür takvimde gönderisi olmayanlar.`
                : undefined}>
              {d.backlist.not && <Note tone="warn">{d.backlist.not}</Note>}
              <ol className="flex flex-col divide-y divide-slate-100">
                {d.backlist.items.map((b) => (
                  <li key={b.stokKodu} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                    <span className="flex min-w-0 items-baseline gap-2 text-[12px]">
                      <span className="w-7 shrink-0 text-right font-mono text-[11px] text-canvas-muted">{b.sira}.</span>
                      <span className="min-w-0">
                        <span className="block truncate font-semibold">{b.ad || b.stokKodu}</span>
                        <span className="text-[11px] text-canvas-muted">
                          {[b.yazar, `${fmtInt(b.adet12)} adet`, b.sonGonderi ? `son gönderi ${fmtShort(b.sonGonderi)}` : 'hiç gönderi yok'].filter(Boolean).join(' · ')}
                        </span>
                      </span>
                    </span>
                    {addBtn({ day: today, book: { stokKodu: b.stokKodu, ad: b.ad, kitapId: null } })}
                  </li>
                ))}
              </ol>
              {d.backlist.total > d.backlist.pageSize && (
                <div className="mt-2 flex items-center justify-between gap-2 text-[11.5px] text-canvas-muted">
                  <span>{fmtInt(bpage * d.backlist.pageSize + 1)}–{fmtInt(bpage * d.backlist.pageSize + d.backlist.items.length)} / {fmtInt(d.backlist.total)}</span>
                  <span className="flex gap-1.5">
                    <button type="button" className={btnGhost} disabled={bpage === 0 || opp.isFetching} onClick={() => setBpage(bpage - 1)}>Önceki</button>
                    <button type="button" className={btnGhost} disabled={(bpage + 1) * d.backlist.pageSize >= d.backlist.total || opp.isFetching} onClick={() => setBpage(bpage + 1)}>Sonraki</button>
                  </span>
                </div>
              )}
            </Block>

            <Block title="Basında çıkan haberler">
              {!d.basin.acik && <p className="text-[12px] text-canvas-muted">Basın ve web taraması bu kurulumda kapalı.</p>}
              {d.basin.acik && d.basin.items.length === 0 && <p className="text-[12px] text-canvas-muted">Bu pencerede yazar ya da kitap haberi yok.</p>}
              <ul className="flex flex-col gap-1.5">
                {d.basin.items.map((n) => (
                  <li key={n.url} className="flex items-start justify-between gap-2 rounded-xl bg-white/80 p-2">
                    <span className="min-w-0 text-[12px]">
                      <span className="block font-semibold">{n.baslik}</span>
                      <span className="text-[11px] text-canvas-muted">{[n.yazar, n.kaynak, fmtShort(n.tarih)].filter(Boolean).join(' · ')}</span>
                    </span>
                    <a href={n.url} target="_blank" rel="noreferrer" className={btnGhost} aria-label="Haberi aç"><ExternalLink aria-hidden className="h-4 w-4" /></a>
                  </li>
                ))}
              </ul>
            </Block>
          </div>
        </div>
      )}

      {m && accounts.data && <NewPost open={!!seed} seed={seed} meta={m} accounts={accounts.data.items} onClose={() => setSeed(null)} />}
    </SocialFrame>
  );
}
