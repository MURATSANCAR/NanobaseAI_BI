import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { Pill } from '../admin/ui';
import { SEGMENT_TONE, commerceApi, type Segment } from './api';

/** E-ticaret müşteri ekranlarının ortak parçaları: kabuk, bölüm çubuğu (adres çubuğuyla), meta sorgusu. */

export const ROOT = '/eticaret-musteri';

export const SECTIONS = [
  { to: ROOT, label: 'Özet' },
  { to: `${ROOT}/musteriler`, label: 'Müşteriler' },
  { to: `${ROOT}/tetikler`, label: 'Tetikler' },
  { to: `${ROOT}/kampanyalar`, label: 'Kampanya sonuçları' },
  { to: `${ROOT}/huni`, label: 'Ürün hunisi' },
  { to: `${ROOT}/veri`, label: 'Veri ve eşikler' },
] as const;

export function useMeta() {
  return useQuery({ queryKey: ['commerce', 'meta'], queryFn: commerceApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export function CommerceFrame({ presence, aside, badges, children }: {
  presence: string;
  aside?: ReactNode;
  badges?: Record<string, number | null>;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb: 'E-ticaret müşterileri', source: 'T-soft (okuma) + Logo kanal cirosu', presence }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Dijital ve topluluk · Okur ve topluluk</div>
                <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">E-ticaret müşterileri</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">
                  timas.com.tr siparişlerinden müşteri segmentleri, tetik listeleri ve kontrol gruplu kampanya sonucu. Müşteri adı ekranda
                  yok; kişi bilgisi yalnız yetkiyle ve o an siteden okunur. Portal siteye, CRM'e ve Logo'ya yazmaz, ileti göndermez.
                </p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[420px]">{aside}</div>}
            </header>
            <nav aria-label="Bölüm" className="-mx-1 overflow-x-auto px-1">
              <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                {SECTIONS.map((s) => {
                  const active = s.to === ROOT ? here === ROOT : here.startsWith(s.to);
                  const badge = badges?.[s.to];
                  return (
                    <Link
                      key={s.to}
                      to={s.to}
                      aria-current={active ? 'page' : undefined}
                      className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                        active ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                      }`}
                    >
                      {s.label}
                      {badge ? (
                        <span className={`rounded-md px-1.5 py-0.5 font-mono text-[10.5px] tabular-nums ${active ? 'bg-white/20' : 'bg-amber-50 text-amber-800'}`}>{badge}</span>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            </nav>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export function SegmentPill({ segment, label }: { segment: Segment; label: string }) {
  return <Pill tone={SEGMENT_TONE[segment]}>{label}</Pill>;
}

/** Sayı + değişim: artış yeşil, düşüş kırmızı; işaret metinde de var (renk tek başına anlam taşımaz). */
export function Delta({ value, text }: { value: number | null | undefined; text: string }) {
  if (value == null) return <span className="text-canvas-muted">{text}</span>;
  return <span className={value >= 0 ? 'text-emerald-700' : 'text-red-700'}>{text}</span>;
}
