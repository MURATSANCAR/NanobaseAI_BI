import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { categorize, pickCategory, searchSettings } from './settingsCategories';
import type { AdminSetting } from '../engine';

const item = (key: string, group: string, label: string): AdminSetting =>
  ({ key, group, label, type: 'text', help: '', source: 'default', value: '', hasValue: false }) as unknown as AdminSetting;

const data = {
  categories: [
    { id: 'baglanti', label: 'Bağlantılar ve giriş' },
    { id: 'zeki', label: 'Zeki AI' },
    { id: 'bos', label: 'Boş kategori' },
  ],
  groups: [
    { id: 'database', label: 'Logo veritabanı', help: '', category: 'baglanti' },
    { id: 'llm', label: 'Yapay zekâ modeli', help: '', category: 'zeki' },
    { id: 'yeni', label: 'Yeni modül', help: '' },
    { id: 'eski', label: 'Eski kategori', help: '', category: 'kaldirildi' },
    { id: 'crm', label: 'CRM', help: '', category: 'baglanti' },
  ],
  items: [
    item('SEMANTIC_DB_HOST', 'database', 'Sunucu adresi'),
    item('LLM_BASE_URL', 'llm', 'Model adresi'),
    item('YENI_ESIK', 'yeni', 'Uyarı eşiği'),
    item('CRM_DB', 'crm', 'Veritabanı adı'),
  ],
};

describe('ayar kategorileri', () => {
  it('her grup tam bir kategoride; kategorisiz ve bilinmeyen kategorili grup «Diğer»de, en sonda', () => {
    const cats = categorize(data);
    expect(cats.map((c) => c.id)).toEqual(['baglanti', 'zeki', 'diger']);
    expect(cats.map((c) => c.groups.map((g) => g.id))).toEqual([['database', 'crm'], ['llm'], ['yeni', 'eski']]);
    const all = cats.flatMap((c) => c.groups.map((g) => g.id));
    expect(all.sort()).toEqual(data.groups.map((g) => g.id).sort());
  });

  it('köprü kategori göndermezse bütün gruplar «Diğer» altında görünür (kaybolmaz)', () => {
    const cats = categorize({ groups: data.groups });
    expect(cats).toHaveLength(1);
    expect(cats[0].label).toBe('Diğer');
    expect(cats[0].groups).toHaveLength(data.groups.length);
  });

  it('adresteki kategori yoksa ilk kategori seçilir', () => {
    const cats = categorize(data);
    expect(pickCategory(cats, 'zeki')?.id).toBe('zeki');
    expect(pickCategory(cats, 'kayitlar')?.id).toBe('baglanti');
    expect(pickCategory(cats, null)?.id).toBe('baglanti');
  });

  it('arama grup adı, ayar etiketi ve anahtarı üzerinde, Türkçe harf duyarsız', () => {
    expect(searchSettings(data, 'veritabani').map((h) => [h.group.id, h.keys])).toEqual([
      ['database', 'all'],
      ['crm', ['CRM_DB']],
    ]);
    expect(searchSettings(data, 'llm_base').map((h) => [h.group.id, h.keys])).toEqual([['llm', ['LLM_BASE_URL']]]);
    expect(searchSettings(data, 'esigi').map((h) => [h.category.id, h.group.id])).toEqual([['diger', 'yeni']]);
    expect(searchSettings(data, '   ')).toEqual([]);
    expect(searchSettings(data, 'bulunmayan')).toEqual([]);
  });
});

describe('köprüdeki ayar grupları', () => {
  // admin.py: her grubun `category`si CATEGORIES'te tanımlı ve her grup tam bir kategoride (pytest aynısını köprüde denetler).
  const src = readFileSync(new URL('../../../backend/semantic_bridge/admin.py', import.meta.url), 'utf-8');
  const catBlock = src.slice(src.indexOf('CATEGORIES = ['), src.indexOf(']', src.indexOf('CATEGORIES = [')));
  const catIds = [...catBlock.matchAll(/\{"id": "(\w+)", "label"/g)].map((m) => m[1]);
  const groupBlock = src.slice(src.indexOf('GROUPS = ['), src.indexOf('#: Dosyada tutulan ayarlar'));
  const groups = [...groupBlock.matchAll(/\{"id": "(\w+)", (?:"category": "(\w+)", )?"label"/g)].map((m) => ({ id: m[1], category: m[2] }));

  it('onaylı on kategori, en az kırk grup; her grup bilinen tek kategoride', () => {
    expect(catIds).toEqual(['baglanti', 'zeki', 'eposta', 'pazarlama', 'seo', 'satis', 'lojistik', 'finans', 'ik', 'sistem']);
    expect(groups.length).toBeGreaterThanOrEqual(40);
    expect(new Set(groups.map((g) => g.id)).size).toBe(groups.length);
    expect(groups.filter((g) => !g.category || !catIds.includes(g.category))).toEqual([]);
  });

  it('bağlantı sınama düğmesi olan gruplar yerinde', () => {
    const by = Object.fromEntries(groups.map((g) => [g.id, g.category]));
    expect(['database', 'crm', 'directory'].map((g) => by[g])).toEqual(['baglanti', 'baglanti', 'baglanti']);
    expect(by.llm).toBe('zeki');
    expect([by.seo, by.geo]).toEqual(['seo', 'seo']);
    expect(by.mailbox).toBe('eposta');
  });
});
