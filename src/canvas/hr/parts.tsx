import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';

/** İnsan Kaynakları ekranlarının ortak kabuğu. Sekme çubuğu ve onay penceresi bütçe ekranınınkiyle aynıdır. */
export { Tabs, AskSheet } from '../budget/parts';

export function HrFrame({ crumb, title, lead, detail, back, aside, children }: {
  crumb: string;
  title: string;
  lead: string;
  /** Detay sayfasında kırıntının son halkası. */
  detail?: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'İnsan Kaynakları', crumb, source: 'Kaynak: portal kaydı · CRM · Active Directory', presence: crumb, detail }}>
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">İnsan Kaynakları</div>
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

/** Başlıklı bölüm (kart içinde). */
export function Block({ title, help, action, children }: { title: string; help?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[14.5px] font-extrabold tracking-tight">{title}</h2>
          {help && <p className="mt-0.5 max-w-[80ch] text-[11.5px] leading-snug text-canvas-muted">{help}</p>}
        </div>
        {action && <div className="flex flex-wrap gap-2">{action}</div>}
      </div>
      {children}
    </section>
  );
}

/** Kullanıcı adı listesi alanı: virgülle ayrılmış hesap adları. */
export const splitUsers = (s: string) =>
  s
    .split(/[,;\s]+/)
    .map((x) => x.trim().toLowerCase())
    .filter(Boolean);
