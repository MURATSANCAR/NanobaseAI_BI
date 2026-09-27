import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { FLAG_LABEL, RIGHTS_LABEL, RIGHTS_TONE, dateTime, fmt, seoApi, type CrmFilter, type CrmRights } from './api';
import CrmPanel from './CrmPanel';
import SeoLayout, { Failed, Loading } from './SeoLayout';

const PAGE = 40;
const RIGHTS_ORDER: CrmRights[] = ['eksik', 'incele', 'yok', 'var', 'koruma_disi'];

/** Haklar ve CRM: T-soft'ta satıştaki kitapların CRM kartı, internette gösterim hakkı ve yayın durumu.
 *  Google Kitaplar önizlemesi, tadımlık PDF ve SEO önceliği bu bilgiye bağlıdır. CRM'e yazılmaz. */
export default function SeoRights() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const filter = (params.get('suzgec') ?? '') as CrmFilter | '';
  const selected = params.get('urun') ?? '';
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [filter, query]);

  const list = useQuery({
    queryKey: ['seo-crm', filter, query, start],
    queryFn: () => seoApi.crm({ filter, q: query, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (prev) => prev,
    refetchInterval: (s) => (s.state.data?.summary.state.running ? 10000 : false),
  });
  const read = useMutation({ mutationFn: seoApi.crmSync, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-crm'] }) });
  const detail = useQuery({
    queryKey: ['seo-product', selected],
    queryFn: () => seoApi.product(selected),
    enabled: ENGINE_ENABLED && !!selected,
    retry: false,
  });

  const set = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key === 'suzgec') next.delete('urun');
    setParams(next, { replace: true });
  };

  const s = list.data?.summary;
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;
  const flagged = Object.values(s?.flags ?? {}).reduce((a, n) => a + (n ?? 0), 0);
  const running = !!s?.state.running;

  return (
    <SeoLayout
      path="/seo-geo/crm-haklar"
      crumb="Haklar ve CRM"
      eyebrow="SEO & GEO · CRM kitap kartı"
      title="Haklar ve CRM"
      lead="T-soft’ta satıştaki her kitabın CRM kartı: internette gösterim hakkı (Google Kitaplar önizlemesi, tadımlık PDF), yayın durumu ve SEO’ya kaynak olabilecek bilgiler. CRM’den yalnız okunur. Hak kararı ön süzgeçtir; kesin söz telif biriminindir."
      actions={
        <button className="sg-button" onClick={() => read.mutate()} disabled={read.isPending || running}>
          {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
          {running ? 'CRM okunuyor (1–2 dk)' : 'CRM’den yeniden oku'}
        </button>
      }
    >
      {list.isLoading && <Loading text="CRM kartları getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {read.error && <Failed error={read.error} />}
      {s?.state.error && <p className="sg-banner err">Son CRM okuması başarısız: {s.state.error}</p>}

      {s && !s.books && !running && (
        <div className="sg-empty">
          <h2>CRM henüz okunmadı</h2>
          <p>“CRM’den yeniden oku”ya basın ya da gece işini bekleyin. Okuma yalnız SELECT’tir; CRM’de hiçbir şey değişmez.</p>
        </div>
      )}

      {s && s.books > 0 && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Satıştaki kitap" value={fmt(s.products)} note={`CRM kartıyla eşleşmeyen ${fmt(s.unmatched)} · son okuma ${dateTime(s.lastRead)}`} />
            <Kpi label="Hak var" value={fmt(s.rights?.var)} note="Bütün telif alış sözleşmelerinde internet hakkı" tone="good" />
            <Kpi label="Hak eksik ya da incelenmeli" value={fmt((s.rights?.eksik ?? 0) + (s.rights?.incele ?? 0))} note={`Eksik ${fmt(s.rights?.eksik)} · hak notu var ${fmt(s.rights?.incele)}`} tone="bad" />
            <Kpi label="Sözleşme kaydı yok" value={fmt(s.rights?.yok)} note="CRM’de yürürlükte telif alış sözleşmesi bağlı değil" />
            <Kpi label="Bizim değil / çekildi" value={fmt(flagged)} note="CRM yayın durumu; sitede hâlâ satışta" tone={flagged ? 'bad' : undefined} />
          </section>

          <div className="sg-filters" role="toolbar" aria-label="Süzgeç">
            <Chip on={!filter} onClick={() => set('suzgec', '')} label="Tümü" n={s.products} />
            <Chip on={filter === 'durum'} onClick={() => set('suzgec', filter === 'durum' ? '' : 'durum')} label="Bizim değil / çekildi" n={flagged} />
            {RIGHTS_ORDER.map((r) => (
              <Chip key={r} on={filter === r} onClick={() => set('suzgec', filter === r ? '' : r)} label={RIGHTS_LABEL[r]} n={s.rights?.[r]} />
            ))}
            <Chip on={filter === 'eslesmedi'} onClick={() => set('suzgec', filter === 'eslesmedi' ? '' : 'eslesmedi')} label="CRM’de eşleşmeyen" n={s.unmatched} />
            <Chip on={filter === 'onizleme'} onClick={() => set('suzgec', filter === 'onizleme' ? '' : 'onizleme')} label="Tadımlık PDF var" n={s.preview} />
            <Chip on={filter === 'video'} onClick={() => set('suzgec', filter === 'video' ? '' : 'video')} label="Videosu var" n={s.video} />
          </div>

          <div className="sg-audit">
            <section className="sg-card" aria-label="Kitaplar">
              <label className="sg-search" style={{ marginBottom: 12 }}>
                <Search size={16} aria-hidden />
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, ürün kodu ya da yayınevi" aria-label="Kitap ara" />
              </label>
              {list.data && !items.length && (
                <div className="sg-empty">
                  <h2>Kitap yok</h2>
                  <p>Bu süzgece uyan kitap bulunamadı.</p>
                </div>
              )}
              <div className="sg-list">
                {items.map((p) => (
                  <button key={p.id} className="sg-item" aria-current={selected === p.id} onClick={() => set('urun', p.id)}>
                    {p.image ? <img src={p.image} alt="" loading="lazy" /> : <span className="sg-noimg" aria-hidden />}
                    <span style={{ minWidth: 0 }}>
                      <span className="sg-item-name">{p.name || p.code}</span>
                      <span className="sg-item-meta sg-mono">
                        {fmt(p.sales)} satış{p.crm?.previewPdf ? ' · tadımlık PDF' : ''}{p.crm?.video ? ' · video' : ''}
                      </span>
                    </span>
                    <span className="sg-item-side">
                      {p.crm ? (
                        <span className={`sg-chip ${RIGHTS_TONE[p.crm.rights]}`}>{RIGHTS_LABEL[p.crm.rights]}</span>
                      ) : (
                        <span className="sg-chip">CRM’de yok</span>
                      )}
                      {p.crm?.statusFlag && <span className="sg-chip bad">{FLAG_LABEL[p.crm.statusFlag]}</span>}
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
              {!selected && (
                <div className="sg-empty">
                  <h2>Bir kitap seçin</h2>
                  <p>Soldaki listeden bir kitap seçtiğinizde telif sözleşmeleri, internette gösterim hakkı ve CRM’deki SEO bilgileri burada açılır.</p>
                </div>
              )}
              {selected && detail.isLoading && <Loading text="Kitap açılıyor…" />}
              {selected && detail.error && <Failed error={detail.error} />}
              {detail.data && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <CrmPanel book={detail.data.crm} tsoft={{ words: detail.data.details.words, hasMeta: !!detail.data.current.SeoDescription }} />
                  <Link className="sg-button" style={{ alignSelf: 'flex-start' }} to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(detail.data.id)}`}>
                    Ürün denetiminde aç
                  </Link>
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </SeoLayout>
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
