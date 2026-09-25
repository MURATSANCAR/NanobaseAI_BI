/** Kitap Tasarım Stüdyosu — öğeler (süs/şekil) ve efekt yazı panelleri. Sayfa düzenleyicisine (C) takılır;
 *  sayfaya ekleme ve kaydetme düzenleyicinin otomatik kayıt sırasından geçer. Sözleşme:
 *  docs/analiz/studyo-sayfa-plani-sozlesme.md → «Efekt yazılar ve süs/şekiller». */
export { default as ElementLibrary, ElementLibrarySheet, type ElementLibraryProps } from './ElementLibrary';
export { default as EffectTextPanel, LivePreview as EffectLivePreview, type EffectTextPanelProps } from './EffectTextPanel';
export { default as ShapeInspector, type ShapeInspectorProps } from './ShapeInspector';
export { elementsApi, useElementCatalog, normalizeCatalog } from './api';
export { centerBoxAt, defaultBox, editRuns, newId, roleColor, runsText, safeArea, shapeFromCatalog, styleRuns, swatches } from './model';
export * from './types';
