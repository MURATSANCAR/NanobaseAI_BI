import type { ReactNode } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { btnGhost, btnPrimary } from '../../admin/ui';
import './plan.css';

/** Sayfa düzenleyicinin diyalogları (odak tuzağı, Esc ve dışarı tıklama base-ui'den). Açılış merkezden
 *  hafif büyüme + saydamlık (200 ms), kapanış daha kısa; azaltılmış harekette yalnız saydamlık. */

export function Modal({ open, onClose, title, description, children, dismissible = true }: {
  open: boolean; onClose: () => void; title: string; description?: ReactNode; children: ReactNode; dismissible?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => { if (!o && dismissible) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Backdrop className="pe-scrim" />
        <Dialog.Popup className="pe-dialog font-canvas text-canvas-ink">
          <Dialog.Title className="text-[17px] font-extrabold tracking-tight">{title}</Dialog.Title>
          {description && <Dialog.Description className="mt-1 text-[12.5px] leading-snug text-canvas-muted">{description}</Dialog.Description>}
          <div className="mt-3">{children}</div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function ConfirmDialog({ open, title, body, confirm, danger, onClose, onConfirm }: {
  open: boolean; title: string; body: ReactNode; confirm: string; danger?: boolean; onClose: () => void; onConfirm: () => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title={title} description={body}>
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
        <button type="button" className={danger ? `${btnPrimary} !bg-rose-600` : btnPrimary} onClick={onConfirm}>{confirm}</button>
      </div>
    </Modal>
  );
}
