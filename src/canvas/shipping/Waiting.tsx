import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { ageTone, fmtDay, fmtInt, fmtMoney, fmtNum, shippingApi } from './api';
import { Empty, ExportButton, FreshNote, ShippingFrame } from './parts';

/** M44 Teslim bekleyen (/kargo/bekleyen): kargo kaydında teslim tarihi olmayan ve iade olmayan gönderiler, yaşa göre.
 *  Termin tutulmadığı için «geç teslim» değil «bekleyen gün» yazılır. Süzgeç adres çubuğunda (?gun=, ?firma=, ?sehir=). */

export default function Waiting() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['shipping', 'meta'], queryFn: shippingApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const gunParam = params.get('gun');
  const gun = gunParam !== null && /^\d{1,3}$/.test(gunParam) ? Number(gunParam) : meta.data?.is.bekleyenGun;
  const firma = params.get('firma') ?? '';
  const sehir = params.get('sehir') ?? '';
  const [page, setPage] = useState(0);
  const list = useQuery({
    queryKey: ['shipping', 'waiting', gun, firma, sehir, page],
    queryFn: () => shippingApi.waiting({ gun, firma, sehir, sayfa: page }),
    enabled: ENGINE_ENABLED && gun !== undefined,
    placeholderData: (prev) => prev,
  });
  const set = (k: string, v: string) => {
    const p = new URLSearchParams(params);
    if (v) p.set(k, v);
    else p.delete(k);
    setParams(p, { replace: true });
    setPage(0);
  };
  const d = list.data;
  const cost = !!meta.data?.me.maliyet;
  return (
    <ShippingFrame
      crumb="Teslim bekleyen"
      title="Teslim bekleyen gönderiler"
      lead="Kargo firmasının kaydında teslim tarihi ve iade bilgisi olmayan gönderiler; yaş = bugün − kargo irsaliye tarihi. Firmayı arayıp takip etmek için firma bazında ayrılır."
      meta={meta.data}
      aside={
        meta.data && (
          <div className="flex justify-start lg:justify-end">
            <ExportButton list="bekleyen" params={{ gun, firma: firma || undefined, sehir: sehir || undefined }} can={meta.data.me.disaAktar} label="Excel'e al" />
          </div>
        )
      }
    >
      {list.error && <Note tone="err">{errText(list.error, 'Liste okunamadı.')}</Note>}
      <Panel>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 lg:max-w-[900px]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>En az bekleyen gün</span>
            <input className={field} inputMode="numeric" value={gunParam ?? String(gun ?? '')} onChange={(e) => set('gun', e.target.value.replace(/\D/g, '').slice(0, 3))} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Kargo firması</span>
            <select className={field} value={firma} onChange={(e) => set('firma', e.target.value)}>
              <option value="">Hepsi</option>
              {(d?.firmaListesi ?? []).map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Alıcı şehri</span>
            <select className={field} value={sehir} onChange={(e) => set('sehir', e.target.value)}>
              <option value="">Hepsi</option>
              {(d?.sehirler ?? []).map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </label>
        </div>
      </Panel>
      {d && (
        <>
          <KpiRow>
            <Kpi label={`${d.esikGun}+ gün bekleyen`} value={fmtInt(d.esikUstu)} help="Teslim ve iade bilgisi yok"
              info={<SqlInfo k={d.kaynaklar} alan="esikUstu" label="Eşiği aşan teslim bekleyen" />} />
            <Kpi label="Toplam teslim bekleyen" value={fmtInt(d.toplam)} help="Süzgeçteki bütün gönderiler"
              info={<SqlInfo k={d.kaynaklar} alan="toplam" label="Toplam teslim bekleyen" />} />
            {d.kovalar.slice(-2).map((k) => (
              <Kpi key={k.kova} label={k.kova} value={fmtInt(k.adet)} help="Yaş kovası" info={<SqlInfo k={d.kaynaklar} alan="kovalar" label={`Yaş kovası ${k.kova}`} />} />
            ))}
          </KpiRow>
          <FreshNote f={d.kargoVeri} k={d.kaynaklar} />
          <Panel>
            <h2 className="text-[14px] font-extrabold"><InfoLabel k={d.kaynaklar} alan="firmalar" label="Firma × yaş kovası">Firma bazında</InfoLabel></h2>
            {d.firmalar.length === 0 ? (
              <Empty>Teslim bekleyen gönderi yok (veri sonuna bakın).</Empty>
            ) : (
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Firma</th>
                      {d.kovalar.map((k) => <th key={k.kova} className={`${th} text-right`}>{k.kova}</th>)}
                      <th className={`${th} text-right`}>{d.esikGun}+ gün</th>
                      <th className={`${th} text-right`}>Toplam</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.firmalar.map((f) => (
                      <tr key={f.firma} className="border-t border-slate-100">
                        <td className={td}>
                          <button type="button" className="text-left font-bold text-canvas-violet hover:underline" onClick={() => set('firma', f.firma)}>{f.firma}</button>
                        </td>
                        {d.kovalar.map((k) => <td key={k.kova} className={`${td} text-right font-mono tabular-nums`}>{fmtInt(Number(f[k.kova] ?? 0))}</td>)}
                        <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtInt(f.esikUstu)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(f.toplam)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
            )}
          </Panel>
          <Panel>
            <h2 className="text-[14px] font-extrabold"><InfoLabel k={d.kaynaklar} alan="items[]" label="Bekleyen gönderiler">{`Gönderiler (${d.esikGun}+ gün, en eskisi önce)`}</InfoLabel></h2>
            {d.items.length === 0 ? (
              <Empty>Bu eşikte bekleyen gönderi yok.</Empty>
            ) : (
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Takip no</th>
                      <th className={th}>Firma</th>
                      <th className={th}>Kargo irsaliyesi</th>
                      <th className={`${th} text-right`}>Bekleyen</th>
                      <th className={th}>Şehir / şube</th>
                      <th className={th}>Kanal</th>
                      {cost && <th className={`${th} text-right`}>Desi</th>}
                      {cost && <th className={`${th} text-right`}>Tutar</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((c) => (
                      <tr key={c.id} className="border-t border-slate-100">
                        <td className={`${td} font-mono`}>{c.takipNo ?? c.musteriIrsNo ?? '—'}</td>
                        <td className={td}>{c.firma}</td>
                        <td className={`${td} font-mono tabular-nums`}>{fmtDay(c.irsTarihi)}</td>
                        <td className={`${td} text-right`}><Pill tone={ageTone(c.yas, d.esikGun)}>{fmtInt(c.yas)} gün</Pill></td>
                        <td className={td}>{[c.sehir, c.varisSube].filter(Boolean).join(' · ') || '—'}</td>
                        <td className={td}>{c.kanal ?? '—'}{c.tahsilatli && <span className="ml-1"><Pill tone="warn">Tahsilatlı</Pill></span>}</td>
                        {cost && <td className={`${td} text-right font-mono tabular-nums`}>{fmtNum(c.desi)}</td>}
                        {cost && <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(c.tutar)}</td>}
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
            )}
            {(d.devami || page > 0) && (
              <div className="mt-3 flex items-center justify-between gap-2">
                <span className="font-mono text-[11.5px] text-canvas-muted">Sayfa {page + 1} · {fmtInt(d.esikUstu)} gönderi</span>
                <div className="flex gap-1.5">
                  <button type="button" className={btnGhost} disabled={page === 0 || list.isFetching} onClick={() => setPage((p) => Math.max(0, p - 1))}>Önceki</button>
                  <button type="button" className={btnGhost} disabled={!d.devami || list.isFetching} onClick={() => setPage((p) => p + 1)}>Sonraki</button>
                </div>
              </div>
            )}
          </Panel>
        </>
      )}
      {list.isLoading && <Empty>Kargo kayıtları okunuyor…</Empty>}
    </ShippingFrame>
  );
}
