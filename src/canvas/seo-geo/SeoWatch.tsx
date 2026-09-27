import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft, ChevronRight, ExternalLink, Loader2, RefreshCw, Send } from 'lucide-react';
import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';
import { FLAG_LABEL, call, dateTime, fmt, qs, seoApi } from './api';
import SeoLayout, { Failed, Loading } from './SeoLayout';
import { useCan } from '../useAdmin';

/** İzleme ve rapor: öteki ekranların sakladığı veriden gece çıkarılan olaylar (tıklama düşüşü, 404 artışı, robots.txt,
 *  sitemap, yapay zekâ cevaplarından düşme, CRM yayın durumu, hız) ve haftalık rapor. */

type Sev = 'kritik' | 'yüksek' | 'orta';
type WatchEvent = {
  id: string;
  kind: string;
  kindLabel: string;
  severity: Sev;
  title: string;
  detail: string | null;
  link: string | null;
  hold: boolean;
  firstSeen: string | null;
  lastSeen: string | null;
  resolvedAt: string | null;
  notifiedAt: string | null;
  notifyResult: 'sent' | 'no_recipient' | 'no_smtp' | 'failed' | null;
};
type WatchSettings = { alertRecipients: number; reportRecipients: number; smtp: boolean; reportDay: number; reportDayName: string };
type RunState = { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null; last: Record<string, unknown> | null };
type WatchList = {
  total: number;
  start: number;
  items: WatchEvent[];
  counts: { open: number; resolved: number; unnotified: number; bySeverity: Record<Sev, number> };
  settings: WatchSettings;
  thresholds: Array<{ id: string; label: string; text: string }>;
  state: RunState;
};
type Movers = { query: string; clicks: number; prevClicks: number; delta: number };
type Period = { start: string; end: string; clicks: number; impressions: number };
type Summary = {
  week: { start: string; end: string };
  generatedAt: string;
  google: { available: boolean; reason?: string; current?: Period; previous?: Period; clicksPct?: number | null; impressionsPct?: number | null };
  queries: { available: boolean; reason?: string; top?: number; gainers?: Movers[]; losers?: Movers[]; gainersTotal?: number; losersTotal?: number };
  proposals: { approvedThisWeek: number; pending: number };
  crm: { available: boolean; rights?: Record<string, number>; flags?: Record<string, number>; labels?: Record<string, string> };
  tech: { available: boolean; checked?: number; issues?: Array<{ id: string; title: string; severity: string; count: number }> };
  geo: { engines: Array<{ engine: string; label: string; measured: number; mentioned: number; cited: number; mentionRate: number | null; citeRate: number | null }> };
  alerts: { open: number; items: Array<{ id: string; severity: Sev; title: string; link: string | null; firstSeen: string | null }> };
};
type Report = { id: string; weekStart: string; weekEnd: string; summary: Summary; createdAt: string | null; createdBy: string | null; sentAt: string | null; sentTo: string | null; sendResult: string | null };
type ReportPage = { latest: Report | null; preview: Summary; history: Array<{ id: string; weekStart: string; weekEnd: string; sentAt: string | null; sendResult: string | null }>; settings: WatchSettings };

const watchApi = {
  list: (p: { status: 'open' | 'resolved'; start: number; limit: number }) => call<WatchList>(`watch?${qs(p)}`),
  run: () => call<Record<string, unknown>>('watch/run', { method: 'POST', timeout: 180_000 }),
  report: () => call<ReportPage>('watch/report', { timeout: 120_000 }),
  send: () => call<{ result: string; report: Report }>('watch/report/send', { method: 'POST', timeout: 120_000 }),
};

const PAGE = 40;
const TABS = [
  { id: 'acik', label: 'Açık olaylar' },
  { id: 'kapanan', label: 'Kapanan' },
  { id: 'rapor', label: 'Haftalık rapor' },
  { id: 'esikler', label: 'Eşikler' },
] as const;
type Tab = (typeof TABS)[number]['id'];
const SEV_TONE: Record<Sev, 'bad' | 'mid' | 'violet'> = { kritik: 'bad', yüksek: 'mid', orta: 'violet' };
const SEV_LABEL: Record<Sev, string> = { kritik: 'Kritik', yüksek: 'Yüksek', orta: 'Orta' };
const NOTIFY_LABEL: Record<string, string> = {
  no_recipient: 'E-posta bekliyor: uyarı alıcısı tanımlı değil',
  no_smtp: 'E-posta bekliyor: e-posta sunucusu tanımlı değil',
  failed: 'E-posta gönderilemedi; sonraki turda yeniden denenecek',
};

