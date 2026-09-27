import { useCallback, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls, TableWrap, th, td } from '../admin/ui';
import { Kpi, KpiRow, Panel, useDebounced } from '../editorial/kit';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { fmtDay } from '../budget/api';
import { Tabs } from '../budget/parts';
import { BOOK_TONE, distApi, type Book, type BookState } from './api';
import { DataEnd, DistFrame, n0 } from './parts';
import TrackingTab from './TrackingTab';
import MyRegion from './MyRegion';
import AlertsTab from './AlertsTab';

/** M29 İlk dağılım: dağılım bekleyen kitaplar, izlenenler, BMT görünümü (Bölgem), uyarılar. Sekme adreste (?sekme=). */

const TABS = [
  { key: 'bekleyen', label: 'Dağılım bekleyenler' },
  { key: 'izlenen', label: 'İzlenen kitaplar' },
  { key: 'bolgem', label: 'Bölgem' },
  { key: 'uyarilar', label: 'Uyarılar' },
] as const;
type Tab = (typeof TABS)[number]['key'];

const FILTERS: Array<{ key: string; label: string }> = [
  { key: 'bekleyen', label: 'Planı onaylanmamış' },
  { key: 'yok', label: 'Plan yok' },
  { key: 'onayda', label: 'Onayda' },
  { key: 'onayli', label: 'Onaylı' },
  { key: 'sevkte', label: 'Sevkte' },
  { key: '', label: 'Hepsi' },
];

/** Zeki AI'a sorulabilecek örnekler (analiz belgesi §5); Genel bakıştaki soru kutusuna gider. */
const ASK = [
  'Geçen ay çıkan romanların ilk 4 haftada en çok hangi bölgede sattı?',
  "D&R'a ilk dağılımda gönderdiğimiz adetin ne kadarı 90 günde iade geldi?",
  'Bu hafta sevk edilmemiş dağılım satırı var mı?',
  "Ege'ye gönderdiğimiz yeni çocuk kitaplarından hangisi hiç satmadı?",
];

