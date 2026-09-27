import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, RefreshCw, Search, Send } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs, seoApi } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

const PAGE = 40;

type Stat = { clicks: number; impressions: number; position: number | null };
type CrawlDay = { date: string; crawled: number; inIndex: number; errors: number; code4xx: number; code5xx: number; blockedByRobots: number; inLinks: number };
type BingSummary = {
  configured: boolean;
  site: string;
  running: boolean;
  error: string | null;
  lastRefresh: string | null;
  errors: Record<string, string>;
  totals: { start: string | null; end: string | null; clicks: number; impressions: number; ctr: number; prevClicks: number | null; prevImpressions: number | null };
  daily: Array<{ date: string; clicks: number; impressions: number }>;
  crawlLatest: CrawlDay | null;
  quota: { daily: number | null; monthly: number | null } | null;
  queryPeriod: { start: string | null; end: string | null };
  counts: { queries: number; pages: number; issues: number; compared: number; worse: number; onlyGoogle: number };
  google: { start: string | null; end: string | null; savedAt: string | null } | null;
  gap: number;
};
type CompareRow = { query: string; google: Stat; bing: Stat; gap: number | null; worse: boolean };
type BingRow = Stat & { key: string; ctr: number };
type IssueRow = { url: string; httpCode: number | null; issues: string[]; inLinks: number };
type Kind = 'compare' | 'queries' | 'pages' | 'issues';
type ListOf<K extends Kind> = { total: number; start: number; items: K extends 'compare' ? CompareRow[] : K extends 'issues' ? IssueRow[] : BingRow[] };
type Submission = { id: string; at: string; kind: string; count: number; status: number | null; statusText: string | null; error: string | null; by: string | null };
type IndexNow = {
  configured: boolean;
  keyValid: boolean;
  keyFileUrl: string | null;
  keyFileOk: boolean;
  keyFileError: string | null;
  checkedAt: string | null;
  host: string;
  pending: number;
  tracked: number;
  baselineAt: string | null;
  logTotal: number;
  lastSubmissions: Submission[];
  batchSize: number;
};
type SubmitResult = { submitted: number; urls: number; skipped: number; batches: Array<{ count: number; status: number | null; error: string | null }> };

const bingApi = {
  summary: () => call<BingSummary>('bing'),
  list: <K extends Kind>(kind: K, p: { start: number; limit: number; q?: string; filter?: string }) => call<ListOf<K>>(`bing/list/${kind}?${qs(p)}`),
  refresh: () => call<{ counts: Record<string, number>; errors: Record<string, string> }>('bing/refresh', { method: 'POST', timeout: 600_000 }),
  indexnow: (p: { recheck?: number; start?: number }) => call<IndexNow>(`indexnow?${qs({ ...p, limit: 20 })}`),
  submit: () => call<SubmitResult>('indexnow/submit', { method: 'POST', timeout: 600_000 }),
  submitAll: () => call<SubmitResult>('indexnow/submit-all', { method: 'POST', timeout: 600_000 }),
};

const KIND_LABEL: Record<string, string> = { gece: 'Gece', kuyruk: 'Bekleyenler', tumu: 'Bütün kitaplar' };
const LIST_LABEL: Record<Exclude<Kind, 'issues'>, string> = { compare: 'Google ile karşılaştırma', queries: 'Bing sorguları', pages: 'Bing sayfaları' };
const pct = (v: number) => `%${fmt(v * 100, 1)}`;
const pos = (v: number | null) => (v == null ? '—' : fmt(v, 1));
const change = (cur: number, prev: number | null) => {
  if (prev == null || prev === 0) return 'Önceki dönem verisi yok';
  const d = ((cur - prev) / prev) * 100;
  return `Önceki 28 güne göre ${d >= 0 ? '+' : ''}${fmt(d, 1)}%`;
};

