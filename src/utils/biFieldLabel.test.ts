import { describe, expect, it, beforeEach } from 'vitest';
import { setLocale } from '@/i18n';
import { biFieldLabel, biNumberFormatLabel, humanizeColumnId } from '@/utils/biFieldLabel';

describe('biFieldLabel', () => {
  beforeEach(() => setLocale('tr'));

  it('humanizes snake_case columns', () => {
    expect(humanizeColumnId('fraud_skoru')).toBe('Fraud skoru');
  });

  it('uses locale keys for known fields', () => {
    expect(biFieldLabel('bolge')).toBe('Bölge');
    expect(biFieldLabel('acente_sayisi')).toBe('Acente sayısı');
    expect(biFieldLabel('label')).toBe('Kategori');
    expect(biFieldLabel('value')).toBe('Değer');
  });

  it('localizes number formats', () => {
    expect(biNumberFormatLabel('number')).toBe('Sayı');
    expect(biNumberFormatLabel('percent')).toBe('Yüzde');
    expect(biNumberFormatLabel('currency')).toBe('Para birimi');
  });
});
