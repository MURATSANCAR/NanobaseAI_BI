import { describe, expect, it } from 'vitest';
import { emptyRule, fmtPct, qs, ruleText, type FieldSpec } from './api';

const il: FieldSpec = { field: 'il', label: 'İl', kind: 'set', ops: ['in', 'not_in'], options: ['İstanbul'], optionLabels: null, help: null };
const kaynak: FieldSpec = { field: 'kaynak', label: 'Kaynak', kind: 'set', ops: ['in'], options: ['crm_lead'], optionLabels: { crm_lead: 'CRM müşteri adayı' }, help: null };
const yas: FieldSpec = { field: 'yas', label: 'Yaş', kind: 'range', ops: ['between'], options: null, optionLabels: null, help: null };
const temas: FieldSpec = { field: 'son_temas', label: 'Son temas', kind: 'days', ops: ['within', 'older'], options: null, optionLabels: null, help: null };

describe('okur segment kuralı biçimleri', () => {
  it('kural metni: seçenek etiketi, aralık, gün', () => {
    expect(ruleText({ field: 'kaynak', op: 'in', value: ['crm_lead'] }, kaynak, {})).toBe('Kaynak ∈ CRM müşteri adayı');
    expect(ruleText({ field: 'il', op: 'not_in', value: ['İstanbul'] }, il, {})).toBe('İl ∉ İstanbul');
    expect(ruleText({ field: 'yas', op: 'between', value: [18, null] }, yas, {})).toBe('Yaş: 18–…');
    expect(ruleText({ field: 'son_temas', op: 'older', value: 365 }, temas, {})).toBe('Son temas: 365 günden eski');
  });

  it('yeni kural alan türüne göre başlar', () => {
    expect(emptyRule(il)).toEqual({ field: 'il', op: 'in', value: [] });
    expect(emptyRule(yas)).toEqual({ field: 'yas', op: 'between', value: [null, null] });
    expect(emptyRule(temas)).toEqual({ field: 'son_temas', op: 'within', value: 365 });
  });

  it('sorgu parçası boş ve yanlış değerleri atar; oran', () => {
    expect(qs({ q: 'a@b.com', kisisel: false, page: 0 })).toBe('?q=a%40b.com&page=0');
    expect(qs({})).toBe('');
    expect(fmtPct(1, 4)).toBe('%25');
    expect(fmtPct(1, 0)).toBe('—');
  });
});
