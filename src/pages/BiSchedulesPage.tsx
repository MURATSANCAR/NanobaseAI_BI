import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Pause, Pencil, Play, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import ResponsiveTable from '@/components/ResponsiveTable';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import type { BiSchedule } from '@/api/types';
import { t } from '@/i18n';
import StatusBadge from '@/components/StatusBadge';
import { sortByIsoDateDesc } from '@/utils/sort';

function scheduleStatusLabel(status: string | undefined): string {
  const s = (status || '').toLowerCase();
  if (s === 'pending') return t('bi.scheduleStatusActive');
  if (s === 'paused') return t('bi.scheduleStatusPaused');
  if (s === 'failed') return t('bi.scheduleStatusFailed');
  if (s === 'sent' || s === 'completed') return t('bi.scheduleStatusSent');
  return status || '—';
}

function scheduleStatusTone(status: string | undefined): string | undefined {
  const s = (status || '').toLowerCase();
  if (s === 'pending') return 'ok';
  return undefined;
}

export default function BiSchedulesPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const { openChat } = useBiChatDock();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editRecipient, setEditRecipient] = useState('');
  const [editSubject, setEditSubject] = useState('');

  const schedules = useQuery({
    queryKey: ['bi-schedules', config],
    queryFn: () => api.bi.schedules(config),
    enabled: isRunnerConfigured(config),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.bi.deleteSchedule(config, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-schedules'] }),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, ...body }: { id: string } & Partial<BiSchedule>) =>
      api.bi.updateSchedule(config, id, body),
    onSuccess: () => {
      setEditingId(null);
      qc.invalidateQueries({ queryKey: ['bi-schedules'] });
    },
  });

  const items = sortByIsoDateDesc(schedules.data?.schedules ?? [], (s) => s.created_at ?? s.run_at);

  const startEdit = (s: BiSchedule) => {
    setEditingId(s.id);
    setEditRecipient(s.recipient ?? '');
    setEditSubject(s.subject ?? '');
  };

  const saveEdit = (id: string) => {
    const recipient = editRecipient.trim();
    updateMut.mutate({
      id,
      subject: editSubject.trim() || undefined,
      recipient: recipient || undefined,
    });
  };

  const columns = [
    {
      id: 'subject',
      header: t('bi.scheduleSubject'),
      mobilePrimary: true,
      cell: (s: BiSchedule) =>
        editingId === s.id ? (
          <input
            className="input-field text-sm"
            value={editSubject}
            onChange={(e) => setEditSubject(e.target.value)}
            placeholder={t('bi.scheduleSubject')}
          />
        ) : (
          s.subject
        ),
    },
    {
      id: 'recurrence',
      header: t('bi.scheduleRecurrence'),
      mobileLabel: t('bi.scheduleRecurrence'),
      cell: (s: BiSchedule) =>
        s.recurrence === 'daily'
          ? t('bi.scheduleRecurrenceDaily')
          : s.recurrence === 'weekly'
            ? t('bi.scheduleRecurrenceWeekly')
            : t('bi.scheduleRecurrenceOnce'),
    },
    {
      id: 'run_at',
      header: t('bi.scheduleAt'),
      mobileLabel: t('bi.scheduleAt'),
      cell: (s: BiSchedule) => (
        <span className="font-mono text-xs">
          {s.run_at?.slice(0, 19)}
          {s.local_time ? ` (${s.local_time})` : ''}
        </span>
      ),
    },
    {
      id: 'status',
      header: t('bi.scheduleStatus'),
      mobileLabel: t('bi.scheduleStatus'),
      cell: (s: BiSchedule) => (
        <StatusBadge
          status={scheduleStatusTone(s.status) === 'ok' ? 'ok' : s.status}
          label={scheduleStatusLabel(s.status)}
        />
      ),
    },
    {
      id: 'recipient',
      header: t('bi.recipient'),
      mobileLabel: t('bi.recipient'),
      cell: (s: BiSchedule) =>
        editingId === s.id ? (
          <input
            className="input-field min-w-[12rem] text-sm"
            value={editRecipient}
            onChange={(e) => setEditRecipient(e.target.value)}
            placeholder={t('bi.scheduleRecipientHint')}
          />
        ) : (
          <span className={s.recipient?.trim() ? '' : 'text-amber-700'}>
            {s.recipient?.trim() || t('bi.scheduleRecipientMissing')}
          </span>
        ),
    },
    {
      id: 'alerts',
      header: t('bi.scheduleIncludeAlerts'),
      cell: (s: BiSchedule) => (
        <label className="inline-flex items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            checked={s.include_alerts !== false}
            disabled={updateMut.isPending || editingId === s.id}
            onChange={(e) => updateMut.mutate({ id: s.id, include_alerts: e.target.checked })}
          />
          {s.include_alerts !== false ? t('bi.scheduleAlertsOn') : t('bi.scheduleAlertsOff')}
        </label>
      ),
    },
    {
      id: 'narrative',
      header: t('bi.scheduleIncludeNarrative'),
      cell: (s: BiSchedule) => (
        <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-700">
          <input
            type="checkbox"
            className="h-4 w-4 accent-violet-600"
            checked={Boolean(s.include_narrative)}
            disabled={updateMut.isPending}
            onChange={(e) =>
              updateMut.mutate({
                id: s.id,
                include_narrative: e.target.checked,
              })
            }
          />
          <span>{s.include_narrative ? t('bi.scheduleAlertsOn') : t('bi.scheduleAlertsOff')}</span>
        </label>
      ),
    },
    {
      id: 'actions',
      header: t('common.actions'),
      mobileLabel: t('common.actions'),
      cell: (s: BiSchedule) => (
        <div className="flex flex-wrap gap-1">
          {editingId === s.id ? (
            <>
              <button
                type="button"
                className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-status-ok"
                title={t('common.save')}
                disabled={updateMut.isPending}
                onClick={() => saveEdit(s.id)}
              >
                <Check className="h-4 w-4" />
              </button>
              <button
                type="button"
                className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-slate-500"
                title={t('common.cancel')}
                onClick={() => setEditingId(null)}
              >
                <X className="h-4 w-4" />
              </button>
            </>
          ) : (
            <button
              type="button"
              className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-accent"
              title={t('bi.scheduleEdit')}
              onClick={() => startEdit(s)}
            >
              <Pencil className="h-4 w-4" />
            </button>
          )}
          {s.status === 'pending' && editingId !== s.id && (
            <button
              type="button"
              className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-accent"
              title={t('bi.schedulePause')}
              onClick={() => updateMut.mutate({ id: s.id, status: 'paused' })}
            >
              <Pause className="h-4 w-4" />
            </button>
          )}
          {s.status === 'paused' && editingId !== s.id && (
            <button
              type="button"
              className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-accent"
              title={t('bi.scheduleResume')}
              onClick={() => updateMut.mutate({ id: s.id, status: 'pending' })}
            >
              <Play className="h-4 w-4" />
            </button>
          )}
          {editingId !== s.id && (
            <button
              type="button"
              className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-status-fail"
              onClick={() => {
                if (window.confirm(t('bi.deleteScheduleConfirm'))) deleteMut.mutate(s.id);
              }}
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>
      ),
    },
  ];

  const scheduleAsk = t('empty.bi.schedules.askExample');

  return (
    <PageShell pageId="biSchedules" titleKey="bi.schedulesTitle" subtitleKey="bi.schedulesSubtitle" maxWidth="max-w-7xl">
      <p className="mb-4 text-sm text-slate-500">{t('bi.scheduleIncludeAlertsHint')}</p>
      <p className="mb-4 text-sm text-slate-500">{t('bi.scheduleIncludeNarrativeHint')}</p>

      {!items.length && !schedules.isLoading ? (
        <EmptyState
          emoji="📧"
          titleKey="empty.bi.schedules.title"
          descriptionKey="empty.bi.schedules.description"
          ctaLabelKey="empty.bi.schedules.cta"
          onCtaClick={() => openChat({ prompt: scheduleAsk })}
        />
      ) : (
        <div className="card overflow-hidden">
          <ResponsiveTable columns={columns} rows={items} rowKey={(s) => s.id} />
        </div>
      )}
    </PageShell>
  );
}
