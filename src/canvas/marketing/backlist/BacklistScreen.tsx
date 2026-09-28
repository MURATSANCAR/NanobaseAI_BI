import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Note, errText } from '../../admin/ui';
import { Tabs } from '../../budget/parts';
import { fmtDay } from '../api';
import { MarketingFrame } from '../parts';
import { blApi } from './api';
import OpportunitiesTab from './OpportunitiesTab';
import AgendaTab from './AgendaTab';
import ActivationsTab from './ActivationsTab';
import EffectsTab from './EffectsTab';

/** M17 Backlist — Pazarlama › Planlama › Backlist. Sekme adres çubuğunda (?sekme=firsatlar|gundem|aktivasyonlar|etki). */

const TABS = [
  { key: 'firsatlar', label: 'Fırsatlar' },
  { key: 'gundem', label: 'Gündem' },
  { key: 'aktivasyonlar', label: 'Aktivasyonlar' },
  { key: 'etki', label: 'Etki' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function BacklistScreen() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'firsatlar') as Tab;
  const meta = useQuery({ queryKey: ['bl', 'meta'], queryFn: blApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const m = meta.data;
  const run = m?.run;
  const setTab = (k: Tab) => {
    const p = new URLSearchParams(params);
    p.set('sekme', k);
    setParams(p, { replace: true });
  };

  return (
    <MarketingFrame
      crumb="Backlist"
      title="Backlist pazarlama planları"
      lead="Yayımlanalı bir yılı geçen kitapların uyku endeksi: satış eğilimi, stok, marj, tahmin ve hedef sapması ayrı ayrı görünür, ağırlıklarını siz belirlersiniz. Özel gün ve yazarın yeni kitabıyla eşleşen kitaplar için aktivasyon planı açılır; kampanyaların öncesi/sonrası satışı Etki sekmesinde."
      source={run?.veriSonu ? `Logo verisi ${fmtDay(run.veriSonu)} tarihine kadar · son tam ay ${run.sonTamAyAdi ?? '—'}` : 'Logo + CRM'}
      presence={run?.kume ? `${run.kume.sayi.toLocaleString('tr-TR')} kitap` : '…'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Zeki AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Backlist bilgisi açılamadı.')}</Note>}
      {m && !run && <Note tone="info">Backlist listesi henüz kurulmadı. Her gece 04:00'te Logo ve CRM'den kurulur; ilk kurulum yöneticinin elle başlattığı koşuyla gelir.</Note>}
      {m?.lastRun?.hata && <Note tone="warn">Son gece koşusu tamamlanamadı: {m.lastRun.hata}. Liste bir önceki başarılı koşudan.</Note>}
      {run?.kume && (
        <p className="px-1 text-[11.5px] leading-snug text-canvas-muted">
          Küme: {run.kume.ad}. {run.kume.haric157 ? `${run.kume.haric157} ticari ürün (157) kitap olmadığı için dışarıda. ` : ''}
          {run.son12 && run.onceki12 ? `Son 12 ay ${run.son12[0]} – ${run.son12[1]}, önceki 12 ay ${run.onceki12[0]} – ${run.onceki12[1]} (tam aylar).` : ''}
          {(run.notlar ?? []).map((n) => ` ${n}`)}
        </p>
      )}
      <Tabs tabs={TABS} value={tab} onChange={setTab} />
      {m && tab === 'firsatlar' && <OpportunitiesTab meta={m} />}
      {m && tab === 'gundem' && <AgendaTab meta={m} />}
      {m && tab === 'aktivasyonlar' && <ActivationsTab meta={m} />}
      {m && tab === 'etki' && <EffectsTab meta={m} />}
    </MarketingFrame>
  );
}
