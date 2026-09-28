import { describe, expect, it } from 'vitest';
import { NAV, matchActive, permissionItemFor } from '../nav/navModel';
import { lastMonth } from './api';

describe('M36 dijital yayın rotaları', () => {
  it('satış ekranı ayrı sayfa yetkisine, katalog/fırsat/kitap ayrıntısı dijital yayına düşer', () => {
    expect(matchActive(NAV, '/dijital-yayin/satis')?.item.id).toBe('dijital-satis');
    expect(matchActive(NAV, '/dijital-yayin')?.item.id).toBe('dijital-yayin');
    expect(matchActive(NAV, '/dijital-yayin/firsatlar')?.item.id).toBe('dijital-yayin');
    expect(matchActive(NAV, '/dijital-yayin/kitap/ABC')?.item.id).toBe('dijital-yayin');
    expect(permissionItemFor('/dijital-yayin/satis?sekme=raporlar')?.id).toBe('dijital-satis');
  });

  it('rapor yüklemede varsayılan dönem geçen ay (YYYY-AA)', () => {
    expect(lastMonth()).toMatch(/^\d{4}-(0[1-9]|1[0-2])$/);
  });
});
