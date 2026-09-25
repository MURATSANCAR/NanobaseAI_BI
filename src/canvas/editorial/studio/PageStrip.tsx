import { useState } from 'react';
import {
  DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, arrayMove, rectSortingStrategy, sortableKeyboardCoordinates, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { AlertTriangle, GripVertical, Plus, Trash2 } from 'lucide-react';
import type { Plan, PlanPage } from '../../engine';
import { ConfirmDialog } from './dialogs';

/** Sayfa şeridi: küçük önizlemeler, sürükleyerek sıralama (masaüstü; klavyeyle de: tutamağa odaklanıp
 *  boşluk + ok tuşları), araya boş sayfa ekleme, onaylı silme ve 8'in katı uyarısı. Telefonda şerit yatay
 *  kayar; sıralama sağ paneldeki «öne/arkaya al» düğmeleriyle yapılır. */

const EASE = 'cubic-bezier(0.23, 1, 0.32, 1)';
const reduceMotion = () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

export default function PageStrip({
  plan, current, onSelect, onReorder, onAdd, onDelete, thumb, pendingIds, interactive,
}: {
  plan: Plan;
  current: string | null;
  onSelect: (id: string) => void;
  onReorder: (ids: string[]) => void;
  onAdd: (after: string | null) => void;
  onDelete: (id: string) => void;
  thumb: (p: PlanPage) => string | null;
  pendingIds: Set<string>;
  interactive: boolean;
}) {
  const [ask, setAsk] = useState<{ id: string; no: number } | null>(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const ids = plan.pages.map((p) => p.id);
  const eight = plan.warnings.find((w) => /8'?in kat/i.test(w));

  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const from = ids.indexOf(String(e.active.id));
    const to = ids.indexOf(String(e.over.id));
    if (from >= 0 && to >= 0) onReorder(arrayMove(ids, from, to));
  };

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Sayfalar · {plan.pages.length}</span>
        <button type="button" onClick={() => onAdd(current)} title="Seçili sayfanın arkasına boş sayfa ekle"
          className="inline-flex min-h-8 items-center gap-1 rounded-lg bg-white/80 px-2 text-[11.5px] font-bold text-canvas-violet transition-transform duration-150 ease-out active:scale-[0.97]">
          <Plus className="h-3.5 w-3.5" aria-hidden />Ekle
        </button>
      </div>
      {eight && (
        <div className="flex items-start gap-1.5 rounded-xl bg-amber-50 px-2 py-1.5 text-[11px] font-semibold leading-snug text-amber-800" role="status">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{eight}
        </div>
      )}
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={ids} strategy={rectSortingStrategy}>
          <ol className="flex gap-2 overflow-x-auto overscroll-x-contain pb-1 lg:max-h-[calc(100dvh-220px)] lg:flex-col lg:overflow-y-auto lg:overflow-x-hidden lg:pb-0 lg:pr-1">
            {plan.pages.map((p, i) => (
              <Thumb key={p.id} page={p} no={i + 1} on={p.id === current} src={thumb(p)} pending={pendingIds.has(p.id)}
                interactive={interactive}
                onSelect={() => onSelect(p.id)} onAdd={() => onAdd(p.id)} onDelete={() => setAsk({ id: p.id, no: i + 1 })} />
            ))}
          </ol>
        </SortableContext>
      </DndContext>
      <ConfirmDialog
        open={!!ask}
        title={`Sayfa ${ask?.no ?? ''} silinsin mi?`}
        body="Sayfa plandan çıkar; resmi silinmez, «kullanılmayan resimler»e düşer. Silme sürüm geçmişinden geri alınabilir."
        confirm="Sayfayı sil"
        danger
        onClose={() => setAsk(null)}
        onConfirm={() => { if (ask) onDelete(ask.id); setAsk(null); }}
      />
    </div>
  );
}

function Thumb({ page, no, on, src, pending, interactive, onSelect, onAdd, onDelete }: {
  page: PlanPage; no: number; on: boolean; src: string | null; pending: boolean; interactive: boolean;
  onSelect: () => void; onAdd: () => void; onDelete: () => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: page.id,
    disabled: !interactive,
    transition: reduceMotion() ? null : { duration: 200, easing: EASE },
  });
  const [failed, setFailed] = useState<string | null>(null);
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, zIndex: isDragging ? 5 : undefined }}
      className="group relative w-[92px] shrink-0 lg:w-full"
    >
      <div className={`rounded-xl border p-1 ${on ? 'border-canvas-violet bg-white ring-2 ring-canvas-violet/30' : 'border-white/70 bg-white/70'} ${isDragging ? 'shadow-lg' : ''}`}>
        <div className="flex items-center justify-between gap-1 px-0.5 font-mono text-[10.5px] text-canvas-muted">
          <span className="flex items-center gap-1 whitespace-nowrap">
            {interactive && (
              <button type="button" ref={setActivatorNodeRef} {...attributes} {...listeners}
                aria-label={`Sayfa ${no}: sıralamak için sürükleyin`} className="-ml-0.5 cursor-grab rounded p-0.5 text-slate-400 hover:text-canvas-ink active:cursor-grabbing">
                <GripVertical className="h-3 w-3" aria-hidden />
              </button>
            )}
            s. {no}
          </span>
          <span className="flex items-center gap-1">
            {page.overflow && <span className="rounded bg-amber-100 px-1 text-[9.5px] font-bold text-amber-800" title="Metin kutusuna sığmıyor">taşıyor</span>}
            {pending && <span className="h-1.5 w-1.5 rounded-full bg-canvas-violet" title="Kaydedilmeyi bekliyor" />}
          </span>
        </div>
        <button type="button" onClick={onSelect} aria-current={on ? 'page' : undefined} aria-label={`Sayfa ${no}`}
          className="mt-1 block w-full overflow-hidden rounded-md bg-white transition-transform duration-150 ease-out active:scale-[0.98]">
          {src && failed !== src ? (
            <img src={src} alt="" loading="lazy" decoding="async" draggable={false} onError={() => setFailed(src)} className="block w-full" />
          ) : (
            <div className="flex aspect-[169/231] w-full items-center justify-center bg-slate-50 text-[10.5px] text-canvas-muted">
              {src ? 'dizilmedi' : 'Yeni sayfa'}
            </div>
          )}
        </button>
        <div className={`mt-1 flex justify-between gap-1 ${on ? '' : 'lg:opacity-0 lg:group-hover:opacity-100 lg:group-focus-within:opacity-100'}`}>
          <button type="button" onClick={onAdd} title="Arkasına boş sayfa ekle" aria-label={`Sayfa ${no} arkasına boş sayfa ekle`}
            className="inline-flex h-7 flex-1 items-center justify-center rounded-md bg-slate-100 text-canvas-ink hover:bg-slate-200">
            <Plus className="h-3.5 w-3.5" aria-hidden />
          </button>
          <button type="button" onClick={onDelete} title="Sayfayı sil" aria-label={`Sayfa ${no} sil`}
            className="inline-flex h-7 flex-1 items-center justify-center rounded-md bg-slate-100 text-rose-600 hover:bg-rose-50">
            <Trash2 className="h-3.5 w-3.5" aria-hidden />
          </button>
        </div>
      </div>
    </li>
  );
}
