import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';

/**
 * Kanvas düzeni. Kart konumları ve genişlikleri kullanıcıya ait: sürükle,
 * kenardan çek, bırak. Kayıt tarayıcıda (localStorage), ekran başına ayrı.
 *
 * Varsayılanlar tasarımdaki koordinatlardır; 1440 genişliğe göre çizildikleri
 * için geniş ekranda oranlanarak açılırlar, yoksa sağda boşluk kalır.
 */
export type Box = { x: number; y: number; w: number };
export type BoxMap = Record<string, Box>;

const KEY = (screen: string) => `timas-kanvas-duzen-v1:${screen}`;

type Ctx = {
  boxes: BoxMap;
  defaults: BoxMap;
  set: (id: string, box: Box) => void;
  reset: () => void;
  dirty: boolean;
  stageW: number;
  /** Sürükleme sırasında bağlantı çizgileri anlık yeniden çizilsin diye. */
  tick: number;
  /** En son dokunulan kart üstte durur; taşınınca altta kaybolmasın. */
  front: string | null;
  bringFront: (id: string) => void;
};

const LayoutCtx = createContext<Ctx | null>(null);

export function useLayout(): Ctx {
  const c = useContext(LayoutCtx);
  if (!c) throw new Error('LayoutProvider gerekli');
  return c;
}

function load(screen: string): BoxMap | null {
  try {
    const raw = window.localStorage.getItem(KEY(screen));
    return raw ? (JSON.parse(raw) as BoxMap) : null;
  } catch {
    return null;
  }
}

/** Beş kartın tek satırda dizildiği yuvalar. Sıra tasarımdaki sıradır. */
const ROW = ['c1', 'c2', 'c3', 'c4', 'c5'];
const GAP_MIN = 16;
/** Sol menü sahnenin üstünde yüzüyor; kartlar onun altına girmesin. */
const RAIL = 92;

/**
 * Varsayılan yerleşimi sahne genişliğine göre kurar.
 *
 * Önceden x değerleri orantılanıyordu; ekran 1440'tan darsa konumlar
 * sıkışıyor ama kart genişlikleri sabit kaldığı için kartlar üst üste
 * biniyordu. Şimdi satır, aradaki boşluk hesaplanarak diziliyor: sığmazsa
 * boşluk en aza iner ve satır kaydırılabilir kalır.
 */
function spread(defaults: BoxMap, stageW: number): BoxMap {
  if (!stageW) return defaults;
  const out: BoxMap = { ...defaults };
  const cards = ROW.map((id) => defaults[id]).filter(Boolean);
  const sumW = cards.reduce((a, b) => a + b.w, 0);
  const usable = stageW - RAIL - GAP_MIN;
  const gap = Math.max(GAP_MIN, (usable - sumW) / (cards.length - 1 || 1));
  let x = RAIL + Math.max(0, (usable - sumW - gap * (cards.length - 1)) / 2);
  ROW.forEach((id) => {
    const b = defaults[id];
    if (!b) return;
    out[id] = { ...b, x: Math.round(x) };
    x += b.w + gap;
  });

  // Karar kartı ortada, etiket sağında. Yer darsa önce kart daralır ki etiket yanına sığsın; o da
  // yetmezse etiket kartın altına iner. Kartın yüksekliği ~250 px; 240 px aşağısı üstüne biniyordu.
  const main = defaults.main;
  const sticker = defaults.sticker;
  if (main) {
    const side = sticker ? sticker.w + 24 : 0;
    const roomForBoth = usable - side >= 560;
    const w = Math.min(main.w, Math.max(420, roomForBoth ? usable - side : usable));
    const x = roomForBoth
      ? Math.round(RAIL + Math.max(0, (usable - w - side) / 2))
      : Math.round(RAIL + Math.max(0, (usable - w) / 2));
    out.main = { ...main, w, x };
    if (sticker) {
      out.sticker = roomForBoth
        ? { ...sticker, x: x + w + 24, y: sticker.y }
        : { ...sticker, x: Math.round(RAIL + Math.max(0, (usable - sticker.w) / 2)), y: main.y + 300 };
    }
  }
  // Soru balonu ortalanır.
  const q = defaults.q;
  // Soru iki satıra kayınca kartların üstüne biniyordu; tek satıra sığsın diye genişler.
  if (q) {
    const w = Math.min(760, Math.max(q.w, usable - 2 * GAP_MIN));
    out.q = { ...q, w, x: Math.round(RAIL + Math.max(0, (usable - w) / 2)) };
  }
  return out;
}

