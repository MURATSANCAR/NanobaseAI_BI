import { Fragment, useDeferredValue, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, ChevronDown, ChevronLeft, ChevronRight, Download, ExternalLink, Loader2, RefreshCw, Search, Sparkles } from 'lucide-react';
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs, type WithK } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';
import { EmptyHint } from '../components/Explain';

/** Aramadan satışa: Google araması → organik ziyaret → sepete ekleme → satış → ciro, sayfa/kitap bazında.
 *  Veri Google Analytics ve Search Console'dan yalnız okunur; satırı açınca nedenler ayrıntılı iş kartı olarak gelir. */

export type Metrics = { sessions: number; engaged: number; carts: number; purchases: number; revenue: number };
type Kind = 'urun' | 'kategori' | 'diger' | 'belirsiz';
type Flag = 'satissiz' | 'dusen_oturum' | 'dusen_ciro';
export type Ga4Snapshot = {
  property?: string;
  windows?: { cur: [string, string]; prev: [string, string]; gscCur: [string, string]; gscPrev: [string, string] };
  organic?: { cur: Metrics; prev: Metrics; change: Partial<Record<keyof Metrics, number | null>> };
  all?: { cur: Metrics; prev: Metrics };
  share?: { sessions: number | null; revenue: number | null; purchases: number | null };
  prevShare?: { sessions: number | null; revenue: number | null; purchases: number | null };
  funnel?: Metrics & { clicks: number | null; prevClicks: number | null };
  pages?: { rows: number; matched: number; unmatched: number; notSet: Metrics | null };
  flags?: Record<Flag, number>;
  thresholds?: { highTraffic: number; q3: number; conv: number | null; cartRate: number | null; aov: number | null; expectedSales: number };
  gscError?: string | null;
  error: string | null;
  savedAt: string | null;
};
export type Ga4Overview = {
  configured: boolean;
  snapshot: Ga4Snapshot | null;
  state: { running: boolean; error: string | null };
  refreshHours: number;
  channels: Array<{ channel: string; organic: boolean; cur: Metrics; prev: Metrics; change: { sessions: number | null; revenue: number | null } }>;
  daily: Array<Metrics & { day: string }>;
  kinds: Record<Kind, string>;
  flags: Record<Flag, string>;
};
type Badge = { code: string; label: string; tone: 'bad' | 'mid' | 'violet' | 'good' };
type PageRow = {
  path: string;
  key: string;
  kind: Kind;
  kindLabel: string;
  productId: string | null;
  title: string | null;
  cur: Metrics;
  prev: Metrics;
  change: { sessions: number | null; purchases: number | null; revenue: number | null };
  clicks: number | null;
  prevClicks: number | null;
  impressions: number | null;
  position: number | null;
  conv: number | null;
  cartRate: number | null;
  flags: Flag[];
  flagLabels: string[];
  badges: Badge[];
};
type Change = { label: string; current: string; proposed: string; ok: boolean | null; doc?: string | null };
type ActionCard = {
  code: string;
  badge: string;
  tone: 'bad' | 'mid' | 'violet';
  severity: string;
  title: string;
  why: string;
  changeHeads: [string, string];
  changes: Change[];
  steps: string[];
  owner: string;
  ownerLabel: string;
  impact: { value: number; formula: string } | null;
  priority: number;
  priorityBasis: string;
  links: Array<{ label: string; to: string; kind?: string }>;
};
type Sort = 'ciro' | 'oturum' | 'donusum' | 'tiklama' | 'sepet';

const ga4Api = {
  overview: () => call<Ga4Overview>('ga4'),
  pages: (p: { kind?: string; flag?: string; q?: string; sort: Sort; start: number; limit: number }) =>
    call<{ total: number; start: number; items: PageRow[]; savedAt: string | null }>(`ga4/pages?${qs(p)}`),
  page: (path: string) => call<PageRow & { cards: ActionCard[] }>(`ga4/page?${qs({ path })}`),
  summary: (path: string) => call<{ text: string | null; source: string }>('ga4/page-summary', { method: 'POST', body: { path }, timeout: 180_000 }),
  refresh: () => call<{ started: boolean }>('ga4/refresh', { method: 'POST' }),
  csvUrl: (p: { kind?: string; flag?: string; q?: string; sort: Sort }) => `${ENGINE_BASE}/api/v1/seo-geo/ga4/export.csv?${qs(p)}`,
};

