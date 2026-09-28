import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../../stitch/Shell';
import { Pill } from '../../admin/ui';
import { fmtMoney, fmtPct } from '../../budget/api';

/** Set ve hediye ekranlarının ortak parçaları: kabuk, marj hücresi, maliyet kapalı notu. */

export function SetsFrame({ title, lead, back, source, presence, aside, children }: {
  title: string;
  lead: string;
  /** Detay sayfasında listeye dönüş bağlantısı. */
  back?: { to: string; label: string };
  source: string;
  presence: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb: 'Set ve hediye', source, presence, detail: back ? title : undefined }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to={back.to} className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    {back.label}
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Üretim</div>
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

/** Marj: maliyet yetkisi yoksa alan hiç gelmez (undefined) → «—»; maliyet bilinmiyorsa (null) → «bilinmiyor». */
export function MarginCell({ marj, oran, floor }: { marj?: number | null; oran?: number | null; floor?: number | null }) {
  if (marj === undefined) return <span className="text-canvas-muted">—</span>;
  if (marj === null) return <span className="text-[11.5px] font-semibold text-canvas-muted">bilinmiyor</span>;
  const low = oran !== null && oran !== undefined && floor !== null && floor !== undefined && oran < floor / 100;
  return (
    <span className="inline-flex flex-col items-end">
      <span className={`font-mono tabular-nums ${marj < 0 || low ? 'font-bold text-red-700' : ''}`}>{fmtMoney(marj)}</span>
      <span className="font-mono text-[11px] tabular-nums text-canvas-muted">{fmtPct(oran ?? null)}</span>
    </span>
  );
}

export function Tone({ tone, children }: { tone: 'ok' | 'warn' | 'muted' | 'violet' | 'err'; children: ReactNode }) {
  return <Pill tone={tone}>{children}</Pill>;
}

/** Kişi başı bütçe ↔ fiyat: kalan pay. */
export function BudgetGap({ gap }: { gap: number }) {
  return <span className="font-mono text-[11.5px] tabular-nums text-canvas-muted">bütçeye {fmtMoney(gap)} kalıyor</span>;
}
