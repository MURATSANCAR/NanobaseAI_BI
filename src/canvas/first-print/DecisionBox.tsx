import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label } from '../admin/ui';
import { firstPrintApi, fmtUnits, type Decision, type Forecast } from './api';
import SqlInfo from '../components/SqlInfo';

/** İlk baskı kararı: adet seçilir, karar kaydedilir; satış ve üretim onayı iki ayrı kişiden gelir. Onaylanan karar
 *  üretim modülünün okuyacağı kayıttır (CRM'e ve Logo'ya yazılmaz). */

const STATUS: Record<Decision['status'], { label: string; tone: 'ok' | 'warn' | 'muted' }> = {
  bekliyor: { label: 'Onay bekliyor', tone: 'warn' },
  onaylandi: { label: 'Onaylandı', tone: 'ok' },
  geri_cekildi: { label: 'Geri çekildi', tone: 'muted' },
};
const fmtAt = (iso: string) => new Date(iso).toLocaleString('tr-TR', { timeZone: 'Europe/Istanbul', dateStyle: 'medium', timeStyle: 'short' });

export default function DecisionBox({ fc, can }: { fc: Forecast; can?: { decide: boolean; approve: boolean } }) {
  const qc = useQueryClient();
  const code = fc.book.code;
  const key = ['first-print', 'decisions', code];
  const list = useQuery({ queryKey: key, queryFn: () => firstPrintApi.decisions(code), enabled: ENGINE_ENABLED });
  const [units, setUnits] = useState(String(fc.recommendation.units));
  const [note, setNote] = useState('');
  const done = () => qc.invalidateQueries({ queryKey: key });
  const create = useMutation({
    mutationFn: () => {
      const n = Number(units.replace(/\./g, ''));
      const sc = fc.horizons['6'].scenarios.find((s) => s.units === n);
      return firstPrintApi.decide({
        code, title: fc.book.name, launch: fc.launch, units: n, recommended: fc.recommendation.units,
        scenario: n === fc.recommendation.units ? 'oneri' : sc ? sc.id : 'elle', note: note.trim() || undefined,
        forecast: { six: fc.horizons['6'].scenarios, twelve: fc.horizons['12']?.scenarios, band6: fc.horizons['6'].band, tier: fc.horizons['6'].tier, stockout6: fc.recommendation.stockout6 },
      });
    },
    onSuccess: () => { setNote(''); void done(); },
  });
  const approve = useMutation({ mutationFn: (v: { id: string; role: 'satis' | 'uretim' }) => firstPrintApi.approve(v.id, v.role), onSuccess: done });
  const withdraw = useMutation({ mutationFn: (id: string) => firstPrintApi.withdraw(id), onSuccess: done });
  const items = list.data?.items ?? [];
  const open = items.find((d) => d.status === 'bekliyor');
  const err = errText(create.error ?? approve.error ?? withdraw.error, 'İşlem yapılamadı.');
  if (fc.mode === 'launched' && items.length === 0) return null;

  return (
    <div className="mt-4 border-t border-slate-100 pt-3">
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Karar ve onay</div>
      {err && <div className="mt-2"><Note tone="err">{err}</Note></div>}
      {items.map((d) => (
        <div key={d.id} className="mt-2 rounded-xl border border-slate-100 bg-white/70 p-3 text-[12.5px]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="inline-flex items-center gap-1 font-mono text-[16px] font-bold tabular-nums">{fmtUnits(d.units)} adet<SqlInfo k={list.data?.kaynaklar} alan="items[]" label="Karar kaydı" /></span>
            <Pill tone={STATUS[d.status].tone}>{STATUS[d.status].label}</Pill>
          </div>
          <div className="mt-1 text-canvas-muted">Öneren {d.createdBy} · {fmtAt(d.createdAt)}{d.recommended && d.recommended !== d.units ? ` · öneri ${fmtUnits(d.recommended)}` : ''}</div>
          {d.note && <p className="mt-1">{d.note}</p>}
          <ul className="mt-2 space-y-1">
            {(['satis', 'uretim'] as const).map((role) => {
              const a = d.approvals[role];
              return (
                <li key={role} className="flex flex-wrap items-center justify-between gap-2">
                  <span>{role === 'satis' ? 'Satış onayı' : 'Üretim onayı'}</span>
                  {a ? (
                    <span className="text-canvas-muted">{a.by} · {fmtAt(a.at)}</span>
                  ) : d.status === 'bekliyor' && can?.approve ? (
                    <button type="button" className={btnGhost} disabled={approve.isPending} onClick={() => approve.mutate({ id: d.id, role })}>
                      Onayla
                    </button>
                  ) : (
                    <span className="text-canvas-muted">bekliyor</span>
                  )}
                </li>
              );
            })}
          </ul>
          {d.status === 'bekliyor' && (
            <button type="button" className={`${btnGhost} mt-2`} disabled={withdraw.isPending} onClick={() => withdraw.mutate(d.id)}>
              Geri çek
            </button>
          )}
        </div>
      ))}
      {!open && fc.mode === 'upcoming' && can?.decide && (
        <form
          className="mt-2 flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <label className="flex flex-col gap-1">
            <span className={label}>İlk baskı adedi</span>
            <input className={field} inputMode="numeric" value={units} onChange={(e) => setUnits(e.target.value.replace(/[^\d.]/g, ''))} />
          </label>
          <label className="flex flex-col gap-1">
            <span className={label}>Not (isteğe bağlı)</span>
            <textarea className={`${field} min-h-16`} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Ör. fuar dönemi için yüksek tutuldu" />
          </label>
          <button type="submit" className={btnPrimary} disabled={create.isPending || !Number(units.replace(/\./g, ''))}>
            Karar olarak kaydet ve onaya gönder
          </button>
        </form>
      )}
      {!open && fc.mode === 'upcoming' && can && !can.decide && items.length === 0 && (
        <p className="mt-2 text-[12px] text-canvas-muted">Karar kaydı için «İlk baskı kararı» yetkisi gerekir.</p>
      )}
    </div>
  );
}
