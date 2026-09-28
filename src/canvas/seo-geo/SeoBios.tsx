import { useDeferredValue, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Download, ExternalLink, Loader2, RefreshCw, Search, Sparkles, X } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { useCan } from '../useAdmin';
import { STATUS_LABEL, call, dateTime, fmt, qs, seoApi, type ProductDetail } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/* ------------------------------------------------------------------ uçlar: /api/v1/seo-geo/bios/* */
type DraftStatus = 'hazir' | 'onaylandi' | 'reddedildi';
type Filter = '' | DraftStatus | 'taslak_yok' | 'kaynak_yok' | 'eslesmedi';
type Book = { id: string; name: string; url: string | null; isbn: string | null; sales?: number };
type Run = { running: boolean; phase: string | null; read: number | null; done: number; failed: number; startedAt: string | null; finishedAt: string | null; error: string | null };
type AuthorRow = {
  key: string;
  name: string;
  sales: number;
  bookCount: number;
  bioLength: number;
  hasBio: boolean;
  /** Özgeçmiş yoksa CRM'e girilecek iş. */
  task: string | null;
  /** CRM adı T-soft'taki yazar adıyla eşleşti mi. */
  matched: boolean;
  page: { link: string; url: string; id: string } | null;
  sameAs: string[];
  topBooks: string[];
  draft: { id: string; status: DraftStatus } | null;
};
type BioFields = { Bio: string; Summary: string };
type Draft = {
  id: string;
  authorKey: string;
  name: string | null;
  status: DraftStatus;
  model: string | null;
  createdBy: string | null;
  createdAt: string;
  decidedBy: string | null;
  decidedAt: string | null;
  note: string | null;
  fields: BioFields;
  books: Book[];
  jsonld: unknown;
  /** Özgeçmişte ve kitap adlarında geçmeyen sayı ve özel adlar. */
  unsupported: string[];
  limits: ProductDetail['limits'] & { bio_min_words: number; bio_max_words: number };
};
type AuthorDetail = Omit<AuthorRow, 'topBooks' | 'draft'> & { books: Book[]; source: string; draft: Draft | null; history: Array<Omit<Draft, 'fields' | 'books' | 'jsonld' | 'unsupported' | 'limits'>> };
type Counts = Partial<Record<'yazar' | 'kaynak_var' | 'kaynak_yok' | 'taslak_yok' | 'eslesmedi' | DraftStatus, number>>;

const PAGE = 40;
const biosApi = {
  list: (p: { status: string; q: string; start: number }) =>
    call<{ total: number; start: number; counts: Counts; crmRead: string | null; crmReady: boolean; bioMinChars: number; run: Run; items: AuthorRow[] }>(
      `bios?${qs({ ...p, limit: PAGE })}`,
    ),
  get: (key: string) => call<AuthorDetail>(`bios/${encodeURIComponent(key)}`),
  refresh: () => call<{ started: boolean; run: Run }>('bios/refresh', { method: 'POST' }),
  // Taslak model kuyruğunda bekleyebilir.
  draft: (key: string) => call<Draft>(`bios/${encodeURIComponent(key)}/draft`, { method: 'POST', timeout: 300_000 }),
  decide: (id: string, body: { action: 'approve' | 'reject'; fields?: BioFields; note?: string }) =>
    call<Draft>(`bios/drafts/${encodeURIComponent(id)}/decide`, { method: 'POST', body, timeout: 120_000 }),
  exportUrl: (id: string) => `${ENGINE_BASE}/api/v1/seo-geo/bios/drafts/${encodeURIComponent(id)}/export.html`,
};

