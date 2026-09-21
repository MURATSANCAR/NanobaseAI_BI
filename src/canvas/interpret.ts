/**
 * Belirsiz kelime düzeltmesi. Motor "bakiye"yi Cari bakiyesi olarak yorumlayıp cevap verdiğinde
 * alternatifler (Banka bakiyesi, Kasa bakiyesi) çip olarak gösterilir. Çipe tıklamak yeni bir uç
 * çağırmaz: sorudaki kelime alternatifin `rephrase` ifadesiyle değiştirilip soru yeniden sorulur.
 */
import type { AnswerInterpretation, InterpretationAlternative } from './engine';
import type { InterpretChip } from './stitch/data';

const low = (s: string) => s.toLocaleLowerCase('tr-TR');
const words = (s: string) => low(s).match(/[\p{L}\p{N}]+/gu) ?? [];

// Ek alınca sözcük sonu ünsüzü yumuşar: kitap→kitabı, ağaç→ağacı, dört→dördü, ek→eği, renk→rengi.
const SOFT: Record<string, string[]> = { p: ['b'], ç: ['c'], t: ['d'], k: ['ğ', 'g'] };

/** `word`, `term`in kendisi ya da ekli biçimi mi? bakiye → bakiyesi, bakiyemiz; kitap → kitabı. */
function inflects(word: string, term: string): boolean {
  // Kısa terim ("ay") uzun sözcüğün başına rastlantıyla oturmasın ("ayrıntı"): eke dar pay.
  const maxSuffix = term.length < 4 ? 3 : 6;
  if (word.length - term.length > maxSuffix) return false;
  if (word.startsWith(term)) return true;
  const stem = term.slice(0, -1);
  return word.length > term.length && word.startsWith(stem) && (SOFT[term.slice(-1)] ?? []).includes(word[stem.length]);
}

type Token = { w: string; start: number; end: number };

/**
 * Sorudaki `term`i (ekli biçimiyle) `rephrase` ile değiştirir: "Bakiyesi ne kadar?" + banka bakiyesi →
 * "Banka bakiyesi ne kadar?". Seçilen anlamın niteleyicisi soruda yazılıysa ("cari bakiye") o da gider;
 * yoksa "cari banka bakiyesi" çıkardı. Kelime bulunamazsa soru bozulmaz, sonuna açıklama eklenir.
 */
export function rephraseQuestion(question: string, term: string, rephrase: string, chosenLabel = ''): string {
  const rep = rephrase.trim();
  const termWords = words(term);
  if (!rep || !termWords.length) return question;
  const tokens: Token[] = [...question.matchAll(/[\p{L}\p{N}]+/gu)].map((m) => ({
    w: low(m[0]),
    start: m.index ?? 0,
    end: (m.index ?? 0) + m[0].length,
  }));
  const n = termWords.length;
  let hit = -1;
  for (let i = 0; i + n <= tokens.length && hit < 0; i++) {
    const ok = termWords.every((tw, j) => (j < n - 1 ? tokens[i + j].w === tw : inflects(tokens[i + j].w, tw)));
    if (ok) hit = i;
  }
  if (hit < 0) return `${question.trimEnd()} (${rep} kastediliyor)`;

  // Seçilen anlamın terim dışındaki sözcükleri ("Cari bakiyesi" → cari) hemen öndeyse onlar da değişir.
  const modifiers = new Set(words(chosenLabel).filter((w) => !termWords.some((tw) => inflects(w, tw))));
  let first = hit;
  while (first > 0 && modifiers.has(tokens[first - 1].w) && /^\s+$/.test(question.slice(tokens[first - 1].end, tokens[first].start))) {
    first--;
  }
  const start = tokens[first].start;
  const end = tokens[hit + n - 1].end;
  const head = question[start];
  const upper = head !== low(head);
  const text = upper ? rep[0].toLocaleUpperCase('tr-TR') + rep.slice(1) : rep;
  return question.slice(0, start) + text + question.slice(end);
}

/** Soru eki ünlü uyumuna uyar: "Banka bakiyesi mi?", "Ödeme planı mı?", "Vade sonu mu?". */
export function questionParticle(label: string): string {
  const vowels = low(label).match(/[aıoueiöüâîû]/g);
  const v = vowels?.[vowels.length - 1] ?? 'i';
  if ('aıâ'.includes(v)) return 'mı';
  if ('ouû'.includes(v)) return 'mu';
  if ('öü'.includes(v)) return 'mü';
  return 'mi';
}

/** Motorun `interpretations` alanını çipe çevirir. Eksik/bozuk kayıt sessizce atlanır; boş liste = çip yok. */
export function toChips(list: AnswerInterpretation[] | undefined, question: string): InterpretChip[] {
  if (!Array.isArray(list)) return [];
  const out: InterpretChip[] = [];
  for (const it of list as Array<Partial<AnswerInterpretation> | null>) {
    const term = typeof it?.term === 'string' ? it.term.trim() : '';
    const chosen = typeof it?.chosen?.label === 'string' ? it.chosen.label.trim() : '';
    if (!it || !term || !chosen || !Array.isArray(it.alternatives)) continue;
    const alternatives = it.alternatives
      .filter((a: Partial<InterpretationAlternative> | null) =>
        typeof a?.label === 'string' && a.label.trim() !== '' && typeof a.rephrase === 'string' && a.rephrase.trim() !== '')
      .slice(0, 3)
      .map((a) => ({ label: a.label.trim(), question: rephraseQuestion(question, term, a.rephrase, chosen) }));
    if (!alternatives.length) continue;
    out.push({ term, chosen, basis: it.basis === 'context' ? 'context' : 'default', alternatives });
  }
  return out;
}
