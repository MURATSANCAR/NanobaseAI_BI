import { AlertTriangle, CalendarClock, Clock, Mail, MailX, Send } from 'lucide-react';
import CanvasCard, { CardBadge, CardFootRow } from '../ui/CanvasCard';
import { Donut, ProgressBar } from '../ui/charts';
import { SLOTS } from '../layout';
import type { CanvasScreen } from '../types';
import type { ScheduleSummary } from '../data';
import { dateTime, num, recurrenceLabel, relative, scheduleStatus } from '../format';

/**
 * Planlı raporlar ekranı.
 *
 * Modülün işi: sohbetten kurulan e-posta raporlarını zamanında göndermek.
 * Eski liste ekranı yalnız konu/alıcı/durum gösteriyordu; `error`, `sent_at` ve
 * "sıradaki gönderim" alanları veride olmasına rağmen hiç ekrana çıkmıyordu.
 * Kanvas bu üç boşluğu kapatır: ne zaman gönderilecek, kime gitmeyecek, en son
 * ne patladı.
 */
export function schedulesScreen(s: ScheduleSummary, loading: boolean): CanvasScreen {
  const next = s.next;
  const nextStatus = scheduleStatus(next?.status);

  return {
    id: 'schedules',
    crumb: 'Planlı raporlar',
    askPlaceholder: 'ZEKİ’ye sor… örn. her pazartesi 09:00 satış özeti gönder',
    question: {
      who: 'TY',
      role: 'Timaş Yayınları · Planlı raporlar',
      at: 'Şimdi',
      text: 'Raporlar zamanında ve doğru kişiye gidiyor mu?',
      answered: !loading,
    },
    cards: [
      {
        id: 'next',
        ...SLOTS.a,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Sıradaki gönderim"
            accent="coral"
            icon={<Clock className="h-3.5 w-3.5" />}
            badge={<CardBadge tone={nextStatus.tone === 'ok' ? 'ok' : 'warn'}>{nextStatus.label}</CardBadge>}
          >
            {next ? (
              <>
                <div className="text-2xl font-black tracking-tight text-canvas-coral">{relative(next.run_at)}</div>
                <div className="mt-0.5 truncate text-xs font-semibold text-canvas-ink" title={next.subject}>
                  {next.subject}
                </div>
                <div className="mt-2 text-[11px] text-canvas-muted">
                  {dateTime(next.run_at)}
                  {next.local_time ? ` · ${next.local_time}` : ''} · {recurrenceLabel(next.recurrence)}
                </div>
                <CardFootRow
                  label="Alıcı"
                  value={next.recipient?.trim() || 'yok'}
                  tone={next.recipient?.trim() ? 'plain' : 'warn'}
                />
              </>
            ) : (
              <div className="py-3 text-xs text-canvas-muted">
                {loading ? 'Yükleniyor…' : 'Bekleyen gönderim yok. Sohbetten bir rapor planlayın.'}
              </div>
            )}
          </CanvasCard>
        ),
      },
      {
        id: 'calendar',
        ...SLOTS.b,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Takvim"
            accent="violet"
            icon={<CalendarClock className="h-3.5 w-3.5" />}
            note={`${num(s.active)} etkin`}
          >
            {s.upcoming.length ? (
              <div className="space-y-1.5">
                {s.upcoming.map((it) => (
                  <div key={it.id} className="flex items-center gap-2">
                    <span className="w-[52px] shrink-0 font-mono text-[10px] font-bold tabular-nums text-canvas-violet">
                      {dateTime(it.run_at).slice(0, 5)}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[11.5px] font-semibold" title={it.subject}>
                      {it.subject}
                    </span>
                    <span className="shrink-0 text-[10px] text-canvas-muted">{recurrenceLabel(it.recurrence)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-3 text-xs text-canvas-muted">{loading ? 'Yükleniyor…' : 'Sırada rapor yok.'}</div>
            )}
            <CardFootRow label="Uyarı eklenen" value={`${num(s.withAlerts)} / ${num(s.total)}`} />
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
            icon={<Send className="h-3.5 w-3.5" />}
            note={`${num(s.total)} rapor`}
          >
            <Donut
              center={num(s.total)}
              slices={[
                { label: 'Etkin', value: s.active, accent: 'mint' },
                { label: 'Duraklatıldı', value: s.paused, accent: 'amber' },
                { label: 'Başarısız', value: s.failed, accent: 'coral' },
                { label: 'Gönderildi', value: s.sent, accent: 'slate' },
              ]}
            />
            <CardFootRow label="Yorum metni eklenen" value={`${num(s.withNarrative)} rapor`} />
          </CanvasCard>
        ),
      },
      {
        id: 'recipientless',
        ...SLOTS.d,
        render: ({ stacked }) => {
          const n = s.recipientless.length;
          return (
            <CanvasCard
              stacked={stacked}
              title="Alıcısız raporlar"
              accent="amber"
              icon={<MailX className="h-3.5 w-3.5" />}
              badge={n ? <CardBadge tone="warn">düzeltilmeli</CardBadge> : <CardBadge tone="ok">temiz</CardBadge>}
            >
              <div className="text-2xl font-black tracking-tight text-canvas-ink">{num(n)}</div>
              <div className="mt-0.5 text-[11px] text-canvas-muted">
                {n ? 'Bu raporlar çalışır ama kimseye ulaşmaz.' : 'Her raporun en az bir alıcısı var.'}
              </div>
              {n > 0 && (
                <div className="mt-2.5 space-y-1">
                  {s.recipientless.slice(0, 3).map((it) => (
                    <div key={it.id} className="truncate rounded-lg bg-amber-50/70 px-2 py-1 text-[11px] font-semibold text-amber-800">
                      {it.subject}
                    </div>
                  ))}
                </div>
              )}
              <CardFootRow label="E-posta kanalı" value={`${num(s.total - n)} / ${num(s.total)}`} tone={n ? 'warn' : 'ok'} />
            </CanvasCard>
          );
        },
      },
      {
        id: 'failure',
        ...SLOTS.e,
        render: ({ stacked }) => (
          <CanvasCard
            stacked={stacked}
            title="Son hata"
            accent="slate"
            icon={<AlertTriangle className="h-3.5 w-3.5" />}
            badge={s.lastFailure ? <CardBadge tone="fail">hata</CardBadge> : <CardBadge tone="ok">yok</CardBadge>}
          >
            {s.lastFailure ? (
              <>
                <div className="truncate text-xs font-bold text-canvas-ink" title={s.lastFailure.subject}>
                  {s.lastFailure.subject}
                </div>
                <p className="mt-1.5 max-h-16 overflow-hidden text-[11px] leading-snug text-red-700">
                  {s.lastFailure.error || 'Sunucu ayrıntı vermedi.'}
                </p>
                <CardFootRow label="Denendiği an" value={dateTime(s.lastFailure.sent_at ?? s.lastFailure.run_at)} />
              </>
            ) : (
              <div className="py-3 text-[11px] text-canvas-muted">
                Kayıtlarda başarısız gönderim yok. Bu alan veride vardı ama eski ekranda hiç gösterilmiyordu.
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
                <span className="text-xs font-medium text-canvas-muted">Planlı raporlar · {num(s.total)} kayıt</span>
              </div>
              <span className="text-xs font-semibold text-canvas-muted">
                {s.recipientless.length ? 'Dikkat gerektiren durum var' : 'Kuyruk sağlıklı'}
              </span>
            </div>
            <p className="text-base font-bold leading-snug text-canvas-ink">
              {loading
                ? 'Rapor kuyruğu okunuyor…'
                : s.total === 0
                  ? '“Henüz planlı rapor yok. Sohbete ‘her pazartesi 09:00 satış özeti gönder’ yazarak ilkini kurabilirsiniz.”'
                  : `“${num(s.active)} rapor etkin${
                      s.next ? `, en yakını ${relative(s.next.run_at)}` : ''
                    }.${s.recipientless.length ? ` ${num(s.recipientless.length)} raporun alıcısı boş; çalışsalar da kimseye ulaşmaz.` : ''}${
                      s.failed ? ` ${num(s.failed)} gönderim başarısız.` : ''
                    }”`}
            </p>
            {!stacked && (
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-canvas-muted">
                <span>
                  <strong className="text-canvas-ink">Etkin:</strong> {num(s.active)}
                </span>
                <span className="text-slate-300">•</span>
                <span>
                  <strong className="text-canvas-ink">Duraklatılmış:</strong> {num(s.paused)}
                </span>
                <span className="text-slate-300">•</span>
                <span>
                  <strong className="text-canvas-ink">Başarısız:</strong> {num(s.failed)}
                </span>
              </div>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <a
                href="/bi/schedules"
                className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-canvas-coral to-canvas-violet px-5 py-2.5 text-xs font-extrabold tracking-tight text-white shadow-md transition-all hover:opacity-95 active:scale-95"
              >
                <Mail className="h-4 w-4" />
                Raporları yönet
              </a>
              <a
                href="/bi/chat"
                className="flex items-center gap-1.5 rounded-xl bg-slate-100 px-4 py-2.5 text-xs font-bold text-canvas-ink transition-all hover:bg-slate-200/80 active:scale-95"
              >
                Sohbetten yeni rapor kur
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
                <span className="text-[8px] font-black uppercase tracking-widest text-white/70">Sıradaki</span>
                <span className="font-mono text-[8px] text-white/60">{next ? recurrenceLabel(next.recurrence) : '—'}</span>
              </div>
              <div className="my-auto text-center">
                <div className="mx-auto mb-1.5 flex h-10 w-10 items-center justify-center rounded-full border border-white/40">
                  <Mail className="h-4 w-4 text-white/90" />
                </div>
                <h2 className="line-clamp-3 text-[10px] font-black leading-tight tracking-wide text-white drop-shadow-sm">
                  {next?.subject ?? 'Planlı rapor yok'}
                </h2>
              </div>
              <div className="flex items-center justify-between border-t border-white/20 pt-1 text-[7px] text-white/80">
                <span>{next ? dateTime(next.run_at).slice(0, 10) : '—'}</span>
                <span className="font-bold">{next?.local_time ?? ''}</span>
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
                <span className="text-[11px] font-extrabold text-slate-700">Gönderilmiş raporlar</span>
                <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold text-slate-600">{num(s.sent)}</span>
              </div>
              <p className="mt-2 text-[10px] font-medium leading-relaxed text-slate-600">
                Kuyruktan çıkmış gönderimler burada birikiyor.
              </p>
            </div>
          </div>
        ),
      },
      {
        id: 'health',
        x: 290,
        y: 700,
        w: 860,
        connect: false,
        render: ({ stacked }) =>
          stacked ? null : (
            <div className="cv-card rounded-[24px] px-5 py-4 shadow-canvas-card">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-[13px] font-extrabold">Kuyruk sağlığı</span>
                <span className="text-[11px] text-canvas-muted">
                  Alıcısı olan {num(s.total - s.recipientless.length)} / {num(s.total)}
                </span>
              </div>
              <ProgressBar
                pct={s.total ? ((s.total - s.recipientless.length) / s.total) * 100 : 0}
                left="Alıcısı tanımlı raporlar"
                right={s.recipientless.length ? `${num(s.recipientless.length)} eksik` : 'eksik yok'}
                gradient={s.recipientless.length ? 'from-canvas-amber to-canvas-coral' : 'from-canvas-mint to-canvas-violet'}
              />
            </div>
          ),
      },
    ],
  };
}
