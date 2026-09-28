import type { ReactNode } from 'react';
import Shell, { ZoomStage } from '../stitch/Shell';

/** Fiyatlama ekranının kabuğu: Finans alanında, üst şerit + başlık + kaydırılan gövde (Editoryal çerçevesinin eşi). */
export default function Frame({ title, lead, source, presence, children }: {
  title: string;
  lead: string;
  source: string;
  presence: string;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Finans', crumb: 'Fiyatlama ve maliyet', source, presence }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="px-1">
              <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Finans</div>
              <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
              <p className="mt-1 max-w-[80ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}
