import { useDeferredValue, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Download, ExternalLink, Loader2, Plus, Search, Sparkles, Trash2, X } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { useCan } from '../useAdmin';
import { STATUS_LABEL, call, dateTime, fmt, qs, seoApi } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';
import { EmptyHint } from '../components/Explain';

/* ------------------------------------------------------------------ uçlar: /api/v1/seo-geo/faq/* */
type DraftStatus = 'hazir' | 'onaylandi' | 'reddedildi';
type BookState = 'uygun' | 'kaynak_yok' | 'atlandi';
type Filter = '' | DraftStatus | BookState | 'taslak_yok';
type Qa = { q: string; a: string };
type Run = { running: boolean; done: number; failed: number; startedAt: string | null; finishedAt: string | null; error: string | null };
type Row = {
  id: string;
  name: string | null;
  authors: string | null;
  brand: string | null;
  image: string | null;
  url: string | null;
  sales: number;
  state: BookState;
  reason: string | null;
  draft: { id: string; status: DraftStatus } | null;
};
type DraftBase = {
  id: string;
  productId: string;
  name: string | null;
  status: DraftStatus;
  model: string | null;
  createdBy: string | null;
  createdAt: string;
  decidedBy: string | null;
  decidedAt: string | null;
  note: string | null;
};
type Draft = DraftBase & {
  fields: { Faq: Qa[] };
  jsonld: unknown;
  /** Soru–cevap başına: kitabın kaydında geçmeyen sayı ve özel adlar. */
  unsupported: string[][];
};
type Detail = {
  book: { id: string; name: string | null; authors: string | null; brand: string | null; url: string | null; image: string | null; isbn: string | null; sales: number };
  facts: Array<{ key: string; label: string; value: string }>;
  state: BookState;
  reason: string | null;
  draft: Draft | null;
  history: DraftBase[];
};
type Counts = Partial<Record<Exclude<Filter, ''>, number>>;

const PAGE = 40;
const faqApi = {
  list: (p: { status: string; q: string; start: number }) =>
    call<{ total: number; start: number; counts: Counts; run: Run; items: Row[] }>(`faq?${qs({ ...p, limit: PAGE })}`),
  get: (pid: string) => call<Detail>(`faq/${encodeURIComponent(pid)}`),
  draft: (pid: string) => call<Draft>(`faq/${encodeURIComponent(pid)}/draft`, { method: 'POST', timeout: 300_000 }),
  decide: (id: string, body: { action: 'approve' | 'reject'; fields?: { Faq: Qa[] }; note?: string }) =>
    call<Draft>(`faq/drafts/${encodeURIComponent(id)}/decide`, { method: 'POST', body, timeout: 120_000 }),
  exportUrl: () => `${ENGINE_BASE}/api/v1/seo-geo/faq/export.json`,
};

const FILTERS: Array<{ id: Filter; label: string }> = [
  { id: '', label: 'Tümü' },
  { id: 'taslak_yok', label: 'Taslak bekleyen' },
  { id: 'hazir', label: STATUS_LABEL.hazir },
  { id: 'onaylandi', label: STATUS_LABEL.onaylandi },
  { id: 'reddedildi', label: STATUS_LABEL.reddedildi },
  { id: 'kaynak_yok', label: 'Kaynak yok' },
  { id: 'atlandi', label: 'Atlanan' },
];
const STATE_LABEL: Record<BookState, string> = { uygun: 'Taslak yok', kaynak_yok: 'Kaynak yok', atlandi: 'Atlandı' };
const muted = { fontSize: 12, color: 'var(--sg-muted)' } as const;
const tone = (s: DraftStatus) => (s === 'onaylandi' ? 'good' : s === 'reddedildi' ? 'bad' : 'violet');
const all = (c: Counts) => (c.uygun ?? 0) + (c.kaynak_yok ?? 0) + (c.atlandi ?? 0);

/** Kitap soru–cevapları: kitap sayfası için 3–5 soru–cevap, yalnız kitabın kendi CRM kartından ve site kaydından.
 *  CRM’deki okuma-anlama test soruları kullanılmaz. ZEKİ AI yazar, insan onaylar; onaylananlar JSON olarak indirilir. */
