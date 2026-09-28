import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, field, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtInt, fmtPct, fmtUnit, supplyApi } from './api';
import { ErrorNote, ExportLink, SupplyFrame, Warnings, useSupplyMeta } from './parts';

/** M52 Birim baskı maliyeti eğilimi (/tedarik/maliyet): Logo'daki matbaa baskı faturasında adet başı bedel, ay ×
 *  kırılım (hepsi, cilt, sayfa bandı, baskı tipi, matbaa); kağıt alış fiyatı. «Birim maliyet» açıkça verilen yetkiyle. */

const KIRILIM = [
  { key: 'hepsi', label: 'Bütün baskılar' },
  { key: 'cilt', label: 'Ciltleme şekli' },
  { key: 'sayfa', label: 'Sayfa sayısı' },
  { key: 'baski-tipi', label: 'Baskı tipi' },
  { key: 'matbaa', label: 'Matbaa' },
] as const;

export default function CostTrend() {
  const [params, setParams] = useSearchParams();
  const kirilim = KIRILIM.find((k) => k.key === params.get('kirilim'))?.key ?? 'hepsi';
  const meta = useSupplyMeta();
  const me = meta.data?.me;
  const q = useQuery({ queryKey: ['supply', 'cost', kirilim], queryFn: () => supplyApi.cost(kirilim), enabled: ENGINE_ENABLED && !!me?.canCost });
  const c = q.data;
  const months = c?.aylar ?? [];
  return (
    <SupplyFrame
      title="Birim baskı maliyeti"
      lead="Adet başı baskı bedeli: Logo'daki matbaa baskı faturası (Komple Baskı Giderleri) ÷ faturalanan adet, KDV hariç; fatura ayına göre. «100 sayfa başı» farklı kalınlıktaki kitapları karşılaştırmak içindir. Eğilim: dönemin son yarısı ile ilk yarısının ağırlıklı ortalaması."
      aside={
        <div className="flex flex-wrap items-end justify-start gap-2 lg:justify-end">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kırılım</span>
            <select
              className={`${field} w-auto`}
              value={kirilim}
              onChange={(e) => {
                const n = new URLSearchParams(params);
                if (e.target.value === 'hepsi') n.delete('kirilim');
                else n.set('kirilim', e.target.value);
                setParams(n, { replace: true });
              }}
            >
              {KIRILIM.map((k) => (
                <option key={k.key} value={k.key}>
                  {k.label}
                </option>
              ))}
            </select>
          </label>
          {me?.canExport && me.canCost && <ExportLink href={supplyApi.exportUrl('maliyet', `?kirilim=${kirilim}`)} />}
        </div>
      }
    >
      {me && !me.canCost && <Note tone="info">Birim baskı maliyeti «birim maliyet» yetkisiyle görünür.</Note>}
      <ErrorNote error={q.error} fallback="Maliyet eğilimi okunamadı." />
      <Warnings items={c?.uyarilar} />
      {q.isLoading && <Loading />}
      {c && (
        <Panel>
          {c.gruplar.length === 0 ? (
            <Note tone="info">Dönemde baskı faturası karta bağlanmış iş yok.</Note>
          ) : (
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Grup</th>
                  <th className={`${th} text-right`}>İş</th>
                  <th className={`${th} text-right`}>Ağırlıklı birim</th>
                  <th className={`${th} text-right`}>Önceki yarı</th>
                  <th className={`${th} text-right`}>Son yarı</th>
                  <th className={`${th} text-right`}>Değişim</th>
                  {months.map((m) => (
                    <th key={m.key} className={`${th} text-right`}>
                      {m.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {c.gruplar.map((g) => (
                  <tr key={g.grup} className="border-b border-slate-50 last:border-0">
                    <td className={`${td} font-bold`}>{g.grup}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(g.is)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(g.agirlikliBirim)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(g.oncekiDonem)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(g.sonDonem)}</td>
                    <td className={`${td} text-right font-mono tabular-nums ${g.egilim && g.egilim > 0 ? 'text-red-700' : g.egilim ? 'text-emerald-700' : ''}`}>
                      {fmtPct(g.egilim, true)}
                    </td>
                    {months.map((m) => {
                      const v = g.aylar[m.key];
                      return (
                        <td key={m.key} className={`${td} text-right font-mono text-[11.5px] tabular-nums`}>
                          {v ? (
                            <>
                              {fmtUnit(v.agirlikliBirim)}
                              <div className="text-[10px] text-canvas-muted">
                                {v.is} iş{v.sayfa100 !== null ? ` · ${fmtUnit(v.sayfa100)}/100 sf` : ''}
                              </div>
                            </>
                          ) : (
                            <span className="text-canvas-muted">·</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          )}
        </Panel>
      )}
      {c && c.kagit.length > 0 && (
        <Panel>
          <h2 className="px-1 text-[13px] font-extrabold">Kağıt alış fiyatı (kağıtçı carileri)</h2>
          <div className="mt-2">
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Malzeme</th>
                  <th className={th}>Birim</th>
                  <th className={`${th} text-right`}>İlk ay</th>
                  <th className={`${th} text-right`}>Son ay</th>
                  <th className={`${th} text-right`}>Değişim</th>
                </tr>
              </thead>
              <tbody>
                {c.kagit.map((f) => (
                  <tr key={`${f.kod}-${f.birim}`} className="border-b border-slate-50 last:border-0">
                    <td className={td}>
                      <div className="font-bold">{f.ad}</div>
                      <div className="text-[10.5px] text-canvas-muted">{f.kod}</div>
                    </td>
                    <td className={td}>{f.birim || '—'}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(f.ilk)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnit(f.son)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(f.degisim, true)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        </Panel>
      )}
    </SupplyFrame>
  );
}
