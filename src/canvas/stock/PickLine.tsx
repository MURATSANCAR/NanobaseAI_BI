import { useSearchParams } from 'react-router-dom';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, TableWrap, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Pager, Panel } from '../editorial/kit';
import { n0, n1, stockApi } from './api';
import { Empty, Loading, SourcesButton, StockFrame, num } from './parts';
import { EmptyHint } from '../components/Explain';
import { RULES } from './rules';

/** Sipariş hazırlık hattı (/stok/depo-hatti): CRM sipariş aşamaları (depoda bekliyor → toplanıyor → kutulanıyor →
 *  kutulandı), aşamadaki bekleme ve penceredeki aşama süreleri. Kişi bazlı toplama süresi yalnız açıkça verilen yetkiyle.
 *  M44 lojistik bu ekranın verisini (`/api/v1/stock/pick-line`) okur. */

const hours = (h: number | null) => (h === null ? '—' : h >= 48 ? `${n1(h / 24)} gün` : `${n1(h)} sa`);

export default function PickLine() {
  const [params, setParams] = useSearchParams();
  const sayfa = Number(params.get('sayfa') ?? 0) || 0;
  const q = useQuery({ queryKey: ['stock', 'pick-line', sayfa], queryFn: () => stockApi.pickLine(sayfa), enabled: ENGINE_ENABLED, placeholderData: (p) => p });
  const d = q.data;

  return (
    <StockFrame
      crumb="Depo hattı"
      title="Sipariş hazırlık hattı"
      lead="Depodaki siparişler hangi aşamada ve ne kadar bekliyor; son günlerde sevk edilen siparişlerde aşama süreleri. Darboğaz en uzun bekleyen aşamadır."
      source="CRM canlı"
      aside={<SourcesButton rules={RULES} />}
    >
      {q.error && <Note tone="err">{errText(q.error, 'Depo hattı okunamadı.')}</Note>}
      {q.isLoading && <Loading what="Depo hattı" />}
      {d && (
        <>
          <KpiRow>
            {d.asamalar.map((a) => (
              <Kpi key={a.key} label={a.label} value={n0(a.adet)} help={`Aşamada ortanca ${hours(a.ortancaSaat)} · en eski ${hours(a.enEskiSaat)}`}
                explain="Şu an bu aşamada duran sipariş sayısı. «Ortanca» siparişlerin yarısının bu süreden kısa beklediğini söyler; «en eski» en uzun bekleyen siparişin süresidir."
                info={<SqlInfo k={d.kaynaklar} alan="asamalar" label={`${a.label} · sipariş ve süre`} />} />
            ))}
          </KpiRow>
          <Panel>
            <h2 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">
              Aşama süreleri — son {d.pencereGun} günde sevk edilenler
              <SqlInfo k={d.kaynaklar} alan="pencereGun" label="Pencere (gün)" />
            </h2>
            <TableWrap>
              <thead>
                <tr>
                  <th className={th}>Aşama</th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="sureler">Ortanca</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="sureler">Sipariş</InfoLabel></th>
                </tr>
              </thead>
              <tbody>
                {d.sureler.map((s) => (
                  <tr key={s.from + s.to} className="border-t border-slate-100">
                    <td className={td}>{s.label}</td>
                    <td className={`${td} ${num}`}>{hours(s.ortancaSaat)}</td>
                    <td className={`${td} ${num}`}>{n0(s.siparis)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </Panel>
          <Panel>
            <h2 className="mb-2 flex items-center gap-1 text-[13px] font-extrabold">
              Depodaki siparişler (en uzun bekleyen üstte)
              <SqlInfo k={d.kaynaklar} alan="acik.total" label="Depodaki sipariş sayısı" />
            </h2>
            {!d.acik.items.length && <EmptyHint title="Depoda bekleyen sipariş yok" why="Şu an hazırlık aşamalarından birinde duran sipariş bulunmuyor." />}
            {!!d.acik.items.length && (
              <TableWrap>
                <thead>
                  <tr>
                    <th className={th}>Sipariş</th>
                    <th className={th}>Aşama</th>
                    <th className={th}>Depo</th>
                    <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="acik.items[].asamaSaat">Aşamada</InfoLabel></th>
                    <th className={th}>Öncelik</th>
                    {d.kisiGorunur && <th className={th}>Toplayan</th>}
                  </tr>
                </thead>
                <tbody>
                  {d.acik.items.map((o) => (
                    <tr key={o.id} className="border-t border-slate-100">
                      <td className={`${td} font-mono`}>{o.no ?? '—'}</td>
                      <td className={td}>{o.asamaEtiket}</td>
                      <td className={td}>{o.depo ?? '—'}</td>
                      <td className={`${td} ${num}`}>{hours(o.asamaSaat)}</td>
                      <td className={td}>{o.oncelik ?? '—'}</td>
                      {d.kisiGorunur && <td className={td}>{o.toplayan ?? '—'}</td>}
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            )}
            <Pager page={d.acik.page} pageSize={d.acik.pageSize} total={d.acik.total} shown={d.acik.items.length} loading={q.isLoading} fetching={q.isFetching}
              onPage={(p) => { const n = new URLSearchParams(params); n.set('sayfa', String(p)); setParams(n, { replace: true }); }} />
          </Panel>
          {d.kisiler && (
            <Panel>
              <h2 className="mb-2 text-[13px] font-extrabold">Toplayıcı başına (pusula → kutulandı)</h2>
              {!d.kisiler.length && <Empty>Pencerede ölçülebilen toplama yok.</Empty>}
              {!!d.kisiler.length && (
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Toplayan</th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kisiler">Sipariş</InfoLabel></th>
                      <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="kisiler">Ortanca süre</InfoLabel></th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.kisiler.map((k) => (
                      <tr key={k.toplayan} className="border-t border-slate-100">
                        <td className={td}>{k.toplayan}</td>
                        <td className={`${td} ${num}`}>{n0(k.siparis)}</td>
                        <td className={`${td} ${num}`}>{hours(k.ortancaSaat)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              )}
            </Panel>
          )}
        </>
      )}
    </StockFrame>
  );
}
