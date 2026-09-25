import type { PlanPage, PlanRun } from '../../../engine';
import type { ReaderTarget } from './api';

/** Okur önerisini sayfa metnine uygulamak: işaretin hedefi (paragraf bloğu, balon, serbest yazı) içinde harf
 *  aralığını yeni metinle değiştirir. Biçim (renk, kalınlık) aralığın başladığı parçadan alınır; editörün elle
 *  verdiği biçim korunur, otomatik renk kuralının işareti (source:"auto") yeni metne taşınmaz. */

const runsText = (runs: PlanRun[]) => runs.map((r) => r.text).join('');

export function replaceInRuns(runs: PlanRun[], start: number, end: number, text: string): PlanRun[] {
  const out: PlanRun[] = [];
  let pos = 0;
  let placed = false;
  for (const r of runs) {
    const a = pos;
    const b = pos + r.text.length;
    pos = b;
    if (b <= start || a >= end) {
      if (!placed && a >= end) {                       // aralık boş ve bu parçanın başında
        out.push(styleOf(r, text));
        placed = true;
      }
      out.push(r);
      continue;
    }
    const head = r.text.slice(0, Math.max(0, start - a));
    const tail = r.text.slice(Math.max(0, end - a));
    if (head) out.push({ ...r, text: head });
    if (!placed) { out.push(styleOf(r, text)); placed = true; }
    if (tail) out.push({ ...r, text: tail });
  }
  if (!placed) out.push({ text });
  return out.filter((r) => r.text !== '');
}

function styleOf(r: PlanRun, text: string): PlanRun {
  return r.source === 'auto' ? { text } : { ...r, text };
}

export function targetText(page: PlanPage, target: ReaderTarget, id: string): string | null {
  if (target === 'block') {
    const b = page.text?.blocks.find((x) => x.id === id);
    return b ? runsText(b.runs) : null;
  }
  if (target === 'bubble') return page.bubbles.find((x) => x.id === id)?.text ?? null;
  const t = page.texts.find((x) => x.id === id);
  return t ? runsText(t.runs) : null;
}

/** Alıntının bugünkü yeri: kayıttaki aralıkta duruyorsa orası, metin başka yerde değiştiyse ilk geçtiği yer,
 *  hiç yoksa null (metin değişmiş; öneri uygulanamaz). */
export function findSpan(text: string | null, quote: string, start: number, end: number): [number, number] | null {
  if (text == null || !quote) return null;
  if (text.slice(start, end) === quote) return [start, end];
  const i = text.indexOf(quote);
  return i >= 0 ? [i, i + quote.length] : null;
}

export function replaceTarget(page: PlanPage, target: ReaderTarget, id: string, start: number, end: number, text: string): PlanPage {
  if (target === 'block' && page.text) {
    return { ...page, text: { ...page.text, blocks: page.text.blocks.map((b) => (b.id === id ? { ...b, runs: replaceInRuns(b.runs, start, end, text) } : b)) } };
  }
  if (target === 'bubble') {
    return { ...page, bubbles: page.bubbles.map((b) => (b.id === id ? { ...b, text: b.text.slice(0, start) + text + b.text.slice(end) } : b)) };
  }
  return { ...page, texts: page.texts.map((t) => (t.id === id ? { ...t, runs: replaceInRuns(t.runs, start, end, text) } : t)) };
}
