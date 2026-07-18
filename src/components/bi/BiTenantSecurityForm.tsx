import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Shield } from 'lucide-react';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';
import { localizeUserMessage } from '@/utils/backendLabels';

type SecurityForm = {
  rls_predicate_template: string;
  embed_origin_allowlist: string;
  metric_policy: string;
  certify_requires_admin: boolean;
};

const DEFAULTS: SecurityForm = {
  rls_predicate_template: '',
  embed_origin_allowlist: '',
  metric_policy: 'approved_or_certified',
  certify_requires_admin: false,
};

export default function BiTenantSecurityForm() {
  const { config } = useApiConfig();
  const runnerOk = isRunnerConfigured(config);
  const qc = useQueryClient();
  const [form, setForm] = useState<SecurityForm>(DEFAULTS);
  const [flash, setFlash] = useState(false);

  const q = useQuery({
    queryKey: ['bi-tenant-security', config],
    queryFn: () => api.bi.tenantSecurity.get(config),
    enabled: runnerOk,
  });

  useEffect(() => {
    if (!q.data) return;
    const allow = q.data.embed_origin_allowlist;
    setForm({
      rls_predicate_template: String(q.data.rls_predicate_template || ''),
      embed_origin_allowlist: Array.isArray(allow) ? allow.map(String).join('\n') : String(allow || ''),
      metric_policy: String(q.data.metric_policy || 'approved_or_certified'),
      certify_requires_admin: Boolean(q.data.certify_requires_admin),
    });
  }, [q.data]);

  const saveMut = useMutation({
    mutationFn: () =>
      api.bi.tenantSecurity.put(config, {
        rls_predicate_template: form.rls_predicate_template,
        embed_origin_allowlist: form.embed_origin_allowlist
          .split(/\n|,/)
          .map((s) => s.trim())
          .filter(Boolean),
        metric_policy: form.metric_policy,
        certify_requires_admin: form.certify_requires_admin,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-tenant-security'] });
      setFlash(true);
      window.setTimeout(() => setFlash(false), 3500);
    },
  });

  if (!runnerOk) return null;

  return (
    <section className="card space-y-4 p-4" data-testid="bi-tenant-security-form">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-xl bg-violet-100 text-violet-700">
          <Shield className="h-4 w-4" />
        </span>
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{t('bi.settings.securityTitle')}</h3>
          <p className="mt-0.5 text-xs text-slate-500">{t('bi.settings.securityHint')}</p>
        </div>
      </div>

      {q.isError ? (
        <p className="text-xs text-rose-700">{localizeUserMessage(String(q.error))}</p>
      ) : null}
      {saveMut.isError ? (
        <p className="text-xs text-rose-700">{localizeUserMessage(String(saveMut.error))}</p>
      ) : null}
      {flash ? <p className="text-xs text-emerald-700">{t('bi.settings.securitySaved')}</p> : null}

      <label className="block space-y-1">
        <span className="text-xs font-medium text-slate-600">{t('bi.settings.rlsTemplate')}</span>
        <textarea
          className="input-field min-h-[72px] font-mono text-xs"
          value={form.rls_predicate_template}
          onChange={(e) => setForm((f) => ({ ...f, rls_predicate_template: e.target.value }))}
        />
      </label>

      <label className="block space-y-1">
        <span className="text-xs font-medium text-slate-600">{t('bi.settings.embedAllowlist')}</span>
        <textarea
          className="input-field min-h-[72px] font-mono text-xs"
          value={form.embed_origin_allowlist}
          onChange={(e) => setForm((f) => ({ ...f, embed_origin_allowlist: e.target.value }))}
          placeholder="https://portal.nanobase.ai"
        />
        <span className="text-[11px] text-slate-500">{t('bi.settings.embedAllowlistHint')}</span>
      </label>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block space-y-1">
          <span className="text-xs font-medium text-slate-600">{t('bi.settings.metricPolicy')}</span>
          <select
            className="input-field"
            value={form.metric_policy}
            onChange={(e) => setForm((f) => ({ ...f, metric_policy: e.target.value }))}
          >
            <option value="approved_or_certified">approved_or_certified</option>
            <option value="certified_only">certified_only</option>
            <option value="any">any</option>
          </select>
        </label>
        <label className="flex items-center gap-2 pt-6 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={form.certify_requires_admin}
            onChange={(e) => setForm((f) => ({ ...f, certify_requires_admin: e.target.checked }))}
          />
          {t('bi.settings.certifyRequiresAdmin')}
        </label>
      </div>

      <button
        type="button"
        className="btn-primary inline-flex items-center gap-1.5 text-sm"
        disabled={saveMut.isPending || q.isLoading}
        onClick={() => saveMut.mutate()}
      >
        {saveMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
        {t('bi.settings.saveSecurity')}
      </button>
    </section>
  );
}
