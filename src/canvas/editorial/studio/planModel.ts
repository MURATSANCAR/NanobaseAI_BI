import type { Plan, PlanBox, PlanLayout, PlanPage, PlanPalette, PlanRun } from '../../engine';

/** Sayfa planının saf yardımcıları: kimlik, karşılaştırma, hazır yerleşimler, yapışma, run düzenleme,
 *  kontrast ve üç yollu birleştirme. React'e bağlı değildir. */

export type PageDims = Plan['page'];

// ------------------------------------------------------------------ kimlik ve karşılaştırma
export const uid = (prefix: string) => {
  const b = new Uint8Array(4);
  crypto.getRandomValues(b);
  return prefix + Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
};

/** Anahtar sırasından bağımsız JSON; eşitlik ve önbellek anahtarı için. */
export function stable(v: unknown): string {
  if (v === undefined) return 'null';
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return `[${v.map(stable).join(',')}]`;
  const o = v as Record<string, unknown>;
  return `{${Object.keys(o).filter((k) => o[k] !== undefined).sort().map((k) => `${JSON.stringify(k)}:${stable(o[k])}`).join(',')}}`;
}
export const same = (a: unknown, b: unknown) => stable(a) === stable(b);

/** Kısa, kararlı özet (FNV-1a); önizleme adresinin önbellek anahtarı. */
export function hash(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(36);
}

export const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
export const r1 = (n: number) => Math.round(n * 10) / 10;

// ------------------------------------------------------------------ hazır yerleşimler
export const LAYOUTS: { key: PlanLayout; label: string; needsArtOnly?: boolean }[] = [
  { key: 'art-top', label: 'Resim üstte' },
  { key: 'art-bottom', label: 'Resim altta' },
  { key: 'art-left', label: 'Resim solda' },
  { key: 'art-right', label: 'Resim sağda' },
  { key: 'text-over-art', label: 'Resim üstüne yazı' },
  { key: 'art-full', label: 'Tam sayfa resim', needsArtOnly: true },
  { key: 'text-only', label: 'Yalnız yazı' },
  { key: 'blank', label: 'Boş sayfa', needsArtOnly: true },
];

/** Yerleşimin kutuları (mm). Sunucunun `plan.preset`'iyle aynı kural; sunucu döndüğünde onun değeri geçerlidir. */
export function preset(layout: PlanLayout, d: PageDims): { art: PlanBox | null; text: PlanBox | null; background?: string | null } {
  const { w: W, h: H, safe } = d;
  const s = d.bleed + safe;
  const artH = r1(H * 0.52);
  switch (layout) {
    case 'art-top': return { art: { x: 0, y: 0, w: W, h: artH }, text: { x: s, y: r1(artH + safe), w: r1(W - 2 * s), h: r1(H - s - artH - safe) } };
    case 'art-bottom': return { art: { x: 0, y: r1(H - artH), w: W, h: artH }, text: { x: s, y: s, w: r1(W - 2 * s), h: r1(H - artH - safe - s) } };
    case 'art-left': return { art: { x: 0, y: 0, w: r1(W / 2), h: H }, text: { x: r1(W / 2 + safe), y: s, w: r1(W / 2 - safe - s), h: r1(H - 2 * s) } };
    case 'art-right': return { art: { x: r1(W / 2), y: 0, w: r1(W / 2), h: H }, text: { x: s, y: s, w: r1(W / 2 - safe - s), h: r1(H - 2 * s) } };
    case 'text-over-art': {
      const ty = r1(H * 0.62);
      return { art: { x: 0, y: 0, w: W, h: H }, text: { x: s, y: ty, w: r1(W - 2 * s), h: r1(H - s - ty) }, background: '#FFFFFFE6' };
    }
    case 'art-full': return { art: { x: 0, y: 0, w: W, h: H }, text: null };
    case 'text-only': return { art: null, text: { x: s, y: s, w: r1(W - 2 * s), h: r1(H - 2 * s) } };
    case 'blank': return { art: null, text: null };
    default: return { art: null, text: null };
  }
}

