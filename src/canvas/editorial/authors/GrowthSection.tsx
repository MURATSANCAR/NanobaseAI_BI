import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { toast } from 'sonner';
import { RefreshCw, Sparkles, Star, TrendingDown, TrendingUp } from 'lucide-react';
import { ENGINE_ENABLED, authorsApi, type AuthorAdvice, type AuthorGrowth } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText, nf } from '../../admin/ui';
import { useCan } from '../../useAdmin';
import { LOYALTY, fmtDay, monthLabel, monthLong } from './shared';

/** Yazarın gelişimi: Logo satış gidişatı (yıllık + son 24 ay + kitap kitap), M6 hakedişleri, okur sesi (sitedeki
 *  yorum puanı, açık web taramasının tonu), sadakat puanı ve Zeki AI strateji önerisi. Veri köprüde 12 saat
 *  saklanır; «Yenile» Logo'yu yeniden okur. */

const VIOLET = '#7C5CFF';
const money = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 });
const qtyFmt = (n: number) => nf.format(Math.round(n));

function Sub({ title, children, aside }: { title: string; children: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{title}</h4>
        {aside}
      </div>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function ChartTip({ active, payload, label, unit }: { active?: boolean; payload?: Array<{ value: number }>; label?: string; unit: (l: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[11.5px] shadow-md">
      <div className="font-semibold text-canvas-muted">{unit(String(label))}</div>
      <div className="font-mono font-bold tabular-nums">{qtyFmt(payload[0].value)} adet</div>
    </div>
  );
}

function SalesChart({ data, xKey, xLabel, tipLabel, title }: { data: Array<Record<string, number | string>>; xKey: string; xLabel: (v: string) => string; tipLabel: (v: string) => string; title: string }) {
  return (
    <figure aria-label={title}>
      <div className="h-32 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -18 }} barCategoryGap={2}>
            <CartesianGrid vertical={false} stroke="#EEF0F4" />
            <XAxis dataKey={xKey} tickFormatter={xLabel} tick={{ fontSize: 10, fill: '#64748B' }} tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={6} />
            <YAxis tickFormatter={(v: number) => compact.format(v)} tick={{ fontSize: 10, fill: '#64748B' }} tickLine={false} axisLine={false} width={44} />
            <Tooltip cursor={{ fill: 'rgba(124,92,255,0.08)' }} content={<ChartTip unit={tipLabel} />} />
            <Bar dataKey="qty" fill={VIOLET} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

function Sales({ g }: { g: AuthorGrowth }) {
  const [view, setView] = useState<'ay' | 'yil' | 'tablo'>('ay');
  const s = g.sales;
  const up = s.direction === 'artis';
  const down = s.direction === 'dusus';
  return (
    <Sub
      title="Satış (Logo)"
      aside={<span className="text-[10.5px] text-canvas-muted">veri sonu {fmtDay(g.dataEnd)}</span>}
    >
      <div className="grid grid-cols-3 gap-2">
        <div>
          <div className="text-[10.5px] text-canvas-muted">Son 12 ay</div>
          <div className="font-mono text-[18px] font-bold leading-tight tabular-nums">{qtyFmt(s.last12.qty)}</div>
          <div className="text-[10.5px] text-canvas-muted">adet</div>
        </div>
        <div>
          <div className="text-[10.5px] text-canvas-muted">Önceki 12 ay</div>
          <div className="font-mono text-[18px] font-bold leading-tight tabular-nums">{qtyFmt(s.prev12.qty)}</div>
          <div className="text-[10.5px] text-canvas-muted">adet</div>
        </div>
        <div>
          <div className="text-[10.5px] text-canvas-muted">Değişim</div>
          <div className={`flex items-center gap-1 font-mono text-[18px] font-bold leading-tight tabular-nums ${up ? 'text-emerald-700' : down ? 'text-rose-700' : ''}`}>
            {up && <TrendingUp aria-hidden className="h-4 w-4" />}
            {down && <TrendingDown aria-hidden className="h-4 w-4" />}
            {s.changePct === null ? '—' : `${s.changePct > 0 ? '+' : ''}${nf.format(s.changePct)}%`}
          </div>
          <div className="text-[10.5px] text-canvas-muted">{s.changePct === null ? 'önceki dönem satışı yok' : up ? 'artış' : down ? 'düşüş' : 'yatay'}</div>
        </div>
      </div>
      <div className="mt-1 text-[11px] text-canvas-muted">
        Net tutar son 12 ay {money.format(s.last12.net)} · iade {qtyFmt(s.last12.retQty)} adet · pencere {monthLong(s.window.from)} – {monthLong(s.window.to)}
      </div>
      <div className="mt-2 grid grid-cols-3 gap-1 rounded-xl bg-slate-100 p-1" role="tablist" aria-label="Satış görünümü">
        {(
          [
            ['ay', 'Son 24 ay'],
            ['yil', 'Yıllara göre'],
            ['tablo', 'Tablo'],
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            role="tab"
            aria-selected={view === k}
            onClick={() => setView(k)}
            className={`min-h-9 rounded-lg px-1 text-[11.5px] font-extrabold transition-colors duration-150 ${view === k ? 'bg-white shadow-sm' : 'text-canvas-muted hover:bg-white/60'}`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="mt-2">
        {view === 'ay' && <SalesChart title="Son 24 ayda aylık net satış adedi" data={s.series} xKey="month" xLabel={monthLabel} tipLabel={monthLong} />}
        {view === 'yil' && (
          <SalesChart title="Yıllara göre net satış adedi" data={s.years} xKey="year" xLabel={(v) => String(v)} tipLabel={(v) => `${v} yılı`} />
        )}
        {view === 'tablo' && (
          <div className="max-h-64 overflow-auto rounded-xl border border-slate-100">
            <table className="w-full text-[11.5px]">
              <caption className="sr-only">Yıllara göre net satış</caption>
              <thead className="sticky top-0 bg-white">
                <tr className="text-left text-[10.5px] uppercase tracking-wide text-canvas-muted">
                  <th className="px-2 py-1.5">Yıl</th>
                  <th className="px-2 py-1.5 text-right">Adet</th>
                  <th className="px-2 py-1.5 text-right">Net tutar</th>
                  <th className="px-2 py-1.5 text-right">İade</th>
                  <th className="px-2 py-1.5 text-right">Yeni kitap</th>
                </tr>
              </thead>
              <tbody>
                {s.years.map((y) => (
                  <tr key={y.year} className="border-t border-slate-100">
                    <td className="px-2 py-1.5 font-mono tabular-nums">{y.year}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">{qtyFmt(y.qty)}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">{money.format(y.net)}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">{qtyFmt(y.retQty)}</td>
                    <td className="px-2 py-1.5 text-right font-mono tabular-nums">{g.newBooksByYear.find((n) => n.year === y.year)?.count ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Sub>
  );
}

function Books({ g }: { g: AuthorGrowth }) {
  const [all, setAll] = useState(false);
  const list = all ? g.books : g.books.slice(0, 5);
  return (
    <Sub title={`Kitaplar · ${g.booksTotal}`} aside={g.booksWithCode < g.booksTotal ? <span className="text-[10.5px] text-amber-800">{g.booksTotal - g.booksWithCode} kitapta stok kodu yok</span> : undefined}>
      <ul className="space-y-1">
        {list.map((b) => (
          <li key={b.id} className="flex items-baseline justify-between gap-2 text-[12px]">
            <span className="min-w-0 break-words">
              {b.title || 'Adsız kitap'}
              {b.firstPublished && <span className="ml-1 text-[10.5px] text-canvas-muted">{b.firstPublished.slice(0, 4)}</span>}
            </span>
            <span className="shrink-0 text-right font-mono text-[11.5px] tabular-nums">
              {b.hasCode ? `${qtyFmt(b.qty)} adet` : <span className="text-canvas-muted">kod yok</span>}
            </span>
          </li>
        ))}
      </ul>
      {g.books.length > 5 && (
        <button type="button" className="mt-1.5 text-[12px] font-extrabold text-canvas-violet underline" onClick={() => setAll((v) => !v)}>
          {all ? 'Daha az göster' : `Bütün kitaplar (${g.books.length})`}
        </button>
      )}
      <p className="mt-1 text-[10.5px] text-canvas-muted">
        Adet ve tutar Logo'da {g.sales.years[0]?.year ?? '—'} yılından bu yana, faturalı satır, iade düşülmüş; 157 ile başlayan kodlar ve bedelsiz satırlar
        Baskı önerisi ve hakediş hesabıyla aynı kuralla sayılmaz.
      </p>
    </Sub>
  );
}

function Royalty({ g }: { g: AuthorGrowth }) {
  const st = g.royalty.statements;
  return (
    <Sub title="Telif (hakediş)">
      {st.length === 0 ? (
        <p className="text-[12px] text-canvas-muted">
          {g.royalty.contracts ? `${g.royalty.contracts} sözleşmesi var; ` : ''}portalda hesaplanmış hakediş yok. Hakediş sözleşme oranıyla{' '}
          <Link to="/telif-sozlesme" className="font-bold text-canvas-violet underline">
            Sözleşmeler
          </Link>{' '}
          ekranında hesaplanır; burada tahmin üretilmez.
        </p>
      ) : (
        <ul className="space-y-1 text-[12px]">
          {st.map((r, i) => (
            <li key={i} className="flex flex-wrap items-baseline justify-between gap-x-2">
              <span className="min-w-0">
                <span className="font-mono text-[11.5px] tabular-nums">{r.contractNo}</span>{' '}
                <span className="text-canvas-muted">
                  {fmtDay(r.periodStart)} – {fmtDay(r.periodEnd)}
                </span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="font-mono tabular-nums">{new Intl.NumberFormat('tr-TR', { style: 'currency', currency: r.currency || 'TRY', maximumFractionDigits: 0 }).format(r.net)}</span>
                <Pill tone={r.approved ? 'ok' : 'muted'}>{r.approved ? 'onaylı' : 'taslak'}</Pill>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Sub>
  );
}

function Readers({ g }: { g: AuthorGrowth }) {
  const site = g.readers.site;
  const web = g.readers.web;
  const maxStar = Math.max(1, ...Object.values(site.stars));
  return (
    <Sub title="Okur sesi">
      {!site.available ? (
        <p className="text-[12px] text-canvas-muted">Sitedeki yorum özeti bu ortamda yok.</p>
      ) : site.comments === 0 ? (
        <p className="text-[12px] text-canvas-muted">Yazarın kitaplarında sitede yorum yok.</p>
      ) : (
        <div>
          <div className="flex items-baseline gap-2">
            <Star aria-hidden className="h-4 w-4 self-center fill-amber-400 text-amber-400" />
            <span className="font-mono text-[18px] font-bold tabular-nums">{site.average !== null ? nf.format(site.average) : '—'}</span>
            <span className="text-[11.5px] text-canvas-muted">
              / 5 · {nf.format(site.rated)} puanlı, {nf.format(site.comments)} yorum (timas.com.tr)
            </span>
          </div>
          <ul className="mt-1.5 space-y-0.5" aria-label="Yıldız dağılımı">
            {['5', '4', '3', '2', '1'].map((k) => (
              <li key={k} className="flex items-center gap-2 text-[11px]">
                <span className="w-6 font-mono tabular-nums text-canvas-muted">{k}★</span>
                <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <span className="block h-full rounded-full bg-amber-400" style={{ width: `${(site.stars[k] / maxStar) * 100}%` }} />
                </span>
                <span className="w-8 text-right font-mono tabular-nums">{nf.format(site.stars[k])}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {web && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11.5px]">
          <span className="text-canvas-muted">Basın ve web:</span>
          <Pill tone="ok">olumlu {web.olumlu ?? 0}</Pill>
          <Pill tone="muted">nötr {web.notr ?? 0}</Pill>
          <Pill tone="err">olumsuz {web.olumsuz ?? 0}</Pill>
        </div>
      )}
    </Sub>
  );
}

function Loyalty({ g }: { g: AuthorGrowth }) {
  const l = g.loyalty;
  const rows: Array<[string, number, number, string]> = [
    ['Birliktelik süresi', l.parts.years, 30, l.since ? `${fmtDay(l.since)}'den beri` : 'iz yok'],
    ['Külliyat', l.parts.books, 25, `${l.books} kitap`],
    ['Süreklilik', l.parts.recent, 20, l.last ? `son iz ${fmtDay(l.last)}` : 'iz yok'],
    ['Yürürlükte sözleşme', l.parts.active, 15, `${l.activeContracts} sözleşme`],
    ['Yeniden imza', l.parts.returning, 10, `${l.contracts} sözleşme toplam`],
  ];
  return (
    <Sub title="Sadakat" aside={<span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${LOYALTY[l.band].pill}`}>{LOYALTY[l.band].label} · {l.score}</span>}>
      <ul className="space-y-1">
        {rows.map(([label, v, max, note]) => (
          <li key={label} className="grid grid-cols-[minmax(0,1fr)_64px_36px] items-center gap-2 text-[11.5px]">
            <span className="min-w-0">
              {label} <span className="text-[10.5px] text-canvas-muted">· {note}</span>
            </span>
            <span className="h-1.5 overflow-hidden rounded-full bg-slate-100">
              <span className="block h-full rounded-full bg-canvas-violet" style={{ width: `${(v / max) * 100}%` }} />
            </span>
            <span className="text-right font-mono tabular-nums">
              {v}/{max}
            </span>
          </li>
        ))}
      </ul>
    </Sub>
  );
}

function AdviceView({ a }: { a: AuthorAdvice }) {
  return (
    <div className="space-y-2">
      {a.summary && <p className="text-[12.5px] leading-snug">{a.summary}</p>}
      <ol className="space-y-1.5">
        {a.recommendations.map((r, i) => (
          <li key={i} className="rounded-xl bg-slate-50 px-2.5 py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-x-2">
              <span className="font-extrabold">
                {i + 1}. {r.title}
              </span>
              {r.when && <span className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{r.when}</span>}
            </div>
            {r.why && <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{r.why}</p>}
          </li>
        ))}
      </ol>
      {a.risks.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-4 text-[11.5px] text-amber-900">
          {a.risks.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
      <p className="text-[10.5px] text-canvas-muted">
        {a.createdBy}, {fmtDay(a.createdAt)} · ekrandaki sayılar ve gizli olmayan son görüşme notlarından; kararı editör verir.
      </p>
    </div>
  );
}

function Advice({ contactId, ready }: { contactId: string; ready: boolean }) {
  const qc = useQueryClient();
  const can = useCan('yazar-iliski.oneri');
  const q = useQuery({ queryKey: ['authors', 'advice', contactId], queryFn: () => authorsApi.advice(contactId), enabled: ENGINE_ENABLED });
  const make = useMutation({
    mutationFn: () => authorsApi.makeAdvice(contactId),
    onSuccess: (a) => {
      qc.setQueryData(['authors', 'advice', contactId], { advice: a, modelReady: true });
      toast.success('Öneri hazır');
    },
    onError: (e) => toast.error('Öneri üretilemedi', { description: e instanceof Error ? e.message : undefined }),
  });
  const a = q.data?.advice;
  return (
    <Sub
      title="ZEKİ AI önerisi"
      aside={
        can && ready && q.data?.modelReady ? (
          <button type="button" className={`${a ? btnGhost : btnPrimary} !min-h-9 !py-1`} disabled={make.isPending} onClick={() => make.mutate()}>
            <Sparkles aria-hidden className="h-3.5 w-3.5" />
            {make.isPending ? 'Yazılıyor…' : a ? 'Yeniden öner' : 'Öneri üret'}
          </button>
        ) : undefined
      }
    >
      {q.isLoading ? (
        <Loading />
      ) : a ? (
        <AdviceView a={a} />
      ) : (
        <p className="text-[12px] text-canvas-muted">
          {q.data && !q.data.modelReady ? 'ZEKİ AI şu an bağlı değil.' : can ? 'Satış, sadakat, ilişki ısısı ve son görüşme notlarından bu yazar için ne yapılacağını önerir.' : 'Henüz öneri üretilmedi.'}
        </p>
      )}
    </Sub>
  );
}

export default function GrowthSection({ contactId }: { contactId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['authors', 'growth', contactId],
    queryFn: () => authorsApi.growth(contactId),
    enabled: ENGINE_ENABLED && !!contactId,
    staleTime: 10 * 60_000,
    retry: 0,
  });
  const refresh = useMutation({
    mutationFn: () => authorsApi.growth(contactId, true),
    onSuccess: (g) => qc.setQueryData(['authors', 'growth', contactId], g),
    onError: (e) => toast.error('Yenilenemedi', { description: e instanceof Error ? e.message : undefined }),
  });
  const g = q.data;
  const err = errText(q.error, 'Gelişim okunamadı.');
  return (
    <section className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[12px] font-extrabold">Gelişim</h3>
        {g && (
          <button type="button" className={`${btnGhost} !min-h-9 !py-1 text-[11.5px]`} disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            <RefreshCw aria-hidden className={`h-3.5 w-3.5 ${refresh.isPending ? 'animate-spin' : ''}`} />
            {refresh.isPending ? 'Logo okunuyor…' : `Yenile · ${fmtDay(g.computedAt)}`}
          </button>
        )}
      </div>
      {q.isLoading && <p className="py-4 text-center text-[12px] text-canvas-muted">Logo satışları ve CRM okunuyor; ilk açılış 1–2 dakika sürer, sonra 12 saat hazır bekler…</p>}
      {err && <Note tone="err">{err}</Note>}
      {g && (
        <>
          {g.notes.map((n) => (
            <Note key={n} tone="warn">
              {n}
            </Note>
          ))}
          <Sales g={g} />
          <Books g={g} />
          <Royalty g={g} />
          <Readers g={g} />
          <Loyalty g={g} />
          <Advice contactId={contactId} ready />
        </>
      )}
    </section>
  );
}
