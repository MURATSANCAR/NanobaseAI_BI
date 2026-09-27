import { Outlet, useLocation } from 'react-router-dom';
import Shell, { ZoomStage } from './stitch/Shell';
import NoAccess from './NoAccess';
import { NAV, matchActive, needsPagePermission } from './nav/navModel';
import { canSeePage, useAccessMe, usePageAccess } from './useAdmin';

/**
 * Rota kapısı: adresin menüdeki karşılığı (detay sayfaları `also` ile bağlı öğeye düşer) kişinin rolünde
 * yoksa ekran hiç yüklenmez, «yetkiniz yok» kartı çıkar. Asıl kapı köprüdedir; bu, adrese elle gidilince
 * ekranın 403'lerle yarım açılmasını önler. Kampüs ve menüde karşılığı olmayan adresler serbest; Yönetim
 * ekranları kendi yönetici kapısını taşır.
 */
export default function PageGate() {
  const loc = useLocation();
  const pages = usePageAccess();
  const me = useAccessMe();
  const hit = matchActive(NAV, loc.pathname, loc.search);
  if (!hit || !needsPagePermission(hit.group, hit.item)) return <Outlet />;
  // Yetki gelene kadar boş: ekran açılıp sonra kapanmasın, 403'lü istekler de gitmesin.
  if (pages === null) return null;
  if (canSeePage(pages, hit.item.id)) return <Outlet />;
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: hit.group.label, crumb: hit.item.label, source: '', presence: '' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage className="h-full">
          <div className="mx-auto flex min-h-full w-full max-w-3xl items-center justify-center">
            <NoAccess
              title="Bu sayfa rolünüzde yok"
              hint={`${me.data?.user ? me.data.user : 'Hesabınız'} «${hit.item.label}» sayfasını açma yetkisine sahip değil. Sayfalar, Active Directory grubunuza, biriminize ya da CRM rolünüze bağlı rollerle açılır; bir yönetici Portal ayarları → Yetkiler'den ekleyebilir.`}
            />
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}
