import type { Kaynaklar } from '../components/sqlInfo';
import type { ReactNode } from 'react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';

/** Yarışan sayfalar: /api/v1/seo-geo/cannibal. Search Console'un sorgu+sayfa kırılımından; yalnız okunur. */

type Severity = 'zararli' | 'izle' | 'baskin';
type PairType = 'kopya' | 'baski' | 'urun_sayfa' | 'sayfa_sayfa' | 'urun_urun' | 'diger';
type Page = {
  url: string;
  primary: boolean;
  clicks: number;
  impressions: number;
  position: number;
  ctr: number;
  share: number;
  clickShare: number | null;
  params: boolean;
  linkType: string | null;
  linkLabel: string | null;
  productId: string | null;
  productName: string | null;
  productActive: boolean | null;
};
type Item = {
  query: string;
  brand: boolean;
  impressions: number;
  clicks: number;
  severity: Severity;
  topShare: number;
  types: PairType[];
  pages: Page[];
  pairs: Array<{ a: string; b: string; type: PairType; why: string; action: string }>;
};
type Cannibal = {
  kind: string;
  brand: string;
  type: string;
  start: number;
  total: number;
  connected: boolean;
  ready: boolean;
  reason: string | null;
  source: { from: 'query_page' | 'queries' | null; start: string | null; end: string | null; savedAt: string | null; rowCount: number };
  totals: { severity: Record<Severity, { all: number; brand: number; nonBrand: number; impressions: number }>; types: Record<PairType, number> };
  items: Item[];
  pairTypes: Array<{ id: PairType; label: string }>;
  thresholds: { minPageImpressions: number; minQueryImpressions: number; dominantShare: number; harmPosition: number; editionSimilarity: number };
};

const cannibal = (p: { kind: string; brand: string; type: string; start: number; limit: number }) => call<Cannibal>(`cannibal?${qs(p)}`);

const PAGE = 50;
const SEV_LABEL: Record<Severity, string> = { zararli: 'Zararlı bölünme', izle: 'İzlenmeli', baskin: 'Bir sayfa baskın' };
const SEV_TONE: Record<Severity, string> = { zararli: 'bad', izle: 'mid', baskin: 'good' };
const pct = (v: number | null | undefined) => (v == null ? '—' : `%${fmt(v * 100)}`);
const day = (iso: string | null | undefined) =>
  iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';
const pathOf = (url: string) => {
  try {
    const u = new URL(url);
    return decodeURIComponent(u.pathname + u.search) || url;
  } catch {
    return url;
  }
};

/** Aynı Google aramasında sitemizin birden çok adresinin gösterim aldığı aramalar: gösterim ve tıklama bölünür, iki sayfa
 *  da geride kalabilir. Her çift için tür ve önerilen iş; karar işletmenindir, hiçbir yere gönderilmez. */
export default function SeoCannibal() {
  return (
    <SeoLayout
      path="/seo-geo/yarisan"
      crumb="Yarışan sayfalar"
      eyebrow="SEO & GEO · Search Console"
      title="Yarışan sayfalar"
      lead="Aynı aramada sitemizin iki ya da daha çok adresi gösteriliyorsa Google hangisini öne çıkaracağına karar veremez; gösterim ve tıklama bölünür. Son 28 günün Search Console verisinden hesaplanır, her gece yenilenir."
    >
      <CannibalList />
    </SeoLayout>
  );
}

