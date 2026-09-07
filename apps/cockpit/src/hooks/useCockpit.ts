import { useQuery } from '@tanstack/react-query';
import { loadCockpit, type DataMode } from '../lib/metrics';
import { readSnapshot, saveSnapshot } from '../lib/snapshot';
import { engineStatus } from '../lib/engine';

// Üretim varsayılanı 'live': önbellek (fixture) rakamı hiçbir zaman sessizce gösterilmez; motor cevap
// vermezse ekranda "Veri alınamadı" + hata görünür. Geliştirme için VITE_DATA_MODE=fixture|auto.
const MODE = ((import.meta.env.VITE_DATA_MODE as string | undefined) ?? 'live') as DataMode;

/** Ekran canlı bir tablodur: bu aralıkta kendiliğinden yenilenir. Yenileme kullanıcıya bir bekleme
 *  olarak yansımaz, çünkü köprü aynı beş sorguyu arka planda sıcak tutar (SEMANTIC_REFRESH_SEC) —
 *  istek kaynağa inmez, hazır sonucu alır. */
const REFRESH_MS = Number(import.meta.env.VITE_REFRESH_MS ?? 15_000);

/** Sayfa açılırken bir kez okunur: ilk boyamada gösterilecek en son tablo. */
const BOOT = readSnapshot(MODE);

export function useCockpit() {
  return useQuery({
    queryKey: ['cockpit', MODE],
    queryFn: async () => {
      const data = await loadCockpit(MODE);
      saveSnapshot(MODE, data);
      return data;
    },
    // Elde bir kopya varsa ekran onunla açılır ve aynı anda tazesi istenir: kimse boş ekrana bakmaz.
    initialData: BOOT?.data,
    initialDataUpdatedAt: BOOT?.at,
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
