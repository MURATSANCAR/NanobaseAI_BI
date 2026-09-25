import { describe, expect, it } from 'vitest';
import type { PlanPage } from '../../engine';
import { nextZ, paletteKey, restackStep } from './pageItems';

const box = { x: 10, y: 10, w: 20, h: 20 };
const page: PlanPage = {
  id: 'p_1', chapter: null, layout: 'custom', art: null, text: null, bubbles: [], overflow: false,
  figures: [{ id: 'f_1', asset: 'g_1', box, rotate: 0, flip: false, z: 3 }],
  texts: [{ id: 't_1', box, align: 'center', size: null, background: null, runs: [{ text: 'a' }], z: 5 }],
  shapes: [{ id: 's_1', kind: 'star', box, rotate: 0, flip: false, z: 4 }],
};
const order = (p: PlanPage) => [
  ...p.figures.map((f) => [f.id, f.z] as const), ...p.texts.map((t) => [t.id, t.z] as const), ...(p.shapes ?? []).map((s) => [s.id, s.z] as const),
].sort((a, b) => a[1] - b[1]).map(([id]) => id);

describe('katman sırası', () => {
  it('bir adım öne/arkaya komşusuyla yer değiştirir', () => {
    expect(order(page)).toEqual(['f_1', 's_1', 't_1']);
    expect(order(restackStep(page, { kind: 'shape', id: 's_1' }, 'front'))).toEqual(['f_1', 't_1', 's_1']);
    expect(order(restackStep(page, { kind: 'shape', id: 's_1' }, 'back'))).toEqual(['s_1', 'f_1', 't_1']);
  });
  it('uçtaki öge o yöne gidemez; yeni öge en üste', () => {
    expect(restackStep(page, { kind: 'free', id: 't_1' }, 'front')).toBe(page);
    expect(nextZ(page)).toBe(6);
  });
  it('palet özeti yalnız palet değişince değişir', () => {
    const pal = { colors: [{ name: 'Kiremit', hex: '#B0341C', source: 'resim' }], text: '#2C2C2A', characters: {} };
    expect(paletteKey(pal)).toBe(paletteKey({ ...pal, colors: [...pal.colors] }));
    expect(paletteKey(pal)).not.toBe(paletteKey({ ...pal, text: '#000000' }));
  });
});
