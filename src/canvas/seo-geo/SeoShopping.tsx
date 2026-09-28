import { useDeferredValue, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, Download, Search } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';
import { useCan } from '../useAdmin';

/** Google Alışveriş hazırlığı: satıştaki ürünler Google'ın ürün verisi kurallarına göre denetlenir. Hiçbir yere
 *  gönderilmez; besleme dosyası elle yüklenmek içindir. */

type Sev = 'engelleyici' | 'sorun' | 'bilgi';
type Status = 'hazir' | 'sorunlu' | 'engelleyici';
type ShopIssue = { code: string; severity: Sev; title: string; detail: string };
type ShopRow = {
  id: string;
  name: string;
  author: string | null;
  url: string | null;
  image: string | null;
  gtin: string | null;
  book: boolean;
  price: number | null;
  salePrice: number | null;
  currency: string;
  availability: 'in_stock' | 'out_of_stock' | null;
  status: Status;
  issues: ShopIssue[];
  score: number;
  sales: number;
};
type ShopPage = {
  total: number;
  start: number;
  items: ShopRow[];
  summary: {
    products: number;
    ready: number;
    problem: number;
    blocked: number;
    issues: Array<{ code: string; severity: Sev; title: string; why: string; count: number }>;
  };
  lastSync: string | null;
  merchant: boolean;
  scopes: Record<string, string>;
  limits: { title: number; description: number };
  bookCategory: string;
};

const shopApi = {
  list: (p: { issue?: string; status?: string; q?: string; start: number; limit: number }) => call<ShopPage>(`shopping?${qs(p)}`, { timeout: 180_000 }),
  feedUrl: (scope: string) => `${ENGINE_BASE}/api/v1/seo-geo/shopping/feed.tsv?kapsam=${encodeURIComponent(scope)}`,
};

const PAGE = 40;
const SEV_TONE: Record<Sev, 'bad' | 'mid' | 'violet'> = { engelleyici: 'bad', sorun: 'mid', bilgi: 'violet' };
const STATUS_LABEL: Record<Status, string> = { hazir: 'Hazır', sorunlu: 'Sorunlu', engelleyici: 'Engelleyici' };
const STATUS_TONE: Record<Status, 'good' | 'mid' | 'bad'> = { hazir: 'good', sorunlu: 'mid', engelleyici: 'bad' };
const AVAIL_LABEL = { in_stock: 'Stokta', out_of_stock: 'Stokta yok' } as const;

const money = (v: number | null, cur: string) => (v == null ? '—' : `${fmt(v, 2)} ${cur === 'TRY' ? '₺' : cur}`);

