import { describe, expect, it } from 'vitest';
import { answerSources } from './askSources';

const books = [
  { id: 'a', title: 'Gölge Tilki', names: ['golge tilki'] },
  { id: 'b', title: 'Taşra İdaresi', names: ['tasra idaresi'] },
  { id: 'c', title: 'Başka Kitap', names: ['baska kitap'] },
];

describe('answerSources', () => {
  it('cevapta adı geçen kitaplar ve atıf sayfaları, kitap başına', () => {
    const out = answerSources({
      answer: "Gölge Tilki'de ana karakter Ece'dir [s.12], (s. 40, 7). Taşra İdaresi ise sancakları anlatır s. 3.",
      notFound: false,
      citations: { books, defaultId: null },
    });
    expect(out).toEqual([
      { id: 'a', title: 'Gölge Tilki', pages: [7, 12, 40] },
      { id: 'b', title: 'Taşra İdaresi', pages: [3] },
    ]);
  });

  it('adı geçmeyen atıf varsayılan kitaba bağlanır', () => {
    const out = answerSources({ answer: 'Ana karakter Ece [s.5].', notFound: false, citations: null, bookId: 'a', bookTitle: 'Gölge Tilki' });
    expect(out).toEqual([{ id: 'a', title: 'Gölge Tilki', pages: [5] }]);
  });

  it('uzun sayfa listesinin bütün sayfaları kaynağa girer (sayı bölünmez)', () => {
    const out = answerSources({
      answer: "Gölge Tilki'de kötü karakter Gölge'dir (s.81, 101,130]. Taşra İdaresi'nde anlatılır s.17, 44,59,68]",
      notFound: false,
      citations: { books, defaultId: null },
    });
    expect(out).toEqual([
      { id: 'a', title: 'Gölge Tilki', pages: [81, 101, 130] },
      { id: 'b', title: 'Taşra İdaresi', pages: [17, 44, 59, 68] },
    ]);
  });

  it('kart cevabında seçilen kitaplar, yayınevi adıyla', () => {
    const out = answerSources({
      answer: 'İstediğiniz kitapların kartı aşağıda.',
      notFound: false,
      cards: [{ id: 'b', title: 'tasra-idaresi', publisher: { title: 'Taşra İdaresi' } } as never],
    });
    expect(out).toEqual([{ id: 'b', title: 'Taşra İdaresi', pages: [] }]);
  });

  it('bulunamadı cevabında kaynak yok', () => {
    expect(answerSources({ answer: 'Kitapta bulunamadı. Gölge Tilki s. 3', notFound: true, citations: { books, defaultId: null } })).toEqual([]);
  });
});
