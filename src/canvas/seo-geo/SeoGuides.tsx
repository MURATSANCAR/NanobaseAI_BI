import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Check, ChevronLeft, ChevronRight, Download, ExternalLink, Loader2, Plus, Sparkles, Trash2, X } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { STATUS_LABEL, call, dateTime, fmt, qs, seoApi, type ProductDetail } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/* ------------------------------------------------------------------ uçlar: /api/v1/seo-geo/guides/* */
type GuideStatus = 'hazir' | 'onaylandi' | 'reddedildi';
type GuideTopic = {
  key: string;
  title: string;
  terms: string[];
  ages: [number, number] | null;
  impressions: number;
  clicks: number;
  position: number | null;
  sources: Array<'arama' | 'soru'>;
  queries: Array<{ text: string; impressions: number; clicks: number; position: number | null; source: 'arama' | 'soru' }>;
  draft?: { id: string; status: GuideStatus } | null;
};
type GuideRun = { running: boolean; done: number; failed: number; skipped: number; startedAt: string | null; finishedAt: string | null; error: string | null };
type Candidate = {
  id: string;
  name: string;
  author: string | null;
  brand: string | null;
  url: string | null;
  image: string | null;
  sales: number;
  score: number;
  why: string[];
  genres: string | null;
  audience: string | null;
  category: string | null;
  ages: string | null;
};
type Faq = { q: string; a: string };
type GuideFields = { SeoTitle: string; SeoDescription: string; Intro: string; Books: Record<string, string>; Faq: Faq[] };
type GuideBook = Pick<Candidate, 'id' | 'name' | 'author' | 'brand' | 'url' | 'image' | 'category' | 'genres' | 'audience' | 'ages'> & { isbn: string | null; why?: string[] };
type GuideBase = {
  id: string;
  topicKey: string;
  title: string | null;
  status: GuideStatus;
  topic: GuideTopic;
  model: string | null;
  createdBy: string | null;
  createdAt: string;
  decidedBy: string | null;
  decidedAt: string | null;
  note: string | null;
};
type GuideRow = GuideBase & { books: number };
type Guide = GuideBase & {
  fields: GuideFields;
  books: GuideBook[];
  jsonld: unknown[];
  /** Kaynakta geçmeyen sayı/özel adlar: genel metin ve kitap başına. */
  unsupported: { general: string[]; books: Record<string, string[]> };
  limits: ProductDetail['limits'];
};

const PAGE = 30;
const BOOK_PAGE = 50;
const guidesApi = {
  topics: (start: number) =>
    call<{ total: number; start: number; search: { start: string | null; end: string | null; savedAt: string | null }; items: GuideTopic[]; run: GuideRun }>(
      `guides/topics?${qs({ start, limit: PAGE })}`,
    ),
  books: (key: string, start: number) =>
    call<{ topic: GuideTopic; total: number; start: number; preselect: number; items: Candidate[] }>(
      `guides/topics/${encodeURIComponent(key)}/books?${qs({ start, limit: BOOK_PAGE })}`,
    ),
  // Taslak model kuyruğunda bekleyebilir ve on kitaplık bir liste uzun sürer.
  create: (topicKey: string, bookIds: string[]) => call<Guide>('guides', { method: 'POST', body: { topicKey, bookIds }, timeout: 600_000 }),
  list: (status: string, start: number) =>
    call<{ total: number; start: number; counts: Partial<Record<GuideStatus, number>>; items: GuideRow[] }>(`guides?${qs({ status, start, limit: PAGE })}`),
  get: (id: string) => call<Guide>(`guides/${encodeURIComponent(id)}`),
  decide: (id: string, body: { action: 'approve' | 'reject'; fields?: GuideFields; bookIds?: string[]; note?: string }) =>
    call<Guide>(`guides/${encodeURIComponent(id)}/decide`, { method: 'POST', body, timeout: 120_000 }),
  exportUrl: (id: string) => `${ENGINE_BASE}/api/v1/seo-geo/guides/${encodeURIComponent(id)}/export.html`,
};

