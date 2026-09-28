import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Plus, Trash2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label as labelCls } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { fmtDay, tendersApi, type CheckItem, type CheckState, type TenderDetail, type TenderMeta } from './api';

/** Belge kontrol listesi: şartname özetinden gelen ve elle eklenen kalemler, arşivdeki belgeye bağlama, geçerlilik.
 *  Belge bağlanınca kalem «var» olur; geçerliliği geçmiş belge «süresi dolmuş» görünür ve puana «yok» sayılır. */

const TONE: Record<CheckState, 'ok' | 'warn' | 'err'> = { var: 'ok', eksik: 'warn', gecersiz: 'err' };

export default function TenderChecklist({ d, meta }: { d: TenderDetail; meta: TenderMeta }) {
  const qc = useQueryClient();
  const docs = useQuery({ queryKey: ['tenders', 'documents'], queryFn: tendersApi.documents, enabled: ENGINE_ENABLED });
  const [newItem, setNewItem] = useState('');
  const can = meta.me.canEdit;
  const save = useMutation({
    mutationFn: (items: Array<Partial<CheckItem> & { sil?: boolean }>) => tendersApi.updateChecklist(d.id, items),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tenders'] }),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const items = d.kontrolListesi;
  const missing = items.filter((c) => c.zorunlu && c.durum !== 'var').length;
  return (
    <Panel>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[16px] font-extrabold tracking-tight">Belge kontrol listesi</h2>
          <p className="max-w-[90ch] text-[12px] text-canvas-muted">
            Şartname özetindeki belgeler kendiliğinden eklenir ve arşivde geçerli aynı türden belge varsa bağlanır. Liste taslaktır; ihale sorumlusu şartnameyle karşılaştırıp onaylar.
          </p>
        </div>
        <Pill tone={missing ? 'warn' : 'ok'}>{missing ? `${missing} zorunlu belge eksik` : 'Zorunlu belgeler tamam'}</Pill>
      </div>
      {docs.error && <div className="mt-2"><Note tone="err">{errText(docs.error, 'Belge arşivi okunamadı.')}</Note></div>}
      <ul className="mt-3 flex flex-col gap-1.5">
        {!items.length && <li className="text-[12.5px] text-canvas-muted">Liste boş. Şartnameden Zeki AI özeti çıkarın ya da kalem ekleyin.</li>}
        {items.map((c) => (
          <li key={c.id} className="grid grid-cols-1 gap-2 rounded-xl border border-slate-100 bg-white/80 px-3 py-2 lg:grid-cols-[minmax(0,1fr)_150px_minmax(0,220px)_150px_auto] lg:items-center">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill tone={TONE[c.durum]}>{c.durumAdi}</Pill>
                {!c.zorunlu && <Pill tone="muted">İsteğe bağlı</Pill>}
                {c.belgeTuruAdi && <span className="text-[11px] font-semibold text-canvas-muted">{c.belgeTuruAdi}</span>}
              </div>
              <div className="mt-0.5 break-words text-[12.5px] font-semibold">{c.kalem}</div>
              {c.kaynakCumle && <q className="block break-words text-[11px] italic text-canvas-muted">{c.kaynakCumle}</q>}
            </div>
            {can ? (
              <>
                <label className="flex flex-col gap-0.5">
                  <span className={labelCls}>Durum</span>
                  <select className={field} value={c.durum} disabled={save.isPending} onChange={(e) => save.mutate([{ id: c.id, durum: e.target.value as CheckState }])}>
                    {Object.entries(meta.kontrolDurumlari).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </label>
                <label className="flex min-w-0 flex-col gap-0.5">
                  <span className={labelCls}>Arşivdeki belge</span>
                  <select className={field} value={c.belgeId ?? ''} disabled={save.isPending} onChange={(e) => save.mutate([{ id: c.id, belgeId: e.target.value || null }])}>
                    <option value="">Bağlı değil</option>
                    {(docs.data?.items ?? []).map((x) => <option key={x.id} value={x.id}>{x.ad}{x.gecerlilik ? ` (${fmtDay(x.gecerlilik)})` : ''}</option>)}
                  </select>
                </label>
                <label className="flex flex-col gap-0.5">
                  <span className={labelCls}>Geçerlilik</span>
                  <input className={field} type="date" defaultValue={c.gecerlilik ?? ''} disabled={save.isPending}
                    onBlur={(e) => { if ((e.target.value || null) !== (c.gecerlilik ?? null)) save.mutate([{ id: c.id, gecerlilik: e.target.value || null }]); }} />
                </label>
                <div className="flex gap-1.5 lg:justify-end">
                  <button type="button" className={btnGhost} disabled={save.isPending} onClick={() => save.mutate([{ id: c.id, zorunlu: !c.zorunlu }])}>
                    {c.zorunlu ? 'İsteğe bağlı yap' : 'Zorunlu yap'}
                  </button>
                  <button type="button" className={btnGhost} aria-label={`${c.kalem} kalemini sil`} disabled={save.isPending} onClick={() => save.mutate([{ id: c.id, sil: true }])}>
                    <Trash2 aria-hidden className="h-4 w-4" />
                  </button>
                </div>
              </>
            ) : (
              <div className="text-[12px] text-canvas-muted lg:col-span-4">{c.belgeAdi ?? 'Belge bağlı değil'}{c.gecerlilik ? ` · ${fmtDay(c.gecerlilik)}` : ''}</div>
            )}
          </li>
        ))}
      </ul>
      {can && (
        <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className={labelCls}>Yeni kalem</span>
            <input className={field} value={newItem} onChange={(e) => setNewItem(e.target.value)} placeholder="Örn. Yayınevi yetki belgesi" />
          </label>
          <button
            type="button"
            className={btnPrimary}
            disabled={!newItem.trim() || save.isPending}
            onClick={() => save.mutate([{ kalem: newItem.trim(), zorunlu: true }], { onSuccess: () => setNewItem('') })}
          >
            {save.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Plus aria-hidden className="h-4 w-4" />}
            Ekle
          </button>
        </div>
      )}
    </Panel>
  );
}