export default function SeoShopping() {
  const canExport = useCan('veri.disa-aktar');
  const [status, setStatus] = useState<Status | ''>('');
  const [issue, setIssue] = useState('');
  const [q, setQ] = useState('');
  const dq = useDeferredValue(q.trim());
  const [start, setStart] = useState(0);
  const [scope, setScope] = useState('uygun');
  useEffect(() => setStart(0), [status, issue, dq]);

  const list = useQuery({
    queryKey: ['seo-shopping', status, issue, dq, start],
    queryFn: () => shopApi.list({ status, issue, q: dq, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (prev) => prev,
  });
  const d = list.data;
  const s = d?.summary;
  const shownIssues = (s?.issues ?? []).filter((i) => i.count > 0);

  return (
    <SeoLayout
      path="/seo-geo/alisveris"
      crumb="Google Alışveriş hazırlığı"
      eyebrow="SEO & GEO · Google Alışveriş"
      title="Google Alışveriş hazırlığı"
      lead="Satıştaki her ürün Google Alışveriş’in ürün verisi kurallarına göre denetlenir: başlık, açıklama, görsel, stok, fiyat, barkod (ISBN), yayınevi ve CRM yayın durumu. Hiçbir yere gönderilmez; besleme dosyasını indirip Google’a elle yüklersiniz."
      actions={
        canExport && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <label className="sg-kpi-note" style={{ display: 'inline-flex', gap: 6, alignItems: 'center', margin: 0 }}>
              Kapsam
              <select value={scope} onChange={(e) => setScope(e.target.value)} className="sg-button" style={{ minHeight: 44 }} aria-label="Dosya kapsamı">
                {Object.entries(d?.scopes ?? { uygun: 'engelleyicisi olmayanlar' }).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
            <a className="sg-button" href={shopApi.feedUrl(scope)}>
              <Download size={16} aria-hidden /> Besleme dosyasını indir
            </a>
          </div>
        )
      }
    >
      {list.isLoading && <Loading text="Ürünler denetleniyor…" />}
      {list.error && <Failed error={list.error} />}

      {d && s && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Hazır" value={fmt(s.ready)} note={`${fmt(s.products)} satıştaki üründen`} tone="good" onClick={() => setStatus(status === 'hazir' ? '' : 'hazir')} active={status === 'hazir'} />
            <Kpi label="Sorunlu" value={fmt(s.problem)} note="Geçer ama uyarı alır ya da az gösterilir" onClick={() => setStatus(status === 'sorunlu' ? '' : 'sorunlu')} active={status === 'sorunlu'} />
            <Kpi label="Engelleyici" value={fmt(s.blocked)} note="Google reddeder ya da reklama çıkmamalı" tone={s.blocked ? 'bad' : undefined} onClick={() => setStatus(status === 'engelleyici' ? '' : 'engelleyici')} active={status === 'engelleyici'} />
            <Kpi label="Son T-soft okuması" value={dateTime(d.lastSync)} note="Denetim bu veriden yapılır" small />
          </section>
          {!d.merchant && (
            <p className="sg-banner" style={{ marginTop: 12 }}>
              Google Alışveriş hesabı bağlı değil; bu ekran yalnız hazırlık içindir. Dosyada fiyat KDV dahil ve Türk lirasıdır, kitaplar Google kategorisi {d.bookCategory} (Medya › Kitaplar) ile işaretlenir.
            </p>
          )}
        </>
      )}

      {s && (
        <section className="sg-card" aria-label="Sorun türleri" style={{ marginTop: 16 }}>
          <h2>Sorun türleri</h2>
          <p className="sg-sub">Bir türe dokunarak yalnız o sorunu taşıyan ürünleri listeleyin.</p>
          {shownIssues.length ? (
            <div className="sg-filters" role="group" aria-label="Sorun süzgeci">
              <button className="sg-filter" aria-pressed={issue === ''} onClick={() => setIssue('')}>
                Tümü
              </button>
              {shownIssues.map((i) => (
                <button key={i.code} className="sg-filter" aria-pressed={issue === i.code} onClick={() => setIssue(issue === i.code ? '' : i.code)} title={i.why}>
                  <span className={`sg-dot ${i.severity === 'engelleyici' ? 'kritik' : i.severity === 'sorun' ? 'orta' : 'düşük'}`} aria-hidden />
                  {i.title}
                  <span className="sg-mono"> {fmt(i.count)}</span>
                </button>
              ))}
            </div>
          ) : (
            <p className="sg-kpi-note">Hiçbir üründe sorun bulunmadı.</p>
          )}
          {issue && <p className="sg-kpi-note" style={{ margin: '10px 0 0' }}>{s.issues.find((i) => i.code === issue)?.why}</p>}
        </section>
      )}

      {d && (
        <section className="sg-card" aria-label="Ürünler" style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <h2 style={{ margin: 0 }}>
              Ürünler <span className="sg-mono" style={{ fontSize: 13, color: 'var(--sg-muted)' }}>{fmt(d.total)}</span>
            </h2>
            <label className="sg-search" style={{ flex: '1 1 260px', maxWidth: 420 }}>
              <Search size={16} aria-hidden />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı, yazar ya da barkod" aria-label="Ürün ara" />
            </label>
          </div>
          {!d.items.length ? (
            <div className="sg-empty">
              <h2>Ürün yok</h2>
              <p>Bu süzgeçle eşleşen satıştaki ürün bulunmadı.</p>
            </div>
          ) : (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Kitap</th>
                    <th>Durum</th>
                    <th>Fiyat</th>
                    <th>Stok</th>
                    <th>Barkod</th>
                    <th>Sorunlar</th>
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((r) => (
                    <tr key={r.id}>
                      <td style={{ minWidth: 200 }}>
                        <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(r.id)}`} style={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                          {r.name || r.id}
                        </Link>
                        {r.author && <div className="sg-kpi-note">{r.author}</div>}
                        <div className="sg-kpi-note">Satış {fmt(r.sales)} · puan {fmt(r.score)}</div>
                      </td>
                      <td>
                        <span className={`sg-chip ${STATUS_TONE[r.status]}`}>{STATUS_LABEL[r.status]}</span>
                      </td>
                      <td className="num">
                        {r.salePrice != null ? (
                          <>
                            {money(r.salePrice, r.currency)}
                            <div className="sg-kpi-note" style={{ textDecoration: 'line-through' }}>{money(r.price, r.currency)}</div>
                          </>
                        ) : (
                          money(r.price, r.currency)
                        )}
                      </td>
                      <td>{r.availability ? AVAIL_LABEL[r.availability] : '—'}</td>
                      <td className="url">{r.gtin ?? '—'}</td>
                      <td style={{ minWidth: 220 }}>
                        {r.issues.length ? (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                            {r.issues.map((i) => (
                              <span key={i.code} className={`sg-chip ${SEV_TONE[i.severity]}`} title={i.detail || undefined}>
                                {i.title}
                                {(i.code === 'crm_flag' || i.code === 'title_promo') && i.detail ? `: ${i.detail}` : ''}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span className="sg-kpi-note">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {d.total > PAGE && (
            <div className="sg-pager" style={{ marginTop: 12 }}>
              <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
                <ChevronLeft size={16} aria-hidden />
              </button>
              <span className="sg-mono">
                {fmt(start + 1)}–{fmt(Math.min(d.total, start + PAGE))} / {fmt(d.total)}
              </span>
              <button className="sg-button" disabled={start + PAGE >= d.total} onClick={() => setStart(start + PAGE)} aria-label="Sonraki sayfa">
                <ChevronRight size={16} aria-hidden />
              </button>
            </div>
          )}
        </section>
      )}
    </SeoLayout>
  );
}

function Kpi({ label, value, note, tone, small, onClick, active }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; small?: boolean; onClick?: () => void; active?: boolean }) {
  const body = (
    <>
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono" style={{ ...(tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : {}), ...(small ? { fontSize: 18 } : {}) }}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </>
  );
  if (!onClick) return <div className="sg-kpi">{body}</div>;
  return (
    <button type="button" className="sg-kpi" onClick={onClick} aria-pressed={!!active} style={{ textAlign: 'left', border: active ? '2px solid #aa87e8' : '2px solid transparent', cursor: 'pointer', font: 'inherit' }}>
      {body}
    </button>
  );
}
