import { describe, expect, it } from 'vitest';
import { normalizeCatalog } from './api';
import { defaultBox, editRuns, runsText, shapeFromCatalog, styleRuns } from './model';
import type { Run } from './types';

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

describe('katalog', () => {
  it('sözlük biçimini ve style parametresini tek biçime indirir', () => {
    const c = normalizeCatalog({
      groups: [{ id: 'cerceve', name: 'Çerçeveler' }],
      items: [{ kind: 'frame', name: 'Çerçeve', group: 'cerceve', aspect: 0, full_page: true,
        params: { style: { options: { plain: 'Düz', wavy: 'Dalgalı' }, default: 'plain' } }, text: false },
      { kind: 'sign', label: 'Tabela', group: 'Yazılı', ratio: 2, has_text: true, params: [{ key: 'posts', default: 1 }] }],
    });
    expect(c.groups.map((g) => g.id)).toEqual(['cerceve', 'Yazılı']);
    expect(c.items[0].styles.map((s) => s.value)).toEqual(['plain', 'wavy']);
    expect(c.items[0].params).toEqual([]);
    expect(c.items[1]).toMatchObject({ name: 'Tabela', aspect: 2, text: true });
    expect(c.items[1].params[0]).toMatchObject({ key: 'posts', type: 'int' });
  });
  it('varsayılan kutu güvenli alanda', () => {
    const page = { w: 169, h: 231, bleed: 2, safe: 8 };
    const c = normalizeCatalog([{ kind: 'sign', name: 'Tabela', group: 'g', aspect: 2, text: true }]);
    const b = defaultBox(c.items[0], page);
    expect(b.x).toBeGreaterThanOrEqual(10);
    expect(b.x + b.w).toBeLessThanOrEqual(159);
    expect(b.w / b.h).toBeCloseTo(2, 1);
    const s = shapeFromCatalog(c.items[0], { page, z: 7 });
    expect(s).toMatchObject({ kind: 'sign', z: 7, fill: null, stroke: null, opacity: 1, flip: false, rotate: 0 });
    expect(s.id).toMatch(/^s_[0-9a-f]{8}$/);
    expect(runsText(s.runs)).toBe('Tabela');
  });
});
