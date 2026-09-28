import { describe, expect, it } from 'vitest';
import { DRAFT_KEYS, mergeDraft, type Draft } from './preread';

const draft: Draft = {
  topic: 'İstanbul’da bir aile',
  genre: 'Kurgu (roman, öykü, masal)',
  ageGroup: '12–15 yaş',
  overlapNote: 'Katalogda konusu yakın kitaplar:\n1. Kayıp Kardeş',
  redline: 'dikkat',
  redlineNote: '- Şiddet (s. 3): «kavga sahnesi»',
  report: 'Ön okuma taslağı — Zeki AI önerisidir.',
};
const empty = { topic: '', genre: '', ageGroup: '', overlapNote: '', redline: '', redlineNote: '', report: '', contentScore: null as number | null, recommendation: '' };

describe('ön okuma taslağı → editör raporu formu', () => {
  it('taslak puan ve kabul/red önerisi alanı taşımaz', () => {
    expect(DRAFT_KEYS).not.toContain('contentScore' as never);
    expect(DRAFT_KEYS).not.toContain('recommendation' as never);
  });

  it('toplu aktarım yalnız boş alanları doldurur, puana ve öneriye dokunmaz', () => {
    const { form, changed } = mergeDraft({ ...empty, topic: 'Editörün konusu' }, draft);
    expect(form.topic).toBe('Editörün konusu');
    expect(form.genre).toBe(draft.genre);
    expect(form.redline).toBe('dikkat');
    expect(form.contentScore).toBeNull();
    expect(form.recommendation).toBe('');
    expect(changed).not.toContain('topic');
    expect(changed).toContain('report');
  });

  it('tek alan aktarımında uzun metin editörün yazdığının altına eklenir, silinmez', () => {
    const { form } = mergeDraft({ ...empty, report: 'Editörün notu.' }, draft, ['report']);
    expect(form.report.startsWith('Editörün notu.')).toBe(true);
    expect(form.report).toContain(draft.report as string);
    const again = mergeDraft(form, draft, ['report']);
    expect(again.changed).toEqual([]);
  });

  it('editörün seçtiği yayın ilkesi kararı taslakla değişmez', () => {
    const { form } = mergeDraft({ ...empty, redline: 'temiz' }, draft, ['redline']);
    expect(form.redline).toBe('temiz');
  });

  it('boş öneri alanı formu değiştirmez', () => {
    const { changed } = mergeDraft(empty, { ...draft, topic: null, genre: '', redline: null }, ['topic', 'genre', 'redline']);
    expect(changed).toEqual([]);
  });
});
