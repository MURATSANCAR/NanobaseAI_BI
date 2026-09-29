import { Navigate, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { FUNNEL_PATH, UNIFIED_FUNNEL } from '../eticaret/funnelTabs';
import { Note, errText } from '../admin/ui';
import { commerceApi } from './api';
import { CommerceFrame, ROOT, useMeta } from './parts';
import SqlInfo from '../components/SqlInfo';
import CommerceHome from './CommerceHome';
import Customers from './Customers';
import Triggers from './Triggers';
import Campaigns from './Campaigns';
import Funnel from './Funnel';
import DataSettings from './DataSettings';

/** H3 E-ticaret müşterileri. Bölüm adres çubuğunda (/eticaret-musteri/musteriler, /tetikler, /kampanyalar, /veri);
 *  /huni artık E-ticaret › Huni ekranına yönlenir (o sayfa rolde yoksa sipariş hunisi burada açılır, erişim kaybolmaz). */
export default function CommerceScreen() {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  const pages = usePageAccess();
  const meta = useMeta();
  const runs = useQuery({
    queryKey: ['commerce', 'runs', 'onay-bekliyor'],
    queryFn: () => commerceApi.runs('onay-bekliyor'),
    enabled: ENGINE_ENABLED && !!meta.data?.me.canApprove,
    staleTime: 60_000,
  });
  const fr = meta.data?.freshness;
  const onFunnel = here.startsWith(`${ROOT}/huni`);
  if (onFunnel && pages === null) return null;
  if (onFunnel && canOpenRoute(pages, FUNNEL_PATH)) return <Navigate to={UNIFIED_FUNNEL} replace />;

  const section = here.startsWith(`${ROOT}/musteriler`) ? <Customers />
    : here.startsWith(`${ROOT}/tetikler`) ? <Triggers />
    : here.startsWith(`${ROOT}/kampanyalar`) ? <Campaigns />
    : onFunnel ? <Funnel />
    : here.startsWith(`${ROOT}/veri`) ? <DataSettings />
    : <CommerceHome />;

  return (
    <CommerceFrame
      presence={fr?.okAt ? 'Site siparişleri' : 'Henüz okunmadı'}
      badges={{ [`${ROOT}/tetikler`]: runs.data?.total || null, [`${ROOT}/veri`]: fr && (fr.error || fr.missing.length) ? 1 : null }}
      badgeInfo={runs.data?.total ? <SqlInfo k={runs.data.kaynaklar} alan="total" label="Onay bekleyen liste sayısı (Tetikler rozeti)" /> : undefined}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; sayılar açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'E-ticaret müşteri ekranı açılamadı.')}</Note>}
      {section}
    </CommerceFrame>
  );
}
