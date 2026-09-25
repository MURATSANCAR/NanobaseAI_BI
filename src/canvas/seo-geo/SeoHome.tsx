import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Loader2, RefreshCw } from 'lucide-react';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ENGINE_ENABLED } from '../engine';
import { dateTime, fmt, seoApi, type Overview } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';

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
  const sync = useMutation({ mutationFn: seoApi.sync, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-overview'] }) });
  const batch = useMutation({ mutationFn: () => seoApi.batch(3600), onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-overview'] }) });
  const o = q.data;

  return (
    <SeoLayout
      path="/seo-geo"
      crumb="Genel bakış"
      eyebrow="SEO & GEO · timas.com.tr"
      title="Arama ve yapay zekâ görünürlüğü"
      lead="T-soft’taki ürünlerin SEO durumu, Google’daki performans ve onay bekleyen model önerileri. T-soft’tan yalnız okunur; mağazaya hiçbir şey gönderilmez."
      actions={
        o?.connections.tsoft && (
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
      {o && <Body o={o} onBatch={() => batch.mutate()} batchPending={batch.isPending} />}
    </SeoLayout>
  );
}

function Body({ o, onBatch, batchPending }: { o: Overview; onBatch: () => void; batchPending: boolean }) {
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
        <Kpi label="T-soft ürünü" value={fmt(o.products)} note={o.lastSync ? `Son okuma ${dateTime(o.lastSync.finishedAt || o.lastSync.startedAt)}` : 'Henüz okunmadı'} />
        <Kpi label="Ortalama puan" value={o.activeAverage == null ? '—' : fmt(o.activeAverage, 1)} unit="/100" note="Aktif ürünler" />
        <Kpi label="Düzeltilmesi gereken" value={fmt(o.failing)} note={`Puanı ${o.failingThreshold}’in altında`} />
        <Kpi label="Onay bekleyen öneri" value={fmt(waiting)} note={`Bu hafta onaylanan ${fmt(o.approvedThisWeek)}`} />
        <Kpi
          label="Google tıklaması"
          value={o.search ? fmt(clicks) : '—'}
          note={o.search ? `${o.search.start} – ${o.search.end} · ort. sıra ${fmt(position, 1)}` : 'Search Console bağlı değil'}
        />
      </section>

      <div className="sg-grid">
        <section className="sg-card sg-span-7">
          <h2>Google’dan gelen tıklama</h2>
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
          <h2>Sorunlar kurala göre</h2>
          <p className="sg-sub">Aktif ürünlerde kaç ürünün o sorunu taşıdığı. Tıklayınca ürünler süzülür.</p>
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
            <p className="sg-banner">Ürünler henüz okunmadı.</p>
          )}
        </section>

        <section className="sg-card sg-span-6">
          <h2>İş listesi</h2>
          <p className="sg-sub">Karar bekleyen işler.</p>
          <div className="sg-bars">
            <Todo to="/seo-geo/urun-denetimi?durum=hazir" label="Onay bekleyen model önerisi" n={waiting} />
            <Todo to="/seo-geo/urun-denetimi" label={`Puanı ${o.failingThreshold}’in altındaki ürün`} n={o.failing} />
            <Todo to="/seo-geo/gecmis" label="Onaylanan öneri (CRM bağlantısını bekliyor)" n={o.proposals.onaylandi ?? 0} />
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap', marginTop: 14 }}>
            <button className="sg-button" onClick={onBatch} disabled={batchPending || o.batch.running || !o.products}>
              {o.batch.running ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
              {o.batch.running ? 'Öneriler yazılıyor' : 'Önerileri önceden üret (1 saat)'}
            </button>
            <span style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
              {o.batch.startedAt
                ? `${o.batch.running ? 'Sürüyor' : 'Son tur'}: ${fmt(o.batch.done)} öneri${o.batch.queue != null ? ` / ${fmt(o.batch.queue)} sırada` : ''}${o.batch.failed ? ` · ${fmt(o.batch.failed)} üretilemedi` : ''}${o.batch.error ? ` · ${o.batch.error}` : ''}`
                : 'Her gece eşitlemeden sonra puanı en düşük üründen başlayarak öneriler hazırlanır.'}
            </span>
          </div>
        </section>

        <section className="sg-card sg-span-6">
          <h2>Bağlantı durumu</h2>
          <p className="sg-sub">Ayrıntı ve kurulum adımları Bağlantılar ekranında.</p>
          <div className="sg-bars">
            <Conn label="T-soft mağazası" ok={o.connections.tsoft} />
            <Conn label="Search Console" ok={o.connections.google} extra={o.connections.gscSite ?? undefined} />
            <Conn label="Google Analytics 4" ok={o.connections.google && o.connections.ga4} />
            <Conn label="Merchant Center" ok={o.connections.google && o.connections.merchant} />
          </div>
        </section>
      </div>
    </>
  );
}

function Kpi({ label, value, unit, note }: { label: string; value: string; unit?: string; note: string }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono">
        {value}
        {unit && <small>{unit}</small>}
      </div>
      <div className="sg-kpi-note">{note}</div>
    </div>
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
