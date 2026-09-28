import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ChevronLeft, Info } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Note } from '../admin/ui';
import { fmtDay, fmtStamp, type Alert, type PoolStatus } from './api';

/** Katalog ve bülten ekranlarının kabuğu (Pazarlama › Kampanya). Düzen pazarlama planı ekranıyla aynı. */
export function CnFrame({ crumb, title, lead, source, presence, back, aside, children }: {
  crumb: string;
  title: string;
  lead?: string;
  source: string;
  presence: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb, source, presence }}>
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Kampanya</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[80ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
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

/** Bölüm: başlık, kısa açıklama, sağda işlem. */
export function Block({ title, help, action, children }: { title: string; help?: ReactNode; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold tracking-tight">{title}</h2>
          {help && <p className="mt-0.5 max-w-[80ch] text-[11.5px] leading-snug text-canvas-muted">{help}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Stok ve fiyat verisinin tarihi: donmuş Logo kopyası güncel gibi gösterilmez. */
export function DataAge({ pool }: { pool: Pick<PoolStatus, 'okuma' | 'logoSon'> & { notlar?: string[] } | null | undefined }) {
  if (!pool) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <Note tone="info">
        Stok ve satış verisi <b>{fmtDay(pool.logoSon)}</b> tarihine kadardır (Logo'daki son faturalı satış günü). Kitap havuzu {fmtStamp(pool.okuma)} tarihinde okundu.
      </Note>
      {(pool.notlar ?? []).map((n) => (
        <Note key={n} tone="warn">{n}</Note>
      ))}
    </div>
  );
}

/** Kitabın uyarıları: kritik kırmızı, bilgi gri; «Kabul et» yalnız düzenleme yetkisi varken. */
export function AlertList({ alerts, onAccept, busy }: { alerts: Alert[]; onAccept?: (tur: string) => void; busy?: boolean }) {
  if (!alerts.length) return null;
  return (
    <ul className="mt-1 flex flex-col gap-1">
      {alerts.map((a) => (
        <li key={a.tur} className={`flex flex-wrap items-start gap-1.5 rounded-lg px-2 py-1 text-[11.5px] leading-snug ${a.seviye === 'kritik' ? 'bg-red-50 text-red-800' : 'bg-slate-50 text-canvas-muted'}`}>
          {a.seviye === 'kritik' ? <AlertTriangle aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <Info aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span className="min-w-0 flex-1"><b>{a.baslik}:</b> {a.metin}</span>
          {onAccept && (
            <button type="button" disabled={busy} onClick={() => onAccept(a.tur)}
              className="min-h-8 shrink-0 rounded-md bg-white/80 px-2 text-[11px] font-bold text-canvas-ink transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-50">
              {a.tur === 'fiyat' ? 'Yeni fiyatı kabul et' : 'Gördüm'}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Kritik uyarı rozeti (liste satırları). */
export function AlertBadge({ n }: { n: number }) {
  if (!n) return <span className="text-[11px] font-semibold text-emerald-700">Uyarı yok</span>;
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-red-50 px-1.5 py-0.5 text-[11px] font-bold text-red-700">
      <AlertTriangle aria-hidden className="h-3 w-3" />
      {n} kritik
    </span>
  );
}
