import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ClipboardList, FileText, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, errText, field, label as labelCls } from '../../admin/ui';
import { Kpi, KpiRow } from '../../editorial/kit';
import { AskSheet, Tabs } from '../../budget/parts';
import { fmtDay, fmtInt, fmtPct, fmtStamp } from '../api';
import { MarketingFrame } from '../parts';
import { TONE_CLASS, TONE_LABEL, dLabel, launchApi } from './api';
import ChecklistTab from './ChecklistTab';
import TrackingTab from './TrackingTab';
import EventsTab from './EventsTab';
import MediaTab from './MediaTab';
import ReviewTab from './ReviewTab';

/** Lansman ekranı: Kontrol listesi · İzleme · Etkinlikler · Medya · Değerlendirme. Telefonda sekme çubuğu yatay kayar;
 *  Kontrol listesi ve İzleme önde. Yayın günü adayları (CRM kitap/proje kartı, üretim kartı) başlıkta; biri seçilir ya
 *  da elle girilir. */

const TABS = [
  { key: 'kontrol', label: 'Kontrol listesi' },
  { key: 'izleme', label: 'İzleme' },
  { key: 'etkinlik', label: 'Etkinlikler' },
  { key: 'medya', label: 'Medya' },
  { key: 'degerlendirme', label: 'Değerlendirme' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function LaunchScreen() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [ask, setAsk] = useState<null | 'kapat' | 'ac'>(null);
  const [manual, setManual] = useState('');
  const meta = useQuery({ queryKey: ['launch', 'meta'], queryFn: launchApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['launch', id], queryFn: () => launchApi.get(id), enabled: ENGINE_ENABLED && !!id });
  const l = q.data;
  const m = meta.data;
  const fallback: Tab = l && l.durum !== 'hazirlik' ? 'izleme' : 'kontrol';
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? fallback) as Tab;
  const gun = params.get('gun') === '30' ? 30 : 7;
  const go = (next: Record<string, string>) => setParams({ sekme: tab, ...(gun === 30 ? { gun: '30' } : {}), ...next }, { replace: true });

  const refresh = useMutation({
    mutationFn: () => launchApi.refresh(id),
    onSuccess: (out) => { qc.setQueryData(['launch', id], out.lansman); qc.invalidateQueries({ queryKey: ['launch'] }); toast.success('CRM ve Logo yeniden okundu.'); },
    onError: (e) => toast.error(errText(e, 'Okunamadı.') ?? ''),
  });
  const patch = useMutation({
    mutationFn: (b: Parameters<typeof launchApi.update>[1]) => launchApi.update(id, b),
    onSuccess: (out) => { qc.setQueryData(['launch', id], out); qc.invalidateQueries({ queryKey: ['launch'] }); setAsk(null); toast.success('Kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  const sig = l?.sinyal;
  const cands = Object.entries(l?.ozet.adaylar ?? {});
  const aside = l && m ? (
    <div className="flex flex-wrap gap-2 lg:justify-end">
      <Link className={btnGhost} to={`/pazarlama/plan/${encodeURIComponent(l.planId)}`}><ClipboardList aria-hidden className="h-4 w-4" />Pazarlama planı</Link>
      {m.me.canExport && <a className={btnGhost} href={launchApi.pdfUrl(l.id)} download><FileText aria-hidden className="h-4 w-4" />Rapor PDF</a>}
      {m.me.canWrite && (
        <button type="button" className={btnGhost} disabled={refresh.isPending} onClick={() => refresh.mutate()}>
          <RefreshCw aria-hidden className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />Verileri yenile
        </button>
      )}
    </div>
  ) : undefined;

  return (
    <MarketingFrame
      crumb="Lansman"
      title={l?.baslik ?? 'Lansman'}
      source={l ? `${l.id} · son okuma ${l.okuma ? fmtStamp(l.okuma) : '—'}` : ''}
      presence={l ? l.durumAdi : '…'}
      detail={l?.baslik}
      back={{ to: '/pazarlama/lansman', label: 'Lansmanlar' }}
      aside={aside}
    >
      {q.error && <Note tone="err">{errText(q.error, 'Lansman açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {l && m && (
        <>
          <div className="flex flex-wrap items-center gap-2 px-1">
            <span className="rounded-md bg-slate-900 px-1.5 py-0.5 font-mono text-[12px] font-bold tabular-nums text-white">{dLabel(l.gun)}</span>
            {l.renk && <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ring-1 ring-inset ${TONE_CLASS[l.renk]}`}>{TONE_LABEL[l.renk]}</span>}
            <Pill tone="muted">{l.durumAdi}</Pill>
            <span className="text-[12px] font-semibold text-canvas-muted">
              Yayın günü {fmtDay(l.yayinGunu)} ({l.yayinGunuKaynakAdi}) · stok kodu {l.stokKodu} · sahibi {l.sahip ?? '—'} · plan {l.plan.id} ({l.plan.durumAdi ?? '—'})
            </span>
            {m.me.canWrite && (
              <div className="ml-auto">
                {l.durum === 'kapandi'
                  ? <button type="button" className={btnGhost} onClick={() => setAsk('ac')}>Yeniden aç</button>
                  : <button type="button" className={btnGhost} onClick={() => setAsk('kapat')}>Lansmanı kapat</button>}
              </div>
            )}
          </div>
          {l.uyarilar.map((w) => <Note key={w} tone={/stok|dağılım|eşik/i.test(w) ? 'err' : 'warn'}>{w}</Note>)}
          {(l.ozet.hatalar ?? []).length > 0 && <Note tone="err">Son okumada okunamayan kaynak: {(l.ozet.hatalar ?? []).join(' · ')}</Note>}

          {m.me.canWrite && (
            <details className="glass-panel rounded-2xl p-3 shadow-glass-float">
              <summary className="inline-flex min-h-8 cursor-pointer items-center text-[12.5px] font-extrabold">Yayın günü kaynakları</summary>
              <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">Lansman, onaylı planın yayın gününden açılır. Üretim kartı ve CRM kartları başka gün diyorsa buradan biri esas alınır ya da elle girilir; bekleyen maddeler yeni güne göre kayar.</p>
              <ul className="mt-2 flex flex-col gap-1.5">
                {cands.map(([k, v]) => (
                  <li key={k} className="flex min-h-11 flex-wrap items-center gap-2 rounded-xl bg-white/80 px-3 py-1.5 text-[12.5px]">
                    <span className="min-w-0 flex-1">{m.dateSources[k] ?? k}: <b>{fmtDay(v)}</b></span>
                    {v === l.yayinGunu && k === l.yayinGunuKaynagi ? <Pill tone="ok">Esas</Pill> : (
                      <button type="button" className={btnGhost} disabled={patch.isPending} onClick={() => patch.mutate({ yayinGunuKaynagi: k })}>Bunu esas al</button>
                    )}
                  </li>
                ))}
                {cands.length === 0 && <li className="text-[12px] text-canvas-muted">Henüz okunmadı ya da CRM'de tarih yok.</li>}
              </ul>
              <form className="mt-2 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (manual) patch.mutate({ yayinGunu: manual }); }}>
                <label className="flex flex-col gap-1"><span className={labelCls}>Elle yayın günü</span>
                  <input type="date" className={field} value={manual} onChange={(e) => setManual(e.target.value)} /></label>
                <button type="submit" className={btnGhost} disabled={!manual || patch.isPending}>Kaydet</button>
              </form>
            </details>
          )}

          <KpiRow>
            <Kpi label="Sipariş (yayından beri)" value={fmtInt(sig?.siparis)} help="CRM, saatte bir; sipariş satış değildir"
              active={tab === 'izleme'} onClick={() => go({ sekme: 'izleme' })} />
            <Kpi label="Faturalı satış" value={fmtInt(sig?.fatura)}
              help={sig?.veriSonuLogo ? `Logo, veri ${fmtDay(sig.veriSonuLogo)} tarihinde bitiyor` : 'Logo okunmadı'} />
            <Kpi label="Hedef payına oran" value={sig?.oran != null ? fmtPct(sig.oran) : '—'}
              help={sig?.oran != null ? `${sig.oranEsas === 'fatura' ? 'Faturalı satış' : 'Sipariş'} / hedef payı · eşik ${fmtPct(m.settings.alertRatio)}` : 'Onaylı hedef yok ya da yayın günü gelmedi'} />
            <Kpi label="Açık sipariş / depo" value={`${fmtInt(sig?.bekleyen)} / ${fmtInt(sig?.depo?.deger)}`}
              help={sig?.stokCatismasi ? 'Açık sipariş depo stokunun üstünde' : (sig?.depo?.kaynakAdi ?? 'Depo stoku okunmadı')} />
          </KpiRow>

          <Tabs tabs={TABS.map((t) => (t.key === 'kontrol' ? { ...t, badge: l.tasks.filter((x) => x.durum === 'bekliyor' && !!x.tarih && x.tarih < new Date().toISOString().slice(0, 10)).length } : t))}
            value={tab} onChange={(k) => go({ sekme: k })} />
          {tab === 'kontrol' && <ChecklistTab launch={l} meta={m} />}
          {tab === 'izleme' && <TrackingTab launch={l} meta={m} gun={gun} onGun={(g) => go({ sekme: 'izleme', gun: String(g) })} />}
          {tab === 'etkinlik' && <EventsTab launch={l} meta={m} />}
          {tab === 'medya' && <MediaTab launch={l} meta={m} />}
          {tab === 'degerlendirme' && <ReviewTab launch={l} meta={m} />}
        </>
      )}
      <AskSheet
        open={ask !== null}
        busy={patch.isPending}
        title={ask === 'ac' ? 'Lansmanı yeniden aç' : 'Lansmanı kapat'}
        message={ask === 'ac' ? 'Lansman yayın gününe göre yeniden izlenir; saatlik okuma ve uyarılar devam eder.'
          : 'Kapanan lansman okunmaz, uyarı ve özet göndermez. Rapor ve karar kaydı kalır; istenirse yeniden açılır.'}
        confirm={ask === 'ac' ? 'Yeniden aç' : 'Kapat'}
        onClose={() => setAsk(null)}
        onConfirm={() => patch.mutate({ durum: ask === 'ac' ? 'acik' : 'kapandi' })}
      />
    </MarketingFrame>
  );
}
