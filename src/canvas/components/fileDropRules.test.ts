import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { MB, UPLOAD_FEATURES, acceptLabel, checkFile, dragDepth, fmtSize, lockReason, noPermissionText, titleFromFilename } from './fileDropRules';

/** Ortak yükleme alanının kuralları: tür/boyut reddi, okunur tür adı, dosya adından başlık, sürükleme sayacı, yetki kilidi. */

const f = (name: string, size = 1000, type = '') => ({ name, size, type });

describe('tür ve boyut denetimi', () => {
  it('uzantı büyük/küçük harf duyarsız eşleşir, uygun dosya geçer', () => {
    expect(checkFile(f('Roman.DOCX'), '.docx,.pdf')).toBeNull();
    expect(checkFile(f('prova.pdf', 10, 'application/pdf'), '.pdf')).toBeNull();
  });

  it('yanlış tür adıyla ve kabul edilen türlerle reddedilir', () => {
    const err = checkFile(f('virus.exe'), '.docx,.pdf,.txt');
    expect(err).toContain('«virus.exe» bu alana uygun değil');
    expect(err).toContain('DOCX, PDF, TXT');
  });

  it('joker MIME türü türün başıyla eşleşir; türü boş dosya yalnız uzantıyla geçer', () => {
    expect(checkFile(f('foto.heic', 10, 'image/heic'), 'image/*')).toBeNull();
    expect(checkFile(f('ses.mp3', 10, 'audio/mpeg'), 'image/*')).not.toBeNull();
    expect(checkFile(f('dosya.xliff', 10, ''), '.xlf,.xliff')).toBeNull();
    expect(checkFile(f('foto.jpg', 10, ''), 'image/*')).not.toBeNull();
  });

  it('boyut sınırını aşan ve boş dosya gönderilmeden reddedilir', () => {
    expect(checkFile(f('kitap.pdf', 130 * MB), '.pdf', 120 * MB)).toBe('«kitap.pdf» 130 MB; bu alanın sınırı 120 MB.');
    expect(checkFile(f('kitap.pdf', 120 * MB), '.pdf', 120 * MB)).toBeNull();
    expect(checkFile(f('bos.txt', 0), '.txt')).toBe('«bos.txt» boş bir dosya.');
  });

  it('kabul listesi boşsa her tür geçer', () => {
    expect(checkFile(f('teslim.zip'), '')).toBeNull();
    expect(checkFile(f('teslim.zip'), undefined, 200 * MB)).toBeNull();
  });
});

describe('ekranda yazan kurallar', () => {
  it('kabul edilen türler okunur adla, tekrarsız', () => {
    expect(acceptLabel('.docx,.pdf,.txt,.md')).toBe('DOCX, PDF, TXT, MD');
    expect(acceptLabel('image/*,application/pdf')).toBe('görsel, PDF');
    expect(acceptLabel('.pdf,application/pdf')).toBe('PDF');
    expect(acceptLabel('')).toBe('her tür dosya');
  });

  it('boyut Türkçe ondalıkla', () => {
    expect(fmtSize(120 * MB)).toBe('120 MB');
    expect(fmtSize(12.4 * MB)).toBe('12,4 MB');
    expect(fmtSize(850 * 1024)).toBe('850 KB');
    expect(fmtSize(10)).toBe('1 KB');
  });
});

describe('dosya adından başlık (köprüdeki editorial_desk.title_from_filename ile aynı)', () => {
  it.each([
    ['Kayip_Zaman-son.docx', 'Kayip Zaman son'],
    ['Bir Roman - Taslak 3.txt', 'Bir Roman Taslak 3'],
    ['C:\\Belgeler\\Uzun  Yol.pdf', 'Uzun Yol'],
    ['yalnizad', 'yalnizad'],
    ['___.md', '___.md'],
  ])('%s → %s', (name, title) => {
    expect(titleFromFilename(name)).toBe(title);
  });
});

describe('sürükle-bırak vurgusu', () => {
  it('iç öğeye geçişte (enter/leave çifti) vurgu sönmez, çıkınca ve bırakınca söner', () => {
    let d = 0;
    d = dragDepth(d, 'enter'); // alan
    d = dragDepth(d, 'enter'); // içteki ikon
    d = dragDepth(d, 'leave'); // alandan ikona geçerken gelen leave
    expect(d).toBeGreaterThan(0);
    d = dragDepth(d, 'leave');
    expect(d).toBe(0);
    d = dragDepth(dragDepth(0, 'enter'), 'drop');
    expect(d).toBe(0);
    expect(dragDepth(0, 'leave')).toBe(0);
  });
});

describe('yetki kilidi', () => {
  it('rolde işlem yetkisi yoksa gereken yetkinin adı yazılır', () => {
    const t = lockReason({ feature: 'son-okuma.belge', featureAllowed: false });
    expect(t).toContain('Bu işlem için yetkiniz yok');
    expect(t).toContain('«Belge yükleyip inceletme»');
  });

  it('ekranın kendi bayrağı false ise yetki adı ya da verilen açıklama yazılır', () => {
    expect(lockReason({ feature: 'uyum.yaz', featureAllowed: true, allowed: false })).toBe(noPermissionText('uyum.yaz'));
    expect(lockReason({ featureAllowed: true, allowed: false, deniedText: 'Aday dosyasını İK ekler.' })).toBe('Aday dosyasını İK ekler.');
    expect(lockReason({ featureAllowed: true, allowed: false })).toBe('Bu işlem için yetkiniz yok.');
  });

  it('yetki varsa ya da henüz bilinmiyorsa kilit yok', () => {
    expect(lockReason({ feature: 'ceviri.yonet', featureAllowed: true })).toBeNull();
    expect(lockReason({ feature: 'ceviri.yonet', featureAllowed: true, allowed: undefined })).toBeNull();
    expect(lockReason({ featureAllowed: true, allowed: true })).toBeNull();
  });

  it('yetki adları köprü kataloğundaki etiketle birebir aynı', () => {
    const url = new URL('../../../backend/semantic_bridge/access_catalog.json', import.meta.url);
    const catalog = JSON.parse(readFileSync(url, 'utf-8')) as { features: Array<{ key: string; label: string }> };
    const labels = new Map(catalog.features.map((x) => [x.key, x.label]));
    for (const [key, label] of Object.entries(UPLOAD_FEATURES)) {
      expect(labels.get(`ozellik:${key}`), key).toBe(label);
    }
  });
});
