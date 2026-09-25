import { Suspense, lazy, useEffect, useRef, useState } from 'react';
import { Box, Loader2, Printer } from 'lucide-react';
import type { StudioJob } from '../../../engine';
import { Note, errText } from '../../../admin/ui';
import { Panel } from '../../kit';
import { press } from '../shared';
import { SCREEN, useProofBook, type PaperChoice, type ProofBook } from './api';
import './book3d.css';

/** Stüdyonun «3B ve prova» bölümü: kitap gerçek ölçüleriyle 3B (döner, açılır, sayfaları çevrilir; sunum, PNG,
 *  video) ve seçili kâğıtta baskı provası (ekran ↔ baskı karşılaştırması, renk kaybı ve mürekkep yükü uyarısı).
 *  Çizim kitaplığı ve 3B sahne yalnız bu bölüm ekrana yaklaşınca, 3B sekmesi açıkken indirilir. */

const Book3DView = lazy(() => import('./Book3DView'));
const ProofCompare = lazy(() => import('./ProofCompare'));

type Tab = '3d' | 'proof';

function useNear<T extends Element>(margin = '300px') {
  const ref = useRef<T>(null);
  const [near, setNear] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || near) return;
    if (typeof IntersectionObserver === 'undefined') { setNear(true); return; }
    const io = new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) setNear(true); }, { rootMargin: margin });
    io.observe(el);
    return () => io.disconnect();
  }, [near, margin]);
  return [ref, near] as const;
}

function Waiting() {
  return (
    <div className="flex h-[min(68vh,560px)] min-h-[300px] items-center justify-center rounded-2xl bg-slate-100/70 text-[12px] font-bold text-canvas-muted">
      <Loader2 className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden />Hazırlanıyor…
    </div>
  );
}

function Papers({ book, value, onChange, withScreen }: { book: ProofBook; value: PaperChoice; onChange: (p: PaperChoice) => void; withScreen: boolean }) {
  const items = [...(withScreen ? [{ key: SCREEN, label: 'Ekranda', note: 'Prova yok: ekrandaki renkler', white: '#ffffff' }] : []), ...book.papers];
  return (
    <div role="radiogroup" aria-label="Kâğıt" className="flex flex-wrap gap-1.5">
      {items.map((p) => {
        const on = p.key === value;
        return (
          <button key={p.key} type="button" role="radio" aria-checked={on} title={p.note} onClick={() => onChange(p.key)}
            className={`inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-[12px] font-bold ${press} ${on ? 'border-canvas-violet bg-violet-50 text-canvas-violet ring-2 ring-canvas-violet/20' : 'border-slate-200 bg-white/80 text-canvas-ink'}`}>
            <span className="h-3.5 w-3.5 rounded-full border border-slate-300" style={{ background: p.white }} aria-hidden />
            {p.label}
            {p.key === book.default_paper && <span className="font-semibold text-canvas-muted">· kitabın</span>}
          </button>
        );
      })}
    </div>
  );
}

export function BookProofSection({ jobId, d, rev }: { jobId: string; d: StudioJob; rev: string }) {
  const [ref, near] = useNear<HTMLDivElement>();
  const q = useProofBook(near ? jobId : '', rev);
  const book = q.data;
  const [tab, setTab] = useState<Tab>('3d');
  const [paper, setPaper] = useState<PaperChoice>(SCREEN);
  const proofPaper = paper === SCREEN ? book?.default_paper ?? 'kuse' : paper;
  const firstArt = d.pages.find((p) => p.art)?.no ?? 1;

  return (
    <div ref={ref} className="book3d mt-3 lg:mt-4">
      <Panel>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-[15px] font-extrabold">3B ve prova</h2>
            <p className="text-[12px] text-canvas-muted">Kitap gerçek ölçüleriyle; seçilen kâğıtta baskıda nasıl görüneceği.</p>
          </div>
          <div className="b3-tabs rounded-xl bg-slate-100 p-[3px]" data-tab={tab} role="tablist" aria-label="Görünüm">
            <span className="b3-tab-ind" aria-hidden />
            {([['3d', '3B kitap', Box], ['proof', 'Baskı provası', Printer]] as const).map(([k, label, Icon]) => (
              <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                className={`relative z-[1] inline-flex min-h-9 items-center justify-center gap-1.5 rounded-[10px] px-3 text-[12.5px] font-bold transition-colors duration-150 ${tab === k ? 'text-canvas-ink' : 'text-canvas-muted'}`}>
                <Icon className="h-4 w-4" aria-hidden />{label}
              </button>
            ))}
          </div>
        </div>

        {q.error && <div className="mt-3"><Note tone="err">{errText(q.error, 'Kitabın ölçüleri okunamadı.')}</Note></div>}
        {!book ? (!q.error && <div className="mt-3"><Waiting /></div>) : (
          <div className="mt-3 flex flex-col gap-3">
            <Papers book={book} value={tab === 'proof' ? proofPaper : paper} onChange={setPaper} withScreen={tab === '3d'} />
            <Suspense fallback={<Waiting />}>
              {tab === '3d'
                ? <Book3DView jobId={jobId} book={book} paper={paper} rev={rev} title={d.book?.title || d.state.title} />
                : <ProofCompare jobId={jobId} book={book} paper={proofPaper} rev={rev} pageHint={firstArt} />}
            </Suspense>
          </div>
        )}
      </Panel>
    </div>
  );
}
