import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Note, errText } from '../admin/ui';
import { schoolsApi } from './api';
import { SchoolsFrame, Tabs, fmtDay, useSchoolsMeta } from './parts';
import SchoolsWeek from './SchoolsWeek';
import SchoolsList from './SchoolsList';
import DealerQueue from './DealerQueue';
import TermReport from './TermReport';
import ContextUpload from './ContextUpload';
import SqlInfo from '../components/SqlInfo';

/** M31 Okul tanıtım ve ziyaret. Telefonda ilk açılış «Bu hafta»; sekme ve süzgeçler adres çubuğunda (?sekme=, ?il=…). */

type Tab = 'hafta' | 'okullar' | 'bayi' | 'rapor' | 'veri';

export default function SchoolsScreen() {
  const [params, setParams] = useSearchParams();
  const meta = useSchoolsMeta();
  const me = meta.data?.me;
  const queue = useQuery({ queryKey: ['schools', 'queue'], queryFn: schoolsApi.queue, enabled: ENGINE_ENABLED && !!me?.canDealer });

  const update = useCallback(
    (next: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(next)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      setParams(p, { replace: true });
    },
    [params, setParams],
  );

  const tabs: Array<{ key: Tab; label: string; badge?: number | null }> = [
    { key: 'hafta', label: 'Bu hafta' },
    { key: 'okullar', label: 'Okullar' },
    { key: 'bayi', label: 'Bayi eşleştirme', badge: queue.data?.total ?? null },
    { key: 'rapor', label: 'Dönem raporu' },
    { key: 'veri', label: 'Takvim ve bölge verisi' },
  ];
  const tab: Tab = (tabs.find((t) => t.key === params.get('sekme'))?.key ?? 'hafta') as Tab;
  const st = meta.data?.status;
  const source = st?.schools ? `${st.schools.toLocaleString('tr-TR')} okul · CRM ziyaret yerleri` : 'CRM + Logo';
  const presence = st?.asOf ? `Okundu ${fmtDay(st.asOf)}${st.logoOk === false ? ' · Logo okunamadı' : ''}` : 'CRM + Logo';

  return (
    <SchoolsFrame
      title="Okul tanıtım ve ziyaret"
      lead="Hangi okula, ne zaman, hangi kitaplarla gideceğinizi planlarsınız. Okullar CRM'den gelir, öncelik puanı gerekçesiyle yazar, katalog okulun kademesine uygun ve stokta olan kitaplardan hazırlanır. Ziyaret raporları yalnız burada tutulur, CRM'e yazılmaz."
      source={source}
      presence={presence}
      info={
        st?.schools ? (
          <>
            {`${st.schools.toLocaleString('tr-TR')} okul · CRM ziyaret yerleri`}
            <SqlInfo k={meta.data?.kaynaklar} alan="status" label="Okul sayısı" />
          </>
        ) : undefined
      }
      aside={<Tabs tabs={tabs} value={tab} onChange={(t) => update({ sekme: t === 'hafta' ? null : t })} />}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; liste açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Okul tanıtım bilgileri okunamadı.')}</Note>}
      {st?.warnings?.map((w) => (
        <Note key={w} tone="warn">
          {w}
        </Note>
      ))}
      {tab === 'hafta' && <SchoolsWeek params={params} update={update} />}
      {tab === 'okullar' && <SchoolsList params={params} update={update} />}
      {tab === 'bayi' && <DealerQueue />}
      {tab === 'rapor' && <TermReport params={params} update={update} />}
      {tab === 'veri' && <ContextUpload />}
    </SchoolsFrame>
  );
}