const words = (s: string) => s.split(/\s+/).filter(Boolean).length;
const muted = { fontSize: 12, color: 'var(--sg-muted)' } as const;

/** Rehber içerikler: okurun "hangi kitap?" sorusuna cevap veren liste sayfası taslakları. Konu aramalardan ve izlenen
 *  sorulardan çıkar, kitaplar yalnız kendi kataloğumuzdan seçilir; ZEKİ AI yazar, insan onaylar, hiçbir yere gönderilmez. */
export default function SeoGuides() {
  const [params, setParams] = useSearchParams();
  const tab = params.get('liste') === 'taslaklar' ? 'taslaklar' : 'konular';
  const topicKey = params.get('konu') ?? '';
  const draftId = params.get('taslak') ?? '';
  const status = params.get('durum') ?? '';
  const [start, setStart] = useState(0);
  useEffect(() => setStart(0), [tab, status]);

  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };

  const topics = useQuery({
    queryKey: ['seo-guide-topics', start],
    queryFn: () => guidesApi.topics(start),
    enabled: ENGINE_ENABLED && tab === 'konular',
    retry: false,
    placeholderData: (p) => p,
  });
  const drafts = useQuery({
    queryKey: ['seo-guides', status, start],
    queryFn: () => guidesApi.list(status, start),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const total = tab === 'konular' ? topics.data?.total ?? 0 : drafts.data?.total ?? 0;
  const counts = drafts.data?.counts ?? {};
  const listed = topics.data?.items.find((t) => t.key === topicKey);
  const run = topics.data?.run;

  return (
    <SeoLayout
      path="/seo-geo/rehberler"
      crumb="Rehber içerikler"
      eyebrow="SEO & GEO · rehber içerikler"
      title="Rehber içerikler"
      lead="Yapay zekâ cevap motorları ve Google, okurun “hangi kitap?” sorusuna cevap veren liste ve rehber sayfalarını kaynak gösterir; tek kitabın ürün sayfası bu soruyu cevaplamaz. Konular Search Console aramalarından ve izlenen sorulardan çıkar, kitaplar yalnız kendi kataloğumuzdan ve CRM kartlarından seçilir. ZEKİ AI taslağı yazar, kaynakta olmayan bilgi işaretlenir. Onay yalnız kaydedilir; siteye hiçbir şey gönderilmez."
    >
      <div className="sg-filters" role="tablist" aria-label="Liste">
        <button className="sg-filter" role="tab" aria-selected={tab === 'konular'} aria-pressed={tab === 'konular'} onClick={() => set({ liste: '', taslak: '' })}>
          Konular {topics.data && <span className="sg-mono">{fmt(topics.data.total)}</span>}
        </button>
        <button className="sg-filter" role="tab" aria-selected={tab === 'taslaklar'} aria-pressed={tab === 'taslaklar'} onClick={() => set({ liste: 'taslaklar', konu: '' })}>
          Taslaklar <span className="sg-mono">{fmt((counts.hazir ?? 0) + (counts.onaylandi ?? 0) + (counts.reddedildi ?? 0))}</span>
        </button>
        {tab === 'taslaklar' &&
          (['hazir', 'onaylandi', 'reddedildi'] as GuideStatus[]).map((s) => (
            <button key={s} className="sg-filter" aria-pressed={status === s} onClick={() => set({ durum: status === s ? '' : s })}>
              {STATUS_LABEL[s]} <span className="sg-mono">{fmt(counts[s] ?? 0)}</span>
            </button>
          ))}
      </div>

      <div className="sg-audit">
        <section className="sg-card" aria-label={tab === 'konular' ? 'Konular' : 'Taslaklar'}>
          {tab === 'konular' ? (
            <>
              {topics.isLoading && <Loading text="Konular çıkarılıyor…" />}
              {topics.error && <Failed error={topics.error} />}
              {topics.data && (
                <p style={{ ...muted, margin: '0 0 10px' }}>
                  {fmt(topics.data.total)} konu · Search Console {topics.data.search.start ? `${topics.data.search.start} – ${topics.data.search.end}` : 'verisi yok'} · çok gösterilenden aza
                  {run?.finishedAt && ` · gece hazırlığı ${dateTime(run.finishedAt)}: ${fmt(run.done)} taslak`}
                  {run?.running && ' · gece hazırlığı sürüyor'}
                </p>
              )}
              {topics.data && !topics.data.items.length && (
                <div className="sg-empty">
                  <h2>Konu yok</h2>
                  <p>
                    {topics.data.search.savedAt
                      ? 'Aramalarda liste ya da öneri arayan sorgu bulunamadı.'
                      : 'Search Console verisi henüz okunmadı; konular okunan aramalardan çıkar.'}{' '}
                    Konuyu elle açmak için <Link to="/seo-geo/ai-gorunurluk">izlenen sorulara</Link> soru ekleyin.
                  </p>
                </div>
              )}
              <div className="sg-list">
                {topics.data?.items.map((t) => (
                  <button key={t.key} className="sg-item" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }} aria-current={topicKey === t.key}
                    onClick={() => set({ konu: t.key, taslak: '' })}>
                    <span style={{ minWidth: 0 }}>
                      <span className="sg-item-name">{t.title}</span>
                      <span className="sg-item-meta sg-mono">
                        {fmt(t.impressions)} gösterim · {fmt(t.queries.length)} sorgu{t.position != null ? ` · sıra ${fmt(t.position, 1)}` : ''}
                      </span>
                    </span>
                    <span className="sg-item-side">
                      {t.draft ? <span className={`sg-chip ${t.draft.status === 'onaylandi' ? 'good' : 'violet'}`}>{STATUS_LABEL[t.draft.status]}</span> : <span className="sg-chip">Taslak yok</span>}
                      {t.sources.includes('soru') && <span className="sg-chip mid">İzlenen soru</span>}
                    </span>
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              {drafts.isLoading && <Loading text="Taslaklar getiriliyor…" />}
              {drafts.error && <Failed error={drafts.error} />}
              {drafts.data && !drafts.data.items.length && (
                <div className="sg-empty">
                  <h2>Taslak yok</h2>
                  <p>Konular listesinden bir konu seçip taslak ürettiğinizde burada görünür.</p>
                </div>
              )}
              <div className="sg-list">
                {drafts.data?.items.map((g) => (
                  <button key={g.id} className="sg-item" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }} aria-current={draftId === g.id}
                    onClick={() => set({ taslak: g.id })}>
                    <span style={{ minWidth: 0 }}>
                      <span className="sg-item-name">{g.title || g.topic.title}</span>
                      <span className="sg-item-meta sg-mono">
                        {g.topic.title} · {fmt(g.books)} kitap · {dateTime(g.createdAt)}
                      </span>
                    </span>
                    <span className="sg-item-side">
                      <span className={`sg-chip ${g.status === 'onaylandi' ? 'good' : g.status === 'reddedildi' ? 'bad' : 'violet'}`}>{STATUS_LABEL[g.status]}</span>
                    </span>
                  </button>
                ))}
              </div>
            </>
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

        <section aria-label="Seçilen konu">
          {tab === 'taslaklar' && draftId ? (
            <DraftPanel id={draftId} />
          ) : tab === 'konular' && topicKey ? (
            <TopicPanel topicKey={topicKey} draft={listed?.draft ?? null} />
          ) : (
            <div className="sg-empty">
              <h2>{tab === 'konular' ? 'Bir konu seçin' : 'Bir taslak seçin'}</h2>
              <p>
                {tab === 'konular'
                  ? 'Soldan bir konu seçtiğinizde bu soruya uyan kitaplarımız ve neden seçildikleri açılır; seçtiğiniz kitaplarla ZEKİ AI taslak yazar.'
                  : 'Soldan bir taslak seçtiğinizde metni düzenleyip onaylayabilir ya da dışa aktarabilirsiniz.'}
              </p>
            </div>
          )}
        </section>
      </div>
    </SeoLayout>
  );
}

/* ------------------------------------------------------------------ konu: aday kitaplar + taslak */
function TopicPanel({ topicKey, draft }: { topicKey: string; draft: GuideTopic['draft'] }) {
  const qc = useQueryClient();
  const [start, setStart] = useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [seeded, setSeeded] = useState<string | null>(null);
  const [created, setCreated] = useState<string | null>(null);
  useEffect(() => {
    setStart(0);
    setCreated(null);
    setSelected([]);
  }, [topicKey]);

  const books = useQuery({
    queryKey: ['seo-guide-books', topicKey, start],
    queryFn: () => guidesApi.books(topicKey, start),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  // İlk açılışta en uygun kitaplar seçili gelir (sayı Yönetim ayarından); editör ekler/çıkarır.
  useEffect(() => {
    if (books.data && start === 0 && seeded !== topicKey && books.data.topic.key === topicKey) {
      setSeeded(topicKey);
      setSelected(books.data.items.slice(0, books.data.preselect).map((b) => b.id));
    }
  }, [books.data, start, seeded, topicKey]);

  const create = useMutation({
    mutationFn: () => guidesApi.create(topicKey, selected),
    onSuccess: (g) => {
      setCreated(g.id);
      qc.setQueryData(['seo-guide', g.id], g);
      qc.invalidateQueries({ queryKey: ['seo-guide-topics'] });
      qc.invalidateQueries({ queryKey: ['seo-guides'] });
    },
  });
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const t = books.data?.topic;
  const activeDraft = created ?? draft?.id ?? null;
  const tot = books.data?.total ?? 0;

  if (books.isLoading) return <Loading text="Uygun kitaplar aranıyor…" />;
  if (books.error) return <Failed error={books.error} />;
  if (!t) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="sg-card">
        <div className="sg-eyebrow">Konu · {t.sources.map((s) => (s === 'soru' ? 'izlenen soru' : 'arama')).join(' + ')}</div>
        <h2 style={{ fontSize: 20, margin: '6px 0' }}>{t.title}</h2>
        <div className="sg-mono" style={muted}>
          {fmt(t.impressions)} gösterim · {fmt(t.clicks)} tıklama{t.position != null ? ` · en iyi sıra ${fmt(t.position, 1)}` : ''}
          {t.ages ? ` · yaş ${t.ages[0]}–${t.ages[1]}` : ''}
        </div>
        <details className="sg-more" style={{ marginTop: 10 }}>
          <summary>Bu konudaki sorgular ({fmt(t.queries.length)})</summary>
          <div className="sg-table-wrap" style={{ marginTop: 8 }}>
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Sorgu</th>
                  <th>Gösterim</th>
                  <th>Tıklama</th>
                  <th>Sıra</th>
                </tr>
              </thead>
              <tbody>
                {t.queries.map((q) => (
                  <tr key={q.text}>
                    <td>{q.text}{q.source === 'soru' && <span className="sg-chip mid" style={{ marginLeft: 6 }}>soru</span>}</td>
                    <td className="num">{fmt(q.impressions)}</td>
                    <td className="num">{fmt(q.clicks)}</td>
                    <td className="num">{q.position != null ? fmt(q.position, 1) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </div>

      <div className="sg-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
          <div>
            <h2>Uygun kitaplar</h2>
            <p className="sg-sub" style={{ margin: 0 }}>
              {fmt(tot)} kitap eşleşti · {fmt(selected.length)} seçili. Tür, web kategorisi, anahtar kelime, hedef kitle ve yaşa göre; eşitlikte çok satan önde. CRM’de satıştan çekilmiş ya da bizim olmayan kitap alınmaz.
            </p>
          </div>
          <button className="sg-button primary" disabled={!selected.length || create.isPending} onClick={() => create.mutate()}>
            {create.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Sparkles size={16} aria-hidden />}
            {activeDraft ? 'Seçimle yeniden üret' : 'Taslak üret'}
          </button>
        </div>
        {create.isPending && <p className="sg-banner" style={{ marginTop: 12 }}>ZEKİ AI taslağı yazıyor; kitap sayısına göre birkaç dakika sürebilir.</p>}
        {create.error && <div style={{ marginTop: 12 }}><Failed error={create.error} /></div>}
        {!tot && <p className="sg-banner" style={{ marginTop: 12 }}>Bu konuya uyan kitap verimizde bulunamadı; CRM kartlarında tür ya da anahtar kelime eksik olabilir.</p>}
        <div className="sg-list" style={{ marginTop: 12 }}>
          {books.data?.items.map((b) => (
            <label key={b.id} className="sg-item" style={{ gridTemplateColumns: '24px 44px minmax(0,1fr)', cursor: 'pointer' }}>
              <input type="checkbox" checked={selected.includes(b.id)} onChange={() => toggle(b.id)} aria-label={`${b.name} rehbere alınsın`} style={{ width: 18, height: 18 }} />
              {b.image ? <img src={b.image} alt="" loading="lazy" /> : <span className="sg-noimg" aria-hidden />}
              <span style={{ minWidth: 0 }}>
                <span className="sg-item-name">{b.name}</span>
                <span className="sg-item-meta">
                  {[b.author, b.brand, b.ages].filter(Boolean).join(' · ')} · <span className="sg-mono">{fmt(b.sales)} satış</span>
                </span>
                <span style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
                  {b.why.map((w) => (
                    <span key={w} className="sg-chip" style={{ whiteSpace: 'normal' }}>{w}</span>
                  ))}
                </span>
              </span>
            </label>
          ))}
        </div>
        {tot > BOOK_PAGE && (
          <div className="sg-pager" style={{ marginTop: 12 }}>
            <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - BOOK_PAGE))} aria-label="Önceki kitaplar">
              <ChevronLeft size={16} aria-hidden />
            </button>
            <span className="sg-mono">
              {fmt(start + 1)}–{fmt(Math.min(tot, start + BOOK_PAGE))} / {fmt(tot)}
            </span>
            <button className="sg-button" disabled={start + BOOK_PAGE >= tot} onClick={() => setStart(start + BOOK_PAGE)} aria-label="Sonraki kitaplar">
              <ChevronRight size={16} aria-hidden />
            </button>
          </div>
        )}
      </div>

      {activeDraft && <DraftPanel id={activeDraft} />}
    </div>
  );
}

/* ------------------------------------------------------------------ taslak: düzenleme, gerçeklik, karar */
function DraftPanel({ id }: { id: string }) {
  const d = useQuery({ queryKey: ['seo-guide', id], queryFn: () => guidesApi.get(id), enabled: ENGINE_ENABLED, retry: false });
  if (d.isLoading) return <Loading text="Taslak açılıyor…" />;
  if (d.error) return <Failed error={d.error} />;
  if (!d.data) return null;
  return <Editor key={`${d.data.id}:${d.data.status}`} guide={d.data} />;
}

function Editor({ guide }: { guide: Guide }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const canApprove = !!me.data?.canApprove;
  const open = guide.status === 'hazir';
  const [fields, setFields] = useState<GuideFields>(() => ({
    SeoTitle: guide.fields.SeoTitle ?? '',
    SeoDescription: guide.fields.SeoDescription ?? '',
    Intro: guide.fields.Intro ?? '',
    Books: { ...(guide.fields.Books ?? {}) },
    Faq: (guide.fields.Faq ?? []).map((f) => ({ ...f })),
  }));
  const [order, setOrder] = useState<string[]>(() => guide.books.map((b) => b.id));
  const [note, setNote] = useState('');
  const byId = useMemo(() => Object.fromEntries(guide.books.map((b) => [b.id, b])), [guide.books]);
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') =>
      guidesApi.decide(guide.id, action === 'approve' ? { action, fields, bookIds: order, note } : { action, note }),
    onSuccess: (g) => {
      qc.setQueryData(['seo-guide', g.id], g);
      qc.invalidateQueries({ queryKey: ['seo-guide-topics'] });
      qc.invalidateQueries({ queryKey: ['seo-guides'] });
    },
  });

  const L = guide.limits;
  const titleOver = fields.SeoTitle.length < L.title_min || fields.SeoTitle.length > L.title_max;
  const metaOver = fields.SeoDescription.length < L.meta_min || fields.SeoDescription.length > L.meta_max;
  const introWords = words(fields.Intro);
  const move = (i: number, d: -1 | 1) =>
    setOrder((o) => {
      const n = [...o];
      [n[i], n[i + d]] = [n[i + d], n[i]];
      return n;
    });
  const setFaq = (i: number, patch: Partial<Faq>) => setFields((f) => ({ ...f, Faq: f.Faq.map((x, j) => (j === i ? { ...x, ...patch } : x)) }));
  const general = guide.unsupported.general ?? [];
  const perBook = guide.unsupported.books ?? {};
  const emptyBooks = order.filter((b) => !(fields.Books[b] ?? '').trim());

  return (
    <div className="sg-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <div>
          <h2>ZEKİ AI taslağı</h2>
          <p className="sg-sub" style={{ margin: 0 }}>
            {guide.topic.title} · {dateTime(guide.createdAt)} · {guide.createdBy ?? '—'}
            {open ? ' · onaylamadan önce düzenleyebilirsiniz' : ''}
          </p>
        </div>
        <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className={`sg-chip ${guide.status === 'onaylandi' ? 'good' : guide.status === 'reddedildi' ? 'bad' : 'violet'}`}>{STATUS_LABEL[guide.status]}</span>
          <a className="sg-button" href={guidesApi.exportUrl(guide.id)} download>
            <Download size={16} aria-hidden /> HTML olarak indir
          </a>
        </span>
      </div>

      {!open && (
        <p className={`sg-banner ${guide.status === 'onaylandi' ? 'ok' : ''}`} style={{ marginTop: 12 }}>
          <b>{STATUS_LABEL[guide.status]}</b> · {guide.decidedBy ?? '—'} · {dateTime(guide.decidedAt)}
          {guide.note ? ` — ${guide.note}` : ''}
          {guide.status === 'onaylandi' && ' — Siteye gönderim yok; sayfa, indirilen HTML ile site yönetiminden (CRM/T-soft paneli) elle açılacak.'}
        </p>
      )}
      {general.length > 0 && (
        <p className="sg-banner" style={{ marginTop: 12 }}>
          Gerçeklik denetimi: başlık, giriş ya da soru–cevapta kitap bilgilerinde geçmeyen ifadeler var — <b>{general.join(', ')}</b>. Onaylamadan önce bakın.
        </p>
      )}

      <div className="sg-diff" style={{ marginTop: 16 }}>
        <section className="sg-field" aria-label="SEO başlığı">
          <div className="sg-field-head">
            <span>SEO başlığı</span>
            <span className={`sg-mono ${titleOver ? 'over' : ''}`}>{fields.SeoTitle.length} / {L.title_min}–{L.title_max} karakter</span>
          </div>
          <textarea className="sg-after" rows={2} value={fields.SeoTitle} readOnly={!open} onChange={(e) => setFields({ ...fields, SeoTitle: e.target.value })} aria-label="SEO başlığı" />
        </section>
        <section className="sg-field" aria-label="Meta açıklama">
          <div className="sg-field-head">
            <span>Meta açıklama</span>
            <span className={`sg-mono ${metaOver ? 'over' : ''}`}>{fields.SeoDescription.length} / {L.meta_min}–{L.meta_max} karakter</span>
          </div>
          <textarea className="sg-after" rows={3} value={fields.SeoDescription} readOnly={!open} onChange={(e) => setFields({ ...fields, SeoDescription: e.target.value })} aria-label="Meta açıklama" />
        </section>
        <section className="sg-field" aria-label="Giriş">
          <div className="sg-field-head">
            <span>Giriş</span>
            <span className={`sg-mono ${introWords < 120 || introWords > 200 ? 'over' : ''}`}>{introWords} kelime · 120–200</span>
          </div>
          <textarea className="sg-after" rows={7} value={fields.Intro} readOnly={!open} onChange={(e) => setFields({ ...fields, Intro: e.target.value })} aria-label="Giriş metni" />
        </section>

        <section className="sg-field" aria-label="Kitaplar">
          <div className="sg-field-head">
            <span>Kitaplar ({fmt(order.length)})</span>
            <span className="sg-mono">her biri yalnız kendi bilgisinden · 40–90 kelime</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {order.map((bid, i) => {
              const b = byId[bid];
              const text = fields.Books[bid] ?? '';
              const n = words(text);
              const miss = perBook[bid] ?? [];
              return (
                <article key={bid} style={{ display: 'grid', gridTemplateColumns: '44px minmax(0,1fr)', gap: 12, paddingTop: i ? 12 : 0, borderTop: i ? '1px solid var(--sg-line)' : 0 }}>
                  {b?.image ? <img src={b.image} alt="" loading="lazy" style={{ width: 44, height: 60, objectFit: 'cover', borderRadius: 8 }} /> : <span className="sg-noimg" aria-hidden style={{ width: 44, height: 60, borderRadius: 8, background: 'var(--sg-soft)' }} />}
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span style={{ minWidth: 0 }}>
                        <b style={{ fontSize: 13, color: 'var(--sg-ink)' }}>{i + 1}. {b?.name ?? bid}</b>
                        <span style={{ ...muted, display: 'block' }}>
                          {[b?.author, b?.brand, b?.ages].filter(Boolean).join(' · ')}
                          {b?.url && (
                            <>
                              {' · '}
                              <a href={b.url} target="_blank" rel="noreferrer">sayfa <ExternalLink size={11} aria-hidden /></a>
                            </>
                          )}
                        </span>
                      </span>
                      {open && (
                        <span style={{ display: 'flex', gap: 4 }}>
                          <button className="sg-button" style={{ minHeight: 36, padding: '6px 10px' }} disabled={i === 0} onClick={() => move(i, -1)} aria-label={`${b?.name} yukarı`}>
                            <ArrowUp size={14} aria-hidden />
                          </button>
                          <button className="sg-button" style={{ minHeight: 36, padding: '6px 10px' }} disabled={i === order.length - 1} onClick={() => move(i, 1)} aria-label={`${b?.name} aşağı`}>
                            <ArrowDown size={14} aria-hidden />
                          </button>
                          <button className="sg-button danger" style={{ minHeight: 36, padding: '6px 10px' }} onClick={() => setOrder((o) => o.filter((x) => x !== bid))} aria-label={`${b?.name} listeden çıkar`}>
                            <Trash2 size={14} aria-hidden />
                          </button>
                        </span>
                      )}
                    </div>
                    {miss.length > 0 && (
                      <p className="sg-banner" style={{ marginTop: 8, padding: '8px 12px' }}>
                        Bu kitabın kaydında geçmiyor: <b>{miss.join(', ')}</b>
                      </p>
                    )}
                    <textarea className="sg-after" rows={4} value={text} readOnly={!open}
                      onChange={(e) => setFields({ ...fields, Books: { ...fields.Books, [bid]: e.target.value } })} aria-label={`${b?.name} paragrafı`} />
                    <div className={`sg-mono ${n < 40 || n > 90 ? 'over' : ''}`} style={{ ...muted, fontSize: 11, color: n < 40 || n > 90 ? '#c2361b' : 'var(--sg-muted)' }}>{n} kelime</div>
                  </div>
                </article>
              );
            })}
          </div>
          {open && <p style={{ ...muted, margin: '10px 0 0' }}>Kitap eklemek için yukarıdaki listeden seçip “Seçimle yeniden üret” deyin; çıkarılan kitap onayda listeden düşer.</p>}
        </section>

        <section className="sg-field" aria-label="Sıkça sorulan sorular">
          <div className="sg-field-head">
            <span>Sıkça sorulan sorular ({fmt(fields.Faq.length)})</span>
            <span className={`sg-mono ${fields.Faq.length < 3 || fields.Faq.length > 5 ? 'over' : ''}`}>3–5 soru · yalnız kitap bilgisiyle cevaplanabilen</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {fields.Faq.map((f, i) => (
              <div key={i} style={{ display: 'grid', gap: 6 }}>
                <div style={{ display: 'flex', gap: 6 }}>
                  <input value={f.q} readOnly={!open} onChange={(e) => setFaq(i, { q: e.target.value })} placeholder="Soru" aria-label={`Soru ${i + 1}`}
                    style={{ flex: 1, minWidth: 0, minHeight: 44, padding: '0 12px', border: '1px solid #bfeedb', borderRadius: 12, background: '#eefbf5', font: 'inherit', fontSize: 12.5, fontWeight: 700 }} />
                  {open && (
                    <button className="sg-button danger" style={{ padding: '6px 10px' }} onClick={() => setFields((x) => ({ ...x, Faq: x.Faq.filter((_, j) => j !== i) }))} aria-label={`Soru ${i + 1} sil`}>
                      <Trash2 size={14} aria-hidden />
                    </button>
                  )}
                </div>
                <textarea className="sg-after" style={{ marginTop: 0 }} rows={2} value={f.a} readOnly={!open} onChange={(e) => setFaq(i, { a: e.target.value })} aria-label={`Cevap ${i + 1}`} />
              </div>
            ))}
            {open && (
              <button className="sg-button" style={{ alignSelf: 'flex-start' }} onClick={() => setFields((x) => ({ ...x, Faq: [...x.Faq, { q: '', a: '' }] }))}>
                <Plus size={16} aria-hidden /> Soru ekle
              </button>
            )}
          </div>
        </section>
      </div>

      <p className="sg-tag" style={{ marginTop: 16 }}>GOOGLE’DA GÖRÜNÜŞÜ (YAKLAŞIK)</p>
      <div className="sg-snippet">
        <div className="u">timas.com.tr › rehber</div>
        <div className="t">{fields.SeoTitle || guide.topic.title}</div>
        <div className="d">{fields.SeoDescription || 'Meta açıklama yok; Google sayfadan kendisi bir parça seçer.'}</div>
      </div>

      <details className="sg-more" style={{ marginTop: 12 }}>
        <summary>Yapılandırılmış veri (ItemList + soru–cevap) — kodla kurulur, onayda yeniden hesaplanır</summary>
        <pre className="sg-pre" style={{ marginTop: 8 }}>{JSON.stringify(guide.jsonld, null, 2)}</pre>
      </details>

      {open && (
        <>
          {decide.error && <div style={{ marginTop: 12 }}><Failed error={decide.error} /></div>}
          <div className="sg-decide" style={{ marginTop: 16 }}>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Editör notu (isteğe bağlı)" aria-label="Editör notu" />
            <button className="sg-button primary" disabled={!canApprove || decide.isPending || !order.length || emptyBooks.length > 0 || !fields.SeoTitle.trim()}
              onClick={() => decide.mutate('approve')}>
              {decide.isPending && decide.variables === 'approve' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />}
              Onayla
            </button>
            <button className="sg-button danger" disabled={!canApprove || decide.isPending} onClick={() => decide.mutate('reject')}>
              <X size={16} aria-hidden /> Reddet
            </button>
            <small>
              {!canApprove
                ? 'Onay yetkiniz yok; taslağı görebilir, indirebilir ve yeniden ürettirebilirsiniz. Yetki: Yönetim → SEO & GEO → Onay verebilenler.'
                : emptyBooks.length
                  ? 'Paragrafı boş kitap var; yazın ya da listeden çıkarın.'
                  : 'Onay yalnız kaydedilir; siteye, T-soft’a ya da CRM’e gönderim yok. Sayfa, indirilen HTML ile site yönetiminden elle açılır.'}
            </small>
          </div>
        </>
      )}
    </div>
  );
}
