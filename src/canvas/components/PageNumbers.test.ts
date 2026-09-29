import { describe, expect, it } from 'vitest';
import { pageItems } from './PageNumbers';

describe('sayfa numaraları', () => {
  it('ilk ve son sayfa her zaman görünür, arası «…» ile kısalır', () => {
    expect(pageItems(9, 20, 1)).toEqual([0, 'gap', 8, 9, 10, 'gap', 19]);
    expect(pageItems(9, 20, 0)).toEqual([0, 'gap', 9, 'gap', 19]);
  });
  it('tek sayfalık boşluk «…» değil, sayfanın kendisi', () => {
    expect(pageItems(3, 20, 1)).toEqual([0, 1, 2, 3, 4, 'gap', 19]);
    expect(pageItems(2, 5, 0)).toEqual([0, 1, 2, 3, 4]);
  });
  it('baştaki ve sondaki sayfa', () => {
    expect(pageItems(0, 20, 1)).toEqual([0, 1, 'gap', 19]);
    expect(pageItems(19, 20, 1)).toEqual([0, 'gap', 18, 19]);
  });
  it('az sayfa ya da hiç sayfa', () => {
    expect(pageItems(0, 1, 1)).toEqual([0]);
    expect(pageItems(0, 2, 0)).toEqual([0, 1]);
    expect(pageItems(0, 0, 1)).toEqual([]);
  });
});
