import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Info, X } from 'lucide-react';
import clsx from 'clsx';
import { INFO, type InfoKey, type MetricInfo } from '../lib/definitions';

const W = 360; // popover genişliği
const M = 12; // ekran kenar boşluğu

/** "i" düğmesi: tıklanınca göstergenin tanımı, formülü, kaynağı, SQL'i ve uyarıları açılır.
 *  Panel `document.body` altına (portal) sabit konumla çizilir — tablo/kart içindeki
 *  `overflow-x-auto` kapları onu kırpamaz, sohbet paneli de üstünü örtemez. */
export function InfoTip({ k, className }: { k: InfoKey; className?: string; align?: 'left' | 'right' }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const info: MetricInfo = INFO[k];

  useLayoutEffect(() => {
    if (!open || !btnRef.current) return;
    const place = () => {
      const b = btnRef.current!.getBoundingClientRect();
      // Telefonda W (360) ekrandan geniş kalıyor: hizalama gerçek genişlikle yapılmazsa panel sağa kayıyor.
      const w = Math.min(W, window.innerWidth - 2 * M);
      const left = Math.min(Math.max(M, b.left), Math.max(M, window.innerWidth - w - M));
      const h = popRef.current?.offsetHeight ?? 320;
      const below = b.bottom + 8;
      const top = below + h > window.innerHeight - M ? Math.max(M, b.top - h - 8) : below;
      setPos({ top, left });
    };
    place();
    window.addEventListener('resize', place);
    window.addEventListener('scroll', place, true);
    return () => {
      window.removeEventListener('resize', place);
      window.removeEventListener('scroll', place, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!popRef.current?.contains(t) && !btnRef.current?.contains(t)) setOpen(false);
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
    <span className={clsx('relative inline-flex', className)}>
      <button
        ref={btnRef}
        type="button"
        aria-label={`${info.title}: nasıl hesaplanır?`}
        aria-expanded={open}
        title="Nasıl hesaplanır?"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className={clsx(
          'grid h-4 w-4 place-items-center rounded-full border text-[10px] leading-none transition',
          open ? 'border-brand bg-brand text-white' : 'border-ink-faint text-ink-faint hover:border-brand hover:text-brand',
        )}
      >
        <Info size={10} strokeWidth={2.4} />
      </button>

      {open &&
        createPortal(
          <div
            ref={popRef}
            role="dialog"
            aria-label={info.title}
            style={{ position: 'fixed', top: pos?.top ?? -9999, left: pos?.left ?? -9999, width: W, maxWidth: 'calc(100vw - 24px)', maxHeight: 'calc(100vh - 24px)' }}
            className="scroll-thin z-[120] overflow-y-auto rounded-2xl border border-line bg-white p-4 text-left shadow-[0_18px_48px_-18px_rgba(42,25,18,0.45)]"
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
          </div>,
          document.body,
        )}
    </span>
  );
}
