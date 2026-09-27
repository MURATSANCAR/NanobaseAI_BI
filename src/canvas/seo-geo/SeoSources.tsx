import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/** Yapay zekânın kaynakları: /api/v1/seo-geo/ai-sources, /ai-sources/{alan}, /ai-source-questions. Yalnız okunur. */

type SourceType = 'bizim' | 'rakip' | 'pazaryeri' | 'haber' | 'blog' | 'ansiklopedi' | 'sosyal' | 'yayinevi' | 'diger';
type Url = { url: string; title: string; redirect: boolean; count: number };
type Domain = {
  domain: string;
  type: SourceType;
  typeLabel: string;
  why: string;
  citations: number;
  answers: number;
  share: number;
  questions: number;
  mentionedAnswers: number;
  mentionShare: number;
  engines: Record<string, number>;
  firstSeen: string | null;
  lastSeen: string | null;
  target: boolean;
  action: string | null;
  urlCount: number;
  examples: Url[];
};
type DomainDetail = Domain & {
  questionList: Array<{ id: string; text: string; category: string | null; answers: number; mentioned: number; engines: string[] }>;
  trend: Array<{ date: string; answers: number; total: number | null; share: number | null }>;
};
type Summary = {
  answers: number;
  answersWithSources: number;
  citations: number;
  domains: number;
  oursCited: number;
  oursShare: number | null;
  mentioned: number;
  mentionShare: number | null;
  questions: number;
  engines: string[];
  firstAt: string | null;
  lastAt: string | null;
  byType: Record<SourceType, { domains: number; answers: number; citations: number }>;
  targets: number;
  unknown: number;
};
type Meta = {
  types: Array<{ id: SourceType; label: string }>;
  engineLabels: Record<string, string>;
  thresholds: { targetMinQuestions: number; targetMaxMentionShare: number; targetTypes: SourceType[]; examplesInList: number; blogUrlShare: number };
};
type Sources = Meta & {
  type: string;
  engine: string;
  start: number;
  total: number;
  items: Domain[];
  summary: Summary;
  trend: Array<{ date: string; answers: number; withSources: number; ours: number; mentioned: number; domains: number }>;
  our: string;
  rivals: string[];
};
type QuestionSources = Meta & {
  engine: string;
  start: number;
  total: number;
  our: string;
  items: Array<{
    id: string;
    text: string;
    category: string | null;
    engines: Record<string, { askedAt: string | null; mentioned: boolean | null; cited: boolean | null; sources: Array<{ domain: string; type: SourceType; url: string; title: string; redirect: boolean }> }>;
  }>;
};

const api = {
  list: (p: { type: string; engine: string; start: number; limit: number }) => call<Sources>(`ai-sources?${qs(p)}`),
  detail: (domain: string, engine: string) =>
    call<Meta & { engine: string; item: DomainDetail; summary: Summary }>(`ai-sources/${encodeURIComponent(domain)}?${qs({ engine })}`),
  questions: (p: { engine: string; start: number; limit: number }) => call<QuestionSources>(`ai-source-questions?${qs(p)}`),
};

const PAGE = 50;
const TONE: Record<SourceType, string> = {
  bizim: 'good',
  rakip: 'bad',
  pazaryeri: 'mid',
  haber: 'violet',
  blog: 'violet',
  ansiklopedi: '',
  sosyal: '',
  yayinevi: '',
  diger: '',
};
const pct = (v: number | null | undefined, digits = 0) => (v == null ? '—' : `%${fmt(v * 100, digits)}`);
const day = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' });
const shortEngine = (label: string | undefined, id: string) => (label ? label.replace(/\s*\(.*\)$/, '') : id);

/** Yapay zekâ motorlarının bizim konularımızdaki sorulara verdiği cevaplarda hangi sitelerin kaynak gösterildiği;
 *  Timaş'ın anılmadığı sık kaynaklar tanıtım için hedef listesidir. */
