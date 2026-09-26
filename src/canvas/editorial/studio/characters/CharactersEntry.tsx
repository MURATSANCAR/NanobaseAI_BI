import { useState } from 'react';
import { Drawer } from '@base-ui/react/drawer';
import { Users, X } from 'lucide-react';
import { ghostBtn, press } from '../shared';
import CharactersPanel from './CharactersPanel';
import { useCardsView } from './api';
import './characters.css';

/** Stüdyodan «Karakterler» paneline giriş: düğme + yan panel (telefonda alttan açılan, aşağı kaydırınca kapanan
 *  sayfa; masaüstünde sağda yüzen panel). Düğmedeki sayı bu kitapta karta uymayan resim sayısıdır. */
export default function CharactersEntry({ jobId }: { jobId: string }) {
  const [open, setOpen] = useState(false);
  const q = useCardsView(jobId);
  const bad = q.data?.check.items.filter((i) => i.status === 'mismatch').length ?? 0;
  return (
    <Drawer.Root open={open} onOpenChange={setOpen} swipeDirection="down">
      <Drawer.Trigger className={ghostBtn} title="Dizinin karakter kartları: görünüş ve renkler her resimde aynı">
        <Users className="h-4 w-4" aria-hidden />Karakterler
        {bad > 0 && (
          <span className="rounded-full bg-rose-600 px-1.5 font-mono text-[10.5px] font-bold text-white" aria-label={`${bad} resim karta uymuyor`}>{bad}</span>
        )}
      </Drawer.Trigger>
      <Drawer.Portal>
        <Drawer.Backdrop className="cc-scrim" />
        <Drawer.Viewport className="cc-viewport">
          <Drawer.Popup className="cc-sheet glass-panel font-canvas text-canvas-ink">
            <div className="shrink-0 touch-none select-none px-4 pb-1 pt-2.5">
              <div className="mx-auto h-1 w-10 rounded-full bg-slate-300 sm:hidden" aria-hidden />
              <div className="mt-1.5 flex items-center justify-between gap-2">
                <Drawer.Title className="text-[17px] font-extrabold tracking-tight">Karakterler</Drawer.Title>
                <Drawer.Close className={`flex h-10 w-10 items-center justify-center rounded-full bg-white/80 ${press}`} aria-label="Kapat">
                  <X className="h-4 w-4" aria-hidden />
                </Drawer.Close>
              </div>
              <Drawer.Description className="text-[12px] leading-snug text-canvas-muted">
                Karakterin görünüşü ve renkleri bir kez kaydedilir; dizinin her kitabında, her resimde aynı kullanılır.
              </Drawer.Description>
            </div>
            <Drawer.Content className="min-h-0 flex-1 touch-auto overflow-y-auto overscroll-contain px-4 pb-[max(16px,env(safe-area-inset-bottom))] pt-3">
              {open && <CharactersPanel jobId={jobId} />}
            </Drawer.Content>
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
