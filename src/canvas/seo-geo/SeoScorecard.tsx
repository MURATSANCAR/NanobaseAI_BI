import type { Kaynaklar } from '../components/sqlInfo';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight, ChevronLeft, ChevronRight, ExternalLink, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { FLAG_LABEL, RIGHTS_LABEL, RIGHTS_TONE, call, dateTime, fmt, qs, scoreTone, type CrmBook, type CrmFlag, type CrmRights } from './api';
import CrmPanel from './CrmPanel';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { EmptyHint, Explain } from '../components/Explain';
import { TermLabel } from './terms';

/* ------------------------------------------------------------------ uç tipleri (/api/v1/seo-geo/scorecard*) */
type Status = 'iyi' | 'dikkat' | 'sorun' | 'bilinmiyor';
type Action = { text: string; link: string };
type Section = {
  id: string;
  title: string;
  weight: number;
  status: Status;
  summary: string;
  facts: Array<{ label: string; value: string }>;
  actions: Action[];
  link: string;
  reason: string | null;
  /** Yalnız «arama» bölümünde: bu sayfanın göründüğü bütün aramalar. */
  queries?: Array<{ query: string; clicks: number; impressions: number; position: number | null }>;
  /** Yalnız «video» bölümünde. */
  thumbnail?: string;
};
type Scorecard = {
  product: {
    id: string;
    name: string;
    code: string | null;
    brand: string | null;
    active: boolean;
    author: string | null;
    image: string | null;
    url: string | null;
    barcode: string | null;
    sales: number;
    views: number;
    score: number;
    comments: number;
  };
  grade: {
    score: number | null;
    letter: string | null;
    coverage: number;
    lowData: boolean;
    counts: Record<Status, number>;
    points: Record<'iyi' | 'dikkat' | 'sorun', number>;
    letters: Array<{ letter: string; min: number }>;
  };
  top: Array<Action & { sectionId: string; section: string; status: Status }>;
  sections: Section[];
  crm: CrmBook | null;
  weights: Array<{ id: string; title: string; weight: number }>;
  generatedAt: string;
};
type BookRow = {
  id: string;
  name: string;
  code: string | null;
  brand: string | null;
  author: string | null;
  image: string | null;
  sales: number;
  score: number;
  rights: CrmRights | null;
  statusFlag: CrmFlag | null;
};

const api = {
  search: (p: { q?: string; start?: number; limit?: number }) => call<{ total: number; start: number; items: BookRow[] }>(`scorecard?${qs(p)}`),
  card: (id: string) => call<Scorecard>(`scorecard/${encodeURIComponent(id)}`, { timeout: 120_000 }),
};

const STATUS_LABEL: Record<Status, string> = { iyi: 'İyi', dikkat: 'Dikkat', sorun: 'Sorun', bilinmiyor: 'Bilinmiyor' };
const STATUS_TONE: Record<Status, string> = { iyi: 'good', dikkat: 'mid', sorun: 'bad', bilinmiyor: '' };
const GRADE_TONE = (l: string | null) => (l === 'A' || l === 'B' ? 'good' : l === 'C' ? 'mid' : l ? 'bad' : '');
const PAGE = 40;

/** Kitap SEO karnesi: bir kitabın bütün SEO & GEO ekranlarındaki durumu tek sayfada. `?urun=` yoksa kitap seçilir. */
export default function SeoScorecard() {
  const [params, setParams] = useSearchParams();
  const selected = params.get('urun') ?? '';

  const choose = (id: string) => {
    const next = new URLSearchParams(params);
    if (id) next.set('urun', id);
    else next.delete('urun');
    setParams(next);
  };

  return (
    <SeoLayout
      path="/seo-geo/kitap"
      crumb="Kitap karnesi"
      eyebrow="SEO & GEO · Kitap karnesi"
      title="Kitap karnesi"
      lead="Bir kitabın bütün SEO ve GEO durumu tek sayfada: ürün kaydı, hakları, Google’daki durumu, aramadaki performansı, rakipleri, yapay zekâ cevapları ve daha fazlası. Önce en üstteki işlere bakın; her bölüm kendi ayrıntı ekranına bağlanır. Yalnız okunur."
      actions={
        selected && (
          <button className="sg-button" onClick={() => choose('')}>
            <Search size={16} aria-hidden /> Başka kitap seç
          </button>
        )
      }
    >
      {selected ? <Card id={selected} /> : <Picker onPick={choose} />}
    </SeoLayout>
  );
}

