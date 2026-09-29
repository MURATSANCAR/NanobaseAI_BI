import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText, field, label as labelCls } from '../admin/ui';
import { Tabs } from '../budget/parts';
import { fieldApi, fmtCount, fmtDay } from './api';
import { FieldFrame } from './parts';
import TodayTab from './TodayScreen';
import CollectionsTab from './CollectionsTab';
import PlansTab from './PlansTab';
import ManagerReport from './ManagerReport';
import SqlInfo from '../components/SqlInfo';

/** M30 Saha satış ve tahsilat (BMT). Telefon önce: ilk sekme «Bugün». Sekme ve temsilci adres çubuğunda
 *  (?sekme=, ?temsilci=); temsilci seçimi yalnız bütün temsilcileri görme yetkisi olanda. */

const TABS = [
  { key: 'bugun', label: 'Bugün' },
  { key: 'tahsilat', label: 'Tahsilat' },
  { key: 'plan', label: 'Ödeme planları' },
  { key: 'rapor', label: 'Haftalık rapor' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export default function FieldScreen() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'bugun') as Tab;
  const meta = useQuery({ queryKey: ['field', 'meta'], queryFn: fieldApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const m = meta.data;
  const temsilci = m?.me.canAll ? (params.get('temsilci') ?? '') : '';

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

  const err = errText(meta.error, 'Saha ekranı açılamadı.');
  const run = m?.run;
  const aside = m?.me.canAll ? (
    <label className="flex flex-col gap-1">
      <span className={`${labelCls} flex items-center gap-0.5`}>
        Temsilci (müşteri sayısı)
        <SqlInfo k={m.kaynaklar} alan="reps" label="Temsilci başına cari" />
      </span>
      <select className={field} value={temsilci} onChange={(e) => update({ temsilci: e.target.value || null })}>
        <option value="">Bütün temsilciler</option>
        {m.reps.map((r) => (
          <option key={r.hesap} value={r.hesap}>
            {r.ad} ({fmtCount(r.cari)})
          </option>
        ))}
      </select>
    </label>
  ) : undefined;

  return (
    <FieldFrame
      crumb="Saha ve tahsilat"
      title="Saha ve tahsilat"
      lead="Bugün hangi müşteriye gideceğinizi, müşterinin borç ve sipariş özetini, vadesi geçmiş alacakları ve tahsilat onaylarını tek yerde görürsünüz. Müşterileriniz CRM'den, bakiye ve satış Logo'dan gelir; tahsilatı yine CRM'e girersiniz."
      source={run?.asof ? `${fmtCount(run.portfolio ?? 0)} cari · Logo ${fmtDay(run.dataEnd)} tarihine kadar` : 'CRM + Logo'}
      presence={run?.asof ? `Veri ${fmtDay(run.asof)}` : 'Hazırlanmadı'}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; liste açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {run?.asof && (
        <p className="flex flex-wrap items-center gap-1 px-1 text-[11.5px] font-semibold text-canvas-muted">
          {`${fmtCount(run.portfolio ?? 0)} cari · Logo ${fmtDay(run.dataEnd)} tarihine kadar`}
          <SqlInfo k={m?.kaynaklar} alan="run" label="Gece turu: cari sayısı ve veri sonu" />
        </p>
      )}
      {meta.isLoading && <Loading />}
      {m && (
        <>
          {!run?.asof && <Note tone="warn">Saha verisi henüz hazırlanmadı: ilk gece turu koştuğunda liste dolar (her gün 06:30).</Note>}
          {(run?.warnings ?? []).map((w) => (
            <Note key={w} tone="warn">
              {w}
            </Note>
          ))}
          {!m.me.canAll && run?.asof && m.me.cari === 0 && (
            <Note tone="info">CRM'de size atanmış müşteri yok. Müşteriler, CRM'deki cari sahibi ya da ilin müşteri temsilcisi alanından size bağlanır; eksikse CRM yöneticinizden atama isteyin.</Note>
          )}
          <Tabs tabs={TABS} value={tab} onChange={(t) => update({ sekme: t === 'bugun' ? null : t })} />
          {tab === 'bugun' && <TodayTab meta={m} temsilci={temsilci} />}
          {tab === 'tahsilat' && <CollectionsTab meta={m} temsilci={temsilci} />}
          {tab === 'plan' && <PlansTab meta={m} />}
          {tab === 'rapor' && <ManagerReport meta={m} temsilci={temsilci} />}
        </>
      )}
    </FieldFrame>
  );
}
