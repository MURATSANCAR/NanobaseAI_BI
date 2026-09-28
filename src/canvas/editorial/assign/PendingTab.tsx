import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search, UserPlus } from 'lucide-react';
import type { AssignProject } from '../../engine';
import { useCan } from '../../useAdmin';
import { Note, Pill, errText, field, nf } from '../../admin/ui';
import { crmLabel } from '../../format';
import { Pager, Panel, useDebounced } from '../kit';
import { assignPendingOptions } from '../queries';
import AssignSheet from './AssignSheet';
import { day, projectMeta } from './parts';
import SqlInfo from '../../components/SqlInfo';
import { kaynakOf } from '../../components/kaynakOf';

/** CRM'de editörü boş ve ZEKİ AI'da açık görevi olmayan projeler. Varsayılan süzgeç iş durumundakiler
 *  (iş planı / kurul onaylı); durum çipleriyle diğerleri de açılır. */
export default function PendingTab() {
  const canAssign = useCan('editor-atama.ata');
  const [text, setText] = useState('');
  const [status, setStatus] = useState<number[] | null>(null);
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<AssignProject | null>(null);
  const q = useDebounced(text.trim(), 350);
  // null: ilk açılış (köprünün iş durumu süzgeci); boş seçim: bütün durumlar.
  const statusKey = status === null ? '' : status.length ? status.join('|') : 'hepsi';
  useEffect(() => setPage(0), [q, statusKey]);

  const list = useQuery(assignPendingOptions(q, statusKey, '', page));
  const d = list.data;
  const selected = new Set(status ?? d?.defaultStatuses ?? []);
  const allStatuses = status !== null && status.length === 0;
  const toggle = (code: number) => {
    const next = new Set(selected);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    setStatus([...next].sort());
  };
  const err = errText(list.error, 'Atama bekleyen projeler okunamadı.');

  return (
    <Panel>
      <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
        <h2 className="flex items-center gap-1 text-[13px] font-extrabold">
          Atama bekleyen projeler
          <SqlInfo k={kaynakOf(d)} alan="_hepsi" label="Atama bekleyen projeler" />
        </h2>
        {d && d.onBoard > 0 && <span className="text-[11.5px] text-canvas-muted">{nf.format(d.onBoard)} proje ZEKİ AI'da atanmış, listede yok</span>}
      </div>
      <p className="mt-0.5 px-1 text-[11.5px] leading-snug text-canvas-muted">
        CRM proje kartında «Editörü» boş olan {d ? `${d.sinceYear} ve sonrası ` : ''}etkin projeler.
        {!canAssign && ' Atama yetkiniz yok; listeyi ve adayları görebilirsiniz.'}
      </p>
      {d && (
        <div className="mt-2 flex flex-wrap gap-1.5" role="group" aria-label="Proje durumu">
          {d.statusFacets.map((s) => (
            <button
              key={s.code}
              type="button"
              onClick={() => toggle(s.code)}
              aria-pressed={selected.has(s.code)}
              className={`min-h-9 rounded-full border px-2.5 text-[11.5px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] ${selected.has(s.code) ? 'border-canvas-violet bg-canvas-violet/10 text-canvas-violet' : 'border-slate-200 bg-white text-canvas-ink'}`}
            >
              {crmLabel(s.label)} <span className="font-mono tabular-nums">{nf.format(s.count)}</span>
            </button>
          ))}
          {allStatuses && <span className="self-center text-[11.5px] font-semibold text-canvas-muted">Durum seçilmedi: bütün durumlar</span>}
        </div>
      )}
      <label className="relative mt-2 block">
        <span className="sr-only">Projelerde ara</span>
        <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
        <input type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Proje ya da yazar" className={`${field} pl-9`} />
      </label>
      {err && (
        <div className="mt-2">
          <Note tone="err">{err}</Note>
        </div>
      )}
      <Pager page={page} pageSize={d?.pageSize ?? 50} total={d?.total ?? 0} shown={d?.items.length ?? 0} loading={list.isLoading} fetching={list.isFetching} db={d?.db} onPage={setPage} />
      {!list.isLoading && !err && !d?.items.length && <p className="py-10 text-center text-[12.5px] text-canvas-muted">Bu süzgece uyan editörsüz proje yok.</p>}
      <ul className="mt-3 space-y-2">
        {(d?.items ?? []).map((p) => (
          <li key={p.id} className="flex flex-col gap-2 rounded-2xl border border-slate-100 bg-white/85 p-3 text-[12.5px] sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="break-words font-extrabold leading-snug">{p.name || 'Adsız proje'}</span>
                {p.status && <Pill tone="muted">{crmLabel(p.status)}</Pill>}
              </div>
              <div className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{projectMeta(p)}</div>
              <div className="mt-0.5 text-[11px] text-canvas-muted">Son değişiklik {day(p.modifiedOn)}</div>
            </div>
            <button
              type="button"
              onClick={() => setOpen(p)}
              className="inline-flex min-h-11 shrink-0 items-center justify-center gap-1.5 rounded-xl bg-canvas-violet px-3.5 text-[12.5px] font-extrabold text-white shadow-md transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9"
            >
              <UserPlus aria-hidden className="h-4 w-4" />
              {canAssign ? 'Editör ata' : 'Adayları gör'}
            </button>
          </li>
        ))}
      </ul>
      <AssignSheet project={open} onClose={() => setOpen(null)} canAssign={canAssign} />
    </Panel>
  );
}
