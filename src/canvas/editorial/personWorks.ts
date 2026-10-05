/** Kişi ayrıntısında eserler rol başlığı altında toplanır (ZEKI-27).
 *
 *  Eskiden tek liste en yeni kayıttan eskiye akıyordu; hem yazar hem çevirmen olan birinin çevirileri yazdığı
 *  kitapların arasına, çoğu zaman önüne karışıyordu. Şimdi:
 *  - Her rol bir grup. Grup sırası sekmeye göre (kullanıcı geri bildirimi 10-05): Yazarlar'da «Yazar», Çevirmenler'de
 *    «Tercüme» en üstte, sonra eser sayısı çok olan rol, eşitse ada göre. Çizer ve serbest sekmesinde öncelik yok,
 *    roller alfabetik. «Rol girilmemiş» her zaman en sonda.
 *  - Grup içinde sıra köprünün sırasıdır (katılım kaydı en yeniden eskiye).
 *  - Aynı kitap aynı rolde iki kez kayıtlıysa bir kez yazılır.
 *  Kişiye ya da kitaba özel kural yoktur; sayı tavanı yoktur. */

export type PersonWork = { bookId: string | null; title: string | null; role: string | null; on: string | null };
export type WorkGroup = { role: string; works: PersonWork[] };

export const NO_ROLE = 'Rol girilmemiş';
export type WorkOrder = { first?: readonly string[]; alpha?: boolean };

export function groupWorks(works: readonly PersonWork[], order: WorkOrder = {}): WorkGroup[] {
  const first = order.first ?? [];
  const groups = new Map<string, { works: PersonWork[]; seen: Set<string> }>();
  for (const w of works) {
    const role = (w.role ?? '').trim() || NO_ROLE;
    const g = groups.get(role) ?? { works: [], seen: new Set<string>() };
    groups.set(role, g);
    const key = (w.bookId ?? '').toLowerCase() || `t:${(w.title ?? '').trim().toLocaleLowerCase('tr')}`;
    if (key !== 't:' && g.seen.has(key)) continue;
    g.seen.add(key);
    g.works.push(w);
  }
  const rank = (role: string) => {
    const i = first.indexOf(role);
    return i >= 0 ? i : first.length + (role === NO_ROLE ? 1 : 0);
  };
  return [...groups.entries()]
    .map(([role, g]) => ({ role, works: g.works }))
    .sort(
      (a, b) =>
        rank(a.role) - rank(b.role) ||
        (order.alpha ? 0 : b.works.length - a.works.length) ||
        a.role.localeCompare(b.role, 'tr'),
    );
}
