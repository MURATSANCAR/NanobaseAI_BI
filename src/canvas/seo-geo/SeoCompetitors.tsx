import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

type Verdict = 'geride' | 'onde' | 'yok';
type RunState = { running: boolean; done: number; failed: number; queue: number | null; startedAt: string | null; finishedAt: string | null; error: string | null };
type Features = { shopping?: boolean; shoppingUs?: boolean; aiOverview?: boolean; aiOverviewUs?: boolean | null; knowledgePanel?: boolean; knowledgePanelTitle?: string | null };
type Row = {
  productId: string;
  name: string;
  image: string | null;
  url: string | null;
  sales: number;
  query: string;
  searchedAt: string;
  our: number | null;
  best: { domain: string; position: number } | null;
  positions: Record<string, number | null>;
  verdict: Verdict;
  features: Features;
  results: Array<{ position: number; domain: string; title: string; link: string }>;
};
type Summary = {
  configured: boolean;
  our: string;
  competitors: string[];
  tracked: number;
  first: number;
  firstShare: number | null;
  counts: Record<Verdict, number>;
  domains: Array<{ domain: string; ours: boolean; found: number; average: number | null; beatsUs: number }>;
  features: { shopping: number; shoppingUs: number; aiOverview: number; aiOverviewUs: number; knowledgePanel: number };
  quota: { monthly: number; used: number; remaining: number; dailySlice: number; month: string };
  refreshDays: number;
  state: RunState;
  lastSearched: string | null;
};

const PAGE = 40;
const VERDICT: Record<Verdict, { label: string; tone: 'good' | 'mid' | 'bad' }> = {
  onde: { label: 'Öndeyiz', tone: 'good' },
  geride: { label: 'Rakip önde', tone: 'bad' },
  yok: { label: 'İlk 20’de yokuz', tone: 'mid' },
};

const api = {
  list: (p: { filter?: string; start: number; limit: number }) =>
    call<{ total: number; start: number; items: Row[]; summary: Summary }>(`competitors?${qs(p)}`),
  run: () => call<{ started: boolean; count: number }>('competitors/run', { method: 'POST' }),
};

