import { Suspense, lazy, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CircleHelp } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { canOpenRoute, usePageAccess } from '../../useAdmin';
import { learningApi, recordVisit } from './learningApi';

// Pencere yalnız açılınca yüklenir: kabuğun ana parçası büyümesin.
const GuideSheet = lazy(() => import('./GuideSheet'));

/** Kabuk başlığındaki «Bu ekran nasıl kullanılır» bağlantısı (M57). Etkin menü öğesinin yayımlı rehberi yoksa hiçbir
 *  şey çizmez. Aynı bileşen ekran ziyaret sayacını da besler: menü öğesi değişince (gün × öğe başına bir kez) köprüye
 *  yalnız öğe kimliği gider; hesap köprüde oturumdan okunur. */
export default function GuideLink({ item }: { item?: { id: string; to: string } }) {
  const [open, setOpen] = useState(false);
  const pages = usePageAccess();
  const itemId = item?.id;
  // Yalnız açılabilen ekran sayılır («yetkiniz yok» kartı ziyaret değildir); yetki bilinmiyorken beklenir.
  const counted = !!item && item.id !== 'kampus' && pages !== null && canOpenRoute(pages, item.to);
  useEffect(() => {
    if (counted && itemId) recordVisit(itemId);
  }, [counted, itemId]);
  const index = useQuery({
    queryKey: ['hr', 'learning', 'guide-index'],
    queryFn: learningApi.guideIndex,
    enabled: ENGINE_ENABLED && !!itemId,
    staleTime: 10 * 60_000,
    retry: false,
  });
  const guide = itemId ? index.data?.items.find((g) => g.moduleRoute === itemId) : undefined;
  if (!guide) return null;
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Bu ekran nasıl kullanılır"
        title="Bu ekran nasıl kullanılır"
        className="glass-panel flex min-h-10 min-w-10 items-center justify-center gap-1.5 rounded-full px-2.5 py-1.5 text-[11px] font-bold text-ink shadow-glass-float transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-0 sm:min-w-0 sm:px-3.5 sm:py-2 sm:text-xs"
      >
        <CircleHelp aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted" />
        <span className="hidden sm:inline">Nasıl kullanılır</span>
      </button>
      {open && (
        <Suspense fallback={null}>
          <GuideSheet id={guide.id} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </>
  );
}
