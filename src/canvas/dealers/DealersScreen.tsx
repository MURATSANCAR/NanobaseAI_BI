import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText } from '../admin/ui';
import { Tabs } from '../budget/parts';
import { fmtDay } from '../field/api';
import { FieldFrame } from '../field/parts';
import { dealersApi } from './api';
import PanoTab from './PanoTab';
import ListTab from './ListTab';
import LimitsTab from './LimitsTab';
import ActionsTab from './ActionsTab';
import RulesTab from './RulesTab';

/** M59 Bayi riski. İlk sekme «Pano» (segment dağılımı, vadesi geçmiş, segmenti düşenler, onay bekleyen limit önerileri).
 *  Sekme ve süzgeçler adres çubuğunda; BMT yalnız CRM'de kendisine atanmış carileri görür, bütün bayiler açıkça verilen
 *  yetkiyle. Skor bir sınıflandırmadır, kredi kararı değildir; vade/gecikme yaklaşıktır. */

const TABS = [
  { key: 'pano', label: 'Pano' },
  { key: 'bayiler', label: 'Bayiler' },
  { key: 'limit', label: 'Limit önerileri' },
  { key: 'aksiyon', label: 'Aksiyonlar' },
  { key: 'kural', label: 'Kurallar' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function DealersScreen() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'pano') as Tab;
  const meta = useQuery({ queryKey: ['dealers', 'meta'], queryFn: dealersApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const m = meta.data;

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

  const err = errText(meta.error, 'Bayi riski ekranı açılamadı.');
  const run = m?.run;
  return (
    <FieldFrame
      crumb="Bayi riski"
      title="Bayi riski"
      lead="Her kitapçı ve bayi için günlük, açıklanabilir risk skoru (A/B/C/D), alacak yaşlandırması, çek olayı, iade ve CRM limit doluluğu. Skor kuraldan çıkar ve bileşenleriyle yazılır; kredi kararı satış müdürünündür. Onaylanan limit değişikliğini CRM'e insan işler."
      source={run?.gun ? `${run.scope ?? 0} cari · Logo ${fmtDay(run.dataEnd)} tarihine kadar · kural sürüm ${run.kural ?? '—'}` : 'Logo + CRM'}
      presence={run?.gun ? `Skor ${fmtDay(run.gun)}` : 'Hazırlanmadı'}
    >
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {meta.isLoading && <Loading />}
      {m && (
        <>
          {!run?.gun && <Note tone="warn">Bayi riski henüz hesaplanmadı: ilk günlük tur koştuğunda liste dolar (her gün 06:00).</Note>}
          {!m.me.canAll && run?.gun && m.me.cari === 0 && (
            <Note tone="info">CRM'de size atanmış bayi ya da kitapçı yok. Atama CRM'deki cari sahibi (BMT) ya da ilin müşteri temsilcisi alanından gelir.</Note>
          )}
          <Tabs tabs={TABS} value={tab} onChange={(t) => update({ sekme: t === 'pano' ? null : t })} />
          {tab === 'pano' && <PanoTab meta={m} goList={(p) => update({ sekme: 'bayiler', ...p })} />}
          {tab === 'bayiler' && <ListTab meta={m} params={params} update={update} />}
          {tab === 'limit' && <LimitsTab meta={m} />}
          {tab === 'aksiyon' && <ActionsTab meta={m} />}
          {tab === 'kural' && <RulesTab meta={m} />}
        </>
      )}
    </FieldFrame>
  );
}
