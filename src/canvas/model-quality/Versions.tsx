import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { InfoLabel } from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { Note, Pill, TableWrap, errText, td, th } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { fmtAt, mqApi, shortSha } from './api';
import { Empty } from './parts';

/** Sürümler: kod, katalog, bilgi paketi/kural, gündelik terim havuzu ve model tek satırda. Satır, bir parça değişince
 *  (koşu anında) ya da her kurulumda yazılır; «değişen» sütunu hangi parçanın değiştiğini söyler. */
export default function Versions() {
  const [page, setPage] = useState(0);
  const q = useQuery({ queryKey: ['mq', 'versions', page], queryFn: () => mqApi.versions(page), enabled: ENGINE_ENABLED });
  return (
    <>
      <Panel>
        {q.isLoading && <Empty>Yükleniyor…</Empty>}
        {q.error && <Note tone="err">{errText(q.error, 'Sürümler okunamadı.')}</Note>}
        {q.data && !q.data.items.length && <Empty>Henüz sürüm kaydı yok. İlk kurulumda ya da ilk kalite koşusunda yazılır.</Empty>}
        {q.data && q.data.items.length > 0 && (
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Zaman</th>
                <th className={th}>Kaynak</th>
                <th className={th}>Değişen</th>
                <th className={th}>Kod</th>
                <th className={th}><InfoLabel k={kaynakOf(q.data)} alan="items">Katalog</InfoLabel></th>
                <th className={th}>Bilgi paketi</th>
                <th className={th}>Kural</th>
                <th className={th}>Model</th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((v) => (
                <tr key={v.id} className="border-b border-slate-50 last:border-0">
                  <td className={`${td} whitespace-nowrap font-mono tabular-nums`}>{fmtAt(v.at)}</td>
                  <td className={td}>
                    {v.sourceLabel}
                    {v.env && <span className="text-canvas-muted"> · {v.env === 'vm' ? 'müşteri' : 'test'}</span>}
                    {v.by && <div className="text-[11px] text-canvas-muted">{v.by}</div>}
                  </td>
                  <td className={td}>
                    <span className="flex flex-wrap gap-1">{v.kindLabels.length ? v.kindLabels.map((k) => <Pill key={k} tone="violet">{k}</Pill>) : <span className="text-canvas-muted">—</span>}</span>
                  </td>
                  <td className={`${td} font-mono`}>{shortSha(v.codeSha)}</td>
                  <td className={`${td} whitespace-nowrap`}>v{v.catalogVersion ?? '—'}<span className="text-canvas-muted"> · {v.catalogCertified ?? '—'} onaylı</span></td>
                  <td className={`${td} font-mono`}>{v.knowledgeDigest ?? '—'}</td>
                  <td className={`${td} font-mono`}>{v.rulesDigest ?? '—'}</td>
                  <td className={td}>{v.model}<div className="font-mono text-[11px] text-canvas-muted">ayar {v.modelDigest ?? '—'}</div></td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        )}
        {q.data && q.data.total > q.data.size && (
          <Pager page={page} pageSize={q.data.size} total={q.data.total} shown={q.data.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
        )}
      </Panel>
      {q.data && q.data.installs.length > 0 && (
        <Panel>
          <h2 className="text-[15px] font-extrabold tracking-tight">Sistem durumunun kurulum kaydı</h2>
          <ul className="mt-2 flex flex-col gap-1 text-[12px]">
            {q.data.installs.map((i, k) => (
              <li key={k} className="font-mono tabular-nums">
                {fmtAt(i.at)} · {i.env ?? '—'} · {shortSha(i.codeSha)}{i.note ? ` · ${i.note}` : ''}
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </>
  );
}
