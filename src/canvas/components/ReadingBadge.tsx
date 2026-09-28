import { Pill } from '../admin/ui';
import { readingLabel, type Okuma } from './reading';

export type { Okuma } from './reading';

/** Ortak belge okuma hattının (doc_read) sayfa özeti: kaç sayfa taranmış görüntüden (OCR) okundu, en düşük güven,
 *  okunamayan sayfalar. Teknoloji adı yazılmaz; «OCR» işlevin adıdır. */
export type Reading = {
  sayfa: number;
  ocrSayfa: string[];
  okunamayan: string[];
  dusukGuven: string[];
  enDusukGuven: number | null;
  esik: number;
  hatalar: string[];
  not: string | null;
};

/** Belgeden çıkarılan tek alanın etiketi: OCR'dan geldiyse «OCR» + sayfa + güven; metin katmanındaysa yalnız sayfa. */
export function ReadingBadge({ okuma, guven, sayfa, esik = 0.8 }: { okuma?: Okuma | null; guven?: number | null; sayfa?: string | null; esik?: number }) {
  const l = readingLabel(okuma, guven, sayfa, esik);
  if (!l) return null;
  if (l.tone === 'plain') return <span className="text-[10.5px] text-canvas-muted" title={l.title}>{l.text}</span>;
  return (
    <span title={l.title}>
      <Pill tone={l.tone}>{l.text}</Pill>
    </span>
  );
}

/** Belge okuma özeti satırı (yalnız OCR ya da okunamayan sayfa varsa görünür). */
export function ReadingNote({ reading }: { reading?: Reading | null }) {
  if (!reading || (!reading.ocrSayfa.length && !reading.okunamayan.length && !reading.hatalar.length)) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[11.5px] text-canvas-muted">
      {reading.ocrSayfa.length > 0 && <Pill tone="violet">OCR</Pill>}
      <span className="min-w-0 break-words">
        {reading.not}
        {reading.dusukGuven.length > 0 && ` Düşük güvenli sayfalar: ${reading.dusukGuven.join(', ')} — alanları belgeyle karşılaştırın.`}
        {reading.hatalar.length > 0 && ` ${reading.hatalar.join(' ')}`}
      </span>
    </div>
  );
}
