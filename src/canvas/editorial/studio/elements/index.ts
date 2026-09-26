/** Kitap Tasarım Stüdyosu — öğeler (süs/şekil) ve efekt yazı panelleri. Sayfa düzenleyicisine (C) `../slots.tsx`
 *  üzerinden takılır; sayfaya ekleme ve kaydetme düzenleyicinin otomatik kayıt sırasından geçer. Sözleşme:
 *  docs/analiz/studyo-sayfa-plani-sozlesme.md → «Efekt yazılar ve süs/şekiller», «E teslim notları». */
export { default as ElementLibrary, ElementLibrarySheet, type ElementLibraryProps } from './ElementLibrary';
export { default as EffectTextPanel, LivePreview as EffectLivePreview, type EffectTextPanelProps } from './EffectTextPanel';
export { default as ShapeInspector, ParamControl, type ShapeInspectorProps } from './ShapeInspector';
export { elementsApi, useElementCatalog, normalizeCatalog } from './api';
export {
  EFFECT_LABEL, applyStyle, centerBoxAt, defaultBox, editRuns, newId, paintOf, roleColor, runsText, safeArea,
  shapeFromCatalog, styleOf, styleRuns, swatches,
} from './model';
export * from './types';
