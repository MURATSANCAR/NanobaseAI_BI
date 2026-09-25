import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, ExternalLink, Loader2, Search, Sparkles, X } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import {
  FIELD_LABEL, SEO_FIELDS, STATUS_LABEL, dateTime, fmt, scoreTone, seoApi,
  type Fields, type ProductDetail, type Proposal, type SeoField,
} from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

const PAGE = 30;
const plain = (html: string) => html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();

/** Ürün denetimi ve onay: solda süzülen ürünler, sağda seçilen ürünün sorunları, model önerisi ve karar. */
export default function SeoAudit() {
  const [params, setParams] = useSearchParams();
  const rule = params.get('kural') ?? '';
  const status = params.get('durum') ?? '';
  const selected = params.get('urun') ?? '';
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  const order = (params.get('sira') as 'oncelik' | 'score' | null) ?? 'oncelik';

  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [rule, status, query, order]);

  const overview = useQuery({ queryKey: ['seo-overview'], queryFn: seoApi.overview, enabled: ENGINE_ENABLED, retry: false });
  const list = useQuery({
    queryKey: ['seo-products', rule, status, query, start, order],
    queryFn: () => seoApi.products({ rule, status, q: query, start, limit: PAGE, order }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (prev) => prev,
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };

  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;

  return (
    <SeoLayout
      path="/seo-geo/urun-denetimi"
      crumb="Ürün denetimi"
      eyebrow="SEO & GEO · T-soft ürünleri"
      title="Ürün denetimi ve onay"
      lead="Her ürün kurallardan geçer; neden uyumsuz olduğu yazılır. Zeki AI ürünün kendi kaydından öneri üretir; onay kararı kayıt altına alınır. T-soft’a hiçbir şey gönderilmez."
    >
      <div className="sg-filters" role="toolbar" aria-label="Kural süzgeci">
        <button className="sg-filter" aria-pressed={!rule && !status} onClick={() => setParams(new URLSearchParams(), { replace: true })}>
          Tümü <span className="sg-mono">{fmt(overview.data?.products)}</span>
        </button>
        <button className="sg-filter" aria-pressed={status === 'hazir'} onClick={() => set('durum', status === 'hazir' ? '' : 'hazir')}>
          Onay bekleyen <span className="sg-mono">{fmt(overview.data?.proposals.hazir ?? 0)}</span>
        </button>
        {(overview.data?.rules ?? [])
          .filter((r) => r.count > 0)
          .map((r) => (
            <button key={r.rule} className="sg-filter" aria-pressed={rule === r.rule} onClick={() => set('kural', rule === r.rule ? '' : r.rule)}>
              <i className={`sg-dot ${r.severity}`} aria-hidden />
              {r.title} <span className="sg-mono">{fmt(r.count)}</span>
            </button>
          ))}
      </div>

      {overview.data && !overview.data.connections.tsoft && (
        <p className="sg-banner">
          T-soft bağlantısı tanımlı değil. <Link to="/seo-geo/baglantilar">Bağlantılar</Link> ekranından kurun.
        </p>
      )}

      <div className="sg-audit">
        <section className="sg-card" aria-label="Ürünler">
          <label className="sg-search" style={{ marginBottom: 8 }}>
            <Search size={16} aria-hidden />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, ürün kodu ya da yayınevi" aria-label="Ürün ara" />
          </label>
          <div className="sg-filters" role="radiogroup" aria-label="Sıralama" style={{ marginBottom: 12 }}>
            <button className="sg-filter" role="radio" aria-checked={order === 'oncelik'} aria-pressed={order === 'oncelik'} onClick={() => set('sira', '')}>
              Önce çok satan
            </button>
            <button className="sg-filter" role="radio" aria-checked={order === 'score'} aria-pressed={order === 'score'} onClick={() => set('sira', 'score')}>
              Önce en düşük puan
            </button>
          </div>
          {list.isLoading && <Loading text="Ürünler getiriliyor…" />}
          {list.error && <Failed error={list.error} />}
          {list.data && !items.length && (
            <div className="sg-empty">
              <h2>Ürün yok</h2>
              <p>{overview.data?.products ? 'Bu süzgece uyan ürün bulunamadı.' : 'T-soft’tan henüz ürün okunmadı.'}</p>
            </div>
          )}
          <div className="sg-list">
            {items.map((p) => (
              <button key={p.id} className="sg-item" aria-current={selected === p.id} onClick={() => set('urun', p.id)}>
                {p.image ? <img src={p.image} alt="" loading="lazy" /> : <span className="sg-noimg" aria-hidden />}
                <span style={{ minWidth: 0 }}>
                  <span className="sg-item-name">{p.name || p.code}</span>
                  <span className="sg-item-meta sg-mono">
                    {fmt(p.sales)} satış · {fmt(p.views)} görüntülenme · {p.issues.length} sorun
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

        <section aria-label="Seçilen ürün">
          {selected ? (
            <Detail id={selected} />
          ) : (
            <div className="sg-empty">
              <h2>Bir ürün seçin</h2>
              <p>Soldaki listeden bir ürün seçtiğinizde neden uyumsuz olduğu, mevcut alanlar ve modelin önerisi burada açılır.</p>
            </div>
          )}
        </section>
      </div>
    </SeoLayout>
  );
}

function Detail({ id }: { id: string }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const d = useQuery({ queryKey: ['seo-product', id], queryFn: () => seoApi.product(id), enabled: ENGINE_ENABLED, retry: false });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['seo-product', id] });
    qc.invalidateQueries({ queryKey: ['seo-products'] });
    qc.invalidateQueries({ queryKey: ['seo-overview'] });
  };
  const propose = useMutation({ mutationFn: () => seoApi.propose(id), onSuccess: refresh });
  const p = d.data;
  const open = p?.proposals.find((x) => x.status === 'hazir');
  const last = p?.proposals.find((x) => x.status !== 'hazir');
  const needs = !!p && !open && p.issues.some((i) => i.field);

  // Öneri kendiliğinden: ürün açılınca, düzeltilebilir sorun varsa ve bekleyen öneri yoksa bir kez istenir.
  const [asked, setAsked] = useState<string | null>(null);
  useEffect(() => {
    if (needs && asked !== id && !propose.isPending) {
      setAsked(id);
      propose.mutate();
    }
  }, [needs, id, asked, propose]);

  if (d.isLoading) return <Loading text="Ürün açılıyor…" />;
  if (d.error) return <Failed error={d.error} />;
  if (!p) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="sg-card">
        <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          {p.image && <img src={p.image} alt="" style={{ width: 72, height: 100, objectFit: 'cover', borderRadius: 10 }} />}
          <div style={{ flex: '1 1 240px', minWidth: 0 }}>
            <div className="sg-eyebrow">{p.brand || 'T-soft'} · #{p.id}</div>
            <h2 style={{ fontSize: 20, margin: '6px 0' }}>{p.name}</h2>
            <div className="sg-mono" style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
              {p.code}
              {p.barcode ? ` · ISBN ${p.barcode}` : ''} · açıklama {fmt(p.details.words)} kelime
            </div>
            {p.url && (
              <a href={p.url} target="_blank" rel="noreferrer" className="sg-mono" style={{ fontSize: 11.5, display: 'inline-flex', gap: 4, marginTop: 6 }}>
                Sayfayı aç <ExternalLink size={12} aria-hidden />
              </a>
            )}
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="sg-kpi-label">Puan</div>
            <div className="sg-kpi-value sg-mono" style={{ color: p.score >= 80 ? '#0f7a51' : p.score >= 50 ? '#9a5b00' : '#c2361b' }}>
              {p.score}
              <small>/100</small>
            </div>
            {open?.scoreAfter != null && <div className="sg-kpi-note">Öneriyle {open.scoreAfter}</div>}
          </div>
        </div>
      </div>

      {p.issues.length === 0 ? (
        <div className="sg-banner ok">Bu ürün kurallara uyuyor.</div>
      ) : (
        <Review
          key={open?.id ?? 'bekliyor'}
          product={p}
          proposal={open}
          pending={propose.isPending}
          error={propose.error}
          canApprove={!!me.data?.canApprove}
          onDone={refresh}
          onRegenerate={() => propose.mutate()}
        />
      )}

      {last && <LastDecision proposal={last} canApprove={!!me.data?.canApprove} onDone={refresh} />}
    </div>
  );
}

