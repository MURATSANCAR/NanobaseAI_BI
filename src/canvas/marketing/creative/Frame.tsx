import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../../stitch/Shell';

/** Pazarlama › Üretim ekranlarının kabuğu: üst şerit, başlık, sağda eylemler, kaydırılan gövde. Yeni hareket yok
 *  (sık açılan iş ekranı); basış geri bildirimi düğmelerin kendi `active:scale` sınıfındadır. */
export default function Frame({ crumb, title, lead, back, source, detail, aside, children }: {
  crumb: string;
  /** Menüde olmayan detay sayfasının adı (kırıntı ve «Son açılanlar»). */
  detail?: string;
  title: string;
  lead?: ReactNode;
  back?: { to: string; label: string };
  source: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb, source, presence: 'Görsel ve metin', detail }}>
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · Üretim</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <div className="mt-1 max-w-[80ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</div>}
              </div>
              {aside && <div className="w-full min-w-0 shrink-0 lg:w-auto lg:max-w-[560px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}
