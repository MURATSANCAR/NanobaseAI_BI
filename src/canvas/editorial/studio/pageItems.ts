import type { Plan, PlanAsset, PlanBox, PlanPage, PlanShape } from '../../engine';

/** Sayfadaki seçilebilir ögeler ve kutularının okunup yazılması (tuval ve sağ panel ortak kullanır). */

export type ItemKind = 'art' | 'text' | 'bubble' | 'figure' | 'free' | 'shape';
export type ItemRef = { kind: ItemKind; id: string };

export const ITEM_LABEL: Record<ItemKind, string> = {
  art: 'Sayfa resmi', text: 'Metin kutusu', bubble: 'Balon', figure: 'Figür', free: 'Serbest yazı', shape: 'Süs / şekil',
};

export const itemKey = (r: ItemRef) => `${r.kind}:${r.id}`;
export const shapesOf = (p: PlanPage): PlanShape[] => p.shapes ?? [];

export type PageItem = ItemRef & { box: PlanBox; z: number; rotate: number; flip: boolean; asset: string | null; image: boolean };

/** Döndürülebilen ögeler: figür ve şekil (sözleşmede `rotate` alanı olanlar). */
export const rotatable = (k: ItemKind) => k === 'figure' || k === 'shape';

/** Katman sırası sözleşmedeki gibi: resim 0, yazı kutusu 1, balonlar 2, figür/serbest yazı/şekil kendi z'si (≥ 3). */
export function pageItems(p: PlanPage): PageItem[] {
  const out: PageItem[] = [];
  if (p.art) out.push({ kind: 'art', id: 'art', box: p.art.box, z: 0, rotate: 0, flip: false, asset: p.art.asset ?? null, image: true });
  if (p.text) out.push({ kind: 'text', id: 'text', box: p.text.box, z: 1, rotate: 0, flip: false, asset: null, image: false });
  for (const b of p.bubbles) out.push({ kind: 'bubble', id: b.id, box: b.box, z: 2, rotate: 0, flip: false, asset: null, image: false });
  for (const f of p.figures) out.push({ kind: 'figure', id: f.id, box: f.box, z: Math.max(3, f.z), rotate: f.rotate, flip: f.flip, asset: f.asset, image: true });
  for (const t of p.texts) out.push({ kind: 'free', id: t.id, box: t.box, z: Math.max(3, t.z), rotate: 0, flip: false, asset: null, image: false });
  for (const s of shapesOf(p)) out.push({ kind: 'shape', id: s.id, box: s.box, z: Math.max(3, s.z), rotate: s.rotate ?? 0, flip: !!s.flip, asset: null, image: false });
  return out.sort((a, b) => a.z - b.z);
}

export const findItem = (p: PlanPage, r: ItemRef | null) => (r ? pageItems(p).find((i) => i.kind === r.kind && i.id === r.id) ?? null : null);

/** Ögenin kutusunu (figür ve şekilde dönüşü de) değiştirir; resim/yazı kutusu oynayınca sayfa `custom` yerleşime geçer.
 *  Balon taşınınca kuyruk ucu konuşanda kalır (ucu ayrıca sürüklenir). */
export function withBox(p: PlanPage, r: ItemRef, box: PlanBox, rotate?: number): PlanPage {
  switch (r.kind) {
    case 'art': return p.art ? { ...p, layout: 'custom', art: { ...p.art, box } } : p;
    case 'text': return p.text ? { ...p, layout: 'custom', text: { ...p.text, box } } : p;
    case 'bubble': return { ...p, bubbles: p.bubbles.map((b) => (b.id === r.id ? { ...b, box } : b)) };
    case 'figure': return { ...p, figures: p.figures.map((f) => (f.id === r.id ? { ...f, box, rotate: rotate ?? f.rotate } : f)) };
    case 'free': return { ...p, texts: p.texts.map((t) => (t.id === r.id ? { ...t, box } : t)) };
    case 'shape': return { ...p, shapes: shapesOf(p).map((s) => (s.id === r.id ? { ...s, box, rotate: rotate ?? s.rotate } : s)) };
  }
}

export function removeItem(p: PlanPage, r: ItemRef): PlanPage {
  if (r.kind === 'bubble') return { ...p, bubbles: p.bubbles.filter((b) => b.id !== r.id) };
  if (r.kind === 'figure') return { ...p, figures: p.figures.filter((f) => f.id !== r.id) };
  if (r.kind === 'free') return { ...p, texts: p.texts.filter((t) => t.id !== r.id) };
  if (r.kind === 'shape') return { ...p, shapes: shapesOf(p).filter((s) => s.id !== r.id) };
  return p;
}

export const removable = (r: ItemRef | null) => !!r && (r.kind === 'bubble' || r.kind === 'figure' || r.kind === 'free' || r.kind === 'shape');

/** z sırası: figür, serbest yazı ve şekiller arasında öne/arkaya (hiçbiri 3'ün altına inmez). */
export function restack(p: PlanPage, r: ItemRef, dir: 'front' | 'back'): PlanPage {
  const layered = [
    ...p.figures.map((f) => ({ kind: 'figure', id: f.id, z: f.z })),
    ...p.texts.map((t) => ({ kind: 'free', id: t.id, z: t.z })),
    ...shapesOf(p).map((s) => ({ kind: 'shape', id: s.id, z: s.z })),
  ].sort((a, b) => a.z - b.z);
  const i = layered.findIndex((x) => x.kind === r.kind && x.id === r.id);
  if (i < 0) return p;
  const [me] = layered.splice(i, 1);
  if (dir === 'front') layered.push(me); else layered.unshift(me);
  const z = new Map(layered.map((x, k) => [`${x.kind}:${x.id}`, 3 + k]));
  return {
    ...p,
    figures: p.figures.map((f) => ({ ...f, z: z.get(`figure:${f.id}`) ?? f.z })),
    texts: p.texts.map((t) => ({ ...t, z: z.get(`free:${t.id}`) ?? t.z })),
    ...(p.shapes ? { shapes: p.shapes.map((s) => ({ ...s, z: z.get(`shape:${s.id}`) ?? s.z })) } : {}),
  };
}

export const nextZ = (p: PlanPage) => Math.max(2, ...p.figures.map((f) => f.z), ...p.texts.map((t) => t.z), ...shapesOf(p).map((s) => s.z)) + 1;

/** Kutudaki etkin çözünürlük (dpi): `cover` kırparak doldurur, `contain` sığdırır (figür/fotoğraf katmanı). */
export function effectiveDpi(a: PlanAsset | undefined, box: PlanBox, fit: 'cover' | 'contain' = 'contain'): number | null {
  if (!a || !a.w_px || !a.h_px || box.w <= 0 || box.h <= 0) return null;
  const dx = a.w_px / (box.w / 25.4);
  const dy = a.h_px / (box.h / 25.4);
  return Math.round(fit === 'cover' ? Math.min(dx, dy) : Math.max(dx, dy));
}
export const PRINT_DPI = 300;

export function itemDpi(plan: Plan, p: PlanPage, it: PageItem): number | null {
  if (!it.asset) return null;
  const a = plan.assets[it.asset];
  if (it.kind === 'art') return effectiveDpi(a, it.box, p.art?.fit ?? 'cover');
  return effectiveDpi(a, it.box, 'contain');
}
