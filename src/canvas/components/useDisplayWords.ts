import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, displayWordsApi } from '../engine';
import { setDisplayWords, useDisplayWordsVersion } from './readableName';

/**
 * Katalogdaki Türkçe yazım haritasını (`/semantic/display-words`) bir kez indirir ve başlık çeviricisine
 * (`readableName`) verir. Kabuk (Shell) çağırır; her ekran aynı önbelleği paylaşır. Harita gelene kadar başlıklar
 * yerleşik sözlükle yazılır. Dönen sayı harita her değiştiğinde artar; başlık çizen bileşen bununla yeniden çizilir.
 */
export function useDisplayWords(): number {
  const words = useQuery({
    queryKey: ['display-words'],
    queryFn: displayWordsApi.get,
    enabled: ENGINE_ENABLED,
    staleTime: 30 * 60_000,
    retry: false,
  });
  const data = words.data?.words;
  useEffect(() => setDisplayWords(data), [data]);
  return useDisplayWordsVersion();
}
