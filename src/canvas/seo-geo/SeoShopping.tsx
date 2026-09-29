import type { ReactNode } from 'react';
import { useDeferredValue, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';
import { EmptyHint } from '../components/Explain';
import { TermLabel } from './terms';
import SeoPager from './SeoPager';

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
    <SeoLayout k={list.data?.kaynaklar}
      path="/seo-geo/alisveris"
      crumb="Google Alışveriş hazırlığı"
      eyebrow="SEO & GEO · Google Alışveriş"
      title="Google Alışveriş hazırlığı"
      lead="Satıştaki ürünler Google Alışveriş sonuçlarına çıkmaya hazır mı: başlık, açıklama, görsel, stok, fiyat, barkod (ISBN), yayınevi ve CRM yayın durumu denetlenir. Hiçbir yere gönderilmez; ürün listesi dosyasını («besleme dosyası») indirip Google’a elle yüklersiniz."
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
            <Kpi label="Hazır" value={fmt(s.ready)} note={`${fmt(s.products)} satıştaki üründen`} tone="good" onClick={() => setStatus(status === 'hazir' ? '' : 'hazir')} active={status === 'hazir'} info={<SeoInfo k={list.data?.kaynaklar} label="Hazır" />} />
            <Kpi label="Sorunlu" value={fmt(s.problem)} note="Geçer ama uyarı alır ya da az gösterilir" onClick={() => setStatus(status === 'sorunlu' ? '' : 'sorunlu')} active={status === 'sorunlu'} info={<SeoInfo k={list.data?.kaynaklar} label="Sorunlu" />} />
            <Kpi label="Engelleyici" value={fmt(s.blocked)} note="Google reddeder ya da reklama çıkmamalı" tone={s.blocked ? 'bad' : undefined} onClick={() => setStatus(status === 'engelleyici' ? '' : 'engelleyici')} active={status === 'engelleyici'} info={<SeoInfo k={list.data?.kaynaklar} label="Engelleyici" />} />
            <Kpi label="Son T-soft okuması" value={dateTime(d.lastSync)} note="Denetim bu veriden yapılır" small info={<SeoInfo k={list.data?.kaynaklar} label="Son T-soft okuması" />} />
          </section>
          <p className="sg-kpi-note" style={{ margin: '8px 0 0' }}>
            «Hazır»: Google’ın kurallarına uyuyor. «Sorunlu»: kabul edilir ama uyarı alır ya da az gösterilir. «Engelleyici»: Google reddeder; önce bunlar düzeltilmeli. Karta dokunun, liste süzülsün.
          </p>
          {!d.merchant && (
            <p className="sg-banner" style={{ marginTop: 12 }}>
              Google Merchant Center’dan henüz ürün durumu okunmadı; aşağıdaki denetim yalnız hazırlık içindir. Dosyada fiyat KDV dahil ve Türk lirasıdır, kitaplar Google kategorisi {d.bookCategory} (Medya › Kitaplar) ile işaretlenir.
            </p>
          )}
        </>
      )}

      <MerchantSection />

      {s && (
        <section className="sg-card" aria-label="Sorun türleri" style={{ marginTop: 16 }}>
          <h2>Sorun türleri <SeoInfo k={list.data?.kaynaklar} label="Sorun türleri" /></h2>
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
            <p className="sg-banner ok">Hiçbir üründe sorun bulunmadı.</p>
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
            <EmptyHint title="Bu süzgece uyan ürün yok" why="Aramayı kısaltın, durum kartındaki seçimi ya da sorun türünü kaldırın." />
          ) : (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Kitap</th>
                    <th>Durum</th>
                    <th>Fiyat <SeoInfo k={list.data?.kaynaklar} label="Fiyat" /></th>
                    <th>Stok <SeoInfo k={list.data?.kaynaklar} label="Stok" /></th>
                    <th><TermLabel k="gtin" label="Barkod" /></th>
                    <th>Sorunlar <SeoInfo k={list.data?.kaynaklar} label="Sorunlar" /></th>
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
          <SeoPager start={start} total={d.total} size={PAGE} onChange={setStart} />
        </section>
      )}
    </SeoLayout>
  );
}

