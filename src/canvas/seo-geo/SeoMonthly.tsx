import type { Kaynaklar } from '../components/sqlInfo';
import type { ReactNode } from 'react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Area, AreaChart, Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Download, FileText, Loader2, Send } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { call, dateTime, fmt, qs, seoApi } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';
import { useCan } from '../useAdmin';

/** Aylık yönetim raporu: önceki takvim ayının SEO & GEO özeti, PDF olarak; gece kendiliğinden hazırlanır, alıcı
 *  tanımlıysa e-postayla gider. */

type Period = { month: string; available: boolean; reason?: string; source?: string; clicks?: number; impressions?: number; ctr?: number | null; position?: number | null };
type Mover = { key: string; clicks: number; prevClicks: number; delta: number };
type Movers = { available: boolean; reason?: string; top?: number; gainers?: Mover[]; losers?: Mover[]; gainersTotal?: number; losersTotal?: number };
type Kpis = { clicks?: number | null; impressions?: number | null; ctr?: number | null; position?: number | null; share80?: number | null; techIssues?: number | null; geoMention?: number | null; alertsOpen?: number | null };
type GeoEngine = { engine: string; label: string; measured: number; mentioned: number; mentionRate: number | null };
type Summary = {
  month: string;
  label: string;
  generatedAt: string;
  complete: boolean;
  google: { current: Period; previous: Period; lastYear: Period; daily: Array<{ d: string; clicks: number; impressions: number }> };
  queries: Movers;
  pages: Movers;
  books: { top: number; threshold: number; counted: number; good: number; share: number | null; active: number; activeGood: number; activeShare: number | null };
  proposals: { created: number; approved: number; rejected: number; pending: number };
  crm: { available: boolean; rights?: Record<string, number>; flags?: Record<string, number>; labels?: Record<string, string>; flagLabels?: Record<string, string> };
  tech: { available: boolean; checked?: number; issues?: Array<{ id: string; title: string; severity: string; count: number; previous: number | null }> };
  geo: { engines: GeoEngine[]; previous: GeoEngine[] };
  alerts: { available: boolean; open?: number; bySeverity?: Record<string, number>; openedInMonth?: number; resolvedInMonth?: number; items?: Array<{ id: string; severity: string; title: string; link: string | null }> };
  worklist: { available: boolean; total?: number; byStatus?: Record<string, number>; changedInMonth?: number | null };
  kpi: Kpis;
  trend: Array<{ month: string } & Kpis>;
};
type ReportMeta = { month: string; label: string; complete: boolean; createdAt: string | null; createdBy: string | null; sentAt: string | null; sentTo: string | null; sendResult: string | null; hasPdf: boolean; kpi: Kpis };
type MonthlyPage = {
  items: ReportMeta[];
  selected: (ReportMeta & { summary: Summary }) | null;
  defaultMonth: string;
  settings: { recipients: number; smtp: boolean; google: boolean };
  state: { running: boolean; month: string | null; error: string | null };
};

const monthlyApi = {
  get: (month: string) => call<MonthlyPage>(`monthly?${qs({ month })}`),
  build: (month: string) => call<ReportMeta & { summary: Summary }>(`monthly/build?${qs({ month })}`, { method: 'POST', timeout: 600_000 }),
  send: (month: string) => call<{ result: string }>(`monthly/${month}/send`, { method: 'POST', timeout: 120_000 }),
  pdfUrl: (month: string) => `${ENGINE_BASE}/api/v1/seo-geo/monthly/${month}.pdf`,
};