export function CannibalList() {
  const [kind, setKind] = useState<Severity | 'hepsi'>('zararli');
  const [brand, setBrand] = useState('0');
  const [type, setType] = useState<PairType | ''>('');
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-cannibal', kind, brand, type, start],
    queryFn: () => cannibal({ kind, brand, type, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const d = r.data;
  const t = d?.thresholds;
  const count = (k: Severity) => (d ? (brand === '1' ? d.totals.severity[k].brand : brand === '0' ? d.totals.severity[k].nonBrand : d.totals.severity[k].all) : undefined);
  const reset = <T,>(set: (v: T) => void) => (v: T) => {
    set(v);
    setStart(0);
  };

  return (
    <>
      <p style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
        {d?.source.savedAt ? `Son okuma ${dateTime(d.source.savedAt)} · ${day(d.source.start)} – ${day(d.source.end)}` : 'Henüz okuma yok'}
      </p>
      {r.isLoading && <Loading text="Yarışan sayfalar aranıyor…" />}
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
              <Kpi label="Zararlı bölünme" value={fmt(d.totals.severity.zararli.nonBrand)} note={`Marka dışı arama · ${fmt(d.totals.severity.zararli.impressions)} gösterim`} info={<SeoInfo k={r.data?.kaynaklar} label="Zararlı bölünme" />} />
              <Kpi label="İzlenmeli" value={fmt(d.totals.severity.izle.nonBrand)} note={`Baskın sayfa yok ama biri ilk ${fmt(t!.harmPosition)} sırada`} info={<SeoInfo k={r.data?.kaynaklar} label="İzlenmeli" />} />
              <Kpi label="Adres kopyası" value={fmt(d.totals.types.kopya)} note="Parametreli ya da yazım farklı aynı sayfa" info={<SeoInfo k={r.data?.kaynaklar} label="Adres kopyası" />} />
              <Kpi label="Aynı kitabın iki ürünü" value={fmt(d.totals.types.baski)} note="Eski/yeni baskı ya da ikinci kayıt" info={<SeoInfo k={r.data?.kaynaklar} label="Aynı kitabın iki ürünü" />} />
            </section>

            <div className="sg-filters" role="toolbar" aria-label="Önem">
              {(['zararli', 'izle', 'baskin'] as Severity[]).map((k) => (
                <Chip key={k} on={kind === k} onClick={() => reset(setKind)(k)} label={SEV_LABEL[k]} n={count(k)} />
              ))}
              <Chip on={kind === 'hepsi'} onClick={() => reset(setKind)('hepsi')} label="Hepsi" />
              <span style={{ width: 8 }} aria-hidden />
              <Chip on={brand === '0'} onClick={() => reset(setBrand)('0')} label="Marka dışı" />
              <Chip on={brand === '1'} onClick={() => reset(setBrand)('1')} label="Marka araması" />
              <Chip on={brand === ''} onClick={() => reset(setBrand)('')} label="Hepsi" />
            </div>
            <div className="sg-filters" role="toolbar" aria-label="Çift türü">
              <Chip on={!type} onClick={() => reset(setType)('')} label="Bütün türler" />
              {d.pairTypes
                .filter((p) => d.totals.types[p.id] || type === p.id)
                .map((p) => (
                  <Chip key={p.id} on={type === p.id} onClick={() => reset(setType)(p.id)} label={p.label} n={d.totals.types[p.id]} />
                ))}
            </div>

            <section className="sg-card">
              <h2>{kind === 'hepsi' ? 'Bütün yarışan aramalar' : SEV_LABEL[kind]}</h2>
              <p className="sg-sub">
                En az {fmt(t!.minPageImpressions)} gösterimli iki ya da daha çok adresimizin göründüğü aramalar (arama toplamı en az {fmt(t!.minQueryImpressions)}{' '}
                gösterim). Zararlı: hiçbir adres gösterimin {pct(t!.dominantShare)}’ini almıyor ve en çok gösterilen iki adres de {fmt(t!.harmPosition)}. sıranın
                gerisinde. Asıl adres en çok tıklanandır; öneriler ona göre yazılır. Gösterime göre sıralı.
              </p>
              {!d.items.length ? (
                <div className="sg-empty">
                  <h2>Bu süzgeçte yarışan arama yok</h2>
                  <p>Önem ya da marka süzgecini değiştirmeyi deneyin.</p>
                </div>
              ) : (
                <div className="sg-list">
                  {d.items.map((i) => (
                    <Group key={i.query} i={i} k={d.kaynaklar} />
                  ))}
                </div>
              )}
              <Pager start={start} total={d.total} onChange={setStart} />
            </section>
          </>
        )
      )}
    </>
  );
}

