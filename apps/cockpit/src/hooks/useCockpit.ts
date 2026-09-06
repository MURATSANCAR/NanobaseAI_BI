import { useQuery } from '@tanstack/react-query';
import { loadCockpit, type DataMode } from '../lib/metrics';
import { engineStatus } from '../lib/wren';

const MODE = ((import.meta.env.VITE_DATA_MODE as string | undefined) ?? 'auto') as DataMode;

export function useCockpit() {
  return useQuery({ queryKey: ['cockpit', MODE], queryFn: () => loadCockpit(MODE) });
}

export function useEngine() {
  return useQuery({ queryKey: ['engine'], queryFn: engineStatus, retry: 0, staleTime: 60_000 });
}
