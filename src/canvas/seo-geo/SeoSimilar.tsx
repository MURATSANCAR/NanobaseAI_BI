import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, ChevronLeft, ChevronRight, Download, ExternalLink, RefreshCw, Search, X } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { useCan } from '../useAdmin';
import { call, dateTime, fmt, qs, seoApi } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

/** Benzer kitaplar: /api/v1/seo-geo/similar. CRM emsal bağları + tema/yaş + yazar/dizi → kitap sayfasından verilecek
 *  «ilgili ürünler» bağlantıları. Karar yalnız kaydedilir; onaylananlar CSV ile T-soft'a elle girilir. */

type View = 'eklenecek' | 'yetimler' | 'hepsi';
type Tier = 'emsal' | 'tema' | 'yazar' | 'dizi' | 'elle' | 'anlam';
type Suggestion = {
  id: string;
  code: string | null;
  name: string | null;
  url: string;
  author: string | null;
  sales: number;
  reason: Tier;
  reasonText: string;
  /** true: sayfada zaten bağlantı var; false: yok; null: kaynak sayfa taranmadı. */
  linked: boolean | null;
  inlinks: number | null;
  orphan: boolean;
  weak: boolean;
};
/** Kurala ek aday: kitap benzerliği dizininde özeti anlamca yakın, satıştaki kitaplar (sıra; puan yok). */
type Meaning = {
  hazir: boolean;
  not?: string | null;
  kaynak?: string;
  items: Array<{ id: string; code: string | null; name: string | null; url: string; author: string | null; sales: number; reasonText: string; sira: number }>;
};
type Decision = {
  status: 'onaylandi' | 'reddedildi';
  targets: Array<Pick<Suggestion, 'id' | 'code' | 'name' | 'url' | 'reason' | 'reasonText' | 'linked'>>;
  note: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
  /** Karardan sonra öneri listesi değişti. */
  changed: boolean;
};
type Row = {
  id: string;
  code: string | null;
  name: string | null;
  url: string;
  author: string | null;
  sales: number;
  crawled: boolean | null;
  suggestions: Suggestion[];
  excluded: Array<{ id: string; name: string | null; why: 'baski' | 'set' }>;
  emsalTotal: number;
  toAdd: number;
  unknown: number;
  alreadyLinked: number;
  orphanTargets: number;
  weakTargets: number;
  decision: Decision | null;
};
type Similar = {
  view: View;
  views: Record<View, string>;
  start: number;
  total: number;
  counts: Record<View, number>;
  ready: boolean;
  reason: string | null;
  crmReady: boolean;
  state: { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null; partial: Record<string, string> | null };
  tiers: Array<{ id: Tier; label: string }>;
  decisions: { onaylandi: number; reddedildi: number };
  summary: {
    perBook: number;
    eligible: number;
    withSuggestions: number;
    emsalLinks: number;
    emsalOnSale: number;
    tiers: Record<Exclude<Tier, 'elle' | 'anlam'>, number>;
    excluded: { baski: number; set: number };
    graphKnown: boolean;
    crawledSources: number;
    toAdd: number;
    alreadyLinked: number;
    orphanTargets: number;
    weakInlinks: number;
    lastRead: string | null;
    computedAt: string | null;
  };
  items: Row[];
};

const PAGE = 30;
const TIER_TONE: Record<Tier, string> = { emsal: 'violet', tema: 'good', yazar: '', dizi: '', elle: 'mid', anlam: 'mid' };
const TIER_SHORT: Record<Tier, string> = { emsal: 'Emsal', tema: 'Tema', yazar: 'Yazar', dizi: 'Dizi', elle: 'Elle', anlam: 'Anlam' };

const api = {
  list: (p: { view: View; q: string; start: number; limit: number }) => call<Similar>(`similar?${qs(p)}`),
  refresh: () => call<{ started: boolean }>('similar/refresh', { method: 'POST' }),
  decide: (id: string, body: { action: 'approve' | 'reject'; targets: string[]; note: string }) =>
    call<Row>(`similar/${encodeURIComponent(id)}/decide`, { method: 'POST', body }),
  csv: () => `${ENGINE_BASE}/api/v1/seo-geo/similar/export.csv`,
  one: (id: string) => call<{ meaning?: Meaning }>(`similar/${encodeURIComponent(id)}`),
};

