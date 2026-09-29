import { describe, expect, it } from 'vitest';
import { CiteCursor, citationsOf, lastMention, norm, pageStatus, splitCitations, type CitePiece } from './citations';

const pages = (text: string) =>
  splitCitations(text).flatMap((s) => (s.kind === 'cite' ? s.pieces.filter((p): p is Extract<CitePiece, { page: number }> => 'page' in p).map((p) => p.page) : []));
const labels = (text: string) =>
  splitCitations(text).flatMap((s) => (s.kind === 'cite' ? s.pieces.flatMap((p) => ('page' in p ? [p.label] : [])) : []));

describe('splitCitations — çoklu sayfa biçimleri (ZEKI-43)', () => {
  it('«(s. 114, 127)» iki rozet; ayraç ve parantez düz metin', () => {
    const segs = splitCitations('asıl konu ( s. 114, 127) dır');
    expect(pages('asıl konu ( s. 114, 127) dır')).toEqual([114, 127]);
    expect(labels('asıl konu ( s. 114, 127) dır')).toEqual(['s. 114', '127']);
    expect(segs.map((s) => (s.kind === 'text' ? s.text : '#')).join('')).toBe('asıl konu ( #) dır');
  });
  it('aralık, «ss.», «ve», «sayfa», köşeli ayraç, paragraf', () => {
    expect(pages('s. 12-14')).toEqual([12, 14]);
    expect(pages('s. 12–14')).toEqual([12, 14]);
    expect(pages('ss. 3, 5 ve 9')).toEqual([3, 5, 9]);
    expect(pages('sayfa 7 ve 8')).toEqual([7, 8]);
    expect(pages('[s.2]')).toEqual([2]);
    expect(pages('[s.3 p2]')).toEqual([3]);
    expect(pages('s. 3, s. 5')).toEqual([3, 5]);
    expect(labels('s. 3, s. 5')).toEqual(['s. 3', 's. 5']);
  });
  it('sayıdan sonra kelime gelen ek sayı atıf değildir; kelime içindeki önek atıf değildir', () => {
    expect(pages('s. 14, 3 kişi gelir')).toEqual([14]);
    expect(pages('s. 3, 5 ve 9 arasında')).toEqual([3, 5]);
    expect(pages('vs. 14')).toEqual([]);
  });
});

describe('atıfın kitabı', () => {
  const books = [
    { id: 'A', title: 'Birinci Kitap', names: [norm('birinci-kitap'), norm('Birinci Kitap')] },
    { id: 'B', title: 'İkinci Kitap', names: [norm('ikinci-kitap'), norm('İkinci Kitap')] },
  ];
  it('Türkçe harf ve ek farkı yok sayılır', () => {
    expect(norm("İkinci Kitap'ta")).toBe('ikinci kitap ta');
    expect(lastMention("İkinci Kitap'ta anne", books)).toBe('B');
    expect(lastMention('hiçbiri', books)).toBeNull();
  });
  it('rozet kendinden önce en son anılan kitaba, anılmadıysa varsayılana bağlanır', () => {
    const cursor = new CiteCursor({ books, defaultId: 'A', pages: { A: { '5': true }, B: { '114': true, '127': false } } });
    const seen: [string | null, number, string][] = [];
    const text = "Burada dede [s. 5]. İkinci Kitap'ta asıl konu (s. 114, 127).";
    for (const seg of splitCitations(text)) {
      if (seg.kind === 'text') cursor.read(seg.text);
      else for (const p of seg.pieces) if ('page' in p) seen.push([cursor.current, p.page, pageStatus(cursor.c, cursor.current, p.page)]);
    }
    expect(seen).toEqual([['A', 5, 'ok'], ['B', 114, 'ok'], ['B', 127, 'missing']]);
  });
  it('köprü atıf özeti yoksa bütün rozetler cevabın tek kitabına (önceki davranış)', () => {
    const c = citationsOf({ bookId: 'A', bookTitle: 'x' });
    expect(c.defaultId).toBe('A');
    expect(pageStatus(c, 'A', 3)).toBe('unknown');
  });
});
