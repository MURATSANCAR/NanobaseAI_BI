import type { ReactNode } from 'react';
import { useState, type CSSProperties } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, CalendarDays, ChevronLeft, ChevronRight, Loader2, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { useCan } from '../useAdmin';
import { RIGHTS_LABEL, RIGHTS_TONE, call, dateTime, fmt, qs, scoreTone, type CrmRights } from './api';
import SeoLayout, { Failed, Loading, SeoInfo } from './SeoLayout';

/** Sezon takvimi: /api/v1/seo-geo/seasons. Yaklaşan özel günler (CRM + hareketli günler), bağlı kitaplar ve
 *  sayfalarının hazırlığı; geçen yılın arama artışı Search Console'dan. Hiçbir yere yazılmaz. */

type Phase = 'yaklasiyor' | 'hazirlik' | 'suruyor';
type Precision = 'kesin' | 'yaklasik' | 'hafta' | 'bilinmiyor';
type Level = 'hazir' | 'duzelt' | 'onay_bekliyor' | 'onaylandi';
type Uplift = {
  dayStart: string;
  window: [string, string];
  baseline: [string, string];
  impressions: number;
  weekly: number;
  baselineWeekly: number;
  upliftPct: number | null;
  siteUpliftPct: number | null;
  netPt: number | null;
} | null;
type Counts = { books: number; rightsWarning: number } & Record<Level, number>;
type Day = {
  id: string;
  name: string;
  source: 'crm' | 'kural';
  web: boolean;
  crmBooks: number;
  keywords: string[];
  precision: Precision;
  uncertaintyDays: number | null;
  dateWhy: string;
  crmWeeks: [number, number] | null;
  uplift: Uplift;
  start: string | null;
  end: string | null;
  prepStart?: string;
  daysLeft?: number;
  prepDaysLeft?: number;
  phase?: Phase;
  counts?: Counts;
  fix?: Array<{ id: string; name: string; score: number; label: string }>;
  /** null: rehber taslakları kullanılmıyor. */
  guides?: string[] | null;
};
type RefreshState = { running: boolean; startedAt: string | null; finishedAt: string | null; error: string | null; gscError: string | null };
type Calendar = {
  today: string;
  weeks: number;
  leadDays: number;
  readyScore: number;
  windowWeeks: number;
  baselineWeeks: number;
  connected: { crm: boolean; gsc: boolean };
  guidesAvailable: boolean;
  state: RefreshState;
  lastRefresh: string | null;
  days: Day[];
  undated: Day[];
  actions: Array<{ kind: 'duzelt' | 'rehber'; dayId: string; dayName: string; start: string; text: string; books?: Day['fix'] }>;
};
type Book = {
  id: string;
  name: string;
  ean: string;
  score: number;
  sales: number;
  issues: Array<{ rule: string; title: string; severity: string }>;
  proposal: 'hazir' | 'onaylandi' | null;
  rights: CrmRights | null;
  readiness: { level: Level; label: string; reasons: string[]; rightsWarning: boolean; openIssues: number; blockingIssues: number };
  uplift: Uplift;
};
type DayDetail = {
  day: Day & { counts: Counts };
  start: number;
  total: number;
  items: Book[];
  leadDays: number;
  readyScore: number;
  connected: { crm: boolean; gsc: boolean };
  guidesAvailable: boolean;
};

const api = {
  calendar: (weeks: number) => call<Calendar>(`seasons?${qs({ weeks })}`),
  day: (id: string, start: number, limit: number) => call<DayDetail>(`seasons/${encodeURIComponent(id)}?${qs({ start, limit })}`),
  refresh: () => call<{ started: boolean; state: RefreshState }>('seasons/refresh', { method: 'POST' }),
};

