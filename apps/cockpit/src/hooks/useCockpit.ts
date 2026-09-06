import { useQuery } from '@tanstack/react-query';
import { loadCockpit, type DataMode } from '../lib/metrics';
import { engineStatus } from '../lib/engine';

// Üretim varsayılanı 'live': önbellek (fixture) rakamı hiçbir zaman sessizce gösterilmez; motor cevap
// vermezse ekranda "Veri alınamadı" + hata görünür. Geliştirme için VITE_DATA_MODE=fixture|auto.
const MODE = ((import.meta.env.VITE_DATA_MODE as string | undefined) ?? 'live') as DataMode;

export function useCockpit() {
  return useQuery({ queryKey: ['cockpit', MODE], queryFn: () => loadCockpit(MODE) });
}

export function useEngine() {
  return useQuery({ queryKey: ['engine'], queryFn: engineStatus, retry: 0, staleTime: 60_000 });
}