export const hasText = (p: PlanPage) => !!p.text && p.text.blocks.some((b) => b.runs.some((r) => r.text.trim()));

/** Sayfaya yerleşim uygular. Metin ve resim kaybolmaz: metinli sayfada metinsiz yerleşim seçilemez
 *  (ekran düğmeyi kapatır); resimsiz sayfaya resimli yerleşimde `art.id = null` gider, sunucu kimlik verir. */
export function applyLayout(p: PlanPage, layout: PlanLayout, d: PageDims): PlanPage {
  const b = preset(layout, d);
  const next = clone(p);
  next.layout = layout;
  if (b.art) next.art = { id: p.art?.id ?? null, box: b.art, fit: p.art?.fit ?? 'cover', focus: p.art?.focus ?? { x: 0.5, y: 0.5 } };
  else next.art = null;
  if (b.text) next.text = { box: b.text, align: p.text?.align ?? 'left', size: p.text?.size ?? null,
    background: b.background ?? (layout === 'text-over-art' ? '#FFFFFFE6' : null), blocks: p.text?.blocks ?? [] };
  else next.text = null;
  return next;
}

// ------------------------------------------------------------------ geometri
export const safeRect = (d: PageDims): PlanBox => {
  const s = d.bleed + d.safe;
  return { x: s, y: s, w: d.w - 2 * s, h: d.h - 2 * s };
};
export const trimRect = (d: PageDims): PlanBox => ({ x: d.bleed, y: d.bleed, w: d.w - 2 * d.bleed, h: d.h - 2 * d.bleed });

/** Kutunun kenarlarını yakındaki kılavuza (güvenli alan, kesim, taşma kenarı, sayfa ortası) çeker. */
export function snapBox(b: PlanBox, d: PageDims, threshold: number, moving: boolean): PlanBox {
  const sr = safeRect(d);
  const xs = [0, d.bleed, sr.x, d.w / 2, sr.x + sr.w, d.w - d.bleed, d.w];
  const ys = [0, d.bleed, sr.y, d.h / 2, sr.y + sr.h, d.h - d.bleed, d.h];
  const pick = (edges: number[], lines: number[]) => {
    let best: number | null = null;
    for (const e of edges) for (const l of lines) {
      const delta = l - e;
      if (Math.abs(delta) <= threshold && (best === null || Math.abs(delta) < Math.abs(best))) best = delta;
    }
    return best ?? 0;
  };
  if (moving) {
    return { ...b, x: r1(b.x + pick([b.x, b.x + b.w / 2, b.x + b.w], xs)), y: r1(b.y + pick([b.y, b.y + b.h / 2, b.y + b.h], ys)) };
  }
  // Boyutlandırmada yalnız sağ/alt kenar çekilir (sol/üst kenarı işleyen tutamak kutuyu zaten taşıyor).
  const dx = pick([b.x + b.w], xs);
  const dy = pick([b.y + b.h], ys);
  return { ...b, w: r1(b.w + dx), h: r1(b.h + dy) };
}

export const outsideSafe = (b: PlanBox, d: PageDims) => {
  const s = safeRect(d);
  const e = 0.05;
  return b.x < s.x - e || b.y < s.y - e || b.x + b.w > s.x + s.w + e || b.y + b.h > s.y + s.h + e;
};

// ------------------------------------------------------------------ run düzenleme
export const runsText = (runs: PlanRun[]) => runs.map((r) => r.text).join('');

const sameStyle = (a: PlanRun, b: PlanRun) =>
  (a.color ?? null) === (b.color ?? null) && (a.weight ?? null) === (b.weight ?? null) && (a.size ?? null) === (b.size ?? null)
  && (a.font ?? null) === (b.font ?? null) && (a.source ?? null) === (b.source ?? null);

