import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as RPointerEvent, type SyntheticEvent } from 'react';
import { useDroppable } from '@dnd-kit/core';
import { ImageUp } from 'lucide-react';
import { studioPlanApi, type Plan, type PlanArt, type PlanBox, type PlanBubble, type PlanEffect, type PlanFreeText, type PlanPage, type PlanRun, type PlanShape } from '../../engine';
import { r1, safeRect, trimRect, type PageDims } from './planModel';
import { ITEM_LABEL, PRINT_DPI, findItem, itemDpi, itemKey, pageItems, rotatable, shapesOf, withBox, type ItemRef, type PageItem } from './pageItems';
import { SHAPE_MIME } from './slots';

/** Sayfa tuvali. Altta sunucunun dizdiği sayfa önizlemesi (gerçek dizgi), üstünde seçilebilir ögeler.
 *  Konumlar yüzdeyle verilir (mm / sayfa ölçüsü); böylece kabuğun yakınlaştırması (CSS zoom) ve ekran
 *  genişliği hesabı bozmaz. Fare hareketi mm'ye `sayfa genişliği / ekrandaki genişlik` ile çevrilir.
 *
 *  Sürükleme, boyutlandırma ve döndürme sırasında ögenin yeni hâli yalnız burada çizilir (anında);
 *  bırakınca `onChange` bir kez çağrılır ve otomatik kayıt sırası devralır. Sayfanın ekrandaki hâli
 *  sunucudakinden farklıyken önizleme soluklaşır, ögeler tarayıcıda yaklaşık çizilir; sunucu yeni dizgiyi
 *  verince gerçek önizleme geri gelir. Sürükleme animasyonsuzdur (el hareketini birebir izler). */

export const CANVAS_DROP = 'sayfa-tuvali';

type Mode = 'move' | 'nw' | 'ne' | 'sw' | 'se' | 'rotate' | 'tail';
type Drag = {
  mode: Mode; ref: ItemRef; pointerId: number; sx: number; sy: number; mmPerPx: number;
  box0: PlanBox; rot0: number; tail0: { x: number; y: number } | null; cx: number; cy: number; moved: boolean;
};
type Draft = { key: string; box: PlanBox; rotate?: number; tail?: { x: number; y: number } | null };

const pct = (v: number, of: number) => `${(v / of) * 100}%`;
const boxStyle = (b: PlanBox, d: PageDims): CSSProperties => ({ left: pct(b.x, d.w), top: pct(b.y, d.h), width: pct(b.w, d.w), height: pct(b.h, d.h) });
const PT_MM = 25.4 / 72;
const MIN = 5;

/** Kılavuz çizgileri: sayfa kenarı, kesim (taşma payı), güvenli alan, orta. */
function guides(d: PageDims) {
  const s = safeRect(d);
  return { xs: [0, d.bleed, s.x, d.w / 2, s.x + s.w, d.w - d.bleed, d.w], ys: [0, d.bleed, s.y, d.h / 2, s.y + s.h, d.h - d.bleed, d.h] };
}
function snap1(v: number, lines: number[], th: number) {
  let best = v;
  let dist = th;
  for (const l of lines) if (Math.abs(l - v) <= dist) { best = l; dist = Math.abs(l - v); }
  return best;
}

