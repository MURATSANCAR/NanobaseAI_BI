import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, adminApi } from './engine';

/** Oturumdaki kişinin yönetici olup olmadığı. Yönetici = AD hesabı yönetici listesinde
 *  ya da yönetici AD grubunda (köprü karar verir). Yönetim, Veri Sözlüğü ve Onaylar
 *  menüleri yalnız yöneticilere gösterilir; sonuç ['admin','me'] anahtarıyla paylaşılır. */
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
