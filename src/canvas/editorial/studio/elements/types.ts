/** Efekt yazılar ve süs/şekiller — sayfa planı sözleşmesindeki alanların birebir karşılığı
 *  (docs/analiz/studyo-sayfa-plani-sozlesme.md → «Efekt yazılar ve süs/şekiller»). Ölçüler mm, köken taşma
 *  paylı sayfanın sol üstü. Bu dosyada alan adı değişirse önce sözleşme değişir. */

export type Box = { x: number; y: number; w: number; h: number };

/** Yazı parçası (`run`). `source: "editor"` olan parçaya otomatik kural dokunmaz. */
export type Run = {
  text: string;
  color?: string | null;
  weight?: 400 | 700 | 800;
  size?: number | null;
  font?: 'body' | 'heading';
  source?: 'auto' | 'editor';
};

/** Sözleşmedeki katalog türleri. Motor yeni tür eklerse ekran onu da gösterir (string). */
export const SHAPE_KINDS = [
  'frame', 'corner', 'scatter', 'arrow', 'sign', 'note', 'envelope', 'scroll',
  'badge', 'ribbon', 'star', 'heart', 'cloud', 'burst', 'line',
] as const;
export type KnownShapeKind = (typeof SHAPE_KINDS)[number];
export type ShapeKind = KnownShapeKind | (string & {});

/** Şekil katmanı öğesi (`page.shapes[]`). `fill`/`stroke` null → motor paletten rolle doldurur. */
export type Shape = {
  id: string;
  kind: ShapeKind;
  box: Box;
  rotate: number;
  flip: boolean;
  z: number;
  fill: string | null;
  stroke: string | null;
  stroke_w: number;
  opacity: number;
  /** Türe özel; biçim seçeneği (düz/dalgalı/…) `params.style`'da durur. */
  params: Record<string, unknown>;
  /** Yalnız yazı taşıyan türlerde. */
  runs?: Run[];
  text_size?: number | null;
};

export const EFFECT_STYLES = ['burst', 'wave', 'arc', 'shadow', 'outline', 'stacked', 'bounce', 'rainbow'] as const;
export type EffectStyle = (typeof EFFECT_STYLES)[number];

export type EffectParams = {
  /** arc/wave: -1..1 kavis. */
  curve?: number;
  outline?: string;
  /** mm */
  outline_w?: number;
  shadow?: string;
  /** mm */
  shadow_dx?: number;
  /** mm */
  shadow_dy?: number;
  /** rainbow/bounce: harf harf dönen renkler. */
  colors?: string[];
  burst_fill?: string;
  burst_stroke?: string;
  /** derece */
  angle?: number;
};

/** Serbest yazının (`page.texts[]`) isteğe bağlı `effect` alanı. */
export type Effect = { style: EffectStyle; params: EffectParams };

/** Palet rengi rolü; şekil rengi boşsa motor bu rolle doldurur. */
export type ColorRole = 'accent' | 'soft' | 'ink';

export type PaletteColor = { name: string; hex: string; source?: 'resim' | 'timas' | 'editor' | string };

/** `plan.palette`. `accent` B'nin teslim notunda isteğe bağlı alan. */
export type Palette = {
  colors: PaletteColor[];
  text: string;
  characters?: Record<string, string>;
  accent?: string | null;
  soft?: string | null;
};

/** `plan.page` — varsayılan kutuyu güvenli alana yerleştirmek için. */
export type PageGeom = { w: number; h: number; bleed: number; safe: number; gutter?: number };

/** Katalog parametresi. `type` verilmezse varsayılan değerden çıkarılır. */
export type CatalogParam = {
  key: string;
  label: string;
  type: 'choice' | 'number' | 'int' | 'bool' | 'color' | 'text';
  options?: { value: string; label: string }[];
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  default?: unknown;
};

/** Katalogdaki tür (`elements.CATALOG` öğesi): Türkçe ad, grup, varsayılan kutu oranı (en/boy), varsayılan renk
 *  rolleri, parametreler, yazı taşır mı. `styles` biçim seçenekleri (çerçeve: düz/dalgalı/…). */
export type CatalogItem = {
  kind: ShapeKind;
  name: string;
  group: string;
  /** en / boy; 0 ya da `full_page` → güvenli alanın tamamı (çerçeve). */
  aspect: number;
  full_page?: boolean;
  roles: { fill?: ColorRole | null; stroke?: ColorRole | null; text?: ColorRole | null };
  params: CatalogParam[];
  text: boolean;
  styles: { value: string; label: string }[];
  /** Varsayılan çizgi kalınlığı (mm) ve yazı puntosu; yoksa ekranın varsayılanı. */
  stroke_w?: number;
  text_size?: number;
};

export type CatalogGroup = { id: string; name: string };
export type Catalog = { groups: CatalogGroup[]; items: CatalogItem[] };

/** Sayfaya sürükle-bırakta taşınan veri türü; içerik hazır bir `Shape` (JSON). */
export const SHAPE_DND_TYPE = 'application/x-studio-shape';
