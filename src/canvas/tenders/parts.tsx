import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Pill } from '../admin/ui';
import { fmtLeft, leftTone } from './api';

/** İhale ekranlarının ortak kabuğu ve küçük parçaları. Sekme çubuğu ve onay penceresi bütçe ekranınınkiyle aynıdır. */
export { Tabs, AskSheet } from '../budget/parts';

export function TenderFrame({ title, lead, detail, back, aside, children }: {
  title: string;
  lead: string;
  /** Detay sayfasında kırıntının son halkası. */
  detail?: string;
  back?: boolean;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Satış ve saha', crumb: 'İhale takibi', source: 'Kaynak: portal kaydı · Logo · CRM', presence: 'İhale takibi', detail }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to="/ihale" className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    İhale listesi
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Satış ve saha · Kurumsal</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
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

export function LeftPill({ days }: { days: number | null | undefined }) {
  return <Pill tone={leftTone(days)}>{fmtLeft(days)}</Pill>;
}

/** 0–100 uygunluk puanı; puan yoksa neden yazılır. */
export function ScoreBadge({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-[11.5px] text-canvas-muted">puan yok</span>;
  const tone = value >= 70 ? 'bg-emerald-500' : value >= 45 ? 'bg-amber-400' : 'bg-red-500';
  return (
    <span className="inline-flex min-w-[88px] items-center gap-2" title="Uygunluk puanı (100 üzerinden)">
      <span className="relative h-1.5 w-12 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <span className={`absolute inset-y-0 left-0 rounded-full ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </span>
      <span className="font-mono text-[12px] font-bold tabular-nums">{Math.round(value)}</span>
    </span>
  );
}

/** Kısa etiketli değer (özet kutuları). */
export function Fact({ label, value, help }: { label: string; value: ReactNode; help?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-0.5 break-words text-[13.5px] font-bold">{value}</div>
      {help && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}

/** Dosya seçme düğmesi (gizli input + etiket; telefonda dokunulabilir boy). */
export function FilePick({ label, accept, disabled, onPick }: { label: string; accept: string; disabled?: boolean; onPick: (f: File) => void }) {
  return (
    <label className={`inline-flex min-h-11 cursor-pointer items-center justify-center gap-1.5 rounded-xl bg-slate-100 px-3.5 py-2 text-[12.5px] font-extrabold text-canvas-ink transition-transform duration-150 ease-out hover:bg-slate-200 active:scale-[0.97] sm:min-h-0 ${disabled ? 'pointer-events-none opacity-50' : ''}`}>
      <input
        type="file"
        accept={accept}
        className="sr-only"
        disabled={disabled}
        onChange={(e) => {
          const f = e.target.files?.[0];
          e.target.value = '';
          if (f) onPick(f);
        }}
      />
      {label}
    </label>
  );
}
