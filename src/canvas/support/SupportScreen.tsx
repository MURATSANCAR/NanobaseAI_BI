import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';
import { Loading, Note, btnGhost, errText } from '../admin/ui';
import { Tabs } from '../budget/parts';
import { ENGINE_ENABLED } from '../engine';
import ClassesTab from './ClassesTab';
import CustomerContext from './CustomerContext';
import DealerView from './DealerView';
import FaqGaps from './FaqGaps';
import QualityTab from './QualityTab';
import QueueTab from './QueueTab';
import { SupportFrame } from './parts';
import { fmtDay, supportApi } from './api';
import { destekUrl } from '../kampus/DestekCard';

/** M51 Müşteri hizmetleri. Sekme adres çubuğunda (?sekme=). Müşteri bağlamı ve bayi görünümü «Müşteri bağlamı ve bayi
 *  görünümü» yetkisiyle görünür; sınıf ayarı «Konu sınıfları ve SLA» yetkisiyle düzenlenir. */

type Tab = 'ozet' | 'kuyruk' | 'konular' | 'baglam' | 'bayi' | 'sss' | 'siniflar';

export default function SupportScreen() {
  const [params, setParams] = useSearchParams();
  const meta = useQuery({ queryKey: ['support', 'meta'], queryFn: supportApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const m = meta.data;
  const tabs: Array<{ key: Tab; label: string }> = [
    { key: 'ozet', label: 'Özet' },
    { key: 'kuyruk', label: 'Kuyruk' },
    { key: 'konular', label: 'Konular' },
    ...(m?.me.canContext ? [{ key: 'baglam' as Tab, label: 'Müşteri bağlamı' }, { key: 'bayi' as Tab, label: 'Bayi görünümü' }] : []),
    { key: 'sss', label: 'Bilgi bankası açıkları' },
    { key: 'siniflar', label: 'Konu sınıfları' },
  ];
  const tab: Tab = (tabs.find((t) => t.key === params.get('sekme'))?.key ?? 'ozet') as Tab;
  const go = useCallback(
    (t: Tab) => {
      const p = new URLSearchParams(params);
      if (t === 'ozet') p.delete('sekme');
      else p.set('sekme', t);
      setParams(p, { replace: true });
    },
    [params, setParams],
  );
  const run = m?.runs.classify as { _at?: string; classified?: number; stop?: string | null } | undefined;

  return (
    <SupportFrame
      source="Destek masası · CRM · Logo"
      presence={run?._at ? `Son sınıflama ${fmtDay(run._at)}` : 'Henüz sınıflama turu yok'}
      aside={
        // Ayar boşsa masa portalla aynı sunucu adında 8446'dadır (Kampüs kartıyla aynı kural).
        m ? (
          <div className="flex flex-col items-stretch gap-1 lg:items-end">
            <a href={m.destek.link ? `${m.destek.link}/helpdesk` : destekUrl()} target="_blank" rel="noreferrer" className={btnGhost}>
              Talep masasını aç <ExternalLink aria-hidden className="h-4 w-4" />
            </a>
            <span className="text-[11px] text-canvas-muted lg:text-right">Talepler masada açılır, cevaplanır ve kapanır.</span>
          </div>
        ) : undefined
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Ekran bilgisi okunamadı.')}</Note>}
      {m && !m.destek.configured && (
        <Note tone="warn">Destek masası bağlantısı ayarlanmamış; kuyruk ve kalite boş kalır. Yönetim → Ayarlar → Müşteri hizmetleri.</Note>
      )}
      {m?.me.canContext && (!m.me.dataCari || !m.me.dataSatis) && (
        <Note tone="info">
          Rolünüzde {[!m.me.dataCari && '«Cari ve tahsilat»', !m.me.dataSatis && '«Satış ve sipariş»'].filter(Boolean).join(' ve ')} veri alanı yok;
          müşteri bağlamının bu bölümleri görünmez.
        </Note>
      )}
      <Tabs tabs={tabs} value={tab} onChange={go} />
      {meta.isLoading && <Loading />}
      {m && tab === 'ozet' && <QualityTab meta={m} view="ozet" />}
      {m && tab === 'konular' && <QualityTab meta={m} view="konular" />}
      {m && tab === 'kuyruk' && <QueueTab meta={m} />}
      {m && tab === 'baglam' && <CustomerContext />}
      {m && tab === 'bayi' && <DealerView />}
      {m && tab === 'sss' && <FaqGaps />}
      {m && tab === 'siniflar' && <ClassesTab meta={m} />}
    </SupportFrame>
  );
}
