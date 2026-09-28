import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';

const PAGE = 50;
type View = 'pages' | 'domains' | 'new' | 'lost' | 'books';
type Snapshot = { id: string; taken_at: string; pages: number; detailed: number; links: number; complete: boolean; error: string | null };
type Resp = {
  configured: boolean;
  setup: string;
  site: string;
  state: { running: boolean; phase: string | null; done: number; queue: number | null; error: string | null };
  snapshot: Snapshot | null;
  previous: Snapshot | null;
  summary: { pages: number; inbound: number; domains: number; detailed: number; new: number; lost: number } | null;
  total: number;
  start: number;
  items: Array<Record<string, unknown>>;
};
const VIEWS: Array<{ id: View; label: string }> = [
  { id: 'pages', label: 'En çok bağlantı alan sayfalar' },
  { id: 'domains', label: 'Bağlantı veren siteler' },
  { id: 'new', label: 'Yeni' },
  { id: 'lost', label: 'Kaybolan' },
  { id: 'books', label: 'Bağlantısız çok satanlar' },
];

/** Gelen bağlantılar: Bing'in gördüğü dış bağlantılar — hangi sayfamıza kaç bağlantı var, hangi siteler bağlantı veriyor,
 *  son okumaya göre yeni ve kaybolanlar, hiç bağlantı görünmeyen çok satan kitaplar. Yalnız okunur. */
