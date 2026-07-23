import { describe, expect, it } from 'vitest';
import {
  isSqlLookingText,
  sanitizeChatDisplayValue,
  stripSqlFromChatText,
} from '@/utils/biChatSanitize';

describe('biChatSanitize', () => {
  it('detects SELECT cell values', () => {
    expect(isSqlLookingText('SELECT COUNT(*) FROM public.musteriler')).toBe(true);
    expect(isSqlLookingText('2488')).toBe(false);
    expect(isSqlLookingText('Adana')).toBe(false);
  });

  it('strips sql from reply text', () => {
    const raw =
      'Toplam şöyle:\n```sql\nSELECT 1\n```\nVe SELECT COUNT(*) FROM x; bitti.';
    const cleaned = stripSqlFromChatText(raw);
    expect(cleaned.toLowerCase()).not.toContain('select');
    expect(cleaned).toContain('Toplam');
  });

  it('strips SQL and EXPLAIN plan dumps from chat reply', () => {
    const raw = [
      'Sonuç başarıyla hesaplandı. Değer: 400360.0.',
      '',
      'SQL:',
      'SELECT COUNT(*) AS row_count FROM public.faturalar',
      '',
      'EXPLAIN:',
      'Limit  (cost=8806.74..8806.75 rows=1 width=8)',
      '  ->  Finalize Aggregate  (cost=8806.74..8806.75 rows=1 width=8)',
      '        ->  Gather  (cost=8806.52..8806.73 rows=2 width=8)',
      '              Workers Planned: 2',
      '              ->  Partial Aggregate  (cost=7806.52..7806.53 rows=1 width=8)',
      '                    ->  Parallel Seq Scan on faturalar t  (cost=0.00..7389.42 rows=166842 width=0)',
    ].join('\n');
    const cleaned = stripSqlFromChatText(raw);
    expect(cleaned).toBe('Sonuç başarıyla hesaplandı. Değer: 400360.0.');
    expect(cleaned.toLowerCase()).not.toContain('select');
    expect(cleaned.toLowerCase()).not.toContain('explain');
    expect(cleaned.toLowerCase()).not.toContain('seq scan');
    expect(cleaned).not.toContain('cost=');
  });

  it('replaces sql cells', () => {
    expect(sanitizeChatDisplayValue('SELECT * FROM t')).toBe('—');
    expect(sanitizeChatDisplayValue(42)).toBe(42);
  });
});
