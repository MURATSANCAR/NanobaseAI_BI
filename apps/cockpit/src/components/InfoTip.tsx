import { useEffect, useRef, useState } from 'react';
import { Info, X } from 'lucide-react';
import clsx from 'clsx';
import { INFO, type InfoKey, type MetricInfo } from '../lib/definitions';

/** "i" düğmesi: tıklanınca göstergenin tanımı, formülü, kaynağı, SQL'i ve uyarıları açılır. */
export function InfoTip({ k, className, align = 'left' }: { k: InfoKey; className?: string; align?: 'left' | 'right' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const info: MetricInfo = INFO[k];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className={clsx('relative inline-flex', className)}>
      <button
        type="button"
        aria-label={`${info.title}: nasıl hesaplanır?`}
        aria-expanded={open}
        title="Nasıl hesaplanır?"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className={clsx('grid h-4 w-4 place-items-center rounded-full border text-[10px] leading-none transition', open ? 'border-brand bg-brand text-white' : 'border-ink-faint text-ink-faint hover:border-brand hover:text-brand')}
      >
        <Info size={10} strokeWidth={2.4} />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label={info.title}
          className={clsx('absolute z-40 mt-2 w-[360px] max-w-[85vw] rounded-2xl border border-line bg-white p-4 text-left shadow-card', align === 'right' ? 'right-0 top-full' : 'left-0 top-full')}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <div className="eyebrow">Nasıl hesaplanır</div>
              <div className="mt-0.5 font-display text-[15px] font-semibold leading-tight">{info.title}</div>
            </div>
            <button type="button" onClick={() => setOpen(false)} className="text-ink-faint hover:text-ink" aria-label="Kapat">
              <X size={14} />
            </button>
          </div>
          <p className="mt-2 text-[12px] leading-snug text-ink">{info.definition}</p>
          <div className="mt-2 rounded-xl bg-page px-3 py-2 font-mono text-[11px] leading-snug text-ink">{info.formula}</div>
          <div className="mt-2 text-[11px] text-ink-muted">
            <span className="font-semibold text-ink">Kaynak:</span> {info.sources.join(' · ')}
          </div>
          {info.sql && (
            <details className="mt-2">
              <summary className="cursor-pointer text-[11px] font-semibold text-brand">Kullanılan SQL (semantik model)</summary>
              <pre className="scroll-thin mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-ink p-2 text-[10px] text-white/90">{info.sql}</pre>
            </details>
          )}
          {info.caveats && info.caveats.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] leading-snug text-ink-muted">
              {info.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
