import { useState } from 'react';
import { BookOpen } from 'lucide-react';
import { ENGINE_BASE, type BookCard as Card } from '../engine';

export default function BookCard({ card, onAsk }: { card: Card; onAsk: () => void }) {
  const [failed, setFailed] = useState(false);
  const publisher = card.publisher;
  // Editördeki ad dosya adından gelebilir («anne-terligi»); CRM'deki yayın adı okunaklıdır.
  const title = publisher?.title || card.title;
  return (
    <article aria-label={title} className="my-3 min-w-0 rounded-2xl border border-slate-200 bg-white p-3 sm:p-4">
      <div className="flex flex-col items-start gap-3 sm:flex-row sm:gap-4">
        <div className="flex w-20 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-slate-100 sm:w-28">
          {card.cover && !failed ? (
            <img src={`${ENGINE_BASE}/api/v1/editorial/ask/covers/${encodeURIComponent(card.id)}`}
              alt={`${title} — ${card.cover.source === 'PDF_PAGE' ? 'kitabın içinden görsel' : 'kapak'}`}
              loading="lazy" onError={() => setFailed(true)} className="aspect-[2/3] w-full object-contain" />
          ) : <div className="flex aspect-[2/3] flex-col items-center justify-center gap-2 px-2 text-center text-xs text-canvas-muted">
            <BookOpen aria-hidden className="h-6 w-6" />Kapak mevcut değil
          </div>}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="break-words text-base font-bold leading-snug text-canvas-ink">{title}</h3>
          <p className="mt-1 break-words text-sm text-canvas-muted">
            {card.authors.length ? card.authors.join(', ') : 'Yazar bilgisi henüz doğrulanmadı.'}
            {card.authorsSource === 'CRM' && <span className="ml-1 text-xs">(yayınevi kaydı)</span>}
          </p>
          {publisher && publisher.illustrators.length > 0 && <p className="mt-0.5 break-words text-xs text-canvas-muted">Çizer: {publisher.illustrators.join(', ')}</p>}
          {card.cover?.source === 'PDF_PAGE' && <p className="mt-2 text-xs text-canvas-muted">Kapak yerine kitabın içinden bir sayfa gösteriliyor.</p>}
        </div>
      </div>
      <div className="mt-3 space-y-2 break-words text-sm leading-relaxed">
        {card.summary.length ? card.summary.map((sentence, index) => <p key={index}>
          {sentence.text}{sentence.pages.length > 0 && <span className="ml-1 text-xs text-canvas-violet">(s. {sentence.pages.join(', ')})</span>}
        </p>) : publisher?.summary ? <>
          <p className="text-xs font-bold text-canvas-muted">Yayınevinin tanıtımı (CRM)</p>
          {publisher.summary.split('\n').map((line, index) => <p key={index}>{line}</p>)}
        </> : <p className="text-canvas-muted">Güncel kitap özeti henüz hazır değil.</p>}
      </div>
      <button type="button" onClick={onAsk} className="mt-3 min-h-11 rounded-xl bg-canvas-violet/10 px-4 py-2 text-sm font-bold text-canvas-violet hover:bg-canvas-violet/20">Bu kitabı sor</button>
    </article>
  );
}
