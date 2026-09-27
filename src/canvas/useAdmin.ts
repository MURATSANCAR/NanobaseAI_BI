import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED, accessApi, adminApi } from './engine';
import { permissionItemFor } from './nav/navModel';

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

/* ------------------------------------------------------------------ sayfa yetkisi */

/** Kişinin görebildiği sayfalar: 'all' (yönetici ya da «bütün sayfalar» rolü) ya da `sayfa:<menü id>` kümesi.
 *  Karar köprüde verilir (sayfa kapısı); menü, rota kapısı ve Kampüs kartları bu cevabı yansıtır. */
export type PageAccess = 'all' | ReadonlySet<string>;

export function useAccessMe() {
  return useQuery({
    queryKey: ['access', 'me'],
    queryFn: accessApi.me,
    enabled: ENGINE_ENABLED,
    retry: false,
    staleTime: 60_000,
  });
}

/** Yetki henüz bilinmiyorsa null. Köprü bu ucu tanımıyorsa (eski sürüm) ya da okunamıyorsa 'all': menüyü
 *  boşaltmak yerine eski davranış sürer — kapı zaten köprüde. */
export function usePageAccess(): PageAccess | null {
  const q = useAccessMe();
  const data = q.data;
  const failed = !!q.error;
  const loading = q.isLoading;
  // Aynı cevap için aynı küme: menü ve rota kapısı her çizimde yeniden hesaplamasın.
  return useMemo<PageAccess | null>(() => {
    if (!ENGINE_ENABLED) return 'all';
    if (loading) return null;
    if (failed || !data) return 'all';
    return data.all ? 'all' : new Set(data.perms);
  }, [data, failed, loading]);
}

export const pageKey = (itemId: string) => `sayfa:${itemId}`;

export const canSeePage = (access: PageAccess | null, itemId: string): boolean =>
  access === 'all' || (access !== null && access.has(pageKey(itemId)));

/** Bağlantının gittiği sayfa kişinin rolünde mi (Kampüs kartları, «Tüm modüller»). Yetki bilinmiyorken gizli. */
export function canOpenRoute(access: PageAccess | null, to: string): boolean {
  const item = permissionItemFor(to);
  return !item || canSeePage(access, item.id);
}