export default function PageCanvas({
  job, plan, page, previewSrc, dirty, artSrc, bodySize, selected, onSelect, onChange, interactive, suggestions, onFiles, onDropShape,
}: {
  job: string;
  plan: Plan;
  page: PlanPage;
  /** Sunucudaki hâlin önizlemesi; sayfa henüz sunucuda yoksa null. */
  previewSrc: (w: number) => string | null;
  /** Ekrandaki sayfa sunucudakinden farklı mı (kaydedilmemiş ya da dizgisi bekleniyor). */
  dirty: boolean;
  artSrc: (art: PlanArt, w: number) => string | null;
  bodySize: number;
  selected: ItemRef | null;
  onSelect: (r: ItemRef | null) => void;
  onChange: (p: PlanPage, undoKey: string) => void;
  interactive: boolean;
  suggestions: PlanBubble[] | null;
  onFiles: (files: File[]) => void;
  /** Öğeler panelinden bırakılan şekil (`application/x-studio-shape`); nokta mm cinsinden. */
  onDropShape: (shape: Partial<PlanShape>, cx: number, cy: number) => void;
}) {
  const d = plan.page;
  const wrap = useRef<HTMLDivElement | null>(null);
  const [cssW, setCssW] = useState(0);
  const drag = useRef<Drag | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [fileOver, setFileOver] = useState(false);
  const [shapeOver, setShapeOver] = useState(false);
  const { setNodeRef, isOver } = useDroppable({ id: CANVAS_DROP });

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setCssW(el.offsetWidth));
    ro.observe(el);
    setCssW(el.offsetWidth);
    return () => ro.disconnect();
  }, []);

  // Önizleme genişliği ekrandaki genişlik × piksel yoğunluğu, 200'lük basamakla (önbellek tutsun diye).
  const dpr = typeof window !== 'undefined' ? Math.min(2, window.devicePixelRatio || 1) : 1;
  const pw = Math.max(240, Math.min(2400, Math.ceil((cssW * dpr) / 200) * 200));
  const src = cssW ? previewSrc(pw) : null;
  const [loadedSrc, setLoadedSrc] = useState<string | null>(null);
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const previewReady = !!src && loadedSrc === src && failedSrc !== src;
  const live = dirty || !!draft || !previewReady;

  // Sürükleme sürerken çizilen sayfa: taslak kutu uygulanmış hâl.
  const shown = useMemo(() => {
    if (!draft) return page;
    const r = selected && itemKey(selected) === draft.key ? selected : null;
    if (!r) return page;
    let p = withBox(page, r, draft.box, draft.rotate);
    if (r.kind === 'bubble' && draft.tail !== undefined) p = { ...p, bubbles: p.bubbles.map((b) => (b.id === r.id ? { ...b, tail: draft.tail ?? null } : b)) };
    return p;
  }, [page, draft, selected]);
  const items = useMemo(() => pageItems(shown), [shown]);
  const mmPx = cssW / d.w; // CSS pikseli / mm (yazı boyu için)

  // ---------------------------------------------------------------- sürükleme
  const begin = (e: RPointerEvent, it: PageItem, mode: Mode) => {
    e.stopPropagation();
    onSelect({ kind: it.kind, id: it.id });
    if (!interactive || e.button !== 0 || drag.current) return; // ikinci parmak/tuş sürüklemeyi devralmaz
    const rect = wrap.current!.getBoundingClientRect();
    const b = page.bubbles.find((x) => x.id === it.id);
    try {
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    } catch { /* işaretçi bu arada bırakıldıysa yakalama yapılamaz; sürükleme yine de tuval üstünde izlenir */ }
    drag.current = {
      mode, ref: { kind: it.kind, id: it.id }, pointerId: e.pointerId, sx: e.clientX, sy: e.clientY, mmPerPx: d.w / rect.width,
      box0: it.box, rot0: it.rotate, tail0: it.kind === 'bubble' ? b?.tail ?? null : null,
      cx: rect.left + ((it.box.x + it.box.w / 2) / d.w) * rect.width, cy: rect.top + ((it.box.y + it.box.h / 2) / d.h) * rect.height, moved: false,
    };
  };

  const move = (e: RPointerEvent) => {
    const g = drag.current;
    if (!g || e.pointerId !== g.pointerId) return;
    const dx = (e.clientX - g.sx) * g.mmPerPx;
    const dy = (e.clientY - g.sy) * g.mmPerPx;
    if (!g.moved && Math.hypot(e.clientX - g.sx, e.clientY - g.sy) < 3) return;
    g.moved = true;
    const th = 6 * g.mmPerPx; // 6 piksellik yapışma
    const noSnap = e.altKey;
    const { xs, ys } = guides(d);
    const key = itemKey(g.ref);
    const b0 = g.box0;
    if (g.mode === 'move') {
      let x = b0.x + dx;
      let y = b0.y + dy;
      if (!noSnap) {
        const cands = [
          [x, 0], [x + b0.w / 2, b0.w / 2], [x + b0.w, b0.w],
        ] as const;
        let bx = x; let bd = th;
        for (const [edge, off] of cands) { const sx = snap1(edge, xs, th); if (sx !== edge && Math.abs(sx - edge) <= bd) { bd = Math.abs(sx - edge); bx = sx - off; } }
        const cy = [[y, 0], [y + b0.h / 2, b0.h / 2], [y + b0.h, b0.h]] as const;
        let by = y; let bdy = th;
        for (const [edge, off] of cy) { const sy = snap1(edge, ys, th); if (sy !== edge && Math.abs(sy - edge) <= bdy) { bdy = Math.abs(sy - edge); by = sy - off; } }
        x = bx; y = by;
      }
      setDraft({ key, box: { x: r1(x), y: r1(y), w: b0.w, h: b0.h } });
    } else if (g.mode === 'rotate') {
      let a = (Math.atan2(e.clientY - g.cy, e.clientX - g.cx) * 180) / Math.PI + 90;
      if (e.shiftKey) a = Math.round(a / 15) * 15;
      a = ((Math.round(a) % 360) + 360) % 360;
      setDraft({ key, box: b0, rotate: a > 180 ? a - 360 : a });
    } else if (g.mode === 'tail') {
      const t0 = g.tail0 ?? { x: b0.x + b0.w / 2, y: b0.y + b0.h + 8 };
      setDraft({ key, box: b0, tail: { x: r1(t0.x + dx), y: r1(t0.y + dy) } });
    } else {
      // Köşeden boyutlandırma: karşı köşe sabit; Shift resim/figürde en-boy oranını korur.
      const left = g.mode === 'nw' || g.mode === 'sw';
      const top = g.mode === 'nw' || g.mode === 'ne';
      let x1 = left ? b0.x + dx : b0.x;
      let x2 = left ? b0.x + b0.w : b0.x + b0.w + dx;
      let y1 = top ? b0.y + dy : b0.y;
      let y2 = top ? b0.y + b0.h : b0.y + b0.h + dy;
      if (!noSnap) {
        if (left) x1 = snap1(x1, xs, th); else x2 = snap1(x2, xs, th);
        if (top) y1 = snap1(y1, ys, th); else y2 = snap1(y2, ys, th);
      }
      let w = Math.max(MIN, x2 - x1);
      let h = Math.max(MIN, y2 - y1);
      const image = g.ref.kind === 'art' || g.ref.kind === 'figure' || g.ref.kind === 'shape';
      if (image && e.shiftKey && b0.w > 0 && b0.h > 0) {
        const ratio = b0.w / b0.h;
        if (w / h > ratio) w = h * ratio; else h = w / ratio;
      }
      const x = left ? b0.x + b0.w - w : b0.x;
      const y = top ? b0.y + b0.h - h : b0.y;
      setDraft({ key, box: { x: r1(x), y: r1(y), w: r1(w), h: r1(h) } });
    }
  };

  const end = (e: RPointerEvent) => {
    const g = drag.current;
    if (!g || e.pointerId !== g.pointerId) return;
    drag.current = null;
    if (draft && g.moved) {
      let p = withBox(page, g.ref, draft.box, draft.rotate);
      if (g.mode === 'tail') p = { ...p, bubbles: p.bubbles.map((b) => (b.id === g.ref.id ? { ...b, tail: draft.tail ?? null, source: 'editor' } : b)) };
      onChange(p, `${g.mode}:${itemKey(g.ref)}:${Date.now()}`);
    }
    setDraft(null);
  };

  const cancel = () => { drag.current = null; setDraft(null); };

  // Seçim başka sayfaya geçince yarım sürükleme bırakılır.
  useEffect(() => cancel, [page.id]);

  const sel = selected ? findItem(shown, selected) : null;
  const sr = safeRect(d);
  const tr = trimRect(d);

  return (
    <div
      ref={(el) => { wrap.current = el; setNodeRef(el); }}
      className={`relative w-full select-none overflow-hidden bg-white shadow-md ${isOver || fileOver || shapeOver ? 'ring-2 ring-canvas-violet' : ''}`}
      style={{ aspectRatio: `${d.w} / ${d.h}`, touchAction: interactive ? 'none' : 'auto' }}
      onPointerDown={() => onSelect(null)}
      onPointerMove={move}
      onPointerUp={end}
      onPointerCancel={cancel}
      onDragOver={(e) => {
        const t = e.dataTransfer.types;
        if (t.includes(SHAPE_MIME)) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setShapeOver(true); return; }
        if (t.includes('Files')) { e.preventDefault(); setFileOver(true); }
      }}
      onDragLeave={() => { setFileOver(false); setShapeOver(false); }}
      onDrop={(e) => {
        setFileOver(false);
        setShapeOver(false);
        const raw = e.dataTransfer.getData(SHAPE_MIME);
        if (raw) {
          e.preventDefault();
          let shape: Partial<PlanShape> | null = null;
          try { shape = JSON.parse(raw) as Partial<PlanShape>; } catch { shape = null; }
          if (!shape || typeof shape !== 'object' || !shape.kind) return;
          const rect = wrap.current!.getBoundingClientRect();
          onDropShape(shape, ((e.clientX - rect.left) / rect.width) * d.w, ((e.clientY - rect.top) / rect.height) * d.h);
          return;
        }
        if (!e.dataTransfer.files.length) return;
        e.preventDefault();
        onFiles(Array.from(e.dataTransfer.files));
      }}
    >
      {src && (
        <img
          key={src}
          src={src}
          alt=""
          draggable={false}
          onLoad={() => setLoadedSrc(src)}
          onError={() => setFailedSrc(src)}
          className="pe-fade absolute inset-0 h-full w-full"
          style={{ opacity: live ? (previewReady ? 0.22 : 0) : 1 }}
        />
      )}
      {live && <LiveLayer job={job} plan={plan} page={shown} mmPx={mmPx} bodySize={bodySize} artSrc={artSrc} />}
      {suggestions && suggestions.length > 0 && (
        <div className="pointer-events-none absolute inset-0">
          {suggestions.map((b) => (
            <div key={b.id} className="absolute rounded-[50%] border-2 border-dashed border-canvas-violet bg-violet-50/70 p-1 text-center text-[10px] font-bold text-canvas-violet" style={boxStyle(b.box, d)}>
              {b.text}
            </div>
          ))}
        </div>
      )}

      {/* Kılavuzlar: kesim çizgisi (taşma payının içi) ve güvenli alan */}
      <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox={`0 0 ${d.w} ${d.h}`} preserveAspectRatio="none" aria-hidden>
        <rect x={tr.x} y={tr.y} width={tr.w} height={tr.h} fill="none" stroke="#FF6B4A" strokeOpacity={0.7} strokeWidth={0.35} strokeDasharray="2 1.5" vectorEffect="non-scaling-stroke" />
        <rect x={sr.x} y={sr.y} width={sr.w} height={sr.h} fill="none" stroke="#7C5CFF" strokeOpacity={0.55} strokeWidth={0.35} strokeDasharray="1 1.5" vectorEffect="non-scaling-stroke" />
      </svg>

      {/* Etkileşim katmanı */}
      {items.map((it) => {
        const on = !!selected && selected.kind === it.kind && selected.id === it.id;
        const dpi = itemDpi(plan, shown, it);
        const low = dpi !== null && dpi < PRINT_DPI;
        return (
          <div
            key={itemKey(it)}
            role="button"
            tabIndex={-1}
            aria-label={`${ITEM_LABEL[it.kind]}${on ? ' (seçili)' : ''}`}
            onPointerDown={(e) => begin(e, it, 'move')}
            className={`group absolute ${interactive ? 'cursor-move' : 'cursor-pointer'} ${on ? 'outline outline-2 outline-canvas-violet' : 'outline-1 outline-canvas-violet/0 [@media(hover:hover)]:hover:outline [@media(hover:hover)]:hover:outline-canvas-violet/50'}`}
            style={{ ...boxStyle(it.box, d), zIndex: 10 + it.z, transform: rotatable(it.kind) && it.rotate ? `rotate(${it.rotate}deg)` : undefined }}
          >
            {low && (
              <span className="pointer-events-none absolute left-1 top-1 max-w-[calc(100%-8px)] truncate rounded-md bg-amber-500 px-1.5 py-0.5 text-[10.5px] font-bold text-white shadow">
                Baskıda bulanık çıkabilir · {dpi} dpi
              </span>
            )}
            {on && interactive && (
              <>
                {(['nw', 'ne', 'sw', 'se'] as const).map((c) => (
                  <span
                    key={c}
                    onPointerDown={(e) => begin(e, it, c)}
                    className={`absolute h-3 w-3 rounded-[3px] border-2 border-canvas-violet bg-white ${c[0] === 'n' ? '-top-1.5' : '-bottom-1.5'} ${c[1] === 'w' ? '-left-1.5' : '-right-1.5'} ${c === 'nw' || c === 'se' ? 'cursor-nwse-resize' : 'cursor-nesw-resize'}`}
                  />
                ))}
                {rotatable(it.kind) && (
                  <span onPointerDown={(e) => begin(e, it, 'rotate')} title="Döndür (Shift: 15°)"
                    className="absolute -top-7 left-1/2 h-3.5 w-3.5 -translate-x-1/2 cursor-grab rounded-full border-2 border-canvas-violet bg-white" />
                )}
              </>
            )}
          </div>
        );
      })}
      {sel?.kind === 'bubble' && interactive && (() => {
        const b = shown.bubbles.find((x) => x.id === sel.id);
        const t = b?.tail;
        if (!b || !t) return null;
        return (
          <span
            onPointerDown={(e) => begin(e, sel, 'tail')}
            title="Kuyruğun ucu: konuşana sürükleyin"
            className="absolute z-[60] h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 cursor-crosshair rounded-full border-2 border-white bg-canvas-coral shadow"
            style={{ left: pct(t.x, d.w), top: pct(t.y, d.h) }}
          />
        );
      })()}
      {fileOver && (
        <div className="pointer-events-none absolute inset-0 z-[70] flex items-center justify-center bg-violet-50/70 text-[13px] font-bold text-canvas-violet">
          <ImageUp className="mr-2 h-5 w-5" aria-hidden />Fotoğrafı bu sayfaya bırakın
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ tarayıcıda yaklaşık çizim
function Runs({ runs, base }: { runs: PlanRun[]; base: { mmPx: number; color: string } }) {
  return (
    <>
      {runs.map((r, i) => (
        <span key={i} style={{
          color: r.color || base.color,
          fontWeight: r.weight ?? undefined,
          fontSize: r.size ? r.size * PT_MM * base.mmPx : undefined,
          fontFamily: r.font === 'heading' ? '"Plus Jakarta Sans", system-ui, sans-serif' : undefined,
        }}>{r.text}</span>
      ))}
    </>
  );
}

/** Görsel yüklenemezse kırık resim simgesi yerine boşluk kalır (kutunun çerçevesi seçimde yine görünür). */
const hideBroken = (e: SyntheticEvent<HTMLImageElement>) => { e.currentTarget.style.visibility = 'hidden'; };

const SHAPE: Record<string, string> = { oval: 'rounded-[50%]', thought: 'rounded-[45%] border-dashed', shout: 'rounded-md border-[3px]', box: 'rounded-lg' };

function LiveLayer({ job, plan, page, mmPx, bodySize, artSrc }: {
  job: string; plan: Plan; page: PlanPage; mmPx: number; bodySize: number; artSrc: (a: PlanArt, w: number) => string | null;
}) {
  const d = plan.page;
  const fs = (pt: number | null | undefined) => (pt ?? bodySize) * PT_MM * mmPx;
  const color = plan.palette.text || '#2C2C2A';
  const art = page.art;
  const artUrl = art ? artSrc(art, Math.min(2400, Math.ceil((art.box.w * mmPx * 2) / 200) * 200 || 800)) : null;
  return (
    <div className="pointer-events-none absolute inset-0" aria-hidden>
      {art && (
        artUrl
          ? <img src={artUrl} alt="" className="absolute" draggable={false} onError={hideBroken}
              style={{ ...boxStyle(art.box, d), objectFit: art.fit, objectPosition: `${art.focus.x * 100}% ${art.focus.y * 100}%` }} />
          : <div className="absolute flex items-center justify-center bg-[repeating-linear-gradient(45deg,#f1f5f9_0_8px,#e2e8f0_8px_16px)] text-[11px] font-bold text-slate-500" style={boxStyle(art.box, d)}>Resim yok</div>
      )}
      {page.text && (
        <div className="absolute overflow-hidden" style={{ ...boxStyle(page.text.box, d), background: page.text.background ?? undefined, textAlign: page.text.align, fontSize: fs(page.text.size), lineHeight: 1.35, color }}>
          {page.text.blocks.map((b) => (
            <p key={b.id} style={{ margin: `0 0 ${0.5 * fs(page.text!.size)}px`, fontWeight: b.kind === 'heading' ? 800 : undefined, fontSize: b.kind === 'sound' ? fs(page.text!.size) * 1.25 : undefined }}>
              <Runs runs={b.runs} base={{ mmPx, color }} />
            </p>
          ))}
        </div>
      )}
      {page.bubbles.map((b) => {
        const c = b.color || (b.speaker ? plan.palette.characters[b.speaker] : null) || color;
        return (
          <div key={b.id}>
            {b.tail && (
              <svg className="absolute inset-0 h-full w-full" viewBox={`0 0 ${d.w} ${d.h}`} preserveAspectRatio="none">
                <line x1={b.box.x + b.box.w / 2} y1={b.box.y + b.box.h / 2} x2={b.tail.x} y2={b.tail.y} stroke="#1B1F2A" strokeWidth={0.5} vectorEffect="non-scaling-stroke" />
              </svg>
            )}
            <div className={`absolute flex items-center justify-center border-2 border-[#1B1F2A] bg-white p-[4%] text-center ${SHAPE[b.shape] ?? SHAPE.oval}`}
              style={{ ...boxStyle(b.box, d), color: c, fontSize: fs(bodySize), lineHeight: 1.2, fontWeight: b.shape === 'shout' ? 800 : 600 }}>
              {b.text}
            </div>
          </div>
        );
      })}
      {[...page.figures.map((f) => ({ z: f.z, el: (
        <img key={f.id} src={studioPlanApi.assetUrl(job, f.asset, Math.min(1600, Math.ceil((f.box.w * mmPx * 2) / 200) * 200 || 400))} alt="" draggable={false} onError={hideBroken}
          className="absolute object-contain" style={{ ...boxStyle(f.box, d), transform: `rotate(${f.rotate}deg) scaleX(${f.flip ? -1 : 1})` }} />
      ) })), ...page.texts.map((t) => ({ z: t.z, el: <FreeTextLive key={t.id} t={t} d={d} fs={fs(t.size)} mmPx={mmPx} color={color} /> })),
      ...shapesOf(page).map((sh) => ({ z: sh.z, el: <ShapeLive key={sh.id} s={sh} plan={plan} fs={fs(sh.text_size ?? 14)} mmPx={mmPx} /> }))]
        .sort((a, b) => a.z - b.z).map((x) => x.el)}
    </div>
  );
}

/** Efekt yazının tarayıcı taslağı: dış çizgi, gölge, harf harf renk, patlama zemini ve açı. Kavis/dalga dizgide
 *  harf harf çizilir; taslakta düz satır kalır (kaydedilince gerçek önizleme gelir). */
function FreeTextLive({ t, d, fs, mmPx, color }: { t: PlanFreeText; d: PageDims; fs: number; mmPx: number; color: string }) {
  const e: PlanEffect | null | undefined = t.effect;
  const p = e?.params ?? {};
  const style: CSSProperties = { ...boxStyle(t.box, d), textAlign: t.align, fontSize: fs, background: t.background ?? undefined, lineHeight: 1.2, color };
  if (e) {
    if (typeof p.angle === 'number') style.transform = `rotate(${p.angle}deg)`;
    if (e.style === 'outline' || p.outline) style.WebkitTextStroke = `${Math.max(0.5, (p.outline_w ?? 0.6) * mmPx)}px ${p.outline ?? '#FFFFFF'}`;
    if (e.style === 'shadow' || e.style === 'stacked' || p.shadow) {
      style.textShadow = `${(p.shadow_dx ?? 0.8) * mmPx}px ${(p.shadow_dy ?? 0.8) * mmPx}px 0 ${p.shadow ?? '#1F3B73'}`;
    }
    if (e.style === 'burst') {
      style.background = p.burst_fill ?? '#FAC775';
      style.clipPath = 'polygon(50% 0,61% 20%,85% 8%,78% 33%,100% 42%,80% 58%,93% 82%,67% 76%,58% 100%,45% 80%,22% 94%,24% 69%,0 58%,18% 42%,6% 18%,32% 22%)';
      style.display = 'flex'; style.alignItems = 'center'; style.justifyContent = 'center'; style.padding = '12%';
    }
  }
  const colors = e && (e.style === 'rainbow' || e.style === 'bounce') && Array.isArray(p.colors) && p.colors.length ? p.colors as string[] : null;
  return (
    <div className="absolute overflow-hidden" style={style}>
      {colors
        ? [...t.runs.map((r) => r.text).join('')].map((ch, i) => (
            <span key={i} style={{ color: colors[i % colors.length], display: e?.style === 'bounce' ? 'inline-block' : undefined,
              transform: e?.style === 'bounce' ? `translateY(${i % 2 ? -0.08 : 0.08}em)` : undefined }}>{ch}</span>))
        : <Runs runs={t.runs} base={{ mmPx, color }} />}
    </div>
  );
}

const ROUND: Record<string, string> = { cloud: '9999px', badge: '9999px', heart: '45% 45% 12% 12%', note: '2px', sign: '6px', scroll: '14px', ribbon: '2px' };
const POLY: Record<string, string> = {
  star: 'polygon(50% 0,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%)',
  burst: 'polygon(50% 0,61% 20%,85% 8%,78% 33%,100% 42%,80% 58%,93% 82%,67% 76%,58% 100%,45% 80%,22% 94%,24% 69%,0 58%,18% 42%,6% 18%,32% 22%)',
  arrow: 'polygon(0 35%,70% 35%,70% 10%,100% 50%,70% 90%,70% 65%,0 65%)',
  envelope: 'polygon(0 0,100% 0,100% 100%,0 100%)',
};

/** Süs/şeklin tarayıcı taslağı: dolgu, çizgi, saydamlık ve yazısı; asıl çizim dizgide vektördür. */
function ShapeLive({ s, plan, fs, mmPx }: { s: PlanShape; plan: Plan; fs: number; mmPx: number }) {
  const d = plan.page;
  const outline = s.kind === 'frame' || s.kind === 'corner' || s.kind === 'line';
  const fill = outline ? 'transparent' : s.fill ?? plan.palette.colors[0]?.hex ?? '#F2E3C6';
  const style: CSSProperties = {
    ...boxStyle(s.box, d),
    background: POLY[s.kind] || !outline ? fill : 'transparent',
    border: POLY[s.kind] ? undefined : `${Math.max(1, (s.stroke_w ?? 0.6) * mmPx)}px ${s.kind === 'frame' && (s.params as { style?: string } | undefined)?.style === 'dotted' ? 'dotted' : 'solid'} ${s.stroke ?? plan.palette.text}`,
    borderRadius: ROUND[s.kind],
    clipPath: POLY[s.kind],
    opacity: s.opacity ?? 1,
    transform: `rotate(${s.rotate ?? 0}deg) scaleX(${s.flip ? -1 : 1})`,
    display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: '6%', lineHeight: 1.15,
    fontSize: fs, overflow: 'hidden',
  };
  return (
    <div className="absolute" style={style}>
      {s.runs?.length ? <span><Runs runs={s.runs} base={{ mmPx, color: plan.palette.text }} /></span> : null}
    </div>
  );
}
