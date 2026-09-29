/** Kitaba sor cevabındaki sayfa atıfları (ZEKI-43). Köprüdeki `editorial_citations.py` ile aynı kural:
 *
 *  - Atıf grubu: «s. 14», «[s.2]», «s. 12-14», «(s. 114, 127)», «ss. 3, 5 ve 9», «sayfa 7», «[s.3 p2]».
 *    Gruptaki HER sayı ayrı rozettir (önceden yalnız ilki rozet oluyordu); aralığın iki ucu ayrı rozettir.
 *  - Grubun kitabı: metinde gruptan önce en son anılan aday kitap (adı, kısa adı ya da yayınevi adı; Türkçe harf ve
 *    büyük/küçük farkı yok sayılır). Hiç anılmadıysa cevabın varsayılan kitabı (seçili kitap).
 *  - Sayfa durumu köprüden: o kitapta var (önizleme), yok (kaynaksız), bilinmiyor (önizleme dener).
 *  Kitap adı ya da sayfa numarası kodda yoktur; adlar köprünün katalogdan verdiği aday listesindendir. */

export type CitationBook = { id: string; title?: string | null; names: string[] };
export type Citations = {
  books: CitationBook[];
  defaultId: string | null;
  /** kitap kimliği → sayfa → o kitabın son okumasında var mı. Olmayan anahtar: denetlenemedi. */
  pages?: Record<string, Record<string, boolean>>;
};

const PREFIX = String.raw`(?:ss\.|sf\.|syf\.|s\.|sayfa(?:lar)?)`;
const ITEM = String.raw`\d+(?:[ \t]?[-–—][ \t]?\d+)?(?:[ \t]?p[ \t]?\d+)?`;
// Ek sayı yalnız ardından ondalık ya da kelime gelmiyorsa atıftır: «s. 14, 3 kişi» → yalnız 14.
const MORE = String.raw`(?:(?:[ \t]*[,;/&][ \t]*|[ \t]+(?:ve|ile)[ \t]+)(?:(?:ss|sf|syf|s)\.[ \t]?)?` + ITEM
  + String.raw`(?![ \t]*[.,]\d)(?![ \t]+(?!(?:ve|ile)[ \t]+\d)\p{L}))`;
const GROUP_SRC = String.raw`\[?` + PREFIX + String.raw`[ \t]?` + ITEM + MORE + String.raw`*\]?`;
const ITEM_RE = /\d+(?:[ \t]?p[ \t]?\d+)?/giu;
const REPREFIX = /(?:ss|sf|syf|s)\.[ \t]?$/iu;
const WORDISH = /[\p{L}\p{N}]/u;

export type CitePiece = { text: string } | { label: string; page: number };
export type Segment = { kind: 'text'; text: string } | { kind: 'cite'; pieces: CitePiece[] };

/** Bir grubun parçaları: ilk rozet önekiyle («s. 114»), sonrakiler yalnız sayı («127»); ayraçlar düz metin. */
function pieces(group: string): CitePiece[] {
  const body = group.replace(/^\[/, '').replace(/\]$/, '');
  const out: CitePiece[] = [];
  let last = 0;
  ITEM_RE.lastIndex = 0;
  for (let m = ITEM_RE.exec(body); m; m = ITEM_RE.exec(body)) {
    const page = Number(/\d+/.exec(m[0])?.[0]);
    let between = body.slice(last, m.index);
    let lead = '';
    if (out.length === 0) {
      lead = between; // önek: «s. », «sayfa »
      between = '';
    } else {
      const re = REPREFIX.exec(between);
      if (re) {
        lead = re[0];
        between = between.slice(0, re.index);
      }
    }
    if (between) out.push({ text: between });
    if (Number.isFinite(page) && page >= 1) out.push({ label: `${lead}${m[0]}`, page });
    else out.push({ text: `${lead}${m[0]}` });
    last = m.index + m[0].length;
  }
  if (last < body.length) out.push({ text: body.slice(last) });
  return out;
}

/** Metni düz parçalara ve atıf gruplarına böler (sırayla). */
export function splitCitations(text: string): Segment[] {
  const re = new RegExp(GROUP_SRC, 'giu');
  const out: Segment[] = [];
  let pos = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    // Önek bir kelimenin parçası olmamalı («vs. 14» atıf değildir); köşeli ayraçla başlayan grup zaten ayrıktır.
    const prev = text[m.index - 1];
    if (!m[0].startsWith('[') && prev && WORDISH.test(prev)) {
      re.lastIndex = m.index + 1;
      continue;
    }
    if (m.index > pos) out.push({ kind: 'text', text: text.slice(pos, m.index) });
    out.push({ kind: 'cite', pieces: pieces(m[0]) });
    pos = m.index + m[0].length;
  }
  if (pos < text.length) out.push({ kind: 'text', text: text.slice(pos) });
  return out;
}

const TR: Record<string, string> = { ı: 'i', İ: 'i', I: 'i', ç: 'c', Ç: 'c', ğ: 'g', Ğ: 'g', ö: 'o', Ö: 'o', ş: 's', Ş: 's', ü: 'u', Ü: 'u' };

/** «Anne Terliği'nde» → «anne terligi nde», «dedem-tekrar-cocuk-oldu» → «dedem tekrar cocuk oldu». */
export function norm(s: string | null | undefined): string {
  return Array.from(s ?? '', (ch) => TR[ch] ?? ch).join('').toLowerCase()
    .normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .replace(/[^0-9a-z]+/g, ' ').trim();
}

/** Parçada en son anılan aday kitap (anılışın bittiği yer en sağda olan; eşitse uzun ad). Yoksa null. */
export function lastMention(segment: string, books: CitationBook[]): string | null {
  const body = ` ${norm(segment)} `;
  let best: { end: number; len: number; id: string } | null = null;
  for (const b of books) {
    for (const n of b.names) {
      if (!n) continue;
      const i = body.lastIndexOf(` ${n} `);
      if (i < 0) continue;
      const cand = { end: i + n.length, len: n.length, id: b.id };
      if (!best || cand.end > best.end || (cand.end === best.end && cand.len > best.len)) best = cand;
    }
  }
  return best?.id ?? null;
}

export type PageStatus = 'ok' | 'missing' | 'unknown';

export function pageStatus(c: Citations, bookId: string | null, page: number): PageStatus {
  if (!bookId) return 'unknown';
  const known = c.pages?.[bookId]?.[String(page)];
  return known === true ? 'ok' : known === false ? 'missing' : 'unknown';
}

/** Köprü atıf özeti göndermediyse (eski köprü) cevabın tek kitabı varsayılandır: önceki davranış. */
export function citationsOf(q: { citations?: Citations | null; bookId?: string | null; bookTitle?: string | null }): Citations {
  if (q.citations && Array.isArray(q.citations.books)) return q.citations;
  return q.bookId ? { books: [{ id: q.bookId, title: q.bookTitle ?? null, names: [] }], defaultId: q.bookId, pages: {} } : { books: [], defaultId: null, pages: {} };
}

/** Metin sırayla okunurken «şu anki kitap»: düz parçadaki son anılış onu değiştirir, atıf onu kullanır. */
export class CiteCursor {
  current: string | null;
  constructor(readonly c: Citations) {
    this.current = c.defaultId;
  }
  read(text: string): void {
    this.current = lastMention(text, this.c.books) ?? this.current;
  }
  title(bookId: string | null): string | null {
    return this.c.books.find((b) => b.id === bookId)?.title ?? null;
  }
}
