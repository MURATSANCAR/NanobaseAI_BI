import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { fmtDay } from '../budget/api';

/** İlk dağılım ekranlarının ortak kabuğu ve küçük parçaları. Sekme çubuğu ve onay penceresi bütçeden (`../budget/parts`). */

export function DistFrame({ title, lead, presence, source, back, aside, children }: {
  title: string;
  lead: string;
  presence: string;
  source: string;
  back?: boolean;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Satış ve saha', crumb: 'İlk dağılım', source, presence, detail: back ? title : undefined }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to="/ilk-dagilim" className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    Dağılım bekleyenler
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Satış ve saha · İlk dağılım yönetimi</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[420px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Logo verisinin bittiği gün: her ekranda yazılır (donmuş kopyada takip anlamını yitirir). */
export function DataEnd({ veriSonu, depoSonu }: { veriSonu: string | null | undefined; depoSonu?: string | null }) {
  return (
    <div className="rounded-2xl bg-white/70 px-3 py-2 text-[12px] font-semibold text-canvas-muted">
      {veriSonu ? (
        <>
          Logo satış ve sevk verisi <strong className="text-canvas-ink">{fmtDay(veriSonu)}</strong> tarihinde bitiyor
          {depoSonu ? <>, son üretimden giriş {fmtDay(depoSonu)}</> : null}; takip ve uyarılar bu güne göre değerlendirilir.
          Sonraki depo girişleri üretim kartından (CRM) gelir.
        </>
      ) : (
        'Logo verisi henüz okunmadı; liste ilk yenilemede dolar.'
      )}
    </div>
  );
}

/** Oran çubuğu (0–1, 1'de doyar). */
export function Share({ value, tone = 'violet' }: { value: number | null; tone?: 'violet' | 'emerald' | 'amber' }) {
  const w = value === null ? 0 : Math.max(0, Math.min(1, value));
  const bar = { violet: 'bg-canvas-violet', emerald: 'bg-emerald-500', amber: 'bg-amber-400' }[tone];
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100" aria-hidden>
      <div className={`h-full rounded-full ${bar}`} style={{ width: `${w * 100}%` }} />
    </div>
  );
}

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
export const n0 = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
