import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText } from '../admin/ui';
import { schoolsApi } from './api';
import { LinkRow } from './DealerPanel';
import { invalidateSchools, useSchoolsMeta } from './parts';
import SqlInfo from '../components/SqlInfo';

/** Onay kuyruğu (saha yöneticisi): Zeki AI'ın plandaki okullara önerdiği ve temsilcilerin ziyaret raporunda yönlendirdiği
 *  bayi eşleşmeleri. Onay açıkça verilen `okul.bayi-onay` yetkisiyle; herkes kuyruğu görür, karar veremez. */

export default function DealerQueue() {
  const qc = useQueryClient();
  const meta = useSchoolsMeta();
  const canDealer = !!meta.data?.me.canDealer;
  const q = useQuery({ queryKey: ['schools', 'queue'], queryFn: schoolsApi.queue, enabled: ENGINE_ENABLED });
  const decide = useMutation({
    mutationFn: (a: { school: string; link: string; approve: boolean }) => schoolsApi.decideDealer(a.school, a.link, a.approve),
    onSuccess: (_r, a) => {
      toast.success(a.approve ? 'Eşleşme onaylandı.' : 'Eşleşme reddedildi.');
      invalidateSchools(qc);
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.'),
  });
  return (
    <div className="flex flex-col gap-3">
      {!canDealer && <Note tone="info">Eşleşmeleri görebilirsiniz; onay ya da ret yetkisi rolünüzde yok.</Note>}
      {q.error && <Note tone="err">{errText(q.error, 'Kuyruk okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && q.data.items.length === 0 && <Note tone="ok">Onay bekleyen bayi eşleşmesi yok.</Note>}
      {q.data && q.data.items.length > 0 && (
        <p className="flex items-center gap-1 px-1 text-[12px] font-semibold text-canvas-muted">
          Onay bekleyen {q.data.total.toLocaleString('tr-TR')} eşleşme
          <SqlInfo k={q.data.kaynaklar} alan="total" label="Onay bekleyen eşleşme" />
        </p>
      )}
      <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {q.data?.items.map((l) => (
          <LinkRow
            key={l.id}
            l={l}
            canDealer={canDealer}
            busy={decide.isPending}
            schoolLine={[l.schoolName, l.schoolIlce ? `${l.schoolIlce}, ${l.schoolIl ?? ''}` : l.schoolIl, l.kademe].filter(Boolean).join(' · ')}
            onDecide={(approve) => decide.mutate({ school: l.school, link: l.id, approve })}
            footer={
              <Link to={`/okul-tanitim/${l.school}`} className="mt-1.5 inline-flex min-h-11 items-center text-[11.5px] font-bold text-canvas-violet hover:underline sm:min-h-0">
                Okul kartı ve diğer adaylar
              </Link>
            }
          />
        ))}
      </ul>
    </div>
  );
}
