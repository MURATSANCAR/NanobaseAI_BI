import type { ReactNode } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { X } from 'lucide-react';
import './reader.css';

/** Yan panel (masaüstünde sağda, telefonda alttan). `modal=false`: sayfa tuvali görünür ve kullanılır kalır (Okur);
 *  `modal`: arka plan kararır, odak panelde (Karşılaştır). Esc ve kapat düğmesi kapatır. */
export default function Sheet({ open, onClose, title, subtitle, wide, modal, children }: {
  open: boolean; onClose: () => void; title: string; subtitle?: ReactNode; wide?: boolean; modal?: boolean; children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} modal={modal ? true : false} disablePointerDismissal={!modal}
      onOpenChange={(o) => { if (!o) onClose(); }}>
      <Dialog.Portal>
        {modal && <Dialog.Backdrop className="rd-scrim" />}
        <Dialog.Popup className={`rd-sheet font-canvas text-canvas-ink ${wide ? 'rd-wide' : ''}`}>
          <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-4 pb-3 pt-4">
            <div className="min-w-0">
              <Dialog.Title className="text-[17px] font-extrabold tracking-tight">{title}</Dialog.Title>
              {subtitle && <Dialog.Description className="mt-0.5 text-[12px] leading-snug text-canvas-muted">{subtitle}</Dialog.Description>}
            </div>
            <Dialog.Close aria-label="Kapat"
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-slate-100 text-canvas-ink transition-transform duration-150 ease-out hover:bg-slate-200 active:scale-[0.97]">
              <X className="h-4 w-4" aria-hidden />
            </Dialog.Close>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-6 pt-3">{children}</div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
