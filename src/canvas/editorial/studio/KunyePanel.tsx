import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { studioApi, type StudioJob } from '../../engine';
import { Note, errText } from '../../admin/ui';
import { Panel } from '../kit';
import { gradientBtn } from './shared';

/** Künye: sistem kitabın kendi künyesinden (alıntıyla) doldurur; kaynağı olmayan alan «—» kalır ve ön baskı
 *  denetimi durur. Editör eksik ya da değişecek alanı burada yazar; kaydedince iç sayfa yeniden dizilir. */
export default function KunyePanel({ jobId, front }: { jobId: string; front: NonNullable<StudioJob['front']> }) {
  const qc = useQueryClient();
  const [edit, setEdit] = useState<Record<string, string>>({});
  useEffect(() => setEdit({}), [front]);
  const save = useMutation({
    mutationFn: () => studioApi.kunye(jobId, edit),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['studio', 'job', jobId] }),
  });
  const missing = front.rows.filter((r) => r.missing).length;
  const dirty = Object.keys(edit).length > 0;

  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-[15px] font-extrabold">Künye</h2>
        <span className={`text-[12px] font-bold ${missing ? 'text-amber-700' : 'text-emerald-700'}`}>
          {missing ? `${missing} alan eksik` : 'Tam'}
        </span>
      </div>
      <p className="text-[11.5px] text-canvas-muted">Kitabın kendi künyesinden alındı; kaynağı olmayan alanı siz yazın. Resim ve tasarım satırları sistemindir.</p>
      {save.error && <Note tone="err">{errText(save.error, 'Künye kaydedilemedi.')}</Note>}
      <dl className="mt-2 grid gap-1.5">
        {front.rows.map((r) => (
          <div key={r.label} className={`grid grid-cols-[130px_1fr] items-center gap-2 rounded-xl px-2.5 py-1.5 ${r.missing ? 'bg-amber-50/80' : 'bg-white/70'}`}>
            <dt className="text-[11.5px] font-bold text-canvas-muted">{r.label}</dt>
            <dd className="min-w-0">
              {r.editable ? (
                <input
                  value={edit[r.label] ?? (r.missing ? '' : r.value)}
                  placeholder={r.missing ? 'Eksik — yazın' : ''}
                  onChange={(e) => setEdit((x) => ({ ...x, [r.label]: e.target.value }))}
                  aria-label={r.label}
                  className="w-full rounded-lg border border-transparent bg-transparent px-1.5 py-0.5 text-[12.5px] outline-none focus:border-canvas-violet focus:bg-white"
                />
              ) : (
                <span className="block truncate px-1.5 text-[12.5px]">{r.value}</span>
              )}
              {r.source && !r.missing && <span className="block px-1.5 text-[10.5px] text-canvas-muted">{r.source}</span>}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 flex justify-end">
        <button type="button" className={gradientBtn} disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
          {save.isPending ? 'Kaydediliyor…' : 'Künyeyi kaydet'}
        </button>
      </div>
    </Panel>
  );
}
