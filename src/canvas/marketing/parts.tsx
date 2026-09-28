import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';

/** Pazarlama ekranlarının kabuğu (Pazarlama › Planlama). Sekme çubuğu ve onay penceresi bütçe ekranınınkiyle aynı
 *  (`budget/parts`): iki ekranda aynı el alışkanlığı. */
export function MarketingFrame({ crumb, title, lead, source, presence, detail, back, aside, children }: {
  crumb: string;
  title: string;
  lead?: string;
  source: string;
  presence: string;
  detail?: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Planlama</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Kalan gün rozeti: 14 gün ve altı kırmızı, 30 gün ve altı sarı. */
export function DaysLeft({ days }: { days: number | null }) {
  if (days === null) return <span className="text-canvas-muted">—</span>;
  const tone = days < 0 ? 'bg-slate-100 text-canvas-muted' : days <= 14 ? 'bg-red-50 text-red-700' : days <= 30 ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-canvas-ink';
  return (
    <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 font-mono text-[11px] font-bold tabular-nums ${tone}`}>
      {days < 0 ? `${-days} gün geçti` : days === 0 ? 'bugün' : `${days} gün`}
    </span>
  );
}

/** Bölüm başlığı + isteğe bağlı sağ düğme. `info`: başlığın yanındaki sorgu bilgisi «i»'si (`<SqlInfo …/>`). */
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

/** Rakamın nereden geldiği: açılır küçük kutu (SQL ya da kaynak cümlesi). */
export function SourceNote({ text, sql }: { text?: string | null; sql?: string | null }) {
  if (!text && !sql) return null;
  return (
    <details className="mt-2 text-[11px] text-canvas-muted">
      <summary className="inline-flex min-h-8 cursor-pointer items-center font-bold text-canvas-violet">Kaynak</summary>
      {text && <p className="mt-1 leading-snug">{text}</p>}
      {sql && <pre className="mt-1 max-w-full overflow-x-auto rounded-lg bg-slate-50 p-2 font-mono text-[10.5px] leading-snug">{sql}</pre>}
    </details>
  );
}
