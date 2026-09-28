import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Panel, useDebounced } from '../editorial/kit';
import { ACTION_TEXT, categoriesApi, fmtDay, fmtInt } from './api';
import { ROOT, useMeta } from './parts';

/** CRM'e işlenecek fark: onaylı profil ile CRM'in bugünkü değeri. Portal CRM'e yazmaz; liste CRM'de elle işlenir,
 *  bir sonraki okumada CRM aynı değeri gösterince satır kendiliğinden düşer. */
export default function CrmDiff() {
  const meta = useMeta();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 300);
  const owner = params.get('sahip') === 'ben' ? 'me' : '';
  const diff = useQuery({ queryKey: ['categories', 'crm-diff', owner, dq], queryFn: () => categoriesApi.crmDiff({ owner, q: dq }), enabled: ENGINE_ENABLED });
  const d = diff.data;
  return (
    <Panel>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="grid flex-1 gap-2 sm:grid-cols-2 lg:max-w-[640px]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Ara</span>
            <input className={field} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Kitap adı ya da stok kodu" />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kimin</span>
            <select className={field} value={params.get('sahip') ?? ''} onChange={(e) => { const p = new URLSearchParams(params); if (e.target.value) p.set('sahip', e.target.value); else p.delete('sahip'); setParams(p, { replace: true }); }}>
              <option value="">Bütün katalog</option>
              <option value="ben">Benim kitaplarım</option>
            </select>
          </label>
        </div>
        {meta.data?.me.canExport && (
          <a className={btnGhost} href={categoriesApi.crmDiffUrl(owner || undefined)} download>
            <Download aria-hidden className="h-4 w-4" /> Excel olarak indir
          </a>
        )}
      </div>
      {d && (
        <p className="mt-2 text-[12px] font-semibold text-canvas-muted">
          {fmtInt(d.books)} kitapta {fmtInt(d.total)} satır{d.stale ? <>; <span className="text-red-700">{fmtInt(d.stale)} satır {d.staleDays} günden uzun süredir bekliyor</span></> : ''}.
          Portal CRM'e yazmaz; bu değerler CRM'de elle işlenir.
        </p>
      )}
      {diff.isLoading && <Loading />}
      {diff.error && <div className="mt-3"><Note tone="err">{errText(diff.error, 'Liste açılamadı.')}</Note></div>}
      {d && d.total === 0 && <p className="mt-3 text-[12.5px] text-canvas-muted">CRM'e işlenecek fark yok.</p>}
      {d && d.total > 0 && (
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>Kitap</th>
                <th className={th}>CRM alanı</th>
                <th className={th}>İşlem</th>
                <th className={th}>CRM'de</th>
                <th className={th}>Onaylı</th>
                <th className={th}>Onaylayan</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((x, i) => (
                <tr key={`${x.bookId}-${x.field}-${x.crmField}-${i}`} className="border-b border-slate-50">
                  <td className={td}>
                    <Link to={`${ROOT}/kitap/${x.bookId}`} className="font-bold hover:text-canvas-violet">{x.name}</Link>
                    <div className="text-[11px] text-canvas-muted">{x.stockCode}</div>
                  </td>
                  <td className={td}>{x.crmField}</td>
                  <td className={td}><Pill tone={x.action === 'bilgi' ? 'muted' : x.action === 'cikar' ? 'err' : 'violet'}>{ACTION_TEXT[x.action]}</Pill></td>
                  <td className={`${td} text-canvas-muted`}>{x.crmValue ?? '—'}</td>
                  <td className={`${td} font-semibold`}>{x.portalValue ?? '—'}{x.note && x.note !== x.portalValue && <div className="text-[11px] font-normal text-canvas-muted">{x.note}</div>}</td>
                  <td className={td}>
                    {x.approvedBy} · {fmtDay(x.approvedAt)}
                    {x.stale && <div className="text-[11px] font-bold text-red-700">{x.ageDays} gündür bekliyor</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
    </Panel>
  );
}
