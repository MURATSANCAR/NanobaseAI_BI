import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Section, TableWrap, btnGhost, errText, td, th } from '../admin/ui';
import { fmtDay, fmtInt, readersApi } from './api';
import { ROOT } from './parts';
import { InfoLabel } from '../components/SqlInfo';

/** Dışa aktarım günlüğü: kim, ne zaman, hangi segment, hangi kanal, kaç kişi, amaç ve dışarıda kalanlar. */
export default function Exports() {
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['readers', 'exports', page], queryFn: () => readersApi.exports(page), enabled: ENGINE_ENABLED });
  const d = q.data;
  return (
    <Section
      title="Dışa aktarımlar"
      help="Her liste alımı burada. Liste portalda saklanmaz; hangi okurların listede olduğu okur numarasıyla tutulur (KVKK başvurusunda cevap için)."
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Günlük açılamadı.')}</Note>}
      {d && d.items.length === 0 && <Note tone="info">Henüz dışa aktarım yok.</Note>}
      {d && d.items.length > 0 && (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Zaman</th><th className={th}>Kişi</th><th className={th}>Segment</th><th className={th}>Kanal</th>
              <th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="items[]">Listede</InfoLabel></th><th className={th}><InfoLabel k={d?.kaynaklar} alan="items[]">Dışarıda</InfoLabel></th><th className={th}>Amaç</th>
            </tr>
          </thead>
          <tbody>
            {d.items.map((x) => (
              <tr key={x.id} className="border-t border-slate-100">
                <td className={`${td} whitespace-nowrap`}>{fmtDay(x.at)}</td>
                <td className={td}>{x.user}</td>
                <td className={td}><Link className="font-bold text-canvas-violet hover:underline" to={`${ROOT}/segmentler/${x.segmentId}`}>{x.segment}</Link> <span className="text-canvas-muted">v{x.version}</span></td>
                <td className={td}>{x.channelLabel}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.count)}</td>
                <td className={td}>
                  <span className="font-mono tabular-nums">{fmtInt(x.excludedTotal)}</span>
                  {x.excluded.length > 0 && <span className="block text-[11px] text-canvas-muted">{x.excluded.map((e) => `${e.label} ${fmtInt(e.count)}`).join(' · ')}</span>}
                </td>
                <td className={td}>{x.purpose}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      {d && d.total > d.pageSize && (
        <div className="flex justify-end gap-1">
          <button type="button" className={btnGhost} disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Önceki</button>
          <button type="button" className={btnGhost} disabled={(page + 1) * d.pageSize >= d.total} onClick={() => setPage((p) => p + 1)}>Sonraki</button>
        </div>
      )}
    </Section>
  );
}
