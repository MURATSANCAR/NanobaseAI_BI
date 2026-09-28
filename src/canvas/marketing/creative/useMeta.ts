import { useQuery, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { creativeApi } from './api';

/** Kanal/biçim/metin türü listeleri, platform sınırları ve kişinin yetkileri (köprüden; ekranda sabit liste yok). */
export function useCreativeMeta() {
  return useQuery({ queryKey: ['creative', 'meta'], queryFn: creativeApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export const invalidateCreative = (qc: QueryClient) => qc.invalidateQueries({ queryKey: ['creative'] });
