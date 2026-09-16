import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { Minus, Plus } from 'lucide-react';

/**
 * Profil fotoğrafı kırpıcı. Fotoğraf kare çerçeveye sığdırılır; kişi sürükleyerek konumu, kaydırıcıyla
 * (ya da fare tekerleği/klavye ile) yakınlığı seçer. Görüntü hiçbir zaman esnemez: tek bir ölçek iki eksene
 * birden uygulanır ve çerçevede boşluk kalmayacak şekilde sınırlanır.
 *
 * Çıktı OUT×OUT kare. Büyük kaynak tek adımda küçültülürse ince ayrıntı kırılır; bu yüzden yarıya yarıya
 * iner, son adım yüksek kaliteli yumuşatmayla yapılır. Telefon fotoğraflarının yönü (EXIF) çözülürken
 * uygulanır. Saydam PNG beyaz zemine oturur (JPEG'de siyah görünmesin).
 */

export const OUT = 512;
/** Bunun altındaki fotoğraf büyütülerek dolar; kişiye bulanık olabileceği söylenir. */
export const LOW_RES = 256;
const MAX_ZOOM = 4;

export type Decoded = { bitmap: ImageBitmap; url: string; width: number; height: number };

export async function decode(file: File): Promise<Decoded> {
  if (!/^image\/(jpeg|png|webp|heic|heif|gif|bmp|avif)$/i.test(file.type) && file.type !== '') {
    throw new Error('Bu dosya bir fotoğraf değil; JPEG, PNG ya da WebP seçin.');
  }
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    throw new Error('Bu fotoğraf açılamadı; JPEG, PNG ya da WebP seçin.');
  }
  // Önizleme <img> ile: tarayıcı EXIF yönünü CSS `image-orientation: from-image` ile zaten uygular.
  return { bitmap, url: URL.createObjectURL(file), width: bitmap.width, height: bitmap.height };
}

type View = { zoom: number; x: number; y: number };

/** Çerçeveyi dolduran en küçük ölçek (zoom=1) ve verilen zoom'da görüntünün çerçevedeki boyutu. */
function fit(img: { width: number; height: number }, frame: number, zoom: number) {
  const base = frame / Math.min(img.width, img.height);
  const s = base * zoom;
  return { s, w: img.width * s, h: img.height * s };
}

/** Görüntü çerçeveyi her zaman kaplasın: kayma, taşan kısmın yarısıyla sınırlı. */
function clamp(v: View, img: { width: number; height: number }, frame: number): View {
  const zoom = Math.min(MAX_ZOOM, Math.max(1, v.zoom));
  const { w, h } = fit(img, frame, zoom);
  const mx = (w - frame) / 2;
  const my = (h - frame) / 2;
  return { zoom, x: Math.min(mx, Math.max(-mx, v.x)), y: Math.min(my, Math.max(-my, v.y)) };
}

export function render(img: Decoded, view: View, frame: number): Promise<string> {
  const { s, w, h } = fit(img, frame, view.zoom);
  // Çerçevenin sol üstü, görüntü koordinatında.
  const left = (w / 2 - frame / 2 - view.x) / s;
  const top = (h / 2 - frame / 2 - view.y) / s;
  const side = frame / s;

  // Kaynak kareyi al, yarıya yarıya küçült.
  let cur = document.createElement('canvas');
  let size = Math.max(1, Math.round(side));
  cur.width = cur.height = size;
  let ctx = cur.getContext('2d')!;
  ctx.fillStyle = '#fff';
  ctx.fillRect(0, 0, size, size);
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(img.bitmap, left, top, side, side, 0, 0, size, size);
  while (size / 2 >= OUT) {
    const next = document.createElement('canvas');
    const half = Math.round(size / 2);
    next.width = next.height = half;
    const nctx = next.getContext('2d')!;
    nctx.imageSmoothingEnabled = true;
    nctx.imageSmoothingQuality = 'high';
    nctx.drawImage(cur, 0, 0, size, size, 0, 0, half, half);
    cur = next;
    size = half;
  }
  const out = document.createElement('canvas');
  out.width = out.height = OUT;
  ctx = out.getContext('2d')!;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(cur, 0, 0, size, size, 0, 0, OUT, OUT);

  // WebP aynı kalitede JPEG'in yaklaşık üçte ikisi; desteklemeyen tarayıcı PNG döndürür, o zaman JPEG.
  const webp = out.toDataURL('image/webp', 0.9);
  return Promise.resolve(webp.startsWith('data:image/webp') ? webp : out.toDataURL('image/jpeg', 0.92));
}