const day = (iso: string | null | undefined) => (iso ? new Date(`${iso.slice(0, 10)}T12:00:00`).toLocaleDateString('tr-TR') : '—');
const pct = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}%${fmt(Math.abs(v) * 100, 1)}`);

export default function SeoWatch() {
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.some((t) => t.id === params.get('sekme')) ? params.get('sekme') : 'acik') as Tab;
  const setTab = (t: Tab) => {
    const next = new URLSearchParams(params);
    if (t !== 'acik') next.set('sekme', t);
    else next.delete('sekme');
    setParams(next, { replace: true });
  };
  const summary = useQuery({
    queryKey: ['seo-watch', 'open', 0],
    queryFn: () => watchApi.list({ status: 'open', start: 0, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
  });
  const run = useMutation({ mutationFn: watchApi.run, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-watch'] }) });
  const s = summary.data;

  return (
    <SeoLayout
      path="/seo-geo/izleme"
      crumb="İzleme ve rapor"
      eyebrow="SEO & GEO · izleme"
      title="İzleme ve rapor"
      lead="Her gece öteki ekranların topladığı veriye bakılır: Google tıklamasında düşüş, bulunamayan ya da hata veren sayfa artışı, robots.txt ve sitemap değişikliği, yapay zekâ cevaplarından düşme, CRM yayın durumu ve sayfa hızı. Olay ilk görüldüğünde bir kez e-posta gider; sorun sürdükçe açık kalır, kalkınca kendiliğinden kapanır."
      actions={
        canRun && (
          <button className="sg-button" onClick={() => run.mutate()} disabled={run.isPending || !!s?.state.running}>
            {run.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {run.isPending ? 'Denetleniyor…' : 'Şimdi denetle'}
          </button>
        )
      }
    >
      {summary.isLoading && <Loading text="Olaylar getiriliyor…" />}
      {summary.error && <Failed error={summary.error} />}
      {run.error && <Failed error={run.error} />}
      {run.data && (
        <p className="sg-banner ok" role="status">
          Denetim bitti: {fmt(Number(run.data.new ?? 0))} yeni, {fmt(Number(run.data.reopen ?? 0))} yeniden açılan, {fmt(Number(run.data.resolve ?? 0))} kapanan olay.
        </p>
      )}
      {s?.state.error && <p className="sg-banner err">Son denetim başarısız: {s.state.error}</p>}

      {s && (
        <>
          <section className="sg-kpis" aria-label="Özet">
            <Kpi label="Açık olay" value={fmt(s.counts.open)} note={`Kritik ${fmt(s.counts.bySeverity.kritik)} · yüksek ${fmt(s.counts.bySeverity.yüksek)} · orta ${fmt(s.counts.bySeverity.orta)}`} tone={s.counts.bySeverity.kritik ? 'bad' : undefined} />
            <Kpi label="E-posta bekleyen" value={fmt(s.counts.unnotified)} note="Açık olup henüz bildirilmemiş olaylar" />
            <Kpi label="Kapanan" value={fmt(s.counts.resolved)} note="Koşulu kalkan olaylar" />
            <Kpi label="Son denetim" value={s.state.finishedAt ? dateTime(s.state.finishedAt) : '—'} note="Gece işiyle ya da düğmeyle" small />
          </section>
          <DeliveryBanner settings={s.settings} />
        </>
      )}

      <div className="sg-filters" role="tablist" aria-label="Bölüm" style={{ marginTop: 16 }}>
        {TABS.map((t) => (
          <button key={t.id} role="tab" className="sg-filter" aria-pressed={tab === t.id} aria-selected={tab === t.id} onClick={() => setTab(t.id)}>
            {t.label}
            {t.id === 'acik' && s ? <span className="sg-mono"> {fmt(s.counts.open)}</span> : null}
            {t.id === 'kapanan' && s ? <span className="sg-mono"> {fmt(s.counts.resolved)}</span> : null}
          </button>
        ))}
      </div>

      {tab === 'acik' && <EventsTab status="open" />}
      {tab === 'kapanan' && <EventsTab status="resolved" />}
      {tab === 'rapor' && <ReportTab />}
      {tab === 'esikler' && s && <ThresholdsTab thresholds={s.thresholds} />}
    </SeoLayout>
  );
}

function DeliveryBanner({ settings }: { settings: WatchSettings }) {
  if (settings.alertRecipients && settings.smtp) return null;
  const missing = [
    !settings.alertRecipients && 'uyarı alıcısı (Yönetim → SEO & GEO → SEO uyarı alıcıları)',
    !settings.smtp && 'e-posta sunucusu (Yönetim → Uyarılar)',
  ].filter(Boolean);
  return (
    <p className="sg-banner" style={{ marginTop: 12 }}>
      E-posta gitmiyor: {missing.join(' ve ')} tanımlı değil. Olaylar ekranda görünür; ayar yapılınca bekleyenler bir sonraki denetimde gönderilir.
    </p>
  );
}

function EventsTab({ status }: { status: 'open' | 'resolved' }) {
  const [start, setStart] = useState(0);
  useEffect(() => setStart(0), [status]);
  const list = useQuery({
    queryKey: ['seo-watch', status, start],
    queryFn: () => watchApi.list({ status, start, limit: PAGE }),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (prev) => prev,
  });
  const items = list.data?.items ?? [];
  const total = list.data?.total ?? 0;

  return (
    <section className="sg-card" aria-label={status === 'open' ? 'Açık olaylar' : 'Kapanan olaylar'} style={{ marginTop: 12 }}>
      {list.isLoading && <Loading text="Olaylar getiriliyor…" />}
      {list.error && <Failed error={list.error} />}
      {list.data && !items.length && (
        <div className="sg-empty">
          <h2>{status === 'open' ? 'Açık olay yok' : 'Kapanan olay yok'}</h2>
          <p>
            {status === 'open'
              ? 'Son denetimde izlenen hiçbir koşul aşılmadı. Veri gelmeyen alanlar (bağlantısı olmayan kaynaklar) denetlenmez; eşikler «Eşikler» sekmesinde.'
              : 'Henüz koşulu kalkıp kapanan bir olay yok.'}
          </p>
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {items.map((e) => (
          <article key={e.id} className="sg-issue" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 6 }}>
              <span className={`sg-chip ${SEV_TONE[e.severity]}`}>{SEV_LABEL[e.severity]}</span>
              <span className="sg-chip">{e.kindLabel}</span>
              {e.hold && <span className="sg-chip">Bilgi</span>}
            </div>
            <h3 style={{ margin: 0, fontSize: 14.5, lineHeight: 1.4, overflowWrap: 'anywhere' }}>{e.title}</h3>
            {e.detail && <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, overflowWrap: 'anywhere' }}>{e.detail}</p>}
            <div className="sg-kpi-note" style={{ display: 'flex', flexWrap: 'wrap', gap: '4px 14px' }}>
              <span>İlk görüldü {dateTime(e.firstSeen)}</span>
              {status === 'open' ? <span>Son görüldü {dateTime(e.lastSeen)}</span> : <span>Kapandı {dateTime(e.resolvedAt)}</span>}
              {e.notifiedAt ? <span>E-posta gitti {dateTime(e.notifiedAt)}</span> : status === 'open' && e.notifyResult ? <span>{NOTIFY_LABEL[e.notifyResult] ?? ''}</span> : null}
            </div>
            {e.link && (
              <Link className="sg-button" style={{ alignSelf: 'flex-start' }} to={e.link}>
                İlgili ekranda aç
              </Link>
            )}
          </article>
        ))}
      </div>
      {total > PAGE && (
        <div className="sg-pager" style={{ marginTop: 12 }}>
          <button className="sg-button" disabled={start === 0} onClick={() => setStart(Math.max(0, start - PAGE))} aria-label="Önceki sayfa">
            <ChevronLeft size={16} aria-hidden />
          </button>
          <span className="sg-mono">
            {fmt(start + 1)}–{fmt(Math.min(total, start + PAGE))} / {fmt(total)}
          </span>
          <button className="sg-button" disabled={start + PAGE >= total} onClick={() => setStart(start + PAGE)} aria-label="Sonraki sayfa">
            <ChevronRight size={16} aria-hidden />
          </button>
        </div>
      )}
    </section>
  );
}

function ReportTab() {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ['seo-me'], queryFn: seoApi.me, enabled: ENGINE_ENABLED, retry: false, staleTime: 300_000 });
  const rep = useQuery({ queryKey: ['seo-watch-report'], queryFn: watchApi.report, enabled: ENGINE_ENABLED, retry: false });
  const send = useMutation({
    mutationFn: watchApi.send,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['seo-watch-report'] });
      qc.invalidateQueries({ queryKey: ['seo-watch'] });
    },
  });
  const [view, setView] = useState<'onizleme' | 'son'>('onizleme');

  if (rep.isLoading) return <Loading text="Rapor hazırlanıyor…" />;
  if (rep.error) return <Failed error={rep.error} />;
  if (!rep.data) return null;
  const { latest, preview, settings, history } = rep.data;
  const canApprove = !!me.data?.canApprove;
  const blocked = !canApprove ? 'Göndermek onay yetkisi ister.' : !settings.reportRecipients ? 'Haftalık rapor alıcısı tanımlı değil (Yönetim → SEO & GEO).' : !settings.smtp ? 'E-posta sunucusu tanımlı değil (Yönetim → Uyarılar).' : null;
  const shown = view === 'son' && latest ? latest.summary : preview;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 12 }}>
      <section className="sg-card" aria-label="Rapor gönderimi">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ minWidth: 0 }}>
            <h2 style={{ margin: 0, fontSize: 16 }}>Haftalık rapor</h2>
            <p className="sg-kpi-note" style={{ margin: '4px 0 0' }}>
              Her {settings.reportDayName} gecesi biten son tam hafta (Pazartesi–Pazar, İstanbul saati) için hazırlanır
              {settings.reportRecipients ? ` ve ${fmt(settings.reportRecipients)} alıcıya gönderilir.` : '; alıcı tanımlı olmadığı için yalnız burada durur.'}
            </p>
          </div>
          <button className="sg-button" onClick={() => send.mutate()} disabled={!!blocked || send.isPending} title={blocked ?? undefined}>
            {send.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <Send size={16} aria-hidden />}
            Şimdi gönder
          </button>
        </div>
        {blocked && <p className="sg-kpi-note" style={{ margin: '8px 0 0' }}>{blocked}</p>}
        {send.error && <div style={{ marginTop: 8 }}><Failed error={send.error} /></div>}
        {send.data && <p className="sg-banner ok" role="status" style={{ marginTop: 8 }}>Rapor gönderildi.</p>}
        <div className="sg-filters" role="tablist" aria-label="Rapor" style={{ marginTop: 12 }}>
          <button role="tab" className="sg-filter" aria-pressed={view === 'onizleme'} aria-selected={view === 'onizleme'} onClick={() => setView('onizleme')}>
            Şimdi gönderilecek ({day(preview.week.start)}–{day(preview.week.end)})
          </button>
          {latest && (
            <button role="tab" className="sg-filter" aria-pressed={view === 'son'} aria-selected={view === 'son'} onClick={() => setView('son')}>
              Son kayıtlı ({day(latest.weekStart)}–{day(latest.weekEnd)})
            </button>
          )}
        </div>
        {view === 'son' && latest && (
          <p className="sg-kpi-note" style={{ margin: '8px 0 0', display: 'flex', flexWrap: 'wrap', gap: '4px 14px', alignItems: 'center' }}>
            <span>Hazırlandı {dateTime(latest.createdAt)}{latest.createdBy ? ` · ${latest.createdBy}` : ''}</span>
            <span>{latest.sentAt ? `Gönderildi ${dateTime(latest.sentAt)}` : latest.sendResult ? NOTIFY_LABEL[latest.sendResult] ?? 'Gönderilmedi' : 'Gönderilmedi'}</span>
            <a href={`${ENGINE_BASE}/api/v1/seo-geo/watch/report/${latest.id}.html`} target="_blank" rel="noreferrer" style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}>
              E-posta görünümü <ExternalLink size={13} aria-hidden />
            </a>
          </p>
        )}
      </section>

      <ReportView s={shown} />

      {history.length > 1 && (
        <section className="sg-card" aria-label="Geçmiş raporlar">
          <h2 style={{ margin: '0 0 8px', fontSize: 15 }}>Geçmiş raporlar</h2>
          <div className="sg-table-wrap">
            <table className="sg-table">
              <thead>
                <tr><th>Hafta</th><th>Gönderim</th><th /></tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td>{day(h.weekStart)}–{day(h.weekEnd)}</td>
                    <td>{h.sentAt ? dateTime(h.sentAt) : h.sendResult ? NOTIFY_LABEL[h.sendResult] ?? 'Gönderilmedi' : 'Gönderilmedi'}</td>
                    <td>
                      <a href={`${ENGINE_BASE}/api/v1/seo-geo/watch/report/${h.id}.html`} target="_blank" rel="noreferrer">E-posta görünümü</a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function ReportView({ s }: { s: Summary }) {
  const g = s.google;
  const q = s.queries;
  return (
    <>
      <section className="sg-kpis" aria-label="Haftanın özeti">
        {g.available && g.current && g.previous ? (
          <>
            <Kpi label="Google tıklaması" value={fmt(g.current.clicks)} note={`${pct(g.clicksPct)} · önceki 7 gün ${fmt(g.previous.clicks)} (${day(g.current.start)}–${day(g.current.end)})`} tone={g.clicksPct != null && g.clicksPct < 0 ? 'bad' : g.clicksPct ? 'good' : undefined} />
            <Kpi label="Google gösterimi" value={fmt(g.current.impressions)} note={`${pct(g.impressionsPct)} · önceki 7 gün ${fmt(g.previous.impressions)}`} tone={g.impressionsPct != null && g.impressionsPct < 0 ? 'bad' : g.impressionsPct ? 'good' : undefined} />
          </>
        ) : (
          <Kpi label="Google" value="—" note={g.reason ?? 'Veri yok.'} small />
        )}
        <Kpi label="Bu hafta onaylanan öneri" value={fmt(s.proposals.approvedThisWeek)} note={`Onay bekleyen ${fmt(s.proposals.pending)}`} />
        <Kpi label="Açık uyarı" value={fmt(s.alerts.open)} note="Rapor anında" tone={s.alerts.open ? 'bad' : undefined} />
      </section>
      {g.available && <p className="sg-kpi-note" style={{ margin: 0 }}>Search Console verisi 2–3 gün geç geldiği için Google karşılaştırması eldeki son 7 günle önceki 7 gündür; takvim haftası değildir.</p>}

      <div className="sg-grid">
        <section className="sg-card sg-span-6" aria-label="Kazanan sorgular">
          <h2 style={{ margin: '0 0 8px', fontSize: 15 }}>Tıklaması en çok artan sorgular</h2>
          {q.available ? <MoversTable rows={q.gainers ?? []} note={`İlk ${fmt(q.top)} / ${fmt(q.gainersTotal)}`} /> : <p className="sg-kpi-note">{q.reason ?? 'İki dönemin sorgu verisi yok.'}</p>}
        </section>
        <section className="sg-card sg-span-6" aria-label="Kaybeden sorgular">
          <h2 style={{ margin: '0 0 8px', fontSize: 15 }}>Tıklaması en çok azalan sorgular</h2>
          {q.available ? <MoversTable rows={q.losers ?? []} note={`İlk ${fmt(q.top)} / ${fmt(q.losersTotal)}`} /> : <p className="sg-kpi-note">{q.reason ?? 'İki dönemin sorgu verisi yok.'}</p>}
        </section>

        <section className="sg-card sg-span-6" aria-label="Yapay zekâ cevapları">
          <h2 style={{ margin: '0 0 8px', fontSize: 15 }}>Yapay zekâ cevaplarında Timaş (bu hafta)</h2>
          {s.geo.engines.length ? (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <thead>
                  <tr><th>Motor</th><th>Ölçüm</th><th>Anılma</th><th>Kaynak</th></tr>
                </thead>
                <tbody>
                  {s.geo.engines.map((e) => (
                    <tr key={e.engine}>
                      <td>{e.label}</td>
                      <td className="num">{fmt(e.measured)}</td>
                      <td className="num">{e.mentionRate == null ? '—' : `%${fmt(e.mentionRate * 100, 0)}`}</td>
                      <td className="num">{e.citeRate == null ? '—' : `%${fmt(e.citeRate * 100, 0)}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="sg-kpi-note">Bu hafta ölçüm yok.</p>
          )}
        </section>

        <section className="sg-card sg-span-6" aria-label="Teknik tarama">
          <h2 style={{ margin: '0 0 8px', fontSize: 15 }}>Teknik tarama{s.tech.available ? ` (${fmt(s.tech.checked)} sayfa)` : ''}</h2>
          {!s.tech.available ? (
            <p className="sg-kpi-note">Tarama henüz yapılmadı.</p>
          ) : s.tech.issues?.length ? (
            <div className="sg-table-wrap">
              <table className="sg-table">
                <tbody>
                  {s.tech.issues.map((x) => (
                    <tr key={x.id}>
                      <td>{x.title}</td>
                      <td className="num">{fmt(x.count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="sg-kpi-note">Sorun bulunmadı.</p>
          )}
        </section>

        <section className="sg-card sg-span-6" aria-label="Haklar ve CRM">
          <h2 style={{ margin: '0 0 8px', fontSize: 15 }}>Haklar ve CRM (satıştaki kitaplar)</h2>
          {s.crm.available ? (
            <dl className="sg-facts">
              {Object.entries(s.crm.rights ?? {}).map(([k, v]) => (
                <div key={k}>
                  <dt>{s.crm.labels?.[k] ?? k}</dt>
                  <dd className="sg-mono">{fmt(v)}</dd>
                </div>
              ))}
              {Object.entries(s.crm.flags ?? {}).map(([k, v]) => (
                <div key={`f-${k}`}>
                  <dt>{(FLAG_LABEL as Record<string, string>)[k] ?? k}</dt>
                  <dd className="sg-mono">{fmt(v)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="sg-kpi-note">CRM henüz okunmadı.</p>
          )}
        </section>

        <section className="sg-card sg-span-6" aria-label="Açık uyarılar">
          <h2 style={{ margin: '0 0 8px', fontSize: 15 }}>Açık uyarılar</h2>
          {s.alerts.items.length ? (
            <ul style={{ margin: 0, paddingLeft: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
              {s.alerts.items.map((a) => (
                <li key={a.id} style={{ display: 'flex', gap: 8, alignItems: 'baseline', minWidth: 0 }}>
                  <span className={`sg-chip ${SEV_TONE[a.severity] ?? ''}`}>{SEV_LABEL[a.severity] ?? a.severity}</span>
                  {a.link ? <Link to={a.link} style={{ overflowWrap: 'anywhere' }}>{a.title}</Link> : <span style={{ overflowWrap: 'anywhere' }}>{a.title}</span>}
                </li>
              ))}
            </ul>
          ) : (
            <p className="sg-kpi-note">Açık uyarı yok.</p>
          )}
        </section>
      </div>
    </>
  );
}

function MoversTable({ rows, note }: { rows: Movers[]; note: string }) {
  if (!rows.length) return <p className="sg-kpi-note">Yok.</p>;
  return (
    <>
      <div className="sg-table-wrap">
        <table className="sg-table">
          <thead>
            <tr><th>Sorgu</th><th>Önceki</th><th>Bu dönem</th><th>Fark</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.query}>
                <td style={{ overflowWrap: 'anywhere' }}>{r.query}</td>
                <td className="num">{fmt(r.prevClicks)}</td>
                <td className="num">{fmt(r.clicks)}</td>
                <td className="num">{r.delta > 0 ? '+' : '−'}{fmt(Math.abs(r.delta))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="sg-kpi-note" style={{ margin: '6px 0 0' }}>{note}</p>
    </>
  );
}

function ThresholdsTab({ thresholds }: { thresholds: WatchList['thresholds'] }) {
  return (
    <section className="sg-card" aria-label="Eşikler" style={{ marginTop: 12 }}>
      <p style={{ margin: '0 0 12px', fontSize: 13, lineHeight: 1.55 }}>
        Eşikler mutlak sayı değildir: her ölçü sitenin kendi geçmişiyle karşılaştırılır. İlk ölçümde yalnız taban kaydedilir; olay ikinci ölçümden sonra açılabilir. Bir kaynaktan veri gelmezse (bağlantı yok, tarama yapılmadı) o konudaki açık olaylar kapanmaz, yeni olay da açılmaz.
      </p>
      <dl className="sg-facts">
        {thresholds.map((t) => (
          <div key={t.id}>
            <dt>{t.label}</dt>
            <dd>{t.text}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Kpi({ label, value, note, tone, small }: { label: string; value: string; note: string; tone?: 'good' | 'bad'; small?: boolean }) {
  return (
    <div className="sg-kpi">
      <div className="sg-kpi-label">{label}</div>
      <div className="sg-kpi-value sg-mono" style={{ ...(tone ? { color: tone === 'good' ? '#0f7a51' : '#c2361b' } : {}), ...(small ? { fontSize: 18 } : {}) }}>{value}</div>
      <div className="sg-kpi-note">{note}</div>
    </div>
  );
}