/* ------------------------------------------------------------------ kitap seçimi */
function Picker({ onPick }: { onPick: (id: string) => void }) {
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [query]);

  const list = useQuery({
    queryKey: ['seo-scorecard-search', query, start],
    queryFn: () => api.search({ q: query, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (prev) => prev,
  });
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;

  return (
    <section className="sg-card" aria-label="Kitap seç">
      <h2>Kitap seçin</h2>
      <p className="sg-sub">Satıştaki kitaplar çok satandan aza sıralı. Ad, yazar, ürün kodu, yayınevi ya da barkodla arayın.</p>
      <label className="sg-search" style={{ marginBottom: 12 }}>
        <Search size={16} aria-hidden />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, yazar, ürün kodu ya da barkod" aria-label="Kitap ara" autoFocus />
      </label>
      {list.isLoading && <Loading text="Kitaplar getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {list.data && !items.length && (
        <EmptyHint
          title="Kitap bulunamadı"
          why={query ? 'Bu aramaya uyan satıştaki kitap yok; adı kısaltarak ya da yazarla arayın.' : 'T-soft’tan henüz ürün okunmadı; gece okumasından sonra kitaplar burada listelenir.'}
        />
      )}
      <div className="sg-list">
        {items.map((p) => (
          <button key={p.id} className="sg-item" onClick={() => onPick(p.id)}>
            {p.image ? <img src={p.image} alt="" loading="lazy" /> : <span className="sg-noimg" aria-hidden />}
            <span style={{ minWidth: 0 }}>
              <span className="sg-item-name">{p.name || p.code}</span>
              <span className="sg-item-meta">
                {[p.author, p.brand].filter(Boolean).join(' · ') || p.code} · <span className="sg-mono">{fmt(p.sales)}</span> satış
              </span>
            </span>
            <span className="sg-item-side">
              <span className={`sg-chip ${scoreTone(p.score)}`}>Puan {p.score}</span>
              {p.statusFlag ? (
                <span className="sg-chip bad">{FLAG_LABEL[p.statusFlag]}</span>
              ) : (
                p.rights && <span className={`sg-chip ${RIGHTS_TONE[p.rights]}`}>{RIGHTS_LABEL[p.rights]}</span>
              )}
            </span>
          </button>
        ))}
      </div>
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
  );
}

/* ------------------------------------------------------------------ karne */
function Card({ id }: { id: string }) {
  const card = useQuery({ queryKey: ['seo-scorecard', id], queryFn: () => api.card(id), enabled: ENGINE_ENABLED, retry: false });
  if (card.isLoading) return <Loading text="Karne hazırlanıyor; bütün ekranların verisi okunuyor…" />;
  if (card.error) return <Failed error={card.error} />;
  const d = card.data;
  if (!d) return null;
  const p = d.product;
  const g = d.grade;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <section className="sg-card" aria-label="Kitap">
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', alignItems: 'flex-start' }}>
          {p.image ? (
            <img src={p.image} alt={`${p.name} kapağı`} style={{ width: 88, height: 124, objectFit: 'cover', borderRadius: 10, background: 'var(--sg-soft)', flex: 'none' }} />
          ) : (
            <span aria-hidden style={{ width: 88, height: 124, borderRadius: 10, background: 'var(--sg-soft)', flex: 'none' }} />
          )}
          <div style={{ minWidth: 0, flex: '1 1 240px' }}>
            <h2 style={{ fontSize: 20 }}>{p.name}</h2>
            <p className="sg-sub" style={{ margin: '2px 0 10px' }}>
              {[p.author, p.brand].filter(Boolean).join(' · ') || '—'}
            </p>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              <span className="sg-chip">
                <span className="sg-mono">{fmt(p.sales)}</span> satış
              </span>
              <span className="sg-chip">
                <span className="sg-mono">{fmt(p.views)}</span> görüntülenme
              </span>
              <span className={`sg-chip ${scoreTone(p.score)}`}>Ürün puanı {p.score}</span>
              {!p.active && <span className="sg-chip bad">T-soft’ta pasif</span>}
              {p.url && (
                <a className="sg-chip" href={p.url} target="_blank" rel="noreferrer">
                  Sitede aç <ExternalLink size={11} aria-hidden />
                </a>
              )}
            </div>
            <p className="sg-sub" style={{ margin: '10px 0 0', fontSize: 11.5 }}>
              <span className="sg-mono">{p.code}</span>
              {p.barcode ? <> · barkod <span className="sg-mono">{p.barcode}</span></> : null} · karne {dateTime(d.generatedAt)}
            </p>
          </div>
          <div style={{ textAlign: 'center', flex: 'none', minWidth: 110 }} aria-label={`Genel not ${g.letter ?? 'yok'}, ${g.score ?? '—'} puan`}>
            <div className="sg-kpi-label">Genel not <SeoInfo k={card.data?.kaynaklar} label="Genel not" /> <Explain label="Genel not">Aşağıdaki bölümlerin durumuna (iyi, dikkat, sorun) göre verilen A–F arası not. Hesabın ayrıntısı «Not nasıl hesaplanır» bölümünde.</Explain></div>
            <div
              className={`sg-chip ${GRADE_TONE(g.letter)}`}
              style={{ fontSize: 30, fontWeight: 800, padding: '8px 22px', marginTop: 6, borderRadius: 18 }}
            >
              {g.letter ?? '—'}
            </div>
            <div className="sg-kpi-note sg-mono">{g.score != null ? `${g.score}/100` : 'Veri yok'}</div>
            {g.lowData && <div className="sg-kpi-note">Az veriyle; bölümlerin çoğu bilinmiyor</div>}
          </div>
        </div>
      </section>

      <section className="sg-card" aria-label="Önce yapılacak işler">
        <h2>Önce yapılacak {d.top.length > 0 ? d.top.length : ''} iş</h2>
        <p className="sg-sub" style={{ margin: '0 0 4px' }}>Bu kitap için en önemli işler; işe dokunun, ilgili ekran açılsın.</p>
        {d.top.length === 0 ? (
          <p className="sg-banner ok" style={{ margin: 0 }}>Bilinen bölümlerde açık iş yok.</p>
        ) : (
          <ol style={{ margin: '8px 0 0', paddingLeft: 20, display: 'grid', gap: 8 }}>
            {d.top.map((a) => (
              <li key={a.text} style={{ fontSize: 13, lineHeight: 1.5 }}>
                <span className={`sg-chip ${STATUS_TONE[a.status]}`} style={{ marginRight: 6 }}>
                  {a.section}
                </span>
                <Link to={a.link}>{a.text}</Link>
              </li>
            ))}
          </ol>
        )}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
          {(['sorun', 'dikkat', 'iyi', 'bilinmiyor'] as Status[]).map((s) => (
            <span key={s} className={`sg-chip ${STATUS_TONE[s]}`}>
              {STATUS_LABEL[s]} <span className="sg-mono">{g.counts[s] ?? 0}</span>
            </span>
          ))}
        </div>
        <details className="sg-more" style={{ marginTop: 12 }}>
          <summary>Not nasıl hesaplanır</summary>
          <p>
            Her bölüm durumuna göre puan alır (iyi {g.points.iyi}, dikkat {g.points.dikkat}, sorun {g.points.sorun}); genel not bu puanların ağırlıklı
            ortalamasıdır. Bilinmeyen bölüm hesaba girmez. Bilinen bölümlerin ağırlık payı %{Math.round(g.coverage * 100)}.
            {' '}Harf: {g.letters.map((l) => `${l.letter} ≥ ${l.min}`).join(', ')}.
          </p>
          <p>Ağırlıklar: {d.weights.map((w) => `${w.title} ${w.weight}`).join(' · ')}.</p>
        </details>
      </section>

      <div className="sg-grid">
        {d.sections.map((s) => (
          <SectionCard key={s.id} s={s} crm={s.id === 'crm' ? d.crm : undefined} k={d.kaynaklar} />
        ))}
      </div>
    </div>
  );
}