export function normalizeRuns(runs: PlanRun[]): PlanRun[] {
  const out: PlanRun[] = [];
  for (const r of runs) {
    if (!r.text) continue;
    const last = out[out.length - 1];
    if (last && sameStyle(last, r)) last.text += r.text;
    else out.push({ ...r });
  }
  return out;
}

/** Düz metin değişikliğini run'lara işler: değişmeyen baş ve son korunur, araya yazılan metin imlecin
 *  solundaki run'ın biçimini alır. Böylece renkli sözcüğün içinde yazım düzeltmesi renk kaybettirmez. */
export function editRuns(runs: PlanRun[], next: string): PlanRun[] {
  const prev = runsText(runs);
  if (prev === next) return runs;
  if (!runs.length) return next ? [{ text: next }] : [];
  let p = 0;
  while (p < prev.length && p < next.length && prev[p] === next[p]) p++;
  let s = 0;
  while (s < prev.length - p && s < next.length - p && prev[prev.length - 1 - s] === next[next.length - 1 - s]) s++;
  const delEnd = prev.length - s;
  const insert = next.slice(p, next.length - s);
  const style = runAt(runs, p > 0 ? p - 1 : 0);
  return normalizeRuns([...sliceRuns(runs, 0, p), ...(insert ? [{ ...style, text: insert }] : []), ...sliceRuns(runs, delEnd, prev.length)]);
}

function sliceRuns(runs: PlanRun[], start: number, end: number): PlanRun[] {
  const out: PlanRun[] = [];
  let pos = 0;
  for (const r of runs) {
    const a = pos;
    const b = pos + r.text.length;
    pos = b;
    const i = Math.max(start, a);
    const j = Math.min(end, b);
    if (j > i) out.push({ ...r, text: r.text.slice(i - a, j - a) });
  }
  return out;
}

function runAt(runs: PlanRun[], i: number): PlanRun {
  let pos = 0;
  for (const r of runs) {
    if (i < pos + r.text.length) return r;
    pos += r.text.length;
  }
  return runs[runs.length - 1] ?? { text: '' };
}

/** [start, end) aralığına biçim verir; o aralık `source:"editor"` olur (otomatik kural dokunmaz). */
export function styleRange(runs: PlanRun[], start: number, end: number, patch: Partial<PlanRun>): PlanRun[] {
  if (end <= start) return runs;
  const out: PlanRun[] = [];
  let pos = 0;
  for (const r of runs) {
    const a = pos;
    const b = pos + r.text.length;
    pos = b;
    if (b <= start || a >= end) { out.push({ ...r }); continue; }
    const i = Math.max(start, a) - a;
    const j = Math.min(end, b) - a;
    if (i > 0) out.push({ ...r, text: r.text.slice(0, i) });
    const mid: PlanRun = { ...r, ...patch, text: r.text.slice(i, j), source: 'editor' };
    for (const k of Object.keys(mid) as (keyof PlanRun)[]) if (mid[k] === undefined) delete mid[k];
    out.push(mid);
    if (j < r.text.length) out.push({ ...r, text: r.text.slice(j) });
  }
  return normalizeRuns(out);
}

