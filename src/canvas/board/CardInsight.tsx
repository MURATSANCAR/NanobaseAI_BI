import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { dateTime } from '../format';
import { Note, errText } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import ReasonPanel, { NarrativePill } from '../reason/ReasonPanel';
import { reasonApi, type CardChange } from '../reason/api';

/** Pano kartının «ne değişti» ve «neden» yaprağı. Fark sunucuda kodla bulunur (önceki sonuç ↔ yeni sonuç); Zeki AI
 *  yalnız bu olguları madde madde anlatır, bir kez üretilir ve saklanır. «Neden?» kartın sorusunu ayrıştırır.
 *  Ortak yan panel (masaüstünde sağda, telefonda alttan). */

export function cardChange(data: unknown): CardChange | null {
  const f = (data as { fark?: CardChange } | undefined)?.fark;
  return f && Array.isArray(f.maddeler) ? f : null;
}

function ChangeNote({ cardId, fark }: { cardId: string; fark: CardChange }) {
  const want = ENGINE_ENABLED && !fark.ilk && Boolean(fark.degisti) && !fark.anlatildi;
  const q = useQuery({ queryKey: ['pano-fark', cardId, fark.zaman], queryFn: () => reasonApi.cardChange(cardId), enabled: want,
    staleTime: Infinity, retry: false });
  const note = q.data ?? fark;
  return (
    <section>
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <h3 className="text-[14px] font-extrabold">Ne değişti</h3>
        {!fark.ilk && fark.degisti && <NarrativePill kaynak={note.kaynak} />}
        {fark.zaman && <span className="text-[11px] text-canvas-muted">son değişim {dateTime(fark.zaman)}</span>}
      </div>
      {q.isLoading && <p className="text-[12px] text-canvas-muted">Zeki AI anlatımı hazırlıyor… Şimdilik hesaplanan farklar gösteriliyor.</p>}
      {q.error && <Note tone="warn">{errText(q.error, 'Zeki AI anlatımı alınamadı; hesaplanan farklar gösteriliyor.')}</Note>}
      <ul className="flex list-disc flex-col gap-1 pl-5 text-[13px] leading-snug">
        {note.maddeler.map((m, i) => <li key={i}>{m}</li>)}
      </ul>
    </section>
  );
}

export default function CardInsight({ cardId, title, question, data, onClose }: {
  cardId: string; title: string; question: string; data: unknown; onClose: () => void;
}) {
  const fark = cardChange(data);
  return (
    <Sheet open modal wide onClose={onClose} title={title} subtitle="Önceki sonuca göre ne değişti ve rakamın nedeni">
      {fark ? <ChangeNote cardId={cardId} fark={fark} /> : (
        <p className="text-[12.5px] text-canvas-muted">Kart yenilendikçe önceki sonuçla arasındaki fark burada yazılır.</p>
      )}
      {question ? (
        <div className="mt-4 border-t border-slate-100 pt-3">
          <ReasonPanel queryKey={['fark', 'kart', cardId, question]} label="Neden? (kanal, cari, kitap katkısı)"
            load={(karsi) => reasonApi.forAnswer({ question, karsi })} />
        </div>
      ) : null}
    </Sheet>
  );
}
