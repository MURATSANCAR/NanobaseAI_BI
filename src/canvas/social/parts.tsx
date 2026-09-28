import type { ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Pill } from '../admin/ui';
import { STATUS_TONE, accountColor, type Account, type PostStatus } from './api';

/** Sosyal medya ekranlarının kabuğu (Pazarlama › İletişim) ve ortak küçük parçaları. Sekmeler bağlantıdır: her ekran
 *  kendi adresinde, geri tuşu ve paylaşılan bağlantı doğru ekranı açar. */

const TABS = [
  { to: '/sosyal-medya', label: 'Takvim', end: true },
  { to: '/sosyal-medya/firsatlar', label: 'Fırsatlar' },
  { to: '/sosyal-medya/rapor', label: 'Rapor' },
  { to: '/sosyal-medya/hesaplar', label: 'Hesaplar' },
] as const;

export function SocialFrame({ crumb, title, lead, source, presence, back, aside, tabs = true, children }: {
  crumb: string;
  title: string;
  lead?: string;
  source: string;
  presence: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
  tabs?: boolean;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb, source, presence }}>
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Sosyal medya</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            {tabs && (
              <nav aria-label="Sosyal medya bölümleri" className="-mx-1 overflow-x-auto px-1">
                <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                  {TABS.map((t) => (
                    <NavLink
                      key={t.to}
                      to={t.to}
                      end={'end' in t ? t.end : false}
                      className={({ isActive }) =>
                        `inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3.5 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                          isActive ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                        }`
                      }
                    >
                      {t.label}
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

export function StatusPill({ status, label }: { status: PostStatus; label: string }) {
  return <Pill tone={STATUS_TONE[status]}>{label}</Pill>;
}

/** Hesap işareti: renkli nokta + ad. Renk tek başına anlam taşımaz; adı yanında yazar. */
export function AccountTag({ account, compact }: { account: Account | null | undefined; compact?: boolean }) {
  if (!account) return <span className="text-[11.5px] font-semibold text-canvas-muted">Hesap yok</span>;
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 text-[11.5px] font-bold text-canvas-ink">
      <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: accountColor(account) }} />
      <span className="truncate">{compact ? `${account.platformAdi} · ${account.handle}` : account.ad}</span>
    </span>
  );
}

/** Bölüm başlığı + isteğe bağlı sağ düğme. */
export function Block({ title, help, action, info, children }: { title: string; help?: ReactNode; action?: ReactNode; info?: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
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

/** Kalan gün rozeti: 7 gün ve altı kırmızı, 14 gün ve altı sarı. */
export function DaysLeft({ days, running }: { days: number; running?: boolean }) {
  if (running) return <Pill tone="ok">Sürüyor</Pill>;
  const tone = days <= 7 ? 'bg-red-50 text-red-700' : days <= 14 ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-canvas-ink';
  return (
    <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 font-mono text-[11px] font-bold tabular-nums ${tone}`}>
      {days === 0 ? 'bugün' : `${days} gün`}
    </span>
  );
}
