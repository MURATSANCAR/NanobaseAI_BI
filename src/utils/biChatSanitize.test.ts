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

  it('replaces sql cells', () => {
    expect(sanitizeChatDisplayValue('SELECT * FROM t')).toBe('—');
    expect(sanitizeChatDisplayValue(42)).toBe(42);
  });
});
