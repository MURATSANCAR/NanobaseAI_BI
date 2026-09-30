import { useCallback, useState, type ReactNode } from 'react';
import { NavLink, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, CheckCheck, X } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import Sheet from '../editorial/studio/reader/Sheet';
import { useDebounced } from '../editorial/kit';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { AskSheet } from '../budget/parts';
import { SUGGESTION_TONE, adsApi, fmtDay, iso, type Campaign, type Meta, type Period, type Suggestion } from './api';

/** M21 Reklam ekranlarının ortak parçaları: kabuk + bölüm çubuğu, dönem seçici, veri tarihi notu, öneri kartı. */

const SECTIONS = [
  { to: '/reklam', label: 'Özet', end: true },
  { to: '/reklam/kampanyalar', label: 'Kampanyalar', end: false },
  { to: '/reklam/yukle', label: 'Veri yükle', end: false },
  { to: '/reklam/butce', label: 'Bütçe', end: false },
  { to: '/reklam/brief', label: 'Brief', end: false },
] as const;

export function useAdsMeta() {
  return useQuery({
    queryKey: ['ads', 'meta'],
    queryFn: adsApi.meta,
    enabled: ENGINE_ENABLED,
    staleTime: 30_000,
    // Satış verisi yenilenirken durum ekranda güncel kalsın; bitince yoklama durur.
    refetchInterval: (q) => (q.state.data?.refresh?.durum === 'calisiyor' ? 5000 : false),
  });
}

