import { useQuery } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { Note, errText } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { ReasonBody } from './ReasonPanel';
import type { Reason } from './api';

/** Bütçe sapma satırının nedeni (M46 İzleme, M45 Bütçe–gerçekleşme): satışta kitap (hedefe göre) ve kanal/cari (geçen
 *  yılın aynı aylarına göre), giderde ay ay aşım. Rakamlar tablolardan; Zeki AI yalnız anlatır. */
export default function ReasonSheet({ target, load, onClose }: {
  target: { id: string; title: string } | null;
  load: (id: string) => Promise<Reason>;
  onClose: () => void;
}) {
  const q = useQuery({ queryKey: ['fark', 'sapma', target?.id], queryFn: () => load(target!.id), enabled: !!target,
    staleTime: 10 * 60_000, retry: false });
  const r = q.data;
  return (
    <Sheet open={!!target} modal wide onClose={onClose} title="Sapmanın nedeni" subtitle={target?.title}>
      {q.isLoading && (
        <p className="flex items-center gap-2 text-[12.5px] text-canvas-muted">
          <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> Kırılımlar hesaplanıyor…
        </p>
      )}
      {q.error && <Note tone="err">{errText(q.error, 'Ayrıştırma yapılamadı.')}</Note>}
      {r && !r.ok && <Note tone="info">{r.neden}</Note>}
      {r && r.ok && <ReasonBody r={r} />}
    </Sheet>
  );
}
