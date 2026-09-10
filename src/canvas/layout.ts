import type { CanvasAccent } from './types';

/**
 * Yıldız kümesinin sahnedeki yerleşimi — design/stitch-wow/03-canvas.html'deki
 * koordinatların birebir kendisi. Her ekran aynı beş yuvayı, aynı karar kartını,
 * aynı bant etiketini ve aynı hayalet kümeyi kullanır: tasarım tek, içerik değişir.
 */
export const SLOTS = {
  a: { x: 110, y: 175, w: 235, rot: -3, connect: 'coral' as CanvasAccent },
  b: { x: 365, y: 170, w: 250, rot: 2, connect: 'violet' as CanvasAccent },
  c: { x: 635, y: 185, w: 240, rot: -1.5, connect: 'mint' as CanvasAccent },
  d: { x: 895, y: 170, w: 235, rot: 1, connect: 'amber' as CanvasAccent },
  e: { x: 1150, y: 175, w: 215, rot: 2.5, connect: 'slate' as CanvasAccent },
  /** Ortadaki geniş karar/cevap kartı. */
  main: { x: 290, y: 445, w: 860, rot: 0, connect: false as const },
  /** Bantla tutturulmuş etiket. */
  sticker: { x: 1185, y: 445, w: 125, rot: 6, connect: false as const, z: 30 },
  /** Sağda yarı görünen önceki küme — tuvalin devam ettiğini gösterir. */
  ghost: { x: 1340, y: 240, w: 220, rot: -3, connect: false as const, z: 10 },
} as const;

export type SlotName = keyof typeof SLOTS;
