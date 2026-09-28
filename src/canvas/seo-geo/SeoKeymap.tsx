import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Check, ChevronLeft, ChevronRight, Download, ExternalLink, Search } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { useCan } from '../useAdmin';
import { call, dateTime, fmt, qs, seoApi } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';

/** Sorgu–sayfa eşlemesi: /api/v1/seo-geo/keymap. Search Console'un sorgu+sayfa kırılımından; her önemli arama için
 *  hedef sayfa, yanlış sıralanan sayfa ve sayfamızın olmadığı aramalar. Karar yalnız kaydedilir. */

type Kind = 'eslesme' | 'yanlis' | 'bosluk';
type Intent = 'kitap' | 'yazar' | 'kategori' | 'bilgi' | 'marka' | 'diger';
type PageRef = { url: string | null; type: string | null; typeLabel: string | null; name: string | null; id: string | null };
type Item = {
  query: string;
  brand: boolean;
  impressions: number;
  clicks: number;
  intent: Intent;
  intentLabel: string;
  ranking: PageRef & { clicks: number; impressions: number; position: number };
  pages: Array<PageRef & { clicks: number; impressions: number; position: number }>;
  kind: Kind;
  target: PageRef | null;
  reason: string;
  decision: { status: 'onaylandi' | 'reddedildi'; target: string | null; suggested: string | null; note: string | null; decidedBy: string | null; decidedAt: string | null } | null;
};
type Keymap = {
  kind: Kind | 'hepsi';
  brand: string;
  start: number;
  total: number;
  ready: boolean;
  connected: boolean;
  reason: string | null;
  source: { from: 'query_page' | 'queries' | null; start: string | null; end: string | null; savedAt: string | null; rowCount: number };
  totals: Record<Kind, { all: number; brand: number; nonBrand: number; impressions: number }>;
  counts: Record<Kind, number>;
  kinds: Array<{ id: Kind; label: string }>;
  decided: { onaylandi: number; reddedildi: number };
  thresholds: { minImpressions: number };
  items: Item[];
};

const PAGE = 50;
const KIND_TONE: Record<Kind, string> = { eslesme: 'good', yanlis: 'bad', bosluk: 'mid' };
const api = {
  list: (p: { kind: string; brand: string; q: string; start: number; limit: number }) => call<Keymap>(`keymap?${qs(p)}`),
  decide: (body: { query: string; target: string; note: string; action: 'approve' | 'reject' }) => call<Item>('keymap/decide', { method: 'POST', body }),
  csv: (brand: string) => `${ENGINE_BASE}/api/v1/seo-geo/keymap/export.csv${brand ? `?brand=${brand}` : ''}`,
};
const day = (iso: string | null | undefined) =>
  iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';
const pathOf = (url: string | null) => {
  if (!url) return '—';
  try {
    const u = new URL(url, 'https://timas.com.tr');
    return decodeURIComponent(u.pathname + u.search) || url;
  } catch {
    return url;
  }
};

