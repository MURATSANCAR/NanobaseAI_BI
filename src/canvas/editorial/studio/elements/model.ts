import type {
  Box, CatalogEffect, CatalogItem, CatalogStyle, ColorRole, Effect, EffectParams, EffectStyle, PageGeom, Palette, RoleColors, Run, Shape,
} from './types';

/** Öğelerin saf yardımcıları: kimlik, varsayılan kutu, hazır biçim, palet rolleri, yazı parçası düzenleme. Ekran
 *  bileşeni yok. Varsayılanlar motorun kataloğundan gelir (tek kaynak); burada yalnız sayfaya yerleştirme hesabı. */

/** Şekil kimliği: `s_` + 8 onaltılık hane (motorun `new_shape`'iyle aynı biçim). */
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

/** Şeklin parametrelerine uyan hazır biçim (parametreleri şekildekilerle aynı olan ilk biçim); yoksa null. */
export function styleOf(item: CatalogItem | undefined, params: Record<string, unknown> | undefined): CatalogStyle | null {
  if (!item) return null;
  const p = params ?? {};
  return item.styles.find((s) => Object.entries(s.params).every(([k, v]) => p[k] === v)) ?? null;
}

/** Yeni şeklin kutusu (motorun `default_box` kuralı): genişlik kesim eninin `width` oranı, boy orana göre; `page`
 *  yerleşimi güvenli payın yarısı içeride tam sayfa, `corner` sol üst köşe, `center` sayfanın ortası. Kutu güvenli
 *  alana sığmazsa oran korunarak küçülür (yalnız ilk yerleşim; editör sonra istediği kadar büyütür). */