export default function SeoSources() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('sekme') === 'sorular' ? 'sorular' : 'alanlar';
  const engine = params.get('motor') ?? '';
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    setParams(next, { replace: true });
  };

  return (
    <SeoLayout
      path="/seo-geo/kaynaklar"
      crumb="Yapay zekânın kaynakları"
      eyebrow="SEO & GEO · Yapay zekâ"
      title="Yapay zekânın kaynakları"
      lead="İzlenen sorulara yapay zekâ motorlarının verdiği cevaplarda kaynak gösterilen siteler. Sık kaynak gösterilen ama o cevaplarda Timaş’ın anılmadığı siteler tanıtım ve iletişim için hedef listesidir. Ölçümlerden hesaplanır; hiçbir siteye istek gönderilmez."
    >
      <div className="sg-filters" role="toolbar" aria-label="Bölüm">
        <button className="sg-filter" aria-pressed={tab === 'alanlar'} onClick={() => set('sekme', '')}>
          Siteler
        </button>
        <button className="sg-filter" aria-pressed={tab === 'sorular'} onClick={() => set('sekme', 'sorular')}>
          Soru başına
        </button>
      </div>
      {tab === 'alanlar' ? (
        <Domains engine={engine} setEngine={(v) => set('motor', v)} selected={params.get('alan') ?? ''} select={(v) => set('alan', v)} />
      ) : (
        <Questions engine={engine} setEngine={(v) => set('motor', v)} />
      )}
    </SeoLayout>
  );
}

// ------------------------------------------------------------------ Siteler

