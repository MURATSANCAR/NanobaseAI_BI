import { useEffect, useState } from 'react';

const MASCOT = `${import.meta.env.BASE_URL}zeki-ai.gif`;
const SHOW_MS = 5000;

/** The artwork already contains the brand: keep one visual signature. */
export function Splash({ onDone }: { onDone: () => void }) {
  const [leaving, setLeaving] = useState(false);
  const [reducedMotion] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  useEffect(() => {
    if (reducedMotion) { onDone(); return; }
    const timer = setTimeout(() => setLeaving(true), SHOW_MS);
    return () => clearTimeout(timer);
  }, [onDone, reducedMotion]);
  useEffect(() => {
    if (!leaving) return;
    const timer = setTimeout(onDone, 450);
    return () => clearTimeout(timer);
  }, [leaving, onDone]);
  if (reducedMotion) return null;

  return (
    <div role="dialog" aria-modal="true" aria-label="ZEKİ AI karşılama ekranı"
      className={`fixed inset-0 z-[100] flex h-[100dvh] flex-col items-center justify-center bg-[#F6EFE8] px-4 py-6 transition-opacity duration-500 ${leaving ? 'opacity-0' : 'opacity-100'}`}>
      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        <img src={MASCOT} alt="ZEKİ AI — Timaş Yayın Grubu" draggable={false}
          className="h-auto max-h-[78dvh] w-[min(100%,1120px)] object-contain mix-blend-multiply"
          style={{
            WebkitMaskImage: 'radial-gradient(ellipse farthest-side, #000 65%, transparent 100%)',
            maskImage: 'radial-gradient(ellipse farthest-side, #000 65%, transparent 100%)',
          }} />
      </div>
      <button type="button" autoFocus onClick={() => setLeaving(true)}
        className="mb-[env(safe-area-inset-bottom)] flex min-h-11 shrink-0 items-center gap-3 rounded-full border border-brand/15 bg-white/35 px-5 py-2 text-xs text-ink-muted transition hover:bg-white/70 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand">
        Çalışma alanına geç <span aria-hidden>→</span>
      </button>
    </div>
  );
}
