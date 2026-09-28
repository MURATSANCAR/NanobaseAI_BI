import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, btnGhost, btnPrimary, errText } from '../../admin/ui';
import { fmtDay } from '../hrApi';
import { Block, HrFrame } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { engApi } from './engApi';

/** M58 Anketlerim: açık anketlerim. «Cevapla» her seferinde yeni bir tek kullanımlık bağlantı üretir; cevap bu bağlantıyla,
 *  adınız olmadan kaydedilir. */
export default function MySurveys() {
  const nav = useNavigate();
  const q = useQuery({ queryKey: ['hr', 'eng', 'mine'], queryFn: engApi.mySurveys, enabled: ENGINE_ENABLED });
  const meta = useQuery({ queryKey: ['hr', 'eng', 'meta'], queryFn: engApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const link = useMutation({
    mutationFn: (sid: string) => engApi.link(sid),
    onSuccess: (r) => nav(`/ik/anket/${encodeURIComponent(r.token)}`),
    onError: (e) => toast.error(errText(e, 'Bağlantı alınamadı.')),
  });
  return (
    <HrFrame crumb="Anketlerim" title="Anketlerim" lead="Size açık çalışan anketleri. Cevaplarınız adınızla saklanmaz; katılıp katılmadığınız bilgisi de anket kapanınca silinir."
      aside={<div className="flex justify-start lg:justify-end"><Link to="/ik/oneriler" className={btnGhost}>Öneri ver</Link></div>}>
      {q.error && <Note tone="err">{errText(q.error, 'Anketler okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {q.data && !q.data.items.length && <Note tone="info">Şu an size açık anket yok.</Note>}
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {(q.data?.items ?? []).map((s) => (
          <li key={s.id} className="glass-panel flex flex-col gap-2 rounded-2xl p-4 shadow-glass-float">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="min-w-0 flex-1 break-words text-[15px] font-extrabold">{s.title}</span>
              {s.responded ? <Pill tone="ok">Cevapladınız</Pill> : <Pill tone="warn">{fmtDay(s.closesAt)} kapanır</Pill>}
            </div>
            <div className="flex items-center gap-1 text-[12px] text-canvas-muted">{s.kindLabel} · {s.questions} soru · yaklaşık iki dakika<SqlInfo k={q.data?.kaynaklar} alan="items[]" label="Soru sayısı" /></div>
            {!s.responded && (
              <button type="button" className={btnPrimary} disabled={link.isPending} onClick={() => link.mutate(s.id)}>Cevapla</button>
            )}
          </li>
        ))}
      </ul>
      {meta.data && (
        <Block title="Anonimlik nasıl sağlanıyor?">
          <p className="text-[12.5px] leading-relaxed">{meta.data.anonymity}</p>
        </Block>
      )}
    </HrFrame>
  );
}
