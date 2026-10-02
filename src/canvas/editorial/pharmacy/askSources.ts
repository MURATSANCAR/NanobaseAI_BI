import type { BookQuestion } from '../../engine';
import { CiteCursor, citationsOf, norm, splitCitations } from '../citations';

/** Kitap Eczanesi «Zeki'ye sor» cevabının kaynak kitapları: ekranda cevabın altında, tıklanınca kitabın ayrıntısı açılır.
 *
 *  Kaynak, cevabın kendisinden çıkar (yeni bir motor bilgisi istenmez):
 *  - Kart cevabı (kitap arayan soru): seçilen kitap kartları, sırasıyla.
 *  - Metin cevabı: köprünün atıf özetindeki aday kitaplardan cevapta adı geçenler, ve sayfa atıfı olan kitaplar
 *    (atıfın kitabı Kitaba sor'daki kuralla: metinde atıftan önce en son anılan kitap, yoksa varsayılan kitap).
 *  Sayfalar atıflardan, artan sırada. «Kitapta bulunamadı» cevabında kaynak gösterilmez.
 *  Kitap kimliği kart servisindeki kitap kimliğidir; Kitap Eczanesi'nin kitap kimliğiyle aynıdır. */
export type AskSource = { id: string; title: string; pages: number[] };

type Q = Pick<BookQuestion, 'answer' | 'notFound' | 'cards' | 'citations' | 'bookId' | 'bookTitle'>;

export function answerSources(q: Q): AskSource[] {
  if (!q.answer || q.notFound) return [];
  const out = new Map<string, { title: string; pages: Set<number> }>();
  const add = (id: string | null | undefined, title: string | null | undefined) => {
    if (!id) return null;
    const cur = out.get(id) ?? { title: '', pages: new Set<number>() };
    if (!cur.title && title) cur.title = title;
    out.set(id, cur);
    return cur;
  };
  for (const c of q.cards ?? []) add(c.id, c.publisher?.title || c.title);

  const cit = citationsOf(q);
  const titleOf = (id: string | null) => cit.books.find((b) => b.id === id)?.title ?? (id === q.bookId ? q.bookTitle : null);
  const body = ` ${norm(q.answer)} `;
  for (const b of cit.books) {
    if (b.names.some((n) => n && body.includes(` ${n} `))) add(b.id, b.title ?? null);
  }
  const cursor = new CiteCursor(cit);
  for (const seg of splitCitations(q.answer)) {
    if (seg.kind === 'text') {
      cursor.read(seg.text);
      continue;
    }
    const hit = add(cursor.current, titleOf(cursor.current));
    if (!hit) continue;
    for (const p of seg.pieces) if ('page' in p) hit.pages.add(p.page);
  }
  return [...out].map(([id, v]) => ({ id, title: v.title || 'Kitap', pages: [...v.pages].sort((a, b) => a - b) }));
}