export function LayoutProvider({
  screen,
  defaults,
  stageW,
  children,
}: {
  screen: string;
  defaults: BoxMap;
  stageW: number;
  children: ReactNode;
}) {
  const [saved, setSaved] = useState<BoxMap | null>(() => load(screen));
  const [tick, setTick] = useState(0);
  const [front, setFront] = useState<string | null>(null);

  useEffect(() => {
    setSaved(load(screen));
  }, [screen]);

  const spreadDefaults = useMemo(() => spread(defaults, stageW), [defaults, stageW]);
  const boxes = useMemo(() => ({ ...spreadDefaults, ...(saved ?? {}) }), [spreadDefaults, saved]);

  const set = useCallback(
    (id: string, box: Box) => {
      setSaved((prev) => {
        const next = { ...(prev ?? {}), [id]: box };
        try {
          window.localStorage.setItem(KEY(screen), JSON.stringify(next));
        } catch {
          /* saklama kapalıysa düzen yalnız bu oturumda yaşar */
        }
        return next;
      });
      setTick((t) => t + 1);
    },
    [screen],
  );

  const reset = useCallback(() => {
    try {
      window.localStorage.removeItem(KEY(screen));
    } catch {
      /* yoksay */
    }
    setSaved(null);
    setTick((t) => t + 1);
  }, [screen]);

  const value = useMemo<Ctx>(
    () => ({ boxes, defaults: spreadDefaults, set, reset, dirty: Boolean(saved), stageW, tick, front, bringFront: setFront }),
    [boxes, spreadDefaults, set, reset, saved, stageW, tick, front],
  );

  return <LayoutCtx.Provider value={value}>{children}</LayoutCtx.Provider>;
}

const INTERACTIVE = 'a, button, input, select, textarea, [role="button"]';

/**
 * Taşınabilir ve genişliği ayarlanabilir kart kabı. Kart içeriğindeki
 * bağlantı ve düğmeler çalışmaya devam eder: sürükleme yalnız boş alandan
 * ve 4 pikselden fazla hareket ettiğinde başlar.
 */
/**
 * Kanvasın gerçek ölçeği. Sahne CSS `zoom` ile küçülüp büyüyor (sığdırma × kullanıcı yakınlaştırması);
 * imleç ekran pikseliyle, kart konumu sahne pikseliyle ölçülür. Bölmeden sürüklenen kart imleci geriden izler.
 */
function stageScale(el: HTMLElement | null): number {
  let s = 1;
  for (let n = el; n; n = n.parentElement) {
    const z = parseFloat(getComputedStyle(n).zoom || '1');
    if (Number.isFinite(z) && z > 0 && z !== 1) s *= z;
  }
  return s;
}

export default function Node({
  id,
  tilt = 0,
  z = 20,
  minW = 180,
  maxW = 1200,
  resizable = true,
  className = '',
  children,
}: {
  id: string;
  tilt?: number;
  z?: number;
  minW?: number;
  maxW?: number;
  resizable?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const { boxes, set, stageW, front, bringFront } = useLayout();
  const box = boxes[id];
  const [drag, setDrag] = useState<{ dx: number; dy: number; x: number; y: number; moved: boolean; scale: number } | null>(null);
  const [live, setLive] = useState<Box | null>(null);
  const resizing = useRef<{ startX: number; startW: number; scale: number } | null>(null);

  if (!box) return null;
  const b = live ?? box;

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest(INTERACTIVE)) return;
    if ((e.target as HTMLElement).dataset.resize) return;
    bringFront(id);
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setDrag({ dx: e.clientX, dy: e.clientY, x: b.x, y: b.y, moved: false, scale: stageScale(e.currentTarget as HTMLElement) });
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (resizing.current) {
      const w = Math.max(minW, Math.min(maxW, resizing.current.startW + (e.clientX - resizing.current.startX) / resizing.current.scale));
      setLive({ ...b, w });
      return;
    }
    if (!drag) return;
    const nx = drag.x + (e.clientX - drag.dx) / drag.scale;
    const ny = drag.y + (e.clientY - drag.dy) / drag.scale;
    const moved = drag.moved || Math.abs(e.clientX - drag.dx) > 4 || Math.abs(e.clientY - drag.dy) > 4;
    if (moved) {
      setDrag({ ...drag, moved: true });
      setLive({ ...b, x: Math.max(0, Math.min(nx, Math.max(0, stageW - 40))), y: Math.max(0, ny) });
    }
  };
  const finish = () => {
    if (live) set(id, live);
    setLive(null);
    setDrag(null);
    resizing.current = null;
  };

  return (
    <div
      data-node={id}
      className={['absolute touch-none', drag?.moved ? 'cursor-grabbing' : 'cursor-grab', className].join(' ')}
      style={{ left: b.x, top: b.y, width: b.w, zIndex: drag?.moved ? 70 : front === id ? 55 : z, transform: tilt ? `rotate(${tilt}deg)` : undefined }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={finish}
      onPointerCancel={finish}
    >
      {children}
      {resizable && (
        <span
          data-resize="1"
          title="Genişliği ayarla"
          onPointerDown={(e) => {
            e.stopPropagation();
            (e.currentTarget.parentElement as HTMLElement).setPointerCapture(e.pointerId);
            resizing.current = { startX: e.clientX, startW: b.w, scale: stageScale(e.currentTarget as HTMLElement) };
          }}
          className="absolute -bottom-1 -right-1 z-50 h-3.5 w-3.5 cursor-ew-resize rounded-full border border-white bg-slate-300/80 opacity-0 shadow transition hover:bg-violet group-hover/node:opacity-100"
        />
      )}
    </div>
  );
}
