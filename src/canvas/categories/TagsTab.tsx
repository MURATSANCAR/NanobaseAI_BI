import { useState } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ENGINE_ENABLED } from '../engine';
import { Note, btnGhost, btnPrimary, errText, field, fmtDate, label as labelCls } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { categoriesApi, fmtInt } from './api';
import { useMeta } from './parts';

/** Etiket sözlüğü: CRM anahtar kelimeleri (CRM'de yönetilir) + editörlerin yazdığı yeni etiket önerileri (burada
 *  onaylanır, reddedilir ya da var olan etikete birleştirilir). Zeki AI sözlük dışı etiket üretmez. */
const STATUS = [
  { key: 'oneri', label: 'Onay bekleyen' },
  { key: 'aktif', label: 'Sözlükte' },
  { key: 'red', label: 'Reddedilen' },
  { key: 'birlesti', label: 'Birleştirilen' },
];

export default function TagsTab() {
  const qc = useQueryClient();
  const meta = useMeta();
  const can = !!meta.data?.me.canEditTree;
  const [status, setStatus] = useState('oneri');
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const dq = useDebounced(q, 300);
  const list = useQuery({ queryKey: ['categories', 'tags', status, dq, page], queryFn: () => categoriesApi.tags({ status, q: dq, page }), enabled: ENGINE_ENABLED, placeholderData: keepPreviousData });
  const [merge, setMerge] = useState<Record<string, string>>({});
  const act = useMutation({
    mutationFn: ({ tag, s, into }: { tag: string; s: 'aktif' | 'red' | 'birlesti'; into?: string }) => categoriesApi.decideTag(tag, s, into),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['categories', 'tags'] }); qc.invalidateQueries({ queryKey: ['categories', 'options'] }); toast.success('Etiket kararı kaydedildi.'); },
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const counts = list.data?.counts ?? {};
  return (
    <Panel>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div className="-mx-1 overflow-x-auto px-1">
          <div className="flex w-max gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Etiket durumu">
            {STATUS.map((s) => (
              <button key={s.key} type="button" role="tab" aria-selected={status === s.key} onClick={() => { setStatus(s.key); setPage(0); }}
                className={`inline-flex min-h-11 items-center gap-1 rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${status === s.key ? 'bg-canvas-violet text-white' : 'hover:bg-white/70'}`}>
                {s.label} <span className="font-mono text-[11px] tabular-nums opacity-80">{fmtInt(counts[s.key] ?? 0)}</span>
              </button>
            ))}
          </div>
        </div>
        <label className="flex flex-col gap-1 sm:w-72">
          <span className={labelCls}>Ara</span>
          <input className={field} value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
        </label>
      </div>
      {list.error && <div className="mt-3"><Note tone="err">{errText(list.error, 'Liste açılamadı.')}</Note></div>}
      <ul className="mt-3 flex flex-col gap-1.5">
        {(list.data?.items ?? []).map((t) => (
          <li key={t.tag} className="flex flex-col gap-2 rounded-2xl border border-slate-100 bg-white/80 px-3 py-2 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="truncate text-[13px] font-extrabold">{t.tag}</div>
              <div className="text-[11.5px] text-canvas-muted">
                {t.source === 'crm_anahtarkelime' ? `CRM anahtar kelimesi · ${fmtInt(t.books)} kitapta` : `${t.createdBy ?? '—'} önerdi · ${fmtDate(t.createdAt)}`}
                {t.mergedInto && ` · → ${t.mergedInto}`}
              </div>
            </div>
            {can && t.status === 'oneri' && (
              <div className="flex flex-wrap items-center gap-1.5">
                <button type="button" className={`${btnPrimary} !min-h-9`} disabled={act.isPending} onClick={() => act.mutate({ tag: t.tag, s: 'aktif' })}>Sözlüğe al</button>
                <button type="button" className={`${btnGhost} !min-h-9`} disabled={act.isPending} onClick={() => act.mutate({ tag: t.tag, s: 'red' })}>Reddet</button>
                <input className={`${field} !w-40`} placeholder="Birleştir: etiket" aria-label={`${t.tag} etiketini birleştir`} value={merge[t.tag] ?? ''}
                  onChange={(e) => setMerge({ ...merge, [t.tag]: e.target.value })} />
                <button type="button" className={`${btnGhost} !min-h-9`} disabled={act.isPending || !(merge[t.tag] ?? '').trim()}
                  onClick={() => act.mutate({ tag: t.tag, s: 'birlesti', into: merge[t.tag].trim() })}>Birleştir</button>
              </div>
            )}
          </li>
        ))}
      </ul>
      {list.data && !list.data.total && <p className="mt-3 text-[12.5px] text-canvas-muted">Kayıt yok.</p>}
      <Pager page={page} pageSize={list.data?.pageSize ?? 100} total={list.data?.total ?? 0} shown={list.data?.items.length ?? 0}
        loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
    </Panel>
  );
}