export default function SeoFaq() {
  const [params, setParams] = useSearchParams();
  const status = (params.get('durum') ?? '') as Filter;
  const pid = params.get('kitap') ?? '';
  const [q, setQ] = useState('');
  const dq = useDeferredValue(q.trim());
  const [start, setStart] = useState(0);
  useEffect(() => setStart(0), [status, dq]);
  const canExport = useCan('veri.disa-aktar');

  const set = (changes: Record<string, string>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };

  const list = useQuery({
    queryKey: ['seo-faq', status, dq, start],
    queryFn: () => faqApi.list({ status, q: dq, start }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (query) => (query.state.data?.run.running ? 15_000 : false),
  });
  const d = list.data;
  const counts = d?.counts ?? {};
  const total = d?.total ?? 0;

  return (
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/sss"
      crumb="Kitap soru–cevapları"
      eyebrow="SEO & GEO · kitap soru–cevapları"
      title="Kitap soru–cevapları"
      lead="Google ve yapay zekâ asistanları «kaç yaş için uygun?», «ne anlatıyor?», «kaç sayfa?» gibi sorulara doğrudan cevap veren soru–cevapları alıntılar. Zeki AI bunları yalnız kitabın CRM kartından ve sitedeki kaydından yazar; siz düzenleyip onaylarsınız. Siteye hiçbir şey gönderilmez."
      actions={
        canExport && (
          <a className="sg-button" href={faqApi.exportUrl()} download>
            <Download size={16} aria-hidden /> Onaylananları indir (JSON)
          </a>
        )
      }
    >
      <div className="sg-filters" role="toolbar" aria-label="Süzgeç">
        {FILTERS.map((f) => (
          <button key={f.id || 'tum'} className="sg-filter" aria-pressed={status === f.id} onClick={() => set({ durum: f.id })}>
            {f.label} <span className="sg-mono">{fmt(f.id ? counts[f.id] ?? 0 : all(counts))}</span>
          </button>
        ))}
      </div>
      <p style={{ margin: '-6px 0 0', fontSize: 12.5, color: 'var(--sg-muted)' }}>
        Sıra satıştan aza. «Taslak bekleyen»: bilgisi yeterli, henüz taslak yazılmadı. «Kaynak yok»: CRM kartında soru–cevaba yetecek bilgi yok. «Atlanan»: kitap bu iş için uygun görülmedi; nedeni kitabı açınca yazar. CRM’deki okuma-anlama test soruları kullanılmaz.
      </p>
      {d?.run.error && <p className="sg-banner err">Son gece turu: {d.run.error}</p>}

      <div className="sg-audit">
        <section className="sg-card" aria-label="Kitaplar">
          <label className="sg-search" style={{ marginBottom: 8 }}>
            <Search size={16} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, yazar ya da ürün kodu" aria-label="Kitap ara" />
          </label>
          {d && (
            <p style={{ ...muted, margin: '0 0 10px' }}>
              {fmt(total)} kitap · satıştan aza
              {d.run.running && ` · gece hazırlığı sürüyor (${fmt(d.run.done)})`}
              {!d.run.running && d.run.finishedAt && ` · gece hazırlığı ${dateTime(d.run.finishedAt)}: ${fmt(d.run.done)} taslak`}
            </p>
          )}
          {list.isLoading && <Loading text="Kitaplar getiriliyor…" />}
          {list.error && <Failed error={list.error} />}
          {d && !d.items.length && (
            <EmptyHint title="Bu süzgece uyan kitap yok" why="Aramayı kısaltın ya da üstten «Tümü»nü seçin." />
          )}
          <div className="sg-list">
            {d?.items.map((b) => (
              <button key={b.id} className="sg-item" style={{ gridTemplateColumns: '44px minmax(0,1fr) auto' }} aria-current={pid === b.id} onClick={() => set({ kitap: b.id })}>
                {b.image ? <img src={b.image} alt="" loading="lazy" /> : <span className="sg-noimg" aria-hidden />}
                <span style={{ minWidth: 0 }}>
                  <span className="sg-item-name">{b.name}</span>
                  <span className="sg-item-meta">
                    {[b.authors, b.brand].filter(Boolean).join(' · ')} · <span className="sg-mono">{fmt(b.sales)} satış</span>
                  </span>
                </span>
                <span className="sg-item-side">
                  {b.draft ? (
                    <span className={`sg-chip ${tone(b.draft.status)}`}>{STATUS_LABEL[b.draft.status]}</span>
                  ) : (
                    <span className={`sg-chip ${b.state === 'uygun' ? '' : 'mid'}`} title={b.reason ?? undefined}>{STATE_LABEL[b.state]}</span>
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

        <section aria-label="Seçilen kitap">
          {pid ? (
            <BookPanel pid={pid} />
          ) : (
            <EmptyHint
              title="Listeden bir kitap seçin"
              why="Seçtiğiniz kitabın soru–cevaba kaynak olan bilgileri ve varsa Zeki AI taslağı burada açılır."
            />
          )}
        </section>
      </div>
    </SeoLayout>
  );
}

/* ------------------------------------------------------------------ kitap: bilgiler + taslak */
function BookPanel({ pid }: { pid: string }) {
  const qc = useQueryClient();
  const canPropose = useCan('seo.oneri-uret');
  const x = useQuery({ queryKey: ['seo-faq-book', pid], queryFn: () => faqApi.get(pid), enabled: ENGINE_ENABLED, retry: false });
  const draft = useMutation({
    mutationFn: () => faqApi.draft(pid),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo-faq-book', pid] });
      qc.invalidateQueries({ queryKey: ['seo-faq'] });
    },
  });

  if (x.isLoading) return <Loading text="Kitap açılıyor…" />;
  if (x.error) return <Failed error={x.error} />;
  if (!x.data) return null;
  const { book, facts, state, reason } = x.data;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="sg-card">
        <div className="sg-eyebrow">Kitap · soru–cevap kaynağı</div>
        <h2 style={{ fontSize: 20, margin: '6px 0' }}>{book.name}</h2>
        <div className="sg-mono" style={muted}>
          {[book.authors, book.brand, book.isbn].filter(Boolean).join(' · ')} · {fmt(book.sales)} satış
          {book.url && (
            <>
              {' · '}
              <a href={book.url} target="_blank" rel="noreferrer">sayfa <ExternalLink size={11} aria-hidden /></a>
            </>
          )}
        </div>
        {state !== 'uygun' && <p className="sg-banner" style={{ marginTop: 12 }}>{reason}</p>}
        <details className="sg-more" style={{ marginTop: 10 }}>
          <summary>Kullanılan bilgiler ({fmt(facts.length)})</summary>
          <dl style={{ margin: '8px 0 0', display: 'grid', gridTemplateColumns: 'minmax(0,140px) minmax(0,1fr)', gap: '6px 12px', fontSize: 12.5, lineHeight: 1.5 }}>
            {facts.map((f) => (
              <div key={f.key} style={{ display: 'contents' }}>
                <dt style={{ color: 'var(--sg-muted)' }}>{f.label}</dt>
                <dd style={{ margin: 0, minWidth: 0, overflowWrap: 'anywhere' }}>{f.value}</dd>
              </div>
            ))}
          </dl>
        </details>
        {canPropose && state === 'uygun' && (
          <div style={{ marginTop: 12 }}>
            <button className="sg-button primary" disabled={draft.isPending} onClick={() => draft.mutate()}>
              {draft.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Sparkles size={16} aria-hidden />}
              {x.data.draft ? 'Yeniden üret' : 'Taslak üret'}
            </button>
          </div>
        )}
        {draft.isPending && <p className="sg-banner" style={{ marginTop: 12 }}>Zeki AI soru–cevapları yazıyor; bir iki dakika sürebilir.</p>}
        {draft.error && <div style={{ marginTop: 12 }}><Failed error={draft.error} /></div>}
      </div>

      {x.data.draft && <Editor key={`${x.data.draft.id}:${x.data.draft.status}`} draft={x.data.draft} />}

      {x.data.history.length > 0 && (
        <details className="sg-more">
          <summary>Önceki kararlar ({fmt(x.data.history.length)})</summary>
          <ul style={{ margin: '8px 0 0', paddingLeft: 20, fontSize: 12.5, lineHeight: 1.6 }}>
            {x.data.history.map((h) => (
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
function Editor({ draft }: { draft: Draft }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const canApprove = !!me.data?.canApprove;
  const open = draft.status === 'hazir';
  const [faq, setFaq] = useState<Qa[]>(() => (draft.fields.Faq ?? []).map((f) => ({ ...f })));
  const [note, setNote] = useState('');
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') => faqApi.decide(draft.id, action === 'approve' ? { action, fields: { Faq: faq }, note } : { action, note }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo-faq-book', draft.productId] });
      qc.invalidateQueries({ queryKey: ['seo-faq'] });
    },
  });
  const edit = (i: number, patch: Partial<Qa>) => setFaq((l) => l.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const filled = faq.filter((f) => f.q.trim() && f.a.trim());
  const countOff = faq.length < 3 || faq.length > 5;

  return (
    <div className="sg-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <div>
          <h2>Zeki AI taslağı</h2>
          <p className="sg-sub" style={{ margin: 0 }}>
            {dateTime(draft.createdAt)} · {draft.createdBy ?? '—'}
            {open ? ' · onaylamadan önce düzenleyebilirsiniz' : ''}
          </p>
        </div>
        <span className={`sg-chip ${tone(draft.status)}`}>{STATUS_LABEL[draft.status]}</span>
      </div>

      {!open && (
        <p className={`sg-banner ${draft.status === 'onaylandi' ? 'ok' : ''}`} style={{ marginTop: 12 }}>
          <b>{STATUS_LABEL[draft.status]}</b> · {draft.decidedBy ?? '—'} · {dateTime(draft.decidedAt)}
          {draft.note ? ` — ${draft.note}` : ''}
          {draft.status === 'onaylandi' && ' — Siteye gönderim yok; onaylananlar «Onaylananları indir» dosyasıyla site yönetimine elle verilir.'}
        </p>
      )}

      <section className="sg-field" aria-label="Soru–cevaplar" style={{ marginTop: 16 }}>
        <div className="sg-field-head">
          <span>Soru–cevaplar ({fmt(faq.length)})</span>
          <span className={`sg-mono ${countOff ? 'over' : ''}`}>3–5 soru · yalnız kitap bilgisiyle cevaplanabilen</span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {faq.map((f, i) => {
            const miss = draft.unsupported[i] ?? [];
            return (
              <div key={i} style={{ display: 'grid', gap: 6 }}>
                <div style={{ display: 'flex', gap: 6 }}>
                  <input value={f.q} readOnly={!open} onChange={(e) => edit(i, { q: e.target.value })} placeholder="Soru" aria-label={`Soru ${i + 1}`}
                    style={{ flex: 1, minWidth: 0, minHeight: 44, padding: '0 12px', border: '1px solid #bfeedb', borderRadius: 12, background: '#eefbf5', font: 'inherit', fontSize: 12.5, fontWeight: 700 }} />
                  {open && (
                    <button className="sg-button danger" style={{ padding: '6px 10px' }} onClick={() => setFaq((l) => l.filter((_, j) => j !== i))} aria-label={`Soru ${i + 1} sil`}>
                      <Trash2 size={14} aria-hidden />
                    </button>
                  )}
                </div>
                <textarea className="sg-after" style={{ marginTop: 0 }} rows={3} value={f.a} readOnly={!open} onChange={(e) => edit(i, { a: e.target.value })} aria-label={`Cevap ${i + 1}`} />
                {miss.length > 0 && (
                  <p className="sg-banner" style={{ margin: 0, padding: '8px 12px' }}>
                    Kitabın kaydında geçmiyor: <b>{miss.join(', ')}</b>
                  </p>
                )}
              </div>
            );
          })}
          {open && (
            <button className="sg-button" style={{ alignSelf: 'flex-start' }} onClick={() => setFaq((l) => [...l, { q: '', a: '' }])}>
              <Plus size={16} aria-hidden /> Soru ekle
            </button>
          )}
        </div>
      </section>

      <details className="sg-more" style={{ marginTop: 12 }}>
        <summary>Yapısal veri (soru–cevap) — kendiliğinden kurulur, onayda yeniden hesaplanır</summary>
        <pre className="sg-pre" style={{ marginTop: 8 }}>{JSON.stringify(draft.jsonld, null, 2)}</pre>
      </details>

      {open && (
        <>
          {decide.error && <div style={{ marginTop: 12 }}><Failed error={decide.error} /></div>}
          <div className="sg-decide" style={{ marginTop: 16 }}>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (isteğe bağlı), ör. yaş aralığı düzeltildi" aria-label="Editör notu" />
            <button className="sg-button primary" disabled={!canApprove || decide.isPending || !filled.length} onClick={() => decide.mutate('approve')}>
              {decide.isPending && decide.variables === 'approve' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />}
              Onayla
            </button>
            <button className="sg-button danger" disabled={!canApprove || decide.isPending} onClick={() => decide.mutate('reject')}>
              <X size={16} aria-hidden /> Reddet
            </button>
            <small>
              {!canApprove
                ? 'Onay yetkiniz yok; taslağı görebilir ve yeniden ürettirebilirsiniz. Yetki: Yönetim → SEO & GEO → Onay verebilenler.'
                : 'Onay yalnız kayda geçer; siteye, T-soft’a ya da CRM’e hiçbir şey gönderilmez. Boş soru–cevaplar onayda düşer.'}
            </small>
          </div>
        </>
      )}
    </div>
  );
}