const PAGE = 50;
const WEEK_CHOICES = [4, 8, 12, 26, 52];
const LEVEL_TONE: Record<Level, string> = { hazir: 'good', duzelt: 'bad', onay_bekliyor: 'violet', onaylandi: 'mid' };
const PHASE_LABEL: Record<Phase, string> = { yaklasiyor: 'Yaklaşıyor', hazirlik: 'Hazırlık zamanı', suruyor: 'Bugün / sürüyor' };
const PHASE_TONE: Record<Phase, string> = { yaklasiyor: '', hazirlik: 'bad', suruyor: 'good' };

const d = (iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'long' }) =>
  iso ? new Date(`${iso}T12:00:00`).toLocaleDateString('tr-TR', opts) : '—';
const signed = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : v < 0 ? '−' : ''}%${fmt(Math.abs(v), 0)}`);

function dateLine(day: Day) {
  if (!day.start) return 'Tarih bilinmiyor';
  const multi = day.end && day.end !== day.start;
  const text = multi ? `${d(day.start)} – ${d(day.end)}` : d(day.start, { day: 'numeric', month: 'long', weekday: 'long' });
  if (day.precision === 'yaklasik') return `${text} · ±${day.uncertaintyDays ?? 1} gün`;
  return text;
}

function precisionNote(day: Day) {
  if (day.precision === 'yaklasik')
    return day.uncertaintyDays && day.uncertaintyDays > 1
      ? `Yaklaşık tarih: ${day.dateWhy}.`
      : `Hicri takvimden hesaplandı (${day.dateWhy}); resmî ilanla bir gün fark olabilir.`;
  if (day.precision === 'hafta') return `${day.dateWhy}; günü belli değil, haftanın başı esas alındı.`;
  return day.dateWhy;
}

/** Sezon takvimi ekranı. `?gun=` seçili günün kitap tablosunu açar. */
export default function SeoSeasons() {
  const canRun = useCan('seo.calistir');
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const selected = params.get('gun') ?? '';
  const [weeks, setWeeks] = useState(12);

  const cal = useQuery({
    queryKey: ['seo-seasons', weeks],
    queryFn: () => api.calendar(weeks),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
    refetchInterval: (q) => (q.state.data?.state.running ? 8000 : false),
  });
  const refresh = useMutation({ mutationFn: api.refresh, onSuccess: () => qc.invalidateQueries({ queryKey: ['seo-seasons'] }) });
  const c = cal.data;
  const running = !!c?.state.running;

  const select = (id: string) => {
    const next = new URLSearchParams(params);
    if (id) next.set('gun', id);
    else next.delete('gun');
    setParams(next);
  };

  return (
    <SeoLayout k={cal.data?.kaynaklar}
      path="/seo-geo/takvim"
      crumb="Sezon takvimi"
      eyebrow="SEO & GEO · CRM özel günleri"
      title="Sezon takvimi"
      lead={`Yaklaşan özel günler ve CRM'de o güne bağlı kitaplar. Hazırlık günden ${c?.leadDays ?? 21} gün önce başlar: sayfa düzeltmesinin Google'da görünmesi zaman alır. Geçen yılın arama artışı Search Console'dan her gece hesaplanır.`}
      actions={
        canRun ? (
          <button className="sg-button" onClick={() => refresh.mutate()} disabled={refresh.isPending || running}>
            {running || refresh.isPending ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <RefreshCw size={16} aria-hidden />}
            {running ? 'Okunuyor…' : 'Şimdi yenile'}
          </button>
        ) : undefined
      }
    >
      {selected ? (
        <DayBooks id={selected} onBack={() => select('')} />
      ) : (
        <>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'space-between', alignItems: 'center' }}>
            <div className="sg-filters" role="toolbar" aria-label="Kaç hafta ileri">
              {WEEK_CHOICES.map((w) => (
                <button key={w} className="sg-filter" aria-pressed={weeks === w} onClick={() => setWeeks(w)}>
                  {w === 52 ? '1 yıl' : `${w} hafta`}
                </button>
              ))}
            </div>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--sg-muted)' }}>
              {c?.lastRefresh ? `Son okuma ${dateTime(c.lastRefresh)} · her gece yenilenir` : 'Henüz okuma yok; her gece yenilenir'}
            </p>
          </div>

          {cal.isLoading && <Loading text="Takvim hazırlanıyor…" />}
          {cal.error && <Failed error={cal.error} />}
          {refresh.error && <Failed error={refresh.error} />}
          {c?.state.error && <p className="sg-banner err">Son okuma başarısız: {c.state.error}</p>}
          {c && !c.connected.crm && <p className="sg-banner">CRM bağlantısı tanımlı değil: yalnız hesaplanan günler görünür, kitap bağı yok.</p>}
          {c && !c.connected.gsc && (
            <p className="sg-banner">Search Console bağlı değil: geçen yılın arama artışı hesaplanamıyor. Bağlantı Yönetim → SEO & GEO ekranından kurulur.</p>
          )}
          {c?.state.gscError && <p className="sg-banner err">Search Console okunamadı: {c.state.gscError}</p>}

          {c && (
            <>
              <section className="sg-kpis" aria-label="Özet">
                <Kpi label="Yaklaşan gün" value={fmt(c.days.length)} note={`Önümüzdeki ${weeks === 52 ? 'bir yıl' : `${weeks} hafta`}`} info={<SeoInfo k={cal.data?.kaynaklar} label="Yaklaşan gün" />} />
                <Kpi label="Hazırlık zamanı" value={fmt(c.days.filter((x) => x.phase === 'hazirlik').length)} note={`Güne ${c.leadDays} günden az kaldı`} info={<SeoInfo k={cal.data?.kaynaklar} label="Hazırlık zamanı" />} />
                <Kpi
                  label="Düzeltilecek sayfa"
                  value={fmt(c.days.filter((x) => x.phase !== 'yaklasiyor').reduce((a, x) => a + (x.counts?.duzelt ?? 0), 0))}
                  note="Hazırlık zamanındaki günlerin kitapları" info={<SeoInfo k={cal.data?.kaynaklar} label="Düzeltilecek sayfa" />} />
                <Kpi label="Rehber sayfası eksik" value={c.guidesAvailable ? fmt(c.actions.filter((a) => a.kind === 'rehber').length) : '—'} note="Hazırlık zamanındaki günler" info={<SeoInfo k={cal.data?.kaynaklar} label="Rehber sayfası eksik" />} />
              </section>

              {c.actions.length > 0 && <Actions actions={c.actions} onOpen={select} />}

              {!c.days.length ? (
                <div className="sg-empty">
                  <CalendarDays size={22} aria-hidden />
                  <h2>Bu aralıkta özel gün yok</h2>
                  <p>Daha uzun bir aralık seçin.</p>
                </div>
              ) : (
                <section aria-label="Yaklaşan günler" style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fill, minmax(min(100%, 320px), 1fr))' }}>
                  {c.days.map((day) => (
                    <DayCard key={day.id} day={day} leadDays={c.leadDays} gsc={c.connected.gsc} onOpen={() => select(day.id)} />
                  ))}
                </section>
              )}

              {c.undated.length > 0 && (
                <details className="sg-more sg-card">
                  <summary>Tarihi bilinmeyen günler ({fmt(c.undated.length)})</summary>
                  <p style={{ fontSize: 12, color: 'var(--sg-muted)' }}>Tarih tahmin edilmez; CRM'e hafta girilince ya da tarih açıklanınca takvime girer.</p>
                  <ul className="sg-hints">
                    {c.undated.map((u) => (
                      <li key={u.id}>
                        <strong>{u.name}</strong> — {u.dateWhy}
                        {u.crmBooks > 0 && (
                          <>
                            {' '}
                            <button className="sg-filter" style={{ minHeight: 28 }} onClick={() => select(u.id)}>
                              {fmt(u.crmBooks)} kitap
                            </button>
                          </>
                        )}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </>
      )}
    </SeoLayout>
  );
}

function Actions({ actions, onOpen }: { actions: Calendar['actions']; onOpen: (id: string) => void }) {
  return (
    <section className="sg-card">
      <h2>Şimdi yapılacaklar</h2>
      <p className="sg-sub">Hazırlık zamanına girmiş günler. Kitaplar çok satandan aza sıralı.</p>
      <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: 10 }}>
        {actions.map((a) => (
          <li key={`${a.kind}-${a.dayId}`} style={{ padding: '10px 12px', borderRadius: 14, background: 'var(--sg-soft)' }}>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'space-between' }}>
              <strong style={{ fontSize: 13, color: 'var(--sg-ink)' }}>{a.text}</strong>
              <span style={{ fontSize: 12, color: 'var(--sg-muted)' }}>{d(a.start)}</span>
            </div>
            {a.kind === 'duzelt' && a.books && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginTop: 8 }}>
                {a.books.map((b) => (
                  <Link key={b.id} className="sg-chip bad" to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(b.id)}`} title={`SEO puanı ${b.score}`}>
                    {b.name} · {b.score}
                  </Link>
                ))}
              </div>
            )}
            {a.kind === 'rehber' && (
              <div style={{ marginTop: 8, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Link className="sg-button" to="/seo-geo/rehberler">
                  Rehber taslağı hazırla
                </Link>
                <button className="sg-button" onClick={() => onOpen(a.dayId)}>
                  Güne bağlı kitaplar
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function DayCard({ day, leadDays, gsc, onOpen }: { day: Day; leadDays: number; gsc: boolean; onOpen: () => void }) {
  const phase = day.phase ?? 'yaklasiyor';
  const hot = phase === 'hazirlik';
  const n = day.counts;
  // Hazırlık penceresinin ne kadarı geçti: 0 (başlamadı) … 1 (gün geldi).
  const progress = day.daysLeft == null ? 0 : Math.max(0, Math.min(1, 1 - day.daysLeft / leadDays));
  const card: CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    textAlign: 'left',
    width: '100%',
    cursor: 'pointer',
    font: 'inherit',
    color: 'inherit',
    border: hot ? '1px solid var(--sg-coral)' : '1px solid var(--sg-line)',
    background: hot ? '#fff8f5' : undefined,
  };
  return (
    <button className="sg-card" style={card} onClick={onOpen} aria-label={`${day.name}: kitapları göster`}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        <div
          aria-hidden
          style={{ minWidth: 56, padding: '6px 4px', borderRadius: 14, textAlign: 'center', background: hot ? 'var(--sg-coral)' : 'var(--sg-soft)', color: hot ? '#fff' : 'var(--sg-ink)' }}
        >
          <div className="sg-mono" style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.1 }}>
            {day.start ? new Date(`${day.start}T12:00:00`).getDate() : '?'}
          </div>
          <div style={{ fontSize: 10.5, fontWeight: 750, textTransform: 'uppercase' }}>{day.start ? d(day.start, { month: 'short' }) : ''}</div>
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 800, color: 'var(--sg-ink)', letterSpacing: '-.3px' }}>{day.name}</div>
          <div style={{ fontSize: 12, color: 'var(--sg-muted)', marginTop: 2 }}>{dateLine(day)}</div>
        </div>
        <span className={`sg-chip ${PHASE_TONE[phase]}`}>{phase === 'suruyor' ? PHASE_LABEL.suruyor : `${fmt(day.daysLeft)} gün`}</span>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11.5, color: hot ? '#c2361b' : 'var(--sg-muted)', fontWeight: hot ? 750 : 500 }}>
          <span>{phase === 'yaklasiyor' ? `Hazırlık ${d(day.prepStart)} başlar (${fmt(day.prepDaysLeft)} gün sonra)` : PHASE_LABEL[phase]}</span>
        </div>
        <div aria-hidden style={{ height: 4, borderRadius: 4, background: 'var(--sg-line)', marginTop: 4, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${progress * 100}%`, background: hot ? 'var(--sg-coral)' : 'var(--sg-violet)' }} />
        </div>
      </div>

      {n && n.books > 0 ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          <span className="sg-chip">{fmt(n.books)} kitap</span>
          {n.duzelt > 0 && <span className="sg-chip bad">{fmt(n.duzelt)} düzeltilmeli</span>}
          {n.onay_bekliyor > 0 && <span className="sg-chip violet">{fmt(n.onay_bekliyor)} onay bekliyor</span>}
          {n.onaylandi > 0 && <span className="sg-chip mid">{fmt(n.onaylandi)} onaylandı</span>}
          {n.hazir > 0 && <span className="sg-chip good">{fmt(n.hazir)} hazır</span>}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: 'var(--sg-muted)' }}>
          {day.crmBooks > 0 ? `CRM'de ${fmt(day.crmBooks)} kitap bağlı; sitede satışta olanı yok.` : "CRM'de bu güne bağlı kitap yok."}
        </div>
      )}

      <UpliftLine u={day.uplift} gsc={gsc} />
      {day.guides != null && (
        <div style={{ fontSize: 12, color: day.guides.length ? '#0f7a51' : 'var(--sg-muted)' }}>
          {day.guides.length ? `Rehber taslağı var: ${day.guides.join(', ')}` : 'Bu gün için rehber/liste sayfası yok'}
        </div>
      )}
    </button>
  );
}

