import { describe, expect, it } from 'vitest';
import { fmtPct, fmtProb, showValue } from './api';

describe('kategori ağacı biçimleri', () => {
  it('değer gösterimi: düğüm yolu önce, liste virgülle, boş tire', () => {
    expect(showValue('n1', 'Timaş Çocuk > Çocuk > Masal')).toBe('Timaş Çocuk > Çocuk > Masal');
    expect(showValue(['Roman', 'Öykü'])).toBe('Roman, Öykü');
    expect(showValue([])).toBe('—');
    expect(showValue(null)).toBe('—');
  });

  it('oran ve olasılık', () => {
    expect(fmtPct(4546, 9091)).toBe('%50');
    expect(fmtPct(1, 0)).toBe('—');
    expect(fmtProb(0.957)).toBe('%96');
    expect(fmtProb(null)).toBeNull();
  });
});
