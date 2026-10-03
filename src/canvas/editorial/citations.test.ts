import { describe, expect, it } from 'vitest';
import { CiteCursor, citePages, citationsOf, lastMention, norm, pageStatus, splitCitations, type CitePiece } from './citations';

const pages = (text: string) =>
  splitCitations(text).flatMap((s) => (s.kind === 'cite' ? s.pieces.filter((p): p is Extract<CitePiece, { page: number }> => 'page' in p).map((p) => p.page) : []));
const labels = (text: string) =>
  splitCitations(text).flatMap((s) => (s.kind === 'cite' ? s.pieces.flatMap((p) => ('page' in p ? [p.label] : [])) : []));

/** Metnin atıf dışı kısmı; her grup «#». */
const rest = (text: string) => splitCitations(text).map((s) => (s.kind === 'text' ? s.text : '#')).join('');
/** Her grubun rozet etiketleri (`citePages`). */
const groups = (text: string) => splitCitations(text).flatMap((s) => (s.kind === 'cite' ? [citePages(s.pieces).map((p) => p.label)] : []));

describe('uzun sayfa listesi tek grup (canlıda bozuk görünen cevaplar)', () => {
  it('«(s.81, 101,130]»: bütün sayfalar tek grup, ayraç/virgül kalmaz', () => {
    const t = "Kötü karakter Gölge'dir (s.81, 101,130].";
    expect(rest(t)).toBe("Kötü karakter Gölge'dir #.");
    expect(groups(t)).toEqual([['s.81', '101', '130']]);
  });
  it('«s.17, 44,59,…,192]»: sayılar bölünmez, kapanış ayracı metinde kalmaz', () => {
    const t = 'Bu konu anlatılır s.17, 44,59,68,88,93,95,119,120,124,128,135,149,160,171,174,191,192]';
    expect(rest(t)).toBe('Bu konu anlatılır #');
    expect(pages(t)).toEqual([17, 44, 59, 68, 88, 93, 95, 119, 120, 124, 128, 135, 149, 160, 171, 174, 191, 192]);
  });
  it('«[s. 4, 59, 68, …]»: köşeli ayraçlı liste tek grup', () => {
    const t = 'anlatılır [s. 4, 59, 68, 88, 93].';
    expect(rest(t)).toBe('anlatılır #.');
    expect(groups(t)).toEqual([['s. 4', '59', '68', '88', '93']]);
  });
  it('aralık tek rozet; tekrar eden sayfa bir kez', () => {
    expect(groups('[s. 12-14, 20, 20]')).toEqual([['s. 12–14', '20']]);
  });
  it('ayraçsız grupta ondalık ve sayı+kelime yine atıf değildir; sayı bölünmez', () => {
    expect(pages('s. 14, 3,5 milyon')).toEqual([14]);
    expect(pages('s. 101,130 arası')).toEqual([101]);
  });
});

describe('splitCitations — çoklu sayfa biçimleri (ZEKI-43)', () => {
  it('«(s. 114, 127)» iki sayfa; parantez grubun parçası, metinde kalmaz', () => {
    const segs = splitCitations('asıl konu ( s. 114, 127) dır');
    expect(pages('asıl konu ( s. 114, 127) dır')).toEqual([114, 127]);
    expect(labels('asıl konu ( s. 114, 127) dır')).toEqual(['s. 114', '127']);
    expect(segs.map((s) => (s.kind === 'text' ? s.text : '#')).join('')).toBe('asıl konu # dır');
  });
  it('«(bkz. s. 12)»: açılışsız grup cümlenin parantezini yutmaz', () => {
    expect(rest('Bkz. (bkz. s. 12) sonra')).toBe('Bkz. (bkz. #) sonra');
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
