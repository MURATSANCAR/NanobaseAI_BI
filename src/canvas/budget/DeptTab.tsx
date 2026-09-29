import { Fragment, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnGhost, btnPrimary, errText, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { DEPT, budgetApi, fmtMoney, fmtPct, parseNum, type DeptLine, type Plan } from './api';
import { NumField } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

const AY = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

function EditSheet({ plan, line, editable, onClose, k }: { plan: Plan; line: DeptLine | null; editable: boolean; onClose: () => void; k?: Kaynaklar }) {
  const qc = useQueryClient();
  const [months, setMonths] = useState<string[]>([]);
  const [total, setTotal] = useState('');
  useEffect(() => {
    if (!line) return;
    setMonths(line.aylar.map((v) => v.toLocaleString('tr-TR', { maximumFractionDigits: 2 })));
    setTotal(line.yillik.toLocaleString('tr-TR', { maximumFractionDigits: 2 }));
  }, [line]);
  const save = useMutation({
    mutationFn: (mode: 'aylar' | 'yillik') => {
      if (mode === 'yillik') {
        const y = parseNum(total);
        if (y === null) throw new Error('Yıllık bütçe sayı olmalı.');
        return budgetApi.updateDept(plan.id, line!.merkezKodu, line!.hesap, { yillik: y });
      }
      const vals = months.map(parseNum);
      if (vals.some((v) => v === null)) throw new Error('Her ayın tutarı sayı olmalı.');
      return budgetApi.updateDept(plan.id, line!.merkezKodu, line!.hesap, { aylar: vals as number[] });
    },
    onSuccess: () => {
      toast.success('Bütçe satırı kaydedildi.');
      qc.invalidateQueries({ queryKey: ['budget'] });
      onClose();
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const iz = line?.izleme;
  return (
    <Sheet open={!!line} onClose={onClose} modal wide title={line ? `${line.merkezAdi} · ${line.hesapAdi}` : ''}
      subtitle={line ? (
        <>
          Masraf merkezi {line.merkezKodu.startsWith('#') ? '—' : line.merkezKodu} · hesap {line.hesap}. Öneri: taban dönemin aynı ayı × (1 + gider artışı {fmtPct(line.oneri.gider ?? 0)}).
          <SqlInfo k={k} alan="items[].oneri" label="Gider artışı ve öneri" className="ml-0.5" />
        </>
      ) : undefined}>
      {line && (
        <div className="flex flex-col gap-4">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Ay</th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="items[].oneri" label="Taban dönemi gideri">Taban</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="items[].aylar" label="Aylık bütçe">Bütçe</InfoLabel></th>
                {iz && <th className={`${th} text-right`}><InfoLabel k={k} alan="items[].izleme.gercekAylar" label="Aylık gerçekleşen gider">Gerçekleşen</InfoLabel></th>}
              </tr>
            </thead>
            <tbody>
              {AY.map((a, i) => (
                <tr key={a} className="border-t border-slate-100">
                  <td className={td}>{a}</td>
                  <td className={`${td} text-right font-mono tabular-nums text-canvas-muted`}>{fmtMoney(line.oneri.taban?.[i] ?? null)}</td>
                  <td className={`${td} text-right`}>
                    {editable ? (
                      <input inputMode="decimal" aria-label={`${a} bütçesi`} className="w-36 rounded-lg border border-slate-200 bg-white px-2 py-1 text-right font-mono text-base tabular-nums sm:text-[12px]"
                        value={months[i] ?? ''} onChange={(e) => setMonths((m) => m.map((x, j) => (j === i ? e.target.value : x)))} />
                    ) : (
                      <span className="font-mono tabular-nums">{fmtMoney(line.aylar[i])}</span>
                    )}
                  </td>
                  {iz && <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(iz.gercekAylar[i])}</td>}
                </tr>
              ))}
            </tbody>
          </TableWrap>
          {editable && (
            <div className="grid grid-cols-1 items-end gap-3 sm:grid-cols-[1fr_auto_auto]">
              <NumField id="d-yillik" label="Yıllık toplam (aylara mevcut oranla dağıtılır)" value={total} onChange={setTotal} suffix="₺" />
              <button type="button" className={btnGhost} onClick={() => save.mutate('yillik')} disabled={save.isPending}>Yıllığı dağıt</button>
              <button type="button" className={btnPrimary} onClick={() => save.mutate('aylar')} disabled={save.isPending}>Ayları kaydet</button>
            </div>
          )}
        </div>
      )}
    </Sheet>
  );
}

export default function DeptTab({ plan, editable }: { plan: Plan; editable: boolean }) {
  const [open, setOpen] = useState<DeptLine | null>(null);
  const q = useQuery({ queryKey: ['budget', 'departments', plan.id], queryFn: () => budgetApi.departments(plan.id), enabled: ENGINE_ENABLED });
  const groups = useMemo(() => {
    const m = new Map<string, DeptLine[]>();
    for (const d of q.data?.items ?? []) m.set(d.merkezKodu, [...(m.get(d.merkezKodu) ?? []), d]);
    return [...m.entries()]
      .map(([k, rows]) => ({ key: k, name: rows[0].merkezAdi ?? k, rows, total: rows.reduce((s, r) => s + r.yillik, 0) }))
      .sort((a, b) => b.total - a.total);
  }, [q.data]);
  const track = !!q.data?.asof;
  return (
    <Panel>
      <div className="mb-2">
        <h3 className="text-[15px] font-extrabold">Departman bütçesi</h3>
        <p className="max-w-[80ch] text-[12px] text-canvas-muted">
          Masraf merkezi × ana gider hesabı (Logo 7 ile başlayan hesaplar; yansıtma ve dönem sonu kapanış kayıtları hariç). Kitaba açılmış merkezler (telif, baskı)
          tek satırda toplanır. Kullanım = gerçekleşen ÷ bugüne düşen bütçe; %90 sınırda, %100 aşım uyarısıdır.
        </p>
      </div>
      {q.isLoading ? <Loading /> : q.error ? <Note tone="err">{errText(q.error, 'Bütçe okunamadı.')}</Note> : !groups.length ? (
        <Note tone="info">Bu planda departman bütçesi satırı yok.</Note>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Departman / hesap</th>
              <th className={`${th} text-right`}><InfoLabel k={q.data?.kaynaklar} alan="items[].yillik">Yıllık bütçe</InfoLabel></th>
              {track && (
                <>
                  <th className={`${th} text-right`}><InfoLabel k={q.data?.kaynaklar} alan="items[].izleme.butceDonem">Bugüne bütçe</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={q.data?.kaynaklar} alan="items[].izleme.gercek">Gerçekleşen</InfoLabel></th>
                  <th className={`${th} text-right`}><InfoLabel k={q.data?.kaynaklar} alan="items[].izleme.kullanim">Kullanım</InfoLabel></th>
                  <th className={th}>Durum</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <Fragment key={g.key}>
                <tr className="border-t-2 border-slate-200 bg-slate-50/70">
                  <td className={`${td} font-extrabold`}>{g.name}</td>
                  <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtMoney(g.total)}</td>
                  {track && (
                    <>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(g.rows.reduce((s, r) => s + (r.izleme?.butceDonem ?? 0), 0))}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(g.rows.reduce((s, r) => s + (r.izleme?.gercek ?? 0), 0))}</td>
                      <td className={td} />
                      <td className={td} />
                    </>
                  )}
                </tr>
                {g.rows.map((r) => (
                  <tr key={`${r.merkezKodu}-${r.hesap}`} onClick={() => setOpen(r)} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50/80">
                    <td className={`${td} pl-6`}>
                      <button type="button" className="text-left" onClick={(e) => { e.stopPropagation(); setOpen(r); }}>
                        {r.hesap} · {r.hesapAdi}
                        {r.elle && <span className="ml-1 text-[11px] text-canvas-muted">· elle</span>}
                      </button>
                    </td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.yillik)}</td>
                    {track && r.izleme && (
                      <>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.izleme.butceDonem)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.izleme.gercek)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.izleme.kullanim, 0)}</td>
                        <td className={td}>
                          <span className={`inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-bold ${DEPT[r.izleme.durum].pill}`}>{DEPT[r.izleme.durum].label}</span>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </Fragment>
            ))}
          </tbody>
        </TableWrap>
      )}
      <EditSheet plan={plan} line={open} editable={editable} onClose={() => setOpen(null)} k={q.data?.kaynaklar} />
    </Panel>
  );
}
