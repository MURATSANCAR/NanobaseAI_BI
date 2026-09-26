import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, adminApi } from './engine';

/** Oturumdaki kişinin rolü. Yönetici = AD hesabı yönetici listesinde ya da yönetici AD grubunda; editör =
 *  yönetim ekranındaki «Editör AD grubu» üyesi (köprü karar verir). Sonuç ['admin','me'] anahtarıyla
 *  paylaşılır; menü, Portal ayarları ve yönetici kapısı aynı cevabı okur. */
export function useAdminMe() {
  return useQuery({
    queryKey: ['admin', 'me'],
    queryFn: adminApi.me,
    enabled: ENGINE_ENABLED,
    retry: false,
    staleTime: 60_000,
  });
}

/** Menü filtreleme için sade bayrak: yükleniyorken de, hata varken de yönetici sayma. */
export function useIsAdmin(): boolean {
  return !!useAdminMe().data?.isAdmin;
}

/** Menünün rolü: yükleniyorken ya da hata varken ikisi de false (genel menü). */
export function useNavRole(): { isAdmin: boolean; isEditor: boolean } {
  const me = useAdminMe();
  return { isAdmin: !!me.data?.isAdmin, isEditor: !!me.data?.isEditor };
}
