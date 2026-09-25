import type {
  Plan, PlanBox, PlanColorRole, PlanEffect, PlanEffectParams, PlanEffectStyle, PlanPalette, PlanRun, PlanShape,
} from '../../../engine';

/** Efekt yazılar ve süs/şekiller (docs/analiz/studyo-sayfa-plani-sozlesme.md → «Efekt yazılar ve süs/şekiller»).
 *  Sayfa nesnesindeki alanların tek kaynağı `engine.ts`'tir (PlanShape, PlanEffect …); burada yalnız kısa adlarla
 *  yeniden verilir. Katalog tipleri motorun `GET plan/elements/catalog` çıktısının ekrandaki (normalleştirilmiş)
 *  hâlidir; dönüşüm `api.ts` → `normalizeCatalog`. Ölçüler mm, köken taşma paylı sayfanın sol üstü. */

export type Box = PlanBox;
export type Run = PlanRun;
export type Shape = PlanShape;
export type Effect = PlanEffect;
export type EffectParams = PlanEffectParams;
export type EffectStyle = PlanEffectStyle;
export type Palette = PlanPalette;
/** Palet rolü: renk boşsa dizgi kitabın paletinden bu rolle doldurur. */
export type ColorRole = PlanColorRole;
/** `plan.page` — varsayılan kutuyu yerleştirmek için. */
export type PageGeom = Pick<Plan['page'], 'w' | 'h' | 'bleed' | 'safe'> & { gutter?: number };

/** Sözleşmedeki katalog türleri. Motor yeni tür eklerse ekran onu da gösterir (string). */
export const SHAPE_KINDS = [
  'frame', 'corner', 'scatter', 'arrow', 'sign', 'note', 'envelope', 'scroll',
  'badge', 'ribbon', 'star', 'heart', 'cloud', 'burst', 'line',
] as const;
export type ShapeKind = Shape['kind'];

export const EFFECT_STYLES: readonly EffectStyle[] = ['burst', 'wave', 'arc', 'shadow', 'outline', 'stacked', 'bounce', 'rainbow'];

export const COLOR_ROLES: readonly ColorRole[] = [
  'accent', 'accent2', 'ink', 'pop', 'pop2', 'sun', 'rose', 'soft', 'soft2', 'paper', 'wood', 'bark', 'deep', 'white',
];

/** Katalog parametresi (motorda `params` sözlüğünün bir öğesi; burada anahtarıyla liste). `min`/`max` motorun
 *  doğrulama sınırıdır (yoksa açık uçlu); ekran kaydırıcı aralığını bundan alır, sayı kutusu açık uçta sınır koymaz. */
export type CatalogParam = {
  key: string;
  label: string;
  type: 'choice' | 'number' | 'int' | 'bool' | 'color' | 'colors' | 'text';
  options?: { value: string; label: string }[];
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
  default?: unknown;
};

/** Hazır biçim (motorda `presets[]`): önizleme ucunun `style`'ı `value`'dur; seçilince `params` şeklin
 *  parametrelerine yazılır, `box` yeni eklenen şeklin kutusunu belirler (oran, genişlik, yer). */
export type CatalogStyle = {
  value: string;
  label: string;
  params: Record<string, unknown>;
  box?: { w?: number; ratio?: number; place?: 'center' | 'page' | 'corner' } | null;
};

/** Katalogdaki tür. `aspect` en/boy; `width` kesim genişliğine oran; `full_page` güvenli alanın yarısı içeride tam
 *  sayfa (çerçeve kenarlığı); `place: corner` sol üst köşe. `roles` boş renk alanının varsayılan rolü ("none" = boya
 *  yok). `runs` yazı taşıyan türün varsayılan yazısı (boş olabilir: yıldıza yazı sonradan yazılır). */
export type CatalogItem = {
  kind: ShapeKind;
  name: string;
  group: string;
  aspect: number;
  width: number;
  place: 'center' | 'page' | 'corner';
  full_page?: boolean;
  roles: { fill?: ColorRole | 'none' | null; stroke?: ColorRole | 'none' | null; text?: ColorRole | null };
  params: CatalogParam[];
  text: boolean;
  runs: Run[];
  styles: CatalogStyle[];
  stroke_w?: number;
  text_size?: number | null;
};

export type CatalogGroup = { id: string; name: string };
export type CatalogEffect = { style: EffectStyle; name: string; sample: string; params: CatalogParam[] };
/** Rol → bu kitabın paletinden hesaplanmış renk (dizgiyle birebir aynı hesap, motordan). */
export type RoleColors = Partial<Record<ColorRole, { name: string; hex: string }>>;
export type Catalog = { groups: CatalogGroup[]; items: CatalogItem[]; effects: CatalogEffect[]; roles: RoleColors };

/** Sayfaya sürükle-bırakta taşınan veri türü; içerik hazır bir `Shape` (JSON). */
export const SHAPE_DND_TYPE = 'application/x-studio-shape';
