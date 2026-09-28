import type { ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ChevronLeft, PlugZap } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Note } from '../admin/ui';
import { PRIORITY_TONE, STATUS_TONE, lastRunText, probText, type Connection, type LastRun, type Message, type Priority, type Status } from './api';

const SECTIONS = [
  { to: '/kurumsal-eposta', label: 'Gelen kutusu', end: true },
  { to: '/kurumsal-eposta/rapor', label: 'Rapor', end: false },
  { to: '/kurumsal-eposta/kurallar', label: 'Kurallar', end: false },
  { to: '/kurumsal-eposta/etiketleme', label: 'Etiketleme', end: false },
];

/** Kurumsal e-posta ekranlarının kabuğu: başlık, bölüm bağlantıları, kutu bağlantısı satırı. */
export function MailFrame({
  title,
  lead,
  connection,
  lastRun,
  detail,
  back,
  aside,
  children,
}: {
  title: string;
  lead?: string;
  connection?: Connection;
  lastRun?: LastRun;
  detail?: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
  children: ReactNode;
}) {
  const source = connection?.connected ? `${connection.mailbox} · yalnız okuma` : 'Kutu bağlı değil';
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Kayıtlar', crumb: 'Kurumsal e-posta', source, presence: lastRunText(connection, lastRun ?? null), detail }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1500px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to={back.to} className="inline-flex min-h-8 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    {back.label}
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Kayıtlar · Kurumsal e-posta</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-auto">{aside}</div>}
            </header>
            {!back && (
              <nav aria-label="Kurumsal e-posta bölümleri" className="-mx-1 overflow-x-auto px-1">
                <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                  {SECTIONS.map((s) => (
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
            )}
            {connection && !connection.connected && <NotConnected connection={connection} />}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Kutu bağlı değilken: ne eksik ve kimin ne yapacağı. Sahte ileti gösterilmez. */
export function NotConnected({ connection }: { connection: Connection }) {
  return (
    <div className="flex gap-3 rounded-2xl border border-amber-200/70 bg-amber-50/80 px-4 py-3 text-amber-900">
      <PlugZap aria-hidden className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="min-w-0 text-[12.5px] leading-snug">
        <div className="font-extrabold">Kutu bağlı değil</div>
        <div>{connection.reason ?? 'Bağlantı ayarı eksik.'}</div>
        <div className="mt-1 text-amber-800/90">
          Bağlantı Yönetim → Portal ayarları → Kurumsal e-posta bölümünden girilir. Kutu yalnız okunur; portal ileti göndermez, kutudan silmez.
        </div>
      </div>
    </div>
  );
}

export function StatusPill({ status, label }: { status: Status; label: string }) {
  return <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${STATUS_TONE[status]}`}>{label}</span>;
}

export function PriorityPill({ priority, label }: { priority: Priority; label: string }) {
  return <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${PRIORITY_TONE[priority]}`}>{label}</span>;
}

/** Tür rozeti: kaynağı (Zeki AI olasılıkla / kural / insan) ile. Emin olunmayan tür kesikli çerçeveyle. */
export function CategoryPill({ m }: { m: Pick<Message, 'categoryLabel' | 'categoryProb' | 'categorySource' | 'unsure' | 'classified'> }) {
  if (!m.classified) return <span className="inline-flex items-center rounded-md bg-slate-50 px-1.5 py-0.5 text-[11px] font-bold text-canvas-muted">Sınıflanıyor</span>;
  if (!m.categoryLabel) return <span className="inline-flex items-center rounded-md border border-dashed border-amber-300 px-1.5 py-0.5 text-[11px] font-bold text-amber-800">Tür belirsiz</span>;
  const src = m.categorySource === 'insan' ? 'elle' : m.categorySource === 'kural' ? 'kural' : probText(m.categoryProb);
  return (
    <span
      className={`inline-flex max-w-full items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold ${
        m.unsure ? 'border border-dashed border-amber-300 text-amber-800' : 'bg-canvas-violet/10 text-canvas-violet'
      }`}
      title={m.unsure ? 'Zeki AI emin değil; türü kontrol edin' : undefined}
    >
      <span className="truncate">{m.categoryLabel}</span>
      <span className="shrink-0 font-semibold opacity-75">{src}</span>
    </span>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-8 text-center">
      <div className="text-[13px] font-extrabold">{title}</div>
      {children && <div className="mx-auto mt-1 max-w-[56ch] text-[12px] leading-snug text-canvas-muted">{children}</div>}
    </div>
  );
}

export function Warn({ children }: { children: ReactNode }) {
  return <Note tone="warn">{children}</Note>;
}
