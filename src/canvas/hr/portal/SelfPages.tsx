import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Cake, ChevronDown, ChevronLeft, ChevronRight, Download, FileText, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../../admin/ui';
import { EmptyHint } from '../../components/Explain';
import { AskSheet, Block, HrFrame, Tabs } from '../parts';
import { fileSize, localIso, longDay, monthName, portalApi, portalSrc, weekday, type DocRequest } from './portalApi';

const BACK = { to: '/ik', label: 'İK ana sayfası' };

/* ------------------------------------------------------------------ Şirket içi duyurular */

export function PostsPage() {
  const q = useQuery({ queryKey: ['hr', 'portal', 'posts'], queryFn: portalApi.posts, enabled: ENGINE_ENABLED });
  const [cat, setCat] = useState('');
  const items = q.data?.items ?? [];
  const cats = [...new Set(items.map((p) => p.category))];
  const shown = items.filter((p) => !cat || p.category === cat);
  useEffect(() => {
    // Ana sayfadaki bağlantı (#id) duyuruya kaydırır.
    const id = window.location.hash.slice(1);
    if (id && q.data) document.getElementById(id)?.scrollIntoView({ block: 'start' });
  }, [q.data]);
  return (
    <HrFrame crumb="Şirket içi duyurular" title="Şirket içi duyurular" back={BACK}
      lead="İK'nın yayımladığı duyurular, en yeni önce."
      aside={cats.length > 1 ? (
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Kategori</span>
          <select className={field} value={cat} onChange={(e) => setCat(e.target.value)}>
            <option value="">Bütün kategoriler</option>
            {cats.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      ) : undefined}>
      {q.error && <Note tone="err">{errText(q.error, 'Duyurular okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !shown.length && <EmptyHint title="Henüz duyuru yok" why="İK duyuru yayımlayınca burada görünür." />}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 lg:gap-4">
        {shown.map((p) => (
          <article key={p.id} id={p.id} className="glass-panel flex scroll-mt-4 flex-col overflow-hidden rounded-2xl shadow-glass-float sm:rounded-3xl">
            {p.hasImage && <img src={portalSrc(`/portal/posts/${p.id}/image`)} alt="" loading="lazy" className="aspect-[16/9] w-full bg-slate-100 object-cover" />}
            <div className="flex flex-col gap-1 p-3 sm:p-4">
              <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-violet">{p.category} · {longDay(p.publishDate)}</div>
              <h2 className="text-[15px] font-extrabold leading-snug tracking-tight">{p.title}</h2>
              <p className="whitespace-pre-line break-words text-[13px] leading-relaxed">{p.body}</p>
            </div>
          </article>
        ))}
      </div>
    </HrFrame>
  );
}

/* ------------------------------------------------------------------ Doğum günleri */

export function BirthdaysPage() {
  const q = useQuery({ queryKey: ['hr', 'portal', 'birthdays'], queryFn: portalApi.birthdays, enabled: ENGINE_ENABLED });
  const now = new Date();
  const [month, setMonth] = useState(now.getMonth() + 1);
  const items = (q.data?.items ?? []).filter((b) => b.month === month);
  return (
    <HrFrame crumb="Doğum günleri" title="Doğum günleri" back={BACK}
      lead="Aktif çalışanların doğum günleri; yalnız gün ve ay görünür, yaş görünmez."
      aside={
        <div className="flex items-center justify-between gap-2 rounded-2xl bg-white/85 p-1.5">
          <button type="button" className={btnGhost} aria-label="Önceki ay" onClick={() => setMonth((m) => (m === 1 ? 12 : m - 1))}><ChevronLeft aria-hidden className="h-4 w-4" /></button>
          <span className="text-[14px] font-extrabold">{monthName(month)}</span>
          <button type="button" className={btnGhost} aria-label="Sonraki ay" onClick={() => setMonth((m) => (m === 12 ? 1 : m + 1))}><ChevronRight aria-hidden className="h-4 w-4" /></button>
        </div>
      }>
      {q.error && <Note tone="err">{errText(q.error, 'Doğum günleri okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !items.length && <EmptyHint icon={<Cake className="h-[18px] w-[18px]" />} title={`${monthName(month)} ayında doğum günü yok`} why="Doğum tarihi girilmiş aktif çalışanlar burada görünür." />}
      {items.length > 0 && (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((b) => (
            <li key={b.id} className={`flex items-center gap-3 rounded-2xl p-3 shadow-sm ${b.inDays === 0 ? 'bg-pink-50 ring-1 ring-pink-200' : 'bg-white/85'}`}>
              <span className="flex h-12 w-12 shrink-0 flex-col items-center justify-center rounded-xl bg-pink-100 text-pink-700">
                <span className="text-[17px] font-extrabold leading-none tabular-nums">{b.day}</span>
                <span className="text-[10px] font-bold uppercase">{monthName(b.month).slice(0, 3)}</span>
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-[13.5px] font-extrabold">{b.adSoyad}</div>
                <div className="truncate text-[12px] text-canvas-muted">{[b.departman, b.unvan].filter(Boolean).join(' · ') || '—'}</div>
              </div>
              {b.inDays === 0 && <Pill tone="violet">Bugün</Pill>}
            </li>
          ))}
        </ul>
      )}
    </HrFrame>
  );
}

/* ------------------------------------------------------------------ Yemek listesi */

const mondayOf = (d: Date) => {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  return x;
};

export function MenuPage() {
  const [start, setStart] = useState(() => mondayOf(new Date()));
  const end = new Date(start);
  end.setDate(end.getDate() + 13);
  const q = useQuery({ queryKey: ['hr', 'portal', 'menu', localIso(start)], queryFn: () => portalApi.menu(localIso(start), localIso(end)), enabled: ENGINE_ENABLED });
  const today = localIso(new Date());
  const shift = (weeks: number) => setStart((s) => { const x = new Date(s); x.setDate(x.getDate() + weeks * 7); return x; });
  const days = q.data?.days ?? [];
  return (
    <HrFrame crumb="Yemek listesi" title="Yemek listesi" back={BACK}
      lead="İki haftalık menü. İK her hafta girer; girilmeyen gün boş görünür."
      aside={
        <div className="flex items-center justify-between gap-2 rounded-2xl bg-white/85 p-1.5">
          <button type="button" className={btnGhost} aria-label="Önceki hafta" onClick={() => shift(-1)}><ChevronLeft aria-hidden className="h-4 w-4" /></button>
          <span className="text-center text-[12.5px] font-extrabold">{longDay(localIso(start))} – {longDay(localIso(end))}</span>
          <button type="button" className={btnGhost} aria-label="Sonraki hafta" onClick={() => shift(1)}><ChevronRight aria-hidden className="h-4 w-4" /></button>
        </div>
      }>
      {q.error && <Note tone="err">{errText(q.error, 'Menü okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !days.length && <EmptyHint title="Bu iki hafta için menü girilmemiş" why="İK yemek listesini girince burada görünür." />}
      {days.length > 0 && (
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-5">
          {days.map((d) => (
            <li key={d.day} className={`rounded-2xl p-3 shadow-sm ${d.day === today ? 'bg-orange-50 ring-1 ring-orange-200' : 'bg-white/85'}`}>
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="text-[12.5px] font-extrabold capitalize">{weekday(d.day)}</span>
                {d.day === today && <Pill tone="warn">Bugün</Pill>}
              </div>
              <ul className="flex flex-col gap-0.5 text-[12.5px]">
                {d.items.map((x, i) => <li key={i}>{x}</li>)}
              </ul>
            </li>
          ))}
        </ul>
      )}
    </HrFrame>
  );
}

/* ------------------------------------------------------------------ Evrak deposu ve evrak talebi */

const DOC_TABS = [{ key: 'depo', label: 'Evrak deposu' }, { key: 'talep', label: 'Evrak talebi' }] as const;

export function DocsPage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('sekme') === 'talep' ? 'talep' : 'depo';
  return (
    <HrFrame crumb="Evrak" title="Evrak" back={BACK}
      lead="İK formları ve rehberleri indirin; çalışma belgesi, bordro, hizmet dökümü gibi belgeleri İK'dan isteyin.">
      <Tabs tabs={DOC_TABS} value={tab} onChange={(t) => setParams(t === 'depo' ? {} : { sekme: t }, { replace: true })} />
      {tab === 'depo' ? <DocStore /> : <MyRequests />}
    </HrFrame>
  );
}

function DocStore() {
  const q = useQuery({ queryKey: ['hr', 'portal', 'docs'], queryFn: portalApi.docs, enabled: ENGINE_ENABLED });
  const items = q.data?.items ?? [];
  const cats = [...new Set(items.map((d) => d.category))];
  if (q.error) return <Note tone="err">{errText(q.error, 'Evrak deposu okunamadı.')}</Note>;
  if (q.isLoading) return <Loading />;
  if (!items.length) return <EmptyHint title="Evrak deposu boş" why="İK form ve rehber yükleyince burada görünür." />;
  return (
    <>
      {cats.map((c) => (
        <Block key={c} title={c}>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {items.filter((d) => d.category === c).map((d) => (
              <li key={d.id}>
                <button type="button" onClick={() => void portalApi.docFile(d).catch((e) => toast.error(errText(e, 'İndirilemedi.')))}
                  className="flex min-h-[60px] w-full items-center gap-3 rounded-xl bg-white/85 px-3 py-2 text-left shadow-sm transition-transform duration-150 ease-out active:scale-[0.98]">
                  <FileText aria-hidden className="h-5 w-5 shrink-0 text-teal-700" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] font-bold">{d.title}</span>
                    <span className="block truncate text-[11.5px] text-canvas-muted">{[d.code, fileSize(d.size)].filter(Boolean).join(' · ')}</span>
                  </span>
                  <Download aria-hidden className="h-4 w-4 shrink-0 text-canvas-violet" />
                </button>
              </li>
            ))}
          </ul>
        </Block>
      ))}
    </>
  );
}

const TONE: Record<string, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = { bekliyor: 'warn', hazirlaniyor: 'violet', hazir: 'ok', red: 'err' };

function MyRequests() {
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['hr', 'portal', 'meta'], queryFn: portalApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useQuery({ queryKey: ['hr', 'portal', 'requests'], queryFn: portalApi.myRequests, enabled: ENGINE_ENABLED });
  const [docType, setDocType] = useState('');
  const [delivery, setDelivery] = useState('eposta');
  const [mail, setMail] = useState<string | null>(null);
  const [note, setNote] = useState('');
  const [cancel, setCancel] = useState<DocRequest | null>(null);
  const mailValue = mail ?? list.data?.defaultMail ?? '';
  const create = useMutation({
    mutationFn: () => portalApi.createRequest({ docType, delivery, mail: mailValue, note }),
    onSuccess: () => {
      toast.success('Talebiniz İK’ya iletildi.');
      setDocType(''); setNote('');
      void qc.invalidateQueries({ queryKey: ['hr', 'portal'] });
    },
    onError: (e) => toast.error(errText(e, 'Talep gönderilemedi.')),
  });
  const del = useMutation({
    mutationFn: (id: string) => portalApi.cancelRequest(id),
    onSuccess: () => { setCancel(null); toast.success('Talep geri alındı.'); void qc.invalidateQueries({ queryKey: ['hr', 'portal'] }); },
    onError: (e) => toast.error(errText(e, 'Geri alınamadı.')),
    onSettled: () => setCancel(null),
  });
  const types = meta.data?.settings.docTypes ?? [];
  const deliveries = Object.entries(meta.data?.delivery ?? {});
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,420px)_1fr] lg:gap-4">
      <Block title="Yeni talep" help="İK talebi görür, hazırlayınca durumunu buradan izlersiniz.">
        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Evrak tipi</span>
            <select className={field} value={docType} onChange={(e) => setDocType(e.target.value)} required>
              <option value="" disabled>Seçin</option>
              {types.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <fieldset className="flex flex-col gap-1">
            <legend className={labelCls}>Teslim şekli</legend>
            <div className="mt-1 grid grid-cols-2 gap-2">
              {deliveries.map(([k, v]) => (
                <label key={k} className={`flex min-h-11 cursor-pointer items-center justify-center rounded-xl px-2 text-center text-[12.5px] font-bold transition-colors duration-150 ${delivery === k ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'}`}>
                  <input type="radio" name="delivery" value={k} checked={delivery === k} onChange={() => setDelivery(k)} className="sr-only" />
                  {v}
                </label>
              ))}
            </div>
          </fieldset>
          {delivery === 'eposta' && (
            <label className="flex flex-col gap-1">
              <span className={labelCls}>E-posta adresiniz</span>
              <input type="email" className={field} value={mailValue} onChange={(e) => setMail(e.target.value)} required autoComplete="email" />
            </label>
          )}
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Not (isteğe bağlı)</span>
            <textarea className={`${field} min-h-[80px]`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ör. hangi kuruma verilecek, hangi dönem" />
          </label>
          <button type="submit" className={btnPrimary} disabled={!docType || create.isPending}>{create.isPending ? 'Gönderiliyor…' : 'Talep oluştur'}</button>
        </form>
      </Block>
      <Block title="Taleplerim">
        {list.error && <Note tone="err">{errText(list.error, 'Talepler okunamadı.')}</Note>}
        {list.isLoading && <Loading />}
        {list.data && !list.data.items.length && <EmptyHint title="Henüz talebiniz yok" />}
        <ul className="flex flex-col gap-2">
          {(list.data?.items ?? []).map((r) => (
            <li key={r.id} className="rounded-xl bg-white/85 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-[13px] font-bold">{r.docType}</span>
                <Pill tone={TONE[r.status] ?? 'muted'}>{r.statusLabel}</Pill>
              </div>
              <div className="text-[11.5px] text-canvas-muted">{longDay(r.createdAt)} · {r.deliveryLabel}{r.mail ? ` · ${r.mail}` : ''}</div>
              {r.note && <div className="mt-1 whitespace-pre-line text-[12px]">{r.note}</div>}
              {r.answer && <div className="mt-1 rounded-lg bg-slate-50 px-2 py-1 text-[12px]"><span className="font-bold">İK:</span> {r.answer}</div>}
              {r.status === 'bekliyor' && (
                <button type="button" className="mt-1 text-[12px] font-bold text-red-700 hover:underline" onClick={() => setCancel(r)}>Geri al</button>
              )}
            </li>
          ))}
        </ul>
      </Block>
      <AskSheet open={!!cancel} title="Talebi geri al" danger confirm="Geri al" busy={del.isPending}
        message={<>«{cancel?.docType}» talebiniz silinecek. Bu işlem geri alınamaz.</>}
        onClose={() => setCancel(null)} onConfirm={() => cancel && del.mutate(cancel.id)} />
    </div>
  );
}

/* ------------------------------------------------------------------ Sık sorulan sorular */

export function FaqPage() {
  const q = useQuery({ queryKey: ['hr', 'portal', 'faq'], queryFn: portalApi.faq, enabled: ENGINE_ENABLED });
  const [text, setText] = useState('');
  const t = text.trim().toLocaleLowerCase('tr-TR');
  const items = (q.data?.items ?? []).filter((f) => !t || `${f.question} ${f.answer}`.toLocaleLowerCase('tr-TR').includes(t));
  const cats = [...new Set(items.map((f) => f.category))];
  return (
    <HrFrame crumb="Sık sorulan sorular" title="Sık sorulan sorular" back={BACK}
      lead="İzin, ücret, çalışma düzeni ve eğitim hakkında İK'nın cevapları. Burada olmayan soruyu İK'ya sorun."
      aside={
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Ara</span>
          <span className="relative flex items-center">
            <Search aria-hidden className="pointer-events-none absolute left-3 h-4 w-4 text-canvas-muted" />
            <input className={`${field} pl-9`} value={text} onChange={(e) => setText(e.target.value)} placeholder="Ör. yıllık izin" />
          </span>
        </label>
      }>
      {q.error && <Note tone="err">{errText(q.error, 'Sorular okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !items.length && <EmptyHint title={text ? 'Aramaya uyan soru yok' : 'Henüz soru eklenmemiş'} />}
      {cats.map((c) => (
        <Block key={c} title={c}>
          <div className="flex flex-col divide-y divide-slate-100">
            {items.filter((f) => f.category === c).map((f) => (
              <details key={f.id} className="group py-1">
                <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 text-[13px] font-bold [&::-webkit-details-marker]:hidden">
                  {f.question}
                  <ChevronDown aria-hidden className="h-4 w-4 shrink-0 text-canvas-muted transition-transform duration-200 ease-out group-open:rotate-180 motion-reduce:transition-none" />
                </summary>
                <p className="whitespace-pre-line pb-2 text-[13px] leading-relaxed text-canvas-ink">{f.answer}</p>
              </details>
            ))}
          </div>
        </Block>
      ))}
    </HrFrame>
  );
}

