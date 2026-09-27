import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnPrimary, errText, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { budgetApi, fmtInt, fmtMoney, fmtPct, parseNum, type Plan, type ProgramLine } from './api';
import { NumField } from './parts';

function EditSheet({ plan, line, onClose }: { plan: Plan; line: ProgramLine | null; onClose: () => void }) {
  const qc = useQueryClient();
  const [ek, setEk] = useState('');
  const [adet, setAdet] = useState('');
  const [ciro, setCiro] = useState('');
  const [marj, setMarj] = useState('');
  useEffect(() => {
    if (!line) return;
    setEk(String(line.ekBaslik));
    setAdet(line.baslikAdet.toLocaleString('tr-TR', { maximumFractionDigits: 1 }));
    setCiro(line.baslikCiro.toLocaleString('tr-TR', { maximumFractionDigits: 2 }));
    setMarj(line.marj === null ? '' : (line.marj * 100).toLocaleString('tr-TR', { maximumFractionDigits: 1 }));
  }, [line]);
  const save = useMutation({
    mutationFn: () => {
      const e = parseNum(ek);
      const a = parseNum(adet);
      const c = parseNum(ciro);
      const m = parseNum(marj);
      if (e === null || a === null || c === null) throw new Error('Başlık sayısı, adet ve ciro sayı olmalı.');
      return budgetApi.updateProgram(plan.id, line!.yayinevi, { ekBaslik: e, baslikAdet: a, baslikCiro: c, marj: m === null ? null : m / 100 });
    },
    onSuccess: () => {
      toast.success('Program satırı kaydedildi.');
      qc.invalidateQueries({ queryKey: ['budget'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const o = (line?.oneri ?? {}) as Record<string, number | string>;
  return (
    <Sheet open={!!line} onClose={onClose} modal title={line?.yayinevi ?? ''}
      subtitle={line ? `Taban dönemde (${o.pencere ?? ''}) ${fmtInt(Number(o.kohortBaslik ?? 0))} yeni başlık çıktı, toplam ${fmtInt(Number(o.kohortAdet ?? 0))} adet sattı. CRM'de adıyla planlanmış ${fmtInt(line.bilinen)} kitap hedef listesinde.` : undefined}>
      <div className="flex flex-col gap-3">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <NumField id="p-ek" label="Ek başlık (adı belli olmayan)" value={ek} onChange={setEk} />
          <NumField id="p-adet" label="Başlık başına net adet" value={adet} onChange={setAdet} />
          <NumField id="p-ciro" label="Başlık başına net ciro" value={ciro} onChange={setCiro} suffix="₺" />
          <NumField id="p-marj" label="Brüt marj" value={marj} onChange={setMarj} suffix="%" />
        </div>
        <div className="flex justify-end">
          <button type="button" className={btnPrimary} onClick={() => save.mutate()} disabled={save.isPending}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}

export default function ProgramTab({ plan, editable }: { plan: Plan; editable: boolean }) {
  const [open, setOpen] = useState<ProgramLine | null>(null);
  const q = useQuery({ queryKey: ['budget', 'program', plan.id], queryFn: () => budgetApi.program(plan.id), enabled: ENGINE_ENABLED });
  const items = q.data?.items ?? [];
  const sum = items.reduce((s, p) => ({ baslik: s.baslik + p.baslik, bilinen: s.bilinen + p.bilinen, ek: s.ek + p.ekBaslik, adet: s.adet + p.adet, ciro: s.ciro + p.ciro }),
    { baslik: 0, bilinen: 0, ek: 0, adet: 0, ciro: 0 });
  return (
    <Panel>
      <div className="mb-2">
        <h3 className="text-[15px] font-extrabold">Yeni kitap programı</h3>
        <p className="max-w-[80ch] text-[12px] text-canvas-muted">
          Yayınevi başına yıl içinde beklenen yeni başlık sayısı, taban dönemde çıkan başlık sayısıdır. CRM'de adı ve yayın tarihi belli olanlar
          Kitap hedefleri listesinde tek tek durur; geri kalanı «ek başlık» olarak burada, taban dönemdeki yeni kitapların başlık başına ortalamasıyla hedeflenir.
        </p>
      </div>
      {q.isLoading ? <Loading /> : q.error ? <Note tone="err">{errText(q.error, 'Program okunamadı.')}</Note> : !items.length ? (
        <Note tone="info">Programda satır yok.</Note>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Yayınevi</th>
              <th className={`${th} text-right`}>Beklenen başlık</th>
              <th className={`${th} text-right`}>CRM'de planlı</th>
              <th className={`${th} text-right`}>Ek başlık</th>
              <th className={`${th} text-right`}>Başlık başına adet</th>
              <th className={`${th} text-right`}>Ek başlık adedi</th>
              <th className={`${th} text-right`}>Ek başlık cirosu</th>
              <th className={`${th} text-right`}>Marj</th>
            </tr>
          </thead>
          <tbody>
            {items.map((p) => (
              <tr key={p.yayinevi} onClick={() => editable && setOpen(p)} className={`border-t border-slate-100 ${editable ? 'cursor-pointer hover:bg-slate-50/80' : ''}`}>
                <td className={`${td} font-semibold`}>
                  {editable ? <button type="button" className="text-left" onClick={(e) => { e.stopPropagation(); setOpen(p); }}>{p.yayinevi}</button> : p.yayinevi}
                  {p.elle && <span className="ml-1 text-[11px] font-normal text-canvas-muted">· elle</span>}
                </td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.baslik)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.bilinen)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.ekBaslik)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.baslikAdet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(p.adet)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(p.ciro)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(p.marj)}</td>
              </tr>
            ))}
            <tr className="border-t-2 border-slate-200 font-bold">
              <td className={td}>Toplam</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(sum.baslik)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(sum.bilinen)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(sum.ek)}</td>
              <td className={td} />
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(sum.adet)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(sum.ciro)}</td>
              <td className={td} />
            </tr>
          </tbody>
        </TableWrap>
      )}
      <EditSheet plan={plan} line={open} onClose={() => setOpen(null)} />
    </Panel>
  );
}
