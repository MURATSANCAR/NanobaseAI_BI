import { describe, expect, it } from 'vitest';
import { normalizeCatalog } from './api';
import { applyStyle, defaultBox, editRuns, effectDefaults, paintOf, runsText, shapeFromCatalog, styleOf, styleRuns, swatches } from './model';
import { COLOR_ROLES, EFFECT_STYLES, SHAPE_KINDS, type Run } from './types';
import REAL from './catalog.fixture.json';

const R: Run[] = [{ text: 'Elif ' }, { text: 'Ayşe', color: '#B0341C', weight: 700, source: 'auto' }, { text: ' geldi.' }];

describe('yazı parçaları', () => {
  it('ortadaki yazım biçimi korur', () => {
    const out = editRuns(R, 'Elif Ayşecik geldi.');
    expect(runsText(out)).toBe('Elif Ayşecik geldi.');
    expect(out[1]).toMatchObject({ text: 'Ayşecik', color: '#B0341C' });
  });
  it('silme parçayı boşaltırsa atar', () => {
    const out = editRuns(R, 'Elif  geldi.');
    expect(out).toEqual([{ text: 'Elif  geldi.' }]);
  });
  it('baştan yazım sağdaki parçanın biçimini alır, boştan başlar', () => {
    expect(editRuns([], 'Selam')).toEqual([{ text: 'Selam' }]);
  });
  it('seçime renk verir, editör kaynağı yazar', () => {
    const out = styleRuns(R, 0, 4, { color: '#1F3B73' });
    expect(out[0]).toEqual({ text: 'Elif', color: '#1F3B73', source: 'editor' });
    expect(runsText(out)).toBe(runsText(R));
  });
  it('seçim yoksa bütün yazıya uygular', () => {
    const out = styleRuns(R, 3, 3, { weight: 800 });
    expect(out.every((r) => r.weight === 800)).toBe(true);
  });
});

/** Motorun `elements.catalog` çıktısından kesit (alan adları birebir). */
const RAW = {
  groups: [{ key: 'cerceve', name: 'Çerçeve ve köşe', kinds: ['frame'] }, { key: 'yazi', name: 'Yazı taşıyanlar', kinds: ['sign'] },
    { key: 'sus', name: 'Süs, çizgi ve ok', kinds: ['scatter'] }],
  kinds: [
    { kind: 'frame', name: 'Çerçeve', group: 'cerceve', text: false, box: { w: 0.7, ratio: 0.75, place: 'center' },
      fill: 'none', stroke: 'accent', stroke_w: 1.2,
      params: { style: { label: 'Çizgi', type: 'choice', default: 'plain', choices: [{ value: 'plain', label: 'Düz' }, { value: 'double', label: 'Çift çizgi' }] },
        radius: { label: 'Köşe yuvarlaklığı (mm)', type: 'number', default: 4, min: 0, max: null, step: 0.5 } },
      runs: [],
      presets: [{ key: 'plain', name: 'Düz çerçeve', params: { style: 'plain' }, box: null },
        { key: 'page', name: 'Tam sayfa kenarlık', params: { style: 'double', radius: 6 }, box: { place: 'page' } }] },
    { kind: 'sign', name: 'Tabela', group: 'yazi', text: true, box: { w: 0.42, ratio: 1.3, place: 'center' },
      fill: 'wood', stroke: 'bark', stroke_w: 0.7,
      params: { posts: { label: 'Direk', type: 'int', default: 1, min: 0, max: 2, step: 1 } },
      runs: [{ text: 'Orman Yolu' }],
      presets: [{ key: 'post', name: 'Direkli tabela', params: { posts: 1 }, box: null },
        { key: 'board', name: 'Direksiz tabela', params: { posts: 0 }, box: { ratio: 2.2 } }] },
    { kind: 'scatter', name: 'Serpiştirme', group: 'sus', text: false, box: { w: 0.6, ratio: 1.3, place: 'center' },
      fill: null, stroke: 'none', stroke_w: 0,
      params: { count: { label: 'Adet', type: 'int', default: 14, min: 1, max: null, step: 1 } }, runs: [],
      presets: [{ key: 'star', name: 'Yıldız serpiştir', params: { item: 'star' }, box: null }] },
  ],
  effects: [{ style: 'burst', name: 'Patlama', sample: 'Güüüm!', box: { w: 80, h: 56 },
    params: { burst_fill: { label: 'Patlama rengi', type: 'color', default: 'sun' }, angle: { label: 'Eğim (°)', type: 'number', default: -8, min: -45, max: 45, step: 1 } } },
  { style: 'bounce', name: 'Zıplayan', sample: 'Hop', box: { w: 90, h: 30 },
    params: { colors: { label: 'Harf renkleri (boş = palet)', type: 'colors', default: null } } }],
  roles: [{ key: 'accent', name: 'Vurgu', hex: '#B0341C' }, { key: 'sun', name: 'Güneş sarısı', hex: '#F2C84B' },
    { key: 'soft', name: 'Açık vurgu', hex: '#F7ECE9' }, { key: 'ink', name: 'Yazı rengi', hex: '#2C2C2A' }],
  fonts: { body: 'Andika', heading: 'Baloo 2' },
};
const PAGE = { w: 169, h: 231, bleed: 2, safe: 8 };

