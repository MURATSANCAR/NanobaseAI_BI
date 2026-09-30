import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, crmNamesApi, displayWordsApi } from '../engine';
import { setCrmNames, setDisplayWords, setLogoNames, useDisplayWordsVersion } from './readableName';

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
 * Başlık çeviricisinin (`readableName`) haritalarını yükler: katalogdaki Türkçe yazım haritası
 * (`/semantic/display-words`), CRM'in kendi Türkçe etiketleri (`/semantic/crm-names`) ve Logo'nun alan sözlüğünden
 * türetilen ad haritası (`logoNames.json`). Kabuk (Shell)
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
  // CRM'in kendi Türkçe etiketleri: şema değişmedikçe aynı; okunamazsa başlık kurala düşer.
  const crm = useQuery({ queryKey: ['crm-names'], queryFn: crmNamesApi.get, enabled: ENGINE_ENABLED, staleTime: 6 * 3600_000, retry: false });
  useEffect(() => setCrmNames(crm.data), [crm.data]);
  useEffect(() => {
    void loadLogoNames();
  }, []);
  return useDisplayWordsVersion();
}
