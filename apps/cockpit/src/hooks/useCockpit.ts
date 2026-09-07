import { useQuery } from '@tanstack/react-query';
import { loadCockpit, type DataMode } from '../lib/metrics';
import { readSnapshot, saveSnapshot } from '../lib/snapshot';
import { loadPeriods, type Period } from '../lib/periods';
import { engineStatus } from '../lib/engine';

// Üretim varsayılanı 'live': önbellek (fixture) rakamı hiçbir zaman sessizce gösterilmez; motor cevap
// vermezse ekranda "Veri alınamadı" + hata görünür. Geliştirme için VITE_DATA_MODE=fixture|auto.
const MODE = ((import.meta.env.VITE_DATA_MODE as string | undefined) ?? 'live') as DataMode;

/** Ekran canlı bir tablodur: bu aralıkta kendiliğinden yenilenir. Yenileme kullanıcıya bir bekleme
 *  olarak yansımaz, çünkü köprü aynı beş sorguyu arka planda sıcak tutar (SEMANTIC_REFRESH_SEC) —
 *  istek kaynağa inmez, hazır sonucu alır. */
const REFRESH_MS = Number(import.meta.env.VITE_REFRESH_MS ?? 15_000);

/** Hangi yıllar seçilebilir — veritabanının kendi dönem tablosundan. Yıl listesi ekranın en
 *  üstündeki seçimi besler ve nadiren değişir, o yüzden uzun süre taze sayılır. */
export function usePeriods() {
  return useQuery({ queryKey: ['periods'], queryFn: loadPeriods, staleTime: 60 * 60_000, retry: 1 });
}

export function useCockpit(period: Period | null, year: number | null) {
  const enabled = Boolean(period && year);
  const boot = enabled ? readSnapshot(MODE, year as number) : null;
  return useQuery({
    queryKey: ['cockpit', MODE, period?.firm, period?.period, year],
    enabled,
    queryFn: async () => {
      const data = await loadCockpit(MODE, period as Period, year as number);
      saveSnapshot(MODE, year as number, data);
      return data;
    },
    // Elde bir kopya varsa ekran onunla açılır ve aynı anda tazesi istenir: kimse boş ekrana bakmaz.
    initialData: boot?.data,
    initialDataUpdatedAt: boot?.at,
    refetchInterval: REFRESH_MS,
    // Sekme arkadayken yenilemek kimseye bir şey göstermez; öne gelince zaten tazelenir.
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: REFRESH_MS,
  });
}

export function useEngine() {
  return useQuery({ queryKey: ['engine'], queryFn: engineStatus, retry: 0, staleTime: 60_000, refetchInterval: 60_000 });
}