export default function PhotoCropper({
  image,
  busy,
  onCancel,
  onApply,
}: {
  image: Decoded;
  busy: boolean;
  onCancel: () => void;
  onApply: (dataUrl: string) => void;
}) {
  const frameRef = useRef<HTMLDivElement>(null);
  const [frame, setFrame] = useState(280);
  const [view, setView] = useState<View>({ zoom: 1, x: 0, y: 0 });
  const drag = useRef<{ id: number; sx: number; sy: number; vx: number; vy: number } | null>(null);

  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setFrame(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Çerçeve boyutu değişince konum yeniden sınırlanır.
  useEffect(() => setView((v) => clamp(v, image, frame)), [frame, image]);

  const set = useCallback((next: View) => setView(clamp(next, image, frame)), [image, frame]);

  /** Yakınlaştırırken işaretçinin altındaki nokta yerinde kalsın. */
  const zoomAt = (zoom: number, px = frame / 2, py = frame / 2) => {
    const z = Math.min(MAX_ZOOM, Math.max(1, zoom));
    const k = z / view.zoom;
    const cx = px - frame / 2;
    const cy = py - frame / 2;
    set({ zoom: z, x: cx - (cx - view.x) * k, y: cy - (cy - view.y) * k });
  };

  const onPointerDown = (e: PointerEvent<HTMLDivElement>) => {
    if (drag.current) return; // ikinci parmak sürüklemeyi devralmasın
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { id: e.pointerId, sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y };
  };
  const onPointerMove = (e: PointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (!d || d.id !== e.pointerId) return;
    set({ zoom: view.zoom, x: d.vx + e.clientX - d.sx, y: d.vy + e.clientY - d.sy });
  };
  const endDrag = (e: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.id === e.pointerId) drag.current = null;
  };
  // Tekerlek: React'in dinleyicisi pasif, sayfanın kaymasını durduramaz; bu yüzden yerel dinleyici.
  const zoomRef = useRef(zoomAt);
  zoomRef.current = zoomAt;
  const zoomNow = useRef(view.zoom);
  zoomNow.current = view.zoom;
  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomRef.current(zoomNow.current * Math.exp(-e.deltaY * 0.0015), e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.shiftKey ? 40 : 10;
    const moves: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[e.key]) {
      e.preventDefault();
      set({ zoom: view.zoom, x: view.x + moves[e.key][0], y: view.y + moves[e.key][1] });
    } else if (e.key === '+' || e.key === '=') {
      e.preventDefault();
      zoomAt(view.zoom * 1.1);
    } else if (e.key === '-') {
      e.preventDefault();
      zoomAt(view.zoom / 1.1);
    }
  };

  const { w, h } = fit(image, frame, view.zoom);
  const lowRes = Math.min(image.width, image.height) / view.zoom < LOW_RES;

  return (
    <div className="flex flex-col gap-3">
      <div
        ref={frameRef}
        role="application"
        aria-label="Fotoğrafı konumlandır: ok tuşlarıyla kaydır (Shift ile hızlı), artı ve eksiyle yakınlaştır"
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onKeyDown={onKey}
        className="relative mx-auto aspect-square w-full max-w-[280px] cursor-grab touch-none select-none overflow-hidden rounded-2xl bg-slate-100 outline-none ring-1 ring-slate-200 focus-visible:ring-2 focus-visible:ring-violet active:cursor-grabbing"
      >
        <img
          src={image.url}
          alt=""
          draggable={false}
          className="pointer-events-none absolute left-1/2 top-1/2 max-w-none"
          style={{
            width: w,
            height: h,
            imageOrientation: 'from-image',
            transform: `translate(calc(-50% + ${view.x}px), calc(-50% + ${view.y}px))`,
          }}
        />
        {/* Daire kılavuz: sağ üstteki avatar yuvarlak kesilir; köşeler karede kalır. */}
        <div aria-hidden className="pointer-events-none absolute inset-0 rounded-full shadow-[0_0_0_999px_rgba(15,23,42,0.35)]" />
      </div>

      <div className="flex items-center gap-2 px-1">
        <button
          type="button"
          aria-label="Uzaklaştır"
          onClick={() => zoomAt(view.zoom / 1.2)}
          className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-slate-100 sm:h-8 sm:w-8"
        >
          <Minus className="h-3.5 w-3.5" />
        </button>
        <input
          type="range"
          min={1}
          max={MAX_ZOOM}
          step={0.01}
          value={view.zoom}
          aria-label="Yakınlık"
          onChange={(e) => zoomAt(Number(e.target.value))}
          className="h-11 min-w-0 flex-1 accent-violet sm:h-6"
        />
        <button
          type="button"
          aria-label="Yakınlaştır"
          onClick={() => zoomAt(view.zoom * 1.2)}
          className="kp-press flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-slate-100 sm:h-8 sm:w-8"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
      <p className={`text-center text-[11px] ${lowRes ? 'text-amber-700' : 'text-muted'}`}>
        {lowRes ? 'Bu yakınlıkta fotoğraf bulanık görünebilir; biraz uzaklaştırın ya da daha büyük bir fotoğraf seçin.' : 'Sürükleyerek konumlandırın, kaydırıcıyla yakınlaştırın.'}
      </p>

      <div className="flex justify-end gap-2">
        <button type="button" onClick={onCancel} disabled={busy} className="kp-press min-h-11 rounded-xl px-3 text-xs font-medium text-muted hover:bg-slate-100 disabled:opacity-60 sm:min-h-9">
          Vazgeç
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void render(image, view, frame).then(onApply)}
          className="kp-press min-h-11 rounded-xl bg-violet px-4 text-xs font-bold text-white hover:bg-violet/90 disabled:opacity-60 sm:min-h-9"
        >
          {busy ? 'Yükleniyor…' : 'Fotoğrafı kullan'}
        </button>
      </div>
    </div>
  );
}
