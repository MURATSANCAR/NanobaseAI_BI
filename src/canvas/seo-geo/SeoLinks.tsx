import { useState, type FormEvent, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/* ------------------------------------------------------------------ uç tipleri (/api/v1/seo-geo/links*) */
type View = 'orphans' | 'deep' | 'author' | 'weak' | 'anchors';
type Kind = 'product' | 'author' | 'category' | 'brand' | 'home' | 'other';
type Row = {
  url: string;
  kind: Kind;
  id: string | null;
  name: string | null;
  sales: number;
  inlinks: number;
  nofollowInlinks: number;
  depth: number | null;
  crawled: boolean;
  inSitemap?: boolean | null;
  authorUrl?: string | null;
  authorPageCrawled?: boolean | null;
  path?: string[];
  anchors?: { ok: number; generic: number; empty: number };
  examples?: string[];
};
type Book = { id: string; name: string | null; url: string; sales: number };
type AuthorRow = {
  id: string;
  kind: 'author';
  name: string | null;
  url: string;
  pageCrawled: boolean;
  books: number;
  sales: number;
  linkedBooks: number | null;
  missingBooks: Book[];
  paginated: boolean;
  crawledBooks: number;
  booksWithoutAuthorLink: Book[];
};
type Summary = {
  crawledPages: number;
  techPages: number;
  edges: number;
  followedEdges: number;
  homeCrawled: boolean;
  inventory: number;
  coverage: { byKind: Partial<Record<Kind, { crawled: number; of: number }>>; crawled: number; of: number; share: number | null };
  counts: { orphans: number; orphanProducts: number; deep: number; unreachable: number; author: number; weak: number; anchors: number };
  anchorTexts: Array<{ text: string; count: number }>;
  genericAnchorLinks: number;
  emptyAnchorLinks: number;
  authorsWithoutPage: number;
  deepClicks: number;
  weakInlinks: number;
  sitemapKnown: boolean;
  sitemapPartial: boolean;
  series: { available: boolean; note: string };
  computedAt: string | null;
  lastCrawl: string | null;
};
type Report = {
  summary: Summary;
  view: View;
  total: number;
  start: number;
  items: Array<Row | AuthorRow>;
  crawl: { running: boolean; done?: number; queue?: number | null } | null;
  history: Array<{ day: string; counts: Summary['counts']; coverage: { share: number | null } }>;
};
type LinkInfo = { url: string; kind: Kind; id: string | null; name: string | null; anchors: string[]; nofollow: boolean; anchorClass: 'ok' | 'generic' | 'empty' };
type UrlDetail = {
  url: string;
  item: { url: string; kind: Kind; id: string | null; name: string | null } | null;
  crawled: boolean;
  status: number | null;
  depth: number | null;
  path: string[];
  inlinks: LinkInfo[];
  outlinks: LinkInfo[];
  outlinksKnown: boolean;
};

const linksApi = {
  report: (p: { view: View; kind?: string; q?: string; start?: number; limit?: number }) => call<Report>(`links?${qs(p)}`, { timeout: 180_000 }),
  url: (u: string) => call<UrlDetail>(`links/url?${qs({ u })}`, { timeout: 180_000 }),
};

const PAGE = 40;
const TABS: Array<{ id: View; slug: string; label: string }> = [
  { id: 'orphans', slug: 'yetim', label: 'Bağlantı almayan sayfalar' },
  { id: 'weak', slug: 'oncelik', label: 'Çok satan, az bağlantılı' },
  { id: 'deep', slug: 'derin', label: 'Derindeki sayfalar' },
  { id: 'author', slug: 'yazar', label: 'Yazar ↔ kitap' },
  { id: 'anchors', slug: 'metin', label: 'Bağlantı metni' },
];
const KIND_LABEL: Record<Kind, string> = { product: 'Ürün', author: 'Yazar', category: 'Kategori', brand: 'Yayınevi', home: 'Anasayfa', other: 'Diğer' };
const KIND_FILTERS: Kind[] = ['product', 'author', 'category', 'brand'];
const short = (u: string) => u.replace(/^https?:\/\/(www\.)?/, '');
const pct = (share: number | null | undefined) => (share == null ? '—' : `%${fmt(share * 100)}`);

/** Site içi bağlantılar: teknik taramanın açtığı sayfaların birbirine verdiği bağlantılar. Siteye ayrıca istek gitmez. */
export default function SeoLinks() {
  const [params, setParams] = useSearchParams();
  const tab = TABS.find((t) => t.slug === params.get('sekme')) ?? TABS[0];
  const adres = params.get('adres') ?? '';
  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  return (
    <SeoLayout
      path="/seo-geo/ic-baglantilar"
      crumb="Site içi bağlantılar"
      eyebrow="SEO & GEO · teknik tarama"
      title="Site içi bağlantılar"
      lead="Sitenin kendi sayfaları arasındaki bağlantılar: hiç bağlantı almayan kitaplar, anasayfadan çok uzakta kalanlar, yazar sayfası ile kitap sayfalarının birbirine bağlanıp bağlanmadığı ve bir şey anlatmayan bağlantı metinleri. Veri teknik taramadan gelir; siteye ayrıca istek gitmez, değişiklik yapılmaz."
    >
      <UrlLookup key={adres} value={adres} onChange={(u) => set('adres', u)} />
      <div className="sg-filters" role="tablist" aria-label="Bölüm" style={{ marginTop: 16 }}>
        {TABS.map((t) => (
          <button key={t.id} role="tab" className="sg-filter" aria-pressed={tab.id === t.id} aria-selected={tab.id === t.id} onClick={() => set('sekme', t.id === 'orphans' ? '' : t.slug)}>
            {t.label}
          </button>
        ))}
      </div>
      <ViewTab key={tab.id} view={tab.id} onUrl={(u) => set('adres', u)} />
    </SeoLayout>
  );
}

/* ------------------------------------------------------------------ görünüm */
function ViewTab({ view, onUrl }: { view: View; onUrl: (u: string) => void }) {
  const [kind, setKind] = useState<Kind | ''>('');
  const [q, setQ] = useState('');
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-links', view, kind, q, start],
    queryFn: () => linksApi.report({ view, kind, q: q.trim(), start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (x) => (x.state.data?.crawl?.running ? 60_000 : false),
  });
  const d = r.data;
  const s = d?.summary;

  return (
    <>
      {r.isLoading && <Loading text="Bağlantı grafiği hesaplanıyor…" />}
      {r.error && <Failed error={r.error} />}
      {s && d && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Bağlantısı okunan sayfa" value={fmt(s.crawledPages)} note={`${fmt(s.followedEdges)} izlenen bağlantı · son tarama ${dateTime(s.lastCrawl)}`} />
            <Kpi
              label="Kapsam"
              value={pct(s.coverage.share)}
              note={(['product', 'author', 'category', 'brand'] as Kind[])
                .filter((k) => s.coverage.byKind[k])
                .map((k) => `${KIND_LABEL[k]} ${fmt(s.coverage.byKind[k]!.crawled)}/${fmt(s.coverage.byKind[k]!.of)}`)
                .join(' · ')}
            />
            <Kpi label="Bağlantı almayan kitap" value={fmt(s.counts.orphanProducts)} note={`Bütün türlerde ${fmt(s.counts.orphans)} sayfa`} />
            <Kpi label="Yazar ↔ kitap sorunu" value={fmt(s.counts.author)} note={`${fmt(s.authorsWithoutPage)} yazarın sitede yazar sayfası yok`} />
          </section>

          <CoverageNote s={s} running={!!d.crawl?.running} />

          {!s.crawledPages ? (
            <div className="sg-empty">
              <h2>Henüz bağlantı verisi yok</h2>
              <p>
                Bağlantılar teknik taramada okunur. <Link to="/seo-geo/teknik">Teknik sağlık</Link> ekranından taramayı başlatın ya da gece taramasını bekleyin.
              </p>
            </div>
          ) : (
            <section className="sg-card" style={{ marginTop: 16 }}>
              <h2>{TABS.find((t) => t.id === view)?.label}</h2>
              <p className="sg-sub">{VIEW_HELP[view](s)}</p>
              {view === 'anchors' && <AnchorTexts s={s} />}
              {view === 'author' && !s.series.available && <p className="sg-banner" style={{ marginBottom: 12 }}>{s.series.note}</p>}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', margin: '8px 0 12px' }}>
                <label className="sg-search" style={{ flex: '1 1 240px' }}>
                  <Search size={16} aria-hidden />
                  <input
                    value={q}
                    onChange={(e) => {
                      setQ(e.target.value);
                      setStart(0);
                    }}
                    placeholder={view === 'author' ? 'Yazar adı' : 'Sayfa adı ya da adres'}
                    aria-label="Ara"
                  />
                </label>
                {view !== 'author' && view !== 'weak' && (
                  <div className="sg-filters" role="toolbar" aria-label="Sayfa türü">
                    {(['', ...KIND_FILTERS] as const).map((k) => (
                      <button
                        key={k || 'all'}
                        className="sg-filter"
                        aria-pressed={kind === k}
                        onClick={() => {
                          setKind(k);
                          setStart(0);
                        }}
                      >
                        {k ? KIND_LABEL[k] : 'Tümü'}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {!d.items.length ? (
                <div className="sg-empty">
                  <h2>Kayıt yok</h2>
                  <p>Taranan sayfalarda bu görünümde sorun bulunmadı.</p>
                </div>
              ) : view === 'author' ? (
                <AuthorTable rows={d.items as AuthorRow[]} />
              ) : (
                <RowTable view={view} rows={d.items as Row[]} s={s} onUrl={onUrl} />
              )}
              <Pager start={start} total={d.total} setStart={setStart} />
            </section>
          )}
        </>
      )}
    </>
  );
}

const VIEW_HELP: Record<View, (s: Summary) => string> = {
  orphans: () =>
    'Satıştaki kitaplar ve yazar/kategori/yayınevi sayfaları içinde, taranan sayfaların hiçbirinden (izlenen) bağlantı almayanlar. Arama motoru bu sayfaları yalnız sitemapten bulur ve önemsiz sayar. Çok satandan aza.',
  weak: (s) => `Taranan sayfalardan ${fmt(s.weakInlinks)}'ten az bağlantı alan kitaplar, çok satandan aza. Bu kitaplara anasayfadan, kategori ve yazar sayfalarından, benzer kitaplardan bağlantı vermek önceliklidir.`,
  deep: (s) =>
    s.homeCrawled
      ? `Anasayfadan ${fmt(s.deepClicks)} tıklamadan daha uzakta kalan ya da taranan sayfalar üzerinden anasayfaya bağlanamayan sayfalar. Derindeki sayfa daha seyrek taranır.`
      : 'Anasayfa henüz taranmadığı için tıklama derinliği hesaplanamadı.',
  author: () =>
    'Kitap sayfası yazar sayfasına, yazar sayfası yazarın satıştaki kitaplarına bağlantı veriyor mu. Yazar sayfası birden çok sayfaya bölünmüşse yalnız ilk sayfası taranmıştır; eksik görünen kitaplar sonraki sayfalarda olabilir.',
  anchors: () => 'Kendisine gelen bütün bağlantıların metni boş ya da "tıklayın, detay, incele" gibi bir şey anlatmayan sayfalar. Bağlantı metni, sayfanın ne olduğunu arama motoruna anlatır.',
};

function CoverageNote({ s, running }: { s: Summary; running: boolean }) {
  const old = s.techPages - s.crawledPages;
  return (
    <p className="sg-banner" style={{ marginTop: 16 }}>
      Sonuçlar taranan sayfalar kadar doğrudur: tarama siteyi bağlantı izleyerek dolaşmaz, anasayfayı, ürünleri (çok satandan) ve yazar/kategori/yayınevi sayfalarını sırayla açar. Bilinen sayfalardan
      bağlantıları okunanların payı {pct(s.coverage.share)} ({fmt(s.coverage.crawled)}/{fmt(s.coverage.of)}); taranmamış bir sayfadan gelen bağlantı burada görünmez.
      {old > 0 && ` ${fmt(old)} sayfa bağlantı okuması eklenmeden önce tarandı; sonraki taramalarda okunacak.`}
      {!s.homeCrawled && ' Anasayfanın bağlantıları henüz okunmadı.'}
      {running && ' Tarama sürüyor; sonuçlar birkaç dakikada bir yenilenir.'}
      {s.computedAt && ` Hesaplandı: ${dateTime(s.computedAt)}.`}
    </p>
  );
}

function AnchorTexts({ s }: { s: Summary }) {
  if (!s.anchorTexts.length && !s.emptyAnchorLinks) return null;
  return (
    <details className="sg-more" style={{ marginBottom: 12 }}>
      <summary>
        Sitede {fmt(s.genericAnchorLinks)} bağlantı genel metinli, {fmt(s.emptyAnchorLinks)} bağlantı metinsiz
      </summary>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
        {s.anchorTexts.map((t) => (
          <span key={t.text} className="sg-chip">
            “{t.text}” · {fmt(t.count)}
          </span>
        ))}
      </div>
    </details>
  );
}

function PageName({ row }: { row: { kind: Kind; id: string | null; name: string | null; url: string } }) {
  const label = row.name || short(row.url);
  return (
    <>
      {row.kind === 'product' && row.id ? (
        <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(row.id)}`}>{label}</Link>
      ) : (
        <span style={{ fontWeight: 700 }}>{label}</span>
      )}
      <div className="sg-mono" style={{ fontSize: 11, wordBreak: 'break-all', marginTop: 2 }}>
        <a href={row.url} target="_blank" rel="noreferrer">
          {short(row.url)} <ExternalLink size={10} aria-hidden />
        </a>
      </div>
    </>
  );
}

function RowTable({ view, rows, s, onUrl }: { view: View; rows: Row[]; s: Summary; onUrl: (u: string) => void }) {
  return (
    <div className="sg-table-wrap">
      <table className="sg-table">
        <thead>
          <tr>
            <th>Sayfa</th>
            <th>Tür</th>
            <th style={{ textAlign: 'right' }}>Satış</th>
            <th style={{ textAlign: 'right' }}>Gelen bağlantı</th>
            <th>{view === 'deep' ? 'Derinlik' : view === 'anchors' ? 'Bağlantı metinleri' : 'Durum'}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.url}>
              <td style={{ minWidth: 220 }}>
                <PageName row={row} />
                {view === 'deep' && row.path && row.path.length > 1 && (
                  <details className="sg-more" style={{ marginTop: 6 }}>
                    <summary>Anasayfadan yol</summary>
                    <ol style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 11.5 }}>
                      {row.path.map((p) => (
                        <li key={p} className="sg-mono" style={{ wordBreak: 'break-all' }}>
                          {short(p)}
                        </li>
                      ))}
                    </ol>
                  </details>
                )}
                <button className="sg-filter" style={{ marginTop: 6 }} onClick={() => onUrl(row.url)}>
                  Bağlantıları gör
                </button>
              </td>
              <td>
                <span className="sg-chip">{KIND_LABEL[row.kind] ?? row.kind}</span>
              </td>
              <td className="sg-mono" style={{ textAlign: 'right' }}>
                {row.kind === 'other' || row.kind === 'home' ? '—' : fmt(row.sales)}
              </td>
              <td className="sg-mono" style={{ textAlign: 'right' }}>
                {fmt(row.inlinks)}
                {row.nofollowInlinks > 0 && <div style={{ fontSize: 11 }}>+{fmt(row.nofollowInlinks)} nofollow</div>}
              </td>
              <td>
                <Status view={view} row={row} s={s} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Status({ view, row, s }: { view: View; row: Row; s: Summary }) {
  const chips: ReactNode[] = [];
  if (view === 'deep') {
    chips.push(
      <span key="d" className={`sg-chip ${row.depth == null ? 'bad' : 'mid'}`}>
        {row.depth == null ? 'Anasayfadan ulaşılamadı' : `${fmt(row.depth)} tıklama`}
      </span>,
    );
  } else if (view === 'anchors' && row.anchors) {
    chips.push(
      <span key="a" className="sg-chip mid">
        {fmt(row.anchors.generic)} genel · {fmt(row.anchors.empty)} metinsiz
      </span>,
    );
    (row.examples ?? []).forEach((t) =>
      chips.push(
        <span key={`e${t}`} className="sg-chip">
          “{t}”
        </span>,
      ),
    );
  } else {
    if (!row.inlinks) chips.push(<span key="o" className="sg-chip bad">Bağlantı yok</span>);
    if (row.crawled) chips.push(<span key="c" className="sg-chip">Kendisi tarandı</span>);
    if (row.inSitemap === false) chips.push(<span key="s" className="sg-chip bad">Sitemapte de yok</span>);
    if (row.authorPageCrawled === true) chips.push(<span key="y" className="sg-chip mid">Yazar sayfası tarandı, bağlantı yok</span>);
    if (row.authorPageCrawled === false) chips.push(<span key="y" className="sg-chip">Yazar sayfası taranmadı</span>);
    if (row.depth != null) chips.push(<span key="d" className={`sg-chip ${row.depth > s.deepClicks ? 'mid' : ''}`}>{fmt(row.depth)} tıklama</span>);
  }
  return <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>{chips}</div>;
}

function Books({ title, books }: { title: string; books: Book[] }) {
  if (!books.length) return null;
  return (
    <details className="sg-more" style={{ marginTop: 6 }}>
      <summary>
        {title} ({fmt(books.length)})
      </summary>
      <ul style={{ margin: '6px 0 0', paddingLeft: 18, fontSize: 12.5 }}>
        {books.map((b) => (
          <li key={b.id}>
            <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(b.id)}`}>{b.name || b.id}</Link>
            <span className="sg-mono" style={{ fontSize: 11 }}> · {fmt(b.sales)} satış</span>
          </li>
        ))}
      </ul>
    </details>
  );
}

function AuthorTable({ rows }: { rows: AuthorRow[] }) {
  return (
    <div className="sg-table-wrap">
      <table className="sg-table">
        <thead>
          <tr>
            <th>Yazar</th>
            <th style={{ textAlign: 'right' }}>Kitap</th>
            <th>Yazar sayfası → kitaplar</th>
            <th>Kitap sayfaları → yazar</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.id}>
              <td style={{ minWidth: 200 }}>
                <PageName row={{ kind: 'author', id: a.id, name: a.name, url: a.url }} />
              </td>
              <td className="sg-mono" style={{ textAlign: 'right' }}>
                {fmt(a.books)}
                <div style={{ fontSize: 11 }}>{fmt(a.sales)} satış</div>
              </td>
              <td style={{ minWidth: 200 }}>
                {a.pageCrawled ? (
                  <>
                    <span className={`sg-chip ${a.missingBooks.length ? 'mid' : 'good'}`}>
                      {fmt(a.linkedBooks)}/{fmt(a.books)} kitaba bağlantı
                    </span>
                    {a.paginated && <div className="sg-sub" style={{ marginTop: 4 }}>Sayfa bölünmüş; yalnız ilk sayfa tarandı.</div>}
                    <Books title="Bağlantı verilmeyen kitaplar" books={a.missingBooks} />
                  </>
                ) : (
                  <span className="sg-chip">Yazar sayfası henüz taranmadı</span>
                )}
              </td>
              <td style={{ minWidth: 200 }}>
                <span className={`sg-chip ${a.booksWithoutAuthorLink.length ? 'mid' : 'good'}`}>
                  {fmt(a.crawledBooks - a.booksWithoutAuthorLink.length)}/{fmt(a.crawledBooks)} taranan kitap yazara bağlanıyor
                </span>
                <Books title="Yazar sayfasına bağlantı vermeyen kitaplar" books={a.booksWithoutAuthorLink} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ tek adres */
function UrlLookup({ value, onChange }: { value: string; onChange: (u: string) => void }) {
  const [draft, setDraft] = useState(value);
  const r = useQuery({ queryKey: ['seo-links-url', value], queryFn: () => linksApi.url(value), enabled: ENGINE_ENABLED && !!value, retry: false });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    onChange(draft.trim());
  };
  const d = r.data;
  return (
    <section className="sg-card">
      <h2>Bir sayfanın bağlantıları</h2>
      <form onSubmit={submit} style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 8 }}>
        <label className="sg-search" style={{ flex: '1 1 260px' }}>
          <Search size={16} aria-hidden />
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Sayfa adresi (ör. timas.com.tr/kitap-adi)" aria-label="Sayfa adresi" />
        </label>
        <button className="sg-button" type="submit" disabled={!draft.trim()}>
          Göster
        </button>
        {value && (
          <button
            className="sg-button"
            type="button"
            onClick={() => {
              setDraft('');
              onChange('');
            }}
          >
            Kapat
          </button>
        )}
      </form>
      {r.isLoading && value && <Loading text="Bağlantılar getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {d && value && (
        <div style={{ marginTop: 12 }}>
          <div className="sg-sub">
            {d.item ? <PageName row={d.item} /> : <span className="sg-mono">{short(d.url)}</span>}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '8px 0' }}>
            <span className="sg-chip">{d.crawled ? 'Bağlantıları okundu' : 'Kendisi taranmadı'}</span>
            <span className="sg-chip">{d.depth == null ? 'Derinlik bilinmiyor' : `Anasayfadan ${fmt(d.depth)} tıklama`}</span>
            <span className={`sg-chip ${d.inlinks.filter((i) => !i.nofollow).length ? '' : 'bad'}`}>{fmt(d.inlinks.length)} sayfadan gelen bağlantı</span>
          </div>
          {d.path.length > 1 && <p className="sg-sub sg-mono" style={{ wordBreak: 'break-all' }}>{d.path.map(short).join(' → ')}</p>}
          <div className="sg-grid">
            <LinkList title="Gelen bağlantılar" items={d.inlinks} empty="Taranan sayfaların hiçbiri bu adrese bağlantı vermiyor." onPick={onChange} />
            <LinkList
              title="Giden bağlantılar"
              items={d.outlinks}
              empty={d.outlinksKnown ? 'Site içine bağlantı yok.' : 'Bu sayfa taranmadığı için giden bağlantıları bilinmiyor.'}
              onPick={onChange}
            />
          </div>
        </div>
      )}
    </section>
  );
}