export default function SeoSimilar() {
  const canRun = useCan('seo.calistir');
  const canExport = useCan('veri.disa-aktar');
  const qc = useQueryClient();
  const [view, setView] = useState<View>('eklenecek');
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
    queryKey: ['seo-similar', view, query, start],
    queryFn: () => api.list({ view, q: query, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (x) => (x.state.data?.state.running ? 5000 : false),
  });
  const refresh = useMutation({ mutationFn: api.refresh, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-similar'] }) });
  const d = r.data;
  const s = d?.summary;

  return (
    <SeoLayout
      path="/seo-geo/benzer-kitaplar"
      crumb="Benzer kitaplar"
      eyebrow="SEO & GEO · Site içi bağlantılar"
      title="Benzer kitaplar"
      lead="Her kitap sayfası için «ilgili ürünler» önerisi: önce CRM’de editörün girdiği emsal kitaplar, sonra ortak tema ve yaş, aynı yazar ve aynı dizi. Sayfada zaten bağlantı olanlar ayrılır; hiç bağlantı almayan kitaplara giden öneriler öne alınır. Karar yalnız kaydedilir — onaylananları CSV olarak indirip T-soft’a elle girin."
      actions={
        <>
          {canRun && d?.crmReady && (
            <button className="sg-button" disabled={refresh.isPending || d.state.running} onClick={() => refresh.mutate()}>
              <RefreshCw size={16} aria-hidden className={d.state.running ? 'animate-spin' : undefined} /> {d.state.running ? 'CRM okunuyor…' : 'CRM’den yeniden oku'}
            </button>
          )}
          {canExport && (
            <a className="sg-button" href={api.csv()}>
              <Download size={16} aria-hidden /> Onaylananları indir (CSV)
            </a>
          )}
        </>
      }
    >
      <p style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
        {s?.lastRead ? `CRM bağları son okuma ${dateTime(s.lastRead)}` : 'CRM bağları henüz okunmadı'}
        {s && ` · Kitap başına en çok ${fmt(s.perBook)} öneri`}
      </p>
      {r.isLoading && <Loading text="Öneriler hazırlanıyor…" />}
      {r.error && <Failed error={r.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {d?.state.error && <p className="sg-banner err">Son CRM okuması başarısız: {d.state.error}</p>}
      {d?.state.partial && <p className="sg-banner">Bazı CRM bağları okunamadı ({Object.keys(d.state.partial).join(', ')}); önceki okuma kullanılıyor.</p>}
      {d?.reason && <p className="sg-banner">{d.reason}</p>}
      {d && s && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Öneri çıkan kitap" value={fmt(s.withSuggestions)} note={`Satıştaki ${fmt(s.eligible)} kitaptan`} />
            <Kpi label="Eklenecek bağlantı" value={fmt(s.toAdd)} note={s.graphKnown ? `${fmt(s.alreadyLinked)} öneri sayfada zaten var` : 'Site taraması yok; sayfada olup olmadığı bilinmiyor'} />
            <Kpi label="Yetim kitaba giden" value={fmt(s.orphanTargets)} note="Hiçbir sayfadan bağlantı almayan hedef kitap" />
            <Kpi label="CRM emsal bağı" value={fmt(s.emsalLinks)} note={`${fmt(s.emsalOnSale)} bağda iki kitap da satışta`} />
          </section>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <div className="sg-filters" role="toolbar" aria-label="Görünüm" style={{ flex: '1 1 auto' }}>
              {(Object.keys(d.views) as View[]).map((v) => (
                <button
                  key={v}
                  className="sg-filter"
                  aria-pressed={view === v}
                  onClick={() => {
                    setView(v);
                    setStart(0);
                  }}
                >
                  {d.views[v]} <span className="sg-mono">{fmt(d.counts[v])}</span>
                </button>
              ))}
            </div>
            <label className="sg-search">
              <Search size={16} aria-hidden />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap, kod ya da yazar ara" aria-label="Kitap ara" />
            </label>
          </div>

          <section className="sg-card">
            <h2>{d.views[view]}</h2>
            <p className="sg-sub">
              Sıra: CRM emsal kitap ({fmt(s.tiers.emsal)} öneri) → ortak tema ve yaş ({fmt(s.tiers.tema)}) → aynı yazar ({fmt(s.tiers.yazar)}) → adından aynı dizi (
              {fmt(s.tiers.dizi)}); her basamakta hedefin satışına göre. Aynı kitabın başka baskısı ({fmt(s.excluded.baski)}) ve set bağıyla bağlı kitaplar (
              {fmt(s.excluded.set)}) öneriye girmez. Hedef {fmt(s.weakInlinks)} sayfadan az bağlantı alıyorsa zayıf sayılır.
            </p>
            {!d.items.length ? (
              <div className="sg-empty">
                <h2>Bu görünümde kitap yok</h2>
                <p>{view === 'eklenecek' ? 'Eklenecek bağlantı kalmadı ya da hepsine karar verildi.' : 'Aramayı ya da görünümü değiştirmeyi deneyin.'}</p>
              </div>
            ) : (
              <div className="sg-list">
                {d.items.map((row) => (
                  <Book key={row.id} row={row} perBook={s.perBook} canApprove={!!me.data?.canApprove} />
                ))}
              </div>
            )}
            <Pager start={start} total={d.total} onChange={setStart} />
          </section>
        </>
      )}
    </SeoLayout>
  );
}

function Book({ row, perBook, canApprove }: { row: Row; perBook: number; canApprove: boolean }) {
  const qc = useQueryClient();
  const initial = () => (row.decision?.status === 'onaylandi' ? row.decision.targets.map((t) => t.id) : row.suggestions.map((x) => x.id));
  const [picked, setPicked] = useState<string[]>(initial);
  const [extra, setExtra] = useState('');
  const [note, setNote] = useState(row.decision?.note ?? '');
  useEffect(() => setPicked(initial()), [row.id, row.decision?.decidedAt]); // eslint-disable-line react-hooks/exhaustive-deps
  const decide = useMutation({
    mutationFn: (action: 'approve' | 'reject') => api.decide(row.id, { action, targets: picked, note }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-similar'] }),
  });
  const toggle = (id: string) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  const [showMeaning, setShowMeaning] = useState(false);
  const meaning = useQuery({ queryKey: ['seo-similar-meaning', row.id], queryFn: () => api.one(row.id), enabled: ENGINE_ENABLED && showMeaning, retry: false });
  const meaningItems = meaning.data?.meaning?.items ?? [];
  const manual = picked.filter((id) => !row.suggestions.some((x) => x.id === id) && !meaningItems.some((x) => x.id === id));
  const addExtra = () => {
    const code = extra.trim();
    if (code && !picked.includes(code)) setPicked((p) => [...p, code]);
    setExtra('');
  };
  const dec = row.decision;

  return (
    <article style={{ border: '1px solid var(--sg-line)', borderRadius: 16, padding: 14, minWidth: 0 }}>
      <header style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'baseline', justifyContent: 'space-between' }}>
        <div style={{ minWidth: 0 }}>
          <h3 style={{ margin: 0, fontSize: 14, color: 'var(--sg-ink)', overflowWrap: 'anywhere' }}>
            <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(row.id)}`}>{row.name || row.code || row.id}</Link>{' '}
            <a href={row.url} target="_blank" rel="noreferrer" aria-label="Kitap sayfasını aç">
              <ExternalLink size={12} aria-hidden />
            </a>
          </h3>
          <div style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
            {row.author ? `${row.author} · ` : ''}
            <span className="sg-mono">{row.code}</span> · {fmt(row.sales)} satış
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {row.crawled === false && <span className="sg-chip mid">Sayfa taranmadı</span>}
          {row.toAdd > 0 && <span className="sg-chip bad">{fmt(row.toAdd)} eklenmeli</span>}
          {row.alreadyLinked > 0 && <span className="sg-chip good">{fmt(row.alreadyLinked)} zaten bağlı</span>}
          {dec && <span className={`sg-chip ${dec.status === 'onaylandi' ? 'good' : ''}`}>{dec.status === 'onaylandi' ? 'Onaylandı' : 'Reddedildi'}</span>}
        </div>
      </header>

      {dec && (
        <p style={{ margin: '8px 0 0', fontSize: 12, color: 'var(--sg-muted)' }}>
          {dec.decidedBy} · {dateTime(dec.decidedAt)}
          {dec.note ? ` · “${dec.note}”` : ''}
          {dec.changed && <strong style={{ color: '#9a5b00' }}> · Karardan sonra öneriler değişti; yeniden bakın.</strong>}
        </p>
      )}

      <ul style={{ margin: '10px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {row.suggestions.map((x) => (
          <li key={x.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', background: 'var(--sg-soft)', borderRadius: 12, padding: '8px 10px', minWidth: 0 }}>
            {canApprove && (
              <input
                type="checkbox"
                checked={picked.includes(x.id)}
                onChange={() => toggle(x.id)}
                aria-label={`${x.name ?? x.id} listede`}
                style={{ width: 18, height: 18, marginTop: 2, flex: 'none' }}
              />
            )}
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                <span className={`sg-chip ${TIER_TONE[x.reason]}`}>{TIER_SHORT[x.reason]}</span>
                <a href={x.url} target="_blank" rel="noreferrer" style={{ fontSize: 13, fontWeight: 700, overflowWrap: 'anywhere' }}>
                  {x.name || x.code}
                </a>
                <LinkState s={x} />
                {x.linked !== true && x.orphan && <span className="sg-chip bad">Yetim</span>}
                {x.linked !== true && x.weak && <span className="sg-chip mid">Az bağlantı ({fmt(x.inlinks)})</span>}
              </div>
              <div style={{ fontSize: 11.5, color: 'var(--sg-muted)', marginTop: 2, overflowWrap: 'anywhere' }}>
                {x.reasonText} · <span className="sg-mono">{x.code}</span> · {fmt(x.sales)} satış
              </div>
            </div>
          </li>
        ))}
      </ul>
      <p style={{ margin: '8px 0 0', fontSize: 11.5, color: 'var(--sg-muted)' }}>
        {row.emsalTotal > perBook
          ? `CRM’de satışta ${fmt(row.emsalTotal)} emsal var; kitap başına en çok ${fmt(perBook)} öneri gösterilir, en çok satanlar seçildi.`
          : `Kitap başına en çok ${fmt(perBook)} öneri.`}
        {row.excluded.length > 0 && ` Elenen emsal: ${row.excluded.map((e) => `${e.name ?? e.id} (${e.why === 'baski' ? 'aynı kitabın baskısı' : 'set bağı'})`).join(', ')}.`}
      </p>

      <div style={{ marginTop: 8 }}>
        {!showMeaning ? (
          <button className="sg-button" onClick={() => setShowMeaning(true)}>
            Özeti anlamca yakın kitapları göster
          </button>
        ) : meaning.isLoading ? (
          <small style={{ color: 'var(--sg-muted)' }}>Yükleniyor…</small>
        ) : meaning.error ? (
          <small style={{ color: '#9b1c24' }}>{(meaning.error as Error).message}</small>
        ) : !meaningItems.length ? (
          <small style={{ color: 'var(--sg-muted)' }}>{meaning.data?.meaning?.not ?? 'Kurala ek, anlamca yakın satıştaki kitap bulunamadı.'}</small>
        ) : (
          <>
            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--sg-ink)' }}>Kurala ek aday: özeti anlamca yakın</div>
            <ul style={{ margin: '6px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 6 }}>
              {meaningItems.map((x) => (
                <li key={x.id} style={{ display: 'flex', gap: 10, alignItems: 'flex-start', border: '1px dashed var(--sg-line)', borderRadius: 12, padding: '8px 10px', minWidth: 0 }}>
                  {canApprove && (
                    <input
                      type="checkbox"
                      checked={picked.includes(x.id)}
                      onChange={() => toggle(x.id)}
                      aria-label={`${x.name ?? x.id} listeye ekle`}
                      style={{ width: 18, height: 18, marginTop: 2, flex: 'none' }}
                    />
                  )}
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                      <span className="sg-chip mid">{x.sira}. Anlam</span>
                      <a href={x.url} target="_blank" rel="noreferrer" style={{ fontSize: 13, fontWeight: 700, overflowWrap: 'anywhere' }}>{x.name || x.code}</a>
                    </div>
                    <div style={{ fontSize: 11.5, color: 'var(--sg-muted)', marginTop: 2, overflowWrap: 'anywhere' }}>
                      {x.reasonText} · <span className="sg-mono">{x.code}</span> · {fmt(x.sales)} satış
                    </div>
                  </div>
                </li>
              ))}
            </ul>
            {meaning.data?.meaning?.kaynak && <p style={{ margin: '6px 0 0', fontSize: 11, color: 'var(--sg-muted)' }}>{meaning.data.meaning.kaynak}</p>}
          </>
        )}
      </div>

      {canApprove && (
        <div className="sg-decide" style={{ position: 'static', marginTop: 10 }}>
          {manual.length > 0 && (
            <small>
              Elle eklenen:{' '}
              {manual.map((id) => (
                <button key={id} className="sg-chip" onClick={() => toggle(id)} aria-label={`${id} çıkar`} style={{ border: 0, cursor: 'pointer', marginRight: 4 }}>
                  {id} <X size={10} aria-hidden />
                </button>
              ))}
            </small>
          )}
          <input
            value={extra}
            onChange={(e) => setExtra(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addExtra()}
            placeholder="Ürün kodu ekle"
            aria-label="Listeye ürün kodu ekle"
            className="sg-mono"
            style={{ flex: '0 1 160px' }}
          />
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Not (isteğe bağlı)" aria-label="Not" maxLength={1000} />
          <button className="sg-button primary" disabled={decide.isPending || !picked.length} onClick={() => decide.mutate('approve')}>
            <Check size={16} aria-hidden /> Seçilenleri onayla ({fmt(picked.length)})
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

function LinkState({ s }: { s: Suggestion }) {
  if (s.linked === true) return <span className="sg-chip good">Zaten bağlı</span>;
  if (s.linked === false) return <span className="sg-chip bad">Eklenmeli</span>;
  return <span className="sg-chip">Bilinmiyor</span>;
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
