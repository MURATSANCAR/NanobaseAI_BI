import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExternalLink, Loader2, RefreshCw, Search } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import type { Kaynaklar } from '../components/sqlInfo';
import { EmptyHint, Explain, ExplainLabel } from '../components/Explain';
import { Term, TermLabel } from './terms';
import SeoPager from './SeoPager';

const PAGE = 40;

type Stat = { clicks: number; impressions: number; position: number | null };
type IndexDay = { date: string; code2xx: number; code3xx: number; code4xx: number; code5xx: number; other: number };
type Problem = { code: string; label: string; severity: string; severityLabel: string; since: string | null };
type YandexSummary = {
  kaynaklar?: Kaynaklar;
  configured: boolean;
  site: string;
  running: boolean;
  error: string | null;
  lastRefresh: string | null;
  errors: Record<string, string>;
  summary: { sqi: number; searchable: number; excluded: number; problems: Record<string, number> } | null;
  totals: { start: string | null; end: string | null; clicks: number; impressions: number; ctr: number; prevClicks: number | null; prevImpressions: number | null };
  indexingLatest: IndexDay | null;
  problems: Problem[];
  counts: { queries: number; links: number; problems: number; compared: number; worse: number; onlyGoogle: number };
  google: { start: string | null; end: string | null; savedAt: string | null } | null;
  gap: number;
  period: number;
};
type CompareRow = { query: string; google: Stat; yandex: Stat; gap: number | null; worse: boolean };
type QueryRow = Stat & { key: string; ctr: number };
type LinkRow = { source: string; target: string; found: string | null; seen: string | null };
type Kind = 'compare' | 'queries' | 'links';
type ListOf<K extends Kind> = { total: number; start: number; items: K extends 'compare' ? CompareRow[] : K extends 'links' ? LinkRow[] : QueryRow[] };

const yandexApi = {
  summary: () => call<YandexSummary>('yandex'),
  list: <K extends Kind>(kind: K, p: { start: number; limit: number; q?: string; filter?: string }) => call<ListOf<K>>(`yandex/list/${kind}?${qs(p)}`),
  refresh: () => call<{ counts: Record<string, number>; errors: Record<string, string> }>('yandex/refresh', { method: 'POST', timeout: 600_000 }),
};

const LIST_LABEL: Record<Kind, string> = { compare: 'Google ile karşılaştırma', queries: 'Yandex sorguları', links: 'Dış bağlantılar' };
const SEV_CHIP: Record<string, string> = { FATAL: 'bad', CRITICAL: 'bad', POSSIBLE_PROBLEM: 'mid', RECOMMENDATION: 'good' };
const pct = (v: number) => `%${fmt(v * 100, 1)}`;
const pos = (v: number | null) => (v == null ? '—' : fmt(v, 1));
const path = (u: string) => u.replace(/^https?:\/\/[^/]+/, '') || '/';
const change = (cur: number, prev: number | null) => {
  if (prev == null || prev === 0) return 'Önceki dönem verisi yok';
  const d = ((cur - prev) / prev) * 100;
  return `Önceki 28 güne göre ${d >= 0 ? '+' : ''}${fmt(d, 1)}%`;
};

/** Yandex: Yandex Webmaster'dan yalnız okunan sorgu, trafik, dizin, teşhis ve dış bağlantı verisi; Google ile aynı
 *  sorguların sıra karşılaştırması. Yandex'e hiçbir şey gönderilmez (IndexNow bildirimi Bing ekranında). */
