import type { ComponentType } from 'react';
import type { PlanEffect, PlanShape } from '../../engine';

/** Süs/şekil ve efekt yazı panellerinin takılacağı yuvalar (sözleşme «Efekt yazılar ve süs/şekiller», E hattı:
 *  `src/canvas/editorial/studio/elements/`). Paneller hazır olunca burada `null` yerine o klasörden gelen bileşen
 *  verilir; düzenleyici yalnız dolu yuvanın sekmesini/alanını gösterir, ekleme ve kaydetme kendi otomatik kayıt
 *  sırasından geçer:
 *
 *    import { ElementLibrary, EffectTextPanel, ShapeInspector } from './elements';
 *    export const slots: StudioSlots = { ElementLibrary, EffectTextPanel, ShapeInspector };
 */

export type ElementLibraryProps = { onAdd: (shape: PlanShape) => void };
export type EffectTextPanelProps = { value: PlanEffect | null; onChange: (effect: PlanEffect | null) => void };
export type ShapeInspectorProps = { value: PlanShape; onChange: (shape: PlanShape) => void };

export type StudioSlots = {
  ElementLibrary: ComponentType<ElementLibraryProps> | null;
  EffectTextPanel: ComponentType<EffectTextPanelProps> | null;
  ShapeInspector: ComponentType<ShapeInspectorProps> | null;
};

export const slots: StudioSlots = { ElementLibrary: null, EffectTextPanel: null, ShapeInspector: null };

/** Öğeler panelinden tuvale sürükleme verisi: `dataTransfer.setData(SHAPE_MIME, JSON.stringify(shape))`.
 *  Kimlik, z ve kutu konumu yoksa tuval verir (bırakılan noktaya ortalanır). */
export const SHAPE_MIME = 'application/x-studio-shape';
