import { useState } from 'react';
import { bookCoverUrl } from '../engine';

/** Küçük kapak görseli (sohbet çipi, sohbet başlığı, cevap balonu, kitap detayı). Yüklenemezse hiç çizilmez:
 *  kırık resim ya da yer tutucu yok. Boyutu çağıran verir (`className`), köşe ve çerçeve burada sabittir. */
export default function Cover({ id, alt, className = '' }: { id: string; alt: string; className?: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) return null;
  return (
    <img
      src={bookCoverUrl(id)}
      alt={alt}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={`shrink-0 rounded-md border border-slate-200/80 bg-slate-100 object-cover ${className}`}
    />
  );
}