function UpliftLine({ u, gsc }: { u: Uplift; gsc: boolean }) {
  if (!gsc && !u) return <div style={{ fontSize: 12, color: 'var(--sg-muted)' }}>Search Console bağlı değil; geçen yıl verisi yok.</div>;
  if (!u) return <div style={{ fontSize: 12, color: 'var(--sg-muted)' }}>Geçen yıl için arama verisi yok (Search Console en çok 16 ay geriye bakar).</div>;
  if (!u.impressions && !u.baselineWeekly) return <div style={{ fontSize: 12, color: 'var(--sg-muted)' }}>Geçen yıl bu günle ilgili aramada gösterim yok.</div>;
  const good = u.upliftPct != null && u.upliftPct > 0;
  return (
    <div style={{ fontSize: 12 }} title={`Pencere ${d(u.window[0])} – ${d(u.window[1])}, kıyas ${d(u.baseline[0])} – ${d(u.baseline[1])}`}>
      Geçen yıl gün öncesi: ilgili aramalarda gösterim{' '}
      <strong style={{ color: good ? '#0f7a51' : undefined }}>{u.upliftPct == null ? 'yeni başladı' : signed(u.upliftPct)}</strong>
      <span style={{ color: 'var(--sg-muted)' }}>
        {' '}
        ({fmt(u.impressions)} gösterim · site geneli {signed(u.siteUpliftPct)})
      </span>
    </div>
  );
}

