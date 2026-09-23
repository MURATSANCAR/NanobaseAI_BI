import { useState, useSyncExternalStore } from 'react';
import { useIsFetching, useQueryClient, type Query } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { requestFreshData } from './engine';

/** Veri gösteren bütün ekranların otomatik yenileme aralığı (main.tsx varsayılanı). */
export const DATA_REFRESH_MS = 5 * 60_000;

const SESSION_KEY = 'timas-session';
const counted = (q: Query) => q.getObserversCount() > 0 && q.queryKey[0] !== SESSION_KEY;
const clock = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });

/** Açık ekrandaki verinin en eski alınma anı: ekranın tamamı en az o kadar günceldir. */
function useOldestUpdate(): number {
  const qc = useQueryClient();
  const cache = qc.getQueryCache();
  return useSyncExternalStore(
    (notify) => cache.subscribe(notify),
    () => {
      const times = cache.getAll().filter(counted).map((q) => q.state.dataUpdatedAt).filter(Boolean);
      return times.length ? Math.min(...times) : 0;
    },
  );
}

/**
 * Üst şeritteki "Verileri yenile": açık ekranın bütün sorgularını kaynaktan yeniden okutur
 * (köprü önbelleği atlanır). Sayfa yenilenmez; filtreler, yazılmış metin ve kaydırma yerinde kalır.
 * Yanında son güncelleme saati ve otomatik yenileme aralığı yazar.
 */
export default function DataRefresh() {
  const qc = useQueryClient();
  const fetching = useIsFetching({ predicate: counted }) > 0;
  const [manual, setManual] = useState(false);
  const oldest = useOldestUpdate();
  const minutes = Math.round(DATA_REFRESH_MS / 60_000);
  const note = `${minutes} dk'da bir otomatik yenilenir`;
  const when = oldest ? `Güncellendi ${clock.format(oldest)}` : 'Veriler alınıyor';

  const refresh = async () => {
    if (manual) return; // tek tık iki kez koşmasın
    setManual(true);
    requestFreshData();
    await qc.refetchQueries({ type: 'active', predicate: counted });
    setManual(false);
    const failed = qc.getQueryCache().getAll().filter((q) => counted(q) && q.state.status === 'error');
    if (failed.length) toast.error('Bazı veriler yenilenemedi; son alınan değerler ekranda duruyor.');
  };

  return (
    <div className="glass-panel flex items-center gap-2 rounded-full py-1 pl-1 pr-1 shadow-glass-float sm:pr-3">
      <button
        type="button"
        onClick={refresh}
        disabled={manual}
        aria-label="Verileri yenile"
        title={`${when} · ${note}`}
        className="flex min-h-10 min-w-10 items-center justify-center gap-1.5 whitespace-nowrap rounded-full px-2.5 text-[11px] font-bold text-ink transition-[transform,background-color,color] duration-150 ease-out hover:bg-white hover:text-violet active:scale-[0.97] disabled:cursor-progress sm:min-h-8 sm:min-w-0 sm:px-3 sm:text-xs"
      >
        <RefreshCw aria-hidden className={`h-3.5 w-3.5 shrink-0 ${fetching ? 'motion-safe:animate-spin motion-reduce:opacity-50' : ''}`} />
        <span className="hidden sm:inline">{manual ? 'Yenileniyor…' : 'Verileri yenile'}</span>
      </button>
      <span className="hidden flex-col leading-tight md:flex" aria-live="polite">
        <span className="text-[11px] font-semibold tabular-nums text-ink">{when}</span>
        <span className="text-[10px] font-medium text-muted">{note}</span>
      </span>
    </div>
  );
}
