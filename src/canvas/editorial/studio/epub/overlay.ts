/** Önizlemede dinle: ses eşlemesi (SMIL) okumasının saf yardımcıları (sınanır; tarayıcı ve ağ yok). */

export const ACTIVE_CLASS = '-epub-media-overlay-active';

export type Clip = { key: string; doc: string; id: string; audio: string; start: number; end: number };

export const clock = (v: string | null): number => {
  const m = /^(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)$/.exec(v ?? '');
  return m ? Number(m[1] ?? 0) * 3600 + Number(m[2]) * 60 + Number(m[3]) : NaN;
};

/** «../text/s005.xhtml#w-c0-1» → e-kitap içi yol (OEBPS'e göre). */
export function resolve(base: string, rel: string): string {
  const parts = base.split('/').slice(0, -1);
  for (const seg of rel.split('/')) {
    if (seg === '..') parts.pop();
    else if (seg && seg !== '.') parts.push(seg);
  }
  return parts.join('/');
}
