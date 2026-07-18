import { useEffect, useState } from 'react';
import { api, type ApiConfig } from '@/api/client';
import { t } from '@/i18n';

type Props = {
  config: ApiConfig;
  metricId: string;
  baseValue?: number;
  onResult?: (result: Record<string, unknown>) => void;
};

export default function BiScenarioSliders({ config, metricId, baseValue, onResult }: Props) {
  const [pct, setPct] = useState(0);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ base: number; simulated: number; delta_pct: number } | null>(
    null,
  );

  useEffect(() => {
    const handle = window.setTimeout(() => {
      void (async () => {
        setBusy(true);
        try {
          const out = await api.bi.scenario.simulate(config, {
            base_metric_id: metricId,
            base_value: baseValue,
            drivers: [{ target: 'measure', op: 'pct', value: pct / 100 }],
          });
          setResult(out);
          onResult?.(out as unknown as Record<string, unknown>);
        } catch {
          /* ignore while sliding */
        } finally {
          setBusy(false);
        }
      })();
    }, 300);
    return () => window.clearTimeout(handle);
  }, [config, metricId, baseValue, pct, onResult]);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
      <div className="font-medium text-slate-900">{t('bi.scenario.title')}</div>
      <label className="mt-2 flex items-center gap-3 text-xs text-slate-600">
        {t('bi.scenario.driver')}
        <input
          type="range"
          min={-50}
          max={50}
          value={pct}
          onChange={(e) => setPct(Number(e.target.value))}
          className="flex-1"
        />
        <span>{pct}%</span>
      </label>
      {result ? (
        <p className="mt-2 text-xs text-slate-700">
          {t('bi.scenario.base')}: {result.base} → {t('bi.scenario.simulated')}: {result.simulated} (
          {t('bi.scenario.delta')}: {result.delta_pct}%)
          {busy ? ' …' : ''}
        </p>
      ) : null}
    </div>
  );
}
