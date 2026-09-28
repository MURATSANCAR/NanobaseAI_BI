import type { ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { GIFT_TONE, STAGE_FLOW, paApi, type GiftStatus, type Stage } from './api';

/** M28 Kurumsal ilişkiler ekranlarının ortak parçaları: kabuk + alt sekmeler, aşama çubuğu, durum etiketleri. */

export const BASE = '/kurumsal-iliskiler';

const SUBNAV = [
  { to: BASE, label: 'Bugün', end: true },
  { to: `${BASE}/kisiler`, label: 'Kişiler' },
  { to: `${BASE}/kurumlar`, label: 'Kurumlar' },
  { to: `${BASE}/hediye`, label: 'Hediye programı' },
  { to: `${BASE}/projeler`, label: 'Projeler' },
  { to: `${BASE}/rapor`, label: 'Etki raporu' },
];

export function PaFrame({
  title,
  lead,
  source = 'Portal + CRM',
  presence = 'Kaynak: portal + CRM',
  back,
  aside,
  children,
}: {
  title: string;
  lead: string;
  source?: string;
  presence?: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb: 'Kurumsal ilişkiler', source, presence, detail: back ? title : undefined }}>
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Kurumsal ilişkiler</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-auto lg:max-w-[460px]">{aside}</div>}
            </header>
            {!back && <SubNav />}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

function SubNav() {
  return (
    <nav aria-label="Kurumsal ilişkiler bölümleri" className="-mx-1 overflow-x-auto px-1">
      <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
        {SUBNAV.map((s) => (
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
  );
}

export const metaOptions = () => queryOptions({ queryKey: ['pa', 'meta'], queryFn: paApi.meta, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });
export function usePaMeta() {
  return useQuery(metaOptions());
}

/** Bir kayıt değişince ilişkili bütün görünümler yeniden okunur. */
export function invalidatePa(qc: QueryClient): Promise<void> {
  return qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'pa' && q.queryKey[1] !== 'meta' });
}

/** Açık aşamaların çubuğu: geçilen aşamalar dolu, bulunulan aşama vurgulu. Kapanan/vazgeçilen proje ayrı yazılır. */
export function StageBar({ stage, label }: { stage: Stage; label: string }) {
  if (stage === 'kapandi' || stage === 'vazgecildi') {
    return <span className={`inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-bold ${stage === 'kapandi' ? 'bg-emerald-50 text-emerald-800' : 'bg-slate-100 text-canvas-muted'}`}>{label}</span>;
  }
  const idx = STAGE_FLOW.indexOf(stage);
  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className="flex gap-0.5" role="img" aria-label={`Aşama ${idx + 1} / ${STAGE_FLOW.length}: ${label}`}>
        {STAGE_FLOW.map((s, i) => (
          <span key={s} className={`h-1.5 w-4 rounded-full sm:w-5 ${i < idx ? 'bg-canvas-violet/45' : i === idx ? 'bg-canvas-violet' : 'bg-slate-200'}`} />
        ))}
      </div>
      <span className="truncate text-[11.5px] font-bold">{label}</span>
    </div>
  );
}

export function GiftPill({ status, label }: { status: GiftStatus; label: string }) {
  return <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${GIFT_TONE[status]}`}>{label}</span>;
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-8 text-center">
      <div className="text-[13px] font-extrabold">{title}</div>
      {children && <div className="mx-auto mt-1 max-w-[56ch] text-[12px] leading-snug text-canvas-muted">{children}</div>}
    </div>
  );
}

/** Bölüm başlığı + sağında işlem (kart içi). */
export function Block({ title, help, action, info, children }: { title: string; help?: string; action?: ReactNode; info?: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold tracking-tight">{title}{info}</h2>
          {help && <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{help}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
