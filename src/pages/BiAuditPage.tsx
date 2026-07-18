import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import ResponsiveTable from '@/components/ResponsiveTable';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import type { BiAuditEntry } from '@/api/types';
import { t } from '@/i18n';
import { sortByIsoDateDesc } from '@/utils/sort';

export default function BiAuditPage() {
  const { config } = useApiConfig();
  const { openChat } = useBiChatDock();
  const [action, setAction] = useState('');
  const audit = useQuery({
    queryKey: ['bi-audit', config, action],
    queryFn: () => api.bi.audit(config, 200, action || undefined),
    enabled: isRunnerConfigured(config),
  });

  const entries = sortByIsoDateDesc((audit.data?.entries ?? []) as BiAuditEntry[], (r) => r.at);

  return (
    <PageShell pageId="biAudit" titleKey="bi.auditTitle" subtitleKey="bi.auditSubtitle">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label className="text-xs font-medium text-slate-600">{t('bi.auditActionFilter')}</label>
        <select
          className="input-field max-w-[12rem] text-sm"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        >
          <option value="">{t('bi.auditActionAll')}</option>
          <option value="query">{t('bi.auditAction.query')}</option>
          <option value="export">{t('bi.auditAction.export')}</option>
          <option value="chat">{t('bi.auditAction.chat')}</option>
          <option value="schema_refresh">{t('bi.auditAction.schema_refresh')}</option>
        </select>
      </div>
      {!entries.length && !audit.isLoading ? (
        <EmptyState emoji="📜" titleKey="empty.bi.audit.title" descriptionKey="empty.bi.audit.description" ctaLabelKey="empty.bi.audit.cta" onCtaClick={() => openChat()} />
      ) : (
        <ResponsiveTable<BiAuditEntry>
          columns={[
            { id: 'at', header: t('bi.createdAt'), mobilePrimary: true, cell: (r) => r.at?.slice(0, 19) ?? '—' },
            {
              id: 'dur',
              header: t('bi.auditDuration'),
              mobileLabel: t('bi.auditDuration'),
              cell: (r) => (r.duration_ms != null ? t('bi.auditDurationMs', { ms: r.duration_ms }) : '—'),
            },
            { id: 'rows', header: t('bi.auditRows'), mobileLabel: t('bi.auditRows'), cell: (r) => String(r.row_count ?? '—') },
            { id: 'ok', header: t('bi.auditOk'), mobileLabel: t('bi.auditOk'), cell: (r) => (r.ok ? '✓' : '✗') },
            { id: 'sql', header: t('bi.sqlColumn'), mobileLabel: t('bi.sqlColumn'), cell: (r) => <code className="break-all text-xs">{r.sql?.slice(0, 60) ?? '—'}</code> },
          ]}
          rows={entries}
          rowKey={(r) => `${r.at}-${r.action}-${r.sql ?? ''}`}
        />
      )}
    </PageShell>
  );
}
