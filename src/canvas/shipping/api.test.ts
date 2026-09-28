import { describe, expect, it } from 'vitest';
import { ageTone, fmtDays, fmtMoney, previousMonth, qs, shippingApi } from './api';

describe('kargo ekranı yardımcıları', () => {
  it('sorgu parçası: boş, null ve false atılır; 0 kalır', () => {
    expect(qs({ q: '', firma: null, yenile: false, gun: 0, sayfa: 2 })).toBe('?gun=0&sayfa=2');
    expect(qs({})).toBe('');
  });

  it('bekleyen yaşı eşiğe göre renklenir; yaş yoksa nötr', () => {
    expect(ageTone(2, 5)).toBe('ok');
    expect(ageTone(5, 5)).toBe('warn');
    expect(ageTone(10, 5)).toBe('err');
    expect(ageTone(null, 5)).toBe('muted');
  });

  it('önceki ay yıl dönümünde doğru', () => {
    expect(previousMonth(new Date(2026, 0, 15))).toBe('2025-12');
    expect(previousMonth(new Date(2026, 8, 28))).toBe('2026-08');
  });

  it('boş değer uydurulmaz', () => {
    expect(fmtMoney(null)).toBe('—');
    expect(fmtDays(undefined)).toBe('—');
  });

  it('Excel adresi liste ve süzgeçle kurulur', () => {
    expect(shippingApi.exportUrl('bekleyen', { gun: 5, firma: undefined })).toMatch(/\/api\/v1\/shipping\/export\/bekleyen\.xlsx\?gun=5$/);
  });
});
