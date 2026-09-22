import { useEffect, useRef, useState } from 'react';
import { FileDown, Loader2 } from 'lucide-react';
import { bookAskApi } from '../engine';

/** «PDF olarak dışa aktar»: ekrandaki sohbeti (bu açılışta gösterilen soru kimlikleri, ekran sırasıyla) sunucuda
 *  üretilen A4 PDF olarak indirir. Tarayıcı yazdırma diyaloğu yok: köprü `application/pdf` döner, burada blob'a
 *  alınıp `<a download>` ile kaydedilir (oturum çerezi fetch ile gider; `<a href>` ile de giderdi ama hata
 *  gövdesini sayfa olarak açardı). `ids` boşken düğme devre dışı — aktarılacak bir şey yok. */
export default function ChatExport({ ids, bookTitle }: { ids: string[]; bookTitle?: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const run = async () => {
    if (busy || !ids.length) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(bookAskApi.exportUrl(ids, bookTitle), { credentials: 'include', signal: AbortSignal.timeout(120_000) });
      if (!res.ok) {
        const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
        const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
        throw new Error(res.status === 401 ? 'Oturum gerekli.' : msg || 'PDF hazırlanamadı.');
      }
      const blob = await res.blob();
      const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1]
        ?? `zeki-ai-sohbet-${new Date().toISOString().slice(0, 10)}.pdf`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Nesne URL'si indirme başladıktan sonra serbest bırakılır; hemen bırakılırsa Safari indirmeyi iptal eder.
      window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
    } catch (e) {
      if (alive.current) setError(e instanceof Error && e.name !== 'TimeoutError' ? e.message : 'PDF hazırlanamadı; tekrar deneyin.');
    } finally {
      if (alive.current) setBusy(false);
    }
  };

  const disabled = busy || !ids.length;
  return (
    <span className="flex items-center gap-2">
      {error && <span role="alert" className="hidden max-w-[22ch] truncate text-[11px] font-semibold text-red-700 sm:inline" title={error}>{error}</span>}
      <button
        type="button"
        onClick={run}
        disabled={disabled}
        aria-busy={busy || undefined}
        aria-label={ids.length ? `Sohbeti PDF olarak dışa aktar (${ids.length} soru)` : 'Dışa aktarılacak sohbet yok'}
        title={ids.length ? 'PDF olarak dışa aktar' : 'Önce bir soru sorun'}
        className="zk-press inline-flex min-h-9 items-center gap-1.5 rounded-full border border-canvas-violet/15 bg-white/90 px-3 text-[11.5px] font-bold text-canvas-ink shadow-sm transition-[border-color,color] duration-150 hover:border-canvas-violet/40 hover:text-canvas-violet disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-canvas-violet/15 disabled:hover:text-canvas-ink"
      >
        {busy ? <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" /> : <FileDown aria-hidden className="h-3.5 w-3.5" />}
        <span className="hidden sm:inline">{busy ? 'Hazırlanıyor' : 'PDF'}</span>
      </button>
    </span>
  );
}