export default function SeoBacklinks() {
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [view, setView] = useState<View>('pages');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [view, query]);

  const list = useQuery({
    queryKey: ['seo-backlinks', view, query, start],
    queryFn: () => call<Resp>(`backlinks?${qs({ view, q: query, start, limit: PAGE })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (s) => (s.state.data?.state.running ? 10000 : false),
  });
  const read = useMutation({
    mutationFn: () => call<{ started: boolean }>('backlinks/refresh', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-backlinks'] }),
  });
  const d = list.data;
  const s = d?.summary;
  const running = !!d?.state.running;
  const total = d?.total ?? 0;

  return (
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/geri-baglantilar"
      crumb="Gelen bağlantılar"
      eyebrow="SEO & GEO · Gelen bağlantılar"
      title="Gelen bağlantılar"
      lead="Başka sitelerin sayfalarımıza verdiği bağlantılar, arama motorlarının ve yapay zekâ motorlarının siteye güveninin en güçlü işaretlerinden biridir. Liste Bing’in gördüğü bağlantılardan gelir (tam liste değildir); her gece okunur ve bir önceki okumayla karşılaştırılır."
      actions={
        canRun && d?.configured && (
          <button className="sg-button" onClick={() => read.mutate()} disabled={read.isPending || running}>
            {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {running ? `Okunuyor${d.state.queue ? ` (${fmt(d.state.done)}/${fmt(d.state.queue)} sayfa)` : ''}` : 'Şimdi oku'}
          </button>
        )
      }
    >
      {list.isLoading && <Loading text="Bağlantılar getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {read.error && <Failed error={read.error} />}
      {d?.state.error && <p className="sg-banner err">Son okuma: {d.state.error}</p>}

      {d && !d.configured && (
        <div className="sg-empty">
          <h2>Bing bağlantısı kurulmamış <SeoInfo k={list.data?.kaynaklar} label="Bing bağlantısı kurulmamış" /></h2>
          <p>{d.setup}</p>
        </div>
      )}
      {d && d.configured && !d.snapshot && !running && (
        <div className="sg-empty">
          <h2>Henüz okunmadı</h2>
          <p>Gece turunda ya da “Şimdi oku” ile ilk okuma yapılır. Yeni/kaybolan bağlantılar ikinci okumadan sonra görünür.</p>
        </div>
      )}

      {d && s && d.snapshot && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Bağlantı alan sayfa" value={fmt(s.pages)} note={`Toplam ${fmt(s.inbound)} gelen bağlantı · ${dateTime(d.snapshot.taken_at)}`} info={<SeoInfo k={list.data?.kaynaklar} label="Bağlantı alan sayfa" />} />
            <Kpi label="Bağlantı veren site" value={fmt(s.domains)} note={`Ayrıntısı okunan ${fmt(s.detailed)} sayfadan`} info={<SeoInfo k={list.data?.kaynaklar} label="Bağlantı veren site" />} />
            <Kpi label="Yeni" value={d.previous ? fmt(s.new) : '—'} note={d.previous ? `Önceki okuma ${dateTime(d.previous.taken_at)}` : 'Karşılaştırma için ikinci okuma gerekiyor'} tone={s.new ? 'good' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Yeni" />} />
            <Kpi label="Kaybolan" value={d.previous ? fmt(s.lost) : '—'} note="Yalnız iki okumada da ayrıntısı okunan sayfalar" tone={s.lost ? 'bad' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Kaybolan" />} />
          </section>
          {!d.snapshot.complete && (
            <p className="sg-banner">
              Son okumada {fmt(s.pages)} sayfanın {fmt(s.detailed)} tanesinin bağlantı ayrıntısı okunabildi; kalanı sonraki gece okunur. Bağlantı veren siteler bu sayfalardan hesaplandı.
            </p>
          )}

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div className="sg-filters" role="radiogroup" aria-label="Liste">
              {VIEWS.map((v) => (
                <button key={v.id} className="sg-filter" role="radio" aria-checked={view === v.id} aria-pressed={view === v.id} onClick={() => setView(v.id)}>
                  {v.label}
                </button>
              ))}
            </div>
            <label className="sg-search">
              <Search size={16} aria-hidden />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Adres, site ya da kitap" aria-label="Ara" />
            </label>
          </div>

          {!d.items.length && (
            <div className="sg-empty">
              <h2>Kayıt yok</h2>
              <p>{view === 'new' || view === 'lost' ? (d.previous ? 'İki okuma arasında değişiklik yok.' : 'Karşılaştırma için ikinci okuma gerekiyor.') : 'Bu listeye uyan kayıt yok.'}</p>
            </div>
          )}
          {d.items.length > 0 && (
            <section className="sg-card" aria-label="Liste">
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <Head view={view} />
                  <tbody>
                    {d.items.map((r, i) => (
                      <Line key={i} view={view} r={r} />
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {total > PAGE && (
            <div className="sg-pager">
              <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
                <ChevronLeft size={16} aria-hidden />
              </button>
              <span className="sg-mono">
                {fmt(start + 1)}–{fmt(Math.min(total, start + PAGE))} / {fmt(total)}
              </span>
              <button className="sg-button" disabled={start + PAGE >= total} onClick={() => setStart(start + PAGE)} aria-label="Sonraki sayfa">
                <ChevronRight size={16} aria-hidden />
              </button>
            </div>
          )}
        </>
      )}
    </SeoLayout>
  );
}

const R = { textAlign: 'right' as const };

function Head({ view }: { view: View }) {
  const cols: Record<View, Array<[string, boolean]>> = {
    pages: [['Sayfa', false], ['Gelen bağlantı', true]],
    domains: [['Site', false], ['Bağlantı', true], ['Sayfamız', true]],
    new: [['Bağlantı veren', false], ['Sayfamız', false], ['Bağlantı metni', false]],
    lost: [['Bağlantı veren', false], ['Sayfamız', false], ['Bağlantı metni', false]],
    books: [['Kitap', false], ['Satış', true]],
  };
  return (
    <thead>
      <tr>
        {cols[view].map(([t, right]) => (
          <th key={t} style={right ? R : undefined}>
            {t}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function Url({ href }: { href: string }) {
  return (
    <a className="sg-mono" href={href} target="_blank" rel="noreferrer" style={{ fontSize: 12, wordBreak: 'break-all' }}>
      {href.replace(/^https?:\/\//, '')} <ExternalLink size={11} aria-hidden />
    </a>
  );
}

function Line({ view, r }: { view: View; r: Record<string, unknown> }) {
  const str = (k: string) => String(r[k] ?? '');
  const num = (k: string) => fmt(Number(r[k] ?? 0));
  if (view === 'pages')
    return (
      <tr>
        <td>
          <Url href={str('url')} /> {!r.detailed && <span className="sg-chip">ayrıntı okunmadı</span>}
        </td>
        <td className="num">{num('count')}</td>
      </tr>
    );
  if (view === 'domains')
    return (
      <tr>
        <td className="sg-mono">{str('domain')}</td>
        <td className="num">{num('links')}</td>
        <td className="num">{num('pages')}</td>
      </tr>
    );
  if (view === 'books')
    return (
      <tr>
        <td>{r.url ? <a href={str('url')} target="_blank" rel="noreferrer">{str('name')}</a> : str('name')}</td>
        <td className="num">{num('sales')}</td>
      </tr>
    );
  return (
    <tr>
      <td>
        <Url href={str('source')} />
      </td>
      <td>
        <Url href={str('target')} />
      </td>
      <td style={{ fontSize: 12.5 }}>{str('anchor') || '—'}</td>
    </tr>
  );
}

function Kpi({ label, value, note, tone, info }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; info?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}</div>
      <div className="sg-kpi-value sg-mono" style={tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : undefined}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}
