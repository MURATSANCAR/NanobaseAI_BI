import { useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, errText } from '../admin/ui';
import { commerceApi } from './api';
import { CommerceFrame, ROOT, useMeta } from './parts';
import CommerceHome from './CommerceHome';
import Customers from './Customers';
import Triggers from './Triggers';
import Campaigns from './Campaigns';
import Funnel from './Funnel';
import DataSettings from './DataSettings';

/** H3 E-ticaret müşterileri. Bölüm adres çubuğunda (/eticaret-musteri/musteriler, /tetikler, /kampanyalar, /huni, /veri). */
export default function CommerceScreen() {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  const meta = useMeta();
  const runs = useQuery({
    queryKey: ['commerce', 'runs', 'onay-bekliyor'],
    queryFn: () => commerceApi.runs('onay-bekliyor'),
    enabled: ENGINE_ENABLED && !!meta.data?.me.canApprove,
    staleTime: 60_000,
  });
  const fr = meta.data?.freshness;

  const section = here.startsWith(`${ROOT}/musteriler`) ? <Customers />
    : here.startsWith(`${ROOT}/tetikler`) ? <Triggers />
    : here.startsWith(`${ROOT}/kampanyalar`) ? <Campaigns />
    : here.startsWith(`${ROOT}/huni`) ? <Funnel />
    : here.startsWith(`${ROOT}/veri`) ? <DataSettings />
    : <CommerceHome />;

  return (
    <CommerceFrame
      presence={fr?.okAt ? 'Site siparişleri' : 'Henüz okunmadı'}
      badges={{ [`${ROOT}/tetikler`]: runs.data?.total || null, [`${ROOT}/veri`]: fr && (fr.error || fr.missing.length) ? 1 : null }}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'E-ticaret müşteri ekranı açılamadı.')}</Note>}
      {section}
    </CommerceFrame>
  );
}
