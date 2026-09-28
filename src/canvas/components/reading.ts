/** Belge okuma etiketinin metni (saf; vitest sınar). OCR'dan gelen alan «OCR · s. 3 · %91»; eşik altı güven uyarı
 *  tonunda; metin katmanından gelen alan yalnız sayfa numarası. Teknoloji adı yazılmaz. */
export type Okuma = 'metin' | 'ocr' | 'yok';

export type ReadingLabel = { text: string; tone: 'violet' | 'warn' | 'plain'; title: string };

const pct = (v: number) => `%${Math.round(v * 100)}`;

export function readingLabel(okuma?: Okuma | null, guven?: number | null, sayfa?: string | null, esik = 0.8): ReadingLabel | null {
  if (!okuma || okuma === 'yok') return null;
  if (okuma === 'metin') return sayfa ? { text: `s. ${sayfa}`, tone: 'plain', title: `Belgenin metninden, sayfa ${sayfa}.` } : null;
  const low = guven != null && guven < esik;
  return {
    text: `OCR${sayfa ? ` · s. ${sayfa}` : ''}${guven != null ? ` · ${pct(guven)}` : ''}`,
    tone: low ? 'warn' : 'violet',
    title: `Taranmış görüntüden okundu${sayfa ? `, sayfa ${sayfa}` : ''}${guven != null ? `, güven ${pct(guven)}` : ', güven ölçülemedi'}. Alıntı belgede birebir arandı.`,
  };
}
