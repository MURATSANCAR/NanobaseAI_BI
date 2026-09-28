import { useEffect, type ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { prApi, type Job } from './api';

/** Basın ilişkileri ekranlarının kabuğu (Pazarlama › İletişim). Üstte dört bölüm: Bugün · Medya kişileri ·
 *  Yansımalar · Rapor; PR dosyası ve kişi kartı bunların altındaki detay sayfalarıdır. */
const SECTIONS = [
  { to: '/basin-iliskileri', label: 'Bugün', end: true },
  { to: '/basin-iliskileri/kisiler', label: 'Medya kişileri', end: false },
  { to: '/basin-iliskileri/yansimalar', label: 'Yansımalar', end: false },
  { to: '/basin-iliskileri/rapor', label: 'Rapor', end: false },
];

export function PrFrame({ crumb, title, lead, source, presence, back, aside, children }: {
  crumb: string;
  title: string;
  lead?: string;
  source: string;
  presence: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · İletişim</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[440px]">{aside}</div>}
            </header>
            <nav aria-label="Basın ilişkileri" className="-mx-1 overflow-x-auto px-1">
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
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Bölüm kutusu: başlık, kısa açıklama, sağda düğme. */
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

/** Boş durum: ne olduğunu ve ne yapılacağını söyler. */
export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-4 text-[12.5px] leading-snug text-canvas-muted">{children}</p>;
}

/** Zeki AI işini sorar; bitince `onDone` çağrılır (ilgili sorgular tazelenir). */
export function useJob(job: Job | null | undefined, onDone: () => void) {
  const qc = useQueryClient();
  const running = !!job && (job.status === 'bekliyor' || job.status === 'calisiyor');
  const q = useQuery({
    queryKey: ['pr', 'job', job?.id],
    queryFn: () => prApi.job(job!.id),
    enabled: ENGINE_ENABLED && running,
    refetchInterval: (s) => (s.state.data && (s.state.data.status === 'bitti' || s.state.data.status === 'hata') ? false : 2500),
  });
  const status = q.data?.status;
  useEffect(() => {
    if (status === 'bitti' || status === 'hata') {
      onDone();
      qc.removeQueries({ queryKey: ['pr', 'job', job?.id] });
    }
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps
  return { running: running && status !== 'bitti' && status !== 'hata', live: q.data ?? job ?? null };
}