export default function SeoKeymap() {
  const canExport = useCan('veri.disa-aktar');
  const [kind, setKind] = useState<Kind | 'hepsi'>('yanlis');
  const [brand, setBrand] = useState('0');
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(q);
      setStart(0);
    }, 300);
    return () => clearTimeout(t);
  }, [q]);
  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const r = useQuery({
    queryKey: ['seo-keymap', kind, brand, query, start],
    queryFn: () => api.list({ kind, brand, q: query, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const d = r.data;
  const count = (k: Kind) => (d ? (brand === '1' ? d.totals[k].brand : brand === '0' ? d.totals[k].nonBrand : d.totals[k].all) : undefined);
  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setStart(0);
  };

  return (
    <SeoLayout k={r.data?.kaynaklar}
      path="/seo-geo/sorgu-sayfa"
      crumb="Sorgu–sayfa eşlemesi"
      eyebrow="SEO & GEO · Search Console"
      title="Sorgu–sayfa eşlemesi"
      lead="Her önemli Google araması için hangi sayfamızın öne çıkması gerektiği: kitap araması kitabın sayfasına, yazar araması yazar sayfasına, soru ve liste araması rehber ya da liste sayfasına. Başka bir sayfa sıralanıyorsa ya da uyan sayfamız yoksa burada görünür. Son 28 günün Search Console verisinden; karar yalnız kaydedilir."
      actions={
        canExport && d?.ready ? (
          <a className="sg-button" href={api.csv(brand)}>
            <Download size={16} aria-hidden /> Listeyi indir (CSV)
          </a>
        ) : undefined
      }
    >
      <p style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
        {d?.source.savedAt ? `Son okuma ${dateTime(d.source.savedAt)} · ${day(d.source.start)} – ${day(d.source.end)}` : 'Henüz okuma yok'}
        {d && ` · En az ${fmt(d.thresholds.minImpressions)} gösterimli aramalar`}
      </p>
      {r.isLoading && <Loading text="Aramalar sayfalarla eşleniyor…" />}
      {r.error && <Failed error={r.error} />}
      {d && !d.ready ? (
        <div className="sg-empty">
          <h2>{d.connected ? 'Sayfa kırılımı henüz yok' : 'Search Console bağlı değil'}</h2>
          <p>{d.reason}</p>
        </div>
      ) : (
        d && (
          <>
            <section className="sg-kpis" aria-label="Özet">
              <Kpi label="Yanlış sayfa sıralanıyor" value={fmt(d.totals.yanlis.nonBrand)} note={`Marka dışı · ${fmt(d.totals.yanlis.impressions)} gösterim`} info={<SeoInfo k={r.data?.kaynaklar} label="Yanlış sayfa sıralanıyor" />} />
              <Kpi label="Sayfamız yok" value={fmt(d.totals.bosluk.nonBrand)} note={`Marka dışı · ${fmt(d.totals.bosluk.impressions)} gösterim`} info={<SeoInfo k={r.data?.kaynaklar} label="Sayfamız yok" />} />
              <Kpi label="Doğru sayfa" value={fmt(d.totals.eslesme.nonBrand)} note="Aramaya uyan sayfa öne çıkıyor" info={<SeoInfo k={r.data?.kaynaklar} label="Doğru sayfa" />} />
              <Kpi label="Karar verilen" value={fmt(d.decided.onaylandi + d.decided.reddedildi)} note={`${fmt(d.decided.onaylandi)} onay · ${fmt(d.decided.reddedildi)} ret`} info={<SeoInfo k={r.data?.kaynaklar} label="Karar verilen" />} />
            </section>

            <div className="sg-filters" role="toolbar" aria-label="Durum">
              {(['yanlis', 'bosluk', 'eslesme'] as Kind[]).map((k) => (
                <Chip key={k} on={kind === k} onClick={() => reset(setKind)(k)} label={d.kinds.find((x) => x.id === k)?.label ?? k} n={count(k)} />
              ))}
              <Chip on={kind === 'hepsi'} onClick={() => reset(setKind)('hepsi')} label="Hepsi" />
              <span style={{ width: 8 }} aria-hidden />
              <Chip on={brand === '0'} onClick={() => reset(setBrand)('0')} label="Marka dışı" />
              <Chip on={brand === '1'} onClick={() => reset(setBrand)('1')} label="Marka araması" />
              <Chip on={brand === ''} onClick={() => reset(setBrand)('')} label="Hepsi" />
            </div>
            <label className="sg-search">
              <Search size={16} aria-hidden />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Arama ya da adres ara" aria-label="Arama ya da adres ara" />
            </label>

            <section className="sg-card">
              <h2>{kind === 'hepsi' ? 'Bütün aramalar' : d.kinds.find((x) => x.id === kind)?.label}</h2>
              <p className="sg-sub">
                Sıralanan sayfa, aramada en çok tıklanan adresimizdir. Aramanın türü adından çıkarılır: sitedeki kitap adları, yazarlar ve kategoriler; “en iyi”,
                “önerileri”, “okunması gereken” gibi kalıplar soru/liste araması sayılır. Sitede hiç ürünü olmayan kitap ya da yazar tanınmaz. Gösterime göre sıralı.
              </p>
              {!d.items.length ? (
                <div className="sg-empty">
                  <h2>Bu süzgeçte arama yok</h2>
                  <p>Durum ya da marka süzgecini değiştirmeyi deneyin.</p>
                </div>
              ) : (
                <div className="sg-list">
                  {d.items.map((i) => (
                    <QueryRow key={i.query} i={i} canApprove={!!me.data?.canApprove} />
                  ))}
                </div>
              )}
              <Pager start={start} total={d.total} onChange={setStart} />
            </section>
          </>
        )
      )}
    </SeoLayout>
  );
}

function QueryRow({ i, canApprove }: { i: Item; canApprove: boolean }) {
  const qc = useQueryClient();
  const [target, setTarget] = useState(i.decision?.target ?? i.target?.url ?? '');
  const [note, setNote] = useState(i.decision?.note ?? '');
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') => api.decide({ query: i.query, target: target.trim(), note, action }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-keymap'] }),
  });
  const dec = i.decision;
  const same = i.target?.url && i.ranking.url && pathOf(i.target.url) === pathOf(i.ranking.url);

  return (
    <article style={{ border: '1px solid var(--sg-line)', borderRadius: 16, padding: 14, minWidth: 0 }}>
      <header style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0, fontSize: 14, color: 'var(--sg-ink)', overflowWrap: 'anywhere' }}>
          “{i.query}” {i.brand && <span className="sg-chip violet">Marka</span>}
        </h3>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', fontSize: 12 }}>
          <span className="sg-chip">{i.intentLabel}</span>
          <span className={`sg-chip ${KIND_TONE[i.kind]}`}>{i.kind === 'eslesme' ? 'Doğru sayfa' : i.kind === 'yanlis' ? 'Yanlış sayfa' : 'Sayfamız yok'}</span>
          <span className="sg-mono" style={{ color: 'var(--sg-muted)' }}>
            {fmt(i.impressions)} gösterim · {fmt(i.clicks)} tıklama
          </span>
        </div>
      </header>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'stretch', marginTop: 10 }}>
        <PageBox title="Sıralanan" p={i.ranking} extra={`${fmt(i.ranking.clicks)} tıklama · sıra ${fmt(i.ranking.position, 1)}`} />
        {!same && (
          <>
            <ArrowRight size={18} aria-hidden style={{ alignSelf: 'center', color: 'var(--sg-muted)', flex: 'none' }} />
            {i.target ? <PageBox title="Önerilen hedef" p={i.target} tone="good" /> : <div style={boxStyle('mid')}><strong style={{ fontSize: 12 }}>Uyan sayfamız yok</strong></div>}
          </>
        )}
      </div>
      <p style={{ margin: '8px 0 0', fontSize: 12.5, lineHeight: 1.5, color: 'var(--sg-text)' }}>{i.reason}</p>
      {i.kind === 'bosluk' && i.intent === 'bilgi' && (
        <p style={{ margin: '4px 0 0', fontSize: 12 }}>
          <Link to="/seo-geo/rehberler">Rehber taslağı iste</Link>
        </p>
      )}
      {i.pages.length > 1 && (
        <details style={{ marginTop: 6, fontSize: 12 }}>
          <summary style={{ cursor: 'pointer', color: 'var(--sg-muted)' }}>Bu aramada görünen {fmt(i.pages.length)} adresimiz</summary>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {i.pages.map((p) => (
              <li key={p.url ?? ''} className="sg-mono" style={{ overflowWrap: 'anywhere' }}>
                {pathOf(p.url)} · {p.typeLabel} · {fmt(p.impressions)} gösterim · {fmt(p.clicks)} tıklama · sıra {fmt(p.position, 1)}
              </li>
            ))}
          </ul>
        </details>
      )}

      {dec && (
        <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--sg-muted)' }}>
          <span className={`sg-chip ${dec.status === 'onaylandi' ? 'good' : ''}`}>{dec.status === 'onaylandi' ? 'Onaylandı' : 'Reddedildi'}</span>{' '}
          {dec.target ? `${pathOf(dec.target)} · ` : ''}
          {dec.decidedBy} · {dateTime(dec.decidedAt)}
          {dec.note ? ` · “${dec.note}”` : ''}
        </p>
      )}
      {canApprove && (
        <div className="sg-decide" style={{ position: 'static', marginTop: 10 }}>
          <input className="sg-mono" value={target} onChange={(e) => setTarget(e.target.value)} placeholder="Hedef adres (ör. /yazar-adi)" aria-label="Hedef adres" />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (isteğe bağlı)" aria-label="Not" maxLength={1000} />
          <button className="sg-button primary" disabled={decide.isPending || !target.trim()} onClick={() => decide.mutate('approve')}>
            <Check size={16} aria-hidden /> Hedefi onayla
          </button>
          <button className="sg-button danger" disabled={decide.isPending} onClick={() => decide.mutate('reject')}>
            Reddet
          </button>
          {decide.error && <small style={{ color: '#9b1c24' }}>{(decide.error as Error).message}</small>}
        </div>
      )}
    </article>
  );
}

