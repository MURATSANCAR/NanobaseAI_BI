import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, errText, nf } from '../../admin/ui';
import { Kpi, KpiRow, ModuleFrame } from '../kit';
import SqlInfo from '../../components/SqlInfo';
import { Tabs, flOverviewOptions, tl, type FlCtx } from './shared';
import PeoplePane from './PeoplePane';
import PackagesPane from './PackagesPane';
import CapacityPane from './CapacityPane';
import PayoutsPane from './PayoutsPane';
import MessagesPane from './MessagesPane';

/**
 * Serbest çalışanlar (M8): kayıt ve portfolyo, iş paketi ve toplu dağıtım, kapasite, hakediş, yazışma.
 * Bölüm ve açık kayıt adres çubuğunda durur (?bolum=, ?kisi=, ?paket=, ?hakedis=, ?yazisma=); bağlantı paylaşılabilir.
 */

type Section = 'kisiler' | 'paketler' | 'kapasite' | 'hakedis' | 'mesajlar';
const SECTIONS: Section[] = ['kisiler', 'paketler', 'kapasite', 'hakedis', 'mesajlar'];

export default function FreelanceScreen() {
  const [params, setParams] = useSearchParams();
  const section = (SECTIONS.includes(params.get('bolum') as Section) ? params.get('bolum') : 'kisiler') as Section;
  const ov = useQuery({ ...flOverviewOptions(), refetchInterval: 60_000 });
  const o = ov.data;

  const go = (s: Section, extra: Record<string, string> = {}) => setParams({ bolum: s, ...extra }, { replace: false });
  const ctx: FlCtx | null = o ? { ov: o, roles: o.roles, units: o.units, canManage: o.me.canManage, canApprove: o.me.canApprove } : null;
  const approvals = o?.payouts.onay?.count ?? 0;

  return (
    <ModuleFrame
      route="/serbest-calisanlar"
      crumb="Serbest çalışanlar"
      title="Serbest çalışanlar"
      lead="Çizer, kapak tasarımcı, mizanpajcı, redaktör ve çevirmen havuzu: kayıt ve portfolyo, iş paketlerinin dağıtımı, haftalık kapasite, teslim ve hakediş, yazışma. Tutarlar anlaşılan brüt ücrettir (KDV hariç); ödeme Logo'da yapılır."
      source={o ? `${nf.format(o.people.active)} aktif kişi` : 'Serbest çalışan kayıtları'}
      presence="Kaynak: ZEKİ AI kayıtları"
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {ov.error && <Note tone="err">{errText(ov.error, 'Özet okunamadı.')}</Note>}

      {o && (
        <KpiRow>
          <Kpi
            label="Atanmayı bekleyen"
            value={nf.format(o.tasks.unassigned)}
            help={o.tasks.unassigned ? 'Açık paketlerde kişisi olmayan görev' : 'Bütün görevlerin kişisi var'}
            info={<SqlInfo k={o.kaynaklar} alan="tasks.unassigned" label="Atanmayı bekleyen" />}
            active={section === 'paketler'}
            onClick={() => go('paketler')}
          />
          <Kpi
            label="Süren iş"
            value={nf.format(o.tasks.active)}
            help={o.tasks.late ? `${nf.format(o.tasks.late)} görevin termini geçti` : 'Termini geçen yok'}
            info={<SqlInfo k={o.kaynaklar} alan="tasks.active" label="Süren iş" />}
            active={section === 'kapasite'}
            onClick={() => go('kapasite')}
          />
          <Kpi
            label="Teslim incelemesi"
            value={nf.format(o.tasks.review)}
            help="Kabul ya da revizyon bekleyen teslim"
            info={<SqlInfo k={o.kaynaklar} alan="tasks.review" label="Teslim incelemesi" />}
            onClick={() => go('paketler', { durum: 'inceleme' })}
          />
          <Kpi
            label="Ödenecek"
            value={tl(o.payable)}
            help={approvals ? `${nf.format(approvals)} hakediş onay bekliyor` : 'Kabul edilmiş, hakedişe girmemiş iş'}
            info={<SqlInfo k={o.kaynaklar} alan="payable" label="Ödenecek" />}
            active={section === 'hakedis'}
            onClick={() => go('hakedis')}
          />
        </KpiRow>
      )}

      <Tabs<Section>
        value={section}
        onChange={(s) => go(s)}
        items={[
          { key: 'kisiler', label: 'Kişiler' },
          { key: 'paketler', label: 'İş paketleri', badge: o?.tasks.review || undefined, info: <SqlInfo k={o?.kaynaklar} alan="tasks.review" label="İnceleme bekleyen teslim" /> },
          { key: 'kapasite', label: 'Kapasite' },
          {
            key: 'hakedis',
            label: 'Hakediş',
            badge: (ctx?.canApprove && approvals) || undefined,
            info: <SqlInfo k={o?.kaynaklar} alan="payouts" label="Onay bekleyen hakediş" />,
          },
          { key: 'mesajlar', label: 'Yazışmalar', badge: o?.unread || undefined, info: <SqlInfo k={o?.kaynaklar} alan="unread" label="Okunmamış ileti" /> },
        ]}
      />

      {!ctx ? (
        !ov.error && <Loading />
      ) : section === 'kisiler' ? (
        <PeoplePane ctx={ctx} />
      ) : section === 'paketler' ? (
        <PackagesPane ctx={ctx} />
      ) : section === 'kapasite' ? (
        <CapacityPane ctx={ctx} />
      ) : section === 'hakedis' ? (
        <PayoutsPane ctx={ctx} />
      ) : (
        <MessagesPane ctx={ctx} />
      )}
    </ModuleFrame>
  );
}
