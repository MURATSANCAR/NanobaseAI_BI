import type { ReactNode } from 'react';
import { Popover } from '@base-ui/react/popover';
import { CircleHelp, Inbox } from 'lucide-react';

/**
 * Terim açıklaması: bir göstergenin, kolon başlığının, durum rozetinin ya da iş teriminin yanında küçük «?».
 * Dokununca / tıklayınca sade dille ne anlama geldiğini söyleyen küçük bir kutu açılır; kutu düğmeden büyür.
 * `SqlInfo` («i») rakamın sorgusunu gösterir; `Explain` («?») kavramı anlatır — ikisi yan yana durabilir.
 *
 *   <Explain label="Stok günü">Bugünkü stok, son 90 günün satış hızıyla kaç gün yeter.</Explain>
 *   <Explain label="ROAS" title="Reklam getirisi">Harcanan her 1 ₺ reklamın getirdiği satış tutarı.</Explain>
 *
 * Yazım: tek ya da iki kısa cümle; «siz» dili; teknoloji/ürün adı yok; hesap kodda nasılsa öyle anlatılır.
 */
export function Explain({
  label,
  title,
  children,
  className = '',
}: {
  /** Açıklanan şeyin ekrandaki adı; ekran okuyucu için düğme adı olur. */
  label: string;
  /** Kutunun başlığı; verilmezse `label`. */
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Popover.Root>
      <Popover.Trigger
        className={`explain-trigger relative inline-flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full align-middle text-canvas-muted after:absolute after:-inset-2.5 after:content-[''] hover:bg-violet-50 hover:text-canvas-violet focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-400 data-[popup-open]:bg-violet-50 data-[popup-open]:text-canvas-violet ${className}`}
        aria-label={`${label}: ne anlama gelir?`}
        onClick={(e) => e.stopPropagation()}
      >
        <CircleHelp aria-hidden className="h-3.5 w-3.5" strokeWidth={2.3} />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="top" align="center" sideOffset={8} collisionPadding={12} className="z-[95]">
          <Popover.Popup className="explain-popup w-[min(300px,calc(100vw-24px))] rounded-2xl bg-white px-3.5 py-3 text-left text-canvas-ink shadow-[0_12px_40px_-8px_rgba(15,23,42,0.28),0_0_0_1px_rgba(15,23,42,0.06)] outline-none">
            <Popover.Title className="text-[12.5px] font-extrabold leading-snug">{title ?? label}</Popover.Title>
            <Popover.Description render={<div />} className="mt-1 text-[12.5px] font-medium normal-case leading-relaxed tracking-normal text-canvas-ink/85">
              {children}
            </Popover.Description>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

/** Etiket + «?» yan yana; kolon başlığı ve form etiketi için. */
export function ExplainLabel({ label, children, className = '' }: { label: string; children: ReactNode; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      <span>{label}</span>
      <Explain label={label}>{children}</Explain>
    </span>
  );
}

/**
 * Boş durum: «kayıt yok» yerine neden boş olduğunu ve ne yapılabileceğini söyler.
 *
 *   <EmptyHint title="Bu ay bitecek kitap yok" why="Stoktaki her kitap en az 60 gün yetiyor." />
 *   <EmptyHint title="Süzgece uyan kayıt yok" why="Arama ya da süzgeçleri gevşetin." action={<button …>Süzgeçleri temizle</button>} />
 */
export function EmptyHint({ title, why, action, icon }: { title: string; why?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-2xl border border-dashed border-slate-200 bg-white/50 px-4 py-7 text-center">
      <span aria-hidden className="mb-0.5 flex h-9 w-9 items-center justify-center rounded-full bg-slate-100 text-canvas-muted">
        {icon ?? <Inbox className="h-[18px] w-[18px]" />}
      </span>
      <p className="text-[13px] font-extrabold text-canvas-ink">{title}</p>
      {why && <p className="max-w-[46ch] text-[12.5px] leading-snug text-canvas-muted">{why}</p>}
      {action && <div className="mt-1.5">{action}</div>}
    </div>
  );
}

export default Explain;
