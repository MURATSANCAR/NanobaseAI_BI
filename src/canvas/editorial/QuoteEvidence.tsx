import { useState } from 'react';

/** Belgeden çıkarılan bir değerin dayanağı: birebir alıntı, sayfa ve okuma türü (taranmış sayfada «OCR» ve güven).
 *  Başvuru ön okuması (öneri 12) ve sözleşme şartı çıkarma (öneri 13) aynı görünümü kullanır. Uzun listede ilk
 *  alıntılar görünür, kalanı «n alıntı daha» ile açılır (kesilmez). */

export type QuoteRef = { alinti: string; sayfa: string; okuma: string; guven?: number | null };

export function PageChip({ q }: { q: QuoteRef }) {
  const ocr = q.okuma === 'ocr';
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 font-mono text-[10.5px] font-bold tabular-nums ${ocr ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-canvas-muted'}`}
      title={ocr ? 'Taranmış sayfadan okundu (OCR)' : 'Belgenin metninden'}
    >
      s. {q.sayfa}
      {ocr && ` · OCR${q.guven != null ? ` %${Math.round(q.guven * 100)}` : ''}`}
    </span>
  );
}

export default function QuoteEvidence({ items, first = 2 }: { items: QuoteRef[]; first?: number }) {
  const [all, setAll] = useState(false);
  if (!items.length) return null;
  const shown = all ? items : items.slice(0, first);
  return (
    <ul className="mt-1 space-y-1">
      {shown.map((q, i) => (
        <li key={`${q.sayfa}-${i}`} className="flex items-start gap-1.5 text-[11.5px] leading-snug text-canvas-muted">
          <PageChip q={q} />
          <q className="min-w-0 break-words italic">{q.alinti}</q>
        </li>
      ))}
      {items.length > first && (
        <li>
          <button type="button" onClick={() => setAll((v) => !v)} className="min-h-11 text-[11.5px] font-bold text-canvas-violet hover:underline sm:min-h-0">
            {all ? 'Daha az göster' : `${items.length - first} alıntı daha`}
          </button>
        </li>
      )}
    </ul>
  );
}