function Pager({ start, total, onChange }: { start: number; total: number; onChange: (s: number) => void }) {
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

/** Bing ve IndexNow: Bing Webmaster'dan yalnız okunan sorgu, trafik ve tarama verisi; Google ile aynı sorguların sıra
 *  karşılaştırması; değişen kitap sayfalarının IndexNow ile bildirilmesi. T-soft'a hiçbir şey yazılmaz. */
export default function SeoBing() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Exclude<Kind, 'issues'>>('compare');
  const [worse, setWorse] = useState(false);
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);
  const [issueStart, setIssueStart] = useState(0);
  const [logStart, setLogStart] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [tab, worse, query]);

  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false });
  const summary = useQuery({ queryKey: ['seo-bing'], queryFn: bingApi.summary, enabled: ENGINE_ENABLED, retry: false });
  const configured = !!summary.data?.configured;
  const list = useQuery({
    queryKey: ['seo-bing-list', tab, worse, query, start],
    queryFn: () => bingApi.list(tab, { start, limit: PAGE, q: query, filter: tab === 'compare' && worse ? 'worse' : '' }),
    enabled: ENGINE_ENABLED && configured,
    retry: false,
    placeholderData: (p) => p,
  });
  const issues = useQuery({
    queryKey: ['seo-bing-issues', issueStart],
    queryFn: () => bingApi.list('issues', { start: issueStart, limit: PAGE }),
    enabled: ENGINE_ENABLED && configured,
    retry: false,
    placeholderData: (p) => p,
  });
  const [recheck, setRecheck] = useState(0);
  const ix = useQuery({
    queryKey: ['seo-indexnow', recheck, logStart],
    queryFn: () => bingApi.indexnow({ recheck: recheck ? 1 : undefined, start: logStart }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });

  const refresh = useMutation({
    mutationFn: bingApi.refresh,
    onSuccess: () => qc.invalidateQueries({ predicate: (qq) => String(qq.queryKey[0]).startsWith('seo-bing') }),
  });
  const afterSubmit = () => {
    setLogStart(0);
    return qc.invalidateQueries({ queryKey: ['seo-indexnow'] });
  };
  const submit = useMutation({ mutationFn: bingApi.submit, onSuccess: afterSubmit });
  const submitAll = useMutation({ mutationFn: bingApi.submitAll, onSuccess: afterSubmit });

  const d = summary.data;
  const x = ix.data;
  const canApprove = !!me.data?.canApprove;
  const canSubmit = !!x?.keyFileOk && canApprove;
  const sending = submit.isPending || submitAll.isPending;
  const lastResult = submit.data ?? submitAll.data;
  const errorKinds = Object.entries(d?.errors ?? {});

  return (
    <SeoLayout
      path="/seo-geo/bing"
      crumb="Bing ve IndexNow"
      eyebrow="SEO & GEO · Bing"
      title="Bing ve IndexNow"
      lead="ChatGPT'nin web araması büyük ölçüde Bing dizinine dayanır: Google'da iyi olup Bing'de geride kalan kitap, yapay zekâ cevaplarında da geride kalır. Bing verisi yalnız okunur; değişen kitap sayfaları IndexNow ile arama motorlarına bildirilir."
      actions={
        configured ? (
          <button className="sg-button primary" onClick={() => refresh.mutate()} disabled={refresh.isPending || d?.running}>
            {refresh.isPending || d?.running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {refresh.isPending || d?.running ? 'Bing okunuyor…' : "Bing'den yeniden oku"}
          </button>
        ) : undefined
      }
    >
      {summary.isLoading && <Loading text="Bing verisi getiriliyor…" />}
      {summary.error && <Failed error={summary.error} />}
      {refresh.error && <Failed error={refresh.error} />}

      {d && !configured && (
        <section className="sg-card">
          <h2>Bing bağlantısı kurulmamış</h2>
          <p className="sg-sub">Bing verisi okunabilmesi için bir kez yapılır; yalnız okuma izni kullanılır.</p>
          <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
            <li>
              <a href="https://www.bing.com/webmasters" target="_blank" rel="noreferrer">
                Bing Webmaster
              </a>{' '}
              hesabında <span className="sg-mono">{d.site}</span> sitesi doğrulanmış olmalı. Doğrulanmamışsa “Google Search Console'dan içe aktar” ile tek adımda eklenir.
            </li>
            <li>Bing Webmaster → Ayarlar → API erişimi → API anahtarı oluşturun ve kopyalayın.</li>
            <li>Anahtarı Yönetim → SEO & GEO → “Bing Webmaster API anahtarı” alanına yapıştırın. Ertesi gece kendiliğinden okunur; bu ekrandan hemen de okunabilir.</li>
          </ol>
        </section>
      )}

      {d && configured && (
        <>
          {d.error && <p className="sg-banner err">{d.error}</p>}
          {errorKinds.length > 0 && !d.error && (
            <p className="sg-banner">Son okumada bazı bölümler alınamadı; eski hâlleri gösteriliyor: {errorKinds.map(([, m]) => m).filter((m, i, a) => a.indexOf(m) === i).join(' · ')}</p>
          )}
          <section className="sg-kpis" aria-label="Özet">
            <div className="sg-kpi">
              <div className="sg-kpi-label">Bing tıklaması (28 gün)</div>
              <div className="sg-kpi-value sg-mono">{fmt(d.totals.clicks)}</div>
              <div className="sg-kpi-note">{change(d.totals.clicks, d.totals.prevClicks)}</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Bing gösterimi (28 gün)</div>
              <div className="sg-kpi-value sg-mono">{fmt(d.totals.impressions)}</div>
              <div className="sg-kpi-note">{change(d.totals.impressions, d.totals.prevImpressions)}</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Tıklama oranı</div>
              <div className="sg-kpi-value sg-mono">{pct(d.totals.ctr)}</div>
              <div className="sg-kpi-note">
                {d.totals.start ? `${d.totals.start} – ${d.totals.end}` : 'Veri yok'} · son okuma {dateTime(d.lastRefresh)}
              </div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Bing dizinindeki sayfa</div>
              <div className="sg-kpi-value sg-mono">{fmt(d.crawlLatest?.inIndex)}</div>
              <div className="sg-kpi-note">
                {d.crawlLatest ? `${d.crawlLatest.date} taraması: ${fmt(d.crawlLatest.crawled)} sayfa, ${fmt(d.crawlLatest.errors)} hata` : 'Tarama verisi yok'}
              </div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Bing'de çok geride</div>
              <div className="sg-kpi-value sg-mono">{fmt(d.counts.worse)}</div>
              <div className="sg-kpi-note">
                İki motorda da görünen {fmt(d.counts.compared)} sorgudan · yalnız Google'da {fmt(d.counts.onlyGoogle)}
              </div>
            </div>
          </section>

          <section className="sg-card">
            <h2>{LIST_LABEL[tab]}</h2>
            <p className="sg-sub">
              {tab === 'compare'
                ? d.google
                  ? `Google Search Console (${d.google.start} – ${d.google.end}) ve Bing (${d.queryPeriod.start ?? '—'} – ${d.queryPeriod.end ?? '—'}) sorguları. Bing sırası ${fmt(d.gap)} ya da daha çok gerideyse işaretlenir: ChatGPT bu sorguda kitabı bulmakta zorlanır.`
                  : 'Google Search Console verisi henüz okunmamış; karşılaştırma için önce Arama performansı ekranından okuyun.'
                : `Bing'in haftalık verisinden son 28 gün (${d.queryPeriod.start ?? '—'} – ${d.queryPeriod.end ?? '—'}). Sıra, gösterimle ağırlıklı ortalamadır.`}
            </p>
            <div className="sg-filters" role="group" aria-label="Liste">
              {(Object.keys(LIST_LABEL) as Array<Exclude<Kind, 'issues'>>).map((k) => (
                <button key={k} className="sg-filter" aria-pressed={tab === k} onClick={() => setTab(k)}>
                  {LIST_LABEL[k]}
                  <span className="sg-mono">{fmt(k === 'compare' ? d.counts.compared : k === 'queries' ? d.counts.queries : d.counts.pages)}</span>
                </button>
              ))}
              {tab === 'compare' && (
                <button className="sg-filter" aria-pressed={worse} onClick={() => setWorse(!worse)}>
                  Yalnız Bing'de çok geride
                  <span className="sg-mono">{fmt(d.counts.worse)}</span>
                </button>
              )}
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, margin: '12px 0' }}>
              <Search size={16} aria-hidden />
              <input
                type="search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={tab === 'pages' ? 'Adreste ara' : 'Sorguda ara'}
                aria-label="Ara"
                style={{ flex: 1, minHeight: 40, padding: '0 12px', border: '1px solid var(--sg-line)', borderRadius: 12, font: 'inherit', fontSize: 16 }}
              />
            </label>
            {list.error && <Failed error={list.error} />}
            {list.data && list.data.total === 0 && <p className="sg-sub">Bu süzgeçte kayıt yok.</p>}
            {list.data && list.data.total > 0 && (
              <div className="sg-table-wrap">
                {tab === 'compare' ? (
                  <table className="sg-table">
                    <thead>
                      <tr>
                        <th>Sorgu</th>
                        <th>Google sırası</th>
                        <th>Bing sırası</th>
                        <th>Fark</th>
                        <th>Google gösterim / tık</th>
                        <th>Bing gösterim / tık</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(list.data.items as CompareRow[]).map((r) => (
                        <tr key={r.query}>
                          <td style={{ minWidth: 160 }}>{r.query}</td>
                          <td className="sg-mono">{pos(r.google.position)}</td>
                          <td className="sg-mono">{pos(r.bing.position)}</td>
                          <td>
                            {r.gap == null ? '—' : <span className={`sg-chip ${r.worse ? 'bad' : r.gap > 0 ? 'mid' : 'good'}`}>{r.gap > 0 ? `+${fmt(r.gap, 1)}` : fmt(r.gap, 1)}</span>}
                          </td>
                          <td className="sg-mono">
                            {fmt(r.google.impressions)} / {fmt(r.google.clicks)}
                          </td>
                          <td className="sg-mono">
                            {fmt(r.bing.impressions)} / {fmt(r.bing.clicks)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <table className="sg-table">
                    <thead>
                      <tr>
                        <th>{tab === 'pages' ? 'Sayfa' : 'Sorgu'}</th>
                        <th>Tıklama</th>
                        <th>Gösterim</th>
                        <th>Oran</th>
                        <th>Ort. sıra</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(list.data.items as BingRow[]).map((r) => (
                        <tr key={r.key}>
                          <td style={{ minWidth: 160, wordBreak: 'break-word' }}>
                            {tab === 'pages' ? (
                              <a href={r.key} target="_blank" rel="noreferrer">
                                {r.key.replace(/^https?:\/\/[^/]+/, '') || '/'} <ExternalLink size={11} aria-hidden />
                              </a>
                            ) : (
                              r.key
                            )}
                          </td>
                          <td className="sg-mono">{fmt(r.clicks)}</td>
                          <td className="sg-mono">{fmt(r.impressions)}</td>
                          <td className="sg-mono">{pct(r.ctr)}</td>
                          <td className="sg-mono">{pos(r.position)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
            {list.data && <Pager start={start} total={list.data.total} onChange={setStart} />}
          </section>

          <section className="sg-card">
            <h2>Bing tarama sorunları</h2>
            <p className="sg-sub">Bing'in sitede karşılaştığı hatalar ve engeller. Düzeltmesi site yönetiminden yapılır.</p>
            {issues.error && <Failed error={issues.error} />}
            {issues.data && issues.data.total === 0 && <p className="sg-sub">{d.errors.issues ? 'Bing bu bölümü vermedi.' : 'Bing bir tarama sorunu bildirmiyor.'}</p>}
            {issues.data && issues.data.total > 0 && (
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Adres</th>
                      <th>Sorun</th>
                      <th>Yanıt</th>
                      <th>Gelen bağlantı</th>
                    </tr>
                  </thead>
                  <tbody>
                    {issues.data.items.map((r) => (
                      <tr key={r.url}>
                        <td style={{ minWidth: 180, wordBreak: 'break-word' }}>
                          <a href={r.url} target="_blank" rel="noreferrer">
                            {r.url.replace(/^https?:\/\/[^/]+/, '') || '/'} <ExternalLink size={11} aria-hidden />
                          </a>
                        </td>
                        <td>
                          <span style={{ display: 'inline-flex', flexWrap: 'wrap', gap: 4 }}>
                            {r.issues.map((i) => (
                              <span key={i} className="sg-chip bad">
                                {i}
                              </span>
                            ))}
                          </span>
                        </td>
                        <td className="sg-mono">{r.httpCode ?? '—'}</td>
                        <td className="sg-mono">{fmt(r.inLinks)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {issues.data && <Pager start={issueStart} total={issues.data.total} onChange={setIssueStart} />}
          </section>
        </>
      )}

      <section className="sg-card">
        <h2>IndexNow bildirimi</h2>
        <p className="sg-sub">
          Fiyatı, stoku, adı ya da SEO metni değişen, yeni eklenen ya da satıştan kalkan kitap sayfaları her gece Bing'e ve IndexNow'u destekleyen öteki arama motorlarına bildirilir; sayfa haftalar yerine günler içinde yeniden taranır. İlk gece yalnız mevcut durum kaydedilir, bildirim gitmez.
        </p>
        {ix.isLoading && <Loading text="IndexNow durumu getiriliyor…" />}
        {ix.error && <Failed error={ix.error} />}
        {x && !x.configured && (
          <p className="sg-banner">
            IndexNow anahtarı girilmemiş. Yönetim → SEO & GEO → “IndexNow anahtarı” alanına 8–128 karakterlik, yalnız harf, rakam ve tireden oluşan bir anahtar yazın (örneğin rastgele 32 harf/rakam).
          </p>
        )}
        {x && x.configured && !x.keyValid && <p className="sg-banner err">Anahtarın biçimi geçersiz: 8–128 karakter, yalnız harf, rakam ve tire olmalı.</p>}
        {x && x.configured && x.keyValid && (
          <>
            {x.keyFileOk ? (
              <p className="sg-banner ok">
                Anahtar dosyası sitede doğrulandı: <span className="sg-mono">{x.keyFileUrl}</span> · {dateTime(x.checkedAt)}
              </p>
            ) : (
              <div className="sg-banner err" style={{ display: 'grid', gap: 6 }}>
                <strong>Anahtar dosyası sitede bulunamadı; bildirim gönderilmez.</strong>
                {x.keyFileError && <span>{x.keyFileError}</span>}
                <span>
                  Site yöneticisi, sitenin köküne adı anahtarla aynı olan bir metin dosyası koymalı. Dosya şu adreste açılmalı: <span className="sg-mono">{x.keyFileUrl}</span>. Dosyanın içinde yalnız anahtarın kendisi yazmalı (başka metin, HTML ya da boşluk olmadan). Anahtarı Yönetim ekranındaki kişiden alın; bu sistem siteye dosya yazmaz.
                </span>
              </div>
            )}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', margin: '14px 0' }}>
              <button className="sg-button" onClick={() => setRecheck((n) => n + 1)} disabled={ix.isFetching}>
                {ix.isFetching ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
                Dosyayı yeniden denetle
              </button>
              <button className="sg-button primary" disabled={!canSubmit || sending || x.pending === 0} onClick={() => submit.mutate()}>
                {submit.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Send size={16} aria-hidden />}
                Bekleyenleri şimdi bildir ({fmt(x.pending)})
              </button>
              <button
                className="sg-button"
                disabled={!canSubmit || sending}
                onClick={() => {
                  if (window.confirm(`Satıştaki bütün kitap sayfaları (${fmt(x.tracked)}) bir kez bildirilecek. Bu yalnız ilk kurulumda ya da site taşındığında gerekir. Devam edilsin mi?`)) submitAll.mutate();
                }}
              >
                {submitAll.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Send size={16} aria-hidden />}
                Bütün kitapları bir kez bildir
              </button>
            </div>
            {!canApprove && me.data && <p className="sg-sub">Bildirim göndermek onay yetkisi ister (Yönetim → SEO & GEO → Onay verebilenler).</p>}
            <p className="sg-sub">
              İzlenen kitap sayfası {fmt(x.tracked)} · bildirim bekleyen {fmt(x.pending)}
              {x.baselineAt ? ` · izleme başlangıcı ${dateTime(x.baselineAt)}` : ' · izleme ilk gece başlar'} · bir istekte en çok {fmt(x.batchSize)} adres (IndexNow kuralı), fazlası sıradaki isteğe bölünür.
            </p>
          </>
        )}
        {(submit.error || submitAll.error) && <Failed error={submit.error || submitAll.error} />}
        {lastResult && (
          <p className={`sg-banner ${lastResult.batches.some((b) => b.error) ? 'err' : 'ok'}`}>
            {fmt(lastResult.submitted)} / {fmt(lastResult.urls)} adres bildirildi
            {lastResult.skipped ? ` · adresi olmayan ya da başka alan adındaki ${fmt(lastResult.skipped)} kitap atlandı` : ''}
            {lastResult.batches.filter((b) => b.error).map((b) => ` · ${b.error}`).join('')}
          </p>
        )}
        {x && x.logTotal > 0 && (
          <>
            <div className="sg-table-wrap" style={{ marginTop: 12 }}>
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Zaman</th>
                    <th>Tür</th>
                    <th>Adres</th>
                    <th>Sonuç</th>
                    <th>Kim</th>
                  </tr>
                </thead>
                <tbody>
                  {x.lastSubmissions.map((s) => (
                    <tr key={s.id}>
                      <td className="sg-mono">{dateTime(s.at)}</td>
                      <td>{KIND_LABEL[s.kind] ?? s.kind}</td>
                      <td className="sg-mono">{fmt(s.count)}</td>
                      <td>
                        <span className={`sg-chip ${s.error ? 'bad' : 'good'}`}>{s.error ?? s.statusText ?? 'Alındı'}</span>
                      </td>
                      <td>{s.by ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {x.logTotal > 20 && (
              <div className="sg-pager" style={{ marginTop: 12 }}>
                <button className="sg-button" disabled={logStart === 0} onClick={() => setLogStart(Math.max(0, logStart - 20))} aria-label="Önceki sayfa">
                  <ChevronLeft size={16} aria-hidden />
                </button>
                <span className="sg-mono">
                  {fmt(logStart + 1)}–{fmt(Math.min(x.logTotal, logStart + 20))} / {fmt(x.logTotal)}
                </span>
                <button className="sg-button" disabled={logStart + 20 >= x.logTotal} onClick={() => setLogStart(logStart + 20)} aria-label="Sonraki sayfa">
                  <ChevronRight size={16} aria-hidden />
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </SeoLayout>
  );
}
