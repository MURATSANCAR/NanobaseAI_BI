import type { Box, CatalogItem, ColorRole, Effect, EffectParams, EffectStyle, PageGeom, Palette, Run, Shape } from './types';

/** Öğelerin saf yardımcıları: kimlik, varsayılan kutu, palet rolleri, yazı parçası düzenleme. Ekran bileşeni yok. */

export function newId(prefix: 's'): string {
  const b = new Uint8Array(4);
  crypto.getRandomValues(b);
  return `${prefix}_${Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')}`;
}

const round = (v: number) => Math.round(v * 10) / 10;

/** Sayfa bilinmiyorsa (plan henüz yok) sözleşmedeki örnek ölçü kullanılır; C bırakırken kutuyu yeniden konumlar. */
const FALLBACK_PAGE: PageGeom = { w: 169, h: 231, bleed: 2, safe: 8 };

/** Güvenli alan (taşma payı + güvenli pay içi). */
export function safeArea(page: PageGeom | null | undefined): Box {
  const p = page ?? FALLBACK_PAGE;
  const m = p.bleed + p.safe;
  return { x: m, y: m, w: p.w - 2 * m, h: p.h - 2 * m };
}

/** Katalog türünün varsayılan kutusu: tam sayfa türler güvenli alanın tamamı; diğerleri güvenli alan eninin
 *  %40'ı, oranına göre boy (boy güvenli alanın %40'ını geçerse boydan küçültülür), güvenli alanın ortasında. */
export function defaultBox(item: CatalogItem, page: PageGeom | null | undefined): Box {
  const s = safeArea(page);
  if (item.full_page || !item.aspect) return { x: round(s.x), y: round(s.y), w: round(s.w), h: round(s.h) };
  let w = s.w * 0.4;
  let h = w / item.aspect;
  if (h > s.h * 0.4) {
    h = s.h * 0.4;
    w = h * item.aspect;
  }
  return { x: round(s.x + (s.w - w) / 2), y: round(s.y + (s.h - h) / 2), w: round(w), h: round(h) };
}

/** Kutuyu verilen noktaya ortalar (sürükle-bırakta bırakılan yer, mm). */
export function centerBoxAt(box: Box, x: number, y: number): Box {
  return { ...box, x: round(x - box.w / 2), y: round(y - box.h / 2) };
}

function paramDefaults(item: CatalogItem): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const p of item.params) if (p.default !== undefined) out[p.key] = p.default;
  return out;
}

/** Katalog türünden sayfaya eklenmeye hazır şekil. Renkler boş: motor kitabın paletinden rolle doldurur. */
export function shapeFromCatalog(item: CatalogItem, opts: { page?: PageGeom | null; z?: number; style?: string | null } = {}): Shape {
  const params = paramDefaults(item);
  const style = opts.style ?? item.styles[0]?.value;
  if (style) params.style = style;
  return {
    id: newId('s'),
    kind: item.kind,
    box: defaultBox(item, opts.page),
    rotate: 0,
    flip: false,
    z: opts.z ?? 3,
    fill: null,
    stroke: null,
    stroke_w: item.stroke_w ?? 0.6,
    opacity: 1,
    params,
    ...(item.text ? { runs: [{ text: item.name, weight: 800 as const, font: 'heading' as const, source: 'editor' as const }], text_size: item.text_size ?? 18 } : {}),
  };
}

// ---------------------------------------------------------------- palet

export const ROLE_LABEL: Record<ColorRole, string> = { accent: 'Vurgu', soft: 'Açık zemin', ink: 'Mürekkep' };

function hexToRgb(hex: string): [number, number, number] | null {
  const m = /^#?([0-9a-f]{6}|[0-9a-f]{3})/i.exec(hex.trim());
  if (!m) return null;
  const h = m[1].length === 3 ? m[1].split('').map((c) => c + c).join('') : m[1];
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
}

export function mix(hex: string, withHex: string, t: number): string {
  const a = hexToRgb(hex);
  const b = hexToRgb(withHex);
  if (!a || !b) return hex;
  return `#${a.map((v, i) => Math.round(v + (b[i] - v) * t).toString(16).padStart(2, '0')).join('').toUpperCase()}`;
}

/** Rolün paletteki karşılığı (ekrandaki «otomatik» örneği için; kaydedilen değer null kalır). */
export function roleColor(palette: Palette | null | undefined, r: ColorRole): string {
  const ink = palette?.text || '#2C2C2A';
  const used = new Set(Object.values(palette?.characters ?? {}).map((c) => c.toUpperCase()));
  const accent = palette?.accent || palette?.colors.find((c) => !used.has(c.hex.toUpperCase()))?.hex || palette?.colors[0]?.hex || '#1F3B73';
  if (r === 'ink') return ink;
  if (r === 'accent') return accent;
  return palette?.soft || mix(accent, '#FFFFFF', 0.78);
}

export type Swatch = { hex: string; name: string };

/** Seçilebilir renkler: kitabın paleti + gövde metni rengi + açık zemin (vurgunun açığı) + beyaz; aynı renk bir kez. */
export function swatches(palette: Palette | null | undefined): Swatch[] {
  const out: Swatch[] = [];
  const add = (hex: string | null | undefined, name: string) => {
    if (!hex || out.some((s) => s.hex.toUpperCase() === hex.toUpperCase())) return;
    out.push({ hex, name });
  };
  for (const c of palette?.colors ?? []) add(c.hex, c.name);
  add(palette?.text || '#2C2C2A', 'Metin rengi');
  add(roleColor(palette, 'soft'), 'Açık zemin');
  add('#FFFFFF', 'Beyaz');
  return out;
}

