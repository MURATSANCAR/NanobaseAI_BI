import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, ExternalLink, Loader2, Search, Sparkles, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { STATUS_LABEL, dateTime, fmt, scoreTone, seoApi, type PageDetail, type PageField, type PageKind } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

const PAGE = 30;
const KINDS: Array<{ id: PageKind; label: string }> = [
  { id: 'model', label: 'Yazarlar' },
  { id: 'category', label: 'Kategoriler' },
  { id: 'brand', label: 'Yayınevleri' },
];
const FIELDS: Array<{ id: PageField; label: string }> = [
  { id: 'SeoTitle', label: 'SEO başlığı' },
  { id: 'SeoDescription', label: 'Meta açıklama' },
  { id: 'Intro', label: 'Tanıtım metni' },
];

/** Yazar, kategori ve yayınevi sayfaları: başlık/açıklama denetimi ve Zeki AI önerisi (SEO başlığı, meta, tanıtım).
 *  Öneri sayfanın kitaplarından, satışlarından ve doğrulanmış Wikidata bilgisinden kurulur; T-soft'a gönderilmez. */
export default function SeoPages() {
  const [params, setParams] = useSearchParams();
  const kind = (params.get('tur') as PageKind) || 'model';
  const selected = params.get('sayfa') ?? '';
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [kind, query]);
  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params);
    if (v) next.set(k, v);
    else next.delete(k);
    if (k === 'tur') next.delete('sayfa');
    setParams(next, { replace: true });
  };
  const list = useQuery({
    queryKey: ['seo-pages', kind, query, start],
    queryFn: () => seoApi.pages({ type: kind, q: query, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const total = list.data?.total ?? 0;

  return (
    <SeoLayout
      path="/seo-geo/sayfalar"
      crumb="Yazar ve kategori"
      eyebrow="SEO & GEO · sayfalar"
      title="Yazar, kategori ve yayınevi sayfaları"
      lead="Bu sayfaların başlık ve açıklaması çoğunlukla yalnız ad. Zeki AI, sayfanın kitaplarından, satışlarından ve doğrulanmış Wikidata bilgisinden SEO başlığı, meta açıklama ve tanıtım metni önerir; uydurma bilgi işaretlenir. Karar yalnız kaydedilir, T-soft’a gönderilmez."
    >
      <div className="sg-filters" role="tablist" aria-label="Sayfa türü">
        {KINDS.map((k) => (
          <button key={k.id} className="sg-filter" role="tab" aria-selected={kind === k.id} aria-pressed={kind === k.id} onClick={() => set('tur', k.id)}>
            {k.label}
          </button>
        ))}
      </div>
      <div className="sg-audit">
        <section className="sg-card" aria-label="Sayfalar">
          <label className="sg-search" style={{ marginBottom: 12 }}>
            <Search size={16} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ad ara" aria-label="Sayfa ara" />
          </label>
          {list.isLoading && <Loading text="Sayfalar getiriliyor…" />}
          {list.error && <Failed error={list.error} />}
          {list.data && (
            <p className="sg-sub" style={{ margin: '0 0 10px', fontSize: 12, color: 'var(--sg-muted)' }}>
              {fmt(total)} sayfa · {fmt(list.data.withBooks)} tanesinde aktif kitap var · çok satandan aza
            </p>
          )}
          <div className="sg-list">
            {list.data?.items.map((p) => (
              <button key={p.id} className="sg-item" style={{ gridTemplateColumns: 'minmax(0,1fr) auto' }} aria-current={selected === p.id} onClick={() => set('sayfa', p.id)}>
                <span style={{ minWidth: 0 }}>
                  <span className="sg-item-name">{p.name}</span>
                  <span className="sg-item-meta sg-mono">
                    {fmt(p.books)} kitap · {fmt(p.sales)} satış · {p.issues} sorun
                  </span>
                </span>
                <span className="sg-item-side">
                  <span className={`sg-chip sg-mono ${scoreTone(p.score)}`}>{p.score}</span>
                  {p.proposal && <span className="sg-chip violet">{STATUS_LABEL[p.proposal]}</span>}
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
        <section aria-label="Seçilen sayfa">
          {selected ? (
            <Detail kind={kind} id={selected} />
          ) : (
            <div className="sg-empty">
              <h2>Bir sayfa seçin</h2>
              <p>Soldan bir yazar, kategori ya da yayınevi seçtiğinizde sorunları ve Zeki AI önerisi burada açılır.</p>
            </div>
          )}
        </section>
      </div>
    </SeoLayout>
  );
}

function Detail({ kind, id }: { kind: PageKind; id: string }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const d = useQuery({ queryKey: ['seo-page', kind, id], queryFn: () => seoApi.page(kind, id), enabled: ENGINE_ENABLED, retry: false });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['seo-page', kind, id] });
    qc.invalidateQueries({ queryKey: ['seo-pages'] });
  };
  const propose = useMutation({ mutationFn: () => seoApi.proposePage(kind, id), onSuccess: refresh });
  const p = d.data;
  const open = p?.proposals.find((x) => x.status === 'hazir');
  const last = p?.proposals.find((x) => x.status !== 'hazir');
  const [asked, setAsked] = useState<string | null>(null);
  useEffect(() => {
    const key = `${kind}:${id}`;
    if (p && !open && p.issues.length && asked !== key && !propose.isPending) {
      setAsked(key);
      propose.mutate();
    }
  }, [p, open, kind, id, asked, propose]);

  if (d.isLoading) return <Loading text="Sayfa açılıyor…" />;
  if (d.error) return <Failed error={d.error} />;
  if (!p) return null;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="sg-card">
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', justifyContent: 'space-between' }}>
          <div style={{ minWidth: 0 }}>
            <div className="sg-eyebrow">{KINDS.find((k) => k.id === kind)?.label} · #{p.id}</div>
            <h2 style={{ fontSize: 20, margin: '6px 0' }}>{p.name}</h2>
            <div className="sg-mono" style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
              {fmt(p.facts.books)} aktif kitap · {fmt(p.facts.sales)} satış
            </div>
            <a href={p.url} target="_blank" rel="noreferrer" className="sg-mono" style={{ fontSize: 11.5, display: 'inline-flex', gap: 4, marginTop: 6 }}>
              Sayfayı aç <ExternalLink size={12} aria-hidden />
            </a>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="sg-kpi-label">Puan</div>
            <div className="sg-kpi-value sg-mono">
              {p.score}
              <small>/100</small>
            </div>
            {open?.scoreAfter != null && <div className="sg-kpi-note">Öneriyle {open.scoreAfter}</div>}
          </div>
        </div>
        <div style={{ marginTop: 12, display: 'grid', gap: 6, fontSize: 12.5 }}>
          {p.facts.top.length > 0 && (
            <div>
              <b>Öne çıkan kitaplar:</b> {p.facts.top.slice(0, 6).map((t) => t.name).join(' · ')}
            </div>
          )}
          {p.facts.cats.length > 0 && (
            <div>
              <b>Kategoriler:</b> {p.facts.cats.join(' · ')}
            </div>
          )}
          {kind === 'model' && (
            <div>
              <b>Wikidata:</b>{' '}
              {p.facts.wikidata?.wikidata ? (
                <a href={p.facts.wikidata.wikidata} target="_blank" rel="noreferrer">
                  {p.facts.wikidata.description || 'kayıt'} <ExternalLink size={11} aria-hidden />
                </a>
              ) : (
                <span style={{ color: 'var(--sg-muted)' }}>doğrulanmış kayıt yok — tanıtım yalnız kitaplardan yazılır</span>
              )}
            </div>
          )}
        </div>
      </div>
      {p.issues.length === 0 ? (
        <p className="sg-banner ok">Bu sayfa kurallara uyuyor.</p>
      ) : (
        <Review key={open?.id ?? 'bekliyor'} page={p} proposal={open} pending={propose.isPending} error={propose.error}
          canApprove={!!me.data?.canApprove} onRegenerate={() => propose.mutate()} onDone={refresh} />
      )}
      {last && (
        <p className={`sg-banner ${last.status === 'onaylandi' ? 'ok' : ''}`}>
          <b>{STATUS_LABEL[last.status]}</b> · {last.decidedBy ?? '—'} · {dateTime(last.decidedAt)}
          {last.result ? ` — ${last.result}` : ''}
        </p>
      )}
    </div>
  );
}

function Review({ page, proposal, pending, error, canApprove, onRegenerate, onDone }: {
  page: PageDetail;
  proposal: PageDetail['proposals'][number] | undefined;
  pending: boolean;
  error: unknown;
  canApprove: boolean;
  onRegenerate: () => void;
  onDone: () => void;
}) {
  const initial = useMemo(() => ({ SeoTitle: proposal?.fields.SeoTitle ?? '', SeoDescription: proposal?.fields.SeoDescription ?? '', Intro: proposal?.fields.Intro ?? '' }), [proposal]);
  const [fields, setFields] = useState<Record<PageField, string>>(initial);
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') => seoApi.decidePage(proposal!.id, { action, fields: action === 'approve' ? fields : undefined }),
    onSuccess: onDone,
  });
  const L = page.limits;
  const lim: Partial<Record<PageField, [number, number]>> = { SeoTitle: [L.title_min, L.title_max], SeoDescription: [L.meta_min, L.meta_max] };
  const unsupported = proposal?.unsupported ?? [];
  return (
    <div className="sg-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <div>
          <h2>Uyarılar ve Zeki AI önerisi</h2>
          <p className="sg-sub" style={{ margin: 0 }}>{pending ? 'Öneriler yazılıyor…' : proposal ? `Zeki AI · ${dateTime(proposal.createdAt)}` : 'Öneri henüz yok.'}</p>
        </div>
        <button className="sg-button" onClick={onRegenerate} disabled={pending || decide.isPending}>
          {pending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Sparkles size={16} aria-hidden />} Yeniden üret
        </button>
      </div>
      {!!error && <div style={{ marginTop: 12 }}><Failed error={error} /></div>}
      {unsupported.length > 0 && (
        <p className="sg-banner" style={{ marginTop: 12 }}>
          Gerçeklik denetimi: öneride verilen bilgide geçmeyen ifadeler var — <b>{unsupported.join(', ')}</b>. Onaylamadan önce bakın.
        </p>
      )}
      <div className="sg-diff" style={{ marginTop: 16 }}>
        {FIELDS.map(({ id: k, label }) => {
          const issues = page.issues.filter((i) => i.field === k);
          const next = fields[k];
          const range = lim[k];
          const len = k === 'Intro' ? next.split(/\s+/).filter(Boolean).length : next.length;
          const over = range ? len < range[0] || len > range[1] : false;
          if (!issues.length && !next) return null;
          return (
            <section key={k} className="sg-field" aria-label={label}>
              <div className="sg-field-head">
                <span>{label}</span>
                {next && <span className={`sg-mono ${over ? 'over' : ''}`}>{k === 'Intro' ? `${len} kelime` : `${len} / ${range?.[0]}–${range?.[1]} karakter`}</span>}
              </div>
              <div className="sg-fix">
                <div className="sg-fix-why">
                  {issues.map((i) => (
                    <article key={i.rule} className={`sg-issue ${i.severity}`}>
                      <h3>
                        <i className={`sg-dot ${i.severity}`} aria-hidden />
                        {i.title}
                      </h3>
                      <p>{i.detail}</p>
                      <p>{i.why}</p>
                    </article>
                  ))}
                  <p className="sg-tag" style={{ marginTop: 8 }}>MEVCUT</p>
                  <div className={`sg-before ${page.current[k] ? '' : 'empty'}`}>{page.current[k] || 'Boş'}</div>
                </div>
                <div className="sg-fix-new">
                  <p className="sg-tag">ZEKİ AI ÖNERİSİ</p>
                  {pending && !proposal ? (
                    <div className="sg-after sg-skeleton" aria-busy="true">
                      <Loader2 size={14} className="animate-spin" aria-hidden /> Yazılıyor…
                    </div>
                  ) : (
                    <textarea className="sg-after" rows={k === 'Intro' ? 8 : k === 'SeoDescription' ? 4 : 2} value={next}
                      onChange={(e) => setFields({ ...fields, [k]: e.target.value })} aria-label={`${label} önerisi`} />
                  )}
                </div>
              </div>
            </section>
          );
        })}
      </div>
      {proposal && (
        <div className="sg-decide" style={{ marginTop: 16 }}>
          <button className="sg-button primary" disabled={!canApprove || decide.isPending} onClick={() => decide.mutate('approve')}>
            {decide.isPending && decide.variables === 'approve' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />} Onayla
          </button>
          <button className="sg-button danger" disabled={!canApprove || decide.isPending} onClick={() => decide.mutate('reject')}>
            <X size={16} aria-hidden /> Reddet
          </button>
          <small>
            {canApprove
              ? 'Onay yalnız kaydedilir; T-soft’a gönderim yok.'
              : 'Onay yetkiniz yok. Yetki: Yönetim → SEO & GEO → Onay verebilenler.'}
          </small>
          {decide.error && <Failed error={decide.error} />}
        </div>
      )}
    </div>
  );
}
