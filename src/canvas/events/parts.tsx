import type { ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { CLASS_TONE, type ClassKey } from './api';

/** Fuar ve etkinlik ekranlarının kabuğu (Pazarlama › Etkinlik). Bölüm bağlantıları adres çubuğunda durur: telefonda geri
 *  tuşu bir önceki bölüme döner, bağlantı paylaşılabilir. */

const SECTIONS = [
  { to: '/etkinlikler', label: 'Takvim', end: true },
  { to: '/etkinlikler/crm', label: 'CRM etkinlikleri', end: false },
  { to: '/etkinlikler/oduller', label: 'Ödüller', end: false },
  { to: '/etkinlikler/tip-eslemesi', label: 'Tip eşlemesi', end: false },
];

export function EventsFrame({ crumb, title, lead, source, presence, detail, back, aside, nav = true, children }: {
  crumb: string;
  title: string;
  lead?: string;
  source: string;
  presence: string;
  detail?: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
  nav?: boolean;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb, source, presence, detail }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to={back.to} className="inline-flex min-h-8 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    {back.label}
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Etkinlik</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            {nav && (
              <nav aria-label="Fuar ve etkinlik bölümleri" className="-mx-1 overflow-x-auto px-1">
                <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                  {SECTIONS.map((s) => (
                    <NavLink
                      key={s.to}
                      to={s.to}
                      end={s.end}
                      className={({ isActive }) =>
                        `inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                          isActive ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                        }`
                      }
                    >
                      {s.label}
                    </NavLink>
                  ))}
                </div>
              </nav>
            )}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Bölüm başlığı + isteğe bağlı sağ düğme. */
export function Block({ title, help, action, info, children }: { title: string; help?: ReactNode; action?: ReactNode; info?: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-panel min-w-0 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">{title}{info}</h2>
          {help && <p className="mt-0.5 max-w-[80ch] text-[11.5px] leading-snug text-canvas-muted">{help}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Kalan gün rozeti: 7 gün ve altı kırmızı, 30 gün ve altı sarı; geçmiş gri. */
export function DaysLeft({ days, doneLabel = 'geçti' }: { days: number | null | undefined; doneLabel?: string }) {
  if (days === null || days === undefined) return <span className="text-canvas-muted">—</span>;
  const tone = days < 0 ? 'bg-slate-100 text-canvas-muted' : days <= 7 ? 'bg-red-50 text-red-700' : days <= 30 ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-canvas-ink';
  return (
    <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 font-mono text-[11px] font-bold tabular-nums ${tone}`}>
      {days < 0 ? `${-days} gün ${doneLabel}` : days === 0 ? 'bugün' : `${days} gün`}
    </span>
  );
}

export function ClassPill({ cls, label, suggested }: { cls: ClassKey | null; label: string; suggested?: boolean }) {
  return (
    <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${CLASS_TONE[cls ?? 'yok']} ${suggested ? 'border border-dashed border-current' : ''}`}>
      {label}
    </span>
  );
}

/** Hazırlık çubuğu (yapılan görev ÷ bütün görevler). */
export function PrepBar({ prep, late }: { prep: number | null; late: number }) {
  if (prep === null) return <span className="text-[11px] text-canvas-muted">görev yok</span>;
  return (
    <div className="flex min-w-[110px] items-center gap-2">
      <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <div className={`absolute inset-y-0 left-0 rounded-full ${late ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.round(prep * 100)}%` }} />
      </div>
      <span className="w-10 text-right font-mono text-[11px] font-bold tabular-nums">%{Math.round(prep * 100)}</span>
    </div>
  );
}
