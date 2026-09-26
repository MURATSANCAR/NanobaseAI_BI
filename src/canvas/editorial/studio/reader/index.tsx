import { useState } from 'react';
import { BookOpenText, GitCompareArrows } from 'lucide-react';
import type { EditorCtx } from '../InspectorPanel';
import { ghostBtn } from '../shared';
import Sheet from './Sheet';
import ReaderPanel from './ReaderPanel';
import ComparePanel from '../diff/ComparePanel';

/** Sayfa düzenleyicinin başlığındaki iki giriş: «Okur» (çocuk gözüyle okuma, sayfa çevirme merakı) ve
 *  «Karşılaştır» (sürüm farkı). PlanEditor'a tek satırla takılır: `<StudioReaderEntry ctx={ctx} goTo={setPageId} />`. */
export default function StudioReaderEntry({ ctx, goTo }: { ctx: EditorCtx; goTo: (pid: string) => void }) {
  const [open, setOpen] = useState<'reader' | 'compare' | null>(null);
  return (
    <>
      <button type="button" className={ghostBtn} aria-haspopup="dialog" aria-expanded={open === 'reader'} onClick={() => setOpen('reader')}>
        <BookOpenText className="h-4 w-4" aria-hidden />Okur
      </button>
      <button type="button" className={ghostBtn} aria-haspopup="dialog" aria-expanded={open === 'compare'} onClick={() => setOpen('compare')}>
        <GitCompareArrows className="h-4 w-4" aria-hidden />Karşılaştır
      </button>
      <Sheet open={open === 'reader'} onClose={() => setOpen(null)} title="Okur"
        subtitle={ctx.page ? `Sayfa ${ctx.pageNo} açık · işaretler bu sayfanın metninde` : undefined}>
        <ReaderPanel ctx={ctx} goTo={goTo} />
      </Sheet>
      <Sheet open={open === 'compare'} onClose={() => setOpen(null)} title="Sürümleri karşılaştır" modal wide
        subtitle="İki sürüm sayfa sayfa: eklenen/silinen kelimeler, taşınan kutular, görselde değişen bölgeler.">
        <ComparePanel job={ctx.job} goTo={(pid) => { goTo(pid); setOpen(null); }} />
      </Sheet>
    </>
  );
}
