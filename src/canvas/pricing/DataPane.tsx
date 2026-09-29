import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Save } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnPrimary, errText, field, fmtDate, label as labelCls, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { day, mn, num, overviewKey, pct, pricingApi, tl2, type Defaults, type Overview } from './api';
import { NumField, parseQtys } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { useCan } from '../useAdmin';
import TariffPanel from './TariffPanel';

/** Ölçülen değerler (kanal iskontosu, kâğıt fiyatı, dağıtım gideri), düzenlenebilir varsayımlar ve kaynak sorgular. */
export default function DataPane({ ov }: { ov: Overview }) {
  const m = ov.measured;
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <TariffPanel />
      {m && (
        <>
          <Panel>
            <h3 className="flex flex-wrap items-center gap-1.5 text-[14px] font-extrabold">Kanal iskontoları · {day(m.distribution.from)} – {day(m.dataEnd)}<SqlInfo k={ov.kaynaklar} alan="measured.channels" label="Kanal iskontoları" /></h3>
            <p className="mt-0.5 text-[11.5px] text-canvas-muted">
              Logo kitap satışı (faturalı), cari kartın grup koduna göre. İskonto = 1 − net ÷ liste tutarı. Ağırlıklı ortalama {pct(m.discount)}.
            </p>
            <div className="mt-2">
              <TableWrap>
                <thead>
                  <tr>
                    <th className={th}>Müşteri grubu</th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.channels">Adet</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.channels">Liste tutarı</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.channels">Net</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.channels">İskonto</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.channels">Pay</InfoLabel></th>
                  </tr>
                </thead>
                <tbody>
                  {m.channels.map((c) => (
                    <tr key={c.channel} className="border-t border-slate-100">
                      <td className={td}>{c.channel}</td>
                      <td className={`${td} text-right tabular-nums`}>{num(c.qty)}</td>
                      <td className={`${td} text-right tabular-nums`}>{mn(c.gross)}</td>
                      <td className={`${td} text-right tabular-nums`}>{mn(c.net)}</td>
                      <td className={`${td} text-right tabular-nums`}>{pct(c.discount)}</td>
                      <td className={`${td} text-right tabular-nums`}>{pct(c.share)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            </div>
          </Panel>

          <Panel>
            <h3 className="flex flex-wrap items-center gap-1.5 text-[14px] font-extrabold">Kâğıt ve bandrol alışları · son 6 ay<SqlInfo k={ov.kaynaklar} alan="measured.paper" label="Kâğıt ve bandrol alışları" /></h3>
            <p className="mt-0.5 text-[11.5px] text-canvas-muted">
              İç kâğıt ortalaması {tl2(m.paper.innerPerKg)}/kg, kapak kartonu {tl2(m.paper.coverPerKg)}/kg, bandrol {tl2(m.paper.bandrol?.unit)}/adet. Kâğıt maliyeti
              hesabında fire %10 ve kapak alanı iki sayfanın 2,3 katı varsayılır (ölçülemedi).
            </p>
            <div className="mt-2">
              <TableWrap>
                <thead>
                  <tr>
                    <th className={th}>Kâğıt</th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.paper">Gramaj</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.paper">kg</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.paper">Tutar</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={ov.kaynaklar} alan="measured.paper">₺ / kg</InfoLabel></th>
                    <th className={th}>Son alış</th>
                  </tr>
                </thead>
                <tbody>
                  {m.paper.items.map((p) => (
                    <tr key={p.code} className="border-t border-slate-100">
                      <td className={td}>
                        {p.name}
                        <div className="text-[11px] text-canvas-muted">{p.kind === 'kapak' ? 'Kapak' : 'İç sayfa'} · {p.code}</div>
                      </td>
                      <td className={`${td} text-right tabular-nums`}>{num(p.gsm)}</td>
                      <td className={`${td} text-right tabular-nums`}>{num(p.kg)}</td>
                      <td className={`${td} text-right tabular-nums`}>{mn(p.amount)}</td>
                      <td className={`${td} text-right tabular-nums`}>{tl2(p.perKg)}</td>
                      <td className={td}>{day(p.last)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
            </div>
          </Panel>

          <Panel>
            <h3 className="flex items-center gap-1.5 text-[14px] font-extrabold">Dağıtım gideri<SqlInfo k={ov.kaynaklar} alan="measured.distribution" label="Dağıtım gideri oranı" /></h3>
            <p className="mt-1 text-[12.5px]">
              Son 12 ayın satış nakliye gideri {mn(m.distribution.freight)}, kitap net satışı {mn(m.distribution.net)} → <b>{pct(m.distribution.rate)}</b>. Hesapta
              «dağıtım gideri» kutusunun önerisi budur.
            </p>
          </Panel>
        </>
      )}

      <DefaultsForm ov={ov} />
      <SourcesList />
    </div>
  );
}

function DefaultsForm({ ov }: { ov: Overview }) {
  const qc = useQueryClient();
  const [d, setD] = useState<Defaults>(ov.defaults);
  const [qtyText, setQtyText] = useState(ov.defaults.qtys.join(', '));
  useEffect(() => {
    setD(ov.defaults);
    setQtyText(ov.defaults.qtys.join(', '));
  }, [ov.defaults]);
  const save = useMutation({
    mutationFn: () =>
      pricingApi.saveDefaults({ targetMargin: d.targetMargin, variableRate: d.variableRate, overheadRate: d.overheadRate, sellThrough: d.sellThrough, qtys: parseQtys(qtyText) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: overviewKey }),
  });
  const ro = !ov.me.canWrite;
  return (
    <Panel>
      <h3 className="text-[14px] font-extrabold">Varsayımlar (veride karşılığı olmayan iş kararları)</h3>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">
        Yeni hesapların başlangıç değerleri. Kayıtlı analizler kendi girdileriyle kalır.
        {ov.defaults.updatedBy ? ` Son değiştiren ${ov.defaults.updatedBy}, ${fmtDate(ov.defaults.updatedAt)}.` : ''}
      </p>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <NumField label="Hedef kâr marjı" info={<SqlInfo k={ov.kaynaklar} alan="defaults" label="Hedef kâr marjı (varsayım)" />} suffix="%" percent value={d.targetMargin} disabled={ro} onChange={(v) => setD({ ...d, targetMargin: v ?? 0 })} />
        <NumField label="Dağıtım gideri (ölçülemezse)" info={<SqlInfo k={ov.kaynaklar} alan="defaults" label="Dağıtım gideri (varsayım)" />} suffix="%" percent value={d.variableRate} disabled={ro} onChange={(v) => setD({ ...d, variableRate: v ?? 0 })} />
        <NumField label="Genel gider payı" info={<SqlInfo k={ov.kaynaklar} alan="defaults" label="Genel gider payı (varsayım)" />} suffix="%" percent value={d.overheadRate} disabled={ro} onChange={(v) => setD({ ...d, overheadRate: v ?? 0 })} />
        <NumField label="Satış oranı" info={<SqlInfo k={ov.kaynaklar} alan="defaults" label="Satış oranı (varsayım)" />} suffix="%" percent value={d.sellThrough} disabled={ro} onChange={(v) => setD({ ...d, sellThrough: v ?? 1 })} />
        <label className="block min-w-0">
          <span className={`${labelCls} flex items-center gap-1`}>Baskı adedi senaryoları<SqlInfo k={ov.kaynaklar} alan="defaults" label="Baskı adedi senaryoları (varsayım)" /></span>
          <input className={`${field} mt-1 tabular-nums`} value={qtyText} disabled={ro} onChange={(e) => setQtyText(e.target.value)} />
        </label>
      </div>
      {!ro && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button type="button" className={btnPrimary} disabled={save.isPending || !parseQtys(qtyText).length} onClick={() => save.mutate()}>
            <Save aria-hidden className="h-4 w-4" />
            Varsayımları kaydet
          </button>
          {save.isSuccess && <span className="text-[12px] font-semibold text-emerald-700">Kaydedildi.</span>}
        </div>
      )}
      {save.error && <div className="mt-2"><Note tone="err">{errText(save.error, 'Kaydedilemedi.')}</Note></div>}
    </Panel>
  );
}

function SourcesList() {
  const canSql = useCan('kart.sql-goster');
  const src = useQuery({ queryKey: ['pricing', 'sources'], queryFn: pricingApi.sources, enabled: ENGINE_ENABLED });
  if (src.error) return <Note tone="err">{errText(src.error, 'Kaynaklar okunamadı.')}</Note>;
  if (!src.data) return <Loading />;
  return (
    <Panel>
      <h3 className="text-[14px] font-extrabold">Kaynak sorgular</h3>
      <p className="mt-0.5 text-[11.5px] text-canvas-muted">
        Yalnız okuma. Logo'da her yıl ayrı bir kopya: {(src.data.copies ?? []).map((c) => `${c.from.slice(0, 4)}–${c.last.slice(0, 4)}`).join(', ') || '—'}; her kopyadan
        yalnız kendi tarihleri okunur. Görüntü {day(src.data.asOf)}.
      </p>
      <div className="mt-2 space-y-2">
        {src.data.sources.map((s) => (
          <details key={s.id} className="rounded-xl border border-slate-100 bg-white/70 p-2">
            <summary className="cursor-pointer text-[12.5px] font-bold">
              {s.title} <span className="font-normal text-canvas-muted">· {s.connection === 'logo' ? 'Logo' : 'CRM'}{s.stats ? ` · ${num(s.stats.rows)} satır, ${num(s.stats.ms / 1000)} sn` : ''}{s.runs > 1 ? ` · ${s.runs} kopyada` : ''}</span>
            </summary>
            <p className="mt-1 flex flex-wrap items-center gap-1 text-[11.5px] text-canvas-muted">
              {s.description}
              <InfoLabel k={src.data.kaynaklar} alan="sources[]" row={s.id} label={s.title}>Çalışan sorgular</InfoLabel>
            </p>
            {s.sql && !canSql ? (
              <p className="mt-1 text-[11.5px] text-canvas-muted">SQL metni «SQL'i göster ve kopyala» yetkisinde görünür.</p>
            ) : s.sql ? (
              <pre className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-relaxed text-slate-100">{s.sql}</pre>
            ) : (
              <p className="mt-1 text-[11.5px] text-canvas-muted">Görüntü henüz kurulmadı; sorgu ilk kurulumda çalışır.</p>
            )}
          </details>
        ))}
      </div>
    </Panel>
  );
}
