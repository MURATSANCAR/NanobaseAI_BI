import type { AdminSettings } from '../engine';
import { trFold } from '../nav/navModel';

/**
 * Yönetim › Ayarlar'ın ikinci düzey gezinmesi. Kategori köprüdeki ayar grubunun `category` alanından gelir
 * (backend/semantic_bridge/admin.py → CATEGORIES, GROUPS). Kategorisi olmayan ya da bilinmeyen kategoriye
 * yazılmış grup «Diğer»e düşer: yeni eklenen bir ayar grubu hiçbir zaman ekrandan kaybolmaz.
 */

export const OTHER = { id: 'diger', label: 'Diğer' } as const;

type Group = AdminSettings['groups'][number];
export type SettingsCategory = { id: string; label: string; groups: Group[] };

/** Kategoriler köprünün sırasıyla, her biri kendi gruplarıyla; boş kategori listelenmez, «Diğer» en sonda. */
export function categorize(data: Pick<AdminSettings, 'groups' | 'categories'>): SettingsCategory[] {
  const cats = (data.categories ?? []).filter((c) => c.id !== OTHER.id);
  const known = new Set(cats.map((c) => c.id));
  const out: SettingsCategory[] = cats.map((c) => ({ id: c.id, label: c.label, groups: [] }));
  const other: SettingsCategory = { ...OTHER, groups: [] };
  for (const g of data.groups) {
    const at = g.category && known.has(g.category) ? out.find((c) => c.id === g.category)! : other;
    at.groups.push(g);
  }
  return [...out, other].filter((c) => c.groups.length > 0);
}

/** Adres çubuğundaki kategori; yoksa ya da artık yoksa ilk kategori. */
export function pickCategory(cats: SettingsCategory[], wanted: string | null): SettingsCategory | undefined {
  return cats.find((c) => c.id === wanted) ?? cats[0];
}

export type SettingsHit = { group: Group; category: SettingsCategory; keys: string[] | 'all' };

/**
 * Ayar araması: grup adı, ayar etiketi ve ayar anahtarı üzerinde (Türkçe harf duyarsız, her sözcük geçmeli).
 * Grup adı tutarsa grubun bütün ayarları, yoksa yalnız tutan ayarlar gösterilir. Sonuç kategorilerin sırasıyla.
 */
export function searchSettings(data: Pick<AdminSettings, 'groups' | 'categories' | 'items'>, query: string): SettingsHit[] {
  const words = trFold(query).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const has = (text: string) => {
    const t = trFold(text);
    return words.every((w) => t.includes(w));
  };
  const hits: SettingsHit[] = [];
  for (const category of categorize(data)) {
    for (const group of category.groups) {
      if (has(`${group.label} ${category.label}`)) {
        hits.push({ group, category, keys: 'all' });
        continue;
      }
      const keys = data.items.filter((s) => s.group === group.id && has(`${s.label} ${s.key} ${group.label}`)).map((s) => s.key);
      if (keys.length) hits.push({ group, category, keys });
    }
  }
  return hits;
}
