import { describe, expect, it } from 'vitest';
import { readingLabel } from './reading';

describe('readingLabel', () => {
  it('OCR alanı sayfa ve güvenle, eşik altı uyarı tonunda', () => {
    expect(readingLabel('ocr', 0.914, '3')).toEqual(expect.objectContaining({ text: 'OCR · s. 3 · %91', tone: 'violet' }));
    expect(readingLabel('ocr', 0.62, '4', 0.8)?.tone).toBe('warn');
    expect(readingLabel('ocr', null, null)?.title).toContain('güven ölçülemedi');
  });
  it('metin katmanı yalnız sayfa; okunamayan ya da boş etiket yok', () => {
    expect(readingLabel('metin', null, '2')).toEqual(expect.objectContaining({ text: 's. 2', tone: 'plain' }));
    expect(readingLabel('metin', null, null)).toBeNull();
    expect(readingLabel('yok', null, '1')).toBeNull();
    expect(readingLabel(undefined)).toBeNull();
  });
  it('teknoloji adı yazmaz', () => {
    expect(JSON.stringify(readingLabel('ocr', 0.9, '1'))).not.toMatch(/dots|deepseek|qwen|tesseract/i);
  });
});
