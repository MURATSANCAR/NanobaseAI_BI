import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Pill } from '../../admin/ui';
import { Panel } from '../kit';
import { money } from '../contracts/ui';
import { lineTone, royaltyApi } from './api';
import SqlInfo from '../../components/SqlInfo';
import { Explain } from '../../components/Explain';

/** M6 sözleşme sayfasında «Bu sözleşmenin dönem koşuları». Telif dönemi sayfasına yetkisi olmayan kişide hiç görünmez. */
export default function ContractRuns({ contractKey }: { contractKey: string }) {
  const q = useQuery({ queryKey: ['royalty', 'contract-lines', contractKey], queryFn: () => royaltyApi.contractLines(contractKey), retry: false });
  const items = q.data?.items ?? [];
  if (!items.length) return null;
  return (
    <Panel>
      <h3 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">
        Bu sözleşmenin dönem koşuları <SqlInfo k={q.data?.kaynaklar} alan="items[]" label="Dönem koşularındaki satırlar (net)" />
        <Explain label="Dönem koşuları">«Telif dönemi» ekranında bütün sözleşmeler için toplu yapılan hesaplarda bu sözleşmenin durumu ve net tutarı. Koşu adına dokununca o koşu açılır.</Explain>
      </h3>
      <ul className="space-y-1.5">
        {items.map((x) => (
          <li key={x.lineId} className="flex flex-wrap items-center gap-2 text-[12.5px]">
            <Link to={`/telif-donem?kosu=${x.runId}&sekme=${x.status === 'istisna' ? 'istisna' : 'kosu'}`} className="font-bold text-canvas-violet hover:underline">
              {x.runNo} · {x.label}
            </Link>
            <span className="text-canvas-muted">{x.runStatusLabel}</span>
            <Pill tone={lineTone(x.status)}>{x.statusLabel}</Pill>
            {x.exception && <span className="text-[11.5px] text-canvas-muted">{x.exception}</span>}
            <span className="ml-auto font-mono tabular-nums">{x.net != null ? money(x.net, x.currency) : '—'}</span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
