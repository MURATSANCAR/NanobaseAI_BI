import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Note, btnGhost, errText } from '../../admin/ui';
import Sheet from '../../editorial/studio/reader/Sheet';
import { learningApi } from './learningApi';
import { GuideText, fmtDay } from './guideText';

/** Yayımlı rehberi okuma penceresi ve «yaradı / yaramadı» oyu (oy yalnız o sürüme sayılır). */
export default function GuideSheet({ id, onClose }: { id: string | null; onClose: () => void }) {
  const qc = useQueryClient();
  const g = useQuery({ queryKey: ['hr', 'learning', 'guide', id], queryFn: () => learningApi.readGuide(id as string), enabled: ENGINE_ENABLED && !!id });
  const vote = useMutation({
    mutationFn: (useful: boolean) => learningApi.voteGuide(id as string, useful),
    onSuccess: () => {
      toast.success('Teşekkürler, görüşünüz kaydedildi.');
      void qc.invalidateQueries({ queryKey: ['hr', 'learning', 'guide', id] });
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.')),
  });
  const d = g.data;
  return (
    <Sheet open={!!id} onClose={onClose} title={d?.title ?? 'Rehber'} subtitle={d ? `Sürüm ${d.version} · ${fmtDay(d.approvedAt)}` : undefined}>
      <div className="flex flex-col gap-4 p-4">
        {g.isLoading && <p className="text-[12px] text-canvas-muted">Yükleniyor…</p>}
        {g.error && <Note tone="err">{errText(g.error, 'Rehber okunamadı.')}</Note>}
        {d && <GuideText body={d.body} />}
        {d && (
          <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
            <span className="text-[12px] font-bold">Bu rehber işinize yaradı mı?</span>
            <button type="button" aria-pressed={d.myVote === true} className={`${btnGhost} ${d.myVote === true ? 'ring-2 ring-canvas-violet' : ''}`} disabled={vote.isPending} onClick={() => vote.mutate(true)}>
              Yaradı
            </button>
            <button type="button" aria-pressed={d.myVote === false} className={`${btnGhost} ${d.myVote === false ? 'ring-2 ring-canvas-violet' : ''}`} disabled={vote.isPending} onClick={() => vote.mutate(false)}>
              Yaramadı
            </button>
          </div>
        )}
      </div>
    </Sheet>
  );
}
