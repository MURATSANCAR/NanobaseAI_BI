import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { Pill } from '../admin/ui';
import { CONSENT_TONE, readersApi, type ConsentStatus } from './api';

/** Okur veri tabanı ekranlarının ortak parçaları: kabuk, bölüm çubuğu (adres çubuğuyla), meta sorgusu. */

export const ROOT = '/okurlar';

export const SECTIONS = [
  { to: ROOT, label: 'Özet' },
  { to: `${ROOT}/ara`, label: 'Okur ara' },
  { to: `${ROOT}/birlestirme`, label: 'Birleştirme' },
  { to: `${ROOT}/segmentler`, label: 'Segmentler' },
  { to: `${ROOT}/yuklemeler`, label: 'Yüklemeler' },
  { to: `${ROOT}/disa-aktarimlar`, label: 'Dışa aktarımlar' },
  { to: `${ROOT}/kvkk`, label: 'KVKK başvurusu' },
] as const;

export function useMeta() {
  return useQuery({ queryKey: ['readers', 'meta'], queryFn: readersApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export function ReadersFrame({ presence, aside, badges, children }: {
  presence: string;
  aside?: ReactNode;
  badges?: Record<string, number | null>;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb: 'Okurlar', source: 'CRM (okuma) + etkinlik dosyaları', presence }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Dijital ve topluluk · Okur ve topluluk</div>
                <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Okur veri tabanı</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">
                  CRM kişi, müşteri adayı ve İYS kayıtlarını aynı e-posta ya da telefonla tek okurda birleştirir; kanal başına izni
                  gösterir, kurala dayalı segment kurar. Ekranda kişi adı yok, sayılar var. Portal CRM'e yazmaz ve ileti göndermez.
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

const CONSENT_LABEL: Record<ConsentStatus, string> = { izinli: 'İzinli', ret: 'Ret', bilinmiyor: 'Bilinmiyor' };

export function ConsentPill({ status, prefix }: { status: ConsentStatus; prefix?: string }) {
  return <Pill tone={CONSENT_TONE[status]}>{prefix ? `${prefix}: ` : ''}{CONSENT_LABEL[status]}</Pill>;
}

/** Oran çubuğu: izinli / ret / bilinmiyor (renk + sayı; renk tek başına anlam taşımaz). */
export function ConsentBar({ label, counts, reach }: { label: string; counts: Record<ConsentStatus, number>; reach?: number }) {
  const total = counts.izinli + counts.ret + counts.bilinmiyor;
  const w = (n: number) => (total ? `${(n / total) * 100}%` : '0%');
  const nf = new Intl.NumberFormat('tr-TR');
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2 text-[12.5px] font-bold">
        <span>{label}</span>
        {reach != null && (
          <span className="font-mono text-[12px] tabular-nums text-canvas-muted">
            listeye girebilir <strong className="text-canvas-ink">{nf.format(reach)}</strong>
          </span>
        )}
      </div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <div className="h-full bg-emerald-500" style={{ width: w(counts.izinli) }} />
        <div className="h-full bg-red-400" style={{ width: w(counts.ret) }} />
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11.5px] font-semibold text-canvas-muted">
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-emerald-500" />İzinli {nf.format(counts.izinli)}</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-red-400" />Ret {nf.format(counts.ret)}</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-full bg-slate-300" />Bilinmiyor {nf.format(counts.bilinmiyor)}</span>
      </div>
    </div>
  );
}
