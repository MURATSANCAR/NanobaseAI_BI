import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Note } from '../admin/ui';
import { canSeePage, usePageAccess } from '../useAdmin';

/** M37 Okur topluluğu ekranlarının ortak kabuğu: başlık, dört bölüm arası bağlantı (yalnız rolde olanlar), küçük parçalar. */
export { Tabs, AskSheet } from '../budget/parts';

const SECTIONS = [
  { id: 'okur-toplulugu', to: '/okur-toplulugu', label: 'Okur kitlesi' },
  { id: 'okur-segmentler', to: '/okur-toplulugu/segmentler', label: 'Segmentler' },
  { id: 'okur-programlar', to: '/okur-toplulugu/programlar', label: 'Programlar' },
  { id: 'okur-yorumlar', to: '/okur-toplulugu/yorumlar', label: 'Yorumlar' },
] as const;

export function OkurFrame({ crumb, title, lead, source, aside, children }: {
  crumb: string;
  title: string;
  lead: string;
  source: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const access = usePageAccess();
  const links = SECTIONS.filter((s) => canSeePage(access, s.id));
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb, source, presence: 'Okur ve müşteri' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Okur ve müşteri</div>
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[420px]">{aside}</div>}
            </header>
            {links.length > 1 && (
              <nav aria-label="Okur topluluğu bölümleri" className="-mx-1 overflow-x-auto px-1">
                <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                  {links.map((s) => (
                    <NavLink
                      key={s.id}
                      to={s.to}
                      end
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
            )}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Okur çekirdeği (okur veri tabanı modülü) bağlı değilken sayı yerine gösterilen not. */
export function CoreMissing({ message }: { message?: string | null }) {
  return (
    <Note tone="warn">
      {message || 'Okur çekirdeği bağlı değil'}. Okur sayıları, izin sağlığı ve segment büyüklüğü okur veri tabanı modülünden gelir;
      o modül kurulunca burada görünür. Program takvimi, geçmiş etkinlikler ve yorum cevapları şimdiden çalışır.
    </Note>
  );
}

/** Kısa etiketli değer (özet kutuları). */
export function Fact({ label, value, help }: { label: string; value: ReactNode; help?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-0.5 break-words font-mono text-[14px] font-bold tabular-nums">{value}</div>
      {help && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}

/** Pay çubuğu: izinli / toplam gibi oranlar. Değer bilinmiyorsa çubuk boş, metin tire. */
export function ShareBar({ part, total }: { part: number | null | undefined; total: number | null | undefined }) {
  const ok = part !== null && part !== undefined && !!total;
  const w = ok ? Math.max(0, Math.min(1, (part as number) / (total as number))) : 0;
  return (
    <span className="inline-flex min-w-[96px] items-center gap-2">
      <span className="relative h-1.5 w-14 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <span className="absolute inset-y-0 left-0 rounded-full bg-canvas-violet" style={{ width: `${w * 100}%` }} />
      </span>
      <span className="font-mono text-[11.5px] font-bold tabular-nums">{ok ? `%${Math.round(w * 100)}` : '—'}</span>
    </span>
  );
}
