import { describe, expect, it } from 'vitest';
import type { IntakeCard } from '../../engine';
import { NONE, activeCount, facetOptions, matches, readFilters, withFilter, withoutFilters } from './filters';

const card = (o: Partial<IntakeCard>): IntakeCard => ({
  id: o.id ?? 'x',
  name: 'Kitap',
  author: 'Yazar',
  editor: null,
  bookId: null,
  step: 2,
  phase: 1,
  done: 1,
  progress: [],
  line: '',
  since: null,
  waitingDays: 0,
  late: false,
  outcome: null,
  complete: false,
  boardOn: null,
  modifiedOn: null,
  createdOn: '2026-03-01',
  mine: false,
  brand: 'Timaş Çocuk',
  projectType: 'Editoryal',
  ...o,
});

const cards = [
  card({ id: 'a', editor: 'Ayşe', brand: 'Timaş Çocuk', step: 3, late: true }),
  card({ id: 'b', editor: null, brand: 'Timaş Çocuk', step: 2 }),
  card({ id: 'c', editor: 'Ayşe', brand: 'Genç Timaş', step: 3, createdOn: '2025-11-02', mine: true }),
  card({ id: 'd', editor: 'Ömer', brand: null, step: 7, projectType: 'Pazarlama' }),
];

const none = readFilters(new URLSearchParams());

describe('yazar giriş süzgeçleri', () => {
  it('adresten okur, boş değeri adresten siler, diğer parametreye dokunmaz', () => {
    const p = new URLSearchParams('marka=Timaş Çocuk&geciken=1&evre=2');
    const f = readFilters(p);
    expect(f.brand).toBe('Timaş Çocuk');
    expect(f.late).toBe(true);
    expect(withFilter(p, 'brand', '').has('marka')).toBe(false);
    expect(withFilter(p, 'late', false).has('geciken')).toBe(false);
    expect(withFilter(p, 'editor', 'Ayşe').get('editor')).toBe('Ayşe');
    const cleared = withoutFilters(p);
    expect([...cleared.keys()]).toEqual(['evre']);
  });

  it('süzgeçler birlikte uygulanır; boş alan «girilmemiş» seçeneğiyle seçilir', () => {
    const f = { ...none, brand: 'Timaş Çocuk', step: '3' };
    expect(cards.filter((c) => matches(c, f)).map((c) => c.id)).toEqual(['a']);
    expect(cards.filter((c) => matches(c, { ...none, editor: NONE })).map((c) => c.id)).toEqual(['b']);
    expect(cards.filter((c) => matches(c, { ...none, brand: NONE })).map((c) => c.id)).toEqual(['d']);
    expect(cards.filter((c) => matches(c, { ...none, year: '2025' })).map((c) => c.id)).toEqual(['c']);
    expect(cards.filter((c) => matches(c, { ...none, type: 'Pazarlama' })).map((c) => c.id)).toEqual(['d']);
    expect(cards.filter((c) => matches(c, { ...none, late: true, mine: true }))).toEqual([]);
  });

  it('seçenek sayısı diğer süzgeçler uygulanmış kartlardan; kendi seçimi sayıyı daraltmaz', () => {
    const f = { ...none, brand: 'Timaş Çocuk' };
    // Marka seçenekleri marka süzgecini yok sayar: bütün markalar sayılarıyla görünür.
    expect(facetOptions(cards, f, 'brand')).toEqual([
      { value: 'Timaş Çocuk', count: 2 },
      { value: 'Genç Timaş', count: 1 },
      { value: NONE, count: 1 },
    ]);
    // Editör seçenekleri yalnız Timaş Çocuk kartlarından; atanmamış en üstte.
    expect(facetOptions(cards, f, 'editor')).toEqual([
      { value: NONE, count: 1 },
      { value: 'Ayşe', count: 1 },
    ]);
    // Seçenekler toplamı süzgece uyan kart sayısına eşit.
    const total = cards.filter((c) => matches(c, f)).length;
    expect(facetOptions(cards, f, 'step').reduce((s, o) => s + o.count, 0)).toBe(total);
  });

  it('kartta kalmayan seçili değer 0 sayısıyla listede kalır', () => {
    const f = { ...none, editor: 'Ayşe', brand: 'Genç Timaş', step: '7' };
    expect(facetOptions(cards, f, 'step')).toEqual([
      { value: '3', count: 1 },
      { value: '7', count: 0 },
    ]);
  });

  it('açık süzgeç sayısı aramayı ve düğmeleri de sayar', () => {
    expect(activeCount(none)).toBe(0);
    expect(activeCount({ ...none, q: 'x', year: '2026', late: true })).toBe(3);
  });
});
