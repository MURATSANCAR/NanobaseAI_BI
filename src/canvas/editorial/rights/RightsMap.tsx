import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, X } from 'lucide-react';
import { toast } from 'sonner';
import { Pill, btnGhost, btnPrimary } from '../../admin/ui';
import { errMsg } from '../contracts/ui';
import { rightsApi, type MapFields, type MapItem, type RightsMap } from '../royalty/api';
import { MAP_ORDER as ORDER, dropItem, isEmptyMap, itemsOf, shown, usesModel } from './rightsMapText';

/** Yapılandırılmış hak haritası (öneri 18): dil, ülke, format, bitiş, münhasırlık — her değer hak açıklamasından birebir
 *  alıntıyla gösterilir; alıntısı olmayan alan boştur. Onay telif uzmanındadır: gereksiz değer çıkarılıp onaylanabilir. */

const LABELS: Record<keyof MapFields, string> = { dil: 'Dil', ulke: 'Ülke / bölge', format: 'Metinde geçen format', bitis: 'Bitiş', munhasirlik: 'Münhasırlık' };
const SOURCE: Record<MapItem['kaynak'], string> = { zeki: 'Zeki AI', kural: 'kurala göre', insan: 'elle' };

export default function RightsMapView({ map, canEdit, compact = false }: { map: RightsMap; canEdit: boolean; compact?: boolean }) {
  const qc = useQueryClient();
  const [fields, setFields] = useState<MapFields>(map.fields);
  const decide = useMutation({
    mutationFn: (action: 'onayla' | 'reddet') => rightsApi.decideMap(map.id, { action, fields: action === 'onayla' ? fields : undefined }),
    onSuccess: (m) => {
      toast.success(m.status === 'onayli' ? 'Hak haritası onaylandı.' : 'Hak haritası reddedildi.');
      qc.invalidateQueries({ queryKey: ['rights'] });
    },
    onError: (e) => toast.error(errMsg(e) ?? 'Kaydedilemedi.'),
  });
  const open = map.status === 'oneri' && canEdit;
  const drop = (k: keyof MapFields, i: number) => setFields((f) => dropItem(f, k, i));
  const empty = isEmptyMap(fields);
  const zeki = usesModel(fields);

  return (
    <div className="rounded-xl border border-slate-100 bg-white/70 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
        <span className="font-extrabold uppercase tracking-wide text-canvas-muted">Hak haritası</span>
        <Pill tone={map.status === 'onayli' ? 'ok' : map.status === 'reddedildi' ? 'muted' : zeki ? 'violet' : 'warn'}>
          {map.status === 'oneri' ? (zeki ? 'Zeki AI önerisi' : 'Kurala göre öneri') : map.statusLabel}
        </Pill>
        {map.status !== 'oneri' && map.approvedBy && <span className="text-canvas-muted">{map.approvedBy}</span>}
        {map.dropped > 0 && <span className="text-canvas-muted">{map.dropped} değer metinde alıntısı bulunmadığı için atıldı</span>}
      </div>
      {empty ? (
        <p className="mt-1 text-[12px] text-canvas-muted">Açıklamada dil, ülke, format, bitiş ya da münhasırlık alıntısı bulunamadı.</p>
      ) : (
        <dl className="mt-1.5 grid gap-1.5">
          {ORDER.map((k) => {
            const list = itemsOf(fields, k);
            if (!list.length) return null;
            return (
              <div key={k} className="grid gap-0.5 sm:grid-cols-[8.5rem_1fr] sm:gap-2">
                <dt className="text-[11.5px] font-bold text-canvas-muted">{LABELS[k]}</dt>
                <dd className="flex min-w-0 flex-col gap-1">
                  {list.map((x, i) => (
                    <div key={`${x.deger}-${i}`} className="min-w-0 text-[12.5px]">
                      <span className="inline-flex flex-wrap items-center gap-1.5">
                        <b>{shown(x)}</b>
                        <span className="text-[11px] text-canvas-muted">{SOURCE[x.kaynak]}</span>
                        {open && (
                          <button type="button" aria-label={`${shown(x)} değerini çıkar`} onClick={() => drop(k, i)}
                            className="grid h-11 w-11 place-items-center rounded-lg text-canvas-muted transition-transform duration-150 ease-out hover:bg-slate-100 active:scale-[0.97] sm:h-6 sm:w-6">
                            <X aria-hidden className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </span>
                      {!compact && x.alinti && <q className="block break-words text-[11.5px] italic text-canvas-muted">{x.alinti}</q>}
                    </div>
                  ))}
                </dd>
              </div>
            );
          })}
        </dl>
      )}
      {open && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <button type="button" className={btnPrimary} disabled={decide.isPending || empty} onClick={() => decide.mutate('onayla')}>
            <Check aria-hidden className="h-4 w-4" /> Haritayı onayla
          </button>
          <button type="button" className={btnGhost} disabled={decide.isPending} onClick={() => decide.mutate('reddet')}>
            Reddet
          </button>
        </div>
      )}
    </div>
  );
}