function DayBooks({ id, onBack }: { id: string; onBack: () => void }) {
  const [start, setStart] = useState(0);
  const r = useQuery({
    queryKey: ['seo-season-day', id, start],
    queryFn: () => api.day(id, start, PAGE),
    enabled: ENGINE_ENABLED,
    retry: false,
    placeholderData: (p) => p,
  });
  const x = r.data;
  const day = x?.day;

  return (
    <>
      <div>
        <button className="sg-button" onClick={onBack}>
          <ArrowLeft size={16} aria-hidden /> Takvime dön
        </button>
      </div>
      {r.isLoading && <Loading text="Kitaplar getiriliyor…" />}
      {r.error && <Failed error={r.error} />}
      {day && x && (
        <>
          <section className="sg-card">
            <h2>{day.name}</h2>
            <p className="sg-sub" style={{ marginBottom: 8 }}>
              {dateLine(day)}
              {day.phase && day.phase !== 'suruyor' ? ` · ${fmt(day.daysLeft)} gün kaldı · hazırlık ${d(day.prepStart)}` : ''}
            </p>
            <dl className="sg-facts">
              <div>
                <dt>Tarih</dt>
                <dd>{precisionNote(day)}</dd>
              </div>
              <div>
                <dt>Aranan kelimeler</dt>
                <dd>{day.keywords.join(' · ') || '—'}</dd>
              </div>
              <div>
                <dt>Kaynak</dt>
                <dd>{day.source === 'crm' ? `CRM özel günü${day.web ? ', sitede yayında' : ''}` : 'Hesaplanan gün (CRM’de yok)'}</dd>
              </div>
              <div>
                <dt>Geçen yıl arama</dt>
                <dd>
                  <UpliftLine u={day.uplift} gsc={x.connected.gsc} />
                </dd>
              </div>
            </dl>
          </section>

          <section className="sg-card">
            <h2>Bağlı kitaplar <SeoInfo k={r.data?.kaynaklar} label="Bağlı kitaplar" /></h2>
            <p className="sg-sub">
              Sitede satışta olan, CRM'de durum işareti (çekildi, bizim değil …) olmayan kitaplar; çok satandan aza. Hazır sayılmak için SEO puanı en az{' '}
              {x.readyScore} ve kritik/yüksek sorun olmamalı.
            </p>
            {!x.items.length ? (
              <div className="sg-empty">
                <h2>Kitap yok</h2>
                <p>{day.crmBooks ? "CRM'deki kitapların hiçbiri sitede satışta değil." : "CRM'de bu güne bağlı kitap yok."}</p>
              </div>
            ) : (
              <div className="sg-table-wrap">
                <table className="sg-table">
                  <thead>
                    <tr>
                      <th>Kitap</th>
                      <th>Hazırlık</th>
                      <th>SEO puanı <SeoInfo k={r.data?.kaynaklar} label="SEO puanı" /></th>
                      <th>Açık sorun <SeoInfo k={r.data?.kaynaklar} label="Açık sorun" /></th>
                      <th>Hak</th>
                      <th>Geçen yıl arama <SeoInfo k={r.data?.kaynaklar} label="Geçen yıl arama" /></th>
                    </tr>
                  </thead>
                  <tbody>
                    {x.items.map((b) => (
                      <tr key={b.id}>
                        <td style={{ minWidth: 180 }}>
                          <Link to={`/seo-geo/urun-denetimi?urun=${encodeURIComponent(b.id)}`}>{b.name}</Link>
                        </td>
                        <td style={{ minWidth: 150 }}>
                          <span className={`sg-chip ${LEVEL_TONE[b.readiness.level]}`}>{b.readiness.label}</span>
                          {b.readiness.reasons.length > 0 && (
                            <div style={{ fontSize: 11, color: 'var(--sg-muted)', marginTop: 4 }}>{b.readiness.reasons.join(' · ')}</div>
                          )}
                        </td>
                        <td className="num">
                          <span className={`sg-chip ${scoreTone(b.score)}`}>{b.score}</span>
                        </td>
                        <td style={{ fontSize: 12, minWidth: 140 }}>
                          {b.issues.length ? b.issues.map((i) => i.title).join(', ') : '—'}
                        </td>
                        <td>{b.rights ? <span className={`sg-chip ${RIGHTS_TONE[b.rights]}`}>{RIGHTS_LABEL[b.rights]}</span> : '—'}</td>
                        <td className="num" style={{ fontSize: 12 }}>
                          {b.uplift ? (
                            <>
                              <div>{signed(b.uplift.upliftPct)}</div>
                              <div style={{ color: 'var(--sg-muted)' }}>{fmt(b.uplift.impressions)} gösterim</div>
                            </>
                          ) : x.connected.gsc ? (
                            '—'
                          ) : (
                            'Bağlı değil'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Pager start={start} total={x.total} onChange={setStart} />
          </section>
        </>
      )}
    </>
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
