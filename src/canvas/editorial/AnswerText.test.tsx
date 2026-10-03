import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { AnswerText } from './AskBox';

/** Cevap metninin çizimi: bir atıf grubu tek rozet kümesi, ayraç ve virgül metinde kalmaz, çok sayfa «+N». */
const html = (text: string) => renderToStaticMarkup(<AnswerText text={text} />);
const pills = (h: string) => [...h.matchAll(/class="zk-page-ref"[^>]*>([^<]*)</g)].map((m) => m[1]);
const plain = (h: string) => h.replace(/<button[\s\S]*?<\/button>/g, '#').replace(/<span class="zk-page-ref"[^>]*>[^<]*<\/span>/g, '#').replace(/<[^>]+>/g, '');

describe('AnswerText — atıf grupları', () => {
  it('«(s.81, 101,130]» üç rozet, ayraç/virgül kalmaz', () => {
    const h = html("Kötü karakter Gölge'dir (s.81, 101,130].");
    expect(pills(h)).toEqual(['s.81', '101', '130']);
    expect(plain(h)).toBe('Kötü karakter Gölge&#x27;dir ###.');
  });
  it('uzun listede ilk 3 sayfa ve «+N»', () => {
    const h = html('Bu konu anlatılır s.17, 44,59,68,88,93,95,119,120,124,128,135,149,160,171,174,191,192]');
    expect(pills(h)).toEqual(['s.17', '44', '59']);
    expect(h).toContain('>+15</button>');
    expect(plain(h)).toBe('Bu konu anlatılır ####');
  });
  it('dört sayfa «+1» yerine hepsi', () => {
    expect(pills(html('[s. 4, 59, 68, 88]'))).toEqual(['s. 4', '59', '68', '88']);
  });
});