// ---------------------------------------------------------------- efekt

export const EFFECT_LABEL: Record<EffectStyle, string> = {
  burst: 'Patlama', wave: 'Dalga', arc: 'Kavis', shadow: 'Gölge',
  outline: 'Dış çizgi', stacked: 'Katmanlı', bounce: 'Zıplayan', rainbow: 'Gökkuşağı',
};

/** Stil seçilince ilk değerler; önceki efektte aynı alan varsa o korunur. */
export function effectDefaults(style: EffectStyle, palette: Palette | null | undefined, prev?: EffectParams): EffectParams {
  const accent = roleColor(palette, 'accent');
  const ink = roleColor(palette, 'ink');
  const cols = (palette?.colors ?? []).map((c) => c.hex);
  const d: Record<EffectStyle, EffectParams> = {
    burst: { burst_fill: roleColor(palette, 'soft'), burst_stroke: ink, angle: -8 },
    wave: { curve: 0.5 },
    arc: { curve: 0.6 },
    shadow: { shadow: accent, shadow_dx: 0.8, shadow_dy: 0.8 },
    outline: { outline: '#FFFFFF', outline_w: 0.8 },
    stacked: { shadow: accent, shadow_dx: 0.6, shadow_dy: 0.6 },
    bounce: { colors: cols.slice(0, 3).length ? cols.slice(0, 3) : [accent, ink] },
    rainbow: { colors: cols.length ? cols : [accent, ink] },
  };
  const out: EffectParams = { ...d[style] };
  if (prev) for (const k of Object.keys(out) as (keyof EffectParams)[]) if (prev[k] !== undefined) (out as Record<string, unknown>)[k] = prev[k];
  return out;
}

export function setEffectStyle(style: EffectStyle | null, prev: Effect | null, palette: Palette | null | undefined): Effect | null {
  if (!style) return null;
  return { style, params: effectDefaults(style, palette, prev?.params) };
}

// ---------------------------------------------------------------- yazı parçaları
// Metin kutusunda düz metin düzenlenir; parçalar (renk/kalınlık) değişikliğin çevresinde korunur.

export const runsText = (runs: Run[] | undefined) => (runs ?? []).map((r) => r.text).join('');

const sameStyle = (a: Run, b: Run) =>
  (a.color ?? null) === (b.color ?? null) && (a.weight ?? 400) === (b.weight ?? 400) && (a.size ?? null) === (b.size ?? null)
  && (a.font ?? 'body') === (b.font ?? 'body') && (a.source ?? null) === (b.source ?? null);

function merge(runs: Run[]): Run[] {
  const out: Run[] = [];
  for (const r of runs) {
    if (!r.text) continue;
    const last = out[out.length - 1];
    if (last && sameStyle(last, r)) out[out.length - 1] = { ...last, text: last.text + r.text };
    else out.push({ ...r });
  }
  return out;
}

/** `pos` karakterinde parça sınırı açar; sınırın solundaki parça sayısını da döner. */
function splitAt(runs: Run[], pos: number): { runs: Run[]; index: number } {
  const out: Run[] = [];
  let at = 0;
  let index = -1;
  for (const r of runs) {
    const end = at + r.text.length;
    if (index < 0 && pos <= at) index = out.length;
    if (pos > at && pos < end) {
      out.push({ ...r, text: r.text.slice(0, pos - at) });
      index = out.length;
      out.push({ ...r, text: r.text.slice(pos - at) });
    } else out.push(r);
    at = end;
  }
  return { runs: out, index: index < 0 ? out.length : index };
}

/** Düz metin değişikliğini parçalara uygular: ortak baş/son korunur, araya yazılan metin solundaki parçanın
 *  biçimini alır (baştaysa sağındakinin). */
export function editRuns(runs: Run[] | undefined, next: string): Run[] {
  const cur = runs ?? [];
  const prevText = runsText(cur);
  if (prevText === next) return cur;
  let p = 0;
  while (p < prevText.length && p < next.length && prevText[p] === next[p]) p++;
  let s = 0;
  while (s < prevText.length - p && s < next.length - p && prevText[prevText.length - 1 - s] === next[next.length - 1 - s]) s++;
  const inserted = next.slice(p, next.length - s);
  const a = splitAt(cur, p);
  const b = splitAt(a.runs, prevText.length - s);
  const left = b.runs.slice(0, a.index);
  const right = b.runs.slice(b.index);
  const like = left[left.length - 1] ?? right[0] ?? { text: '' };
  const mid: Run[] = inserted ? [{ ...like, text: inserted }] : [];
  return merge([...left, ...mid, ...right]);
}

/** [start, end) aralığına biçim verir; aralık boşsa bütün metne. Elle verilen biçim `source: "editor"` olur. */
export function styleRuns(runs: Run[] | undefined, start: number, end: number, patch: Partial<Run>): Run[] {
  const cur = runs ?? [];
  const total = runsText(cur).length;
  const [s, e] = start === end ? [0, total] : [Math.min(start, end), Math.max(start, end)];
  const a = splitAt(cur, s);
  const b = splitAt(a.runs, e);
  const out = b.runs.map((r, i) => (i >= a.index && i < b.index ? { ...r, ...patch, source: 'editor' as const } : r));
  return merge(out);
}
