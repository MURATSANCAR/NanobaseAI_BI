import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, RefreshCw, Search, Star } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';
import { EmptyHint, Explain } from '../components/Explain';

const PAGE = 40;
type View = 'yorumsuz' | 'puansiz_sema' | 'yorumlu' | 'dusuk';
type Row = {
  id: string;
  name: string;
  author: string | null;
  image: string | null;
  url: string | null;
  sales: number;
  views: number;
  count: number;
  average: number | null;
  stars: Record<string, number> | null;
  source: string | null;
  schema: 'tamam' | 'puan_yok' | 'taranmadi';
};
type Summary = {
  activeBooks: number;
  withReviews: number;
  reviews: number;
  average: number | null;
  reviewStars: Record<string, number> | null;
  bookAverages: Record<string, number>;
  zeroTopSelling: number;
  schemaMissing: number;
  schemaUnchecked: number;
  prioritySales: number;
  lastRead: string | null;
  state: { running: boolean; done: number; startedAt: string | null; finishedAt: string | null; error: string | null };
};
type Resp = { summary: Summary; views: Record<View, string>; recommendations: string[]; total: number; start: number; items: Row[] };

const SCHEMA_LABEL: Record<Row['schema'], string> = { tamam: 'Google puanı görüyor', puan_yok: 'Google puanı görmüyor', taranmadi: 'Sayfa taranmadı' };

/** Okur yorumları: çok satıp hiç yorum almamış kitaplar, puan dağılımı ve yorumu olup şemada puanı görünmeyen sayfalar.
 *  Yalnız sayı ve puan okunur; yorumcu bilgisi saklanmaz, hiçbir şey gönderilmez. */
