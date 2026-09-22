import { useEffect, useState } from 'react';
import { Loader2 } from 'lucide-react';
import type { ReportSnapshot } from './api';

/**
 * Raporun canlılık satırı: ne zamanki veri ekranda, sıradaki okuma ne zaman, şu an okunuyor mu.
 * Saniyede bir yalnız bu küçük bileşen yeniden çizilir; tablo etkilenmez.
 * Süreler sunucu saatine göre hesaplanır (`offset` = sunucu − istemci).
 */
const clock = (epoch: number) => new Date(epoch * 1000).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
const mmss = (seconds: number) => {
  const s = Math.max(0, Math.round(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

export default function LiveStatus({ snap, offset }: { snap: ReportSnapshot; offset: number }) {
  const [now, setNow] = useState(() => Date.now() / 1000 + offset);
  useEffect(() => {
    const tick = () => setNow(Date.now() / 1000 + offset);
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [offset]);

  const minutes = Math.round(snap.refreshIntervalSeconds / 60);
  const failedLast = !!snap.error && (snap.failedAt ?? 0) >= (snap.updatedAt ?? 0);

  let tone = 'is-live';
  let main: string;
  let side: string | null = null;
  if (snap.refreshing) {
    tone = 'is-busy';
    main = 'Logo ve CRM’den okunuyor';
    side = snap.refreshStartedAt ? mmss(now - snap.refreshStartedAt) : null;
  } else if (failedLast) {
    tone = 'is-warn';
    main = snap.updatedAt ? `Son okuma başarısız · ${clock(snap.updatedAt)} verisi gösteriliyor` : 'Kaynaklara ulaşılamadı';
    side = snap.nextRefreshAt ? `tekrar ${mmss(snap.nextRefreshAt - now)}` : null;
  } else if (snap.updatedAt) {
    main = `Canlı · ${clock(snap.updatedAt)} verisi`;
    side = snap.nextRefreshAt ? `sonraki okuma ${mmss(snap.nextRefreshAt - now)}` : null;
  } else {
    tone = 'is-busy';
    main = 'İlk okuma bekleniyor';
  }

  return (
    <div className={`mg-live ${tone}`} title={`Veriler ${minutes} dakikada bir Logo ve CRM’den otomatik okunur.`}>
      {tone === 'is-busy' ? <Loader2 size={13} className="animate-spin" aria-hidden /> : <span className="mg-live-dot" aria-hidden />}
      {/* Yalnız durum cümlesi duyurulur; saniyelik sayaç ekran okuyucuyu boğmasın. */}
      <span className="mg-live-main" role="status" aria-live="polite">{main}</span>
      {side && <span className="mg-live-side" aria-hidden>{side}</span>}
      <span className="mg-live-every">{minutes} dk’da bir otomatik</span>
    </div>
  );
}