function Domains({ engine, setEngine, selected, select }: { engine: string; setEngine: (v: string) => void; selected: string; select: (v: string) => void }) {
  const [type, setType] = useState('');
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-ai-sources', type, engine, start],
    queryFn: () => api.list({ type, engine, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const d = r.data;
  const s = d?.summary;
  const t = d?.thresholds;
  const pick = (v: string) => {
    setType(v);
    setStart(0);
  };
  const maxAnswers = s ? Math.max(1, ...Object.values(s.byType).map((b) => b.answers)) : 1;

  return (
    <>
      {r.isLoading && <Loading text="Kaynaklar toplanıyor…" />}
      {r.error && <Failed error={r.error} />}
      {d && s && (
        <>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
            {s.lastAt ? `Son ölçüm ${dateTime(s.lastAt)} · ${fmt(s.questions)} soru, ${fmt(s.answers)} cevap` : 'Henüz ölçüm yok'}
          </p>
          <EngineChips labels={d.engineLabels} seen={s.engines} engine={engine} onChange={(v) => { setEngine(v); setStart(0); }} />

          {!s.answers ? (
            <div className="sg-empty">
              <h2>Henüz ölçülmüş cevap yok</h2>
              <p>Yapay zekâ görünürlüğü ekranında sorular ölçüldükçe kaynakları burada toplanır.</p>
            </div>
          ) : (
            <>
              <section className="sg-kpis" aria-label="Özet">
                <Kpi label="Kaynak gösterilen site" value={fmt(s.domains)} note={`${fmt(s.citations)} kaynak, ${fmt(s.answersWithSources)} cevapta`} />
                <Kpi label="Sitemiz kaynak" value={pct(s.oursShare)} note={`${fmt(s.oursCited)} / ${fmt(s.answers)} cevap · ${d.our}`} />
                <Kpi label="Timaş anılıyor" value={pct(s.mentionShare)} note={`${fmt(s.mentioned)} / ${fmt(s.answers)} cevap`} />
                <Kpi label="Hedef site" value={fmt(s.targets)} note={`En az ${fmt(t!.targetMinQuestions)} soruda kaynak, Timaş cevapların en çok ${pct(t!.targetMaxMentionShare)}’inde`} />
              </section>

              <div className="sg-grid">
                <section className="sg-card sg-span-4">
                  <h2>Kaynak türleri</h2>
                  <p className="sg-sub">Türe göre, o türden en az bir kaynak gösterilen cevap sayısı.</p>
                  <div className="sg-bars">
                    {d.types
                      .filter((ty) => s.byType[ty.id]?.domains)
                      .sort((a, b) => s.byType[b.id].answers - s.byType[a.id].answers)
                      .map((ty) => (
                        <button
                          key={ty.id}
                          className="sg-bar-row"
                          style={{ border: 0, background: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', font: 'inherit' }}
                          onClick={() => pick(type === ty.id ? '' : ty.id)}
                          aria-pressed={type === ty.id}
                        >
                          <span style={{ fontWeight: type === ty.id ? 800 : 600 }}>{ty.label}</span>
                          <span className="sg-mono" style={{ color: 'var(--sg-muted)' }}>
                            {fmt(s.byType[ty.id].domains)} site · {fmt(s.byType[ty.id].answers)} cevap
                          </span>
                          <span className="sg-bar">
                            <i style={{ width: `${(s.byType[ty.id].answers / maxAnswers) * 100}%` }} />
                          </span>
                        </button>
                      ))}
                  </div>
                  {s.unknown > 0 && (
                    <p style={{ fontSize: 11.5, color: 'var(--sg-muted)', marginTop: 12 }}>
                      {fmt(s.unknown)} cevaptaki yönlendirme adresinin sitesi okunamadı; “Diğer” içinde “bilinmeyen” olarak sayılır.
                    </p>
                  )}
                </section>

                <section className="sg-card sg-span-8">
                  <h2>Ölçüm günlerine göre</h2>
                  <p className="sg-sub">Her ölçüm gününde cevap sayısı, sitemizin kaynak gösterildiği ve Timaş’ın anıldığı cevaplar.</p>
                  <div className="sg-table-wrap">
                    <table className="sg-table">
                      <thead>
                        <tr>
                          <th>Gün</th>
                          <th>Cevap</th>
                          <th>Kaynaklı</th>
                          <th>Farklı site</th>
                          <th>Sitemiz kaynak</th>
                          <th>Timaş anılıyor</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...d.trend].reverse().map((x) => (
                          <tr key={x.date}>
                            <td className="sg-mono" style={{ whiteSpace: 'nowrap' }}>{day(x.date)}</td>
                            <td className="num">{fmt(x.answers)}</td>
                            <td className="num">{fmt(x.withSources)}</td>
                            <td className="num">{fmt(x.domains)}</td>
                            <td className="num">{fmt(x.ours)} <small style={{ color: 'var(--sg-muted)' }}>{pct(x.answers ? x.ours / x.answers : null)}</small></td>
                            <td className="num">{fmt(x.mentioned)} <small style={{ color: 'var(--sg-muted)' }}>{pct(x.answers ? x.mentioned / x.answers : null)}</small></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              </div>

              <div className="sg-filters" role="toolbar" aria-label="Kaynak türü">
                <Chip on={!type} onClick={() => pick('')} label="Hepsi" n={s.domains} />
                <Chip on={type === 'hedef'} onClick={() => pick('hedef')} label="Hedef listesi" n={s.targets} />
                {d.types
                  .filter((ty) => s.byType[ty.id]?.domains)
                  .map((ty) => (
                    <Chip key={ty.id} on={type === ty.id} onClick={() => pick(ty.id)} label={ty.label} n={s.byType[ty.id].domains} />
                  ))}
              </div>

              {selected && <DomainPanel domain={selected} engine={engine} labels={d.engineLabels} onClose={() => select('')} />}

              <section className="sg-card">
                <h2>{type === 'hedef' ? 'Hedef listesi' : 'Kaynak gösterilen siteler'}</h2>
                <p className="sg-sub">
                  {type === 'hedef'
                    ? `Bizim konularımızda en az ${fmt(t!.targetMinQuestions)} farklı soruda kaynak gösterilen, ama onu kaynak gösteren cevapların en çok ${pct(t!.targetMaxMentionShare)}’inde Timaş anılan siteler. Sitemiz, rakipler ve pazar yerleri hedef sayılmaz. Bu sitelerde görünmek, yapay zekâ cevaplarında anılmanın en kısa yoludur.`
                    : 'Kaynak gösterildiği cevap sayısına göre sıralı. Tür, açık kurallarla bulunur; gerekçesi sitenin ayrıntısında yazar. Rakip listesi Yönetim → SEO & GEO ayarından gelir.'}
                </p>
                {!d.items.length ? (
                  <div className="sg-empty">
                    <h2>{type === 'hedef' ? 'Hedef site yok' : 'Bu süzgeçte site yok'}</h2>
                    <p>{type === 'hedef' ? 'Sık kaynak gösterilen sitelerin cevaplarında Timaş zaten anılıyor ya da ölçüm henüz az.' : 'Başka bir tür seçin.'}</p>
                  </div>
                ) : (
                  <div className="sg-table-wrap">
                    <table className="sg-table">
                      <thead>
                        <tr>
                          <th>Site</th>
                          <th>Cevap</th>
                          <th>Cevap payı</th>
                          <th>Soru</th>
                          <th>Motor</th>
                          <th>Timaş anılıyor</th>
                          <th>Örnek</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.items.map((x) => (
                          <tr key={x.domain} aria-selected={selected === x.domain}>
                            <td style={{ minWidth: 170 }}>
                              <button
                                onClick={() => select(selected === x.domain ? '' : x.domain)}
                                style={{ border: 0, background: 'none', padding: 0, font: 'inherit', fontWeight: 750, color: 'var(--sg-ink)', cursor: 'pointer', textAlign: 'left', textDecoration: 'underline', textUnderlineOffset: 3 }}
                              >
                                {x.domain}
                              </button>
                              <div style={{ marginTop: 4, display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                                <span className={`sg-chip ${TONE[x.type]}`}>{x.typeLabel}</span>
                                {x.target && <span className="sg-chip bad">Hedef</span>}
                              </div>
                            </td>
                            <td className="num">
                              {fmt(x.answers)}
                              <div style={{ fontSize: 11, color: 'var(--sg-muted)' }}>{fmt(x.citations)} kaynak</div>
                            </td>
                            <td className="num">{pct(x.share, 1)}</td>
                            <td className="num">{fmt(x.questions)}</td>
                            <td style={{ fontSize: 12, minWidth: 110 }}>
                              {Object.entries(x.engines).map(([e, n]) => (
                                <div key={e}>
                                  {shortEngine(d.engineLabels[e], e)} <span className="sg-mono">{fmt(n)}</span>
                                </div>
                              ))}
                            </td>
                            <td className="num">
                              <span style={{ color: x.mentionShare > t!.targetMaxMentionShare ? '#0f7a51' : '#c2361b', fontWeight: 700 }}>{pct(x.mentionShare)}</span>
                              <div style={{ fontSize: 11, color: 'var(--sg-muted)' }}>
                                {fmt(x.mentionedAnswers)} / {fmt(x.answers)}
                              </div>
                            </td>
                            <td style={{ minWidth: 220, fontSize: 12 }}>
                              <UrlList urls={x.examples} />
                              {x.urlCount > x.examples.length && (
                                <button
                                  onClick={() => select(x.domain)}
                                  style={{ border: 0, background: 'none', padding: 0, font: 'inherit', color: 'var(--sg-violet)', cursor: 'pointer', fontWeight: 700 }}
                                >
                                  Bütün {fmt(x.urlCount)} adres
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <Pager start={start} total={d.total} onChange={setStart} />
              </section>
            </>
          )}
        </>
      )}
    </>
  );
}

function DomainPanel({ domain, engine, labels, onClose }: { domain: string; engine: string; labels: Record<string, string>; onClose: () => void }) {
  const r = useQuery({
    queryKey: ['seo-ai-source', domain, engine],
    queryFn: () => api.detail(domain, engine),
    enabled: ENGINE_ENABLED,
    retry: false,
  });
  const x = r.data?.item;
  return (
    <section className="sg-card" aria-label={`${domain} ayrıntısı`}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <div style={{ minWidth: 0 }}>
          <h2 style={{ wordBreak: 'break-all' }}>{domain}</h2>
          {x && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', fontSize: 12, color: 'var(--sg-muted)' }}>
              <span className={`sg-chip ${TONE[x.type]}`}>{x.typeLabel}</span>
              {x.target && <span className="sg-chip bad">Hedef</span>}
              <span>{x.why}</span>
            </div>
          )}
        </div>
        <button className="sg-button" onClick={onClose} aria-label="Ayrıntıyı kapat">
          <X size={16} aria-hidden />
        </button>
      </div>
      {r.isLoading && <Loading text="Site ayrıntısı getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {x && (
        <>
          {x.action && <p className="sg-banner" style={{ marginTop: 12 }}>Öneri: {x.action}</p>}
          <section className="sg-kpis" style={{ marginTop: 12 }}>
            <Kpi label="Cevap" value={fmt(x.answers)} note={`${fmt(x.citations)} kaynak · cevapların ${pct(x.share, 1)}’i`} />
            <Kpi label="Soru" value={fmt(x.questions)} note={`İlk ${dateTime(x.firstSeen)} · son ${dateTime(x.lastSeen)}`} />
            <Kpi label="Timaş anılıyor" value={pct(x.mentionShare)} note={`${fmt(x.mentionedAnswers)} / ${fmt(x.answers)} cevap`} />
          </section>
          <div className="sg-grid" style={{ marginTop: 12 }}>
            <div className="sg-span-7">
              <h3 style={{ fontSize: 13, margin: '0 0 8px' }}>Kaynak gösterildiği sorular</h3>
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Soru</th>
                      <th>Cevap</th>
                      <th>Timaş anıldı</th>
                      <th>Motor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {x.questionList.map((q) => (
                      <tr key={q.id}>
                        <td style={{ minWidth: 200 }}>{q.text}</td>
                        <td className="num">{fmt(q.answers)}</td>
                        <td className="num">
                          <span className={`sg-chip ${q.mentioned ? 'good' : 'bad'}`}>{q.mentioned ? `${fmt(q.mentioned)} cevapta` : 'Hayır'}</span>
                        </td>
                        <td style={{ fontSize: 12 }}>{q.engines.map((e) => shortEngine(labels[e], e)).join(', ')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div className="sg-span-5">
              <h3 style={{ fontSize: 13, margin: '0 0 8px' }}>Ölçüm günlerine göre</h3>
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Gün</th>
                      <th>Kaynak olduğu cevap</th>
                      <th>Pay</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...x.trend].reverse().map((p) => (
                      <tr key={p.date}>
                        <td className="sg-mono" style={{ whiteSpace: 'nowrap' }}>{day(p.date)}</td>
                        <td className="num">
                          {fmt(p.answers)}
                          {p.total != null && <span style={{ color: 'var(--sg-muted)' }}> / {fmt(p.total)}</span>}
                        </td>
                        <td className="num">{pct(p.share)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
          <details className="sg-more" style={{ marginTop: 12 }}>
            <summary>Kaynak gösterilen bütün adresler ({fmt(x.urlCount)})</summary>
            <div style={{ marginTop: 8, fontSize: 12 }}>
              <UrlList urls={x.examples} />
            </div>
          </details>
        </>
      )}
    </section>
  );
}

function UrlList({ urls }: { urls: Url[] }) {
  return (
    <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
      {urls.map((u) => (
        <li key={`${u.url}|${u.title}`} style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
          {u.redirect ? (
            <span title="Motor, kaynağı yönlendirme adresiyle verdi; sayfanın kendi adresi bilinmiyor.">{u.title || u.url}</span>
          ) : (
            <a href={u.url} target="_blank" rel="noreferrer">
              {u.title || u.url} <ExternalLink size={11} aria-hidden />
            </a>
          )}
          {u.count > 1 && <span className="sg-mono" style={{ color: 'var(--sg-muted)' }}> ×{fmt(u.count)}</span>}
        </li>
      ))}
    </ul>
  );
}

// ------------------------------------------------------------------ Soru başına

function Questions({ engine, setEngine }: { engine: string; setEngine: (v: string) => void }) {
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-ai-source-questions', engine, start],
    queryFn: () => api.questions({ engine, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const d = r.data;
  const typeLabel = (id: SourceType) => d?.types.find((t) => t.id === id)?.label ?? id;
  return (
    <>
      {r.isLoading && <Loading text="Sorular getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {d && (
        <>
          <EngineChips labels={d.engineLabels} seen={Object.keys(d.engineLabels)} engine={engine} onChange={(v) => { setEngine(v); setStart(0); }} />
          {!d.items.length ? (
            <div className="sg-empty">
              <h2>Henüz ölçülmüş soru yok</h2>
              <p>Yapay zekâ görünürlüğü ekranında sorular ölçüldükçe her cevabın kaynakları burada görünür.</p>
            </div>
          ) : (
            <section className="sg-card">
              <h2>Her motorun son cevabındaki kaynaklar</h2>
              <p className="sg-sub">Sorunun her motordaki son başarılı ölçümü. Yeşil: sitemiz; kırmızı: rakip kitapçı.</p>
              <div className="sg-list">
                {d.items.map((q) => (
                  <article key={q.id} style={{ border: '1px solid var(--sg-line)', borderRadius: 16, padding: 14, minWidth: 0 }}>
                    <h3 style={{ margin: '0 0 8px', fontSize: 14, color: 'var(--sg-ink)' }}>{q.text}</h3>
                    <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))' }}>
                      {Object.entries(q.engines).map(([e, res]) => (
                        <div key={e} style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 12, fontWeight: 750, display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                            {shortEngine(d.engineLabels[e], e)}
                            <span className={`sg-chip ${res.mentioned ? 'good' : ''}`}>{res.mentioned ? 'Timaş anıldı' : 'Timaş anılmadı'}</span>
                            <span style={{ fontWeight: 500, color: 'var(--sg-muted)' }}>{dateTime(res.askedAt)}</span>
                          </div>
                          {!res.sources.length ? (
                            <p style={{ fontSize: 12, color: 'var(--sg-muted)', margin: '6px 0 0' }}>Kaynak göstermedi.</p>
                          ) : (
                            <ul style={{ margin: '6px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12 }}>
                              {res.sources.map((src, i) => (
                                <li key={i} style={{ overflowWrap: 'anywhere' }}>
                                  <span className={`sg-chip ${TONE[src.type]}`} title={typeLabel(src.type)}>
                                    {src.domain}
                                  </span>{' '}
                                  {src.redirect ? (
                                    <span style={{ color: 'var(--sg-muted)' }}>{src.title}</span>
                                  ) : (
                                    <a href={src.url} target="_blank" rel="noreferrer">
                                      {src.title || src.url}
                                    </a>
                                  )}
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
              <Pager start={start} total={d.total} onChange={setStart} />
            </section>
          )}
        </>
      )}
    </>
  );
}

// ------------------------------------------------------------------ ortak

function EngineChips({ labels, seen, engine, onChange }: { labels: Record<string, string>; seen: string[]; engine: string; onChange: (v: string) => void }) {
  const ids = Object.keys(labels).filter((e) => seen.includes(e) || e === engine);
  if (ids.length < 2 && !engine) return null;
  return (
    <div className="sg-filters" role="toolbar" aria-label="Motor">
      <Chip on={!engine} onClick={() => onChange('')} label="Bütün motorlar" />
      {ids.map((e) => (
        <Chip key={e} on={engine === e} onClick={() => onChange(e)} label={shortEngine(labels[e], e)} />
      ))}
    </div>
  );
}

function Pager({ start, total, onChange }: { start: number; total: number; onChange: (n: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <div className="sg-pager" style={{ marginTop: 12 }}>
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

function Kpi({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono">{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}

function Chip({ on, onClick, label, n }: { on: boolean; onClick: () => void; label: string; n?: number }) {
  return (
    <button className="sg-filter" aria-pressed={on} onClick={onClick}>
      {label} {n !== undefined && <span className="sg-mono">{fmt(n)}</span>}
    </button>
  );
}