function Group({ i, k }: { i: Item; k?: Kaynaklar | null }) {
  const typeLabel: Record<PairType, string> = {
    kopya: 'Adres kopyası',
    baski: 'Aynı kitap, iki ürün',
    urun_sayfa: 'Kitap ↔ liste sayfası',
    sayfa_sayfa: 'İki liste sayfası',
    urun_urun: 'Farklı kitaplar',
    diger: 'Türü bilinmiyor',
  };
  return (
    <article style={{ border: '1px solid var(--sg-line)', borderRadius: 16, padding: 14, minWidth: 0 }}>
      <header style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0, fontSize: 14, color: 'var(--sg-ink)', overflowWrap: 'anywhere' }}>
          “{i.query}” {i.brand && <span className="sg-chip violet">Marka</span>}
        </h3>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', fontSize: 12 }}>
          <span className={`sg-chip ${SEV_TONE[i.severity]}`}>{SEV_LABEL[i.severity]}</span>
          <span className="sg-mono" style={{ color: 'var(--sg-muted)' }}>
            {fmt(i.impressions)} gösterim · {fmt(i.clicks)} tıklama
          </span>
        </div>
      </header>

      <div className="sg-table-wrap" style={{ marginTop: 10 }}>
        <table className="sg-table">
          <thead>
            <tr>
              <th>Adres</th>
              <th>Gösterim payı <SeoInfo k={k} label="Gösterim payı" /></th>
              <th>Tıklama <SeoInfo k={k} label="Tıklama" /></th>
              <th>Sıra <SeoInfo k={k} label="Sıra" /></th>
            </tr>
          </thead>
          <tbody>
            {i.pages.map((p) => (
              <tr key={p.url}>
                <td style={{ minWidth: 220 }}>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', alignItems: 'center', marginBottom: 2 }}>
                    {p.primary && <span className="sg-chip good">Asıl</span>}
                    {p.linkLabel && <span className="sg-chip">{p.linkLabel}</span>}
                    {p.params && <span className="sg-chip mid">Parametreli</span>}
                    {p.productActive === false && <span className="sg-chip bad">Satışta değil</span>}
                  </div>
                  {p.productId ? (
                    <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(p.productId)}`}>{p.productName || pathOf(p.url)}</Link>
                  ) : null}
                  <div className="sg-mono" style={{ fontSize: 11.5, overflowWrap: 'anywhere', color: p.productId ? 'var(--sg-muted)' : undefined }}>
                    {pathOf(p.url)}{' '}
                    <a href={p.url} target="_blank" rel="noreferrer" aria-label="Sayfayı aç">
                      <ExternalLink size={11} aria-hidden />
                    </a>
                  </div>
                </td>
                <td className="num" style={{ minWidth: 110 }}>
                  {pct(p.share)} <small style={{ color: 'var(--sg-muted)' }}>{fmt(p.impressions)}</small>
                  <div className="sg-bar" style={{ marginTop: 4 }} aria-hidden>
                    <i style={{ width: `${Math.round(p.share * 100)}%` }} />
                  </div>
                </td>
                <td className="num">
                  {fmt(p.clicks)}
                  {p.clickShare != null && <div style={{ fontSize: 11, color: 'var(--sg-muted)' }}>{pct(p.clickShare)}</div>}
                </td>
                <td className="num">{fmt(p.position, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul style={{ margin: '10px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {i.pairs.map((p) => (
          <li key={`${p.a}|${p.b}`} style={{ fontSize: 12.5, lineHeight: 1.5, background: 'var(--sg-soft)', borderRadius: 12, padding: '8px 10px', overflowWrap: 'anywhere' }}>
            <span className="sg-chip violet">{typeLabel[p.type]}</span> <span style={{ color: 'var(--sg-muted)' }}>{p.why}</span>
            {i.pairs.length > 1 && <div className="sg-mono" style={{ fontSize: 11, color: 'var(--sg-muted)' }}>{pathOf(p.b)}</div>}
            <div style={{ marginTop: 2 }}>
              <strong>Öneri:</strong> {p.action}
            </div>
          </li>
        ))}
      </ul>
    </article>
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
