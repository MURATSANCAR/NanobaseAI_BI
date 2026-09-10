import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { STAGE_H, STAGE_W } from '../types';

/** Dar ekranda kanvas kaydırılamaz: kartlar tek sütuna düşer. */
export const STACK_BREAKPOINT = 1024;

export type StageView = {
  /** Kabın sahneyi tam gösterecek ölçeği. */
  fit: number;
  /** Kullanıcının yakınlaştırması dahil, uygulanan ölçek. */
  scale: number;
  zoom: number;
  stacked: boolean;
  pan: { x: number; y: number };
};

type Props = {
  children: ReactNode;
  /** Bağlantı çizgileri gibi sahne koordinatında duran katman. */
  underlay?: ReactNode;
  onView?: (view: StageView) => void;
  /** Dışarıdan yakınlaştırma denetimi (üst şeritteki % düğmeleri). */
  zoom?: number;
  onZoomChange?: (zoom: number) => void;
};

export const ZOOM_MIN = 0.4;
export const ZOOM_MAX = 2;

/**
 * Sabit 1440×1000 sahneyi kabına ölçekleyerek sığdırır; yakınlaştırma varsa
 * fazlalık kaydırılabilir. Tasarım koordinatları hiç değişmez — responsive'lik
 * yeniden akıtmayla değil, ölçekle çözülür.
 */
export default function CanvasStage({ children, underlay, onView, zoom = 1, onZoomChange }: Props) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);

  useLayoutEffect(() => {
    const el = hostRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r) setBox({ w: r.width, h: r.height });
    });
    ro.observe(el);
    setBox({ w: el.clientWidth, h: el.clientHeight });
    return () => ro.disconnect();
  }, []);

  const stacked = box.w > 0 && box.w < STACK_BREAKPOINT;
  const fit = box.w > 0 && box.h > 0 ? Math.min(box.w / STAGE_W, box.h / STAGE_H) : 1;
  const scale = fit * zoom;

  // Sahne kaba sığıyorsa ortala ve kaydırmayı sıfırla; taşıyorsa kullanıcı kaydırır.
  const overflowX = STAGE_W * scale - box.w;
  const overflowY = STAGE_H * scale - box.h;
  const clampPan = useCallback(
    (p: { x: number; y: number }) => ({
      x: overflowX <= 0 ? 0 : Math.min(0, Math.max(-overflowX, p.x)),
      y: overflowY <= 0 ? 0 : Math.min(0, Math.max(-overflowY, p.y)),
    }),
    [overflowX, overflowY],
  );

  useEffect(() => {
    setPan((p) => clampPan(p));
  }, [clampPan]);

  useEffect(() => {
    onView?.({ fit, scale, zoom, stacked, pan });
  }, [fit, scale, zoom, stacked, pan, onView]);

  const onPointerDown = (e: React.PointerEvent) => {
    if (stacked || (overflowX <= 0 && overflowY <= 0)) return;
    // Etkileşimli öğenin üstünde sürükleme başlatma.
    if ((e.target as HTMLElement).closest('button, a, input, select, textarea')) return;
    drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    setPan(clampPan({ x: d.px + (e.clientX - d.x), y: d.py + (e.clientY - d.y) }));
  };
  const endDrag = () => {
    drag.current = null;
  };

  const onWheel = (e: React.WheelEvent) => {
    if (stacked || !onZoomChange) return;
    if (!(e.ctrlKey || e.metaKey)) return;
    e.preventDefault();
    const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoom - e.deltaY * 0.002));
    onZoomChange(Number(next.toFixed(2)));
  };

  if (stacked) {
    return (
      <div ref={hostRef} className="cv-scroll h-full w-full overflow-y-auto overflow-x-hidden px-4 pb-40 pt-2">
        <div className="mx-auto flex w-full max-w-[560px] flex-col gap-4">{children}</div>
      </div>
    );
  }

  const panning = overflowX > 0 || overflowY > 0;
  return (
    <div
      ref={hostRef}
      className={['relative h-full w-full overflow-hidden', panning ? 'cursor-grab active:cursor-grabbing' : ''].join(' ')}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onWheel={onWheel}
    >
      <div
        className="absolute left-0 top-0 origin-top-left"
        style={{
          width: STAGE_W,
          height: STAGE_H,
          transform: `translate(${pan.x + (overflowX <= 0 ? (box.w - STAGE_W * scale) / 2 : 0)}px, ${
            pan.y + (overflowY <= 0 ? (box.h - STAGE_H * scale) / 2 : 0)
          }px) scale(${scale})`,
        }}
      >
        {underlay}
        {children}
      </div>
    </div>
  );
}
