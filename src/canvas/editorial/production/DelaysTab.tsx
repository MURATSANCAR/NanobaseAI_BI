import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText, nf } from '../../admin/ui';
import { Panel } from '../kit';
import { productionApi, type ProdCard } from './api';
import { CardRow } from './CardsTab';

/** Gecikmeler: planı geçmiş, gerçekleşmemiş adımlar. Basamaklı bildirim: gecikme ayardaki günü aşınca yöneticiye çıkar. */
export default function DelaysTab({ onOpen }: { onOpen: (id: string) => void }) {
  const q = useQuery({ queryKey: ['production', 'delays'], queryFn: productionApi.delays, enabled: ENGINE_ENABLED });
  const err = errText(q.error, 'Gecikmeler okunamadı.');
  const items = q.data?.items ?? [];
  const up = items.filter((c) => c.delays.some((d) => d.level === 'yonetici'));
  const own = items.filter((c) => !c.delays.some((d) => d.level === 'yonetici'));
  const days = q.data?.escalateDays ?? 7;

  const group = (title: string, help: string, list: ProdCard[], tone: string) => (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="text-[13px] font-extrabold">
          <span aria-hidden className={`mr-1.5 inline-block h-2 w-2 rounded-full align-middle ${tone}`} />
          {title} <span className="font-mono tabular-nums text-canvas-muted">{nf.format(list.length)}</span>
        </h2>
        <p className="text-[11.5px] text-canvas-muted">{help}</p>
      </div>
      {list.length === 0 ? (
        <p className="px-1 py-3 text-[12px] text-canvas-muted">Kayıt yok.</p>
      ) : (
        <ul className="mt-2 space-y-1.5">
          {list.map((c) => (
            <CardRow key={c.id} c={c} onOpen={onOpen} />
          ))}
        </ul>
      )}
    </Panel>
  );

  return (
    <>
      {err && <Note tone="err">{err}</Note>}
      {q.isLoading && (
        <Panel>
          <Loading />
        </Panel>
      )}
      {q.data && (
        <>
          {group('Yöneticiye çıkan', `${days} günden uzun süren gecikme`, up, 'bg-rose-600')}
          {group('Sorumluda', `${days} güne kadar gecikme: kartın sorumlu editörü izler`, own, 'bg-rose-300')}
        </>
      )}
    </>
  );
}