/** Uyarılar alan alan gruplanır; her grubun hemen yanında o alanın mevcut değeri ve modelin önerisi durur.
 *  Modelin düzeltmediği sorunlar (görsel, ISBN) ayrı "elle yapılacak" grubunda. */
function Review({ product, proposal, pending, error, canApprove, onDone, onRegenerate }: {
  product: ProductDetail;
  proposal: Proposal | undefined;
  pending: boolean;
  error: unknown;
  canApprove: boolean;
  onDone: () => void;
  onRegenerate: () => void;
}) {
  const initial = useMemo(() => {
    const o: Fields = {};
    SEO_FIELDS.forEach((k) => (o[k] = proposal?.fields[k] ?? ''));
    return o;
  }, [proposal]);
  const [fields, setFields] = useState<Fields>(initial);
  const [note, setNote] = useState('');
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') => seoApi.decide(proposal!.id, { action, fields: action === 'approve' ? fields : undefined, note }),
    onSuccess: onDone,
  });

  const L = product.limits;
  const limits: Partial<Record<SeoField, [number, number]>> = {
    SeoTitle: [L.title_min, L.title_max],
    SeoDescription: [L.meta_min, L.meta_max],
  };
  const groups = SEO_FIELDS.map((k) => ({ field: k, issues: product.issues.filter((i) => i.field === k) }));
  const manual = product.issues.filter((i) => !i.field);
  const changed = SEO_FIELDS.filter((k) => (fields[k] ?? '').trim() && (fields[k] ?? '').trim() !== (product.current[k] ?? '').trim());
  const title = fields.SeoTitle || product.current.SeoTitle || product.name;
  const desc = fields.SeoDescription || product.current.SeoDescription;
  const unsupported = proposal?.unsupported ?? [];

  return (
    <div className="sg-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', alignItems: 'baseline' }}>
        <div>
          <h2>Uyarılar ve ZEKİ AI önerisi</h2>
          <p className="sg-sub" style={{ margin: 0 }}>
            {pending
              ? 'Öneriler yazılıyor…'
              : proposal
                ? `Zeki AI · ${dateTime(proposal.createdAt)} · değişen alan ${changed.length}. Öneriyi onaylamadan önce düzenleyebilirsiniz.`
                : 'Öneri henüz yok.'}
          </p>
        </div>
        <button className="sg-button" onClick={onRegenerate} disabled={pending || decide.isPending}>
          {pending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Sparkles size={16} aria-hidden />}
          Yeniden üret
        </button>
      </div>
      {!!error && <div style={{ marginTop: 12 }}><Failed error={error} /></div>}
      {unsupported.length > 0 && (
        <p className="sg-banner" style={{ marginTop: 12 }}>
          Gerçeklik denetimi: öneride ürün kaydında geçmeyen ifadeler var — <b>{unsupported.join(', ')}</b>. Onaylamadan önce doğru olduklarına bakın.
        </p>
      )}

      <div className="sg-diff" style={{ marginTop: 16 }}>
        {groups
          .filter((g) => g.issues.length || changed.includes(g.field))
          .map(({ field: k, issues }) => {
            const now = product.current[k] ?? '';
            const next = fields[k] ?? '';
            const lim = limits[k];
            const len = k === 'Details' ? plain(next).split(/\s+/).filter(Boolean).length : next.length;
            const over = lim ? len < lim[0] || len > lim[1] : k === 'Details' ? len < L.desc_min_words : false;
            return (
              <section key={k} className="sg-field" aria-label={FIELD_LABEL[k]}>
                <div className="sg-field-head">
                  <span>{FIELD_LABEL[k]}</span>
                  {next && (
                    <span className={`sg-mono ${over ? 'over' : ''}`}>
                      {k === 'Details' ? `${fmt(len)} kelime · en az ${fmt(L.desc_min_words)}` : lim ? `${len} / ${lim[0]}–${lim[1]} karakter` : `${len} karakter`}
                    </span>
                  )}
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
                    <div className={`sg-before ${now ? '' : 'empty'}`}>{now ? (k === 'Details' ? plain(now) : now) : 'Boş'}</div>
                  </div>
                  <div className="sg-fix-new">
                    <p className="sg-tag">ZEKİ AI ÖNERİSİ</p>
                    {pending && !proposal ? (
                      <div className="sg-after sg-skeleton" aria-busy="true">
                        <Loader2 size={14} className="animate-spin" aria-hidden /> Yazılıyor…
                      </div>
                    ) : (
                      <textarea
                        className="sg-after"
                        rows={k === 'Details' ? 12 : k === 'SeoDescription' ? 4 : 2}
                        value={next}
                        onChange={(e) => setFields({ ...fields, [k]: e.target.value })}
                        placeholder={proposal ? 'Bu alan için öneri yok' : 'Öneri bekleniyor'}
                        aria-label={`${FIELD_LABEL[k]} önerisi`}
                      />
                    )}
                  </div>
                </div>
              </section>
            );
          })}

        {manual.length > 0 && (
          <section className="sg-field" aria-label="Elle yapılacaklar">
            <div className="sg-field-head">
              <span>Elle yapılacaklar</span>
            </div>
            <div className="sg-issues">
              {manual.map((i) => (
                <article key={i.rule} className={`sg-issue ${i.severity}`}>
                  <h3>
                    <i className={`sg-dot ${i.severity}`} aria-hidden />
                    {i.title}
                  </h3>
                  <p>{i.detail}</p>
                  <p>Model bunu üretemez; CRM ya da T-soft kaydında düzeltilmeli.</p>
                </article>
              ))}
            </div>
          </section>
        )}
      </div>

      {proposal && (
        <>
          <p className="sg-tag" style={{ marginTop: 16 }}>GOOGLE’DA GÖRÜNÜŞÜ (YAKLAŞIK)</p>
          <div className="sg-snippet">
            <div className="u">{product.url ?? 'timas.com.tr'}</div>
            <div className="t">{title}</div>
            <div className="d">{desc || 'Meta açıklama yok; Google sayfadan kendisi bir parça seçer.'}</div>
          </div>

          {decide.error && <div style={{ marginTop: 12 }}><Failed error={decide.error} /></div>}
          <div className="sg-decide" style={{ marginTop: 16 }}>
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Editör notu (isteğe bağlı)" aria-label="Editör notu" />
            <button className="sg-button primary" disabled={!canApprove || decide.isPending || changed.length === 0} onClick={() => decide.mutate('approve')}>
              {decide.isPending && decide.variables === 'approve' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Check size={16} aria-hidden />}
              Onayla
            </button>
            <button className="sg-button danger" disabled={!canApprove || decide.isPending} onClick={() => decide.mutate('reject')}>
              <X size={16} aria-hidden /> Reddet
            </button>
            <small>
              {canApprove
                ? 'Onay yalnız kaydedilir; T-soft’a gönderim yok. Onaylanan metin CRM bağlantısı gelince CRM’e yazılacak.'
                : 'Onay yetkiniz yok; öneriyi görebilir ve yeniden ürettirebilirsiniz. Yetki: Yönetim → SEO & GEO → Onay verebilenler.'}
            </small>
          </div>
        </>
      )}
    </div>
  );
}

function LastDecision({ proposal }: { proposal: Proposal; canApprove?: boolean; onDone?: () => void }) {
  const tone = proposal.status === 'onaylandi' || proposal.status === 'gonderildi' ? 'ok' : proposal.status === 'hata' ? 'err' : '';
  return (
    <div className={`sg-banner ${tone}`}>
      <b>{STATUS_LABEL[proposal.status]}</b> · {proposal.decidedBy ?? '—'} · {dateTime(proposal.decidedAt)}
      {proposal.result ? ` — ${proposal.result}` : ''}
    </div>
  );
}