const MONTHS = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
const shortMonth = (m: string) => `${MONTHS[Number(m.slice(5, 7)) - 1]} ${m.slice(2, 4)}`;
const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `%${fmt(v * 100, digits)}`);
const change = (cur?: number | null, ref?: number | null) => (cur == null || ref == null || !ref ? null : cur / ref - 1);
const signed = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}%${fmt(Math.abs(v) * 100, 1)}`);
const SEND_LABEL: Record<string, string> = {
  no_recipient: 'Alıcı tanımlı değil; yalnız ekranda',
  no_smtp: 'E-posta sunucusu tanımlı değil',
  failed: 'Gönderilemedi; sonraki gece yeniden denenecek',
};

export default function SeoMonthly() {
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [month, setMonth] = useState('');
  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const page = useQuery({ queryKey: ['seo-monthly', month], queryFn: () => monthlyApi.get(month), enabled: ENGINE_ENABLED, retry: false, placeholderData: (p) => p });
  const d = page.data;
  const [buildMonth, setBuildMonth] = useState('');
  const target = buildMonth || d?.defaultMonth || '';
  const build = useMutation({
    mutationFn: () => monthlyApi.build(target),
    onSuccess: (r) => {
      setMonth(r.month);
      qc.invalidateQueries({ queryKey: ['seo-monthly'] });
    },
  });
  const sel = d?.selected ?? null;
  const send = useMutation({ mutationFn: () => monthlyApi.send(sel!.month), onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-monthly'] }) });
  const canApprove = !!me.data?.canApprove;
  const blocked = !sel
    ? 'Önce raporu hazırlayın.'
    : !canApprove
      ? 'Göndermek onay yetkisi ister.'
      : !d?.settings.recipients
        ? 'Aylık rapor alıcısı tanımlı değil (Yönetim → SEO & GEO).'
        : !d?.settings.smtp
          ? 'E-posta sunucusu tanımlı değil (Yönetim → Uyarılar).'
          : null;

  return (
    <SeoLayout k={page.data?.kaynaklar}
      path="/seo-geo/aylik-rapor"
      crumb="Aylık rapor"
      eyebrow="SEO & GEO · yönetim"
      title="Aylık rapor"
      lead="Her ayın ilk gecesi bir önceki takvim ayının (İstanbul saati) özeti hazırlanır: Google’dan gelen tıklama ve gösterim, en çok değişen sorgu ve sayfalar, kitap sayfalarının durumu, öneri kararları, haklar, teknik sorunlar, yapay zekâ cevaplarında anılma ve uyarılar. Google’ın son günleri birkaç gün geç kesinleştiği için rapor kesinleşince yeniden hazırlanır ve alıcı tanımlıysa bir kez e-postayla gider."
      actions={
        canRun && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <input type="month" className="sg-button" value={target} max={d?.defaultMonth} onChange={(e) => setBuildMonth(e.target.value)} aria-label="Rapor ayı" style={{ minHeight: 44 }} />
            <button className="sg-button primary" onClick={() => build.mutate()} disabled={!target || build.isPending || !!d?.state.running}>
              {build.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <FileText size={16} aria-hidden />}
              {build.isPending ? 'Hazırlanıyor…' : 'Raporu hazırla'}
            </button>
          </div>
        )
      }
    >
      {page.isLoading && <Loading text="Raporlar getiriliyor…" />}
      {page.error && <Failed error={page.error} />}
      {build.error && <Failed error={build.error} />}
      {d?.state.error && <p className="sg-banner err">Son hazırlık başarısız: {d.state.error}</p>}

      {d && !d.items.length && (
        <section className="sg-empty">
          <h2>Henüz rapor yok</h2>
          <p>İlk rapor ayın ilk gecesi kendiliğinden hazırlanır{canRun ? '; isterseniz yukarıdan bir ay seçip şimdi hazırlayın.' : '.'}</p>
        </section>
      )}

      {d && sel && (
        <>
          <section className="sg-card" aria-label="Rapor">
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
              <div style={{ minWidth: 0 }}>
                <h2 style={{ margin: 0 }}>{sel.label}</h2>
                <p className="sg-kpi-note" style={{ margin: '4px 0 0' }}>
                  Hazırlandı {dateTime(sel.createdAt)}
                  {sel.createdBy ? ` · ${sel.createdBy}` : ''} · {sel.sentAt ? `Gönderildi ${dateTime(sel.sentAt)}` : sel.sendResult ? SEND_LABEL[sel.sendResult] ?? 'Gönderilmedi' : 'Gönderilmedi'}
                </p>
                {!sel.complete && <p className="sg-kpi-note" style={{ margin: '4px 0 0' }}>Google’ın son günleri henüz kesinleşmedi; rapor kesinleşince yeniden hazırlanır.</p>}
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                <a className="sg-button" href={monthlyApi.pdfUrl(sel.month)}>
                  <Download size={16} aria-hidden /> PDF indir
                </a>
                <button className="sg-button" onClick={() => send.mutate()} disabled={!!blocked || send.isPending} title={blocked ?? undefined}>
                  {send.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Send size={16} aria-hidden />}
                  E-postayla gönder
                </button>
              </div>
            </div>
            {blocked && sel && <p className="sg-kpi-note" style={{ margin: '8px 0 0' }}>{blocked}</p>}
            {send.error && <div style={{ marginTop: 8 }}><Failed error={send.error} /></div>}
            {send.data && <p className="sg-banner ok" role="status" style={{ marginTop: 8 }}>Rapor {fmt(d.settings.recipients)} alıcıya gönderildi.</p>}
          </section>
          <ReportView s={sel.summary} k={page.data?.kaynaklar} />
        </>
      )}

      {d && d.items.length > 0 && (
        <section className="sg-card" aria-label="Geçmiş raporlar" style={{ marginTop: 16 }}>
          <h2>Raporlar <SeoInfo k={page.data?.kaynaklar} label="Raporlar" /></h2>
          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr>
                  <th>Ay</th>
                  <th>Tıklama <SeoInfo k={page.data?.kaynaklar} label="Tıklama" /></th>
                  <th>Puanı 80+ (çok satan) <SeoInfo k={page.data?.kaynaklar} label="Puanı 80+ (çok satan)" /></th>
                  <th>Gönderim</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {d.items.map((r) => (
                  <tr key={r.month} aria-current={sel?.month === r.month ? 'true' : undefined}>
                    <td>
                      <button className="sg-filter" aria-pressed={sel?.month === r.month} onClick={() => setMonth(r.month)}>
                        {r.label}
                      </button>
                    </td>
                    <td className="num">{fmt(r.kpi.clicks)}</td>
                    <td className="num">{pct(r.kpi.share80, 0)}</td>
                    <td>{r.sentAt ? dateTime(r.sentAt) : r.sendResult ? SEND_LABEL[r.sendResult] ?? 'Gönderilmedi' : r.complete ? 'Gönderilmedi' : 'Veri kesinleşmedi'}</td>
                    <td>
                      <a href={monthlyApi.pdfUrl(r.month)}>PDF</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </SeoLayout>
  );
}

function ReportView({ s, k }: { s: Summary; k?: Kaynaklar | null }) {
  const g = s.google;
  const cur = g.current;
  const trend = s.trend ?? [];
  return (
    <>
      <section className="sg-kpis" aria-label="Google arama" style={{ marginTop: 16 }}>
        {cur.available ? (
          <>
            <Kpi label="Tıklama" value={fmt(cur.clicks)} cur={cur.clicks} prev={g.previous} ly={g.lastYear} k="clicks" info={<SeoInfo k={k} label="Tıklama" />} />
            <Kpi label="Gösterim" value={fmt(cur.impressions)} cur={cur.impressions} prev={g.previous} ly={g.lastYear} k="impressions" info={<SeoInfo k={k} label="Gösterim" />} />
            <Kpi label="Tıklama oranı" value={pct(cur.ctr, 2)} cur={cur.ctr} prev={g.previous} ly={g.lastYear} k="ctr" info={<SeoInfo k={k} label="Tıklama oranı" />} />
            <Kpi label="Ortalama sıra" value={cur.position == null ? '—' : fmt(cur.position, 1)} cur={cur.position} prev={g.previous} ly={g.lastYear} k="position" lowerBetter info={<SeoInfo k={k} label="Ortalama sıra" />} />
          </>
        ) : (
          <div className="sg-kpi">
            <div className="sg-kpi-label">Google arama</div>
            <div className="sg-kpi-value">—</div>
            <div className="sg-kpi-note">{cur.reason ?? 'Veri yok.'}</div>
          </div>
        )}
      </section>

      <div className="sg-grid" style={{ marginTop: 16 }}>
        <section className="sg-card sg-span-7">
          <h2>Günlük tıklama <SeoInfo k={k} label="Günlük tıklama" /></h2>
          <p className="sg-sub">{s.label}</p>
          {g.daily?.length > 1 ? (
            <div className="sg-chart">
              <ResponsiveContainer>
                <AreaChart data={g.daily.map((r) => ({ d: r.d.slice(8, 10), c: r.clicks }))} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                  <defs>
                    <linearGradient id="sgMonthlyArea" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#ff6b4a" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#7c5cff" stopOpacity={0.02} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="d" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={16} />
                  <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={40} />
                  <Tooltip formatter={(v: number) => [fmt(v), 'Tıklama']} labelFormatter={(l) => `Gün ${l}`} />
                  <Area type="monotone" dataKey="c" stroke="#ff6b4a" strokeWidth={2} fill="url(#sgMonthlyArea)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="sg-kpi-note">Günlük veri yok.</p>
          )}
        </section>
        <section className="sg-card sg-span-5">
          <h2>Aylara göre tıklama <SeoInfo k={k} label="Aylara göre tıklama" /></h2>
          <p className="sg-sub">Kayıtlı raporlardan, son {fmt(trend.length)} ay</p>
          <TrendBars data={trend.map((t) => ({ m: shortMonth(t.month), v: t.clicks ?? null }))} format={(v) => fmt(v)} name="Tıklama" />
        </section>

        <section className="sg-card sg-span-6">
          <h2>Tıklaması en çok değişen sorgular <SeoInfo k={k} label="Tıklaması en çok değişen sorgular" /></h2>
          <MoversView mv={s.queries} label="Sorgu" k={k} />
        </section>
        <section className="sg-card sg-span-6">
          <h2>Tıklaması en çok değişen sayfalar <SeoInfo k={k} label="Tıklaması en çok değişen sayfalar" /></h2>
          <MoversView mv={s.pages} label="Sayfa" k={k} />
        </section>

        <section className="sg-card sg-span-6">
          <h2>Kitap sayfalarının durumu <SeoInfo k={k} label="Kitap sayfalarının durumu" /></h2>
          <p className="sg-sub">Ürün puanı {s.books.threshold} ve üstü olanların payı; puan rapor anındaki durumdur.</p>
          {s.books.counted ? (
            <div className="sg-bars">
              <Bar2 label={`En çok satan ${fmt(s.books.counted)} kitap`} value={s.books.share} right={`${fmt(s.books.good)} / ${fmt(s.books.counted)} · ${pct(s.books.share, 0)}`} />
              <Bar2 label="Bütün satıştaki ürünler" value={s.books.activeShare} right={`${fmt(s.books.activeGood)} / ${fmt(s.books.active)} · ${pct(s.books.activeShare, 0)}`} />
            </div>
          ) : (
            <p className="sg-kpi-note">Satış verisi olan ürün yok.</p>
          )}
          {trend.filter((t) => t.share80 != null).length > 1 && (
            <div style={{ marginTop: 12 }}>
              <TrendBars data={trend.map((t) => ({ m: shortMonth(t.month), v: t.share80 == null ? null : t.share80 * 100 }))} format={(v) => `%${fmt(v, 0)}`} name="Puanı 80+" small />
            </div>
          )}
        </section>

        <section className="sg-card sg-span-6">
          <h2>Öneri kararları <SeoInfo k={k} label="Öneri kararları" /></h2>
          <p className="sg-sub">Bu ay hazırlanan ve karar verilen öneriler</p>
          <dl className="sg-facts">
            <Fact k="Hazırlanan" v={fmt(s.proposals.created)} />
            <Fact k="Onaylanan" v={fmt(s.proposals.approved)} />
            <Fact k="Reddedilen" v={fmt(s.proposals.rejected)} />
            <Fact k="Şu an onay bekleyen" v={fmt(s.proposals.pending)} />
          </dl>
          {s.worklist.available && (
            <>
              <h2 style={{ marginTop: 16 }}>İş listesi</h2>
              <dl className="sg-facts">
                {Object.entries(s.worklist.byStatus ?? {}).map(([k, v]) => (
                  <Fact key={k} k={k} v={fmt(v)} />
                ))}
                <Fact k="Toplam" v={fmt(s.worklist.total)} />
                {s.worklist.changedInMonth != null && <Fact k="Bu ay güncellenen" v={fmt(s.worklist.changedInMonth)} />}
              </dl>
            </>
          )}
        </section>

        <section className="sg-card sg-span-6">
          <h2>Teknik sorunlar <SeoInfo k={k} label="Teknik sorunlar" /></h2>
          {s.tech.available ? (
            <>
              <p className="sg-sub">{fmt(s.tech.checked)} sayfa tarandı; fark bir önceki ayın raporuna göre.</p>
              {s.tech.issues?.length ? (
                <div className="sg-table-wrap">
                  <table className="sg-table">
                    <thead>
                      <tr>
                        <th>Sorun <SeoInfo k={k} label="Sorun" /></th>
                        <th>Sayfa</th>
                        <th>Fark <SeoInfo k={k} label="Fark" /></th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.tech.issues.map((i) => {
                        const diff = i.previous == null ? null : i.count - i.previous;
                        return (
                          <tr key={i.id}>
                            <td>
                              <span className={`sg-dot ${i.severity}`} aria-hidden style={{ display: 'inline-block', marginRight: 6 }} />
                              {i.title}
                            </td>
                            <td className="num">{fmt(i.count)}</td>
                            <td className="num" style={diff ? { color: diff > 0 ? '#c2361b' : '#0f7a51' } : undefined}>
                              {diff == null ? '—' : `${diff > 0 ? '+' : diff < 0 ? '−' : ''}${fmt(Math.abs(diff))}`}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="sg-kpi-note">Sorun bulunmadı.</p>
              )}
            </>
          ) : (
            <p className="sg-kpi-note">Tarama henüz yapılmadı.</p>
          )}
        </section>

        <section className="sg-card sg-span-6">
          <h2>Yapay zekâ cevaplarında anılma <SeoInfo k={k} label="Yapay zekâ cevaplarında anılma" /></h2>
          <p className="sg-sub">İzlenen sorularda Timaş’ın anılma oranı, bu ay</p>
          {s.geo.engines.some((e) => e.measured) ? (
            <div className="sg-bars">
              {s.geo.engines
                .filter((e) => e.measured)
                .map((e) => {
                  const prev = s.geo.previous.find((p) => p.engine === e.engine);
                  return (
                    <Bar2
                      key={e.engine}
                      label={e.label}
                      value={e.mentionRate}
                      right={`${pct(e.mentionRate, 0)} · ${fmt(e.measured)} ölçüm${prev?.mentionRate != null ? ` · önceki ay ${pct(prev.mentionRate, 0)}` : ''}`}
                    />
                  );
                })}
            </div>
          ) : (
            <p className="sg-kpi-note">Bu ay ölçüm yok.</p>
          )}
        </section>

        <section className="sg-card sg-span-6">
          <h2>Haklar ve yayın durumu <SeoInfo k={k} label="Haklar ve yayın durumu" /></h2>
          <p className="sg-sub">Satıştaki kitaplar, rapor anında</p>
          {s.crm.available ? (
            <dl className="sg-facts">
              {Object.entries(s.crm.rights ?? {}).map(([k, v]) => (
                <Fact key={k} k={s.crm.labels?.[k] ?? k} v={fmt(v)} />
              ))}
              {Object.entries(s.crm.flags ?? {}).map(([k, v]) => (
                <Fact key={`f-${k}`} k={s.crm.flagLabels?.[k] ?? k} v={fmt(v)} />
              ))}
            </dl>
          ) : (
            <p className="sg-kpi-note">CRM henüz okunmadı.</p>
          )}
        </section>

        <section className="sg-card sg-span-6">
          <h2>Uyarılar <SeoInfo k={k} label="Uyarılar" /></h2>
          {s.alerts.available ? (
            <>
              <p className="sg-sub">
                Şu an açık {fmt(s.alerts.open)} · bu ay açılan {fmt(s.alerts.openedInMonth)} · kapanan {fmt(s.alerts.resolvedInMonth)}
              </p>
              {s.alerts.items?.length ? (
                <ul style={{ margin: 0, paddingLeft: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {s.alerts.items.map((a) => (
                    <li key={a.id} style={{ display: 'flex', gap: 8, alignItems: 'baseline', minWidth: 0 }}>
                      <span className={`sg-dot ${a.severity}`} aria-hidden style={{ display: 'inline-block' }} />
                      {a.link ? <Link to={a.link} style={{ overflowWrap: 'anywhere' }}>{a.title}</Link> : <span style={{ overflowWrap: 'anywhere' }}>{a.title}</span>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="sg-kpi-note">Açık uyarı yok.</p>
              )}
            </>
          ) : (
            <p className="sg-kpi-note">İzleme henüz çalışmadı.</p>
          )}
        </section>
      </div>
    </>
  );
}

function Kpi({ label, value, cur, prev, ly, k, lowerBetter, info }: { label: string; value: string; cur?: number | null; prev: Period; ly: Period; k: 'clicks' | 'impressions' | 'ctr' | 'position'; lowerBetter?: boolean; info?: ReactNode }) {
  const line = (name: string, ref: Period) => {
    if (!ref.available) return <div className="sg-kpi-note">{name}: veri yok</div>;
    const ch = change(cur, ref[k] ?? null);
    const good = ch != null && ch !== 0 && (lowerBetter ? ch < 0 : ch > 0);
    return (
      <div className="sg-kpi-note" style={ch ? { color: good ? '#0f7a51' : '#c2361b' } : undefined}>
        {name}: {signed(ch)}
      </div>
    );
  };
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}{info ? <> {info}</> : null}</div>
      <div className="sg-kpi-value sg-mono">{value}</div>
      {line('Önceki ay', prev)}
      {line('Geçen yıl', ly)}
    </div>
  );
}

function TrendBars({ data, format, name, small }: { data: Array<{ m: string; v: number | null }>; format: (v: number) => string; name: string; small?: boolean }) {
  if (data.filter((d) => d.v != null).length < 1) return <p className="sg-kpi-note">Karşılaştırılacak geçmiş rapor yok.</p>;
  return (
    <div className="sg-chart" style={small ? { height: 120 } : undefined}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
          <XAxis dataKey="m" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} interval={0} />
          <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={40} tickFormatter={(v: number) => format(v)} />
          <Tooltip formatter={(v: number) => [format(v), name]} />
          <Bar dataKey="v" radius={[6, 6, 0, 0]} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={d.m} fill={i === data.length - 1 ? '#ff6b4a' : '#7c5cff'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function MoversView({ mv, label, k }: { mv: Movers; label: string; k?: Kaynaklar | null }) {
  if (!mv.available) return <p className="sg-kpi-note">{mv.reason ?? 'Veri yok.'}</p>;
  const part = (title: string, rows: Mover[], total?: number) => (
    <>
      <p className="sg-sub" style={{ margin: '8px 0 6px' }}>
        {title} — ilk {fmt(mv.top)} / {fmt(total)}
      </p>
      {rows.length ? (
        <div className="sg-table-wrap">
          <table className="sg-table">
            <thead>
              <tr>
                <th>{label}</th>
                <th>Önceki ay <SeoInfo k={k} label="Önceki ay" /></th>
                <th>Bu ay <SeoInfo k={k} label="Bu ay" /></th>
                <th>Fark <SeoInfo k={k} label="Fark" /></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td className={label === 'Sayfa' ? 'url' : undefined} style={{ overflowWrap: 'anywhere' }}>
                    {label === 'Sayfa' ? r.key.replace(/^https?:\/\/[^/]+/, '') || '/' : r.key}
                  </td>
                  <td className="num">{fmt(r.prevClicks)}</td>
                  <td className="num">{fmt(r.clicks)}</td>
                  <td className="num">
                    {r.delta > 0 ? '+' : '−'}
                    {fmt(Math.abs(r.delta))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="sg-kpi-note">Yok.</p>
      )}
    </>
  );
  return (
    <>
      {part('Artan', mv.gainers ?? [], mv.gainersTotal)}
      {part('Azalan', mv.losers ?? [], mv.losersTotal)}
    </>
  );
}

function Bar2({ label, value, right }: { label: string; value: number | null; right: string }) {
  return (
    <div className="sg-bar-row">
      <span style={{ overflowWrap: 'anywhere' }}>{label}</span>
      <span className="sg-mono" style={{ fontSize: 12 }}>{right}</span>
      <div className="sg-bar" role="img" aria-label={`${label}: ${pct(value, 0)}`}>
        <i style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }} />
      </div>
    </div>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt>{k}</dt>
      <dd className="sg-mono">{v}</dd>
    </div>
  );
}
