import { Bell, CalendarClock, Database, LayoutDashboard, Sparkles } from 'lucide-react';
import CanvasCard, { CardBadge, CardFootRow } from '../ui/CanvasCard';
import { SLOTS } from '../layout';
import type { CanvasScreen } from '../types';
import type { AlertSummary, ScheduleSummary } from '../data';
import { num, relative } from '../format';

type EngineStatus = {
  enabled?: boolean;
  health?: { ok?: boolean; message?: string; dashboard_count?: number };
};

/**
 * Genel bakış: üç modülün tek cümlelik hâli ve içeri giriş kapıları.
 * Buradaki her rakam ilgili modülün kendi API'sinden gelir, sabit değildir.
 */
export function overviewScreen(
  sched: ScheduleSummary,
  alerts: AlertSummary,
  status: EngineStatus | undefined,
  boardCount: number,
  loading: boolean,
): CanvasScreen {
  const engineOk = Boolean(status?.enabled) && status?.health?.ok !== false;
  const needsAttention = sched.recipientless.length + alerts.triggered.length + alerts.neverChecked.length;

  return {
    id: 'overview',
    crumb: 'Genel bakış',
    askPlaceholder: 'ZEKİ’ye sor… örn. bu ay satışlar geçen yıla göre nasıl?',
    question: {
      who: 'TY',
      role: 'Timaş Yayınları · Genel bakış',
      at: 'Şimdi',
      text: 'Bugün neye bakmam gerekiyor?',
      answered: !loading,
    },
    cards: [
      {
        id: 'schedules',
        ...SLOTS.a,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Planlı raporlar"
            accent="coral"
            icon={<CalendarClock className="h-3.5 w-3.5" />}
            badge={
              sched.recipientless.length ? <CardBadge tone="warn">alıcı eksik</CardBadge> : <CardBadge tone="ok">düzenli</CardBadge>
            }
          >
            <div className="text-2xl font-black tracking-tight text-canvas-coral">{num(sched.active)}</div>
            <div className="mt-0.5 text-[11px] text-canvas-muted">etkin rapor</div>
            <CardFootRow
              label="Sıradaki"
              value={sched.next ? relative(sched.next.run_at) : 'yok'}
              tone={sched.next ? 'plain' : 'warn'}
            />
          </CanvasCard>
        ),
      },
      {
        id: 'alerts',
        ...SLOTS.b,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Uyarılar"
            accent="violet"
            icon={<Bell className="h-3.5 w-3.5" />}
            badge={alerts.triggered.length ? <CardBadge tone="fail">tetikte</CardBadge> : <CardBadge tone="ok">sakin</CardBadge>}
          >
            <div className="text-2xl font-black tracking-tight text-canvas-ink">{num(alerts.active)}</div>
            <div className="mt-0.5 text-[11px] text-canvas-muted">aktif kural</div>
            <CardFootRow
              label="Eşiği aşan"
              value={num(alerts.triggered.length)}
              tone={alerts.triggered.length ? 'warn' : 'ok'}
            />
          </CanvasCard>
        ),
      },
      {
        id: 'boards',
        ...SLOTS.c,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Panolar"
            accent="mint"
            icon={<LayoutDashboard className="h-3.5 w-3.5" />}
            note={engineOk ? 'motor bağlı' : 'motor kapalı'}
          >
            <div className="text-2xl font-black tracking-tight text-canvas-ink">{num(boardCount)}</div>
            <div className="mt-0.5 text-[11px] text-canvas-muted">pano</div>
            <CardFootRow
              label="Analitik motoru"
              value={engineOk ? 'çalışıyor' : (status?.health?.message ?? 'yapılandırılmadı')}
              tone={engineOk ? 'ok' : 'warn'}
            />
          </CanvasCard>
        ),
      },
      {
        id: 'engine',
        ...SLOTS.d,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Veri kaynağı"
            accent="amber"
            icon={<Database className="h-3.5 w-3.5" />}
            note="canlı"
          >
            <p className="text-[11.5px] leading-snug text-canvas-muted">
              Rakamlar portal API’si üzerinden canlı okunur. Bu ekran hiçbir değeri saklamaz; kart boşsa veri gerçekten
              yoktur.
            </p>
            <CardFootRow label="Pano sayısı (motor)" value={num(status?.health?.dashboard_count ?? null)} />
          </CanvasCard>
        ),
      },
      {
        id: 'attention',
        ...SLOTS.e,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Dikkat isteyen"
            accent="slate"
            icon={<Sparkles className="h-3.5 w-3.5" />}
            badge={needsAttention ? <CardBadge tone="warn">{num(needsAttention)}</CardBadge> : <CardBadge tone="ok">yok</CardBadge>}
          >
            <div className="space-y-1 text-[11px]">
              <div className="flex justify-between">
                <span className="text-canvas-muted">Alıcısız rapor</span>
                <span className="font-bold">{num(sched.recipientless.length)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-canvas-muted">Tetikte uyarı</span>
                <span className="font-bold">{num(alerts.triggered.length)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-canvas-muted">Hiç kontrol edilmemiş</span>
                <span className="font-bold">{num(alerts.neverChecked.length)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-canvas-muted">Başarısız gönderim</span>
                <span className="font-bold">{num(sched.failed)}</span>
              </div>
            </div>
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
                <span className="text-xs font-medium text-canvas-muted">Günün durumu</span>
              </div>
            </div>
            <p className="text-base font-bold leading-snug text-canvas-ink">
              {loading
                ? 'Modüller okunuyor…'
                : needsAttention === 0
                  ? '“Bekleyen bir sorun görünmüyor: raporların alıcısı tam, uyarılar sakin.”'
                  : `“${num(needsAttention)} madde dikkat istiyor.${
                      sched.recipientless.length ? ` ${num(sched.recipientless.length)} raporun alıcısı boş.` : ''
                    }${alerts.triggered.length ? ` ${num(alerts.triggered.length)} uyarı eşiği aşmış.` : ''}${
                      alerts.neverChecked.length ? ` ${num(alerts.neverChecked.length)} kural hiç çalıştırılmamış.` : ''
                    }”`}
            </p>
            {!stacked && (
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <a
                  href="/bi/canvas/planli-raporlar"
                  className="rounded-xl bg-slate-100 px-4 py-2.5 text-xs font-bold transition hover:bg-slate-200/80"
                >
                  Planlı raporlar
                </a>
                <a
                  href="/bi/canvas/uyarilar"
                  className="rounded-xl bg-slate-100 px-4 py-2.5 text-xs font-bold transition hover:bg-slate-200/80"
                >
                  Uyarılar
                </a>
                <a
                  href="/bi/canvas/panolar"
                  className="rounded-xl bg-slate-100 px-4 py-2.5 text-xs font-bold transition hover:bg-slate-200/80"
                >
                  Panolar
                </a>
              </div>
            )}
          </div>
        ),
      },
    ],
  };
}
