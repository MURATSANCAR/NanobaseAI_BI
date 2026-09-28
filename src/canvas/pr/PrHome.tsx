import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Kpi, KpiRow, useDebounced } from '../editorial/kit';
import { KIT_TONE, SEND_TONE, TONE_TONE, fmtDay, monthLabel, prApi, type Book, type KitHead } from './api';
import { Block, Empty, PrFrame } from './parts';

/** M20 Basın ilişkileri — «Bugün»: ayın kitapları ve PR dosyası durumu, onay bekleyenler, takip günü geçen
 *  gönderimler, son 30 günün yansımaları. Ay adres çubuğunda (?ay=YYYY-AA). */

const shift = (ym: string, n: number) => {
  const [y, m] = ym.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + n, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};

export default function PrHome() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const now = new Date();
  const ay = params.get('ay') || `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const setAy = (v: string) => {
    const p = new URLSearchParams(params);
    p.set('ay', v);
    setParams(p, { replace: true });
  };
  const meta = useQuery({ queryKey: ['pr', 'meta'], queryFn: prApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const home = useQuery({ queryKey: ['pr', 'home', ay], queryFn: () => prApi.home(ay), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const refresh = useMutation({
    mutationFn: () => prApi.home(ay, true),
    onSuccess: (d) => qc.setQueryData(['pr', 'home', ay], d),
    onError: (e) => toast.error(errText(e, 'CRM okunamadı.') ?? ''),
  });
  const [busy, setBusy] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: async (bid: string) => {
      setBusy(bid);
      return prApi.createKit(bid);
    },
    onSuccess: (kit) => {
      qc.invalidateQueries({ queryKey: ['pr'] });
      toast.success('PR dosyası açıldı.');
      nav(`/basin-iliskileri/dosya/${encodeURIComponent(kit.id)}`);
    },
    onError: (e) => toast.error(errText(e, 'Dosya açılamadı.') ?? ''),
    onSettled: () => setBusy(null),
  });

  const m = meta.data;
  const d = home.data;
  const canEdit = !!m?.me.canEdit;

  return (
    <PrFrame
      crumb="Basın ilişkileri"
      title="Basın ilişkileri"
      lead="Kitap başına PR dosyası (bülten, kişiye özel e-posta, gönderim listesi), medya kişileri ve yansımalar. Zeki AI taslak yazar, pazarlama müdürü onaylar; gazeteciye e-posta yalnız onaylı satırdan, tek tek ve bir kişinin elinden gider."
      source={d?.webWatch ? 'CRM + Basın ve web taraması' : 'CRM · web taraması bu ortamda kapalı'}
      presence={d ? `${d.kpi.books.toLocaleString('tr-TR')} kitap` : '…'}
      aside={<BookSearch />}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Basın ilişkileri açılamadı.')}</Note>}
      {d?.booksError && <Note tone="warn">{d.booksError} Portaldaki dosyalar ve yansımalar yine görünür.</Note>}

      {d && (
        <KpiRow>
          <Kpi label="Dosyası yok" value={d.kpi.noKit.toLocaleString('tr-TR')} help={`${monthLabel(d.month)} ayında çıkan ${d.kpi.books} kitaptan`} info={<SqlInfo k={d.kaynaklar} alan="kpi" label="Dosyası yok" />} />
          <Kpi label="Onay bekleyen" value={d.kpi.pending.toLocaleString('tr-TR')} help="Onaya gönderilmiş PR dosyası" info={<SqlInfo k={d.kaynaklar} alan="pending" label="Onay bekleyen" />} />
          <Kpi label="Cevap bekleyen" value={d.kpi.overdue.toLocaleString('tr-TR')} help={`Gönderimden ${m?.settings.followUpDays ?? 5} gün geçti, dönüş yok`} info={<SqlInfo k={d.kaynaklar} alan="overdue" label="Cevap bekleyen" />} />
          <Kpi label="Son 30 gün yansıma" value={d.kpi.recent.toLocaleString('tr-TR')} help={d.kpi.candidates ? `${d.kpi.candidates} aday onay bekliyor` : 'Kayıtlı yansıma'} info={<SqlInfo k={d.kaynaklar} alan="kpi" label="Son 30 gün yansıma ve aday" />} />
        </KpiRow>
      )}

      <Block
        title={`${monthLabel(ay)} ayında çıkan kitaplar`}
        help="CRM kitap kartındaki ilk baskı tarihi. Önem derecesi yüksek olan üstte."
        info={<SqlInfo k={d?.kaynaklar} alan="books" label="Ayın kitapları, gönderim ve yansıma sayıları" />}
        action={
          <div className="flex items-center gap-1.5">
            <button type="button" className={btnGhost} aria-label="Önceki ay" onClick={() => setAy(shift(ay, -1))}>
              <ChevronLeft aria-hidden className="h-4 w-4" />
            </button>
            <button type="button" className={btnGhost} aria-label="Sonraki ay" onClick={() => setAy(shift(ay, 1))}>
              <ChevronRight aria-hidden className="h-4 w-4" />
            </button>
            <button type="button" className={btnGhost} onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <RefreshCw aria-hidden className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">CRM'den yenile</span>
            </button>
          </div>
        }
      >
        {home.isLoading && <Loading />}
        {home.error && <Note tone="err">{errText(home.error, 'Liste açılamadı.')}</Note>}
        {d && d.books.length === 0 && <Empty>Bu ay ilk baskı tarihi olan kitap yok. Başka bir ay seçin ya da sağdaki aramayla kitabı bulun.</Empty>}
        {d && d.books.length > 0 && (
          <ul className="grid grid-cols-1 gap-2 md:grid-cols-2 2xl:grid-cols-3">
            {d.books.map((b) => (
              <BookRow key={b.kitapId} b={b} canEdit={canEdit} busy={busy} onCreate={(id) => create.mutate(id)} />
            ))}
          </ul>
        )}
      </Block>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
        <Block title="Onay bekleyen dosyalar" help="Bülten ve gönderim listesi birlikte onaylanır; gönderen onaylayamaz." info={<SqlInfo k={d?.kaynaklar} alan="pending" label="Onay bekleyen dosyalar" />}>
          {d && d.pending.length === 0 && <Empty>Onay bekleyen dosya yok.</Empty>}
          <ul className="flex flex-col gap-2">
            {d?.pending.map((k) => <KitLine key={k.id} k={k} />)}
          </ul>
        </Block>
        <Block title="Cevap bekleyen gönderimler" help="Takip günü geçmiş, durumu «gönderildi» kalan satırlar. Tek tıkla işaretlemek için dosyayı açın." info={<SqlInfo k={d?.kaynaklar} alan="overdue" label="Cevap bekleyen gönderimler" />}>
          {d && d.overdue.length === 0 && <Empty>Takip günü geçen gönderim yok.</Empty>}
          <ul className="flex flex-col gap-2">
            {d?.overdue.map((s) => (
              <li key={s.id}>
                <Link to={`/basin-iliskileri/dosya/${encodeURIComponent(s.kitId)}`} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-100 bg-white/85 p-3 transition-colors duration-150 hover:border-canvas-violet/40">
                  <span className="min-w-0">
                    <span className="block break-words text-[13px] font-extrabold">{s.contactName}</span>
                    <span className="block text-[11.5px] text-canvas-muted">{[s.outlet, s.bookTitle].filter(Boolean).join(' · ')}</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11.5px]">
                    <Pill tone={SEND_TONE[s.status]}>{s.statusLabel}</Pill>
                    <span className="text-canvas-muted">takip {fmtDay(s.followUpAt)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Block>
      </div>

      <Block
        title="Son yansımalar"
        help="Son 30 günde kayıtlı yansımalar (elle girilen ve kabul edilen tarama adayları)."
        info={<SqlInfo k={d?.kaynaklar} alan="recentCoverage" label="Son yansımalar" />}
        action={<Link to="/basin-iliskileri/yansimalar" className={btnGhost}>Tümü ve yeni kayıt</Link>}
      >
        {d && d.recentCoverage.length === 0 && <Empty>Son 30 günde kayıtlı yansıma yok. Çıkan haberin bağlantısını «Yansımalar»dan ekleyin.</Empty>}
        <ul className="flex flex-col divide-y divide-slate-100">
          {d?.recentCoverage.map((c) => (
            <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="break-words text-[13px] font-bold leading-snug">
                  {c.url ? (
                    <a href={c.url} target="_blank" rel="noreferrer" className="inline-flex items-start gap-1 hover:underline">
                      {c.title}
                      <ExternalLink aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-canvas-muted" />
                    </a>
                  ) : c.title}
                </div>
                <div className="text-[11.5px] text-canvas-muted">{[fmtDay(c.publishedAt), c.outlet, c.bookTitle].filter((x) => x && x !== '—').join(' · ')}</div>
              </div>
              {c.tone && <Pill tone={TONE_TONE[c.tone]}>{c.toneLabel}</Pill>}
            </li>
          ))}
        </ul>
      </Block>
    </PrFrame>
  );
}

function BookRow({ b, canEdit, busy, onCreate }: { b: Book & { kit: KitHead | null }; canEdit: boolean; busy: string | null; onCreate: (id: string) => void }) {
  return (
    <li className="flex flex-col gap-2 rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex items-start justify-between gap-2">
        <Link to={`/basin-iliskileri/kitap/${encodeURIComponent(b.kitapId)}`} className="min-w-0 hover:underline">
          <span className="block break-words text-[14px] font-extrabold leading-snug">{b.ad ?? b.stokKodu}</span>
          <span className="mt-0.5 block text-[11.5px] text-canvas-muted">{[b.yazar, b.yayinevi].filter(Boolean).join(' · ') || '—'}</span>
        </Link>
        {b.onemAdi && <Pill tone={b.onem === 100000001 ? 'err' : b.onem === 100000002 ? 'warn' : 'muted'}>{b.onemAdi}</Pill>}
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-[11.5px]">
        <span className="font-semibold">{fmtDay(b.yayinTarihi)}</span>
        {b.kit ? <Pill tone={KIT_TONE[b.kit.status]}>{b.kit.statusLabel}</Pill> : <Pill tone="muted">Dosya yok</Pill>}
        {b.kit && <span className="text-canvas-muted">{b.kit.sentCount ?? 0}/{b.kit.sendCount ?? 0} gönderim · {b.kit.coverageCount ?? 0} yansıma</span>}
      </div>
      <div className="mt-auto flex gap-1.5">
        {b.kit ? (
          <Link to={`/basin-iliskileri/dosya/${encodeURIComponent(b.kit.id)}`} className={`${btnGhost} flex-1`}>Dosyayı aç</Link>
        ) : canEdit ? (
          <button type="button" className={`${btnPrimary} flex-1`} disabled={!!busy} onClick={() => onCreate(b.kitapId)}>
            {busy === b.kitapId && <Loader2 aria-hidden className="h-4 w-4 animate-spin" />}
            PR dosyası aç
          </button>
        ) : (
          <span className="text-[11.5px] text-canvas-muted">Dosya yok</span>
        )}
      </div>
    </li>
  );
}

function KitLine({ k }: { k: KitHead }) {
  return (
    <li>
      <Link to={`/basin-iliskileri/dosya/${encodeURIComponent(k.id)}`} className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border border-slate-100 bg-white/85 p-3 transition-colors duration-150 hover:border-canvas-violet/40">
        <span className="min-w-0">
          <span className="block break-words text-[13px] font-extrabold">{k.bookTitle}</span>
          <span className="block text-[11.5px] text-canvas-muted">{k.id} · gönderen {k.submittedBy ?? '—'}</span>
        </span>
        <Pill tone={KIT_TONE[k.status]}>{k.statusLabel}</Pill>
      </Link>
    </li>
  );
}

/** Ay listesinde olmayan kitap için arama (ad, yazar, stok kodu). */
function BookSearch() {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q.trim(), 300);
  const res = useQuery({
    queryKey: ['pr', 'book-search', dq, page],
    queryFn: () => prApi.searchBooks(dq, page),
    enabled: ENGINE_ENABLED && dq.length >= 2,
    placeholderData: keepPreviousData,
  });
  const last = res.data ? (page + 1) * res.data.pageSize >= res.data.total : true;
  return (
    <div className="relative">
      <label className="relative flex items-center">
        <span className="sr-only">Kitap ara</span>
        <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
        <input className={`${field} pl-9`} value={q} placeholder="Kitap ara: ad, yazar ya da stok kodu" onChange={(e) => { setQ(e.target.value); setPage(0); }} />
      </label>
      {dq.length >= 2 && (
        <div className="mt-1 max-h-[320px] overflow-y-auto rounded-2xl border border-slate-100 bg-white p-1 shadow-glass-float">
          {res.isLoading && <div className="p-2 text-[12px] text-canvas-muted">Aranıyor…</div>}
          {res.data && res.data.items.length === 0 && <div className="p-2 text-[12px] text-canvas-muted">Kitap bulunamadı.</div>}
          {res.data?.items.map((b) => (
            <Link key={b.kitapId} to={`/basin-iliskileri/kitap/${encodeURIComponent(b.kitapId)}`} className="block rounded-xl px-2 py-1.5 hover:bg-slate-50">
              <span className="block text-[12.5px] font-bold">{b.ad}</span>
              <span className="block text-[11px] text-canvas-muted">{[b.yazar, b.stokKodu, fmtDay(b.yayinTarihi)].filter((x) => x && x !== '—').join(' · ')}</span>
            </Link>
          ))}
          {res.data && res.data.total > res.data.pageSize && (
            <div className="flex items-center justify-between gap-2 p-1 text-[11px] text-canvas-muted">
              <span className="font-mono tabular-nums">
                {(page * res.data.pageSize + 1).toLocaleString('tr-TR')}–{(page * res.data.pageSize + res.data.items.length).toLocaleString('tr-TR')} / {res.data.total.toLocaleString('tr-TR')}
                <SqlInfo k={res.data.kaynaklar} alan="total" label="Kitap araması" />
              </span>
              <span className="flex gap-1">
                <button type="button" className={btnGhost} disabled={page === 0 || res.isFetching} onClick={() => setPage(page - 1)} aria-label="Önceki sayfa">
                  <ChevronLeft aria-hidden className="h-4 w-4" />
                </button>
                <button type="button" className={btnGhost} disabled={last || res.isFetching} onClick={() => setPage(page + 1)} aria-label="Sonraki sayfa">
                  <ChevronRight aria-hidden className="h-4 w-4" />
                </button>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
