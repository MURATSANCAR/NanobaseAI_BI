import type { ReactNode } from 'react';
import Shell, { ZoomStage } from './stitch/Shell';
import { railFor } from './stitch/screens';
import NoAccess from './NoAccess';
import { useAdminMe } from './useAdmin';

/** Yalnız yöneticiye açık ekranların kapısı. Yetkisiz kişi içeriği hiç yüklemez
 *  (iç bileşen mount edilmez, sorguları çalışmaz); kabuk + tema uyumlu "yetki yok"
 *  kartı gösterilir. Adrese elle gidince de ekran boş kalmaz, açıklama çıkar. */
export default function AdminGuard({
  rail,
  crumb,
  children,
}: {
  rail: string;
  crumb: string;
  children: ReactNode;
}) {
  const me = useAdminMe();
  if (me.data?.isAdmin) return <>{children}</>;
  return (
    <Shell
      head={{ tenant: 'Timaş Yayınları', section: 'Yapay Zeka Raporları', crumb, source: '', presence: '' }}
      rail={railFor(rail)}
    >
      <main className="absolute bottom-2 left-14 right-2 top-16 overflow-y-auto sm:bottom-6 sm:left-[92px] sm:right-6 sm:top-[84px]">
      <ZoomStage className="h-full">
        <div className="mx-auto flex min-h-full w-full max-w-3xl items-center justify-center">
          {/* Yükleme kısa; yetki belirsizken kart yerine boş bırak, yanıp sönmesin. */}
          {me.isLoading ? null : <NoAccess user={me.data?.user} />}
        </div>
      </ZoomStage>
      </main>
    </Shell>
  );
}
