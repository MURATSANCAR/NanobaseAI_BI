import { useEffect, useState } from 'react';

const MASCOT = `${import.meta.env.BASE_URL}zeki-ai.gif`;
const SHOW_MS = 5000;
/** GIF'in kendi zemin rengi (köşe pikselleri): ekranla dikiş yeri kalmasın diye birebir aynı. */
const CANVAS = '#F6EFE8';

/** Açılış ekranı: sayfa ilk yüklendiğinde Zeki AI ~5 sn görünür, sonra solarak kapanır (tıklayınca hemen geçer). */
export function Splash({ onDone }: { onDone: () => void }) {
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setLeaving(true), SHOW_MS);
    return () => clearTimeout(t);
  }, []);
  useEffect(() => {
    if (!leaving) return;
    const t = setTimeout(onDone, 450);
    return () => clearTimeout(t);
  }, [leaving, onDone]);

  return (
    <div
      role="dialog"
      aria-label="Timaş Yayın Grubu yapay zekâ portalı açılışı"
      onClick={() => setLeaving(true)}
      className={`fixed inset-0 z-[100] flex cursor-pointer flex-col items-center justify-center gap-6 overflow-hidden p-4 transition-opacity duration-500 ${leaving ? 'opacity-0' : 'opacity-100'}`}
      style={{ backgroundColor: CANVAS }}
    >
      <div className="flex min-h-0 w-full flex-1 items-center justify-center">
        <img
          src={MASCOT}
          alt="Zeki AI — Timaş Yayın Grubu"
          className="h-auto max-h-full w-auto max-w-[min(94vw,1040px)] object-contain"
          style={{
            /* GIF karesinin kenarları zemine erisin: dikdörtgen sınırı görünmesin. */
            WebkitMaskImage: 'radial-gradient(closest-side, #000 78%, transparent 100%)',
            maskImage: 'radial-gradient(closest-side, #000 78%, transparent 100%)',
          }}
          draggable={false}
        />
      </div>
      <div className="flex shrink-0 flex-col items-center gap-2">
        <div className="font-display text-[24px] font-semibold tracking-tight text-ink">Zeki AI</div>
        <div className="text-[12px] text-ink-muted">Timaş Yayın Grubu · yapay zekâ destekli iş zekâsı</div>
        <div className="mt-1 h-1 w-56 overflow-hidden rounded-full bg-line">
          <div className="h-1 rounded-full bg-brand" style={{ animation: `splash-progress ${SHOW_MS}ms linear forwards` }} />
        </div>
        <div className="text-[10px] text-ink-faint">geçmek için tıklayın</div>
      </div>
    </div>
  );
}