export default function SeoYandex() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<Kind>('compare');
  const [worse, setWorse] = useState(false);
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [start, setStart] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setQuery(q), 300);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => setStart(0), [tab, worse, query]);

  const summary = useQuery({ queryKey: ['seo-yandex'], queryFn: yandexApi.summary, enabled: ENGINE_ENABLED, retry: false });
  const configured = !!summary.data?.configured;
  const list = useQuery({
    queryKey: ['seo-yandex-list', tab, worse, query, start],
    queryFn: () => yandexApi.list(tab, { start, limit: PAGE, q: query, filter: tab === 'compare' && worse ? 'worse' : '' }),
    enabled: ENGINE_ENABLED && configured,
    retry: false,
    placeholderData: (p) => p,
  });
  const refresh = useMutation({
    mutationFn: yandexApi.refresh,
    onSuccess: () => qc.invalidateQueries({ predicate: (qq) => String(qq.queryKey[0]).startsWith('seo-yandex') }),
  });

  const d = summary.data;
  const k = d?.kaynaklar;
  const errorKinds = Object.entries(d?.errors ?? {});
  const busy = refresh.isPending || !!d?.running;

  return (
    <SeoLayout k={k}
      path="/seo-geo/yandex"
      crumb="Yandex"
      eyebrow="SEO & GEO · Yandex"
      title="Yandex"
      lead={<>Yandex’in yapay zekâ asistanı kendi arama dizinini kullanır: Yandex’te bulunmayan kitap orada da anılmaz. Yandex verisi yalnız okunur; değişen kitap sayfalarının bildirimi Bing ve IndexNow ekranından Yandex’e de gider. <Term k="indexnow" /></>}
      actions={
        configured ? (
          <button className="sg-button primary" onClick={() => refresh.mutate()} disabled={busy}>
            {busy ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {busy ? 'Yandex okunuyor…' : 'Yandex’ten yeniden oku'}
          </button>
        ) : undefined
      }
    >
      {summary.isLoading && <Loading text="Yandex verisi getiriliyor…" />}
      {summary.error && <Failed error={summary.error} />}
      {refresh.error && <Failed error={refresh.error} />}

      {d && !configured && (
        <section className="sg-card">
          <h2>Yandex bağlantısı kurulmamış <SeoInfo k={k} label="Yandex bağlantısı kurulmamış" /></h2>
          <p className="sg-sub">Bir kez yapılır; yalnız okuma izni kullanılır.</p>
          <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, lineHeight: 1.7 }}>
            <li>
              <a href="https://webmaster.yandex.com" target="_blank" rel="noreferrer">Yandex Webmaster</a>’da <span className="sg-mono">{d.site}</span> doğrulanmış olmalı ve jetonu alacak hesaba yetki verilmiş olmalı.
            </li>
            <li>
              <a href="https://oauth.yandex.com/client/new" target="_blank" rel="noreferrer">oauth.yandex.com</a>’da bir uygulama açın; izin olarak «Yandex.Webmaster → webmaster:hostinfo» seçin, yönlendirme adresi için «Hata ayıklama için» seçeneğini işaretleyin.
            </li>
            <li>Uygulamanın jeton bağlantısını aynı hesapla açıp izin verin; çıkan jetonu kopyalayın.</li>
            <li>Jetonu Yönetim → SEO & GEO → “Yandex Webmaster jetonu” alanına yapıştırın. Ertesi gece kendiliğinden okunur; bu ekrandan hemen de okunabilir.</li>
          </ol>
        </section>
      )}

      {d && configured && (
        <>
          {d.error && <p className="sg-banner err">{d.error}</p>}
          {errorKinds.length > 0 && !d.error && (
            <p className="sg-banner">Son okumada bazı bölümler alınamadı; eski hâlleri gösteriliyor: {errorKinds.map(([, m]) => m).filter((m, i, a) => a.indexOf(m) === i).join(' · ')}</p>
          )}
          {!d.lastRefresh && !d.error && <p className="sg-banner">Yandex henüz okunmadı. «Yandex’ten yeniden oku» ile hemen okutabilirsiniz; yoksa bu gece okunur.</p>}
          <section className="sg-kpis" aria-label="Özet">
            <div className="sg-kpi">
              <div className="sg-kpi-label">Yandex tıklaması (28 gün) <SeoInfo k={k} label="Yandex tıklaması (28 gün)" /> <Explain label="Yandex tıklaması">Son 28 günde Yandex sonuçlarından siteye gelen tıklama; altında önceki 28 güne göre değişim.</Explain></div>
              <div className="sg-kpi-value sg-mono">{fmt(d.totals.clicks)}</div>
              <div className="sg-kpi-note">{change(d.totals.clicks, d.totals.prevClicks)}</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Yandex gösterimi (28 gün) <SeoInfo k={k} label="Yandex gösterimi (28 gün)" /> <Term k="impressions" label="Yandex gösterimi" /></div>
              <div className="sg-kpi-value sg-mono">{fmt(d.totals.impressions)}</div>
              <div className="sg-kpi-note">
                {pct(d.totals.ctr)} tıklama oranı · son okuma {dateTime(d.lastRefresh)}
              </div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Yandex aramasındaki sayfa <SeoInfo k={k} label="Yandex aramasındaki sayfa" /> <Explain label="Yandex aramasındaki sayfa">Yandex aramasında çıkabilen timas.com.tr sayfası. Altında Yandex’in aramadan çıkardığı sayfa sayısı.</Explain></div>
              <div className="sg-kpi-value sg-mono">{fmt(d.summary?.searchable)}</div>
              <div className="sg-kpi-note">{d.summary ? `Aramadan çıkarılan ${fmt(d.summary.excluded)}` : 'Veri yok'}</div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Site kalite puanı <SeoInfo k={k} label="Site kalite puanı" /> <Explain label="Site kalite puanı">Yandex’in siteye verdiği kalite puanı (SQI): sitenin okurlar için ne kadar yararlı ve güvenilir olduğunu gösterir. Puan ne kadar yüksekse o kadar iyi.</Explain></div>
              <div className="sg-kpi-value sg-mono">{fmt(d.summary?.sqi)}</div>
              <div className="sg-kpi-note">
                {d.indexingLatest ? `${d.indexingLatest.date} taraması: ${fmt(d.indexingLatest.code4xx)} adet 4xx, ${fmt(d.indexingLatest.code5xx)} adet 5xx` : 'Tarama verisi yok'}
              </div>
            </div>
            <div className="sg-kpi">
              <div className="sg-kpi-label">Yandex'te çok geride <SeoInfo k={k} label="Yandex'te çok geride" /> <Explain label="Yandex'te çok geride">{`Hem Google’da hem Yandex’te görünen sorgulardan, Yandex sırası Google sırasından ${fmt(d.gap)} ya da daha çok geride olanlar.`}</Explain></div>
              <div className="sg-kpi-value sg-mono">{fmt(d.counts.worse)}</div>
              <div className="sg-kpi-note">
                İki motorda da görünen {fmt(d.counts.compared)} sorgudan · yalnız Google'da {fmt(d.counts.onlyGoogle)}
              </div>
            </div>
          </section>

          <section className="sg-card">
            <h2>Site teşhisi <SeoInfo k={k} label="Site teşhisi" /></h2>
            <p className="sg-sub">Yandex’in sitede şu an gördüğü sorunlar, önem sırasıyla. Düzeltme site tarafında yapılır; bu listeyi site yöneticisine iletin.</p>
            {d.problems.length === 0 ? (
              <p className="sg-sub">{d.errors.problems ? 'Yandex bu bölümü vermedi.' : d.lastRefresh ? 'Yandex bir sorun bildirmiyor.' : 'Henüz okunmadı.'}</p>
            ) : (
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Sorun</th>
                      <th>Önem</th>
                      <th>Ne zamandan beri</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.problems.map((p) => (
                      <tr key={p.code}>
                        <td style={{ minWidth: 200 }}>{p.label}</td>
                        <td><span className={`sg-chip ${SEV_CHIP[p.severity] ?? 'mid'}`}>{p.severityLabel}</span></td>
                        <td className="sg-mono">{p.since ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="sg-card">
            <h2>{LIST_LABEL[tab]}</h2>
            <p className="sg-sub">
              {tab === 'compare'
                ? d.google
                  ? `Google Search Console (${d.google.start} – ${d.google.end}) ve Yandex (son ${d.period} gün) sorguları. Yandex sırası ${fmt(d.gap)} ya da daha çok gerideyse kırmızı işaretlenir.`
                  : 'Google Search Console verisi henüz okunmamış; karşılaştırma için önce Arama ve kelimeler ekranından okutun.'
                : tab === 'queries'
                  ? `Yandex’te son ${d.period} günde siteyi gösteren aramalar. Sıra, ortalama gösterim sırasıdır.`
                  : 'Yandex’in bildiği, başka sitelerden timas.com.tr’ye verilen bağlantı örnekleri; en yeni bulunan önce. Yandex yalnız örnek verir, tam liste değildir.'}
            </p>
            <div className="sg-filters" role="group" aria-label="Liste">
              {(Object.keys(LIST_LABEL) as Kind[]).map((kk) => (
                <button key={kk} className="sg-filter" aria-pressed={tab === kk} onClick={() => setTab(kk)}>
                  {LIST_LABEL[kk]}
                  <span className="sg-mono">{fmt(kk === 'compare' ? d.counts.compared : kk === 'queries' ? d.counts.queries : d.counts.links)}</span>
                </button>
              ))}
              {tab === 'compare' && (
                <button className="sg-filter" aria-pressed={worse} onClick={() => setWorse(!worse)}>
                  Yalnız Yandex'te çok geride
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
                placeholder={tab === 'links' ? 'Adreste ara' : 'Sorguda ara'}
                aria-label="Ara"
                style={{ flex: 1, minHeight: 40, padding: '0 12px', border: '1px solid var(--sg-line)', borderRadius: 12, font: 'inherit', fontSize: 16 }}
              />
            </label>
            {list.error && <Failed error={list.error} />}
            {list.data && list.data.total === 0 && <EmptyHint title="Bu süzgeçte kayıt yok" why={query ? 'Aramayı kısaltın ya da temizleyin.' : 'Yandex bu dönem için veri vermedi ya da süzgece uyan kayıt yok. Site yeni eklendiyse veri birkaç gün içinde gelir.'} />}
            {list.data && list.data.total > 0 && (
              <div className="sg-table-wrap">
                {tab === 'compare' && (
                  <table className="sg-table">
                    <thead>
                      <tr>
                        <th>Sorgu</th>
                        <th>Google sırası</th>
                        <th>Yandex sırası</th>
                        <th><ExplainLabel label="Fark">Yandex sırası eksi Google sırası. Artı sayı, Yandex’te o kadar sıra geride olduğunuzu gösterir; kırmızı olanlar çok geride.</ExplainLabel></th>
                        <th>Google gösterim / tık</th>
                        <th>Yandex gösterim / tık</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(list.data.items as CompareRow[]).map((r) => (
                        <tr key={r.query}>
                          <td style={{ minWidth: 160 }}>{r.query}</td>
                          <td className="sg-mono">{pos(r.google.position)}</td>
                          <td className="sg-mono">{pos(r.yandex.position)}</td>
                          <td>
                            {r.gap == null ? '—' : <span className={`sg-chip ${r.worse ? 'bad' : r.gap > 0 ? 'mid' : 'good'}`}>{r.gap > 0 ? `+${fmt(r.gap, 1)}` : fmt(r.gap, 1)}</span>}
                          </td>
                          <td className="sg-mono">{fmt(r.google.impressions)} / {fmt(r.google.clicks)}</td>
                          <td className="sg-mono">{fmt(r.yandex.impressions)} / {fmt(r.yandex.clicks)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {tab === 'queries' && (
                  <table className="sg-table">
                    <thead>
                      <tr>
                        <th>Sorgu</th>
                        <th>Tıklama</th>
                        <th>Gösterim</th>
                        <th><TermLabel k="ctr" label="Oran" /></th>
                        <th><TermLabel k="position" label="Ort. sıra" /></th>
                      </tr>
                    </thead>
                    <tbody>
                      {(list.data.items as QueryRow[]).map((r) => (
                        <tr key={r.key}>
                          <td style={{ minWidth: 160, wordBreak: 'break-word' }}>{r.key}</td>
                          <td className="sg-mono">{fmt(r.clicks)}</td>
                          <td className="sg-mono">{fmt(r.impressions)}</td>
                          <td className="sg-mono">{pct(r.ctr)}</td>
                          <td className="sg-mono">{pos(r.position)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {tab === 'links' && (
                  <table className="sg-table">
                    <thead>
                      <tr>
                        <th>Bağlantı veren sayfa</th>
                        <th>Bizdeki sayfa</th>
                        <th>Bulunma</th>
                        <th>Son görülme</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(list.data.items as LinkRow[]).map((r) => (
                        <tr key={`${r.source}|${r.target}`}>
                          <td style={{ minWidth: 180, wordBreak: 'break-word' }}>
                            <a href={r.source} target="_blank" rel="noreferrer">{r.source} <ExternalLink size={11} aria-hidden /></a>
                          </td>
                          <td style={{ minWidth: 140, wordBreak: 'break-word' }}>
                            {r.target ? <a href={r.target} target="_blank" rel="noreferrer">{path(r.target)} <ExternalLink size={11} aria-hidden /></a> : '—'}
                          </td>
                          <td className="sg-mono">{r.found ?? '—'}</td>
                          <td className="sg-mono">{r.seen ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}
            {list.data && <SeoPager start={start} total={list.data.total} size={PAGE} onChange={setStart} />}
          </section>
        </>
      )}
    </SeoLayout>
  );
}
