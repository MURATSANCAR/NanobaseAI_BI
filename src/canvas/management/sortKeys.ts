/** Çok kolonlu sıralama (ZEKI-49): listedeki sıra önceliktir; ilk anahtar eşitse ikinciye bakılır. */
export type SortKey = { index: number; dir: 1 | -1 };

/** Başlığa her basış: azalan → artan → kaldır (ilk basış azalan: raporda büyük değer önce ilgilendirir). */
const nextDir = (d: 1 | -1 | undefined): 1 | -1 | null => (d === undefined ? -1 : d === -1 ? 1 : null);

/**
 * Düz tıklama tek kolona sıralar (o kolon zaten tek anahtarsa yönünü çevirir); Shift (ya da Ctrl/⌘) ile tıklama
 * kolonu mevcut sıralamaya ek anahtar yapar, yeniden basınca yönü çevirir, üçüncüde çıkarır.
 */
export function sortStep(s: SortKey[], index: number, additive: boolean): SortKey[] {
  const cur = s.find((k) => k.index === index);
  if (!additive) {
    if (s.length === 1 && cur) {
      const d = nextDir(cur.dir);
      return d === null ? [] : [{ index, dir: d }];
    }
    return [{ index, dir: -1 }];
  }
  if (!cur) return [...s, { index, dir: -1 }];
  const d = nextDir(cur.dir);
  return d === null ? s.filter((k) => k.index !== index) : s.map((k): SortKey => (k.index === index ? { index, dir: d } : k));
}
