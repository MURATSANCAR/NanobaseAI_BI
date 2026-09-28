import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { STAGE_TONE, type Stage } from './api';

/** Kurumsal satış ekranlarının kabuğu. `back` verilirse başlığın üstünde geri bağlantısı (fırsat sayfası). */
export function CorporateFrame({
  title,
  lead,
  source,
  presence,
  detail,
  back,
  aside,
  children,
}: {
  title: string;
  lead: string;
  source: string;
  presence: string;
  detail?: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Saha satış ve okul', crumb: 'Kurumsal ve B2B', source, presence, detail }}>
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Saha satış ve okul · Kurumsal satış ve B2B</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
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

export function StagePill({ stage, label }: { stage: Stage; label: string }) {
  return <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${STAGE_TONE[stage]}`}>{label}</span>;
}

/** Ekranda kaynağı yazılan küçük satır (ör. «Logo · 17 Ağustos 2026'ya kadar»). */
export function SourceLine({ children }: { children: ReactNode }) {
  return <p className="text-[11.5px] leading-snug text-canvas-muted">{children}</p>;
}

/** Boş durum: ne olmadığını ve ne yapılacağını söyler. */
export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-8 text-center">
      <div className="text-[13px] font-extrabold">{title}</div>
      {children && <div className="mx-auto mt-1 max-w-[56ch] text-[12px] leading-snug text-canvas-muted">{children}</div>}
    </div>
  );
}
