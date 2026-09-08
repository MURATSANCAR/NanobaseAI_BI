/**
 * Masa: kartların listesi, sırası ve boyu.
 *
 * Önceden bu ekran elle dizilmiş bir JSX bloğuydu. Kimin neyi önce görmek istediği baştan
 * kararlaştırılmıştı ve değiştirilemiyordu; oysa aynı masaya bakan CFO ile yayın kurulu aynı sırayı
 * istemiyor. Burada düzen bir veri: taşınabilir, boyutlandırılabilir, ve sohbette çıkan bir cevap
 * doğrudan buraya iliştirilebilir.
 *
 * Düzen tarayıcıda saklanıyor — sistemde kullanıcı kavramı yok (portalın kendi girişi kapalı), ve
 * "kişiye özel" demek olmayan bir şeyi öyleymiş gibi göstermek yanlış olurdu. Şema kişiye taşınmaya
 * hazır: değişecek tek şey `board.ts` içindeki load/save.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors,
         type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, arrayMove, rectSortingStrategy, sortableKeyboardCoordinates,
         useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, RotateCcw, Trash2 } from 'lucide-react';
import clsx from 'clsx';
import { DEFAULT_BOARD, SPANS, SPAN_LABEL, load, save, type Board as BoardModel, type Span,
         type Tile } from '../lib/board';

const COL: Record<Span, string> = {
  1: 'sm:col-span-2 2xl:col-span-1',
  2: 'sm:col-span-2 2xl:col-span-2',
  4: 'col-span-1 sm:col-span-4 2xl:col-span-4',
};

export function useBoard() {
  const [board, setBoard] = useState<BoardModel>(() => load());
  // İlk çizimde yazma: kaydedilmiş düzen yokken varsayılanı diske basmak, sonraki sürümde eklenen
  // kartların "kullanıcı bunu kaldırmış" sanılmasına yol açıyor.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    save(board);
  }, [board]);

  const reorder = useCallback((from: string, to: string) => {
    setBoard((b) => {
      const a = b.tiles.findIndex((t) => t.id === from);
      const c = b.tiles.findIndex((t) => t.id === to);
      if (a < 0 || c < 0 || a === c) return b;
      return { ...b, tiles: arrayMove(b.tiles, a, c) };
    });
  }, []);
  const resize = useCallback((id: string, span: Span) => {
    setBoard((b) => ({ ...b, tiles: b.tiles.map((t) => (t.id === id ? { ...t, span } : t)) }));
  }, []);
  const remove = useCallback((id: string) => {
    setBoard((b) => ({ ...b, tiles: b.tiles.filter((t) => t.id !== id) }));
  }, []);
  const reset = useCallback(() => setBoard(DEFAULT_BOARD), []);
  const pin = useCallback((tile: Tile) => {
    setBoard((b) => (b.tiles.some((t) => t.id === tile.id)
      ? b
      : { ...b, tiles: [tile, ...b.tiles] }));      // yeni gelen üstte durur, aranmaz
  }, []);
  const patch = useCallback((id: string, fields: Partial<Tile>) => {
    setBoard((b) => ({ ...b, tiles: b.tiles.map((t) => (t.id === id ? ({ ...t, ...fields } as Tile) : t)) }));
  }, []);

  return { board, reorder, resize, remove, reset, pin, patch };
}

export function Board({
  tiles, editing, onEdit, onReorder, onResize, onRemove, onReset, render,
}: {
  tiles: Tile[];
  editing: boolean;
  onEdit: (v: boolean) => void;
  onReorder: (from: string, to: string) => void;
  onResize: (id: string, span: Span) => void;
  onRemove: (id: string) => void;
  onReset: () => void;
  render: (tile: Tile) => React.ReactNode;
}) {
  const sensors = useSensors(
    // 6 piksel eşik: karttaki düğmelere tıklamak sürükleme sayılmasın.
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const onDragEnd = (e: DragEndEvent) => {
    const over = e.over?.id;
    if (over && over !== e.active.id) onReorder(String(e.active.id), String(over));
  };

  return (
    <>
      <div className="flex items-center justify-end gap-1.5">
        {editing && (
          <button type="button" onClick={onReset}
            className="inline-flex items-center gap-1 rounded-lg border border-line bg-white px-2 py-1 text-[11px] text-ink-muted hover:border-brand/40">
            <RotateCcw size={11} /> varsayılana dön
          </button>
        )}
        <button type="button" onClick={() => onEdit(!editing)}
          className={clsx('inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px] font-medium transition',
            editing ? 'bg-brand text-white' : 'border border-line bg-white text-ink-muted hover:border-brand/40')}>
          <GripVertical size={11} /> {editing ? 'düzeni bitir' : 'düzeni değiştir'}
        </button>
      </div>

      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd}>
        <SortableContext items={tiles.map((t) => t.id)} strategy={rectSortingStrategy}>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4 sm:gap-4">
            {tiles.map((t) => (
              <Cell key={t.id} tile={t} editing={editing} onResize={onResize} onRemove={onRemove}>
                {render(t)}
              </Cell>
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </>
  );
}

function Cell({
  tile, editing, onResize, onRemove, children,
}: {
  tile: Tile; editing: boolean; onResize: (id: string, span: Span) => void;
  onRemove: (id: string) => void; children: React.ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: tile.id, disabled: !editing });
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      className={clsx('relative min-w-0', COL[tile.span], isDragging && 'z-20 opacity-70')}
    >
      {editing && (
        <div className="absolute -top-2 right-2 z-10 flex items-center gap-1 rounded-lg border border-line bg-white px-1 py-0.5 shadow-card">
          <button
            type="button"
            {...attributes}
            {...listeners}
            aria-label="Kartı taşı"
            className="cursor-grab rounded p-0.5 text-ink-faint hover:text-brand active:cursor-grabbing"
          >
            <GripVertical size={13} />
          </button>
          {SPANS.map((s) => (
            <button key={s} type="button" onClick={() => onResize(tile.id, s)}
              className={clsx('rounded px-1 text-[9px] font-semibold',
                tile.span === s ? 'bg-brand text-white' : 'text-ink-faint hover:text-brand')}>
              {SPAN_LABEL[s]}
            </button>
          ))}
          {tile.kind === 'pinned' && (
            <button type="button" onClick={() => onRemove(tile.id)} aria-label="Kartı kaldır"
              className="rounded p-0.5 text-ink-faint hover:text-brand-accent">
              <Trash2 size={12} />
            </button>
          )}
        </div>
      )}
      <div className={clsx('h-full', editing && 'rounded-2xl outline-dashed outline-1 outline-offset-4 outline-brand/30')}>
        {children}
      </div>
    </div>
  );
}