export default function SeoReviews() {
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [view, setView] = useState<View>('yorumsuz');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [view, query]);

  const list = useQuery({
    queryKey: ['seo-reviews', view, query, start],
    queryFn: () => call<Resp>(`reviews?${qs({ view, q: query, start, limit: PAGE })}`),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (s) => (s.state.data?.summary.state.running ? 8000 : false),
  });
  const read = useMutation({
    mutationFn: () => call<{ started: boolean }>('reviews/refresh', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-reviews'] }),
  });
  const s = list.data?.summary;
  const total = list.data?.total ?? 0;
  const running = !!s?.state.running;
  const stars = s?.reviewStars ?? s?.bookAverages;
  const starMax = Math.max(1, ...Object.values(stars ?? {}));

  return (
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/yorumlar"
      crumb="Okur yorumları"
      eyebrow="SEO & GEO · Okur yorumları"
      title="Okur yorumları"
      lead="Yorum ve yıldız, Google sonucunda kitabın öne çıkmasını ve yapay zekâ cevaplarında güvenilir görünmesini sağlar. Burada çok satıp yorum almamış kitaplar ve puanı Google’a görünmeyen sayfalar listelenir. Yalnız yorum sayısı ve puan okunur; bu ekran hiçbir şey göndermez."
      actions={
        canRun && (
          <button className="sg-button" onClick={() => read.mutate()} disabled={read.isPending || running}>
            {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {running ? `Yorumlar okunuyor (${fmt(s?.state.done)})` : 'Yorumları yeniden oku'}
          </button>
        )
      }
    >
      {list.isLoading && <Loading text="Yorum özeti getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {read.error && <Failed error={read.error} />}
      {s?.state.error && <p className="sg-banner err">Son yorum okuması başarısız: {s.state.error}</p>}

      {s && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Yorumlu kitap" value={`${fmt(s.withReviews)} / ${fmt(s.activeBooks)}`} note={`Toplam ${fmt(s.reviews)} yorum · son okuma ${dateTime(s.lastRead)}`} info={<SeoInfo k={list.data?.kaynaklar} label="Yorumlu kitap" />} />
            <Kpi label="Ortalama puan" value={s.average == null ? '—' : fmt(s.average, 1)} note="Yorum sayısıyla ağırlıklı, 5 üzerinden" info={<SeoInfo k={list.data?.kaynaklar} label="Ortalama puan" />}
              explain="Bütün yorumların yıldız ortalaması; çok yorumlu kitap ortalamaya daha çok etki eder." />
            <Kpi label="Çok satan, yorumsuz" value={fmt(s.zeroTopSelling)} note={`${fmt(s.prioritySales)} ve üstü satış, hiç yorum yok`} tone={s.zeroTopSelling ? 'bad' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Çok satan, yorumsuz" />}
              explain="Satışı eşiğin üstünde olduğu hâlde hiç yorumu olmayan kitaplar; yorum toplama çalışmasında önce bunlar düşünülmeli." />
            <Kpi label="Google puanı görmüyor" value={fmt(s.schemaMissing)} note={`Yorumlu ama sayfanın yapısal verisinde puan yok · taranmamış ${fmt(s.schemaUnchecked)}`} tone={s.schemaMissing ? 'bad' : undefined} info={<SeoInfo k={list.data?.kaynaklar} label="Şemada puan yok" />}
              explain="Kitabın yorumu var ama sayfadaki gizli yapısal veride (şema) puan yazmıyor; bu yüzden Google sonucunda yıldız çıkmaz. Düzeltme site teması tarafında yapılır." />
          </section>

          <div className="sg-grid">
            <section className="sg-card sg-span-5" aria-label="Puan dağılımı">
              <h2>Puan dağılımı <SeoInfo k={list.data?.kaynaklar} label="Puan dağılımı" /></h2>
              <p className="sg-sub">{s.reviewStars ? 'Onaylı yorumların kaç yıldız verdiği.' : 'Kitapların ortalama puanlarının dağılımı (yorum ayrıntısı henüz okunmadı).'}</p>
              <div className="sg-bars">
                {['5', '4', '3', '2', '1'].map((k) => (
                  <div key={k} className="sg-bar-row">
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      {k} <Star size={12} aria-label="yıldız" />
                    </span>
                    <span className="sg-mono">{fmt(stars?.[k] ?? 0)}</span>
                    <div className="sg-bar" aria-hidden>
                      <i style={{ width: `${(100 * (stars?.[k] ?? 0)) / starMax}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </section>
            <section className="sg-card sg-span-7" aria-label="Öneriler">
              <h2>Ne yapılmalı <SeoInfo k={list.data?.kaynaklar} label="Ne yapılmalı" /></h2>
              <ul style={{ margin: 0, paddingLeft: 18, display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
                {list.data?.recommendations.map((r) => <li key={r}>{r}</li>)}
              </ul>
            </section>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div className="sg-filters" role="radiogroup" aria-label="Liste">
              {(Object.entries(list.data?.views ?? {}) as Array<[View, string]>).map(([id, label]) => (
                <button key={id} className="sg-filter" role="radio" aria-checked={view === id} aria-pressed={view === id} onClick={() => setView(id)}>
                  {label}
                </button>
              ))}
            </div>
            <label className="sg-search">
              <Search size={16} aria-hidden />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap ya da yazar" aria-label="Kitap ara" />
            </label>
          </div>

          {list.data && !list.data.items.length && (
            <EmptyHint title="Bu listeye uyan kitap yok" why={query ? 'Aramayı kısaltın ya da temizleyin.' : 'Başka bir liste seçin.'} />
          )}
          <div className="sg-list">
            {list.data?.items.map((r) => (
              <div key={r.id} className="sg-item" style={{ cursor: 'default' }}>
                {r.image ? <img src={r.image} alt="" loading="lazy" /> : <span className="sg-noimg" aria-hidden />}
                <span style={{ minWidth: 0 }}>
                  <span className="sg-item-name">{r.name}</span>
                  <span className="sg-item-meta sg-mono">
                    {fmt(r.sales)} satış{r.author ? ` · ${r.author}` : ''}
                  </span>
                </span>
                <span className="sg-item-side">
                  {r.count ? (
                    <span className="sg-chip good">
                      {fmt(r.count)} yorum{r.average ? ` · ${fmt(r.average, 1)}★` : ''}
                    </span>
                  ) : (
                    <span className="sg-chip bad">Yorum yok</span>
                  )}
                  {r.count > 0 && <span className={`sg-chip ${r.schema === 'puan_yok' ? 'bad' : r.schema === 'tamam' ? 'good' : ''}`}>{SCHEMA_LABEL[r.schema]}</span>}
                  {r.url && (
                    <a className="sg-button" href={r.url} target="_blank" rel="noreferrer" aria-label={`${r.name} sayfasını aç`}>
                      <ExternalLink size={14} aria-hidden />
                    </a>
                  )}
                </span>
              </div>
            ))}
          </div>
          {total > PAGE && <Pager start={start} total={total} onChange={setStart} />}
        </>
      )}
    </SeoLayout>
  );
}

function Pager({ start, total, onChange }: { start: number; total: number; onChange: (n: number) => void }) {
  return (
    <div className="sg-pager">
      <button className="sg-button" disabled={start === 0} onClick={() => onChange(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
        <ChevronLeft size={16} aria-hidden />
      </button>
      <span className="sg-mono">
        {fmt(start + 1)}–{fmt(Math.min(total, start + PAGE))} / {fmt(total)}
      </span>
      <button className="sg-button" disabled={start + PAGE >= total} onClick={() => onChange(start + PAGE)} aria-label="Sonraki sayfa">
        <ChevronRight size={16} aria-hidden />
      </button>
    </div>
  );
}

function Kpi({ label, value, note, tone, info, explain }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; info?: ReactNode; explain?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}{explain ? <> <Explain label={label}>{explain}</Explain></> : null}</div>
      <div className="sg-kpi-value sg-mono" style={tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : undefined}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}