export function defaultBox(item: CatalogItem, page: PageGeom | null | undefined, style?: CatalogStyle | null): Box {
  const p = page ?? FALLBACK_PAGE;
  const b = style?.box ?? {};
  const where = b.place ?? item.place;
  const ratio = b.ratio ?? item.aspect ?? 1;
  const half = p.safe / 2;
  if (where === 'page') {
    return { x: round(p.bleed + half), y: round(p.bleed + half), w: round(p.w - 2 * p.bleed - p.safe), h: round(p.h - 2 * p.bleed - p.safe) };
  }
  const s = safeArea(p);
  let w = (p.w - 2 * p.bleed) * (b.w ?? item.width);
  let h = w / (ratio > 0 ? ratio : 1);
  const k = Math.min(1, s.w / w, s.h / h);
  w *= k;
  h *= k;
  if (where === 'corner') return { x: round(p.bleed + half), y: round(p.bleed + half), w: round(w), h: round(h) };
  return { x: round((p.w - w) / 2), y: round((p.h - h) / 2), w: round(w), h: round(h) };
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

/** Katalog türünden sayfaya eklenmeye hazır şekil (motorun `new_shape`'iyle aynı alanlar). Renk, çizgi kalınlığı ve
 *  punto boş: dizgi türün varsayılan rolünü, kalınlığını kullanır, yazıyı şekle sığdırır. `style` hazır biçimin
 *  anahtarı; verilmezse türün ilk biçimi. */
export function shapeFromCatalog(item: CatalogItem, opts: { page?: PageGeom | null; z?: number; style?: string | null } = {}): Shape {
  const style = item.styles.find((s) => s.value === opts.style) ?? item.styles[0] ?? null;
  return {
    id: newId('s'),
    kind: item.kind,
    box: defaultBox(item, opts.page, style),
    rotate: 0,
    flip: false,
    z: opts.z ?? 3,
    fill: null,
    stroke: null,
    stroke_w: null,
    opacity: 1,
    params: { ...paramDefaults(item), ...(style?.params ?? {}) },
    runs: item.text ? item.runs.map((r) => ({ ...r })) : [],
    text_size: null,
  };
}

/** Hazır biçimi mevcut şekle uygular: biçimin parametreleri yazılır, kutu ve öbür ayarlar korunur. */
export function applyStyle(shape: Shape, style: CatalogStyle): Shape {
  return { ...shape, params: { ...(shape.params ?? {}), ...style.params } };
}

// ---------------------------------------------------------------- palet

export const ROLE_LABEL: Record<ColorRole, string> = {
  accent: 'Vurgu', accent2: 'İkinci renk', ink: 'Metin rengi', pop: 'Canlı vurgu', pop2: 'Canlı ikinci',
  sun: 'Güneş sarısı', rose: 'Gül kırmızısı', soft: 'Açık zemin', soft2: 'Açık ikinci', paper: 'Kâğıt',
  wood: 'Ahşap', bark: 'Koyu ahşap', deep: 'Koyu vurgu', white: 'Beyaz',
};

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

/** Rolün bu kitaptaki rengi: katalogdaki (dizgiyle aynı hesap) değer; katalog henüz gelmediyse paletten yaklaşık. */
export function roleColor(palette: Palette | null | undefined, r: ColorRole, roles?: RoleColors | null): string {
  const exact = roles?.[r]?.hex;
  if (exact) return exact;
  const ink = palette?.text || '#2C2C2A';
  const used = new Set(Object.values(palette?.characters ?? {}).map((c) => c.toUpperCase()));
  const accent = palette?.accent || palette?.colors.find((c) => !used.has(c.hex.toUpperCase()))?.hex || palette?.colors[0]?.hex || '#1F3B73';
  if (r === 'ink') return ink;
  if (r === 'white') return '#FFFFFF';
  if (r === 'soft' || r === 'soft2' || r === 'paper') return mix(accent, '#FFFFFF', 0.82);
  if (r === 'deep' || r === 'bark') return mix(accent, '#000000', 0.45);
  return accent;
}

/** Renk alanının ekranda boyanacak değeri: hex olduğu gibi, rol kitabın rengine, "none"/boş → null. */
export function paintOf(v: string | null | undefined, palette: Palette | null | undefined, roles?: RoleColors | null): string | null {
  if (!v || v === 'none') return null;
  if (v.startsWith('#')) return v;
  return roleColor(palette, v as ColorRole, roles);
}

export type Swatch = { hex: string; name: string };

/** Seçilebilir renkler: kitabın paleti + metin rengi + açık zemin (vurgunun açık tonu, `soft` rolü) + beyaz; aynı renk
 *  bir kez. Değer hex yazılır; açık zemin katalogdaki rol renginden (dizgiyle aynı). */
export function swatches(palette: Palette | null | undefined, roles?: RoleColors | null): Swatch[] {
  const out: Swatch[] = [];
  const add = (hex: string | null | undefined, name: string) => {
    if (!hex || out.some((s) => s.hex.toUpperCase() === hex.toUpperCase())) return;
    out.push({ hex: hex.toUpperCase(), name });
  };
  for (const c of palette?.colors ?? []) add(c.hex, c.name);
  add(roleColor(palette, 'ink', roles), 'Metin rengi');
  add(roleColor(palette, 'soft', roles), 'Açık zemin');
  add('#FFFFFF', 'Beyaz');
  return out;
}

// ---------------------------------------------------------------- efekt

export const EFFECT_LABEL: Record<EffectStyle, string> = {
  burst: 'Patlama', wave: 'Dalga', arc: 'Kavis', shadow: 'Gölgeli',
  outline: 'Dış çizgili', stacked: 'Kabartma', bounce: 'Zıplayan', rainbow: 'Gökkuşağı',
};

/** Stil seçilince ilk değerler: katalogdaki varsayılanlar, rol adları bu kitabın rengine çevrilmiş (ekrandaki renk
 *  seçimiyle aynı dil: hex). Önceki efektte aynı alan varsa o korunur. Katalog yoksa boş: dizgi stilin kendi
 *  varsayılanını kullanır. Harf renkleri boş kalır (dizgi kitabın paletinden sırayla boyar). */
export function effectDefaults(spec: CatalogEffect | undefined, palette: Palette | null | undefined,
  roles?: RoleColors | null, prev?: EffectParams): EffectParams {
  const out: EffectParams = {};
  for (const p of spec?.params ?? []) {
    if (p.default === undefined || p.default === null) continue;
    out[p.key] = p.type === 'color' && typeof p.default === 'string' ? paintOf(p.default, palette, roles) : p.default;
  }
  if (prev) for (const k of Object.keys(out)) if (prev[k] !== undefined) out[k] = prev[k];
  return out;
}

export function setEffectStyle(style: EffectStyle | null, prev: Effect | null, spec: CatalogEffect | undefined,
  palette: Palette | null | undefined, roles?: RoleColors | null): Effect | null {
  if (!style) return null;
  return { style, params: effectDefaults(spec, palette, roles, prev?.params) };
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
