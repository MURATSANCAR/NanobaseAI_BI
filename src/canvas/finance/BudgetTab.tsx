import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { HelpCircle, MessageSquareText } from 'lucide-react';
import ReasonSheet from '../reason/ReasonSheet';
import { reasonApi } from '../reason/api';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, btnGhost, btnPrimary, errText, field, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import Sheet from '../editorial/studio/reader/Sheet';
import { DEPT, TRACK, type DeptState, type TrackState } from '../budget/api';
import { financeApi, fmtDay, fmtMoney, fmtPct, fmtShort, type BudgetView, type Note as FNote } from './api';
import { DataEnd, Money } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';

/** Bütçe–gerçekleşme: M46'nın yürürlükteki planı (aynı tanım, yeniden hesap yok). Gider kalemine sapma açıklaması
 *  yazılır; kalemin muhasebe fişleri Gelir tablosu sekmesindeki hesap satırından açılır. */

type NoteTarget = { anahtar: string; baslik: string; not: FNote | null } | null;

function NoteSheet({ target, year, onClose }: { target: NoteTarget; year: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const save = useMutation({
    mutationFn: () => financeApi.saveNote({ year, anahtar: target!.anahtar, metin: text || target?.not?.metin || '' }),
    onSuccess: () => { toast.success('Açıklama kaydedildi.'); qc.invalidateQueries({ queryKey: ['finance', 'budget'] }); setText(''); onClose(); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  return (
    <Sheet open={!!target} modal onClose={() => { setText(''); onClose(); }} title="Sapma açıklaması" subtitle={target?.baslik}>
      <div className="flex flex-col gap-3">
        {target?.not && <p className="text-[12px] text-canvas-muted">Son yazan {target.not.hazirlayan}, {fmtDay(target.not.tarih)}.</p>}
        <textarea className={`${field} min-h-[120px]`} defaultValue={target?.not?.metin ?? ''} onChange={(e) => setText(e.target.value)}
          placeholder="Sapmanın nedeni: kayıt hatası mı, gerçek harcama mı, dönem kayması mı?" />
        <div className="flex justify-end gap-2">
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
        </div>
      </div>
    </Sheet>
  );
}

export default function BudgetTab({ year, canNote }: { year: number; canNote: boolean }) {
  const [target, setTarget] = useState<NoteTarget>(null);
  const [why, setWhy] = useState<{ id: string; title: string } | null>(null);
  const q = useQuery({ queryKey: ['finance', 'budget', year], queryFn: () => financeApi.budget(year), enabled: ENGINE_ENABLED });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Bütçe okunamadı.')}</Note>;
  const d: BudgetView | undefined = q.data;
  if (!d) return null;
  if (!d.plan) {
    return (
      <div className="flex flex-col gap-3">
        <DataEnd data={d} />
        <Note tone="info">{d.mesaj ?? 'Bütçe onaylanmadı.'} Plan <Link to="/butce" className="underline">Bütçe ve hedefler</Link> ekranında hazırlanır ve onaylanır.</Note>
      </div>
    );
  }
  const s = d.sirket;
  const g = d.gider;
  const noteBtn = (anahtar: string, baslik: string, n: FNote | null) => (
    canNote || n ? (
      <button type="button" className={`${btnGhost} !min-h-9 !px-2`} onClick={() => setTarget({ anahtar, baslik, not: n })} aria-label="Sapma açıklaması">
        <MessageSquareText aria-hidden className="h-4 w-4" />{n ? 'Açıklama' : 'Açıkla'}
      </button>
    ) : null
  );
  return (
    <div className="flex flex-col gap-3">
      <DataEnd data={d} extra={<span>Plan: {d.plan.title}{d.plan.decidedBy ? ` · ${d.plan.decidedBy} onayladı, ${fmtDay(d.plan.decidedAt)}` : ''}</span>} />
      <KpiRow>
        <Kpi label="Satış (bugüne beklenen)" value={fmtPct(s?.oran)} help={`Gerçekleşen ${fmtShort(s?.gercekCiro)} / beklenen ${fmtShort(s?.beklenenCiro)}`}
          info={<SqlInfo k={d.kaynaklar} alan="sirket" label="Satış (bugüne beklenen)" />} />
        <Kpi label="Yıllık satış hedefi" value={fmtShort(s?.hedefCiro)} help="Kitap hedefleri + yeni kitap programı"
          info={<SqlInfo k={d.kaynaklar} alan="sirket" label="Yıllık satış hedefi" />} />
        <Kpi label="Gider bütçesi kullanımı" value={fmtPct(g?.kullanim)} help={`Gerçekleşen ${fmtShort(g?.gercek)} / bugüne düşen ${fmtShort(g?.butceDonem)}`}
          info={<SqlInfo k={d.kaynaklar} alan="gider" label="Gider bütçesi kullanımı" />} />
        <Kpi label="Aşan / sınırdaki kalem" value={`${g?.asim ?? 0} / ${g?.yaklasti ?? 0}`} help={`Açık sapma uyarısı: ${d.sapmaToplam ?? 0}`}
          info={<SqlInfo k={d.kaynaklar} alan="gider" label="Aşan / sınırdaki kalem" />} />
      </KpiRow>

      <Panel>
        <h3 className="text-[15px] font-extrabold">Departman × gider hesabı</h3>
        <p className="mb-2 max-w-[80ch] text-[12px] text-canvas-muted">
          Bütçe ve gerçekleşme «Bütçe ve hedefler» ekranının yürürlükteki planından (Logo 7 ile başlayan gider hesapları; yansıtma ve kapanış hariç). En çok aşan en üstte. Kalemin fişleri: Gelir tablosu → satır → hesap.
        </p>
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Departman / hesap</th>
              <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="departmanlar[].yillik">Yıllık bütçe</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="departmanlar[].butceDonem">Bugüne bütçe</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="departmanlar[].gercek">Gerçekleşen</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="departmanlar[].sapma">Sapma</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={d.kaynaklar} alan="departmanlar[].kullanim">Kullanım</InfoLabel></th>
              <th className={th}>Durum</th>
              <th className={th}>Açıklama</th>
            </tr>
          </thead>
          <tbody>
            {(d.departmanlar ?? []).map((r) => {
              const st = (r.durum ?? 'baslamadi') as DeptState;
              return (
                <tr key={r.anahtar} className="border-t border-slate-100">
                  <td className={td}>
                    <div className="font-semibold">{r.merkezAdi ?? r.merkezKodu}</div>
                    <div className="text-[11px] text-canvas-muted"><span className="font-mono">{r.hesap}</span> · {r.hesapAdi}</div>
                    {r.not && <div className="mt-1 max-w-[46ch] text-[11.5px] italic text-canvas-ink">“{r.not.metin}”</div>}
                  </td>
                  <td className={`${td} text-right`}><Money v={r.yillik} /></td>
                  <td className={`${td} text-right`}><Money v={r.butceDonem} /></td>
                  <td className={`${td} text-right`}><Money v={r.gercek} /></td>
                  <td className={`${td} text-right`}><Money v={r.sapma} strong /></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.kullanim)}</td>
                  <td className={td}><span className={`inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-bold ${DEPT[st]?.pill ?? ''}`}>{DEPT[st]?.label ?? st}</span></td>
                  <td className={td}>{noteBtn(r.anahtar, `${r.merkezAdi ?? r.merkezKodu} · ${r.hesapAdi ?? r.hesap}`, r.not)}</td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      </Panel>

      <Panel>
        <h3 className="flex items-center gap-1.5 text-[15px] font-extrabold">Açık sapma uyarıları ({d.sapmaToplam ?? 0})<SqlInfo k={d.kaynaklar} alan="sapmalar[]" label="Açık sapma uyarıları" /></h3>
        {!(d.sapmalar ?? []).length ? <p className="text-[12.5px] text-canvas-muted">Açık uyarı yok.</p> : (
          <ul className="mt-2 flex flex-col gap-1.5">
            {(d.sapmalar ?? []).map((a) => (
              <li key={a.id} className="flex flex-col gap-1 rounded-xl bg-white/80 px-3 py-2 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <div className="text-[12.5px] font-bold">{a.label}</div>
                  <div className="text-[11.5px] text-canvas-muted">
                    {a.kind === 'satis' ? `Beklenenin ${fmtPct(a.ratio)}'i` : `Bütçenin ${fmtPct(a.ratio)}'i`} · beklenen {fmtMoney(a.expected)} · gerçekleşen {fmtMoney(a.actual)}
                  </div>
                  {a.not && <div className="mt-0.5 text-[11.5px] italic">“{a.not.metin}”</div>}
                </div>
                {a.kind === 'satis' && <span className={`inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-bold ${TRACK['sapma' as TrackState].pill}`}>Satış</span>}
                {(a.kind === 'satis' || a.kind === 'gider') && (
                  <button type="button" className={`${btnGhost} !min-h-9 !px-2`} onClick={() => setWhy({ id: a.id, title: a.label ?? a.key })}>
                    <HelpCircle aria-hidden className="h-4 w-4" />Neden?
                  </button>
                )}
                {noteBtn(a.anahtar, a.label ?? a.key, a.not)}
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <NoteSheet target={target} year={year} onClose={() => setTarget(null)} />
      <ReasonSheet target={why} load={reasonApi.finance} onClose={() => setWhy(null)} />
    </div>
  );
}
