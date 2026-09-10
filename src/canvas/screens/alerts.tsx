import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Activity, Bell, BellRing, Gauge, Mail, PlayCircle, ShieldQuestion } from 'lucide-react';
import { api } from '@/api/client';
import type { ApiConfig } from '@/api/client';
import CanvasCard, { CardBadge, CardFootRow } from '../ui/CanvasCard';
import { Donut, ProgressBar } from '../ui/charts';
import { SLOTS } from '../layout';
import type { CanvasScreen } from '../types';
import { alertRecipients, type AlertSummary } from '../data';
import { conditionLabel, dateTime, num, relative } from '../format';

/** "Şimdi kontrol et" düğmesi — kural motorunu elle koşturur. */
function CheckNowButton({ config }: { config: ApiConfig }) {
  const qc = useQueryClient();
  const run = useMutation({
    mutationFn: () => api.bi.alerts.runDue(config),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-alerts'] }),
  });
  const r = run.data;
  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => run.mutate()}
        disabled={run.isPending}
        className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-canvas-coral to-canvas-violet px-4 py-2 text-[11px] font-extrabold text-white shadow-md transition disabled:opacity-60"
      >
        <PlayCircle className="h-3.5 w-3.5" />
        {run.isPending ? 'Kontrol ediliyor…' : 'Şimdi kontrol et'}
      </button>
      {r && (
        <div className="rounded-lg bg-slate-50 px-2 py-1.5 text-[10.5px] font-semibold text-canvas-ink">
          {num(r.checked ?? 0)} kural denendi · {num(r.triggered ?? 0)} tetiklendi
          {r.errors?.length ? ` · ${num(r.errors.length)} hata` : ''}
        </div>
      )}
      {run.isError && <div className="text-[10.5px] font-semibold text-red-600">Kontrol çalıştırılamadı.</div>}
    </div>
  );
}

/**
 * Uyarılar ekranı.
 *
 * Modülün işi: bir SQL sonucunu eşikle karşılaştırıp aşıldığında haber vermek.
 * Eski liste ekranında iki şey görünmüyordu: kuralın eşiğe ne kadar yaklaştığı
 * ve `last_checked_at`. Yani "birazdan patlayacak" ile "hiç bakılmamış" ayırt
 * edilemiyordu. Kanvasın ana kartı yakınlık, yan kartı ise sessiz kuralları
 * gösterir.
 */
