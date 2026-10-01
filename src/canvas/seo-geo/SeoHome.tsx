import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Loader2, RefreshCw } from 'lucide-react';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, seoApi, type Overview, type WithK } from './api';
import type { Ga4Overview } from './SeoSearchToSales';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';
import { EmptyHint, Explain } from '../components/Explain';
import { TermLabel } from './terms';

/** Genel bakış: ürün puanları, kural dağılımı, onay bekleyenler, Search Console özeti, bağlantılar. Veri yoksa
 *  örnek göstermez; ne eksikse onu söyler. */
export default function SeoHome() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['seo-overview'],
    queryFn: seoApi.overview,
    enabled: ENGINE_ENABLED,
    retry: false,
    // Eşitleme sürerken sayaç ekranda ilerlesin.
    refetchInterval: (query) => (query.state.data?.sync.running ? 3000 : query.state.data?.batch.running ? 15000 : false),
  });
  // T-soft okuma «SEO eşitleme ve ölçüm», toplu öneri «SEO önerisi üretme» ister.
  const canRun = useCan('seo.calistir');
  const canPropose = useCan('seo.oneri-uret');
  const sync = useMutation({ mutationFn: seoApi.sync, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-overview'] }) });
  const batch = useMutation({ mutationFn: () => seoApi.batch(3600), onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-overview'] }) });
  const o = q.data;

  return (
    <SeoLayout k={q.data?.kaynaklar}
      path="/seo-geo"
      crumb="SEO özeti"
      eyebrow="SEO & GEO · TIMAS.COM.TR"
      title="Arama ve yapay zekâ görünürlüğü"
      lead="Kitap sayfalarının Google’a ne kadar hazır olduğu, Google’dan gelen ziyaret ve Zeki AI’ın onayınızı bekleyen önerileri. T-soft’tan yalnız okunur; mağazaya hiçbir şey gönderilmez."
      actions={
        o?.connections.tsoft && canRun && (
          <button className="sg-button" onClick={() => sync.mutate()} disabled={sync.isPending || o.sync.running}>
            {o.sync.running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {o.sync.running ? `Okunuyor ${fmt(o.sync.done)}${o.sync.total ? ` / ${fmt(o.sync.total)}` : ''}` : 'T-soft’tan yeniden oku'}
          </button>
        )
      }
    >
      {q.isLoading && <Loading text="Durum getiriliyor…" />}
      {q.error && <Failed error={q.error} />}
      {sync.error && <Failed error={sync.error} />}
      {batch.error && <Failed error={batch.error} />}
      {o && <Body o={o} onBatch={canPropose ? () => batch.mutate() : undefined} batchPending={batch.isPending} />}
    </SeoLayout>
  );
}

function Body({ o, onBatch, batchPending }: { o: Overview & WithK; onBatch?: () => void; batchPending: boolean }) {
  const waiting = o.proposals.hazir ?? 0;
  const daily = o.search?.rows ?? [];
  const clicks = daily.reduce((a, r) => a + r.clicks, 0);
  const impressions = daily.reduce((a, r) => a + r.impressions, 0);
  const position = impressions ? daily.reduce((a, r) => a + r.position * r.impressions, 0) / impressions : null;
  const maxRule = Math.max(1, ...o.rules.map((r) => r.count));

  return (
    <>
      {!o.connections.tsoft && (
        <p className="sg-banner">
          T-soft bağlantısı tanımlı değil. <Link to="/seo-geo/baglantilar">Bağlantılar</Link> ekranından kullanıcıyı girin; ürünler ilk okumadan sonra burada puanlanır.
        </p>
      )}
      {o.lastSync?.error && <p className="sg-banner err">Son T-soft okuması başarısız: {o.lastSync.error}</p>}
      {o.sync.error && !o.lastSync?.error && <p className="sg-banner err">{o.sync.error}</p>}

      <section className="sg-kpis" aria-label="Özet">
        <Kpi label="T-soft ürünü" value={fmt(o.products)} note={o.lastSync ? `Son okuma ${dateTime(o.lastSync.finishedAt || o.lastSync.startedAt)}` : 'Henüz okunmadı'} info={<SeoInfo k={o.kaynaklar} label="T-soft ürünü" />}
          explain="T-soft mağazasından son okumada gelen ürün sayısı. Puanlar ve sorunlar bu ürünler üzerinden hesaplanır." />
        <Kpi label="Ortalama puan" value={o.activeAverage == null ? '—' : fmt(o.activeAverage, 1)} unit="/100" note="Aktif ürünler" info={<SeoInfo k={o.kaynaklar} label="Ortalama puan" />}
          explain="Satışta (aktif) ürünlerin SEO puanlarının ortalaması. Her ürün 100 puanla başlar; başlık, açıklama, görsel, ISBN gibi her eksik kendi ağırlığı kadar puan düşürür." />
        <Kpi label="Düzeltilmesi gereken" value={fmt(o.failing)} note={`Puanı ${o.failingThreshold}’in altında`} info={<SeoInfo k={o.kaynaklar} label="Düzeltilmesi gereken" />}
          explain={`SEO puanı ${o.failingThreshold}’in altında kalan ürün sayısı. Bunlar Ürün denetimi ekranında en çok satandan başlayarak sıralanır.`} />
        <Kpi label="Onay bekleyen öneri" value={fmt(waiting)} note={`Bu hafta onaylanan ${fmt(o.approvedThisWeek)}`} info={<SeoInfo k={o.kaynaklar} label="Onay bekleyen öneri" />}
          explain="Zeki AI’ın hazırladığı, henüz kimsenin onaylamadığı ya da reddetmediği başlık ve açıklama önerileri. Ürün denetimi ekranında karar verilir; onay yalnız kayda geçer." />
        <Kpi
          label="Google tıklaması"
          value={o.search ? fmt(clicks) : '—'}
          note={o.search ? `${o.search.start} – ${o.search.end} · ort. sıra ${fmt(position, 1)}` : 'Search Console bağlı değil'} info={<SeoInfo k={o.kaynaklar} label="Google tıklaması" />}
          explain="Search Console’a göre bu tarih aralığında Google sonuçlarından siteye gelen toplam tıklama. «Ort. sıra», sitenin Google’da ortalama kaçıncı çıktığıdır (1 en üst); çok görünen aramalar daha çok sayılır." />
      </section>

      {o.connections.ga4 && <Ga4Card />}

      <div className="sg-grid">
        <section className="sg-card sg-span-7">
          <h2>Google’dan gelen tıklama <SeoInfo k={o.kaynaklar} label="Google’dan gelen tıklama" /></h2>
          <p className="sg-sub">Search Console, günlük; son 3 gün Google’da henüz kesinleşmediği için dahil değil.</p>
          {daily.length ? (
            <div className="sg-chart">
              <ResponsiveContainer>
                <AreaChart data={daily.map((r) => ({ d: r.keys[0].slice(5), c: r.clicks }))} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                  <defs>
                    <linearGradient id="sgArea" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ff6b4a" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#7c5cff" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="d" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={40} />
                  <Tooltip formatter={(v: number) => [fmt(v), 'Tıklama']} />
                  <Area type="monotone" dataKey="c" stroke="#ff6b4a" strokeWidth={2} fill="url(#sgArea)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="sg-banner">
              Search Console verisi yok. Servis hesabı <Link to="/seo-geo/baglantilar">Bağlantılar</Link> ekranında tanımlanınca her gece okunur.
            </p>
          )}
        </section>

        <section className="sg-card sg-span-5">
          <h2>En sık sorunlar <SeoInfo k={o.kaynaklar} label="En sık sorunlar" /></h2>
          <p className="sg-sub">Satıştaki ürünlerden kaçında o sorun var. Renk sorunun ağırlığını gösterir (kırmızı en ağır). Bir satıra dokunun, o ürünler listelensin.</p>
          {o.products ? (
            <div className="sg-bars">
              {o.rules
                .filter((r) => r.count > 0)
                .sort((a, b) => b.count - a.count)
                .map((r) => (
                  <Link key={r.rule} className="sg-bar-row" to={`/seo-geo/urun-denetimi?kural=${r.rule}`}>
                    <span style={{ display: 'flex', gap: 8, alignItems: 'center', minWidth: 0 }}>
                      <i className={`sg-dot ${r.severity}`} aria-hidden />
                      {r.title}
                    </span>
                    <span className="sg-mono">{fmt(r.count)}</span>
                    <span className="sg-bar">
                      <i style={{ width: `${(r.count / maxRule) * 100}%` }} />
                    </span>
                  </Link>
                ))}
            </div>
          ) : (
            <EmptyHint title="Ürünler henüz okunmadı" why="T-soft’tan ilk okuma bitince her ürün puanlanır ve sorunlar burada sayılır. Okuma her gece kendiliğinden yapılır." />
          )}
        </section>

        <section className="sg-card sg-span-12">
          <h2>Önce düzeltilecek kitaplar <SeoInfo k={o.kaynaklar} label="Önce düzeltilecek kitaplar" /></h2>
          <p className="sg-sub">Puanı 70’in altındaki kitaplardan en çok satan 10’u. Düzeltme en çok okura buradan ulaşır; kitabın adına dokunup önerisini açın.</p>
          {o.priority.length ? (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr>
                    <th>Kitap</th>
                    <th style={{ textAlign: 'right' }}>Satış</th>
                    <th style={{ textAlign: 'right' }}>Görüntülenme</th>
                    <th style={{ textAlign: 'right' }}><TermLabel k="score" label="Puan" /></th>
                  </tr>
                </thead>
                <tbody>
                  {o.priority.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(r.id)}`}>{r.name}</Link>
                      </td>
                      <td className="num">{fmt(r.sales)}</td>
                      <td className="num">{fmt(r.views)}</td>
                      <td className="num">{r.score}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyHint title="Öncelikli kitap yok" why={o.products ? 'Puanı 70’in altında kalan satıştaki kitap bulunmadı.' : 'Ürünler henüz okunmadı; ilk okumadan sonra liste dolar.'} />
          )}
        </section>

        <section className="sg-card sg-span-6">
          <h2>İş listesi <SeoInfo k={o.kaynaklar} label="İş listesi" /></h2>
          <p className="sg-sub">Karar bekleyen işler; satıra dokunup ilgili listeye gidin. Bütün SEO işleri tek sırada İş listesi ekranındadır.</p>
          <div className="sg-bars">
            <Todo to="/seo-geo/urun-denetimi?durum=hazir" label="Onay bekleyen Zeki AI önerisi" n={waiting} />
            <Todo to="/seo-geo/urun-denetimi" label={`Puanı ${o.failingThreshold}’in altındaki ürün`} n={o.failing} />
            <Todo to="/seo-geo/gecmis" label="Onaylanan öneri (kayıtta; hiçbir yere gönderilmez)" n={o.proposals.onaylandi ?? 0} />
            {o.crm.books > 0 && (
              <>
                <Todo to="/seo-geo/crm-haklar?suzgec=durum" label="CRM’de artık bizim değil / çekildi, sitede satışta" n={Object.values(o.crm.flags ?? {}).reduce((a, n) => a + (n ?? 0), 0)} />
                <Todo to="/seo-geo/crm-haklar?suzgec=eksik" label="İnternette gösterim hakkı eksik" n={o.crm.rights?.eksik ?? 0} />
              </>
            )}
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginTop: 14 }}>
            {onBatch && <button className="sg-button" onClick={onBatch} disabled={batchPending || o.batch.running || !o.products}>
              {o.batch.running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
              {o.batch.running ? 'Öneriler hazırlanıyor' : 'Önerileri şimdi hazırlat (1 saat)'}
            </button>}
            <span style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
              {o.batch.startedAt
                ? `${o.batch.running ? 'Sürüyor' : 'Son tur'}: ${fmt(o.batch.done)} öneri${o.batch.queue != null ? ` / ${fmt(o.batch.queue)} sırada` : ''}${o.batch.failed ? ` · ${fmt(o.batch.failed)} üretilemedi` : ''}${o.batch.error ? ` · ${o.batch.error}` : ''}`
                : 'Her gece eşitlemeden sonra önerisi olmayan sorunlu ürünler için, en çok satandan başlayarak öneriler hazırlanır.'}
            </span>
          </div>
        </section>

        <section className="sg-card sg-span-6">
          <h2>Bağlantı durumu <SeoInfo k={o.kaynaklar} label="Bağlantı durumu" /></h2>
          <p className="sg-sub">Bu ekranın verisini aldığı yerler. «Tanımlı değil» olan kaynağın verisi boş görünür; kurulum adımları Bağlantılar ekranında.</p>
          <div className="sg-bars">
            <Conn label="T-soft mağazası" ok={o.connections.tsoft} />
            <Conn label="Search Console" ok={o.connections.google} extra={o.connections.gscSite ?? undefined} />
            <Conn label="Google Analytics 4" ok={o.connections.google && o.connections.ga4} />
            <Conn label="Merchant Center" ok={o.connections.google && o.connections.merchant} />
            <Conn label="CRM kitap kartı (yalnız okuma)" ok={o.crm.books > 0} extra={o.crm.lastRead ? `Son okuma ${dateTime(o.crm.lastRead)}` : undefined} />
          </div>
        </section>
      </div>
    </>
  );
}

function Kpi({ label, value, unit, note, info, explain }: { label: string; value: string; unit?: string; note: string; info?: ReactNode; explain?: ReactNode }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}{explain ? <> <Explain label={label}>{explain}</Explain></> : null}</div>
      <div className="sg-kpi-value sg-mono">
        {value}
        {unit && <small>{unit}</small>}
      </div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}

/** Aramadan satışa özeti: organik ciro ve değişimi; yalnız okunmuş veri varsa görünür. */
function Ga4Card() {
  const q = useQuery({ queryKey: ['seo-ga4'], queryFn: () => call<Ga4Overview>('ga4'), enabled: ENGINE_ENABLED, retry: false });
  const org = q.data?.snapshot?.organic;
  if (!org) return null;
  const ch = org.change.revenue;
  const share = q.data?.snapshot?.share?.revenue;
  return (
    <Link to="/seo-geo/aramadan-satisa" className="sg-card" style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', justifyContent: 'space-between', textDecoration: 'none', color: 'inherit' }}>
      <span style={{ minWidth: 0 }}>
        <span className="sg-kpi-label" style={{ display: 'block' }}>Google aramasından gelen ciro · son 28 gün</span>
        <span className="sg-kpi-value sg-mono" style={{ display: 'block' }}>{fmt(org.cur.revenue)} ₺</span>
        <span className="sg-kpi-note" style={{ display: 'block', color: ch == null ? undefined : ch >= 0 ? '#0f7a51' : '#c2361b' }}>
          {ch == null ? 'Önceki dönem yok' : `${ch >= 0 ? '+' : ''}${fmt(ch, 1)}% önceki 28 güne göre`} · {fmt(org.cur.sessions)} ziyaret, {fmt(org.cur.purchases)} satış
          {share != null ? ` · toplam cironun %${fmt(share * 100, 1)}’i` : ''}
        </span>
      </span>
      <span className="sg-button">
        Aramadan satışa <ArrowRight size={14} aria-hidden />
      </span>
    </Link>
  );
}

function Todo({ to, label, n }: { to: string; label: string; n: number }) {
  return (
    <Link to={to} className="sg-bar-row" style={{ padding: '8px 0', borderBottom: '1px solid var(--sg-line)' }}>
      <span>{label}</span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
        <b className="sg-mono">{fmt(n)}</b>
        <ArrowRight size={14} aria-hidden />
      </span>
    </Link>
  );
}

function Conn({ label, ok, extra }: { label: string; ok: boolean; extra?: string }) {
  return (
    <div className="sg-bar-row" style={{ padding: '8px 0', borderBottom: '1px solid var(--sg-line)' }}>
      <span>
        {label}
        {extra && <span className="sg-mono" style={{ marginLeft: 8, fontSize: 11, color: 'var(--sg-muted)' }}>{extra}</span>}
      </span>
      <span className={`sg-chip ${ok ? 'good' : ''}`}>{ok ? 'Tanımlı' : 'Tanımlı değil'}</span>
    </div>
  );
}