const boxStyle = (tone?: string) =>
  ({
    flex: '1 1 220px',
    minWidth: 0,
    borderRadius: 12,
    padding: '8px 10px',
    background: tone === 'good' ? '#e9f9f2' : tone === 'mid' ? '#fff5e7' : 'var(--sg-soft)',
    display: 'flex',
    flexDirection: 'column',
    gap: 2,
  }) as const;

function PageBox({ title, p, extra, tone }: { title: string; p: PageRef; extra?: string; tone?: string }) {
  return (
    <div style={boxStyle(tone)}>
      <span style={{ fontSize: 11, color: 'var(--sg-muted)', fontWeight: 700 }}>
        {title}
        {p.typeLabel ? ` · ${p.typeLabel}` : ''}
      </span>
      {p.type === 'product' && p.id ? (
        <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(p.id)}`} style={{ fontSize: 13, fontWeight: 700, overflowWrap: 'anywhere' }}>
          {p.name || pathOf(p.url)}
        </Link>
      ) : (
        p.name && <strong style={{ fontSize: 13, overflowWrap: 'anywhere' }}>{p.name}</strong>
      )}
      <span className="sg-mono" style={{ fontSize: 11.5, overflowWrap: 'anywhere', color: 'var(--sg-muted)' }}>
        {pathOf(p.url)}{' '}
        {p.url && (
          <a href={p.url.startsWith('http') ? p.url : `https://timas.com.tr${p.url}`} target="_blank" rel="noreferrer" aria-label="Sayfayı aç">
            <ExternalLink size={11} aria-hidden />
          </a>
        )}
      </span>
      {extra && <span style={{ fontSize: 11, color: 'var(--sg-muted)' }}>{extra}</span>}
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

function Kpi({ label, value, note, info }: { label: string; value: string; note: string; info?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}</div>
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