const FILTERS: Array<{ id: Filter; label: string; count: keyof Counts }> = [
  { id: '', label: 'Tümü', count: 'yazar' },
  { id: 'taslak_yok', label: 'Taslak bekleyen', count: 'taslak_yok' },
  { id: 'hazir', label: STATUS_LABEL.hazir, count: 'hazir' },
  { id: 'onaylandi', label: STATUS_LABEL.onaylandi, count: 'onaylandi' },
  { id: 'reddedildi', label: STATUS_LABEL.reddedildi, count: 'reddedildi' },
  { id: 'kaynak_yok', label: 'Özgeçmiş yok', count: 'kaynak_yok' },
  { id: 'eslesmedi', label: 'Sitede adı eşleşmedi', count: 'eslesmedi' },
];
const words = (s: string) => s.split(/\s+/).filter(Boolean).length;
const muted = { fontSize: 12, color: 'var(--sg-muted)' } as const;
const tone = (s: DraftStatus) => (s === 'onaylandi' ? 'good' : s === 'reddedildi' ? 'bad' : 'violet');

/** Yazar biyografileri: CRM özgeçmişinden yazar sayfası biyografisi. Sıra satıştan aza; özgeçmişi olmayan yazar CRM işi
 *  olarak listelenir. ZEKİ AI yazar, insan onaylar; hiçbir yere gönderilmez, HTML olarak indirilir. */
