import { describe, expect, it } from 'vitest';
import { NO_ROLE, groupWorks, type PersonWork } from './personWorks';

const w = (title: string, role: string | null, bookId: string | null = title): PersonWork => ({ bookId, title, role, on: null });

describe('kişi ayrıntısında eserler (ZEKI-27)', () => {
  it('yazar ve çevirmen olan kişide «Yazar» grubu önce gelir, çeviriler karışmaz', () => {
    const g = groupWorks([w('Çeviri 1', 'Tercüme'), w('Kendi kitabı', 'Yazar'), w('Çeviri 2', 'Tercüme'), w('Çeviri 3', 'Tercüme')]);
    expect(g.map((x) => x.role)).toEqual(['Yazar', 'Tercüme']);
    expect(g[0].works.map((x) => x.title)).toEqual(['Kendi kitabı']);
    expect(g[1].works.map((x) => x.title)).toEqual(['Çeviri 1', 'Çeviri 2', 'Çeviri 3']);
  });

  it('ekranın rolleri yazardan sonra, diğerleri eser sayısına göre', () => {
    const g = groupWorks([w('a', 'Redaktör'), w('b', 'Çizer'), w('c', 'Çizer'), w('d', 'Tercüme'), w('e', null)], ['Tercüme']);
    expect(g.map((x) => x.role)).toEqual(['Tercüme', 'Çizer', 'Redaktör', NO_ROLE]);
  });

  it('aynı kitap aynı rolde bir kez yazılır; farklı rolde ayrı durur', () => {
    const g = groupWorks([w('K', 'Yazar', 'B1'), w('K', 'Yazar', 'b1'), w('K', 'Tercüme', 'B1')]);
    expect(g.find((x) => x.role === 'Yazar')?.works).toHaveLength(1);
    expect(g.find((x) => x.role === 'Tercüme')?.works).toHaveLength(1);
  });

  it('kitabı bağlanmamış kayıtlar kaybolmaz', () => {
    const g = groupWorks([w('', 'Yazar', null), w('', 'Yazar', null)]);
    expect(g[0].works).toHaveLength(2);
  });
});