function Kpi({ label, value, note, tone, small, onClick, active, info }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; small?: boolean; onClick?: () => void; active?: boolean; info?: ReactNode }) {
  const body = (
    <>
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}</div>
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

/* ------------------------------------------------------------------ Google Merchant'taki durum (yalnız okunur) */

type MStatus = 'onaylanmayan' | 'sinirli' | 'bekleyen' | 'onayli';
type MSev = 'DISAPPROVED' | 'DEMOTED' | 'NOT_IMPACTED';
type MIssueType = {
  code: string;
  severity: MSev;
  severityLabel: string;
  description: string | null;
  detail: string | null;
  documentation: string | null;
  attributeLabel: string | null;
  resolutionLabel: string | null;
  products: number;
};
type MItemIssue = { code: string; severity: MSev; severityLabel: string; description: string | null; detail: string | null; attributeLabel: string | null; contextLabels: string[] };
type MItem = { name: string; offerId: string; title: string | null; gtin: string | null; status: MStatus; statusLabel: string; issues: MItemIssue[]; productId: string | null };
type MSummary = { total: number; approved: number; disapproved: number; limited: number; pending: number; matched: number; unmatched: number; issues: MIssueType[] };
type MPage = {
  configured: boolean;
  snapshot: { account?: string; link?: string; summary?: MSummary; error: string | null; savedAt: string | null } | null;
  state: { running: boolean; error: string | null };
  refreshHours: number;
  total: number;
  start: number;
  items: MItem[];
  statusLabels: Record<MStatus, string>;
};

const merchantApi = {
  get: (p: { status: string; issue: string; start: number; limit: number }) => call<MPage>(`merchant?${qs(p)}`),
  refresh: () => call<{ started: boolean }>('merchant/refresh', { method: 'POST' }),
};
const M_TONE: Record<MStatus, 'bad' | 'mid' | 'good' | 'violet'> = { onaylanmayan: 'bad', sinirli: 'mid', bekleyen: 'violet', onayli: 'good' };
const M_SEV_TONE: Record<MSev, 'bad' | 'mid' | 'violet'> = { DISAPPROVED: 'bad', DEMOTED: 'mid', NOT_IMPACTED: 'violet' };
const M_PAGE = 25;

/** Merchant Center'daki gerçek ürün durumu: 6 saatte bir, ekran açıldığında da eskiyse yalnız okunarak alınır. */
function MerchantSection() {
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const initialIssue = params.get('merchant') ?? '';
  const [status, setStatus] = useState<string>(initialIssue ? '' : 'sorunlu');
  const [issue, setIssue] = useState(initialIssue);
  const [start, setStart] = useState(0);
  useEffect(() => setStart(0), [status, issue]);

  const r = useQuery({
    queryKey: ['seo-merchant', status, issue, start],
    queryFn: () => merchantApi.get({ status, issue, start, limit: M_PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (prev) => prev,
    refetchInterval: (q) => (q.state.data?.state.running ? 5000 : false),
  });
  const refresh = useMutation({ mutationFn: merchantApi.refresh, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-merchant'] }) });
  const d = r.data;
  const snap = d?.snapshot;
  const sum = snap?.summary;
  const running = !!d?.state.running;
  const pickStatus = (v: string) => {
    setIssue('');
    setStatus(status === v ? 'sorunlu' : v);
  };
  const pickIssue = (code: string) => {
    if (issue === code) {
      setIssue('');
      setStatus('sorunlu');
    } else {
      setIssue(code);
      setStatus('');
    }
  };
  const listTitle = issue
    ? 'Bu sorunu taşıyan ürünler'
    : status === 'sorunlu'
      ? 'Onaylanmayan ve sınırlı ürünler'
      : `${d?.statusLabels?.[status as MStatus] ?? ''} ürünler`;

  if (d && !d.configured) return null;

  return (
    <section className="sg-card" aria-label="Google Merchant’taki durum" style={{ marginTop: 16 }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>Google Merchant’taki durum</h2>
        <div className="sg-actions">
          <button className="sg-button" onClick={() => refresh.mutate()} disabled={refresh.isPending || running}>
            {running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {running ? 'Okunuyor…' : 'Şimdi oku'}
          </button>
          {snap?.link && (
            <a className="sg-button" href={snap.link} target="_blank" rel="noreferrer">
              <ExternalLink size={16} aria-hidden /> Merchant Center’da aç
            </a>
          )}
        </div>
      </div>
      <p className="sg-sub">
        Google’ın ürünlerimiz için verdiği karar: onaylı, onaylanmayan, gösterimi sınırlı ya da incelemede. Her {d?.refreshHours ?? 6} saatte bir yalnız okunur; Google’a hiçbir şey gönderilmez.
        {snap?.savedAt ? ` Son okuma: ${dateTime(snap.savedAt)}.` : ''}
      </p>
      {r.isLoading && <Loading text="Google’daki ürün durumu getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {refresh.error && <Failed error={refresh.error} />}
      {(d?.state.error || snap?.error) && <p className="sg-banner err">Son okuma başarısız: {d?.state.error || snap?.error}</p>}
      {d && !sum && !running && (
        <EmptyHint title="Google’daki durum henüz okunmadı" why="«Şimdi oku»ya basın; sonra kendiliğinden okunur." />
      )}
      {d && sum && (
        <>
          <div className="sg-kpis" style={{ marginTop: 12 }}>
            <Kpi label="Onaylı" value={fmt(sum.approved)} note={`${fmt(sum.total)} üründen`} tone="good" onClick={() => pickStatus('onayli')} active={status === 'onayli'} />
            <Kpi label="Onaylanmayan" value={fmt(sum.disapproved)} note="Google’da görünmüyor" tone={sum.disapproved ? 'bad' : undefined} onClick={() => pickStatus('onaylanmayan')} active={status === 'onaylanmayan'} />
            <Kpi label="Sınırlı" value={fmt(sum.limited)} note="Aynı yerde bazı ülkelerde onaylı, bazılarında reddedilmiş" onClick={() => pickStatus('sinirli')} active={status === 'sinirli'} />
            <Kpi label="Bekleyen" value={fmt(sum.pending)} note="Google inceliyor" onClick={() => pickStatus('bekleyen')} active={status === 'bekleyen'} />
          </div>
          {sum.unmatched > 0 && (
            <p className="sg-kpi-note" style={{ marginTop: 8 }}>
              {fmt(sum.unmatched)} ürün sitedeki bir ürünle eşlenemedi (ürün kodu ya da barkod tutmadı); satış etkisi hesabına girmez.
            </p>
          )}

          <h3 style={{ margin: '18px 0 8px' }}>Sorun türleri</h3>
          {sum.issues.length ? (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Sorun</th>
                    <th>Önem</th>
                    <th>Ürün</th>
                    <th>Ne yapılmalı</th>
                  </tr>
                </thead>
                <tbody>
                  {sum.issues.map((i) => (
                    <tr key={i.code}>
                      <td style={{ minWidth: 200 }}>
                        <button type="button" className="sg-filter" aria-pressed={issue === i.code} onClick={() => pickIssue(i.code)} title={i.detail ?? undefined}>
                          {i.description || i.code}
                        </button>
                        {i.attributeLabel && <div className="sg-kpi-note">Alan: {i.attributeLabel}</div>}
                      </td>
                      <td>
                        <span className={`sg-chip ${M_SEV_TONE[i.severity] ?? 'violet'}`}>{i.severityLabel}</span>
                      </td>
                      <td className="num">{fmt(i.products)}</td>
                      <td style={{ minWidth: 200 }}>
                        {i.resolutionLabel && <div className="sg-kpi-note">{i.resolutionLabel}</div>}
                        {i.documentation && (
                          <a href={i.documentation} target="_blank" rel="noreferrer" className="sg-kpi-note" style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
                            Google’ın açıklaması <ExternalLink size={12} aria-hidden />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="sg-banner ok">Google hiçbir üründe sorun bildirmiyor.</p>
          )}

          <h3 style={{ margin: '18px 0 8px' }}>
            {listTitle} <span className="sg-mono" style={{ fontSize: 13, color: 'var(--sg-muted)' }}>{fmt(d.total)}</span>
          </h3>
          {!d.items.length ? (
            <EmptyHint title="Bu süzgece uyan ürün yok" why="Başka bir durum kartı ya da sorun türü seçin." />
          ) : (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Ürün</th>
                    <th>Durum</th>
                    <th>Sorunlar</th>
                  </tr>
                </thead>
                <tbody>
                  {d.items.map((it) => (
                    <tr key={it.name}>
                      <td style={{ minWidth: 200 }}>
                        {it.productId ? (
                          <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(it.productId)}`} style={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                            {it.title || it.offerId}
                          </Link>
                        ) : (
                          <span style={{ fontWeight: 700, overflowWrap: 'anywhere' }}>{it.title || it.offerId}</span>
                        )}
                        <div className="sg-kpi-note">
                          Kod {it.offerId}
                          {it.gtin ? ` · barkod ${it.gtin}` : ''}
                          {!it.productId ? ' · sitede eşlenemedi' : ''}
                        </div>
                      </td>
                      <td>
                        <span className={`sg-chip ${M_TONE[it.status]}`}>{it.statusLabel}</span>
                      </td>
                      <td style={{ minWidth: 220 }}>
                        {it.issues.length ? (
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                            {it.issues.map((i) => (
                              <span
                                key={i.code}
                                className={`sg-chip ${M_SEV_TONE[i.severity] ?? 'violet'}`}
                                title={[i.detail, i.contextLabels.join(', ')].filter(Boolean).join(' — ') || undefined}
                              >
                                {i.description || i.code}
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
          <SeoPager start={start} total={d.total} size={M_PAGE} onChange={setStart} />
        </>
      )}
    </section>
  );
}
