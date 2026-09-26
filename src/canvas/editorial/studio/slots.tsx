import type { ComponentType } from 'react';
import {
  EffectTextPanel, ElementLibrary, SHAPE_DND_TYPE, ShapeInspector,
  type EffectTextPanelProps, type ElementLibraryProps, type ShapeInspectorProps,
} from './elements';

/** Süs/şekil ve efekt yazı panellerinin takıldığı yuvalar (sözleşme «Efekt yazılar ve süs/şekiller», E hattı:
 *  `src/canvas/editorial/studio/elements/`). Düzenleyici yalnız dolu yuvanın sekmesini/alanını gösterir; ekleme ve
 *  kaydetme kendi otomatik kayıt sırasından geçer. Bileşenlerin istediği bağlam (iş kimliği, palet, sayfa geometrisi,
 *  paletin özeti, yeni z, katman sırası, kaldırma) `InspectorPanel.tsx`'te düzenleyicinin bağlamından verilir. */

export type { EffectTextPanelProps, ElementLibraryProps, ShapeInspectorProps };

export type StudioSlots = {
  ElementLibrary: ComponentType<ElementLibraryProps> | null;
  EffectTextPanel: ComponentType<EffectTextPanelProps> | null;
  ShapeInspector: ComponentType<ShapeInspectorProps> | null;
};

export const slots: StudioSlots = { ElementLibrary, EffectTextPanel, ShapeInspector };

/** Öğeler panelinden tuvale sürükleme verisi: `dataTransfer.setData(SHAPE_MIME, JSON.stringify(shape))`.
 *  Tuval şekli bırakılan noktaya ortalar (`centerBoxAt`), kimlik çakışırsa yenisini, z'yi sayfadan verir. */
export const SHAPE_MIME = SHAPE_DND_TYPE;