export function alertsScreen(s: AlertSummary, loading: boolean, config: ApiConfig): CanvasScreen {
  const hot = s.proximity[0];

  return {
    id: 'alerts',
    crumb: 'Uyarılar',
    askPlaceholder: 'ZEKİ’ye sor… örn. stok 500 adedin altına inerse haber ver',
    question: {
      who: 'TY',
      role: 'Timaş Yayınları · Uyarılar',
      at: 'Şimdi',
      text: 'Hangi eşik patlamak üzere?',
      answered: !loading,
    },
    cards: [
      {
        id: 'triggered',
        ...SLOTS.a,
        render: ({ stacked }) => {
          const n = s.triggered.length;
          const latest = [...s.triggered].sort((a, b) =>
            (a.last_triggered_at ?? '') < (b.last_triggered_at ?? '') ? 1 : -1,
          )[0];
          return (
            <CanvasCard
              stacked={stacked}
              title="Tetiklenenler"
              accent="coral"
              icon={<BellRing className="h-3.5 w-3.5" />}
              badge={n ? <CardBadge tone="fail">tetikte</CardBadge> : <CardBadge tone="ok">sakin</CardBadge>}
            >
              <div className="text-2xl font-black tracking-tight text-canvas-coral">{num(n)}</div>
              <div className="mt-0.5 text-[11px] text-canvas-muted">
                {n ? 'Aktif kural eşiği aşmış durumda.' : 'Aktif kuralların hiçbiri eşiği aşmadı.'}
              </div>
              {latest && (
                <>
                  <div className="mt-2.5 truncate rounded-lg bg-red-50/70 px-2 py-1 text-[11px] font-semibold text-red-700" title={latest.title}>
                    {latest.title}
                  </div>
                  <CardFootRow label="Son tetikleme" value={relative(latest.last_triggered_at)} tone="warn" />
                </>
              )}
            </CanvasCard>
          );
        },
      },
      {
        id: 'proximity',
        ...SLOTS.b,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Eşiğe yakınlık"
            accent="violet"
            icon={<Gauge className="h-3.5 w-3.5" />}
            note={`${num(s.active)} aktif`}
          >
            {s.proximity.length ? (
              <div className="space-y-2.5">
                {s.proximity.map(({ rule, pct: p, distance }) => (
                  <div key={rule.id}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-[11.5px] font-semibold" title={rule.title}>
                        {rule.title}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] font-bold tabular-nums text-canvas-muted">
                        {num(rule.last_value ?? null, 0)} {conditionLabel(rule.condition)} {num(rule.threshold, 0)}
                      </span>
                    </div>
                    <div className="mt-1">
                      <ProgressBar
                        pct={p}
                        gradient={p >= 90 ? 'from-red-500 to-canvas-coral' : p >= 60 ? 'from-canvas-amber to-canvas-coral' : 'from-canvas-violet to-canvas-mint'}
                      />
                    </div>
                    {distance == null && (
                      <div className="mt-0.5 text-[10px] text-canvas-muted">Henüz ölçüm yok</div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-3 text-xs text-canvas-muted">
                {loading ? 'Yükleniyor…' : 'Aktif kural yok ya da hiçbiri henüz ölçülmedi.'}
              </div>
            )}
          </CanvasCard>
        ),
      },
      {
        id: 'status',
        ...SLOTS.c,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Durum dağılımı"
            accent="mint"
            icon={<Bell className="h-3.5 w-3.5" />}
            note={`${num(s.total)} kural`}
          >
            <Donut
              center={num(s.total)}
              slices={[
                { label: 'Sakin', value: Math.max(0, s.active - s.triggered.length), accent: 'mint' },
                { label: 'Tetikte', value: s.triggered.length, accent: 'coral' },
                { label: 'Duraklatıldı', value: s.paused, accent: 'amber' },
              ]}
            />
            <CardFootRow
              label="Son kontrol"
              value={s.lastCheckedAt ? relative(s.lastCheckedAt) : 'hiç'}
              tone={s.lastCheckedAt ? 'plain' : 'warn'}
            />
          </CanvasCard>
        ),
      },
      {
        id: 'channels',
        ...SLOTS.d,
        render: ({ stacked }) => {
          const only = s.browserOnly.length;
          const withMail = s.total - only;
          return (
            <CanvasCard
              stacked={stacked}
              title="Bildirim"
              accent="amber"
              icon={<Mail className="h-3.5 w-3.5" />}
              badge={only ? <CardBadge tone="warn">tarayıcı</CardBadge> : <CardBadge tone="ok">e-posta var</CardBadge>}
            >
              <div className="text-2xl font-black tracking-tight text-canvas-ink">{num(withMail)}</div>
              <div className="mt-0.5 text-[11px] text-canvas-muted">
                kuralın e-posta alıcısı var. Kalanı yalnız tarayıcı açıkken duyulur.
              </div>
              {only > 0 && (
                <div className="mt-2.5 space-y-1">
                  {s.browserOnly.slice(0, 3).map((r) => (
                    <div key={r.id} className="truncate rounded-lg bg-amber-50/70 px-2 py-1 text-[11px] font-semibold text-amber-800" title={r.title}>
                      {r.title}
                    </div>
                  ))}
                </div>
              )}
              <CardFootRow label="Yalnız tarayıcı" value={num(only)} tone={only ? 'warn' : 'ok'} />
            </CanvasCard>
          );
        },
      },
      {
        id: 'silent',
        ...SLOTS.e,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Hiç bakılmamış"
            accent="slate"
            icon={<ShieldQuestion className="h-3.5 w-3.5" />}
            badge={
              s.neverChecked.length ? <CardBadge tone="warn">{num(s.neverChecked.length)}</CardBadge> : <CardBadge tone="ok">yok</CardBadge>
            }
          >
            {s.neverChecked.length ? (
              <>
                <p className="text-[11px] leading-snug text-canvas-muted">
                  Bu kurallar kurulmuş ama bir kez bile çalıştırılmamış. Sessiz kalmaları güvenli oldukları anlamına
                  gelmiyor.
                </p>
                <div className="mt-2 space-y-1">
                  {s.neverChecked.slice(0, 3).map((r) => (
                    <div key={r.id} className="truncate rounded-lg bg-slate-50 px-2 py-1 text-[11px] font-semibold" title={r.title}>
                      {r.title}
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="text-[11px] leading-snug text-canvas-muted">
                Her kural en az bir kez çalıştırılmış. Son kontrol: {dateTime(s.lastCheckedAt)}.
              </p>
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
                <span className="text-xs font-medium text-canvas-muted">Uyarılar · {num(s.total)} kural</span>
              </div>
              <span className="flex items-center gap-2 text-xs font-semibold text-canvas-muted">
                <Activity className="h-3.5 w-3.5" />
                {s.lastCheckedAt ? `Son kontrol ${relative(s.lastCheckedAt)}` : 'Henüz kontrol edilmedi'}
              </span>
            </div>
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
              <div className="min-w-0 flex-1">
                <p className="text-base font-bold leading-snug text-canvas-ink">
                  {loading
                    ? 'Kurallar okunuyor…'
                    : s.total === 0
                      ? '“Henüz uyarı kuralı yok. Sohbete ‘stok 500 adedin altına inerse haber ver’ yazarak ilkini kurabilirsiniz.”'
                      : `“${num(s.active)} kural aktif${
                          s.triggered.length ? `, ${num(s.triggered.length)} tanesi tetikte` : ''
                        }.${
                          hot && hot.distance != null
                            ? ` Eşiğe en yakın kural “${hot.rule.title}”: son değer ${num(hot.rule.last_value ?? null)}, eşik ${num(hot.rule.threshold)}.`
                            : ''
                        }${s.neverChecked.length ? ` ${num(s.neverChecked.length)} kural hiç çalıştırılmamış.` : ''}”`}
                </p>
                {!stacked && (
                  <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-canvas-muted">
                    <span>
                      <strong className="text-canvas-ink">Aktif:</strong> {num(s.active)}
                    </span>
                    <span className="text-slate-300">•</span>
                    <span>
                      <strong className="text-canvas-ink">Duraklatılmış:</strong> {num(s.paused)}
                    </span>
                    <span className="text-slate-300">•</span>
                    <span>
                      <strong className="text-canvas-ink">Yalnız tarayıcı:</strong> {num(s.browserOnly.length)}
                    </span>
                  </div>
                )}
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <a
                    href="/bi/alerts"
                    className="flex items-center gap-2 rounded-xl bg-slate-100 px-4 py-2.5 text-xs font-bold text-canvas-ink transition-all hover:bg-slate-200/80 active:scale-95"
                  >
                    Kuralları yönet
                  </a>
                  <a
                    href="/bi/chat"
                    className="flex items-center gap-1.5 rounded-xl bg-slate-100 px-4 py-2.5 text-xs font-bold text-canvas-ink transition-all hover:bg-slate-200/80 active:scale-95"
                  >
                    Sohbetten kural kur
                  </a>
                </div>
              </div>
              <div className="w-full shrink-0 sm:w-[220px]">
                <CheckNowButton config={config} />
              </div>
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
            <div className="flex h-[175px] w-[125px] flex-col justify-between rounded-xl border-2 border-white/80 bg-gradient-to-br from-rose-600 via-orange-500 to-amber-400 p-3 shadow-canvas-card">
              <div className="flex items-center justify-between">
                <span className="text-[8px] font-black uppercase tracking-widest text-white/75">Eşiğe en yakın</span>
              </div>
              <div className="my-auto text-center">
                <div className="mx-auto mb-1.5 flex h-10 w-10 items-center justify-center rounded-full border border-white/40">
                  <Gauge className="h-4 w-4 text-white/90" />
                </div>
                <h2 className="line-clamp-3 text-[10px] font-black leading-tight tracking-wide text-white drop-shadow-sm">
                  {hot?.rule.title ?? 'Aktif kural yok'}
                </h2>
              </div>
              <div className="flex items-center justify-between border-t border-white/20 pt-1 text-[7px] text-white/85">
                <span>{hot ? `${Math.round(hot.pct)}% yakın` : '—'}</span>
                <span className="font-bold">{hot ? num(hot.rule.threshold) : ''}</span>
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
                <span className="text-[11px] font-extrabold text-slate-700">Alıcı listesi</span>
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-600">
                  {num(s.items.reduce((a, r) => a + alertRecipients(r).length, 0))}
                </span>
              </div>
              <p className="mt-2 text-[10px] font-medium leading-relaxed text-slate-600">
                Kurallara tanımlı e-posta adreslerinin toplamı.
              </p>
            </div>
          </div>
        ),
      },
    ],
  };
}
