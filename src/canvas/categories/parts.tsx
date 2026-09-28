import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { categoriesApi } from './api';

/** Kategori ağacı ekranlarının ortak parçaları: kabuk, bölüm çubuğu (adres çubuğuyla), meta sorgusu. */

export const ROOT = '/kategori-agaci';

export const SECTIONS = [
  { to: ROOT, label: 'Özet' },
  { to: `${ROOT}/kuyruk`, label: 'Onay kuyruğu' },
  { to: `${ROOT}/agac`, label: 'Kategori ağacı' },
  { to: `${ROOT}/tutarsizlik`, label: 'Tutarsızlıklar' },
  { to: `${ROOT}/crm-farki`, label: "CRM'e işlenecek" },
  { to: `${ROOT}/etiketler`, label: 'Etiket sözlüğü' },
] as const;

export function useMeta() {
  return useQuery({ queryKey: ['categories', 'meta'], queryFn: categoriesApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export function CategoriesFrame({ presence, aside, badges, children }: {
  presence: string;
  aside?: ReactNode;
  badges?: Record<string, number | null>;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Kayıtlar', crumb: 'Kategori ağacı', source: 'CRM + Logo + T-soft (okuma)', presence }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Kayıtlar · Kategori ağacı ve kitap profili</div>
                <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Kategori ağacı</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">
                  CRM'deki yedi ayrı sınıflamayı ve sitenin kategori ağacını tek onaylı ağaca bağlar. Zeki AI kitap başına kategori, tür, yaş,
                  tema ve etiket önerir; editör alan alan onaylar. Portal CRM'e ve siteye yazmaz: onaylanan fark liste olarak CRM'e işlenir.
                </p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[440px]">{aside}</div>}
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
                        <span className={`rounded-md px-1.5 py-0.5 font-mono text-[10.5px] tabular-nums ${active ? 'bg-white/20' : 'bg-red-50 text-red-700'}`}>{badge}</span>
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

/** Doluluk çubuğu: dolu / toplam. */
export function FillBar({ label, filled, total }: { label: string; filled: number; total: number }) {
  const share = total ? filled / total : 0;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2 text-[12px] font-semibold">
        <span className="truncate">{label}</span>
        <span className="shrink-0 font-mono tabular-nums text-canvas-muted">
          {new Intl.NumberFormat('tr-TR').format(filled)} · %{Math.round(share * 100)}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <div className={`h-full rounded-full ${share >= 0.8 ? 'bg-emerald-500' : share >= 0.5 ? 'bg-amber-400' : 'bg-red-400'}`} style={{ width: `${share * 100}%` }} />
      </div>
    </div>
  );
}

/** Olasılık rozeti: Zeki AI'ın ne kadar emin olduğu. */
export function Confidence({ probability, confident, method }: { probability?: number | null; confident?: boolean; method?: string }) {
  if (method === 'beyan') return <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-bold text-canvas-ink">CRM beyanı</span>;
  if (confident === false)
    return <span className="rounded-md bg-amber-50 px-1.5 py-0.5 text-[11px] font-bold text-amber-800">Zeki AI emin değil{probability != null ? ` · %${Math.round(probability * 100)}` : ''}</span>;
  if (probability != null)
    return <span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-bold text-emerald-700">Zeki AI · %{Math.round(probability * 100)}</span>;
  return <span className="rounded-md bg-canvas-violet/10 px-1.5 py-0.5 text-[11px] font-bold text-canvas-violet">Zeki AI önerisi</span>;
}
