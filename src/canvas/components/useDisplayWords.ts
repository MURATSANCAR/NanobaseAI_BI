import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, displayWordsApi } from '../engine';
import { setDisplayWords, setLogoNames, useDisplayWordsVersion } from './readableName';

/** Logo alan sözlüğü haritası ayrı parçadır; oturum başına bir kez iner. */
let logoNamesLoad: Promise<void> | null = null;
const loadLogoNames = () =>
  (logoNamesLoad ??= import('./logoNames.json').then(
    (m) => setLogoNames(m.default),
    () => {
      // İnmezse yerleşik çekirdek sözlükle devam edilir; sonraki ekran girişinde yeniden denenir.
      logoNamesLoad = null;
    },
  ));

/**
 * Başlık çeviricisinin (`readableName`) iki haritasını yükler: katalogdaki Türkçe yazım haritası
 * (`/semantic/display-words`) ve Logo'nun alan sözlüğünden türetilen ad haritası (`logoNames.json`). Kabuk (Shell)
 * çağırır; her ekran aynı önbelleği paylaşır. Haritalar gelene kadar başlıklar yerleşik sözlükle yazılır. Dönen sayı
 * harita her değiştiğinde artar; başlık çizen bileşen bununla yeniden çizilir.
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
  useEffect(() => {
    void loadLogoNames();
  }, []);
  return useDisplayWordsVersion();
}
