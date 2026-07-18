import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Loader2, Plus, RefreshCw, Sparkles } from 'lucide-react';
import { useMemo, useState } from 'react';
import { PageShell } from '@/components/PageShell';
import BiQueryTemplateGrid from '@/components/bi/BiQueryTemplateGrid';
import BiSourceSwitcher from '@/components/bi/BiSourceSwitcher';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import type { BiQueryTemplate } from '@/api/types';
import { biTemplatePrompt } from '@/lib/biTemplatePrompt';
import { localizeUserMessage } from '@/utils/backendLabels';
import { getLocale, t } from '@/i18n';

type Persona = 'ceo' | 'cfo' | 'sales_ops';

export default function BiTemplatesPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { openChat } = useBiChatDock();
  const locale = getLocale();
  const [flash, setFlash] = useState<string | null>(null);
  const [seedingDept, setSeedingDept] = useState<Persona | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [seedingId, setSeedingId] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createTitle, setCreateTitle] = useState('');
  const [createPrompt, setCreatePrompt] = useState('');
  const [createSql, setCreateSql] = useState('');

  const templates = useQuery({
    queryKey: ['bi-templates', config],
    queryFn: () => api.bi.templates(config),
    enabled: isRunnerConfigured(config),
  });

  const analyticsBoards = useQuery({
    queryKey: ['bi-analytics-dashboards'],
    queryFn: () => api.bi.analytics.dashboards(config),
    enabled: isRunnerConfigured(config),
    staleTime: 60_000,
  });

  const activeDashboardId = useMemo(() => {
    const list = analyticsBoards.data?.dashboards ?? [];
    return list[0]?.id ?? null;
  }, [analyticsBoards.data?.dashboards]);

  const refreshMut = useMutation({
    mutationFn: () => api.bi.refreshTemplates(config),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-templates'] });
      setFlash(t('bi.templatesRefreshSuccess'));
      window.setTimeout(() => setFlash(null), 3000);
    },
    onError: (err) => window.alert(localizeUserMessage((err as Error).message) || (err as Error).message),
  });

  const createMut = useMutation({
    mutationFn: () =>
      api.bi.createTemplate(config, {
        title: createTitle.trim(),
        prompt: createPrompt.trim(),
        locale,
        sql_hint: createSql.trim() || undefined,
        category: createSql.trim() ? 'widget' : 'query',
      }),
    onSuccess: () => {
      setShowCreate(false);
      setCreateTitle('');
      setCreatePrompt('');
      setCreateSql('');
      void qc.invalidateQueries({ queryKey: ['bi-templates'] });
      setFlash(t('bi.templatesCreateSuccess'));
      window.setTimeout(() => setFlash(null), 3000);
    },
    onError: (err) => window.alert(localizeUserMessage((err as Error).message) || (err as Error).message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => api.bi.deleteTemplate(config, id),
    onSuccess: (_data, id) => {
      void qc.invalidateQueries({ queryKey: ['bi-templates'] });
      setSelectedIds((prev) => prev.filter((x) => x !== id));
    },
    onError: (err) => window.alert(localizeUserMessage((err as Error).message) || (err as Error).message),
  });

  const seedMut = useMutation({
    mutationFn: (ids: string[]) =>
      api.bi.seedTemplates(config, {
        template_ids: ids,
        dashboard_id: activeDashboardId ?? undefined,
        locale,
      }),
    onMutate: (ids) => {
      if (ids.length === 1) setSeedingId(ids[0]);
    },
    onSettled: () => setSeedingId(null),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ['bi-analytics-dashboards'] });
      setSelectedIds([]);
      setFlash(t('bi.templatesSeedSuccess'));
      window.setTimeout(() => setFlash(null), 4000);
      navigate(`/bi?dashboard=${encodeURIComponent(String(data.dashboard_id))}`);
    },
    onError: (err) => window.alert(localizeUserMessage((err as Error).message) || (err as Error).message),
  });

  const seedDeptMut = useMutation({
    mutationFn: (dept: Persona) => api.bi.departmentBoards.create(config, dept, locale),
    onMutate: (dept) => setSeedingDept(dept),
    onSettled: () => setSeedingDept(null),
    onSuccess: (data) => {
      void qc.invalidateQueries({ queryKey: ['bi-analytics-dashboards'] });
      setFlash(data.fallback ? t('bi.dept.seedFallbackSuccess') : t('bi.dept.seedSuccess'));
      window.setTimeout(() => setFlash(null), 4000);
      navigate(`/bi?dashboard=${encodeURIComponent(String(data.dashboard_id))}`);
    },
    onError: (err) => window.alert(localizeUserMessage((err as Error).message) || (err as Error).message),
  });

  const askInChat = (prompt: string) => {
    openChat({ prompt });
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const items = templates.data?.templates ?? [];
  const sourceLabel = String(templates.data?.meta?.source_label || '');
  const seedableSelected = selectedIds.filter((id) => items.find((t) => t.id === id)?.sql_hint);

  return (
    <PageShell pageId="biTemplates" titleKey="bi.templatesTitle" subtitleKey="bi.templatesSubtitle" maxWidth="max-w-7xl">
      {flash && <p className="text-sm text-status-ok">{flash}</p>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <BiSourceSwitcher config={config} />
        <Link to="/bi/sources" className="text-xs font-medium text-violet-700 hover:underline">
          {t('bi.sources.title')}
        </Link>
      </div>

      {sourceLabel ? (
        <p className="text-sm text-slate-600">{t('bi.templatesForSource', { name: sourceLabel })}</p>
      ) : null}

      <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <button
          type="button"
          className="btn-secondary inline-flex min-h-11 w-full items-center justify-center gap-2 text-sm sm:w-auto"
          onClick={() => openChat()}
        >
          <Sparkles className="h-4 w-4" />
          {t('bi.queriesGoToChat')}
        </button>
        <button
          type="button"
          className="btn-secondary inline-flex min-h-11 w-full items-center justify-center gap-2 text-sm sm:w-auto"
          disabled={refreshMut.isPending || !isRunnerConfigured(config)}
          onClick={() => refreshMut.mutate()}
        >
          <RefreshCw className={`h-4 w-4 ${refreshMut.isPending ? 'animate-spin' : ''}`} />
          {t('bi.templatesRefresh')}
        </button>
        <button
          type="button"
          className="btn-primary inline-flex min-h-11 w-full items-center justify-center gap-2 text-sm sm:w-auto"
          onClick={() => setShowCreate((v) => !v)}
        >
          <Plus className="h-4 w-4" />
          {t('bi.templatesCreate')}
        </button>
        <span className="text-sm text-slate-500">
          {items.length} {t('bi.templatesCount')}
        </span>
      </div>

      {showCreate && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-sm font-semibold text-slate-800">{t('bi.templatesCreateTitle')}</p>
          <p className="mt-1 text-xs text-slate-500">{t('bi.templatesCreateHint')}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.templatesCreateName')}</label>
              <input
                className="input-field"
                value={createTitle}
                onChange={(e) => setCreateTitle(e.target.value)}
                placeholder={t('bi.templatesCreateNamePlaceholder')}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.templatesCreateSqlOptional')}</label>
              <input
                className="input-field font-mono text-xs"
                value={createSql}
                onChange={(e) => setCreateSql(e.target.value)}
                placeholder="SELECT …"
              />
            </div>
            <div className="sm:col-span-2">
              <label className="mb-1 block text-xs font-medium text-slate-600">{t('bi.templatesCreatePrompt')}</label>
              <textarea
                className="input-field min-h-[4.5rem]"
                value={createPrompt}
                onChange={(e) => setCreatePrompt(e.target.value)}
                placeholder={t('bi.templatesCreatePromptPlaceholder')}
              />
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={createMut.isPending || !createTitle.trim() || !createPrompt.trim()}
              onClick={() => createMut.mutate()}
            >
              {createMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t('common.save')}
            </button>
            <button type="button" className="btn-secondary text-sm" onClick={() => setShowCreate(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-sky-200/80 bg-gradient-to-br from-sky-50/90 to-white p-4 shadow-sm">
        <p className="text-xs font-semibold uppercase tracking-wide text-sky-800">{t('bi.dept.title')}</p>
        <p className="mt-1 text-sm text-slate-600">{t('bi.dept.hint')}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {(['ceo', 'cfo', 'sales_ops'] as const).map((dept) => {
            const busy = seedingDept === dept && seedDeptMut.isPending;
            return (
              <button
                key={dept}
                type="button"
                className="btn-primary inline-flex min-h-11 items-center gap-2 text-sm disabled:opacity-60"
                disabled={!isRunnerConfigured(config) || seedDeptMut.isPending}
                onClick={() => seedDeptMut.mutate(dept)}
              >
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LayoutDashboard className="h-4 w-4" />}
                {t(`bi.dept.${dept}`)}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-slate-500">{t('bi.dept.createNote')}</p>
      </div>

      {selectedIds.length > 0 && (
        <div className="sticky top-2 z-20 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-violet-200 bg-violet-50/95 px-4 py-3 shadow-sm backdrop-blur">
          <p className="text-sm font-medium text-violet-900">
            {t('bi.templatesSelectedCount', { count: String(selectedIds.length) })}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary text-sm"
              disabled={seedMut.isPending || seedableSelected.length === 0}
              onClick={() => seedMut.mutate(seedableSelected.length ? seedableSelected : selectedIds)}
            >
              {seedMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <LayoutDashboard className="h-4 w-4" />}
              {t('bi.templatesSeedSelected')}
            </button>
            <button type="button" className="btn-secondary text-sm" onClick={() => setSelectedIds([])}>
              {t('bi.templatesClearSelection')}
            </button>
          </div>
        </div>
      )}

      <BiQueryTemplateGrid
        templates={items}
        loading={templates.isLoading || refreshMut.isPending}
        selectedIds={selectedIds}
        onToggleSelect={toggleSelect}
        onSelect={(prompt) => askInChat(prompt)}
        onSeed={(tpl: BiQueryTemplate) => seedMut.mutate([tpl.id])}
        onDelete={(tpl) => {
          if (window.confirm(t('bi.templatesDeleteConfirm'))) deleteMut.mutate(tpl.id);
        }}
        seedingId={seedingId}
      />

      {items.length > 0 && (
        <p className="text-xs text-slate-500">
          {t('bi.templatesHint', { example: biTemplatePrompt(items[0], locale) })}
        </p>
      )}
    </PageShell>
  );
}
