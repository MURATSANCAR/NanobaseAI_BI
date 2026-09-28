import { Fragment, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { fmtMoney, fmtShortDay } from '../api';
import { Block } from '../parts';
import { blApi, fmtChange, fmtN, type BlMeta, type Campaign } from './api';

/** Etki: CRM kampanyalarında ürünlerin kampanya öncesi 3 ay, kampanya ayları ve sonraki 2 ay Logo net adedi (ay düzeyi).
 *  Öncesi/sonrasıdır; «kampanya şu kadar artırdı» denmez. */
export default function EffectsTab({ meta }: { meta: BlMeta }) {
  const [yil, setYil] = useState(0);
  const [onlyBacklist, setOnlyBacklist] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({ queryKey: ['bl', 'effects', yil, onlyBacklist], queryFn: () => blApi.effects(yil || undefined, onlyBacklist), enabled: ENGINE_ENABLED });
  const d = q.data;
  const money = meta.me.canSeeBudget;
  const tone = (c: Campaign) => (c.aylikDegisim === null ? 'muted' : c.aylikDegisim > 0 ? 'ok' : 'warn');

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end gap-2 px-1">
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Başlangıç yılı</span>
          <select className={`${field} w-auto`} value={yil} onChange={(e) => setYil(Number(e.target.value))}>
            <option value={0}>Hepsi</option>
            {(d?.yillar ?? []).map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        </label>
        <label className="inline-flex min-h-11 items-center gap-2 text-[12.5px] font-semibold sm:min-h-9">
          <input type="checkbox" className="h-4 w-4" checked={onlyBacklist} onChange={(e) => setOnlyBacklist(e.target.checked)} />
          Yalnız backlist ürünleri
        </label>
      </div>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Kampanyalar açılamadı.')}</Note>}
      {d && (
        <Block title={`Kampanyalar (${fmtN(d.total)})`} help={d.not}>
          {!d.items.length && <Note tone="info">Bu süzgeçte CRM kampanyası yok.</Note>}
          {d.items.length > 0 && (
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Kampanya</th>
                  <th className={th}>Tarih</th>
                  <th className={`${th} text-right`}>Ürün</th>
                  <th className={`${th} text-right`}>Önceki 3 ay</th>
                  <th className={`${th} text-right`}>Kampanya</th>
                  <th className={`${th} text-right`}>Sonraki 2 ay</th>
                  <th className={`${th} text-right`}>Aylık ort. değişim</th>
                  {money && <th className={`${th} text-right`}>Planlanan / gerçekleşen ciro</th>}
                </tr>
              </thead>
              <tbody>
                {d.items.map((c) => (
                  <Fragment key={c.kampanyaId}>
                    <tr className="border-b border-slate-50 align-top">
                      <td className={td}>
                        <button type="button" className="text-left font-extrabold hover:underline" aria-expanded={open === c.kampanyaId}
                          onClick={() => setOpen(open === c.kampanyaId ? null : c.kampanyaId)}>{c.ad ?? 'Kampanya'}</button>
                        <div className="text-[11px] text-canvas-muted">{c.mecra ?? '—'}{c.netIskonto !== null ? ` · net iskonto %${c.netIskonto}` : ''}</div>
                      </td>
                      <td className={`${td} whitespace-nowrap`}>{fmtShortDay(c.baslangic)} – {fmtShortDay(c.bitis)}</td>
                      <td className={`${td} text-right tabular-nums`}>{fmtN(c.urunler.length)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{c.tam ? fmtN(c.once3) : '—'}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{c.tam ? fmtN(c.kampanya) : '—'}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{c.tam ? fmtN(c.sonra2) : '—'}</td>
                      <td className={`${td} text-right`}><Pill tone={tone(c)}>{c.tam ? fmtChange(c.aylikDegisim) : 'eksik veri'}</Pill></td>
                      {money && <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(c.planlananCiro)} / {fmtMoney(c.gerceklesenCiro)}</td>}
                    </tr>
                    {open === c.kampanyaId && (
                      <tr className="border-b border-slate-50 bg-white/60">
                        <td className={td} colSpan={money ? 8 : 7}>
                          <ul className="flex flex-col gap-1 text-[12px]">
                            {c.urunler.map((u) => (
                              <li key={u.stokKodu} className="flex flex-wrap gap-x-3">
                                <strong>{u.kitapAdi ?? u.stokKodu}</strong>
                                <span className="text-canvas-muted">{u.stokKodu}{u.backlist ? ' · backlist' : ''}</span>
                                <span className="tabular-nums">önce {fmtN(u.once3)} · kampanya {fmtN(u.kampanya)} · sonra {fmtN(u.sonra2)}</span>
                                <span className="tabular-nums text-canvas-muted">{u.kapsam === 'tam' ? fmtChange(u.aylikDegisim) : u.kapsam === 'suruyor' ? 'sonrası henüz veride yok' : 'veri pencere dışında'}</span>
                              </li>
                            ))}
                          </ul>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </TableWrap>
          )}
        </Block>
      )}
    </div>
  );
}
