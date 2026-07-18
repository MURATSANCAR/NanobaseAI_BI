import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, LockKeyhole } from 'lucide-react';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

const LEVELS = ['public', 'internal', 'pii', 'restricted'] as const;

function levelLabel(level: string): string {
  const key = `bi.sensitivity.${level}`;
  const label = t(key);
  return label === key ? level : label;
}

export default function BiSensitivityPanel() {
  const { config } = useApiConfig();
  const runnerOk = isRunnerConfigured(config);
  const qc = useQueryClient();
  const [tableName, setTableName] = useState('');
  const [columnName, setColumnName] = useState('');
  const [sensitivity, setSensitivity] = useState<string>('internal');
  const [flash, setFlash] = useState(false);

  const listQ = useQuery({
    queryKey: ['bi-sensitivity', config],
    queryFn: () => api.bi.sensitivity.list(config),
    enabled: runnerOk,
  });

  const putMut = useMutation({
    mutationFn: () =>
      api.bi.sensitivity.put(config, {
        table_name: tableName.trim(),
        column_name: columnName.trim(),
        sensitivity,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-sensitivity'] });
      setFlash(true);
      window.setTimeout(() => setFlash(false), 3500);
      setColumnName('');
    },
  });

  if (!runnerOk) return null;

  const items = listQ.data?.items || [];

  return (
    <section className="card space-y-4 p-4" data-testid="bi-sensitivity-panel">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-amber-100 text-amber-800">
          <LockKeyhole className="h-4 w-4" />
        </span>
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{t('bi.settings.sensitivityTitle')}</h3>
          <p className="mt-0.5 text-xs text-slate-500">{t('bi.settings.sensitivityHint')}</p>
        </div>
      </div>

      {listQ.isError ? (
        <p className="text-xs text-rose-700">{localizeUserMessage(String(listQ.error))}</p>
      ) : null}
      {putMut.isError ? (
        <p className="text-xs text-rose-700">{localizeUserMessage(String(putMut.error))}</p>
      ) : null}
      {flash ? <p className="text-xs text-emerald-700">{t('bi.settings.sensitivitySaved')}</p> : null}

      {items.length === 0 ? (
        <p className="text-xs text-slate-500">{t('bi.settings.sensitivityEmpty')}</p>
      ) : (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-100">
          {items.map((row) => {
            const id = `${row.table_name}.${row.column_name}`;
            return (
              <li key={id} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs">
                <span className="font-mono text-slate-800">
                  {String(row.table_name)}.{String(row.column_name)}
                </span>
                <span className="rounded-md bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
                  {levelLabel(String(row.sensitivity || ''))}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      <div className="grid gap-2 sm:grid-cols-3">
        <label className="block space-y-1">
          <span className="text-[11px] font-medium text-slate-500">{t('bi.settings.sensitivityTable')}</span>
          <input
            className="input-field font-mono text-xs"
            value={tableName}
            onChange={(e) => setTableName(e.target.value)}
            placeholder="public.musteriler"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-[11px] font-medium text-slate-500">{t('bi.settings.sensitivityColumn')}</span>
          <input
            className="input-field font-mono text-xs"
            value={columnName}
            onChange={(e) => setColumnName(e.target.value)}
            placeholder="email"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-[11px] font-medium text-slate-500">{t('bi.settings.sensitivityLevel')}</span>
          <select
            className="input-field text-xs"
            value={sensitivity}
            onChange={(e) => setSensitivity(e.target.value)}
          >
            {LEVELS.map((lv) => (
              <option key={lv} value={lv}>
                {levelLabel(lv)}
              </option>
            ))}
          </select>
        </label>
      </div>

      <button
        type="button"
        className="btn-primary inline-flex items-center gap-1.5 text-sm"
        disabled={putMut.isPending || !tableName.trim() || !columnName.trim()}
        onClick={() => putMut.mutate()}
      >
        {putMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
        {t('bi.settings.sensitivityAdd')}
      </button>
    </section>
  );
}
