import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { FileDropView, type FileDropViewProps } from './FileDrop';
import { MB, noPermissionText } from './fileDropRules';

/** Yükleme alanının görünümü: kurallar her zaman yazılı, sürükleme vurgusu, bekleme, yetkisiz ve pasif görünüm.
 *  Sunucu tarafı çizimle (tarayıcısız) sınanır; bileşenin davranış kuralları fileDropRules.test.ts'te. */

const base: FileDropViewProps = {
  inputId: 'fd',
  accept: '.docx,.pdf,.txt,.md',
  maxBytes: 120 * MB,
  title: 'Metin dosyası yükle',
  size: 'lg',
};
const html = (p: Partial<FileDropViewProps> = {}) => renderToStaticMarkup(createElement(FileDropView, { ...base, ...p }));

describe('FileDrop görünümü', () => {
  it('ilk görünümde başlık, tıkla/bırak açıklaması, kabul edilen türler ve boyut sınırı yazılı; dosya girişi açık', () => {
    const h = html();
    expect(h).toContain('data-filedrop');
    expect(h).toContain('Metin dosyası yükle');
    expect(h).toContain('sürükleyip bırakabilirsiniz');
    expect(h).toContain('Kabul edilen: DOCX, PDF, TXT, MD · en çok 120 MB');
    expect(h).toMatch(/<input[^>]*type="file"[^>]*accept="\.docx,\.pdf,\.txt,\.md"/);
    expect(h).not.toMatch(/<input[^>]*disabled/);
  });

  it('dosya üstüne gelince vurgu (data-drag) ve «bırakın» metni', () => {
    const h = html({ dragging: true });
    expect(h).toContain('data-drag="true"');
    expect(h).toContain('Bırakın, yüklensin');
  });

  it('yüklenirken «Yükleniyor…» ve giriş kapalı', () => {
    const h = html({ busy: true });
    expect(h).toContain('Yükleniyor…');
    expect(h).toMatch(/<input[^>]*disabled/);
  });

  it('yetkisiz kişide alan gizlenmez: kilitli, gereken yetki yazılı, giriş kapalı, vurgu yok', () => {
    const text = noPermissionText('son-okuma.belge');
    const h = html({ lockedText: text, dragging: true });
    expect(h).toContain('data-locked="true"');
    expect(h).toContain('Gereken yetki: «Belge yükleyip inceletme»');
    expect(h).toContain('Metin dosyası yükle');
    expect(h).toContain('Kabul edilen: DOCX, PDF, TXT, MD');
    expect(h).toMatch(/<input[^>]*disabled/);
    expect(h).not.toContain('data-drag="true"');
  });

  it('eksik seçim yüzünden pasifse nedeni yazılı', () => {
    const h = html({ disabled: true, disabledReason: 'Önce platformu seçin.' });
    expect(h).toContain('Önce platformu seçin.');
    expect(h).toMatch(/<input[^>]*disabled/);
  });

  it('reddedilen dosyanın hatası ve seçilen dosya gösterilir', () => {
    const h = html({ error: '«virus.exe» bu alana uygun değil.', picked: { name: 'rapor.xlsx', size: 2 * MB } });
    expect(h).toContain('role="alert"');
    expect(h).toContain('«virus.exe» bu alana uygun değil.');
    expect(h).toContain('rapor.xlsx');
    expect(h).toContain('2 MB');
  });

  it('düğme boyunda da kurallar altında yazılı ve sürükle-bırak alanıdır', () => {
    const h = html({ size: 'button', title: 'Kanıt yükle', accept: '.pdf', maxBytes: 10 * MB });
    expect(h).toContain('Kanıt yükle');
    expect(h).toContain('Kabul edilen: PDF · en çok 10 MB');
    expect(h).toContain('border-dashed');
  });
});
