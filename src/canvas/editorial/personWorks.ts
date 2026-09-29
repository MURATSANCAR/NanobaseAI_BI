/** Kişi ayrıntısında eserler rol başlığı altında toplanır (ZEKI-27).
 *
 *  Eskiden tek liste en yeni kayıttan eskiye akıyordu; hem yazar hem çevirmen olan birinin çevirileri yazdığı
 *  kitapların arasına, çoğu zaman önüne karışıyordu. Şimdi:
 *  - Her rol bir grup; grup sırası: «Yazar» her zaman ilk, sonra ekranın kendi rolleri (ör. Çevirmenler
 *    sekmesinde «Tercüme»), sonra eser sayısı çok olan rol, eşitse ada göre.
 *  - Grup içinde sıra köprünün sırasıdır (katılım kaydı en yeniden eskiye).
 *  - Aynı kitap aynı rolde iki kez kayıtlıysa bir kez yazılır.
 *  Kişiye ya da kitaba özel kural yoktur; sayı tavanı yoktur. */

export type PersonWork = { bookId: string | null; title: string | null; role: string | null; on: string | null };
export type WorkGroup = { role: string; works: PersonWork[] };

export const NO_ROLE = 'Rol girilmemiş';
const FIRST = 'Yazar';

export function groupWorks(works: readonly PersonWork[], screenRoles: readonly string[] = []): WorkGroup[] {
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
    if (role === FIRST) return 0;
    const i = screenRoles.indexOf(role);
    return i >= 0 ? 1 + i : 1 + screenRoles.length + (role === NO_ROLE ? 1 : 0);
  };
  return [...groups.entries()]
    .map(([role, g]) => ({ role, works: g.works }))
    .sort((a, b) => rank(a.role) - rank(b.role) || b.works.length - a.works.length || a.role.localeCompare(b.role, 'tr'));
}
