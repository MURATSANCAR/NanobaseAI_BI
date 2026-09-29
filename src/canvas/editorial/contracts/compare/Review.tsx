import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, CircleDot, Flag } from 'lucide-react';
import { Note, btnGhost, btnPrimary, field } from '../../../admin/ui';
import { Field, Sheet, errMsg, stamp } from '../ui';
import { compareApi, type Review, type ReviewStatus } from './api';

/** Bulgu incelemesi: rozet (durum, eski değere ait mi) ve işaretleme kartı. Kayıt portalda; CRM'e yazılmaz. */

export const REVIEW_LABEL: Record<ReviewStatus, string> = {
  uygun: 'İncelendi, uygun',
  istisna: 'Bilinçli istisna',
  'crm-duzelt': "CRM'de düzeltilmeli",
  hukuk: 'Hukuka sorulacak',
};

export function ReviewBadge({ r }: { r: Review | null | undefined }) {
  if (!r) return null;
  const closed = !r.open;
  const Icon = closed ? CheckCircle2 : r.stale ? CircleDot : Flag;
  const tone = closed ? 'bg-emerald-50 text-emerald-800' : r.stale ? 'bg-slate-100 text-slate-600' : 'bg-amber-50 text-amber-900';
  return (
    <span className={`inline-flex max-w-full items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold ${tone}`}
      title={[r.note, r.owner ? `Sorumlu: ${r.owner}` : null, r.by ? `${r.by} · ${stamp(r.at)}` : null].filter(Boolean).join(' — ')}>
      <Icon aria-hidden className="h-3 w-3 shrink-0" />
      <span className="truncate">{r.stale ? `${r.statusLabel} (eski değere ait)` : r.statusLabel}</span>
    </span>
  );
}

export function ReviewButton({ contractKey, clause, title, value, current, can }: {
  contractKey: string;
  clause: string;
  title: string;
  value: string;
  current: Review | null | undefined;
  can: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (!can) return <ReviewBadge r={current} />;
  return (
    <>
      <span className="inline-flex flex-wrap items-center gap-1.5">
        <ReviewBadge r={current} />
        <button type="button" onClick={() => setOpen(true)}
          className="inline-flex min-h-11 items-center rounded-lg px-2 text-[11.5px] font-bold text-canvas-violet transition-transform duration-150 ease-out hover:bg-violet-50 active:scale-[0.97] sm:min-h-7">
          {current ? 'İncelemeyi değiştir' : 'İşaretle'}
        </button>
      </span>
      {open && <ReviewSheet contractKey={contractKey} clause={clause} title={title} value={value} current={current} onClose={() => setOpen(false)} />}
    </>
  );
}

function ReviewSheet({ contractKey, clause, title, value, current, onClose }: {
  contractKey: string;
  clause: string;
  title: string;
  value: string;
  current: Review | null | undefined;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<ReviewStatus>(current?.status ?? 'uygun');
  const [note, setNote] = useState(current?.note ?? '');
  const [owner, setOwner] = useState(current?.owner ?? '');
  const done = () => {
    qc.invalidateQueries({ queryKey: ['contracts', 'compare'] });
    onClose();
  };
  const save = useMutation({ mutationFn: () => compareApi.reviewSave({ key: contractKey, clause, status, note, owner }), onSuccess: done });
  const remove = useMutation({ mutationFn: () => compareApi.reviewDelete(contractKey, clause), onSuccess: done });
  const needsWho = (status === 'crm-duzelt' || status === 'hukuk') && !note.trim() && !owner.trim();
  return (
    <Sheet
      title={`İncele: ${title}`}
      onClose={onClose}
      footer={
        <>
          {current && (
            <button type="button" className={btnGhost} disabled={remove.isPending} onClick={() => remove.mutate()}>İncelemeyi kaldır</button>
          )}
          <button type="button" className={btnGhost} onClick={onClose}>Vazgeç</button>
          <button type="button" className={btnPrimary} disabled={save.isPending || needsWho} onClick={() => save.mutate()}>Kaydet</button>
        </>
      }
    >
      <p className="text-[12.5px]">
        <span className="text-canvas-muted">Bu sözleşmedeki değer: </span>
        <span className="font-bold">{value}</span>
      </p>
      <p className="mt-1 text-[11.5px] text-canvas-muted">İnceleme bu değere bağlanır. CRM'de değer değişirse inceleme «eski değere ait» olur ve bulgu yeniden açılır.</p>
      <fieldset className="mt-3 grid gap-1.5 sm:grid-cols-2">
        <legend className="sr-only">Durum</legend>
        {(Object.keys(REVIEW_LABEL) as ReviewStatus[]).map((k) => (
          <label key={k} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 text-[12.5px] font-bold ${status === k ? 'border-canvas-violet bg-violet-50' : 'border-slate-200 bg-white'}`}>
            <input type="radio" name="durum" className="accent-canvas-violet" checked={status === k} onChange={() => setStatus(k)} />
            {REVIEW_LABEL[k]}
          </label>
        ))}
      </fieldset>
      <div className="mt-3 grid gap-3">
        <Field label="Not" hint="Neden uygun ya da ne yapılmalı; ör. «çok satan yazar, yayın kurulu onaylı».">
          <textarea className={`${field} min-h-24`} value={note} maxLength={2000} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <Field label="Sorumlu" hint="Açık kalan iş için kim bakacak (kişi ya da birim).">
          <input className={field} value={owner} maxLength={120} onChange={(e) => setOwner(e.target.value)} />
        </Field>
      </div>
      {needsWho && <p className="mt-2 text-[11.5px] font-semibold text-amber-800">Açık kalan inceleme için not ya da sorumlu yazın.</p>}
      {(save.error || remove.error) && <div className="mt-2"><Note tone="err">{errMsg(save.error || remove.error)}</Note></div>}
    </Sheet>
  );
}