export function AdsFrame({ title, lead, meta, aside, children }: { title: string; lead?: string; meta?: Meta; aside?: ReactNode; children: ReactNode }) {
  const [params] = useSearchParams();
  const keep = ['bas', 'bit', 'kanal'].filter((k) => params.get(k)).map((k) => `${k}=${encodeURIComponent(params.get(k) ?? '')}`).join('&');
  const end = meta?.logo?.veriSonu;
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb: 'Reklam', source: end ? `Logo satış ${fmtDay(end)}'e kadar` : 'Dosya + Logo + CRM',
                   presence: meta ? `${meta.accounts.length} reklam hesabı` : '…' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Kampanya</div>
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            <nav aria-label="Reklam bölümleri" className="overflow-x-auto">
              <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                {SECTIONS.map((s) => (
                  <NavLink key={s.to} to={keep ? `${s.to}?${keep}` : s.to} end={s.end}
                    className={({ isActive }) => `inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                      isActive ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'}`}>
                    {s.label}
                  </NavLink>
                ))}
              </div>
            </nav>
            {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı kurulu değil; bu ekran şu an veri gösteremez. Sistem yöneticinize haber verin.</Note>}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Dönem ve kanal adres çubuğunda (?bas=, ?bit=, ?kanal=); varsayılan son 30 gün. */
export function usePeriod(): [Period, (p: Partial<Record<'bas' | 'bit' | 'kanal', string | null>>) => void] {
  const [params, setParams] = useSearchParams();
  const today = new Date();
  const to = params.get('bit') || iso(today);
  const frm = params.get('bas') || iso(new Date(new Date(`${to}T00:00:00Z`).getTime() - 29 * 86_400_000));
  const kanal = params.get('kanal') || '';
  const update = useCallback(
    (next: Partial<Record<'bas' | 'bit' | 'kanal', string | null>>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  return [{ frm, to, kanal }, update];
}

const addDays = (s: string, n: number) => iso(new Date(new Date(`${s}T00:00:00Z`).getTime() + n * 86_400_000));

export function PeriodPicker({ period, onChange, meta }: { period: Period; onChange: (p: Partial<Record<'bas' | 'bit' | 'kanal', string | null>>) => void; meta?: Meta }) {
  const quick: Array<[string, () => void]> = [
    ['Dün', () => { const y = addDays(iso(new Date()), -1); onChange({ bas: y, bit: y }); }],
    ['7 gün', () => { const t = iso(new Date()); onChange({ bas: addDays(t, -6), bit: t }); }],
    ['30 gün', () => onChange({ bas: null, bit: null })],
    ['Bu ay', () => { const t = iso(new Date()); onChange({ bas: `${t.slice(0, 7)}-01`, bit: t }); }],
  ];
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Başlangıç</span>
          <input type="date" className={field} value={period.frm} onChange={(e) => onChange({ bas: e.target.value || null })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Bitiş</span>
          <input type="date" className={field} value={period.to} onChange={(e) => onChange({ bit: e.target.value || null })} />
        </label>
        <label className="col-span-2 flex flex-col gap-1 sm:col-span-1">
          <span className={labelCls}>Kanal</span>
          <select className={field} value={period.kanal ?? ''} onChange={(e) => onChange({ kanal: e.target.value || null })}>
            <option value="">Hepsi</option>
            {Object.entries(meta?.platforms ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {quick.map(([l, fn]) => (
          <button key={l} type="button" onClick={fn}
            className="min-h-9 rounded-lg bg-slate-100 px-2.5 text-[12px] font-bold text-canvas-ink transition-transform duration-150 ease-out hover:bg-slate-200 active:scale-[0.97]">
            {l}
          </button>
        ))}
      </div>
    </div>
  );
}

/** «Satış verisi şu güne kadar» — donmuş veriyi güncel sandırmamak için her ekranın üstünde. */
export function DataEnd({ meta, verimDonemi }: { meta?: Meta; verimDonemi?: { bas: string; bit: string } | null }) {
  if (!meta) return null;
  const end = meta.logo?.veriSonu;
  const r = meta.refresh;
  return (
    <div className="flex flex-col gap-1.5">
      {!end ? (
        <Note tone="warn">Logo satış verisi henüz okunmadı: e-ticaret cirosu, stok ve pazarlama verimi boş. Veri her sabah kendiliğinden ya da «Satış verisini yenile» ile gelir.</Note>
      ) : (
        <Note tone="info">
          Logo satış verisi <b>{fmtDay(end)}</b> tarihine kadar. E-ticaret cirosu, Logo'da e-ticaret kanalına (kanal kodu {meta.settings.ecomChannels.join(', ')}) bağlı müşterilerin faturalı net satışıdır.
          {verimDonemi === null && ' Seçilen dönemde satış verisi yok; pazarlama verimi hesaplanmadı.'}
        </Note>
      )}
      {r?.durum === 'calisiyor' && <Note tone="info">Satış verisi yenileniyor ({r.kim})…</Note>}
      {r?.durum === 'hata' && <Note tone="err">Son yenileme başarısız: {r.hata}</Note>}
    </div>
  );
}

/** Öneri / uyarı kartı. Para kararı (durdur, kaydır) önce onay ister; uyarılar doğrudan «uygulandı» ya da «yok say». */
export function SuggestionCard({ s, meta }: { s: Suggestion; meta?: Meta }) {
  const qc = useQueryClient();
  const [ask, setAsk] = useState<'reddet' | null>(null);
  const decide = useMutation({
    mutationFn: ({ karar, not }: { karar: 'onayla' | 'reddet' | 'uygulandi'; not?: string }) => adsApi.decide(s.id, karar, not),
    onSuccess: (x) => {
      toast.success(`${x.turAdi}: ${x.durumAdi.toLocaleLowerCase('tr')}`);
      qc.invalidateQueries({ queryKey: ['ads'] });
      setAsk(null);
    },
    onError: (e) => toast.error(errText(e, 'Karar kaydedilemedi.') ?? ''),
  });
  const me = meta?.me;
  const open = s.durum === 'yeni' || s.durum === 'onaylandi';
  const canApprove = !!me?.canApprove && s.onayGerekir && s.durum === 'yeni';
  const canApply = !!me?.canEdit && ((s.onayGerekir && s.durum === 'onaylandi') || (!s.onayGerekir && s.durum === 'yeni'));
  const canDismiss = s.durum === 'yeni' && (s.onayGerekir ? !!me?.canApprove : !!me?.canEdit);
  return (
    <article className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone={s.tur === 'stok' || s.tur === 'satis-disi' ? 'err' : s.onayGerekir ? 'violet' : 'warn'}>{s.turAdi}</Pill>
        <Pill tone={SUGGESTION_TONE[s.durum]}>{s.durumAdi}</Pill>
        {s.platformAdi && <span className="text-[11px] font-semibold text-canvas-muted">{s.platformAdi}</span>}
      </div>
      <p className="mt-1.5 text-[12.5px] leading-snug">{s.gerekce}</p>
      {s.zekiNotu && <p className="mt-1 text-[12px] leading-snug text-canvas-muted">Zeki AI: {s.zekiNotu}</p>}
      {s.karar && <p className="mt-1 text-[11px] text-canvas-muted">Karar: {s.karar}{s.kararNotu ? ` — ${s.kararNotu}` : ''}{s.uygulayan ? ` · uygulayan ${s.uygulayan}` : ''}</p>}
      {open && (canApprove || canApply || canDismiss) && (
        <div className="mt-2 grid grid-cols-1 gap-1.5 sm:flex sm:flex-wrap">
          {canApprove && (
            <button type="button" className={btnPrimary} disabled={decide.isPending} onClick={() => decide.mutate({ karar: 'onayla' })}>
              <Check aria-hidden className="h-4 w-4" />Onayla
            </button>
          )}
          {canApply && (
            <button type="button" className={s.onayGerekir ? btnPrimary : btnGhost} disabled={decide.isPending} onClick={() => decide.mutate({ karar: 'uygulandi' })}>
              <CheckCheck aria-hidden className="h-4 w-4" />Platformda uygulandı
            </button>
          )}
          {canDismiss && (
            <button type="button" className={btnGhost} disabled={decide.isPending}
              onClick={() => (s.onayGerekir ? setAsk('reddet') : decide.mutate({ karar: 'reddet' }))}>
              <X aria-hidden className="h-4 w-4" />{s.onayGerekir ? 'Reddet' : 'Yok say'}
            </button>
          )}
        </div>
      )}
      {s.onayGerekir && s.durum === 'yeni' && !me?.canApprove && (
        <p className="mt-1.5 text-[11px] text-canvas-muted">Para kararı: pazarlama müdürünün onayını bekliyor.</p>
      )}
      <AskSheet open={ask === 'reddet'} title="Öneriyi reddet" message={s.gerekce} confirm="Reddet" danger input="Gerekçe" required busy={decide.isPending}
        onClose={() => setAsk(null)} onConfirm={(t) => decide.mutate({ karar: 'reddet', not: t })} />
    </article>
  );
}

/** Kitap arama penceresi (elle bağ, brief). En iyi 30 eşleşme gösterilir, toplam sayı yazılır. */
export function BookPicker({ campaign, title, busy, onClose, onPick }: { campaign: Campaign | null; title?: string; busy: boolean; onClose: () => void; onPick: (stok: string) => void }) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const hits = useQuery({ queryKey: ['ads', 'books', dq], queryFn: () => adsApi.books(dq), enabled: ENGINE_ENABLED && dq.trim().length >= 2 });
  return (
    <Sheet open={!!campaign} modal onClose={() => { setQ(''); onClose(); }} title={title ?? 'Kitap seç'} subtitle={campaign?.ad}>
      <label className="flex flex-col gap-1">
        <span className={labelCls}>Kitap adı, stok kodu, barkod ya da yazar</span>
        <input className={field} autoFocus placeholder="En az iki harf yazın" value={q} onChange={(e) => setQ(e.target.value)} />
      </label>
      {hits.error && <div className="mt-2"><Note tone="err">{errText(hits.error, 'CRM okunamadı.')}</Note></div>}
      {hits.data && (
        <p className="mt-2 text-[11px] text-canvas-muted">
          <SqlInfo k={hits.data.kaynaklar} alan="total" label="Kitap araması" /> {hits.data.total === 0 ? 'Eşleşen kitap yok.' : hits.data.total > hits.data.shown ? `${hits.data.total} eşleşme; en iyi ${hits.data.shown} gösteriliyor, aramayı daraltın.` : `${hits.data.total} eşleşme.`}
        </p>
      )}
      <ul className="mt-2 flex flex-col gap-1.5">
        {hits.data?.items.map((b) => (
          <li key={b.stokKodu}>
            <button type="button" disabled={busy} onClick={() => { onPick(b.stokKodu); setQ(''); }}
              className="flex min-h-11 w-full items-start justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2 text-left transition-transform duration-150 ease-out hover:bg-slate-100 active:scale-[0.98]">
              <span className="min-w-0">
                <span className="block break-words text-[12.5px] font-bold">{b.ad ?? b.stokKodu}</span>
                <span className="block text-[11px] text-canvas-muted">{b.yazar ?? '—'} · <span className="font-mono">{b.stokKodu}</span></span>
              </span>
              {b.satisDisi && <Pill tone="err">{b.durum ?? 'satış dışı'}</Pill>}
            </button>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}
