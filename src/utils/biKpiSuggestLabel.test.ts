import { describe, expect, it, beforeEach } from 'vitest';
import { setLocale } from '@/i18n';
import { kpiSuggestionPrompt, kpiSuggestionTitle } from '@/utils/biKpiSuggestLabel';

describe('biKpiSuggestLabel', () => {
  beforeEach(() => setLocale('tr'));

  it('localizes count chips', () => {
    expect(
      kpiSuggestionTitle({ id: '1', kind: 'count', table_name: 'acenteler' }),
    ).toBe('Acenteler: toplam kayıt');
  });

  it('localizes sum chips with field labels', () => {
    expect(
      kpiSuggestionTitle({
        id: '2',
        kind: 'sum',
        table_name: 'acente_hedefleri',
        measure: 'hedef_police',
      }),
    ).toBe('Acente hedefleri: Hedef poliçe toplamı');
  });

  it('builds Turkish chat prompts', () => {
    const prompt = kpiSuggestionPrompt({
      id: '3',
      kind: 'breakdown',
      table_name: 'araclar',
      measure: 'adet',
      category: 'yakit_tipi',
    });
    expect(prompt).toContain('Araçlar');
    expect(prompt).toContain('Yakıt tipi');
    expect(prompt.toLowerCase()).not.toContain('break down');
  });
});