/** Rakipler: aynı kitap aramasında (kitap adı + yazar) Google’da kim kaçıncı. Sıra çok satandan; kota aylık. */
export default function SeoCompetitors() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const filter = (params.get('suzgec') ?? '') as Verdict | '';
  const [start, setStart] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => setStart(0), [filter]);

  const list = useQuery({
    queryKey: ['seo-competitors', filter, start],
    queryFn: () => api.list({ filter, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (prev) => prev,
    refetchInterval: (s) => (s.state.data?.summary.state.running ? 15000 : false),
  });
  const run = useMutation({ mutationFn: api.run, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-competitors'] }) });

  const setFilter = (v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set('suzgec', v);
    else next.delete('suzgec');
    setParams(next, { replace: true });
  };

  const s = list.data?.summary;
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const running = !!s?.state.running;

  return (
    <SeoLayout
      path="/seo-geo/rakipler"
      crumb="Rakipler"
      eyebrow="SEO & GEO · Google sırası"
      title="Rakipler"
      lead={`Çok satan kitaplarımız Google’da “kitap adı + yazar” diye arandığında timas.com.tr ile rakip siteler kaçıncı sırada; sayfada alışveriş sonuçları, yapay zekâ özeti ve bilgi paneli var mı. Her kitap en çok ${s?.refreshDays ?? 30} günde bir yeniden aranır; arama sayısı aylık kotayla sınırlıdır.`}
      actions={
        s?.configured ? (
          <button className="sg-button" onClick={() => run.mutate()} disabled={run.isPending || running || !s.quota.remaining}>
            {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Search size={16} aria-hidden />}
            {running ? `Aranıyor ${fmt(s.state.done)} / ${fmt(s.state.queue)}` : `Şimdi ara (${fmt(s.quota.remaining)} arama kaldı)`}
          </button>
        ) : undefined
      }
    >
      {list.isLoading && <Loading text="Aramalar getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {run.error && <Failed error={run.error} />}
      {s?.state.error && <p className="sg-banner err">Son tur yarıda kaldı: {s.state.error}</p>}

      {s && !s.configured && (
        <div className="sg-empty">
          <h2>Google arama sonucu anahtarı girilmemiş</h2>
          <p>Yönetim → SEO & GEO ekranında arama sonucu anahtarı, aylık arama kotası ve rakip alan adları girildiğinde her gece kotanın o güne düşen payı kadar kitap aranır.</p>
        </div>
      )}

      {s && s.configured && !s.competitors.length && (
        <p className="sg-banner">Rakip alan adı girilmemiş (Yönetim → SEO & GEO → Rakip siteler). Yalnız bizim sıramız gösteriliyor.</p>
      )}

      {s && s.configured && !s.tracked && !running && (
        <div className="sg-empty">
          <h2>Henüz arama yapılmadı</h2>
          <p>“Şimdi ara”ya basın ya da gece işini bekleyin. Bu ay {fmt(s.quota.remaining)} arama hakkı var; gece işi günde yaklaşık {fmt(s.quota.dailySlice)} kitap arar.</p>
        </div>
      )}

      {s && s.tracked > 0 && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Aranan kitap" value={fmt(s.tracked)} note={`Son arama ${dateTime(s.lastSearched)}`} />
            <Kpi label="Rakiplerden öndeyiz" value={s.firstShare == null ? '—' : `%${fmt(s.firstShare, 1)}`} note={`${fmt(s.first)} kitapta takip edilen siteler içinde ilk biz`} tone="good" />
            <Kpi label="Rakip önde" value={fmt(s.counts.geride)} note="Bizden üstte en az bir rakip var" tone={s.counts.geride ? 'bad' : undefined} />
            <Kpi label="İlk 20’de yokuz" value={fmt(s.counts.yok)} note="Kitap adı + yazar aramasında sitemiz çıkmıyor" tone={s.counts.yok ? 'bad' : undefined} />
            <Kpi label="Aylık kota" value={`${fmt(s.quota.used)} / ${fmt(s.quota.monthly)}`} note={`Kalan ${fmt(s.quota.remaining)} · günlük pay ${fmt(s.quota.dailySlice)}`} />
          </section>

          <div className="sg-grid">
            <section className="sg-card sg-span-7" aria-label="Siteler">
              <h2>Siteler</h2>
              <p className="sg-sub">Ortalama sıra yalnız sitenin ilk 20’de çıktığı aramalardan. “Bizi geçtiği”: site bizden üstte ya da biz hiç yokken o çıkmış.</p>
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Site</th>
                      <th style={{ textAlign: 'right' }}>Çıktığı kitap</th>
                      <th style={{ textAlign: 'right' }}>Ortalama sıra</th>
                      <th style={{ textAlign: 'right' }}>Bizi geçtiği</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.domains.map((d) => (
                      <tr key={d.domain}>
                        <td>
                          <span className="sg-mono">{d.domain}</span> {d.ours && <span className="sg-chip violet">biz</span>}
                        </td>
                        <td className="num">{fmt(d.found)}</td>
                        <td className="num">{d.average == null ? '—' : fmt(d.average, 1)}</td>
                        <td className="num">{d.ours ? '—' : fmt(d.beatsUs)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="sg-card sg-span-5" aria-label="Sayfa öğeleri">
              <h2>Arama sayfasındaki öğeler</h2>
              <p className="sg-sub">Kaç aramada göründü; parantez içinde bizim sitemizin içinde yer aldığı arama sayısı.</p>
              <div className="sg-bars">
                <Bar label="Alışveriş sonuçları" n={s.features.shopping} of={s.tracked} note={`biz ${fmt(s.features.shoppingUs)}`} />
                <Bar label="Yapay zekâ özeti" n={s.features.aiOverview} of={s.tracked} note={`bize kaynak veren ${fmt(s.features.aiOverviewUs)}`} />
                <Bar label="Bilgi paneli" n={s.features.knowledgePanel} of={s.tracked} />
              </div>
            </section>
          </div>

          <div className="sg-filters" role="toolbar" aria-label="Süzgeç">
            <Chip on={!filter} onClick={() => setFilter('')} label="Tümü" n={s.tracked} />
            {(['geride', 'yok', 'onde'] as Verdict[]).map((v) => (
              <Chip key={v} on={filter === v} onClick={() => setFilter(filter === v ? '' : v)} label={VERDICT[v].label} n={s.counts[v]} />
            ))}
          </div>

          <section className="sg-card" aria-label="Kitaplar">
            {!items.length && (
              <div className="sg-empty">
                <h2>Kitap yok</h2>
                <p>Bu süzgece uyan aranmış kitap yok.</p>
              </div>
            )}
            {!!items.length && (
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Kitap</th>
                      <th style={{ textAlign: 'right' }}>Bizim sıra</th>
                      <th>En iyi rakip</th>
                      <th>Durum</th>
                      <th>Sayfada</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((r) => (
                      <BookRow key={r.productId} row={r} open={open === r.productId} onToggle={() => setOpen(open === r.productId ? null : r.productId)} our={s.our} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {total > PAGE && (
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
            )}
          </section>
        </>
      )}
    </SeoLayout>
  );
}

function BookRow({ row: r, open, onToggle, our }: { row: Row; open: boolean; onToggle: () => void; our: string }) {
  const v = VERDICT[r.verdict];
  const f = r.features;
  return (
    <>
      <tr>
        <td>
          <button onClick={onToggle} aria-expanded={open} style={{ all: 'unset', cursor: 'pointer', fontWeight: 700, color: 'var(--sg-ink)' }}>
            {r.name}
          </button>
          <div style={{ fontSize: 11, color: 'var(--sg-muted)', marginTop: 2 }}>
            “{r.query}” · {fmt(r.sales)} satış · {dateTime(r.searchedAt)}
          </div>
        </td>
        <td className="num">{r.our ?? '—'}</td>
        <td>{r.best ? <span className="sg-mono">{r.best.domain} · {r.best.position}</span> : '—'}</td>
        <td>
          <span className={`sg-chip ${v.tone}`}>{v.label}</span>
        </td>
        <td>
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {f.shopping && <span className={`sg-chip ${f.shoppingUs ? 'good' : ''}`}>Alışveriş{f.shoppingUs ? ' · biz' : ''}</span>}
          {f.aiOverview && <span className={`sg-chip ${f.aiOverviewUs ? 'good' : ''}`}>Yapay zekâ özeti{f.aiOverviewUs ? ' · biz' : ''}</span>}
          {f.knowledgePanel && <span className="sg-chip violet">Bilgi paneli</span>}
          </div>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={5} style={{ background: '#fcfbfe' }}>
            <ol style={{ margin: 0, paddingLeft: 0, listStyle: 'none', display: 'grid', gap: 4, fontSize: 12 }}>
              {r.results.map((x) => (
                <li key={`${x.position}-${x.link}`} style={{ display: 'flex', gap: 8, alignItems: 'baseline', minWidth: 0 }}>
                  <span className="sg-mono" style={{ width: 22, textAlign: 'right', flex: 'none' }}>{x.position}</span>
                  <span className="sg-mono" style={{ flex: 'none', fontWeight: x.domain.endsWith(our) ? 800 : 500 }}>{x.domain}</span>
                  <a href={x.link} target="_blank" rel="noreferrer" style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'inherit' }}>
                    {x.title} <ExternalLink size={11} aria-hidden />
                  </a>
                </li>
              ))}
              {!r.results.length && <li>Bu aramada organik sonuç gelmedi.</li>}
            </ol>
          </td>
        </tr>
      )}
    </>
  );
}

function Bar({ label, n, of, note }: { label: string; n: number; of: number; note?: string }) {
  const pct = of ? Math.round((100 * n) / of) : 0;
  return (
    <div className="sg-bar-row">
      <span>{label}</span>
      <span className="sg-mono">
        {fmt(n)} · %{pct}
        {note ? ` (${note})` : ''}
      </span>
      <div className="sg-bar">
        <i style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Kpi({ label, value, note, tone }: { label: string; value: string; note: string; tone?: 'good' | 'bad' }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono" style={tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : undefined}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}

function Chip({ on, onClick, label, n }: { on: boolean; onClick: () => void; label: string; n: number | undefined }) {
  return (
    <button className="sg-filter" aria-pressed={on} onClick={onClick}>
      {label} <span className="sg-mono">{fmt(n ?? 0)}</span>
    </button>
  );
}