describe('motorun tam kataloğu (catalog.fixture.json = elements.catalog(None) çıktısı, 2026-09-25)', () => {
  const c = normalizeCatalog(REAL);
  it('bütün türler, stiller ve roller okunur; her türün hazır biçimi ve geçerli parametre türü var', () => {
    expect(c.items.map((i) => i.kind).sort()).toEqual([...SHAPE_KINDS].sort());
    expect(c.effects.map((e) => e.style).sort()).toEqual([...EFFECT_STYLES].sort());
    expect(Object.keys(c.roles).sort()).toEqual([...COLOR_ROLES].sort());
    expect(c.groups.map((g) => g.id)).toEqual(['cerceve', 'yazi', 'sekil', 'sus']);
    for (const it of c.items) {
      expect(it.styles.length, it.kind).toBeGreaterThan(0);
      expect(it.aspect, it.kind).toBeGreaterThan(0);
      for (const p of it.params) expect(['choice', 'number', 'int', 'bool', 'color', 'colors'], `${it.kind}.${p.key}`).toContain(p.type);
      const s = shapeFromCatalog(it, { page: PAGE });
      expect(s.box.x, it.kind).toBeGreaterThanOrEqual(0);
      expect(s.box.x + s.box.w, it.kind).toBeLessThanOrEqual(PAGE.w);
      expect(styleOf(it, s.params)?.value, it.kind).toBe(it.styles[0].value);
    }
    const sign = c.items.find((i) => i.kind === 'sign')!;
    expect(runsText(sign.runs)).toBe('Orman Yolu');
    expect(c.items.find((i) => i.kind === 'star')!.runs).toEqual([]);
    expect(c.effects.find((e) => e.style === 'wave')!.params.map((p) => p.key)).toContain('waves');
  });
});

describe('katalog (motorun gerçek biçimi)', () => {
  const c = normalizeCatalog(RAW);
  const [frame, sign, scatter] = c.items;
  it('gruplar, hazır biçimler, roller ve parametre sınırları', () => {
    expect(c.groups.map((g) => g.id)).toEqual(['cerceve', 'yazi', 'sus']);
    expect(frame.styles.map((s) => s.value)).toEqual(['plain', 'page']);
    expect(sign).toMatchObject({ aspect: 1.3, width: 0.42, text: true, roles: { fill: 'wood', stroke: 'bark' } });
    expect(frame.roles.fill).toBe('none');
    expect(scatter.roles.fill).toBeNull();
    expect(scatter.params[0]).toMatchObject({ key: 'count', type: 'int', min: 1 });
    expect(scatter.params[0].max).toBeUndefined();                     // açık uç: sayı kutusu sınırsız
    expect(c.roles.sun?.hex).toBe('#F2C84B');
    expect(c.effects.map((e) => e.style)).toEqual(['burst', 'bounce']);
    expect(c.effects[1].params[0].type).toBe('colors');
  });
  it('yeni şekil motorun new_shape alanlarıyla; varsayılan yazı katalogdan', () => {
    const s = shapeFromCatalog(sign, { page: PAGE, z: 7 });
    expect(s).toMatchObject({ kind: 'sign', z: 7, fill: null, stroke: null, stroke_w: null, text_size: null, opacity: 1, flip: false, rotate: 0,
      params: { posts: 1 } });
    expect(s.id).toMatch(/^s_[0-9a-f]{8}$/);
    expect(runsText(s.runs)).toBe('Orman Yolu');
    expect(s.box.x).toBeGreaterThanOrEqual(PAGE.bleed + PAGE.safe);
    expect(s.box.w / s.box.h).toBeCloseTo(1.3, 1);
    expect(runsText(shapeFromCatalog(frame, { page: PAGE }).runs)).toBe('');
  });
  it('hazır biçim: parametre, kutu oranı ve tam sayfa yerleşim', () => {
    const board = shapeFromCatalog(sign, { page: PAGE, style: 'board' });
    expect(board.params).toMatchObject({ posts: 0 });
    expect(board.box.w / board.box.h).toBeCloseTo(2.2, 1);
    expect(defaultBox(frame, PAGE, frame.styles[1])).toEqual({ x: 6, y: 6, w: 157, h: 219 });
    const plain = shapeFromCatalog(frame, { page: PAGE });
    expect(styleOf(frame, plain.params)?.value).toBe('plain');
    expect(styleOf(frame, applyStyle(plain, frame.styles[1]).params)?.value).toBe('page');
  });
  it('renk: rol kitabın rengine çevrilir, seçenekler metin/açık zemin/beyaz içerir', () => {
    expect(paintOf('sun', null, c.roles)).toBe('#F2C84B');
    expect(paintOf('none', null, c.roles)).toBeNull();
    const pal = { colors: [{ name: 'Kiremit', hex: '#B0341C', source: 'resim' }], text: '#2C2C2A', characters: {} };
    expect(swatches(pal, c.roles).map((s) => s.name)).toEqual(['Kiremit', 'Metin rengi', 'Açık zemin', 'Beyaz']);
    expect(effectDefaults(c.effects[0], pal, c.roles)).toEqual({ burst_fill: '#F2C84B', angle: -8 });
    expect(effectDefaults(c.effects[1], pal, c.roles)).toEqual({});
  });
});
