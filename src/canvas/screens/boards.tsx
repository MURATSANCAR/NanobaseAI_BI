import { Activity, BarChart3, Clock, LayoutDashboard, PlusCircle, RefreshCw } from 'lucide-react';
import CanvasCard, { CardBadge, CardFootRow } from '../ui/CanvasCard';
import { Donut, ProgressBar, type DonutSlice } from '../ui/charts';
import { SLOTS } from '../layout';
import type { CanvasAccent, CanvasScreen } from '../types';
import { dateTime, num } from '../format';

type AnalyticsHealth = { ok?: boolean; message?: string; dashboard_count?: number };
type AnalyticsStatus = { enabled?: boolean; url?: string; health?: AnalyticsHealth };
type BoardItem = {
  id: number;
  title?: string;
  chart_count?: number;
  changed_on?: string;
  changed_on_delta?: string;
};

/** Halka dilimlerinin renk sırası; beşinci ve sonrası "Diğer" altında toplanır. */
const SLICE_ACCENTS: CanvasAccent[] = ['violet', 'mint', 'amber', 'coral'];

/** Başlık boş gelebiliyor; pano yine de kimliğiyle görünsün. */
const boardTitle = (d: BoardItem): string => d.title?.trim() || `Pano #${d.id}`;

/** Panolar "NanobaseAI · <kaynak>" diye adlanıyor; dar kutularda ön ek yer kaplıyor. */
const shortTitle = (t: string): string => t.replace(/^NanobaseAI\s*·\s*/, '').trim() || t;

const chartsOf = (d: BoardItem): number => d.chart_count ?? 0;

/**
 * Panolar ekranı.
 *
 * Modülün işi: her veri kaynağı için bir Superset panosu tutmak.
 * Eski arayüz pano listesini yalnız bir açılır kutuda gösteriyordu; motorun
 * sağlık mesajı ile içi boş kalmış panolar gözden kaçıyordu. Kanvas bu ikisini
 * öne alır: motor bağlı mı, hangi pano boş, en son ne güncellendi.
 */