export default function SeoBios() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const status = (params.get('durum') ?? '') as Filter;
  const key = params.get('yazar') ?? '';
  const [q, setQ] = useState('');
  const dq = useDeferredValue(q.trim());
  const [start, setStart] = useState(0);
  useEffect(() => setStart(0), [status, dq]);
  const canRun = useCan('seo.calistir');

  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };

  const list = useQuery({
    queryKey: ['seo-bios', status, dq, start],
    queryFn: () => biosApi.list({ status, q: dq, start }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (query) => (query.state.data?.run.running ? 15_000 : false),
  });
  const refresh = useMutation({
    mutationFn: biosApi.refresh,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-bios'] }),
  });
  const d = list.data;
  const counts = d?.counts ?? {};
  const total = d?.total ?? 0;

  return (
    <SeoLayout
      path="/seo-geo/yazar-biyografi"
      crumb="Yazar biyografileri"
      eyebrow="SEO & GEO · yazar biyografileri"
      title="Yazar biyografileri"
      lead="“Bu yazar kim?” sorusunda Google ve yapay zekâ cevapları yazarı anlatan, kaynağı belli bir sayfa arar. Biyografi yalnız CRM’deki özgeçmişten yazılır; yazarın Timaş’tan çıkan kitapları listesini sistem kurar. Sıra satıştan aza. Özgeçmişi olmayan yazar için taslak yazılmaz, CRM’e girilecek iş olarak görünür. Onay yalnız kaydedilir; siteye hiçbir şey gönderilmez."
      actions={
        canRun && (
          <button className="sg-button" disabled={refresh.isPending || d?.run.running || d?.crmReady === false} onClick={() => refresh.mutate()}>
            {refresh.isPending || d?.run.running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            CRM’den yeniden oku
          </button>
        )
      }
    >
      <div className="sg-filters" role="toolbar" aria-label="Süzgeç">
        {FILTERS.map((f) => (
          <button key={f.id || 'tum'} className="sg-filter" aria-pressed={status === f.id} onClick={() => set({ durum: f.id })}>
            {f.label} <span className="sg-mono">{fmt(counts[f.count] ?? 0)}</span>
          </button>
        ))}
      </div>

      {d && !d.crmReady && <p className="sg-banner">CRM bağlantısı tanımlı değil; özgeçmişler okunamıyor.</p>}
      {refresh.error && <Failed error={refresh.error} />}
      {d?.run.error && <p className="sg-banner err">Son tur: {d.run.error}</p>}

      <div className="sg-audit">
        <section className="sg-card" aria-label="Yazarlar">
          <label className="sg-search" style={{ marginBottom: 8 }}>
            <Search size={16} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Yazar adı" aria-label="Yazar ara" />
          </label>
          {d && (
            <p style={{ ...muted, margin: '0 0 10px' }}>
              {fmt(total)} yazar · CRM okuması {dateTime(d.crmRead)}
              {d.run.running && ` · ${d.run.phase === 'taslak' ? `taslaklar hazırlanıyor (${fmt(d.run.done)})` : 'CRM okunuyor'}`}
              {!d.run.running && d.run.finishedAt && ` · son tur ${dateTime(d.run.finishedAt)}: ${fmt(d.run.done)} taslak`}
            </p>
          )}
          {list.isLoading && <Loading text="Yazarlar getiriliyor…" />}
          {list.error && <Failed error={list.error} />}
          {d && !d.items.length && (
            <div className="sg-empty">
              <h2>Yazar yok</h2>
              <p>{d.crmRead ? 'Bu süzgece uyan yazar bulunamadı.' : 'CRM’den yazar özgeçmişleri henüz okunmadı; gece okuması ya da “CRM’den yeniden oku” ile gelir.'}</p>
            </div>
          )}
          <div className="sg-list">
            {d?.items.map((a) => (
              <button key={a.key} className="sg-item" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }} aria-current={key === a.key} onClick={() => set({ yazar: a.key })}>
                <span style={{ minWidth: 0 }}>
                  <span className="sg-item-name">{a.name}</span>
                  <span className="sg-item-meta">
                    <span className="sg-mono">{fmt(a.sales)} satış · {fmt(a.bookCount)} kitap</span>
                    {a.topBooks.length > 0 && ` · ${a.topBooks.join(', ')}`}
                  </span>
                </span>
                <span className="sg-item-side">
                  {!a.hasBio ? (
                    <span className="sg-chip bad">Özgeçmiş yok</span>
                  ) : a.draft ? (
                    <span className={`sg-chip ${tone(a.draft.status)}`}>{STATUS_LABEL[a.draft.status]}</span>
                  ) : (
                    <span className="sg-chip">Taslak yok</span>
                  )}
                  {!a.matched && <span className="sg-chip mid">Eşleşmedi</span>}
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

        <section aria-label="Seçilen yazar">
          {key ? (
            <AuthorPanel authorKey={key} />
          ) : (
            <div className="sg-empty">
              <h2>Bir yazar seçin</h2>
              <p>Soldan bir yazar seçtiğinizde CRM özgeçmişi, sitedeki kitapları ve varsa ZEKİ AI taslağı açılır.</p>
            </div>
          )}
        </section>
      </div>
    </SeoLayout>
  );
}

/* ------------------------------------------------------------------ yazar: kaynak + taslak */
function AuthorPanel({ authorKey }: { authorKey: string }) {
  const qc = useQueryClient();
  const canPropose = useCan('seo.oneri-uret');
  const a = useQuery({ queryKey: ['seo-bio', authorKey], queryFn: () => biosApi.get(authorKey), enabled: ENGINE_ENABLED, retry: false });
  const draft = useMutation({
    mutationFn: () => biosApi.draft(authorKey),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo-bio', authorKey] });
      qc.invalidateQueries({ queryKey: ['seo-bios'] });
    },
  });

  if (a.isLoading) return <Loading text="Yazar açılıyor…" />;
  if (a.error) return <Failed error={a.error} />;
  if (!a.data) return null;
  const x = a.data;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="sg-card">
        <div className="sg-eyebrow">Yazar · CRM kaydı</div>
        <h2 style={{ fontSize: 20, margin: '6px 0' }}>{x.name}</h2>
        <div className="sg-mono" style={muted}>
          {fmt(x.sales)} satış · {fmt(x.bookCount)} kitap satışta · özgeçmiş {fmt(x.bioLength)} karakter
        </div>
        <p style={{ ...muted, margin: '8px 0 0' }}>
          {x.page ? (
            <a href={x.page.url} target="_blank" rel="noreferrer">
              Sitedeki yazar sayfası <ExternalLink size={11} aria-hidden />
            </a>
          ) : (
            'Sitede bu yazar için sayfa bulunamadı.'
          )}
          {!x.matched && ' · CRM’deki adı sitedeki yazar adlarıyla eşleşmedi; adın yazımı iki yerde aynı olmalı.'}
          {x.sameAs.length > 0 && ` · kimlik bağlantısı: ${x.sameAs.length}`}
        </p>
        {!x.hasBio ? (
          <p className="sg-banner" style={{ marginTop: 12 }}>
            <b>{x.task}</b> — CRM’deki kişi kaydına özgeçmiş yazıldığında bir sonraki okumada taslak hazırlanabilir.
          </p>
        ) : (
          <details className="sg-more" style={{ marginTop: 10 }}>
            <summary>CRM özgeçmişi (kaynak)</summary>
            <div style={{ marginTop: 8, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-line' }}>{x.source}</div>
          </details>
        )}
        <details className="sg-more" style={{ marginTop: 10 }}>
          <summary>Satıştaki kitapları ({fmt(x.books.length)})</summary>
          <ol style={{ margin: '8px 0 0', paddingLeft: 20, fontSize: 13, lineHeight: 1.6 }}>
            {x.books.map((b) => (
              <li key={b.id}>
                {b.url ? <a href={b.url} target="_blank" rel="noreferrer">{b.name}</a> : b.name} <span className="sg-mono" style={muted}>{fmt(b.sales)} satış</span>
              </li>
            ))}
          </ol>
        </details>
        {canPropose && x.hasBio && (
          <div style={{ marginTop: 12 }}>
            <button className="sg-button primary" disabled={draft.isPending} onClick={() => draft.mutate()}>
              {draft.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Sparkles size={16} aria-hidden />}
              {x.draft ? 'Yeniden üret' : 'Taslak üret'}
            </button>
          </div>
        )}
        {draft.isPending && <p className="sg-banner" style={{ marginTop: 12 }}>ZEKİ AI biyografiyi yazıyor; bir iki dakika sürebilir.</p>}
        {draft.error && <div style={{ marginTop: 12 }}><Failed error={draft.error} /></div>}
      </div>

      {x.draft && <Editor key={`${x.draft.id}:${x.draft.status}`} draft={x.draft} name={x.name} />}

      {x.history.length > 0 && (
        <details className="sg-more">
          <summary>Önceki kararlar ({fmt(x.history.length)})</summary>
          <ul style={{ margin: '8px 0 0', paddingLeft: 20, fontSize: 12.5, lineHeight: 1.6 }}>
            {x.history.map((h) => (
              <li key={h.id}>
                {STATUS_LABEL[h.status]} · {h.decidedBy ?? h.createdBy ?? '—'} · {dateTime(h.decidedAt ?? h.createdAt)}
                {h.note ? ` — ${h.note}` : ''}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ taslak: düzenleme, gerçeklik, karar */
function Editor({ draft, name }: { draft: Draft; name: string }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const canApprove = !!me.data?.canApprove;
  const canExport = useCan('veri.disa-aktar');
  const open = draft.status === 'hazir';
  const [fields, setFields] = useState<BioFields>({ Bio: draft.fields.Bio ?? '', Summary: draft.fields.Summary ?? '' });
  const [note, setNote] = useState('');
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') => biosApi.decide(draft.id, action === 'approve' ? { action, fields, note } : { action, note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo-bio', draft.authorKey] });
      qc.invalidateQueries({ queryKey: ['seo-bios'] });
    },
  });
  const L = draft.limits;
  const n = words(fields.Bio);
  const bioOff = n < L.bio_min_words || n > L.bio_max_words;
  const sumOff = fields.Summary.length < L.meta_min || fields.Summary.length > L.meta_max;

  return (
    <div className="sg-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <div>
          <h2>ZEKİ AI taslağı</h2>
          <p className="sg-sub" style={{ margin: 0 }}>
            {dateTime(draft.createdAt)} · {draft.createdBy ?? '—'}
            {open ? ' · onaylamadan önce düzenleyebilirsiniz' : ''}
          </p>
        </div>
        <span style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className={`sg-chip ${tone(draft.status)}`}>{STATUS_LABEL[draft.status]}</span>
          {canExport && (
            <a className="sg-button" href={biosApi.exportUrl(draft.id)} download>
              <Download size={16} aria-hidden /> HTML olarak indir
            </a>
          )}
        </span>
      </div>

      {!open && (
        <p className={`sg-banner ${draft.status === 'onaylandi' ? 'ok' : ''}`} style={{ marginTop: 12 }}>
          <b>{STATUS_LABEL[draft.status]}</b> · {draft.decidedBy ?? '—'} · {dateTime(draft.decidedAt)}
          {draft.note ? ` — ${draft.note}` : ''}
          {draft.status === 'onaylandi' && ' — Siteye gönderim yok; metin, indirilen HTML ile yazar sayfasına site yönetiminden elle girilir.'}
        </p>
      )}
      {draft.unsupported.length > 0 && (
        <p className="sg-banner" style={{ marginTop: 12 }}>
          Gerçeklik denetimi: CRM özgeçmişinde ve kitap adlarında geçmeyen ifadeler var — <b>{draft.unsupported.join(', ')}</b>. Onaylamadan önce bakın.
        </p>
      )}

      <div className="sg-diff" style={{ marginTop: 16 }}>
        <section className="sg-field" aria-label="Biyografi">
          <div className="sg-field-head">
            <span>Biyografi</span>
            <span className={`sg-mono ${bioOff ? 'over' : ''}`}>{n} kelime · {L.bio_min_words}–{L.bio_max_words}</span>
          </div>
          <textarea className="sg-after" rows={10} value={fields.Bio} readOnly={!open} onChange={(e) => setFields({ ...fields, Bio: e.target.value })} aria-label="Biyografi metni" />
        </section>
        <section className="sg-field" aria-label="Kısa tanım">
          <div className="sg-field-head">
            <span>Kısa tanım (meta açıklama)</span>
            <span className={`sg-mono ${sumOff ? 'over' : ''}`}>{fields.Summary.length} / {L.meta_min}–{L.meta_max} karakter</span>
          </div>
          <textarea className="sg-after" rows={3} value={fields.Summary} readOnly={!open} onChange={(e) => setFields({ ...fields, Summary: e.target.value })} aria-label="Kısa tanım" />
        </section>
        <section className="sg-field" aria-label="Timaş'tan çıkan kitapları">
          <div className="sg-field-head">
            <span>Timaş’tan çıkan kitapları ({fmt(draft.books.length)})</span>
            <span className="sg-mono">sistem kurar · satıştan aza</span>
          </div>
          <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.6 }}>
            {draft.books.map((b) => (
              <li key={b.id}>{b.url ? <a href={b.url} target="_blank" rel="noreferrer">{b.name}</a> : b.name}</li>
            ))}
          </ol>
        </section>
      </div>

      <p className="sg-tag" style={{ marginTop: 16 }}>GOOGLE’DA GÖRÜNÜŞÜ (YAKLAŞIK)</p>
      <div className="sg-snippet">
        <div className="u">timas.com.tr › yazar</div>
        <div className="t">{name}</div>
        <div className="d">{fields.Summary || 'Kısa tanım yok; Google sayfadan kendisi bir parça seçer.'}</div>
      </div>

      <details className="sg-more" style={{ marginTop: 12 }}>
        <summary>Yapılandırılmış veri (kişi) — sistem kurar, onayda yeniden hesaplanır</summary>
        <pre className="sg-pre" style={{ marginTop: 8 }}>{JSON.stringify(draft.jsonld, null, 2)}</pre>
      </details>

      {open && (
        <>
          {decide.error && <div style={{ marginTop: 12 }}><Failed error={decide.error} /></div>}
          <div className="sg-decide" style={{ marginTop: 16 }}>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Editör notu (isteğe bağlı)" aria-label="Editör notu" />
            <button className="sg-button primary" disabled={!canApprove || decide.isPending || !fields.Bio.trim()} onClick={() => decide.mutate('approve')}>
              {decide.isPending && decide.variables === 'approve' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />}
              Onayla
            </button>
            <button className="sg-button danger" disabled={!canApprove || decide.isPending} onClick={() => decide.mutate('reject')}>
              <X size={16} aria-hidden /> Reddet
            </button>
            <small>
              {!canApprove
                ? 'Onay yetkiniz yok; taslağı görebilir ve yeniden ürettirebilirsiniz. Yetki: Yönetim → SEO & GEO → Onay verebilenler.'
                : 'Onay yalnız kaydedilir; siteye, T-soft’a ya da CRM’e gönderim yok.'}
            </small>
          </div>
        </>
      )}
    </div>
  );
}
