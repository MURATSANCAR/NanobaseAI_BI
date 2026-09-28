import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, btnGhost, errText } from '../admin/ui';
import { fmtDay, istanbulToday } from '../field/api';
import { Empty } from '../field/parts';
import { dealersApi, type Action, type DealersMeta } from './api';

/** Aksiyonlar: bayi kartından açılan ziyaret/arama/limit işleri. BMT kendi carilerinin ve kendine atananların aksiyonlarını
 *  görür; bütün bayileri gören herkesinkini. */

export default function ActionsTab({ meta }: { meta: DealersMeta }) {
  const [durum, setDurum] = useState('acik');
  const [mine, setMine] = useState(!meta.me.canAll);
  const q = useQuery({
    queryKey: ['dealers', 'actions', durum, mine],
    queryFn: () => dealersApi.actions({ durum, sahip: mine ? meta.me.username : '' }),
    enabled: ENGINE_ENABLED,
  });
  const err = errText(q.error, 'Aksiyonlar okunamadı.');
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {[
          ['acik', 'Açık'],
          ['yapildi', 'Yapıldı'],
          ['iptal', 'İptal'],
        ].map(([k, v]) => (
          <button
            key={k}
            type="button"
            aria-pressed={durum === k}
            onClick={() => setDurum(k)}
            className={`min-h-10 rounded-xl px-3 text-[12px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] ${
              durum === k ? 'bg-canvas-violet text-white shadow-md' : 'bg-slate-100 text-canvas-ink'
            }`}
          >
            {v}
          </button>
        ))}
        {meta.me.canAll && (
          <label className="ml-auto inline-flex min-h-10 items-center gap-2 text-[12px] font-bold">
            <input type="checkbox" className="h-4 w-4" checked={mine} onChange={(e) => setMine(e.target.checked)} />
            Yalnız bana atananlar
          </label>
        )}
      </div>
      {q.isLoading ? (
        <Loading />
      ) : err ? (
        <Note tone="err">{err}</Note>
      ) : (q.data?.items ?? []).length === 0 ? (
        <Empty>Bu durumda aksiyon yok. Aksiyon bayi kartından açılır.</Empty>
      ) : (
        <ul className="flex flex-col gap-2">
          {q.data!.items.map((a) => (
            <ActionItem key={a.id} a={a} meta={meta} />
          ))}
        </ul>
      )}
    </div>
  );
}

export function ActionItem({ a, meta, compact }: { a: Action; meta: DealersMeta; compact?: boolean }) {
  const qc = useQueryClient();
  const upd = useMutation({
    mutationFn: (durum: string) => dealersApi.updateAction(a.id, { durum }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['dealers'] }),
    onError: (e) => toast.error(errText(e, 'Aksiyon güncellenemedi.') ?? 'Aksiyon güncellenemedi.'),
  });
  const late = a.durum === 'acik' && a.termin && a.termin < istanbulToday();
  const mineOrOpener = meta.me.username === a.sahip || meta.me.username === a.olusturan || meta.me.canAll;
  return (
    <li className="rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {!compact && (
            <Link to={`/bayi-risk/${encodeURIComponent(a.code)}`} className="block truncate text-[13.5px] font-extrabold hover:underline">
              {a.unvan || a.code}
            </Link>
          )}
          <div className="text-[12px]">
            <span className="font-bold">{a.turAd}</span>
            <span className="text-canvas-muted"> · {a.sahip}{a.termin ? ` · termin ${fmtDay(a.termin)}` : ''}</span>
          </div>
        </div>
        <Pill tone={late ? 'err' : a.durum === 'yapildi' ? 'ok' : a.durum === 'iptal' ? 'muted' : 'warn'}>{late ? 'Gecikti' : a.durumAd}</Pill>
      </div>
      {a.notu && <p className="mt-1.5 text-[12px] leading-snug">{a.notu}</p>}
      {a.durum === 'acik' && meta.me.canAction && mineOrOpener && (
        <div className="mt-2 flex justify-end gap-2">
          <button type="button" className={btnGhost} disabled={upd.isPending} onClick={() => upd.mutate('iptal')}>
            İptal
          </button>
          <button type="button" className={btnGhost} disabled={upd.isPending} onClick={() => upd.mutate('yapildi')}>
            Yapıldı
          </button>
        </div>
      )}
    </li>
  );
}
