import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, btnGhost, btnPrimary, errText, field } from '../../admin/ui';
import type { Plan } from '../api';
import { Block } from '../parts';
import { blApi, type PlanBook } from './api';

const ROLES: Record<string, string> = { ana: 'Ana kitap', set: 'Set / paket', capraz: 'Çapraz satış' };

/** Backlist planının kitapları (plan ekranının ilk sekmesi). Taslakta rol değiştirilir ya da kitap çıkarılır; yeni kitap
 *  Backlist listesinden seçilip ayrı planla eklenir. */
export default function PlanBooks({ plan, editable }: { plan: Plan; editable: boolean }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['bl', 'plan-books', plan.id, plan.surum], queryFn: () => blApi.planBooks(plan.id), enabled: ENGINE_ENABLED });
  const [rows, setRows] = useState<PlanBook[]>([]);
  useEffect(() => setRows(q.data?.items ?? []), [q.data]);
  const dirty = JSON.stringify(rows.map((r) => [r.stokKodu, r.rol])) !== JSON.stringify((q.data?.items ?? []).map((r) => [r.stokKodu, r.rol]));
  const save = useMutation({
    mutationFn: () => blApi.savePlanBooks(plan.id, rows.map((r) => ({ stokKodu: r.stokKodu, rol: r.rol }))),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bl'] });
      qc.invalidateQueries({ queryKey: ['mkt', 'plan', plan.id] });
      toast.success('Kitap listesi kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });

  return (
    <Block title="Plandaki kitaplar" help="Her kitabın neden bu planda olduğu fırsat bileşenlerinden yazılır. Onaylı planın listesi değişmez; «Revize et» yeni sürüm açar.">
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Kitaplar açılamadı.')}</Note>}
      <ul className="flex flex-col divide-y divide-slate-100 text-[12.5px]">
        {rows.map((b, i) => (
          <li key={b.stokKodu} className="flex flex-wrap items-center gap-2 py-2">
            <div className="min-w-0 flex-1">
              <div className="font-bold">{b.ad ?? b.stokKodu} <span className="font-normal text-canvas-muted">· {b.stokKodu}</span></div>
              {b.gerekce && <div className="text-[11.5px] text-canvas-muted">{b.gerekce}</div>}
            </div>
            {editable ? (
              <>
                <select aria-label="Rol" className={`${field} w-auto`} value={b.rol}
                  onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, rol: e.target.value } : x)))}>
                  {Object.entries(ROLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
                <button type="button" className={btnGhost} disabled={rows.length <= 1} onClick={() => setRows(rows.filter((_, j) => j !== i))}>Çıkar</button>
              </>
            ) : (
              <span className="text-canvas-muted">{b.rolAdi}</span>
            )}
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap justify-between gap-2">
        <Link className={btnGhost} to="/pazarlama/backlist">Backlist listesine dön</Link>
        {editable && dirty && (
          <div className="flex gap-2">
            <button type="button" className={btnGhost} onClick={() => setRows(q.data?.items ?? [])}>Geri al</button>
            <button type="button" className={btnPrimary} disabled={save.isPending} onClick={() => save.mutate()}>Kaydet</button>
          </div>
        )}
      </div>
    </Block>
  );
}