// ------------------------------------------------------------------ renk
function lum(hex: string): number | null {
  const m = /^#?([0-9a-f]{6})/i.exec(hex.trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const x = v / 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
/** Beyaz zemine karşı WCAG kontrastı; geçersiz renkte null. */
export function contrastOnWhite(hex: string): number | null {
  const l = lum(hex);
  return l === null ? null : 1.05 / (l + 0.05);
}
export const isHex = (s: string) => /^#[0-9a-f]{6}([0-9a-f]{2})?$/i.test(s.trim());

// ------------------------------------------------------------------ üç yollu birleştirme
type WithId = { id: string };

function mergeList<T extends WithId>(base: T[], mine: T[], theirs: T[]): { value: T[]; conflict: boolean } {
  const B = new Map(base.map((x) => [x.id, x]));
  const M = new Map(mine.map((x) => [x.id, x]));
  const Th = new Map(theirs.map((x) => [x.id, x]));
  let conflict = false;
  const out: T[] = [];
  const ids = [...theirs.map((x) => x.id), ...mine.map((x) => x.id).filter((id) => !Th.has(id))];
  for (const id of ids) {
    const b = B.get(id);
    const m = M.get(id);
    const t = Th.get(id);
    if (!b) { // bir taraf ekledi
      if (m && t) { if (!same(m, t)) conflict = true; out.push(m); } else out.push((m ?? t)!);
      continue;
    }
    if (!m && !t) continue;
    if (!m) { if (!same(t, b)) conflict = true; continue; }          // ben sildim, o değiştirdiyse çakışma
    if (!t) { if (!same(m, b)) conflict = true; continue; }          // o sildi, ben değiştirdiysem çakışma
    if (same(m, b)) out.push(t);
    else if (same(t, b) || same(m, t)) out.push(m);
    else { conflict = true; out.push(m); }
  }
  return { value: out, conflict };
}

/** Sayfa düzeyinde üç yollu birleştirme: alan alan, liste ögeleri kimlikle. Aynı alanı iki taraf da
 *  farklı değiştirdiyse `conflict` döner; ekran kullanıcıya sorar. */
export function mergePage(base: PlanPage, mine: PlanPage, theirs: PlanPage): { page: PlanPage; conflict: boolean } {
  let conflict = false;
  const field = <K extends keyof PlanPage>(k: K): PlanPage[K] => {
    const b = base[k]; const m = mine[k]; const t = theirs[k];
    if (same(m, b)) return t;
    if (same(t, b) || same(m, t)) return m;
    conflict = true;
    return m;
  };
  const lists = (k: 'bubbles' | 'figures' | 'texts' | 'shapes') => {
    const r = mergeList((base[k] ?? []) as WithId[], (mine[k] ?? []) as WithId[], (theirs[k] ?? []) as WithId[]);
    if (r.conflict) conflict = true;
    return r.value;
  };
  const shapes = lists('shapes') as NonNullable<PlanPage['shapes']>;
  const page: PlanPage = {
    ...theirs,
    layout: field('layout'),
    chapter: field('chapter'),
    art: field('art'),
    text: field('text'),
    bubbles: lists('bubbles') as PlanPage['bubbles'],
    figures: lists('figures') as PlanPage['figures'],
    texts: lists('texts') as PlanPage['texts'],
    ...(theirs.shapes || mine.shapes ? { shapes } : {}),
    overflow: theirs.overflow,
  };
  return { page, conflict };
}

export function mergePalette(base: PlanPalette, mine: PlanPalette, theirs: PlanPalette): { palette: PlanPalette; conflict: boolean } {
  let conflict = false;
  const f = <K extends keyof PlanPalette>(k: K): PlanPalette[K] => {
    const b = base[k]; const m = mine[k]; const t = theirs[k];
    if (same(m, b)) return t;
    if (same(t, b) || same(m, t)) return m;
    conflict = true;
    return m;
  };
  return { palette: { colors: f('colors'), text: f('text'), characters: f('characters') }, conflict };
}

/** Sayfa sırası: benim istediğim sıra, sunucuda artık olmayanlar düşer, sunucuda yeni olanlar
 *  sunucudaki komşusunun arkasına girer. */
export function mergeOrder(desired: string[], server: string[]): string[] {
  const live = new Set(server);
  const out = desired.filter((id) => live.has(id));
  const have = new Set(out);
  server.forEach((id, i) => {
    if (have.has(id)) return;
    const prev = server.slice(0, i).reverse().find((x) => have.has(x));
    const at = prev ? out.indexOf(prev) + 1 : 0;
    out.splice(at, 0, id);
    have.add(id);
  });
  return out;
}