function SectionCard({ s, crm, k }: { s: Section; crm?: CrmBook | null; k?: Kaynaklar | null }) {
  return (
    <section className="sg-card sg-span-6" aria-label={s.title} style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
        <h2 style={{ margin: 0 }}>{s.title}</h2>
        <span className={`sg-chip ${STATUS_TONE[s.status]}`}>{STATUS_LABEL[s.status]}</span>
      </div>
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: s.status === 'bilinmiyor' ? 'var(--sg-muted)' : 'var(--sg-ink)' }}>{s.summary}</p>

      {s.thumbnail && <img src={s.thumbnail} alt="" loading="lazy" style={{ width: 160, maxWidth: '100%', borderRadius: 10 }} />}

      {s.facts.length > 0 && (
        <dl className="sg-facts" style={{ margin: 0 }}>
          {s.facts.map((f) => (
            <div key={f.label}>
              <dt>{f.label}</dt>
              <dd>{f.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {s.queries && s.queries.length > 0 && (
        <details className="sg-more">
          <summary>
            Göründüğü bütün aramalar (<span className="sg-mono">{fmt(s.queries.length)}</span>)
          </summary>
          <div className="sg-table-wrap" style={{ marginTop: 8 }}>
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Arama <SeoInfo k={k} label="Arama" /></th>
                  <th style={{ textAlign: 'right' }}>Tıklama</th>
                  <th style={{ textAlign: 'right' }}><TermLabel k="impressions" label="Gösterim" /></th>
                  <th style={{ textAlign: 'right' }}><TermLabel k="position" label="Sıra" /></th>
                </tr>
              </thead>
              <tbody>
                {s.queries.map((q) => (
                  <tr key={q.query}>
                    <td>{q.query}</td>
                    <td className="num sg-mono">{fmt(q.clicks)}</td>
                    <td className="num sg-mono">{fmt(q.impressions)}</td>
                    <td className="num sg-mono">{fmt(q.position, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {s.actions.length > 0 && (
        <ul className="sg-hints" style={{ margin: 0 }}>
          {s.actions.map((a) => (
            <li key={a.text}>
              <Link to={a.link}>{a.text}</Link>
            </li>
          ))}
        </ul>
      )}

      {crm && (
        <details className="sg-more">
          <summary>CRM kartının tamamı</summary>
          <div style={{ marginTop: 8 }}>
            <CrmPanel book={crm} />
          </div>
        </details>
      )}

      <Link className="sg-button" style={{ alignSelf: 'flex-start', marginTop: 'auto' }} to={s.link}>
        Ayrıntı ekranına git <ArrowRight size={14} aria-hidden />
      </Link>
    </section>
  );
}