const CLASS_LABEL: Record<LinkInfo['anchorClass'], string> = { ok: '', generic: 'genel metin', empty: 'metinsiz' };

function LinkList({ title, items, empty, onPick }: { title: string; items: LinkInfo[]; empty: string; onPick: (u: string) => void }) {
  const [start, setStart] = useState(0);
  const shown = items.slice(start, start + PAGE);
  return (
    <section className="sg-span-6">
      <h3 style={{ margin: '8px 0' }}>
        {title} ({fmt(items.length)})
      </h3>
      {!items.length ? (
        <p className="sg-sub">{empty}</p>
      ) : (
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 8 }}>
          {shown.map((l) => (
            <li key={l.url} style={{ fontSize: 12.5, wordBreak: 'break-all' }}>
              <button className="sg-filter" style={{ textAlign: 'left' }} onClick={() => onPick(l.url)} title="Bu sayfanın bağlantılarını göster">
                {l.name || short(l.url)}
              </button>
              <div className="sg-mono" style={{ fontSize: 11, marginTop: 2 }}>
                {KIND_LABEL[l.kind] ?? l.kind}
                {l.anchors.filter(Boolean).length ? ` · “${l.anchors.filter(Boolean).join('”, “')}”` : ''}
                {CLASS_LABEL[l.anchorClass] && ` · ${CLASS_LABEL[l.anchorClass]}`}
                {l.nofollow && ' · nofollow'}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Pager start={start} total={items.length} setStart={setStart} />
    </section>
  );
}

/* ------------------------------------------------------------------ küçük parçalar */
function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono">{value}</div>
      {note && <div className="sg-kpi-note">{note}</div>}
    </div>
  );
}

function Pager({ start, total, setStart }: { start: number; total: number; setStart: (n: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <div className="sg-pager" style={{ marginTop: 12 }}>
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
  );
}
