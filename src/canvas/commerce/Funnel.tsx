import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, errText, td, th } from '../admin/ui';
import { Pager, Panel } from '../editorial/kit';
import { commerceApi, fmtInt, fmtRatio, fmtTl } from './api';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

const DAYS = [7, 30, 90];

/** Ürün hunisi: sitede görüntülenme (gece farkı) ↔ geçerli site satışı; çok görüntülenip az satan kitaplar. */
export default function Funnel() {
  const [days, setDays] = useState(30);
  const [weak, setWeak] = useState(true);
  const [page, setPage] = useState(0);
  const q = useQuery({
    queryKey: ['commerce', 'funnel', days, weak, page],
    queryFn: () => commerceApi.funnel(days, page, weak),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Huni açılamadı.')}</Note>;
  const f = q.data;
  if (!f) return null;
  return (
    <Panel>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">{weak ? `Çok görüntülenip az satan (en az ${fmtInt(f.minViews)} görüntülenme)` : 'Bütün ürünler'}
          <SqlInfo k={f.kaynaklar} alan="weakCount" label="Ürün hunisi: az satan sayısı ve toplam" /></h2>
        <div className="flex flex-wrap gap-1.5">
          {DAYS.map((d) => (
            <button key={d} type="button" aria-pressed={days === d} onClick={() => { setDays(d); setPage(0); }}
              className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${days === d ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}>
              {d} gün
            </button>
          ))}
          <button type="button" aria-pressed={weak} onClick={() => { setWeak(!weak); setPage(0); }}
            className={`min-h-11 rounded-xl px-3 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${weak ? 'bg-canvas-violet text-white' : 'bg-slate-100 hover:bg-slate-200'}`}>
            Yalnız az satanlar ({fmtInt(f.weakCount)})
          </button>
        </div>
      </div>
      <p className="mt-1 text-[11.5px] text-canvas-muted">
        {f.not} Seçilen {f.days} günün {fmtInt(f.coveredDays)} gününde görüntülenme farkı var.
        <SqlInfo k={f.kaynaklar} alan="coveredDays" label="Kapsanan gün" className="ml-1" />
      </p>
      <div className="mt-2">
        <TableWrap>
          <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={f.kaynaklar} alan="items">Görüntülenme</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={f.kaynaklar} alan="items">Adet</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={f.kaynaklar} alan="items">Satış / görüntülenme</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={f.kaynaklar} alan="items">Tutar</InfoLabel></th></tr></thead>
          <tbody>
            {f.items.map((r) => (
              <tr key={r.barkod} className="border-t border-slate-100">
                <td className={td}><div className="font-bold">{r.ad ?? '—'}</div><div className="font-mono text-[11px] text-canvas-muted">{r.barkod}</div></td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.goruntulenme)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.adet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtRatio(r.oran, 2)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtTl(r.tutar)}</td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
        <Pager page={page} pageSize={f.pageSize} total={f.total} shown={f.items.length} loading={q.isLoading} fetching={q.isFetching} onPage={setPage} />
      </div>
    </Panel>
  );
}