export default function DistributionScreen() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const pages = usePageAccess();
  const meta = useQuery({ queryKey: ['dist', 'meta'], queryFn: distApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const me = meta.data?.me;
  // Bütün carileri göremeyen kişi (BMT) doğrudan kendi bölgesine iner.
  const fallbackTab: Tab = me && !me.canAll ? 'bolgem' : 'bekleyen';
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? fallbackTab) as Tab;
  const durum = params.get('durum') ?? 'bekleyen';
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 250);

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v !== null) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  const books = useQuery({
    queryKey: ['dist', 'books', durum, dq],
    queryFn: () => distApi.books({ durum, q: dq }),
    enabled: ENGINE_ENABLED && !!meta.data,
  });
  const alertCount = useQuery({ queryKey: ['dist', 'alerts', 'acik', ''], queryFn: () => distApi.alerts({}), enabled: ENGINE_ENABLED && !!meta.data });

  const refresh = useMutation({
    mutationFn: distApi.refreshBooks,
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ['dist'] });
      toast.success(`${n0(r.kitap)} kitap okundu (Logo ${n0(r.logo)}, üretim kartı ${n0(r.m12)}).`);
      r.uyarilar.forEach((w) => toast.warning(w));
    },
    onError: (e) => toast.error(errText(e, 'Liste yenilenemedi.') ?? ''),
  });
  const generate = useMutation({
    mutationFn: (code: string) => distApi.generate(code),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: ['dist'] });
      nav(`/ilk-dagilim/${encodeURIComponent(p.stokKodu)}?plan=${p.id}`);
    },
    onError: (e) => toast.error(errText(e, 'Öneri kurulamadı.') ?? ''),
  });

  const data = books.data;
  const items = data?.items ?? [];
  const waiting = items.filter((b) => b.durum === 'yok').length;
  const canAsk = canOpenRoute(pages, '/genel-bakis');

  const aside = me?.canPlan ? (
    <div className="flex flex-wrap gap-2 lg:justify-end">
      <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={refresh.isPending}>
        {refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
        Depo girişlerini yenile
      </button>
    </div>
  ) : undefined;

  return (
    <DistFrame
      title="İlk dağılım"
      lead="Depoya giren kitabın hangi bölgeye, kanala ve müşteriye kaç adet gideceğini ZEKİ AI benzer kitapların ilk 8 haftasından önerir; satış düzeltir, lojistik onaylar, sevk listesi Excel'e iner. Onaylanan plan 8 hafta boyunca sevk, fatura ve iadeyle izlenir."
      source={meta.data?.veriSonu ? `Logo · ${fmtDay(meta.data.veriSonu)}'e kadar` : 'Logo + CRM'}
      presence={me ? (me.canAll ? 'Bütün bölgeler' : 'Kendi carileriniz') : '…'}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'İlk dağılım açılamadı.')}</Note>}
      {meta.data && <DataEnd veriSonu={meta.data.veriSonu} depoSonu={meta.data.depoSonu} />}

      {me?.canAll && data && (
        <KpiRow>
          <Kpi label="Plan bekleyen" value={n0(waiting)} help={`Son ${data.pencereGun} günde depoya girip planı olmayan kitap`} active={tab === 'bekleyen' && durum === 'yok'} onClick={() => update({ sekme: 'bekleyen', durum: 'yok' })} />
          <Kpi label="Listedeki kitap" value={n0(items.length)} help="Seçili süzgeçte" />
          <Kpi label="İzlenen" value={n0(data.izlenen.length)} help={`Onaydan sonraki ${meta.data?.params.takipHafta ?? 8} hafta`} active={tab === 'izlenen'} onClick={() => update({ sekme: 'izlenen' })} />
          <Kpi label="Açık uyarı" value={n0(alertCount.data?.total)} help="Plansız kitap, sevk gecikmesi, hiç satmayan bölge" active={tab === 'uyarilar'} onClick={() => update({ sekme: 'uyarilar' })} />
        </KpiRow>
      )}

      <Tabs
        tabs={TABS.filter((t) => me?.canAll || t.key !== 'bekleyen').map((t) => (t.key === 'uyarilar' ? { ...t, badge: alertCount.data?.total ?? null } : t))}
        value={tab}
        onChange={(k) => update({ sekme: k })}
      />

      {tab === 'bekleyen' && (
        <Panel>
          <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div className="-mx-1 overflow-x-auto px-1">
              <div className="flex w-max gap-1.5">
                {FILTERS.map((f) => (
                  <button
                    key={f.key || 'hepsi'}
                    type="button"
                    aria-pressed={durum === f.key}
                    onClick={() => update({ durum: f.key })}
                    className={`min-h-11 whitespace-nowrap rounded-xl px-3 text-[12px] font-bold transition-colors duration-150 sm:min-h-8 ${durum === f.key ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
            </div>
            <label className="flex w-full flex-col gap-1 sm:w-72">
              <span className={labelCls}>Kitap ara</span>
              <input className={field} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ad, stok kodu, yayınevi" />
            </label>
          </div>
          {books.error && <Note tone="err">{errText(books.error, 'Liste okunamadı.')}</Note>}
          {data?.uyarilar.map((w) => <Note key={w} tone="warn">{w}</Note>)}
          {books.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Okunuyor…</div>}
          {data && !items.length && (
            <div className="py-8 text-center text-[12.5px] text-canvas-muted">
              {data.asof ? 'Bu süzgeçte kitap yok.' : 'Liste henüz okunmadı. «Depo girişlerini yenile» ile Logo ve üretim kartlarından okunur; sonra her gün 07:30 ve 13:30\'da kendiliğinden tazelenir.'}
            </div>
          )}
          {!!items.length && <BookList items={items} canPlan={!!me?.canPlan} busy={generate.isPending ? generate.variables : undefined} onGenerate={(c) => generate.mutate(c)} />}
        </Panel>
      )}
      {tab === 'izlenen' && <TrackingTab items={data?.izlenen ?? []} loading={books.isLoading} />}
      {tab === 'bolgem' && <MyRegion canAll={!!me?.canAll} />}
      {tab === 'uyarilar' && <AlertsTab />}

      {canAsk && (
        <Panel>
          <div className="mb-2 flex items-center gap-2 text-[12px] font-extrabold">
            <Sparkles aria-hidden className="h-4 w-4 text-canvas-violet" />
            ZEKİ AI'a sorun
          </div>
          <div className="flex flex-wrap gap-2">
            {ASK.map((s) => (
              <Link key={s} to={`/genel-bakis?soru=${encodeURIComponent(s)}`} className="min-h-11 rounded-xl bg-slate-100 px-3 py-2 text-[12px] font-semibold text-canvas-ink transition-colors duration-150 hover:bg-slate-200 sm:min-h-0">
                {s}
              </Link>
            ))}
          </div>
        </Panel>
      )}
    </DistFrame>
  );
}

function StatePill({ b }: { b: Book }) {
  return <Pill tone={BOOK_TONE[b.durum as BookState]}>{b.durumEtiket}</Pill>;
}

function Action({ b, canPlan, busy, onGenerate }: { b: Book; canPlan: boolean; busy?: string; onGenerate: (c: string) => void }) {
  const to = `/ilk-dagilim/${encodeURIComponent(b.stokKodu)}${b.plan ? `?plan=${b.plan.id}` : ''}`;
  if (b.plan) return <Link to={to} className={btnGhost}>Planı aç</Link>;
  if (!canPlan) return <span className="text-[11.5px] text-canvas-muted">Plan yok</span>;
  return (
    <button type="button" className={btnPrimary} disabled={!!busy} onClick={() => onGenerate(b.stokKodu)}>
      {busy === b.stokKodu ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
      ZEKİ AI önerisi
    </button>
  );
}

function BookList({ items, canPlan, busy, onGenerate }: { items: Book[]; canPlan: boolean; busy?: string; onGenerate: (c: string) => void }) {
  return (
    <>
      {/* Telefon: kart listesi */}
      <ul className="flex flex-col gap-2 md:hidden">
        {items.map((b) => (
          <li key={b.stokKodu} className="rounded-2xl border border-slate-100 bg-white/80 p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="break-words text-[13px] font-extrabold leading-snug">{b.ad ?? b.stokKodu}</div>
                <div className="mt-0.5 font-mono text-[11px] text-canvas-muted">{b.stokKodu}</div>
              </div>
              <StatePill b={b} />
            </div>
            <div className="mt-2 grid grid-cols-3 gap-2 text-[11.5px]">
              <div><div className={labelCls}>Depo</div>{fmtDay(b.depoGiris)}</div>
              <div><div className={labelCls}>Baskı</div><span className="font-mono tabular-nums">{n0(b.baskiAdedi)}</span></div>
              <div><div className={labelCls}>Stok</div><span className="font-mono tabular-nums">{n0(b.stok)}</span></div>
            </div>
            <div className="mt-2 flex justify-end"><Action b={b} canPlan={canPlan} busy={busy} onGenerate={onGenerate} /></div>
          </li>
        ))}
      </ul>
      {/* Tablet ve masaüstü: tablo */}
      <div className="hidden md:block">
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Kitap</th>
              <th className={th}>Depoya giriş</th>
              <th className={th}>Baskı</th>
              <th className={`${th} text-right`}>Baskı adedi</th>
              <th className={`${th} text-right`}>Stok</th>
              <th className={`${th} text-right`}>Plan</th>
              <th className={th}>Durum</th>
              <th className={th} />
            </tr>
          </thead>
          <tbody>
            {items.map((b) => (
              <tr key={b.stokKodu} className="border-t border-slate-100">
                <td className={td}>
                  <div className="font-bold">{b.ad ?? b.stokKodu}</div>
                  <div className="font-mono text-[11px] text-canvas-muted">{b.stokKodu}{b.yayinevi ? ` · ${b.yayinevi}` : ''}</div>
                </td>
                <td className={td}>
                  {fmtDay(b.depoGiris)}
                  {b.kaynak === 'm12' && <div className="text-[11px] text-canvas-muted">üretim kartından</div>}
                </td>
                <td className={td}>{b.ilkBaski === false ? `Tekrar${b.baskiNo ? ` (${b.baskiNo}.)` : ''}` : 'İlk baskı'}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{n0(b.baskiAdedi)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{n0(b.stok)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>
                  {b.plan ? <>{n0(b.plan.toplam)}<div className="text-[11px] text-canvas-muted">rezerv {n0(b.plan.rezerv)}</div></> : '—'}
                </td>
                <td className={td}><StatePill b={b} /></td>
                <td className={`${td} text-right`}><Action b={b} canPlan={canPlan} busy={busy} onGenerate={onGenerate} /></td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </div>
    </>
  );
}