const PAGE = 40;
const tl = (v: number | null | undefined) => (v == null ? '—' : `${fmt(v)} ₺`);
const pctText = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `%${fmt(v * 100, digits)}`);
const change = (v: number | null | undefined) => (v == null ? 'önceki dönem yok' : `${v >= 0 ? '+' : ''}${fmt(v, 1)}% önceki 28 güne göre`);
const tone = (v: number | null | undefined): 'good' | 'bad' | undefined => (v == null ? undefined : v >= 0 ? 'good' : 'bad');
const SORT_LABEL: Record<Sort, string> = { ciro: 'Ciro', oturum: 'Organik ziyaret', donusum: 'Dönüşüm', tiklama: 'Google tıklaması', sepet: 'Sepete ekleme' };

export default function SeoSearchToSales() {
  const qc = useQueryClient();
  const canRun = useCan('seo.calistir');
  const canExport = useCan('veri.disa-aktar');
  const [params] = useSearchParams();
  const linked = params.get('sayfa') ?? '';
  const [kind, setKind] = useState<Kind | ''>('');
  const [flag, setFlag] = useState<string>(params.get('filtre') ?? '');
  const [sort, setSort] = useState<Sort>('ciro');
  const [q, setQ] = useState(linked);
  const dq = useDeferredValue(q.trim());
  const [start, setStart] = useState(0);
  const [open, setOpen] = useState<string | null>(linked ? linked.replace(/^\/+/, '').replace(/\/+$/, '').toLowerCase() : null);
  useEffect(() => setStart(0), [kind, flag, dq, sort]);

  const ov = useQuery({
    queryKey: ['seo-ga4'],
    queryFn: ga4Api.overview,
    enabled: ENGINE_ENABLED,
    retry: false,
    refetchInterval: (query) => (query.state.data?.state.running ? 5000 : false),
  });
  const list = useQuery({
    queryKey: ['seo-ga4-pages', kind, flag, dq, sort, start, ov.data?.snapshot?.savedAt],
    queryFn: () => ga4Api.pages({ kind, flag, q: dq, sort, start, limit: PAGE }),
    enabled: ENGINE_ENABLED && !!ov.data?.configured,
    retry: false,
    placeholderData: (prev) => prev,
  });
  const refresh = useMutation({ mutationFn: ga4Api.refresh, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-ga4'] }) });
  const d = ov.data;
  const s = d?.snapshot;
  const running = !!d?.state.running;

  return (
    <SeoLayout
      k={ov.data?.kaynaklar}
      path="/seo-geo/aramadan-satisa"
      crumb="Aramadan satışa"
      eyebrow="SEO & GEO · Google Analytics"
      title="Aramadan satışa"
      lead="Google aramasından gelen okurun sepete ekleyip satın alması ve bıraktığı ciro, sayfa ve kitap bazında. Satırı açınca satmayan ya da düşen sayfanın olası nedenleri ve yapılacak işler ayrıntılı kart olarak gelir. Veri yalnız okunur; hiçbir sisteme yazılmaz."
      actions={
        d?.configured && (
          <>
            {canRun && (
              <button className="sg-button" onClick={() => refresh.mutate()} disabled={refresh.isPending || running}>
                {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
                {running ? 'Okunuyor…' : 'Şimdi oku'}
              </button>
            )}
            {canExport && s?.organic && (
              <a className="sg-button" href={ga4Api.csvUrl({ kind, flag, q: dq, sort })}>
                <Download size={16} aria-hidden /> Listeyi indir
              </a>
            )}
          </>
        )
      }
    >
      {ov.isLoading && <Loading text="Google Analytics verisi getiriliyor…" />}
      {ov.error && <Failed error={ov.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {d && !d.configured && (
        <EmptyHint title="Google Analytics bağlı değil" why={<>Mülk kimliği Yönetim → SEO & GEO ayarında girilince veri günde bir okunur. <Link to="/seo-geo/baglantilar">Bağlantılar</Link></>} />
      )}
      {(d?.state.error || s?.error) && <p className="sg-banner err">Son okuma başarısız: {d?.state.error || s?.error}</p>}
      {d?.configured && !s?.organic && !running && !ov.isLoading && (
        <EmptyHint title="Veri henüz okunmadı" why="«Şimdi oku»ya basın; sonra her gün kendiliğinden okunur." />
      )}
      {d?.configured && !s?.organic && running && <Loading text="Google Analytics okunuyor; birkaç dakika sürebilir…" />}

      {s?.organic && (
        <>
          <p className="sg-kpi-note" style={{ margin: 0 }}>
            Dönem {s.windows?.cur[0]} – {s.windows?.cur[1]} (önceki: {s.windows?.prev[0]} – {s.windows?.prev[1]}) · son okuma {dateTime(s.savedAt)}
            {s.gscError ? ` · Search Console okunamadı: ${s.gscError}` : ''}
          </p>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Organik ziyaret" value={fmt(s.organic.cur.sessions)} note={change(s.organic.change.sessions)} tone={tone(s.organic.change.sessions)} k={d?.kaynaklar} />
            <Kpi label="Sepete ekleme" value={fmt(s.organic.cur.carts)} note={change(s.organic.change.carts)} tone={tone(s.organic.change.carts)} k={d?.kaynaklar} />
            <Kpi label="Satış" value={fmt(s.organic.cur.purchases)} note={change(s.organic.change.purchases)} tone={tone(s.organic.change.purchases)} k={d?.kaynaklar} />
            <Kpi label="Ciro" value={tl(s.organic.cur.revenue)} note={change(s.organic.change.revenue)} tone={tone(s.organic.change.revenue)} k={d?.kaynaklar} />
            <Kpi
              label="Organik ciro payı"
              value={pctText(s.share?.revenue)}
              note={`Bütün kanallar ${tl(s.all?.cur.revenue)} · önceki dönem ${pctText(s.prevShare?.revenue)}`}
              k={d?.kaynaklar}
            />
          </section>

          <div className="sg-grid">
            <section className="sg-card sg-span-5" aria-label="Huni">
              <h2>Aramadan satışa huni <SeoInfo k={d?.kaynaklar} label="Huni" /></h2>
              <p className="sg-sub">Google tıklaması Search Console’dan (kesin veri 3 gün geç gelir), ötekiler Google Analytics organik ziyaretlerinden; son 28 gün.</p>
              <Funnel f={s.funnel} />
            </section>
            <section className="sg-card sg-span-7" aria-label="Günlük seri">
              <h2>Günlük organik ziyaret ve ciro <SeoInfo k={d?.kaynaklar} label="Günlük seri" /></h2>
              <p className="sg-sub">Son 90 gün. Sol eksen ziyaret, sağ eksen ciro (₺).</p>
              {d?.daily.length ? (
                <div className="sg-chart" style={{ height: 220 }}>
                  <ResponsiveContainer>
                    <ComposedChart data={d.daily.map((r) => ({ d: r.day.slice(5), s: r.sessions, r: r.revenue }))} margin={{ left: 0, right: 0, top: 8, bottom: 0 }}>
                      <defs>
                        <linearGradient id="sgGa4" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor="#7c5cff" stopOpacity={0.3} />
                          <stop offset="100%" stopColor="#7c5cff" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#f1edf6" vertical={false} />
                      <XAxis dataKey="d" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={24} />
                      <YAxis yAxisId="s" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={44} />
                      <YAxis yAxisId="r" orientation="right" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => fmt(v / 1000) + ' B'} />
                      <Tooltip formatter={(v: number, name: string) => (name === 's' ? [fmt(v), 'Ziyaret'] : [tl(v), 'Ciro'])} />
                      <Area yAxisId="s" type="monotone" dataKey="s" stroke="#7c5cff" strokeWidth={2} fill="url(#sgGa4)" isAnimationActive={false} />
                      <Line yAxisId="r" type="monotone" dataKey="r" stroke="#ff6b4a" strokeWidth={2} dot={false} isAnimationActive={false} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <EmptyHint title="Günlük seri yok" why="Bir sonraki okumada dolar." />
              )}
            </section>

            <section className="sg-card sg-span-12" aria-label="Kanallar">
              <h2>Kanallar <SeoInfo k={d?.kaynaklar} label="Kanallar" /></h2>
              <p className="sg-sub">Bütün ziyaretler kanala göre; Google’ın organik araması vurgulu. Kanal adları Google Analytics’teki gibidir.</p>
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Kanal</th>
                      <th style={{ textAlign: 'right' }}>Ziyaret</th>
                      <th style={{ textAlign: 'right' }}>Sepete ekleme</th>
                      <th style={{ textAlign: 'right' }}>Satış</th>
                      <th style={{ textAlign: 'right' }}>Ciro</th>
                      <th style={{ textAlign: 'right' }}>Dönüşüm</th>
                      <th style={{ textAlign: 'right' }}>Ciro değişimi</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d?.channels.map((c) => (
                      <tr key={c.channel} style={c.organic ? { background: '#f7f3ff', fontWeight: 700 } : undefined}>
                        <td>{c.channel}</td>
                        <td className="num">{fmt(c.cur.sessions)}</td>
                        <td className="num">{fmt(c.cur.carts)}</td>
                        <td className="num">{fmt(c.cur.purchases)}</td>
                        <td className="num">{tl(c.cur.revenue)}</td>
                        <td className="num">{pctText(c.cur.sessions ? c.cur.purchases / c.cur.sessions : null, 2)}</td>
                        <td className="num">{c.change.revenue == null ? '—' : `${c.change.revenue >= 0 ? '+' : ''}${fmt(c.change.revenue, 1)}%`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className="sg-card" aria-label="Sayfalar">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', justifyContent: 'space-between' }}>
              <h2 style={{ margin: 0 }}>
                Sayfalar <span className="sg-mono" style={{ fontSize: 13, color: 'var(--sg-muted)' }}>{fmt(list.data?.total)}</span> <SeoInfo k={list.data?.kaynaklar} label="Sayfalar" />
              </h2>
              <label className="sg-search" style={{ flex: '1 1 240px', maxWidth: 420 }}>
                <Search size={16} aria-hidden />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı ya da sayfa adresi" aria-label="Sayfa ara" />
              </label>
            </div>
            <p className="sg-sub" style={{ margin: '6px 0 10px', fontSize: 12, color: 'var(--sg-muted)' }}>
              «Trafik yüksek, satış yok»: organik ziyareti ürün sayfalarının üst çeyreğinde ve en az {fmt(s.thresholds?.highTraffic)} (site dönüşümüyle ≈{s.thresholds?.expectedSales} satış beklenir), ama satışı yok.
              «Sert düştü»: site genelindeki değişim hesaba katıldıktan sonra ziyaret ya da satış beklenenin %60’ının altına indi.
              {s.pages?.notSet ? ` Giriş sayfası belirlenemeyen ${fmt(s.pages.notSet.sessions)} ziyaret ayrı satırdadır.` : ''}
            </p>
            <div className="sg-filters" role="group" aria-label="Durum süzgeci">
              <button className="sg-filter" aria-pressed={flag === ''} onClick={() => setFlag('')}>Tümü</button>
              <button className="sg-filter" aria-pressed={flag === 'satissiz'} onClick={() => setFlag(flag === 'satissiz' ? '' : 'satissiz')}>
                Trafik yüksek, satış yok <span className="sg-mono">{fmt(s.flags?.satissiz)}</span>
              </button>
              <button className="sg-filter" aria-pressed={flag === 'dusen'} onClick={() => setFlag(flag === 'dusen' ? '' : 'dusen')}>
                Sert düşen <span className="sg-mono">{fmt((s.flags?.dusen_oturum ?? 0) + (s.flags?.dusen_ciro ?? 0))}</span>
              </button>
            </div>
            <div className="sg-filters" role="group" aria-label="Sayfa türü" style={{ marginTop: 8 }}>
              <button className="sg-filter" aria-pressed={kind === ''} onClick={() => setKind('')}>Bütün türler</button>
              {(['urun', 'kategori', 'diger', 'belirsiz'] as Kind[]).map((k) => (
                <button key={k} className="sg-filter" aria-pressed={kind === k} onClick={() => setKind(kind === k ? '' : k)}>
                  {d?.kinds[k] ?? k}
                </button>
              ))}
              <label className="sg-kpi-note" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', margin: 0 }}>
                Sırala
                <select value={sort} onChange={(e) => setSort(e.target.value as Sort)} className="sg-button" style={{ minHeight: 44 }} aria-label="Sıralama">
                  {(Object.keys(SORT_LABEL) as Sort[]).map((k) => (
                    <option key={k} value={k}>{SORT_LABEL[k]}</option>
                  ))}
                </select>
              </label>
            </div>

            {list.isLoading && <Loading text="Sayfalar getiriliyor…" />}
            {list.error && <Failed error={list.error} />}
            {list.data && !list.data.items.length && <EmptyHint title="Bu süzgece uyan sayfa yok" why="Aramayı kısaltın ya da süzgeci kaldırın." />}
            {list.data && list.data.items.length > 0 && (
              <div className="sg-table-wrap" style={{ marginTop: 12 }}>
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Sayfa / kitap</th>
                      <th style={{ textAlign: 'right' }}>Tıklama</th>
                      <th style={{ textAlign: 'right' }}>Ziyaret</th>
                      <th style={{ textAlign: 'right' }}>Sepete ekleme</th>
                      <th style={{ textAlign: 'right' }}>Satış</th>
                      <th style={{ textAlign: 'right' }}>Ciro</th>
                      <th style={{ textAlign: 'right' }}>Dönüşüm</th>
                      <th style={{ textAlign: 'right' }}>Önceki döneme göre</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.data.items.map((r) => {
                      const isOpen = open === r.key;
                      return (
                        <Fragment key={r.key}>
                          <tr>
                            <td style={{ minWidth: 240 }}>
                              <button
                                type="button"
                                onClick={() => setOpen(isOpen ? null : r.key)}
                                aria-expanded={isOpen}
                                style={{ all: 'unset', cursor: r.kind === 'belirsiz' ? 'default' : 'pointer', display: 'flex', gap: 6, alignItems: 'flex-start' }}
                                disabled={r.kind === 'belirsiz'}
                              >
                                {r.kind !== 'belirsiz' && (
                                  <ChevronDown size={16} aria-hidden style={{ flex: 'none', marginTop: 1, transform: isOpen ? 'rotate(180deg)' : 'none', transition: 'transform 160ms var(--ease-out)' }} />
                                )}
                                <span style={{ minWidth: 0 }}>
                                  <span style={{ fontWeight: 700, overflowWrap: 'anywhere' }}>{r.title || r.path}</span>
                                  <span className="sg-kpi-note sg-mono" style={{ display: 'block', overflowWrap: 'anywhere' }}>{r.path} · {r.kindLabel}</span>
                                </span>
                              </button>
                              {!!(r.flagLabels.length || r.badges.length) && (
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                                  {r.flagLabels.map((f) => (
                                    <span key={f} className="sg-chip bad">{f}</span>
                                  ))}
                                  {r.badges.map((b) => (
                                    <span key={b.code} className={`sg-chip ${b.tone}`}>{b.label}</span>
                                  ))}
                                </div>
                              )}
                            </td>
                            <td className="num">{fmt(r.clicks)}</td>
                            <td className="num">{fmt(r.cur.sessions)}</td>
                            <td className="num">{fmt(r.cur.carts)}</td>
                            <td className="num">{fmt(r.cur.purchases)}</td>
                            <td className="num">{tl(r.cur.revenue)}</td>
                            <td className="num">{pctText(r.conv, 2)}</td>
                            <td className="num">
                              <Delta v={r.change.sessions} label="ziyaret" />
                              <Delta v={r.change.revenue} label="ciro" />
                            </td>
                          </tr>
                          {isOpen && r.kind !== 'belirsiz' && (
                            <tr>
                              <td colSpan={8} style={{ background: '#fcfbfe' }}>
                                <PageCards path={r.path} productId={r.productId} />
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
            {(list.data?.total ?? 0) > PAGE && (
              <div className="sg-pager" style={{ marginTop: 12 }}>
                <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
                  <ChevronLeft size={16} aria-hidden />
                </button>
                <span className="sg-mono">
                  {fmt(start + 1)}–{fmt(Math.min(list.data?.total ?? 0, start + PAGE))} / {fmt(list.data?.total)}
                </span>
                <button className="sg-button" disabled={start + PAGE >= (list.data?.total ?? 0)} onClick={() => setStart(start + PAGE)} aria-label="Sonraki sayfa">
                  <ChevronRight size={16} aria-hidden />
                </button>
              </div>
            )}
          </section>
        </>
      )}
    </SeoLayout>
  );
}

function Kpi({ label, value, note, tone: t, k }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; k?: WithK['kaynaklar'] }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">
        {label} <SeoInfo k={k} label={label} />
      </div>
      <div className="sg-kpi-value sg-mono">{value}</div>
      <div className="sg-kpi-note" style={t ? { color: t === 'good' ? '#0f7a51' : '#c2361b' } : undefined}>{note}</div>
    </div>
  );
}

function Delta({ v, label }: { v: number | null; label: string }) {
  if (v == null) return <div className="sg-kpi-note">{label} —</div>;
  return (
    <div className="sg-kpi-note" style={{ color: v >= 0 ? '#0f7a51' : '#c2361b' }}>
      {label} {v >= 0 ? '+' : ''}
      {fmt(v, 0)}%
    </div>
  );
}

function Funnel({ f }: { f?: Ga4Snapshot['funnel'] }) {
  if (!f) return null;
  const steps: Array<{ label: string; v: number | null; money?: boolean }> = [
    { label: 'Google tıklaması', v: f.clicks },
    { label: 'Organik ziyaret', v: f.sessions },
    { label: 'Sepete ekleme', v: f.carts },
    { label: 'Satış', v: f.purchases },
  ];
  const max = Math.max(1, ...steps.map((s) => s.v ?? 0));
  return (
    <div className="sg-bars">
      {steps.map((s, i) => {
        const prev = i > 0 ? steps[i - 1].v : null;
        const rate = prev && s.v != null ? s.v / prev : null;
        return (
          <div key={s.label} className="sg-bar-row">
            <span>
              {s.label}
              {rate != null && <span className="sg-kpi-note" style={{ marginLeft: 6 }}>bir önceki adımın %{fmt(rate * 100, 1)}’i</span>}
            </span>
            <span className="sg-mono">{s.v == null ? '—' : fmt(s.v)}</span>
            <span className="sg-bar">
              <i style={{ width: `${((s.v ?? 0) / max) * 100}%` }} />
            </span>
          </div>
        );
      })}
      <div className="sg-bar-row" style={{ paddingTop: 6, borderTop: '1px solid var(--sg-line)' }}>
        <span style={{ fontWeight: 800 }}>Ciro</span>
        <span className="sg-mono" style={{ fontWeight: 800 }}>{tl(f.revenue)}</span>
      </div>
      {f.clicks == null && <p className="sg-kpi-note" style={{ margin: 0 }}>Search Console bağlı olmadığı için tıklama adımı boş.</p>}
    </div>
  );
}

/** Satır açılınca: sayfanın eylem kartları (kanıt, mevcut → önerilen, adımlar, sorumlu, beklenen etki). */
function PageCards({ path, productId }: { path: string; productId: string | null }) {
  const canPropose = useCan('seo.oneri-uret');
  const r = useQuery({ queryKey: ['seo-ga4-page', path], queryFn: () => ga4Api.page(path), enabled: ENGINE_ENABLED, retry: false });
  const cards = r.data?.cards ?? [];
  const sum = useQuery({
    queryKey: ['seo-ga4-summary', path],
    queryFn: () => ga4Api.summary(path),
    enabled: ENGINE_ENABLED && canPropose && cards.length > 0,
    retry: false,
    staleTime: Infinity,
  });
  if (r.isLoading) return <Loading text="Nedenler hesaplanıyor…" />;
  if (r.error) return <Failed error={r.error} />;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '4px 0' }}>
      {sum.data?.text && (
        <div className="sg-banner" style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
          <Sparkles size={16} aria-hidden style={{ flex: 'none', marginTop: 2 }} />
          <span>
            <b>Zeki AI özeti:</b> {sum.data.text}
          </span>
        </div>
      )}
      {sum.isFetching && !sum.data && <p className="sg-kpi-note" style={{ margin: 0 }}>Zeki AI özeti yazılıyor…</p>}
      {!cards.length && (
        <p className="sg-banner ok" style={{ margin: 0 }}>
          Bu sayfada kurallarla bulunan bir sorun yok.
          {productId && (
            <>
              {' '}
              <Link to={`/seo-geo/kitap?urun=${encodeURIComponent(productId)}`}>Kitap karnesini aç</Link>
            </>
          )}
        </p>
      )}
      {cards.map((c, i) => (
        <article key={c.code} className={`sg-issue ${c.severity}`} style={{ padding: 16 }}>
          <h3 style={{ flexWrap: 'wrap' }}>
            <span className="sg-mono" style={{ color: 'var(--sg-muted)' }}>{i + 1}.</span>
            {c.title}
          </h3>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '4px 0 10px' }}>
            <span className={`sg-chip ${c.tone}`}>{c.badge}</span>
            <span className="sg-chip violet">Sorumlu: {c.ownerLabel}</span>
            <span className="sg-chip" title={c.priorityBasis}>Öncelik {fmt(c.priority, 1)}</span>
          </div>
          <p><b>Neden:</b> {c.why}</p>
          {c.impact && (
            <p style={{ marginTop: 8, color: 'var(--sg-ink)' }}>
              <b>Beklenen etki:</b> ≈ {tl(c.impact.value)} / 28 gün
              <span className="sg-kpi-note" style={{ display: 'block' }}>Hesap: {c.impact.formula}</span>
            </p>
          )}
          {!!c.changes.length && (
            <div className="sg-table-wrap" style={{ marginTop: 10 }}>
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Ne</th>
                    <th>{c.changeHeads[0]}</th>
                    <th>{c.changeHeads[1]}</th>
                  </tr>
                </thead>
                <tbody>
                  {c.changes.map((x, j) => (
                    <tr key={j}>
                      <td style={{ minWidth: 140, fontWeight: 700 }}>
                        {x.ok === false && <span className="sg-dot kritik" role="img" aria-label="sorunlu" style={{ display: 'inline-block', marginRight: 6 }} />}
                        {x.ok === true && <span className="sg-dot" role="img" aria-label="uygun" style={{ display: 'inline-block', marginRight: 6, background: 'var(--sg-mint)' }} />}
                        {x.label}
                      </td>
                      <td style={{ minWidth: 160, overflowWrap: 'anywhere' }}>{x.current}</td>
                      <td style={{ minWidth: 180, overflowWrap: 'anywhere' }}>
                        {x.proposed}
                        {x.doc && (
                          <a href={x.doc} target="_blank" rel="noreferrer" className="sg-kpi-note" style={{ display: 'inline-flex', gap: 4, alignItems: 'center', marginLeft: 6 }}>
                            Google’ın açıklaması <ExternalLink size={12} aria-hidden />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!!c.steps.length && (
            <ol style={{ margin: '10px 0 0', paddingLeft: 20, fontSize: 12.5, lineHeight: 1.6 }}>
              {c.steps.map((st, j) => (
                <li key={j}>{st}</li>
              ))}
            </ol>
          )}
          <div className="sg-actions" style={{ marginTop: 12 }}>
            {c.links.map((l) => (
              <Link key={l.to + l.label} to={l.to} className={`sg-button${l.kind === 'propose' ? ' primary' : ''}`}>
                {l.label} <ArrowRight size={14} aria-hidden />
              </Link>
            ))}
            <Link to="/seo-geo/is-listesi" className="sg-button">
              İş listesine git <ArrowRight size={14} aria-hidden />
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}
