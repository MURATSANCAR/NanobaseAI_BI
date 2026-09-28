import { describe, expect, it } from 'vitest';
import { applySuggestion, conflicts, stillApplied, suggestionRows, type ExtractResult } from './extract';
import type { Terms } from './api';

const terms = (): Terms => ({
  title: 'Taslak', kind: 'telif-alis', company: '', parties: [], books: [], paymentType: 'tek', basis: 'brut', rates: { sert: 12 }, tiers: [],
  discountPct: null, currency: 'USD', advance: null, advanceRecoupable: true, flatFee: null, withholdingPct: null,
  start: null, end: null, openEnded: true, years: null, periodMonths: 6, paymentDays: 30, printRun: null,
  territory: '', language: '', rights: { temsil: true }, notes: 'Eski not',
});
const q = (alinti: string) => ({ alinti, sayfa: '1', okuma: 'metin' as const });
const result: ExtractResult = {
  alanlar: {
    'rates.karton': { deger: 10, kanit: [q('yazara %10 telif öder')], kaynak: 'kural', celiski: null },
    advance: { deger: 15000, kanit: [q('15.000,00 TL avans öder')], kaynak: 'kural', celiski: null },
    currency: { deger: 'TRY', kanit: [q('15.000,00 TL avans öder')], kaynak: 'kural', celiski: null },
    end: { deger: '2030-12-31', kanit: [q('31.12.2030 tarihine kadar')], kaynak: 'kural', celiski: null },
    flatFee: { deger: null, kanit: [], kaynak: null, celiski: [
      { deger: 5000, kanit: [q('5.000 TL tek ödeme')], kaynak: 'kural' },
      { deger: 7000, kanit: [q('7.000 TL tek ödeme')], kaynak: 'zeki' },
    ] },
  },
  haklar: {
    dil: [{ deger: 'Türkçe', alinti: 'Türkçe dilinde', kaynak: 'kural', sayfa: '1', okuma: 'metin' }],
    ulke: [], format: [{ deger: 'e-kitap', alinti: 'e-kitap olarak', kaynak: 'kural', sayfa: '1', okuma: 'metin', ad: 'E-kitap' }],
    bitis: null, munhasirlik: { deger: 'munhasir', alinti: 'münhasır olarak devreder', kaynak: 'kural', sayfa: '2', okuma: 'ocr', ad: 'Münhasır' },
  },
  maliHaklar: [{ deger: 'cogaltma', ad: 'Çoğaltma', kanit: [q('çoğaltma hakkı')], kaynak: 'kural' }],
  oneri: { rates: { karton: 10 }, advance: 15000, currency: 'TRY', end: '2030-12-31', openEnded: false, language: 'Türkçe',
    rights: { cogaltma: true, ekitap: true }, notesLine: 'Münhasırlık: Münhasır (belge s. 2)' },
  atilan: 2, kaynak: 'kural', neden: null,
  pencere: { sayi: 1, butce: 24000, ortusme: 1, okunamayan: [] },
  okuma: { sayfa: 2, ocrSayfa: ['2'], okunamayan: [], not: null, hatalar: [] },
};
const meta = { paymentTypes: {}, bases: {}, currencies: { TRY: 'TL' }, rates: { karton: 'Karton kapak' }, rights: { cogaltma: 'Çoğaltma', ekitap: 'E-kitap' } };

describe('sözleşme belgesinden şart önerisi', () => {
  it('her satır alanın kendi alıntısıyla gelir', () => {
    const rows = suggestionRows(result, meta);
    const keys = rows.map((r) => r.key);
    expect(keys).toEqual(expect.arrayContaining(['rates.karton', 'advance', 'currency', 'end', 'language', 'rights.cogaltma', 'rights.ekitap', 'notesLine']));
    expect(rows.find((r) => r.key === 'advance')?.text).toBe('15.000 TL');
    expect(rows.find((r) => r.key === 'rights.ekitap')?.evidence[0].alinti).toBe('e-kitap olarak');
    expect(rows.find((r) => r.key === 'notesLine')?.evidence[0].okuma).toBe('ocr');
    expect(keys).not.toContain('flatFee');
  });

  it('çelişen alan öneri olmaz, adaylarıyla ayrı gösterilir', () => {
    const c = conflicts(result, { flatFee: 'Tek ödeme tutarı' });
    expect(c).toHaveLength(1);
    expect(c[0].label).toBe('Tek ödeme tutarı');
    expect(c[0].items.map((x) => x.deger)).toEqual([5000, 7000]);
  });

  it('yalnız seçilen alanlar forma geçer; oran ve hak var olanın üstüne eklenir', () => {
    const t = applySuggestion(terms(), result.oneri, ['rates.karton', 'rights.ekitap', 'end']);
    expect(t.rates).toEqual({ sert: 12, karton: 10 });
    expect(t.rights).toEqual({ temsil: true, ekitap: true });
    expect(t.end).toBe('2030-12-31');
    expect(t.openEnded).toBe(false);
    expect(t.advance).toBeNull();
    expect(t.currency).toBe('USD');
  });

  it('münhasırlık notlara bir kez eklenir', () => {
    const once = applySuggestion(terms(), result.oneri, ['notesLine']);
    const twice = applySuggestion(once, result.oneri, ['notesLine']);
    expect(twice.notes).toBe('Eski not\nMünhasırlık: Münhasır (belge s. 2)');
  });

  it('kabul kaydına yalnız formda hâlâ önerilen değeri taşıyan alanlar yazılır', () => {
    const t = applySuggestion(terms(), result.oneri, ['advance', 'currency', 'rates.karton']);
    t.advance = 20000;
    expect(stillApplied(t, result.oneri, ['advance', 'currency', 'rates.karton'])).toEqual(['currency', 'rates.karton']);
  });
});