export function boardsScreen(
  status: AnalyticsStatus | undefined,
  dashboards: BoardItem[],
  loading: boolean,
): CanvasScreen {
  const health = status?.health;
  const enabled = status?.enabled === true;
  const healthy = health?.ok !== false;
  const state = !enabled ? 'Kapalı' : healthy ? 'Bağlı' : 'Sağlıksız';
  const stateColor = !enabled ? 'text-slate-500' : healthy ? 'text-canvas-mint' : 'text-canvas-coral';

  const total = dashboards.length;
  const totalCharts = dashboards.reduce((a, d) => a + chartsOf(d), 0);
  const empty = dashboards.filter((d) => chartsOf(d) === 0);
  const filled = total - empty.length;

  // Grafik sayısına göre: halka ve "en dolu pano" bundan çıkar.
  const byCharts = [...dashboards].sort((a, b) => chartsOf(b) - chartsOf(a));
  const busiest = total > 0 ? byCharts[0] : null;

  // Güncellenme zamanına göre: damgası olmayanlar sona düşer.
  const byChanged = [...dashboards].sort((a, b) => {
    const av = a.changed_on ?? '';
    const bv = b.changed_on ?? '';
    if (av === bv) return 0;
    if (!av) return 1;
    if (!bv) return -1;
    return av > bv ? -1 : 1;
  });
  const latest = total > 0 ? byChanged[0] : null;
  const latestWhen = latest
    ? latest.changed_on_delta?.trim() || (latest.changed_on ? dateTime(latest.changed_on) : 'bilinmiyor')
    : 'bilinmiyor';

  const top = byCharts.slice(0, 4);
  const restCharts = byCharts.slice(4).reduce((a, d) => a + chartsOf(d), 0);
  const usedLabels = new Set<string>();
  const slices: DonutSlice[] = top.map((d, i) => {
    const base = shortTitle(boardTitle(d));
    const label = usedLabels.has(base) ? `${base} (${i + 1})` : base;
    usedLabels.add(label);
    return { label, value: chartsOf(d), accent: SLICE_ACCENTS[i % SLICE_ACCENTS.length] };
  });
  if (restCharts > 0) slices.push({ label: 'Diğer', value: restCharts, accent: 'slate' });

  return {
    id: 'boards',
    crumb: 'Panolar',
    askPlaceholder: 'ZEKİ’ye sor… örn. bayi bazında satış panosu kur',
    question: {
      who: 'TY',
      role: 'Timaş Yayınları · Panolar',
      at: 'Şimdi',
      text: 'Panolarımız güncel mi, boş kalan var mı?',
      answered: !loading,
    },
    cards: [
      {
        id: 'engine',
        ...SLOTS.a,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Analitik motoru"
            accent="coral"
            icon={<Activity className="h-3.5 w-3.5" />}
            badge={
              !enabled ? (
                <CardBadge tone="muted">kapalı</CardBadge>
              ) : healthy ? (
                <CardBadge tone="ok">çalışıyor</CardBadge>
              ) : (
                <CardBadge tone="fail">sorunlu</CardBadge>
              )
            }
          >
            {loading ? (
              <div className="py-3 text-xs text-canvas-muted">Yükleniyor…</div>
            ) : (
              <>
                <div className={['text-2xl font-black tracking-tight', stateColor].join(' ')}>{state}</div>
                <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">
                  {health?.message?.trim()
                    ? health.message
                    : enabled
                      ? 'Motor yanıt veriyor, ek bir not bildirmedi.'
                      : 'Motor kapalı; panolar okunamıyor.'}
                </div>
                {status?.url ? (
                  <div className="mt-2 truncate font-mono text-[10px] text-canvas-muted" title={status.url}>
                    {status.url}
                  </div>
                ) : null}
                <CardFootRow
                  label="Motorun saydığı pano"
                  value={num(health?.dashboard_count)}
                  tone={enabled && healthy ? 'ok' : 'warn'}
                />
              </>
            )}
          </CanvasCard>
        ),
      },
      {
        id: 'list',
        ...SLOTS.b,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Panolar"
            accent="violet"
            icon={<LayoutDashboard className="h-3.5 w-3.5" />}
            note={`${num(total)} pano`}
          >
            {byChanged.length ? (
              <div className="space-y-1.5">
                {byChanged.slice(0, 5).map((d) => (
                  <div key={d.id} className="flex items-center gap-2">
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-canvas-violet/70" />
                    <span className="min-w-0 flex-1 truncate text-[11.5px] font-semibold" title={boardTitle(d)}>
                      {shortTitle(boardTitle(d))}
                    </span>
                    <span
                      className={[
                        'shrink-0 text-[10px]',
                        chartsOf(d) === 0 ? 'font-bold text-amber-700' : 'text-canvas-muted',
                      ].join(' ')}
                    >
                      {num(chartsOf(d))} grafik
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-3 text-xs text-canvas-muted">
                {loading ? 'Yükleniyor…' : 'Kayıtlı pano yok. Her veri kaynağı için bir pano kurulur.'}
              </div>
            )}
            <CardFootRow label="Toplam grafik" value={`${num(totalCharts)} grafik`} />
          </CanvasCard>
        ),
      },
      {
        id: 'charts',
        ...SLOTS.c,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Grafik dağılımı"
            accent="mint"
            icon={<BarChart3 className="h-3.5 w-3.5" />}
            note={`${num(totalCharts)} grafik`}
          >
            {slices.length ? (
              <Donut center={num(totalCharts)} slices={slices} />
            ) : (
              <div className="py-3 text-xs text-canvas-muted">
                {loading ? 'Yükleniyor…' : 'Dağılım için grafik yok. Panolar boş görünüyor.'}
              </div>
            )}
            <CardFootRow
              label="En dolu pano"
              value={busiest ? `${num(chartsOf(busiest))} grafik` : 'yok'}
              tone={busiest && chartsOf(busiest) > 0 ? 'ok' : 'plain'}
            />
          </CanvasCard>
        ),
      },
      {
        id: 'empty',
        ...SLOTS.d,
        render: ({ stacked }) => {
          const n = empty.length;
          return (
            <CanvasCard
              stacked={stacked}
              title="Boş panolar"
              accent="amber"
              icon={<PlusCircle className="h-3.5 w-3.5" />}
              badge={n ? <CardBadge tone="warn">düzeltilmeli</CardBadge> : <CardBadge tone="ok">temiz</CardBadge>}
            >
              <div className="text-2xl font-black tracking-tight text-canvas-ink">{num(n)}</div>
              <div className="mt-0.5 text-[11px] text-canvas-muted">
                {total === 0
                  ? loading
                    ? 'Yükleniyor…'
                    : 'Henüz pano yok, dolayısıyla boş pano da yok.'
                  : n
                    ? 'Bu panolar açılır ama içinde tek grafik yok.'
                    : 'Her panonun en az bir grafiği var.'}
              </div>
              {n > 0 && (
                <div className="mt-2.5 space-y-1">
                  {empty.slice(0, 3).map((d) => (
                    <div
                      key={d.id}
                      className="truncate rounded-lg bg-amber-50/70 px-2 py-1 text-[11px] font-semibold text-amber-800"
                      title={boardTitle(d)}
                    >
                      {shortTitle(boardTitle(d))}
                    </div>
                  ))}
                </div>
              )}
              <CardFootRow label="Dolu pano" value={`${num(filled)} / ${num(total)}`} tone={n ? 'warn' : 'ok'} />
            </CanvasCard>
          );
        },
      },
      {
        id: 'freshness',
        ...SLOTS.e,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Son güncelleme"
            accent="slate"
            icon={<Clock className="h-3.5 w-3.5" />}
            badge={latest ? <CardBadge tone="info">güncel</CardBadge> : <CardBadge tone="muted">kayıt yok</CardBadge>}
          >
            {latest ? (
              <>
                <div className="text-lg font-black leading-tight tracking-tight text-canvas-ink">{latestWhen}</div>
                <div className="mt-0.5 truncate text-xs font-semibold text-canvas-ink" title={boardTitle(latest)}>
                  {shortTitle(boardTitle(latest))}
                </div>
                <div className="mt-2 text-[11px] text-canvas-muted">
                  {latest.changed_on ? dateTime(latest.changed_on) : 'Zaman damgası gelmedi.'}
                </div>
                <CardFootRow label="Toplam pano" value={`${num(total)} pano`} />
              </>
            ) : (
              <div className="py-3 text-[11px] text-canvas-muted">
                {loading ? 'Yükleniyor…' : 'Güncellenmiş pano kaydı yok. İlk panoyu sohbetten kurabilirsiniz.'}
              </div>
            )}
          </CanvasCard>
        ),
      },
      {
        id: 'answer',
        ...SLOTS.main,
        render: ({ stacked }) => (
          <div className="cv-card cv-card-hover rounded-[28px] border-2 border-white/90 p-6 shadow-canvas-card">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-slate-100/90 pb-3">
              <div className="flex items-center gap-2.5">
                <span className="rounded-full bg-gradient-to-r from-canvas-coral to-canvas-violet px-3 py-1 text-[11px] font-extrabold uppercase tracking-wide text-white shadow-sm">
                  ZEKİ AI ÖZETİ
                </span>
                <span className="text-xs font-medium text-canvas-muted">Panolar · {num(total)} pano</span>
              </div>
              <span className="text-xs font-semibold text-canvas-muted">
                {!enabled ? 'Analitik motoru kapalı' : empty.length ? 'Dikkat gerektiren durum var' : 'Panolar sağlıklı'}
              </span>
            </div>
            <p className="text-base font-bold leading-snug text-canvas-ink">
              {loading
                ? 'Panolar okunuyor…'
                : !enabled
                  ? '“Analitik motoru kapalı. Açıldığında her veri kaynağı için bir pano kurulur ve grafikler buraya düşer.”'
                  : total === 0
                    ? '“Henüz pano yok. Sohbete ‘satış panosu kur’ yazarak ilkini oluşturabilirsiniz.”'
                    : `“${num(total)} pano var, toplam ${num(totalCharts)} grafik taşıyor.${
                        empty.length
                          ? ` ${num(empty.length)} pano boş; açılır ama içinde tek grafik yok.`
                          : ' Her panonun en az bir grafiği var.'
                      }${latest ? ` Son güncelleme ${latestWhen}.` : ''}${
                        healthy ? '' : ' Motor sağlıksız yanıt veriyor, listeler eksik olabilir.'
                      }”`}
            </p>
            {!stacked && (
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-canvas-muted">
                <span>
                  <strong className="text-canvas-ink">Pano:</strong> {num(total)}
                </span>
                <span className="text-slate-300">•</span>
                <span>
                  <strong className="text-canvas-ink">Grafik:</strong> {num(totalCharts)}
                </span>
                <span className="text-slate-300">•</span>
                <span>
                  <strong className="text-canvas-ink">Boş pano:</strong> {num(empty.length)}
                </span>
              </div>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <a
                href="/bi"
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-canvas-coral to-canvas-violet px-5 py-2.5 text-xs font-extrabold tracking-tight text-white shadow-md transition-all hover:opacity-95 active:scale-95"
              >
                <LayoutDashboard className="h-4 w-4" />
                Panoyu aç
              </a>
              <a
                href="/bi/chat"
                className="flex items-center gap-1.5 rounded-xl bg-slate-100 px-4 py-2.5 text-xs font-bold text-canvas-ink transition-all hover:bg-slate-200/80 active:scale-95"
              >
                Sohbetten pano kur
              </a>
            </div>
          </div>
        ),
      },
      {
        id: 'sticker',
        ...SLOTS.sticker,
        decorative: true,
        render: () => (
          <div className="group relative">
            <div className="cv-tape absolute -top-3 left-1/2 z-40 h-6 w-16 -translate-x-1/2 rounded-sm" />
            <div className="flex h-[175px] w-[125px] flex-col justify-between rounded-xl border-2 border-white/80 bg-gradient-to-br from-indigo-900 via-sky-700 to-teal-400 p-3 shadow-canvas-card">
              <div className="flex items-center justify-between">
                <span className="text-[8px] font-black uppercase tracking-widest text-white/70">En dolu</span>
                <span className="font-mono text-[8px] text-white/60">{busiest ? num(chartsOf(busiest)) : '0'}</span>
              </div>
              <div className="my-auto text-center">
                <div className="mx-auto mb-1.5 flex h-10 w-10 items-center justify-center rounded-full border border-white/40">
                  <BarChart3 className="h-4 w-4 text-white/90" />
                </div>
                <h2 className="line-clamp-3 text-[10px] font-black leading-tight tracking-wide text-white drop-shadow-sm">
                  {busiest ? shortTitle(boardTitle(busiest)) : 'Pano yok'}
                </h2>
              </div>
              <div className="flex items-center justify-between border-t border-white/20 pt-1 text-[7px] text-white/80">
                <span>{busiest ? `${num(chartsOf(busiest))} grafik` : 'grafik yok'}</span>
                <span className="font-bold">{num(total)} pano</span>
              </div>
            </div>
          </div>
        ),
      },
      {
        id: 'ghost',
        ...SLOTS.ghost,
        decorative: true,
        render: () => (
          <div className="pointer-events-none opacity-40 blur-[0.5px]">
            <div className="cv-card w-[220px] rounded-[24px] border border-slate-300 p-4 shadow-md">
              <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                <span className="text-[11px] font-extrabold text-slate-700">Tüm grafikler</span>
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-600">
                  {num(totalCharts)}
                </span>
              </div>
              <p className="mt-2 text-[10px] font-medium leading-relaxed text-slate-600">
                Panolara dağılmış grafiklerin toplamı burada birikiyor.
              </p>
            </div>
          </div>
        ),
      },
      {
        id: 'coverage',
        x: 290,
        y: 700,
        w: 860,
        connect: false,
        render: ({ stacked }) =>
          stacked ? null : (
            <div className="cv-card rounded-[24px] px-5 py-4 shadow-canvas-card">
              <div className="mb-2 flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-[13px] font-extrabold">
                  <RefreshCw className="h-3.5 w-3.5 text-canvas-muted" />
                  Pano doluluğu
                </span>
                <span className="text-[11px] text-canvas-muted">
                  Grafiği olan {num(filled)} / {num(total)}
                </span>
              </div>
              <ProgressBar
                pct={total ? (filled / total) * 100 : 0}
                left="İçinde grafik olan panolar"
                right={empty.length ? `${num(empty.length)} boş pano` : 'boş pano yok'}
                gradient={empty.length ? 'from-canvas-amber to-canvas-coral' : 'from-canvas-mint to-canvas-violet'}
              />
            </div>
          ),
      },
    ],
  };
}
