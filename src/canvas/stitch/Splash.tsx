import { useEffect, useState } from 'react';
import zekiGif from '@/assets/zeki-ai.gif';

const KEY = 'timas-acilis-gosterildi';
const SURE = 5000;

/**
 * Açılış ekranı: ZEKİ tam sayfada 5 saniye, isteyen atlar.
 * Oturum başına bir kez; her sayfa geçişinde tekrar çıkmaz.
 */
export default function Splash({ onDone }: { onDone: () => void }) {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    const start = Date.now();
    const timer = window.setInterval(() => {
      const p = Math.min(100, ((Date.now() - start) / SURE) * 100);
      setPct(p);
      if (p >= 100) {
        window.clearInterval(timer);
        onDone();
      }
    }, 50);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === 'Enter') onDone();
    };
    window.addEventListener('keydown', onKey);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('keydown', onKey);
    };
  }, [onDone]);

  return (
    <div className="bg-mesh-canvas fixed inset-0 z-[100] flex flex-col items-center justify-center">
      <div className="dot-grid pointer-events-none absolute inset-0" />

      <div className="relative flex flex-col items-center">
        <img
          src={zekiGif}
          alt="ZEKİ AI"
          className="h-[46vh] max-h-[420px] w-auto drop-shadow-[0_24px_60px_rgba(20,30,60,0.18)]"
        />
        <div className="mt-6 text-center">
          <div className="text-[11px] font-bold uppercase tracking-[.24em] text-muted">Timaş Yayınları</div>
          <h1 className="mt-1 text-4xl font-extrabold tracking-tight text-ink">ZEKİ AI</h1>
          <p className="mt-2 text-sm font-semibold text-muted">Verinizle konuşan yayın zekâsı</p>
        </div>

        <div className="mt-8 h-1 w-56 overflow-hidden rounded-full bg-white/70">
          <div
            className="h-full rounded-full bg-gradient-to-r from-coral to-violet transition-[width] duration-75"
            style={{ width: `${pct}%` }}
          />
        </div>

        <button
          type="button"
          onClick={onDone}
          className="glass-panel mt-5 rounded-full px-5 py-2 text-xs font-bold text-ink shadow-glass-float transition hover:text-violet"
        >
          Atla
        </button>
      </div>
    </div>
  );
}

/** Bu oturumda açılış gösterildi mi. */
export function splashSeen(): boolean {
  try {
    return window.sessionStorage.getItem(KEY) === '1';
  } catch {
    return true;
  }
}

export function markSplashSeen(): void {
  try {
    window.sessionStorage.setItem(KEY, '1');
  } catch {
    /* saklama kapalıysa her açılışta gösterilir */
  }
}
