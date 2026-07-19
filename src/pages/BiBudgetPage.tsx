import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowLeftRight,
  CheckCircle2,
  CopyPlus,
  Download,
  FileSpreadsheet,
  FileText,
  Link2,
  Loader2,
  MessageSquare,
  Network,
  Plus,
  RefreshCw,
  Sparkles,
  Trash2,
  Upload,
  Wallet,
} from 'lucide-react';
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import clsx from 'clsx';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import ResponsiveTable from '@/components/ResponsiveTable';
import StatusBadge from '@/components/StatusBadge';
import { BudgetSparkline } from '@/components/bi/BudgetSparkline';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import { useLocale } from '@/context/LocaleContext';
import { useBiChatDock } from '@/context/BiChatDockContext';
import type { BiBudgetEnvelope } from '@/api/types';
import { t, getLocale } from '@/i18n';
import {
  BI_BUDGET_NONE_TEMPLATE,
  type BiBudgetActualsTemplate,
  type BiBudgetActualsTemplateId,
  resolveActualsTemplateId,
  sqlForActualsTemplate,
  templateOptionLabel,
} from '@/lib/biBudgetTemplates';
import { localizeUserMessage } from '@/utils/backendLabels';

const currentYear = new Date().getFullYear();
const CURRENCIES = ['TRY', 'USD', 'EUR'] as const;

function budgetChangeActionLabel(action: string | undefined): string {
  const code = String(action || '').trim();
  if (!code) return '—';
  const key = `bi.budget.changeAction.${code}`;
  const label = t(key);
  return label === key ? code : label;
}

function budgetChangeFieldLabel(field: string | undefined): string {
  const code = String(field || '').trim();
  if (!code) return '';
  const key = `bi.budget.changeField.${code}`;
  const label = t(key);
  return label === key ? code : label;
}

function budgetCommitmentStatusLabel(status: string | undefined): string {
  const code = String(status || 'open').trim().toLowerCase();
  const key = `bi.budget.commitmentStatus.${code}`;
  const label = t(key);
  return label === key ? code : label;
}

const emptyForm = (fiscalYear: number): Partial<BiBudgetEnvelope> => ({
  fiscal_year: fiscalYear,
  cost_center: '',
  kind: 'opex',
  name: '',
  allocated: 0,
  currency: 'TRY',
  committed: 0,
  actuals_sql: '',
  breakdown_sql: '',
  owner: '',
  status: 'draft',
  notes: '',
});

function money(n: number | null | undefined, currency = 'TRY'): string {
  if (n == null || Number.isNaN(n)) return '—';
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 0 }).format(n);
  } catch {
    return `${n.toLocaleString()} ${currency}`;
  }
}

function formatUsedPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `${Number(n).toFixed(2)}%`;
}

function healthStatus(health?: string | null): string {
  if (health === 'ok') return 'ok';
  if (health === 'watch') return 'warn';
  if (health === 'over') return 'failed';
  return 'pending';
}

function healthLabel(health?: string | null): string {
  if (health === 'ok') return t('bi.budget.healthOk');
  if (health === 'watch') return t('bi.budget.healthWatch');
  if (health === 'over') return t('bi.budget.healthOver');
  return t('bi.budget.healthPending');
}

function statusLabel(status?: string | null): string {
  if (status === 'approved') return t('bi.budget.statusApproved');
  if (status === 'closed') return t('bi.budget.statusClosed');
  return t('bi.budget.statusDraft');
}

function Field({
  label,
  hint,
  className,
  children,
}: {
  label: string;
  hint?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={clsx('block space-y-1', className)}>
      <span className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</span>
      {hint ? <span className="block text-[11px] font-normal normal-case leading-snug text-slate-500">{hint}</span> : null}
      {children}
    </label>
  );
}

function ToolbarGroup({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

const toolbarBtn =
  'inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-slate-200/80 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition hover:border-violet-300 hover:bg-violet-50/70 hover:text-violet-900 disabled:cursor-not-allowed disabled:opacity-45';

export default function BiBudgetPage() {
  useLocale();
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const { openChat } = useBiChatDock();
  const [searchParams, setSearchParams] = useSearchParams();
  const urlHadYearRef = useRef(Boolean(searchParams.get('year')));
  const [year, setYear] = useState(() => {
    const y = Number(searchParams.get('year') || currentYear);
    return Number.isFinite(y) && y >= 2000 && y <= 2100 ? y : currentYear;
  });
  const [scenarioFilter, setScenarioFilter] = useState(() => {
    const s = (searchParams.get('scenario') || 'base').trim().toLowerCase();
    return s === 'optimistic' || s === 'pessimistic' || s === 'base' ? s : 'base';
  });
  const [reportingCurrency, setReportingCurrency] = useState(() =>
    (searchParams.get('currency') || '').trim().toUpperCase(),
  );
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferFrom, setTransferFrom] = useState('');
  const [transferTo, setTransferTo] = useState('');
  const [transferAmount, setTransferAmount] = useState(0);
  const [commitDesc, setCommitDesc] = useState('');
  const [commitAmount, setCommitAmount] = useState(0);
  const [fxFrom, setFxFrom] = useState('USD');
  const [fxTo, setFxTo] = useState('TRY');
  const [fxRate, setFxRate] = useState(1);
  const [form, setForm] = useState<Partial<BiBudgetEnvelope> | null>(null);
  const [actualsMode, setActualsMode] = useState<BiBudgetActualsTemplateId>('none');
  const [advancedSqlOpen, setAdvancedSqlOpen] = useState(false);
  const [flash, setFlash] = useState<{ text: string; ok: boolean } | null>(null);
  const formPanelRef = useRef<HTMLDivElement>(null);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const enabled = isRunnerConfigured(config);

  const yearSuggest = useQuery({
    queryKey: ['bi-budgets-year-suggest', config],
    queryFn: () => api.bi.budgets.summary(config),
    enabled: enabled && !urlHadYearRef.current,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (urlHadYearRef.current) return;
    const sug = yearSuggest.data?.suggested_fiscal_year;
    if (typeof sug === 'number' && sug >= 2000 && sug <= 2100 && sug !== year) {
      setYear(sug);
    }
  }, [yearSuggest.data?.suggested_fiscal_year, year]);

  useEffect(() => {
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams();
        next.set('year', String(year));
        next.set('scenario', scenarioFilter || 'base');
        if (reportingCurrency) next.set('currency', reportingCurrency);
        if (next.toString() === prev.toString()) return prev;
        return next;
      },
      { replace: true },
    );
  }, [year, scenarioFilter, reportingCurrency, setSearchParams]);

  const list = useQuery({
    queryKey: ['bi-budgets', config, year, scenarioFilter],
    queryFn: () => api.bi.budgets.list(config, { fiscal_year: year, scenario: scenarioFilter || undefined }),
    enabled,
  });

  const summary = useQuery({
    queryKey: ['bi-budgets-summary', config, year, scenarioFilter, reportingCurrency],
    queryFn: () =>
      api.bi.budgets.summary(config, year, {
        scenario: scenarioFilter || undefined,
        reporting_currency: reportingCurrency || undefined,
      }),
    enabled,
  });

  const periodsQ = useQuery({
    queryKey: ['bi-budget-periods', config, form?.id],
    queryFn: () => api.bi.budgets.periods(config, form!.id!),
    enabled: enabled && Boolean(form?.id),
  });

  const commitmentsQ = useQuery({
    queryKey: ['bi-budget-commitments', config, form?.id],
    queryFn: () => api.bi.budgets.commitments(config, form!.id!),
    enabled: enabled && Boolean(form?.id),
  });

  const fxQ = useQuery({
    queryKey: ['bi-fx-rates', config],
    queryFn: () => api.bi.budgets.fxRates(config),
    enabled,
  });

  const costCentersQ = useQuery({
    queryKey: ['bi-cost-centers', config],
    queryFn: () => api.bi.budgets.costCenters(config),
    enabled,
  });

  const rollupQ = useQuery({
    queryKey: ['bi-cost-center-rollup', config, year, scenarioFilter, reportingCurrency],
    queryFn: () =>
      api.bi.budgets.costCenterRollup(config, year, {
        scenario: scenarioFilter || undefined,
        reporting_currency: reportingCurrency || undefined,
      }),
    enabled,
  });

  const [ccCode, setCcCode] = useState('');
  const [ccName, setCcName] = useState('');
  const [ccParent, setCcParent] = useState('');
  const [showRollup, setShowRollup] = useState(false);

  const templatesQ = useQuery({
    queryKey: ['bi-budget-actuals-templates', config],
    queryFn: () => api.bi.budgets.actualsTemplates(config),
    enabled,
    staleTime: 60_000,
  });

  const relatedTablesQ = useQuery({
    queryKey: ['bi-budget-related-tables', config],
    queryFn: () => api.bi.budgets.relatedTables(config, 16),
    enabled,
    staleTime: 60_000,
  });

  const actualsTemplates: BiBudgetActualsTemplate[] = useMemo(() => {
    const fromApi = (templatesQ.data?.templates || []).map((tpl) => ({
      id: tpl.id,
      kind: tpl.kind,
      labelKey: tpl.label_key,
      label_key: tpl.label_key,
      table: tpl.table,
      table_name: tpl.table_name,
      measure: tpl.measure,
      sql: tpl.sql || '',
      demo: tpl.demo,
    }));
    if (!fromApi.some((t) => t.id === 'none')) {
      return [BI_BUDGET_NONE_TEMPLATE, ...fromApi];
    }
    return fromApi.length ? fromApi : [BI_BUDGET_NONE_TEMPLATE];
  }, [templatesQ.data]);

  const changeLogQ = useQuery({
    queryKey: ['bi-budget-change-log', config, form?.id],
    queryFn: () => api.bi.budgets.changeLog(config, form!.id!),
    enabled: enabled && Boolean(form?.id),
  });

  const historyQ = useQuery({
    queryKey: ['bi-budget-history', config, form?.id],
    queryFn: () => api.bi.budgets.history(config, form!.id!),
    enabled: enabled && Boolean(form?.id),
  });

  const breakdownQ = useQuery({
    queryKey: ['bi-budget-breakdown', config, form?.id, form?.breakdown_sql],
    queryFn: () => api.bi.budgets.breakdown(config, form!.id!),
    enabled: enabled && Boolean(form?.id && form?.breakdown_sql?.trim()),
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['bi-budgets'] });
    void qc.invalidateQueries({ queryKey: ['bi-budgets-summary'] });
    void qc.invalidateQueries({ queryKey: ['bi-briefing'] });
    void qc.invalidateQueries({ queryKey: ['bi-ops-health'] });
    void qc.invalidateQueries({ queryKey: ['bi-budget-change-log'] });
    void qc.invalidateQueries({ queryKey: ['bi-budget-history'] });
    void qc.invalidateQueries({ queryKey: ['bi-budget-breakdown'] });
    void qc.invalidateQueries({ queryKey: ['bi-budget-periods'] });
    void qc.invalidateQueries({ queryKey: ['bi-budget-commitments'] });
    void qc.invalidateQueries({ queryKey: ['bi-fx-rates'] });
    void qc.invalidateQueries({ queryKey: ['bi-cost-centers'] });
    void qc.invalidateQueries({ queryKey: ['bi-cost-center-rollup'] });
  };

  const showFlash = (text: string, ok: boolean) => {
    setFlash({ text, ok });
    window.setTimeout(() => setFlash(null), ok ? 4000 : 6000);
  };

  const openForm = (next: Partial<BiBudgetEnvelope>) => {
    setForm({
      ...next,
      scenario: next.scenario ?? (scenarioFilter || 'base'),
    });
    const mode = resolveActualsTemplateId(next.actuals_sql, actualsTemplates);
    setActualsMode(mode);
    setAdvancedSqlOpen(mode === 'custom');
    window.requestAnimationFrame(() => {
      formPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      nameInputRef.current?.focus();
    });
  };

  const closeForm = () => setForm(null);

  const submitForm = () => {
    if (!form?.name || form.allocated == null || form.locked || form.status === 'closed') return;
    saveMut.mutate({
      ...form,
      fiscal_year: form.fiscal_year ?? year,
      kind: form.kind || 'opex',
      currency: form.currency || 'TRY',
      status: form.status || 'draft',
      scenario: form.scenario || scenarioFilter || 'base',
      name: form.name,
      allocated: Number(form.allocated),
      actuals_sql:
        actualsMode === 'custom'
          ? form.actuals_sql || ''
          : sqlForActualsTemplate(actualsMode, actualsTemplates) || form.actuals_sql || '',
    });
  };

  const saveMut = useMutation({
    mutationFn: (body: Partial<BiBudgetEnvelope> & { name: string; allocated: number }) =>
      api.bi.budgets.save(config, body),
    onSuccess: () => {
      invalidate();
      setForm(null);
      showFlash(t('bi.budget.saved'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const delMut = useMutation({
    mutationFn: (id: string) => api.bi.budgets.delete(config, id),
    onSuccess: () => {
      invalidate();
      setForm(null);
      showFlash(t('bi.budget.deleted'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const refreshAllMut = useMutation({
    mutationFn: () => api.bi.budgets.refreshAll(config, year),
    onSuccess: (res) => {
      invalidate();
      showFlash(
        t('bi.budget.refreshDone', { count: String(res.refreshed), errors: String(res.errors) }),
        (res.errors ?? 0) === 0,
      );
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const refreshOneMut = useMutation({
    mutationFn: (id: string) => api.bi.budgets.refreshOne(config, id),
    onSuccess: () => {
      invalidate();
      showFlash(t('bi.budget.refreshOneDone'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const templateMut = useMutation({
    mutationFn: () => api.bi.budgets.downloadTemplate(config, year),
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const importMut = useMutation({
    mutationFn: (file: File) => api.bi.budgets.importFile(config, file, year),
    onSuccess: (res) => {
      invalidate();
      const errCount = res.errors?.length ?? 0;
      const extras: string[] = [];
      if (res.periods_updated) {
        extras.push(t('bi.budget.importPeriods', { count: String(res.periods_updated) }));
      }
      if (res.commitments_upserted) {
        extras.push(t('bi.budget.importCommitments', { count: String(res.commitments_upserted) }));
      }
      const extraSuffix = extras.length ? ` · ${extras.join(' · ')}` : '';
      const base = t('bi.budget.importDone', {
        created: String(res.created ?? 0),
        updated: String(res.updated ?? 0),
      });
      if (errCount > 0) {
        const first = res.errors[0];
        const detail = first
          ? ` · ${t('bi.budget.importRowError', {
              row: String(first.row),
              message: localizeUserMessage(first.code),
            })}`
          : '';
        showFlash(
          t('bi.budget.importPartial', {
            created: String(res.created ?? 0),
            updated: String(res.updated ?? 0),
            errors: String(errCount),
          }) +
            extraSuffix +
            detail,
          false,
        );
      } else {
        showFlash(base + extraSuffix, true);
      }
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const exportMut = useMutation({
    mutationFn: (format: 'pdf' | 'xlsx') =>
      api.bi.budgets.exportReport(config, {
        format,
        fiscalYear: year,
        locale: getLocale(),
        scenario: scenarioFilter || 'base',
        reportingCurrency: reportingCurrency || undefined,
      }),
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const createAlertMut = useMutation({
    mutationFn: (id: string) => api.bi.budgets.createAlert(config, id, { threshold_pct: 80, condition: 'gte' }),
    onSuccess: (res) => {
      const created = res.created !== false;
      showFlash(
        created ? t('bi.budget.createAlertDone') : t('bi.budget.createAlertExists'),
        true,
      );
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const narrativeQ = useQuery({
    queryKey: ['bi-budgets-narrative', config, year, scenarioFilter, reportingCurrency, getLocale()],
    queryFn: () =>
      api.bi.budgets.narrative(config, year, getLocale(), {
        scenario: scenarioFilter || 'base',
        reportingCurrency: reportingCurrency || undefined,
      }),
    enabled,
  });

  const cloneMut = useMutation({
    mutationFn: () =>
      api.bi.budgets.cloneYear(config, {
        from_year: year,
        to_year: year + 1,
        copy_actuals_sql: true,
        scenario: scenarioFilter || 'base',
      }),
    onSuccess: (res) => {
      const nextYear = year + 1;
      setYear(nextYear);
      invalidate();
      showFlash(
        t('bi.budget.cloneDone', {
          created: String(res.created ?? 0),
          skipped: String(res.skipped ?? 0),
          year: String(nextYear),
        }),
        true,
      );
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const syncFromSourceMut = useMutation({
    mutationFn: () =>
      api.bi.budgets.syncFromSource(config, {
        fiscal_year: year,
        refresh: true,
        scenario: scenarioFilter || 'base',
      }),
    onSuccess: (res) => {
      invalidate();
      const warn = (res.warnings || [])
        .map((w) => localizeUserMessage(w))
        .filter(Boolean)
        .join(' · ');
      showFlash(
        t('bi.budget.syncFromSourceDone', {
          created: String(res.created ?? 0),
          updated: String(res.updated ?? 0),
          matched: String(res.match_count ?? 0),
        }) + (warn ? ` — ${warn}` : ''),
        true,
      );
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const approveMut = useMutation({
    mutationFn: (id: string) => api.bi.budgets.approve(config, id),
    onSuccess: (row) => {
      invalidate();
      setForm(row);
      showFlash(t('bi.budget.approved'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const lockMut = useMutation({
    mutationFn: ({ id, lock }: { id: string; lock: boolean }) =>
      lock ? api.bi.budgets.lock(config, id) : api.bi.budgets.unlock(config, id),
    onSuccess: (row) => {
      invalidate();
      setForm(row);
      showFlash(row.locked ? t('bi.budget.locked') : t('bi.budget.unlocked'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const validateSqlMut = useMutation({
    mutationFn: (sql: string) => api.bi.budgets.validateSql(config, sql),
    onSuccess: (res) => {
      showFlash(t('bi.budget.validateSqlOk', { sample: String(res.sample) }), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const sharePackMut = useMutation({
    mutationFn: () =>
      api.bi.budgets.sharePack(config, {
        fiscal_year: year,
        scenario: scenarioFilter || 'base',
        reporting_currency: reportingCurrency || undefined,
        locale: getLocale().split('-')[0] || 'en',
        ttl_hours: 72,
      }),
    onSuccess: (share) => {
      const token = String(share.token || '');
      const url = `${window.location.origin}/bi/public/${token}`;
      void navigator.clipboard?.writeText(url).catch(() => undefined);
      showFlash(t('bi.budget.sharePackDone', { url }), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const transferMut = useMutation({
    mutationFn: () =>
      api.bi.budgets.transfer(config, {
        from_budget_id: transferFrom,
        to_budget_id: transferTo,
        amount: transferAmount,
      }),
    onSuccess: () => {
      invalidate();
      setTransferOpen(false);
      showFlash(t('bi.budget.transferDone'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const savePeriodsMut = useMutation({
    mutationFn: (periods: Array<{ period_index: number; allocated: number; actual?: number | null }>) =>
      api.bi.budgets.savePeriods(config, form!.id!, periods),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-budget-periods'] });
      showFlash(t('bi.budget.periodsSaved'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const saveCommitMut = useMutation({
    mutationFn: () =>
      api.bi.budgets.saveCommitment(config, form!.id!, {
        description: commitDesc,
        amount: commitAmount,
        currency: form?.currency || 'TRY',
        status: 'open',
      }),
    onSuccess: () => {
      invalidate();
      setCommitDesc('');
      setCommitAmount(0);
      showFlash(t('bi.budget.commitmentSaved'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const updateCommitStatusMut = useMutation({
    mutationFn: (args: {
      id: string;
      description?: string;
      amount: number;
      currency?: string;
      status: 'open' | 'released' | 'cancelled';
      due_date?: string | null;
    }) =>
      api.bi.budgets.saveCommitment(config, form!.id!, {
        id: args.id,
        description: args.description,
        amount: args.amount,
        currency: args.currency || form?.currency || 'TRY',
        status: args.status,
        due_date: args.due_date || undefined,
      }),
    onSuccess: () => {
      invalidate();
      showFlash(t('bi.budget.commitmentStatusUpdated'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const fxMut = useMutation({
    mutationFn: () =>
      api.bi.budgets.upsertFxRate(config, {
        from_currency: fxFrom,
        to_currency: fxTo,
        rate: fxRate,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-fx-rates'] });
      void qc.invalidateQueries({ queryKey: ['bi-budgets-summary'] });
      showFlash(t('bi.budget.fxSaved'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const saveCcMut = useMutation({
    mutationFn: () =>
      api.bi.budgets.saveCostCenter(config, {
        code: ccCode,
        name: ccName,
        parent_id: ccParent || null,
      }),
    onSuccess: () => {
      invalidate();
      setCcCode('');
      setCcName('');
      setCcParent('');
      showFlash(t('bi.budget.costCenterSaved'), true);
    },
    onError: (err) => showFlash(localizeUserMessage((err as Error).message), false),
  });

  const costCenterOptions = costCentersQ.data?.cost_centers || [];
  const costCenterTreeOptions = useMemo(() => {
    type CcNode = { id: string; code: string; name: string; children?: CcNode[] };
    const walk = (nodes: CcNode[], depth: number): Array<{ id: string; code: string; name: string; depth: number }> => {
      const out: Array<{ id: string; code: string; name: string; depth: number }> = [];
      for (const n of nodes) {
        out.push({ id: n.id, code: n.code, name: n.name, depth });
        out.push(...walk(n.children || [], depth + 1));
      }
      return out;
    };
    const tree = (costCentersQ.data?.tree || []) as CcNode[];
    if (tree.length) return walk(tree, 0);
    return costCenterOptions.map((c) => ({ id: c.id, code: c.code, name: c.name, depth: 0 }));
  }, [costCentersQ.data?.tree, costCenterOptions]);

  const items = list.data?.budgets ?? [];
  const totals = summary.data?.totals;
  const opex = summary.data?.by_kind?.opex;
  const capex = summary.data?.by_kind?.capex;
  const watchCount = summary.data?.budget_watch_count ?? 0;

  const yearOptions = useMemo(() => {
    const ys = new Set<number>([currentYear, currentYear - 1, currentYear + 1, year]);
    for (const b of items) if (b.fiscal_year) ys.add(b.fiscal_year);
    for (const y of summary.data?.available_fiscal_years || []) ys.add(y);
    for (const y of yearSuggest.data?.available_fiscal_years || []) ys.add(y);
    return [...ys].sort((a, b) => b - a);
  }, [items, year, summary.data?.available_fiscal_years, yearSuggest.data?.available_fiscal_years]);

  const applyActualsMode = (mode: BiBudgetActualsTemplateId) => {
    setActualsMode(mode);
    if (mode === 'custom') {
      setAdvancedSqlOpen(true);
      return;
    }
    setAdvancedSqlOpen(false);
    setForm((prev) => (prev ? { ...prev, actuals_sql: sqlForActualsTemplate(mode, actualsTemplates) } : prev));
  };

  const formReadOnly = Boolean(form?.locked) || String(form?.status || '').toLowerCase() === 'closed';

  const formPanel = form ? (
    <div
      ref={formPanelRef}
      className="card overflow-hidden border border-violet-200/80 bg-white shadow-sm ring-2 ring-violet-200/40"
    >
      <div className="sticky top-0 z-20 flex flex-wrap items-start justify-between gap-3 border-b border-violet-100 bg-white/95 px-4 py-3 backdrop-blur">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-slate-900">
            {form.id ? t('bi.budget.formEditTitle') : t('bi.budget.formNewTitle')}
          </p>
          {form.name ? (
            <p className="mt-0.5 truncate text-xs text-violet-700">{form.name}</p>
          ) : (
            <p className="mt-0.5 text-xs leading-snug text-slate-500">{t('bi.budget.formHint')}</p>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <button type="button" className="btn-secondary text-xs" onClick={closeForm}>
            {t('common.cancel')}
          </button>
          <button
            type="button"
            className="btn-primary inline-flex items-center gap-1.5 text-xs"
            disabled={!form.name || form.allocated == null || saveMut.isPending || formReadOnly}
            onClick={submitForm}
          >
            {saveMut.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
            {t('bi.budget.save')}
          </button>
        </div>
      </div>

      <div className="space-y-4 p-4">
      {formReadOnly ? (
        <p className="rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
          {form.locked ? t('bi.budget.lockedHint') : t('bi.budget.closedHint')}
        </p>
      ) : null}

      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
          {t('bi.budget.sectionDefinition')}
        </h3>
        <div className="grid gap-3">
          <Field label={t('bi.budget.name')} hint={t('bi.budget.nameHint')}>
            <input
              ref={nameInputRef}
              className="input-field"
              value={form.name ?? ''}
              disabled={formReadOnly}
              placeholder={t('bi.budget.namePlaceholder')}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('bi.budget.fiscalYear')}>
              <select
                className="input-field"
                value={form.fiscal_year ?? year}
                disabled={formReadOnly}
                onChange={(e) => setForm({ ...form, fiscal_year: Number(e.target.value) })}
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t('bi.budget.kind')} hint={t('bi.budget.kindHint')}>
              <select
                className="input-field"
                value={form.kind ?? 'opex'}
                disabled={formReadOnly}
                onChange={(e) => setForm({ ...form, kind: e.target.value })}
              >
                <option value="opex">{t('bi.budget.kindOpex')}</option>
                <option value="capex">{t('bi.budget.kindCapex')}</option>
                <option value="other">{t('bi.budget.kindOther')}</option>
              </select>
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('bi.budget.allocated')} hint={t('bi.budget.allocatedHint')}>
              <input
                className="input-field"
                type="number"
                value={form.allocated ?? 0}
                disabled={formReadOnly}
                onChange={(e) => setForm({ ...form, allocated: Number(e.target.value) })}
              />
            </Field>
            <Field label={t('bi.budget.currency')}>
              <select
                className="input-field"
                value={form.currency ?? 'TRY'}
                disabled={formReadOnly}
                onChange={(e) => setForm({ ...form, currency: e.target.value })}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </Field>
          </div>
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
          {t('bi.budget.sectionPeople')}
        </h3>
        <div className="grid gap-3">
          <Field label={t('bi.budget.costCenter')} hint={t('bi.budget.costCenterHint')}>
            <input
              className="input-field"
              list="bi-budget-cost-centers"
              value={form.cost_center ?? ''}
              disabled={formReadOnly}
              onChange={(e) => setForm({ ...form, cost_center: e.target.value })}
              placeholder={t('bi.budget.costCenterPlaceholder')}
            />
            <datalist id="bi-budget-cost-centers">
              {costCenterOptions.map((c) => (
                <option key={c.id} value={c.code}>
                  {c.name}
                </option>
              ))}
            </datalist>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t('bi.budget.owner')} hint={t('bi.budget.ownerHint')}>
              <input
                className="input-field"
                value={form.owner ?? ''}
                disabled={formReadOnly}
                placeholder={t('bi.budget.ownerPlaceholder')}
                onChange={(e) => setForm({ ...form, owner: e.target.value })}
              />
            </Field>
            <Field label={t('bi.budget.status')} hint={t('bi.budget.statusHint')}>
              <select
                className="input-field"
                value={form.status ?? 'draft'}
                disabled={formReadOnly}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
              >
                <option value="draft">{t('bi.budget.statusDraft')}</option>
                <option value="approved">{t('bi.budget.statusApproved')}</option>
                <option value="closed">{t('bi.budget.statusClosed')}</option>
              </select>
            </Field>
          </div>

        </div>
      </section>

      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
          {t('bi.budget.sectionActuals')}
        </h3>
        <Field label={t('bi.budget.actualsMode')} hint={t('bi.budget.actualsModeHint')}>
          <select
            className="input-field"
            value={actualsMode === 'custom' ? 'custom' : actualsMode}
            disabled={formReadOnly}
            onChange={(e) => applyActualsMode(e.target.value as BiBudgetActualsTemplateId)}
          >
            {actualsTemplates.map((tpl) => (
              <option key={tpl.id} value={tpl.id}>
                {templateOptionLabel(tpl, t)}
              </option>
            ))}
            <option value="custom">{t('bi.budget.advancedSql')}</option>
          </select>
        </Field>
        {form.id && (historyQ.data?.points || []).length > 1 ? (
          <div className="flex items-center gap-3 rounded-md border border-slate-100 bg-slate-50/80 px-2 py-1.5">
            <span className="text-[11px] font-medium uppercase text-slate-500">{t('bi.budget.sparkline')}</span>
            <BudgetSparkline
              values={[...(historyQ.data?.points || [])].reverse().map((p) => p.actual)}
            />
          </div>
        ) : null}
        {breakdownQ.data?.rows?.length ? (
          <div className="max-h-40 overflow-auto rounded-md border border-slate-100 text-[11px]">
            <table className="min-w-full">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  {(breakdownQ.data.columns || []).map((c) => (
                    <th key={c} className="px-2 py-1 text-left font-medium">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {breakdownQ.data.rows.slice(0, 8).map((row, idx) => {
                  const cells = Array.isArray(row)
                    ? row
                    : (breakdownQ.data?.columns || []).map((c) => (row as Record<string, unknown>)[c]);
                  return (
                    <tr key={idx} className="border-t border-slate-50">
                      {cells.map((cell, i) => (
                        <td key={i} className="px-2 py-1 tabular-nums text-slate-700">
                          {cell == null ? '—' : String(cell)}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </section>

      <details className="rounded-xl border border-slate-200 bg-slate-50/60 open:bg-white">
        <summary className="cursor-pointer select-none px-3 py-2.5 text-sm font-medium text-slate-700">
          {t('bi.budget.sectionAdvanced')}
        </summary>
        <div className="space-y-3 border-t border-slate-100 px-3 pb-3 pt-3">
          <p className="text-[11px] leading-snug text-slate-500">{t('bi.budget.sectionAdvancedHint')}</p>
          <Field label={t('bi.budget.scenario')} hint={t('bi.budget.scenarioHint')}>
            <select
              className="input-field"
              value={form.scenario ?? 'base'}
              disabled={formReadOnly}
              onChange={(e) => setForm({ ...form, scenario: e.target.value })}
            >
              <option value="base">{t('bi.budget.scenarioBase')}</option>
              <option value="optimistic">{t('bi.budget.scenarioOptimistic')}</option>
              <option value="pessimistic">{t('bi.budget.scenarioPessimistic')}</option>
            </select>
          </Field>
          <Field label={t('bi.budget.committed')} hint={t('bi.budget.committedHint')}>
            <input
              className="input-field"
              type="number"
              value={form.committed ?? 0}
              disabled={formReadOnly}
              onChange={(e) => setForm({ ...form, committed: Number(e.target.value) })}
            />
          </Field>
          {(advancedSqlOpen || actualsMode === 'custom') && (
            <Field label={t('bi.budget.actualsSql')} hint={t('bi.budget.actualsSqlHint')}>
              <textarea
                className="input-field min-h-[72px] font-mono text-sm"
                value={form.actuals_sql ?? ''}
                disabled={formReadOnly}
                onChange={(e) => {
                  setActualsMode('custom');
                  setForm({ ...form, actuals_sql: e.target.value });
                }}
              />
              <button
                type="button"
                className="btn-secondary mt-2 text-xs"
                disabled={!form.actuals_sql?.trim() || validateSqlMut.isPending || formReadOnly}
                onClick={() => validateSqlMut.mutate(form.actuals_sql || '')}
              >
                {validateSqlMut.isPending ? <Loader2 className="mr-1 inline h-3 w-3 animate-spin" /> : null}
                {t('bi.budget.validateSql')}
              </button>
            </Field>
          )}
          {!advancedSqlOpen && actualsMode !== 'custom' ? (
            <button
              type="button"
              className="text-xs font-medium text-violet-700 hover:underline"
              disabled={formReadOnly}
              onClick={() => {
                setAdvancedSqlOpen(true);
                setActualsMode('custom');
              }}
            >
              {t('bi.budget.showCustomSql')}
            </button>
          ) : null}
          <Field label={t('bi.budget.breakdownSql')} hint={t('bi.budget.breakdownSqlHint')}>
            <textarea
              className="input-field min-h-[56px] font-mono text-sm"
              value={form.breakdown_sql ?? ''}
              disabled={formReadOnly}
              onChange={(e) => setForm({ ...form, breakdown_sql: e.target.value })}
              placeholder={t('bi.budget.breakdownSqlPlaceholder')}
            />
          </Field>
        </div>
      </details>

      {form.id ? (
        <section className="space-y-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
            {t('bi.budget.sectionControl')}
          </h3>
          <div className="flex flex-wrap gap-2">
            {form.status !== 'approved' ? (
              <button
                type="button"
                className="btn-secondary text-xs"
                disabled={approveMut.isPending || formReadOnly}
                onClick={() => approveMut.mutate(form.id!)}
              >
                {t('bi.budget.approve')}
              </button>
            ) : null}
            <button
              type="button"
              className="btn-secondary text-xs"
              disabled={lockMut.isPending}
              onClick={() => lockMut.mutate({ id: form.id!, lock: !form.locked })}
            >
              {form.locked ? t('bi.budget.unlock') : t('bi.budget.lock')}
            </button>
          </div>
          {(changeLogQ.data?.entries || []).length > 0 ? (
            <div className="max-h-48 overflow-y-auto rounded-md border border-slate-100 bg-slate-50/80 p-2 text-[11px] text-slate-600">
              <p className="mb-1 font-medium text-slate-700">{t('bi.budget.changeLog')}</p>
              <ul className="space-y-1">
                {(changeLogQ.data?.entries || []).slice(0, 40).map((e, idx) => (
                  <li key={`${e.created_at}-${idx}`}>
                    {e.created_at ? new Date(e.created_at).toLocaleString() : '—'} · {e.actor} ·{' '}
                    {budgetChangeActionLabel(e.action)}
                    {e.field ? ` · ${budgetChangeFieldLabel(e.field)}` : ''}
                    {e.old_value != null || e.new_value != null
                      ? ` · ${e.old_value ?? '—'} → ${e.new_value ?? '—'}`
                      : ''}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      {form.id ? (
        <section className="space-y-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
            {t('bi.budget.sectionPeriods')}
          </h3>
          <div className="grid grid-cols-4 gap-1 sm:grid-cols-6">
            {(periodsQ.data?.periods || Array.from({ length: 12 }, (_, i) => ({ period_index: i + 1, allocated: 0, actual: null }))).map(
              (p, idx) => (
                <label key={p.period_index} className="block text-[10px] text-slate-500">
                  M{p.period_index}
                  <input
                    className="input-field mt-0.5 px-1 py-1 text-xs"
                    type="number"
                    value={p.allocated}
                    disabled={formReadOnly}
                    onChange={(e) => {
                      const next = [...(periodsQ.data?.periods || [])];
                      if (!next.length) {
                        for (let i = 1; i <= 12; i++) next.push({ period_index: i, allocated: 0, actual: null });
                      }
                      next[idx] = { ...next[idx], allocated: Number(e.target.value) };
                      void qc.setQueryData(['bi-budget-periods', config, form.id], { periods: next });
                    }}
                  />
                </label>
              ),
            )}
          </div>
          <button
            type="button"
            className="btn-secondary text-xs"
            disabled={savePeriodsMut.isPending || formReadOnly}
            onClick={() => {
              const periods =
                periodsQ.data?.periods ||
                Array.from({ length: 12 }, (_, i) => ({
                  period_index: i + 1,
                  allocated: 0,
                  actual: null as number | null,
                }));
              savePeriodsMut.mutate(periods);
            }}
          >
            {t('bi.budget.savePeriods')}
          </button>
        </section>
      ) : null}

      {form.id ? (
        <section className="space-y-2">
          <h3 className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
            {t('bi.budget.sectionCommitments')}
          </h3>
          <div className="flex flex-wrap gap-2">
            <input
              className="input-field min-w-[8rem] flex-1"
              placeholder={t('bi.budget.commitmentDesc')}
              value={commitDesc}
              disabled={formReadOnly}
              onChange={(e) => setCommitDesc(e.target.value)}
            />
            <input
              className="input-field max-w-[7rem]"
              type="number"
              value={commitAmount}
              disabled={formReadOnly}
              onChange={(e) => setCommitAmount(Number(e.target.value))}
            />
            <button
              type="button"
              className="btn-secondary text-xs"
              disabled={saveCommitMut.isPending || !commitAmount || formReadOnly}
              onClick={() => saveCommitMut.mutate()}
            >
              {t('bi.budget.addCommitment')}
            </button>
          </div>
          <ul className="space-y-1 text-[11px] text-slate-600">
            {(commitmentsQ.data?.commitments || []).slice(0, 24).map((c) => {
              const status = String(c.status || 'open').toLowerCase();
              const busy = updateCommitStatusMut.isPending || formReadOnly;
              return (
              <li key={c.id} className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {c.description || c.id} · {money(c.amount, c.currency)} · {budgetCommitmentStatusLabel(c.status)}
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  {status === 'open' ? (
                    <>
                      <button
                        type="button"
                        className="text-emerald-700 hover:underline disabled:opacity-40"
                        disabled={busy}
                        onClick={() =>
                          updateCommitStatusMut.mutate({
                            id: c.id,
                            description: c.description,
                            amount: Number(c.amount || 0),
                            currency: c.currency,
                            status: 'released',
                            due_date: c.due_date,
                          })
                        }
                      >
                        {t('bi.budget.commitmentRelease')}
                      </button>
                      <button
                        type="button"
                        className="text-amber-700 hover:underline disabled:opacity-40"
                        disabled={busy}
                        onClick={() =>
                          updateCommitStatusMut.mutate({
                            id: c.id,
                            description: c.description,
                            amount: Number(c.amount || 0),
                            currency: c.currency,
                            status: 'cancelled',
                            due_date: c.due_date,
                          })
                        }
                      >
                        {t('bi.budget.commitmentCancel')}
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      className="text-sky-700 hover:underline disabled:opacity-40"
                      disabled={busy}
                      onClick={() =>
                        updateCommitStatusMut.mutate({
                          id: c.id,
                          description: c.description,
                          amount: Number(c.amount || 0),
                          currency: c.currency,
                          status: 'open',
                          due_date: c.due_date,
                        })
                      }
                    >
                      {t('bi.budget.commitmentReopen')}
                    </button>
                  )}
                  <button
                    type="button"
                    className="text-status-fail disabled:opacity-40"
                    disabled={busy}
                    onClick={() => {
                      void api.bi.budgets.deleteCommitment(config, form.id!, c.id).then(() => invalidate());
                    }}
                  >
                    {t('common.delete')}
                  </button>
                </span>
              </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <section className="space-y-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wide text-violet-700">
          {t('bi.budget.sectionNotes')}
        </h3>
        <Field label={t('bi.budget.notes')}>
          <textarea
            className="input-field min-h-[64px]"
            value={form.notes ?? ''}
            disabled={formReadOnly}
            placeholder={t('bi.budget.notesPlaceholder')}
            onChange={(e) => setForm({ ...form, notes: e.target.value })}
          />
        </Field>
      </section>

      <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
        <button
          type="button"
          className="btn-primary inline-flex items-center gap-2"
          disabled={!form.name || form.allocated == null || saveMut.isPending || formReadOnly}
          onClick={submitForm}
        >
          {saveMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          {t('bi.budget.save')}
        </button>
        <button type="button" className="btn-secondary" onClick={closeForm}>
          {t('common.cancel')}
        </button>
        {form.id ? (
          <button
            type="button"
            className="inline-flex min-h-10 items-center gap-1 rounded-lg px-3 text-xs font-medium text-status-fail hover:bg-red-50 disabled:opacity-40"
            disabled={formReadOnly || delMut.isPending}
            onClick={() => {
              if (window.confirm(t('bi.budget.deleteConfirm'))) delMut.mutate(form.id!);
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            {t('common.delete')}
          </button>
        ) : null}
      </div>
      </div>
    </div>
  ) : null;

  return (
    <PageShell pageId="biBudget" titleKey="bi.budget.title" subtitleKey="bi.budget.subtitle" maxWidth="max-w-7xl">
      <div className="mb-4 space-y-3">
        <div className="rounded-2xl border border-violet-200/60 bg-gradient-to-br from-violet-50/80 via-white to-slate-50/90 p-4 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="grid min-w-0 flex-1 grid-cols-1 gap-3 sm:grid-cols-3">
              <Field label={t('bi.budget.fiscalYear')}>
                <select
                  className="input-field"
                  value={year}
                  onChange={(e) => setYear(Number(e.target.value))}
                >
                  {yearOptions.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label={t('bi.budget.planVersion')} hint={t('bi.budget.planVersionHint')}>
                <select
                  className="input-field"
                  value={scenarioFilter}
                  onChange={(e) => setScenarioFilter(e.target.value)}
                >
                  <option value="base">{t('bi.budget.scenarioBase')}</option>
                  <option value="optimistic">{t('bi.budget.scenarioOptimistic')}</option>
                  <option value="pessimistic">{t('bi.budget.scenarioPessimistic')}</option>
                </select>
              </Field>
              <Field label={t('bi.budget.reportingCurrency')}>
                <select
                  className="input-field"
                  value={reportingCurrency}
                  onChange={(e) => setReportingCurrency(e.target.value)}
                >
                  <option value="">{t('bi.budget.reportingCurrencyNone')}</option>
                  {CURRENCIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <button
              type="button"
              className={clsx(
                'group relative w-full shrink-0 overflow-hidden rounded-xl px-4 py-2.5 text-sm font-semibold text-white shadow-md transition',
                'bg-gradient-to-r from-violet-600 via-violet-500 to-indigo-500',
                'hover:from-violet-500 hover:via-violet-500 hover:to-indigo-400',
                'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-violet-500',
                'lg:w-auto',
                form && !form.id ? 'opacity-60' : 'bi-budget-add-cta',
              )}
              disabled={Boolean(form && !form.id)}
              title={t('bi.budget.addItemHint')}
              onClick={() => openForm(emptyForm(year))}
            >
              <span className="pointer-events-none absolute inset-0 bg-gradient-to-r from-transparent via-white/25 to-transparent opacity-0 transition group-hover:animate-[shimmer_1.2s_ease-in-out_infinite] group-hover:opacity-100" />
              <span className="relative inline-flex items-center gap-2">
                <Plus className="h-4 w-4" />
                {t('bi.budget.addItem')}
              </span>
            </button>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-3 shadow-sm sm:p-4">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:gap-5">
            <ToolbarGroup label={t('bi.budget.toolbarExcel')}>
              <button
                type="button"
                className={toolbarBtn}
                disabled={templateMut.isPending || !enabled}
                onClick={() => templateMut.mutate()}
              >
                {templateMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Download className="h-3.5 w-3.5 text-violet-600" />
                )}
                {t('bi.budget.downloadTemplate')}
              </button>
              <button
                type="button"
                className={toolbarBtn}
                disabled={importMut.isPending || !enabled}
                onClick={() => fileInputRef.current?.click()}
              >
                {importMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Upload className="h-3.5 w-3.5 text-violet-600" />
                )}
                {t('bi.budget.uploadExcel')}
              </button>
            </ToolbarGroup>

            <div className="hidden h-auto w-px self-stretch bg-slate-200/80 xl:block" aria-hidden />

            <ToolbarGroup label={t('bi.budget.toolbarReports')}>
              <button
                type="button"
                className={toolbarBtn}
                disabled={exportMut.isPending || !enabled}
                onClick={() => exportMut.mutate('pdf')}
              >
                {exportMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileText className="h-3.5 w-3.5 text-violet-600" />
                )}
                {t('bi.budget.exportPdf')}
              </button>
              <button
                type="button"
                className={toolbarBtn}
                disabled={exportMut.isPending || !enabled}
                onClick={() => exportMut.mutate('xlsx')}
              >
                {exportMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FileSpreadsheet className="h-3.5 w-3.5 text-violet-600" />
                )}
                {t('bi.budget.exportExcel')}
              </button>
            </ToolbarGroup>

            <div className="hidden h-auto w-px self-stretch bg-slate-200/80 xl:block" aria-hidden />

            <ToolbarGroup label={t('bi.budget.toolbarManage')}>
              <button
                type="button"
                className={toolbarBtn}
                disabled={cloneMut.isPending || !enabled}
                onClick={() => {
                  if (window.confirm(t('bi.budget.cloneConfirm', { from: String(year), to: String(year + 1) }))) {
                    cloneMut.mutate();
                  }
                }}
              >
                {cloneMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CopyPlus className="h-3.5 w-3.5 text-violet-600" />
                )}
                {t('bi.budget.cloneYear')}
              </button>
              <button
                type="button"
                className={toolbarBtn}
                disabled={syncFromSourceMut.isPending || !enabled}
                title={t('bi.budget.syncFromSourceHint')}
                onClick={async () => {
                  let previewHint = '';
                  try {
                    const preview = await api.bi.budgets.matchPreview(config, year);
                    const n = preview.matches?.length ?? 0;
                    const warns = (preview.warnings || [])
                      .map((w) => localizeUserMessage(w))
                      .filter(Boolean);
                    previewHint =
                      t('bi.budget.matchPreviewSummary', { count: String(n) }) +
                      (warns.length ? `\n${warns.join(' · ')}` : '');
                  } catch {
                    previewHint = '';
                  }
                  const msg =
                    (previewHint ? `${previewHint}\n\n` : '') +
                    t('bi.budget.syncFromSourceConfirm', { year: String(year) });
                  if (window.confirm(msg)) {
                    syncFromSourceMut.mutate();
                  }
                }}
              >
                {syncFromSourceMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Network className="h-3.5 w-3.5 text-violet-600" />
                )}
                {t('bi.budget.syncFromSource')}
              </button>
              <button
                type="button"
                className={toolbarBtn}
                disabled={sharePackMut.isPending || !enabled}
                onClick={() => {
                  if (window.confirm(t('bi.budget.sharePackConfirm', { year: String(year) }))) {
                    sharePackMut.mutate();
                  }
                }}
              >
                {sharePackMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Link2 className="h-3.5 w-3.5 text-violet-600" />
                )}
                {t('bi.budget.sharePack')}
              </button>
              <button
                type="button"
                className={toolbarBtn}
                disabled={!enabled || items.length < 2}
                onClick={() => {
                  setTransferFrom(items[0]?.id || '');
                  setTransferTo(items[1]?.id || '');
                  setTransferAmount(0);
                  setTransferOpen(true);
                }}
              >
                <ArrowLeftRight className="h-3.5 w-3.5 text-violet-600" />
                {t('bi.budget.transfer')}
              </button>
              <button
                type="button"
                className={toolbarBtn}
                disabled={refreshAllMut.isPending || !enabled}
                onClick={() => refreshAllMut.mutate()}
              >
                {refreshAllMut.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5 text-violet-600" />
                )}
                {t('bi.budget.refreshActuals')}
              </button>
            </ToolbarGroup>
          </div>

          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xlsm,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,text/csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = '';
              if (file) importMut.mutate(file);
            }}
          />

          <p className="mt-3 border-t border-slate-100 pt-2.5 text-[11px] leading-relaxed text-slate-500">
            {t('bi.budget.importHint')}
          </p>
        </div>
      </div>

      {narrativeQ.data?.text ? (
        <section
          className={clsx(
            'mb-4 overflow-hidden rounded-2xl border shadow-sm',
            (narrativeQ.data.over_count || 0) > 0
              ? 'border-red-200/80 bg-gradient-to-br from-red-50/90 via-white to-violet-50/40'
              : (narrativeQ.data.watch_count || 0) > 0
                ? 'border-amber-200/80 bg-gradient-to-br from-amber-50/80 via-white to-violet-50/40'
                : 'border-violet-200/70 bg-gradient-to-br from-violet-50/70 via-white to-emerald-50/30',
          )}
        >
          <div className="flex flex-wrap items-start justify-between gap-3 border-b border-white/60 px-4 py-3 sm:px-5">
            <div className="flex min-w-0 items-start gap-3">
              <span
                className={clsx(
                  'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl shadow-sm',
                  (narrativeQ.data.over_count || 0) > 0
                    ? 'bg-red-100 text-red-700'
                    : (narrativeQ.data.watch_count || 0) > 0
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-violet-100 text-violet-700',
                )}
              >
                <Sparkles className="h-4 w-4" />
              </span>
              <div className="min-w-0">
                <h2 className="text-sm font-semibold text-slate-900">{t('bi.budget.narrativeTitle')}</h2>
                <p className="mt-0.5 text-xs text-slate-500">
                  {narrativeQ.data.fiscal_year || year}
                  {' · '}
                  {scenarioFilter === 'optimistic'
                    ? t('bi.budget.scenarioOptimistic')
                    : scenarioFilter === 'pessimistic'
                      ? t('bi.budget.scenarioPessimistic')
                      : t('bi.budget.scenarioBase')}
                  {reportingCurrency ? ` · ${reportingCurrency}` : ''}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(narrativeQ.data.over_count || 0) > 0 ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-1 text-[11px] font-semibold text-red-800">
                  <AlertTriangle className="h-3 w-3" />
                  {t('bi.budget.narrativeStatusOver', { count: String(narrativeQ.data.over_count) })}
                </span>
              ) : null}
              {(narrativeQ.data.watch_count || 0) > 0 ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-semibold text-amber-900">
                  <AlertTriangle className="h-3 w-3" />
                  {t('bi.budget.narrativeStatusWatch', { count: String(narrativeQ.data.watch_count) })}
                </span>
              ) : null}
              {(narrativeQ.data.over_count || 0) === 0 && (narrativeQ.data.watch_count || 0) === 0 ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-1 text-[11px] font-semibold text-emerald-800">
                  <CheckCircle2 className="h-3 w-3" />
                  {t('bi.budget.narrativeStatusOk')}
                </span>
              ) : null}
            </div>
          </div>

          <div className="space-y-4 px-4 py-4 sm:px-5">
            {narrativeQ.data.totals ? (
              <div className="grid gap-2 sm:grid-cols-3">
                {(
                  [
                    ['allocated', t('bi.budget.kpiAllocated'), narrativeQ.data.totals.allocated],
                    ['actual', t('bi.budget.kpiActual'), narrativeQ.data.totals.actual],
                    ['remaining', t('bi.budget.kpiRemaining'), narrativeQ.data.totals.remaining],
                  ] as const
                ).map(([key, label, value]) => (
                  <div
                    key={key}
                    className="rounded-xl border border-slate-200/70 bg-white/80 px-3 py-2.5 shadow-sm"
                  >
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</p>
                    <p className="mt-0.5 text-sm font-semibold tabular-nums text-slate-900">
                      {money(value, reportingCurrency || undefined)}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}

            {(narrativeQ.data.top || []).length > 0 ? (
              <div>
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  {t('bi.budget.narrativeHighlights')}
                </p>
                <ul className="space-y-2">
                  {narrativeQ.data.top!.map((row) => {
                    const pct = Number(row.used_pct ?? 0);
                    const bar =
                      row.health === 'over'
                        ? 'bg-red-500'
                        : row.health === 'watch'
                          ? 'bg-amber-500'
                          : 'bg-violet-500';
                    const envelope = items.find((i) => i.id === row.id);
                    return (
                      <li key={String(row.id || row.name)}>
                        <button
                          type="button"
                          className="group flex w-full items-center gap-3 rounded-xl border border-slate-200/60 bg-white/70 px-3 py-2 text-left transition hover:border-violet-300 hover:bg-white"
                          disabled={!envelope}
                          onClick={() => {
                            if (envelope) openForm(envelope);
                          }}
                        >
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center justify-between gap-2">
                              <p className="truncate text-sm font-medium text-slate-800 group-hover:text-violet-900">
                                {row.name || '—'}
                              </p>
                              <span className="shrink-0 text-xs font-semibold tabular-nums text-slate-600">
                                {row.used_pct != null ? `${Math.round(pct)}%` : '—'}
                              </span>
                            </div>
                            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-slate-100">
                              <div
                                className={clsx('h-full rounded-full transition-all', bar)}
                                style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                              />
                            </div>
                          </div>
                          {row.health ? (
                            <StatusBadge status={healthStatus(row.health)} label={healthLabel(row.health)} />
                          ) : null}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ) : (
              <p className="text-sm leading-relaxed text-slate-700">{narrativeQ.data.text}</p>
            )}

            {(narrativeQ.data.over_count || 0) > 0 || (narrativeQ.data.watch_count || 0) > 0 ? (
              <div className="rounded-xl border border-violet-200/60 bg-violet-50/50 px-3 py-3">
                <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-violet-700">
                  {t('bi.budget.narrativeActions')}
                </p>
                <ul className="space-y-1.5 text-sm text-slate-700">
                  <li className="flex items-start gap-2">
                    <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-600" />
                    <span>{t('bi.budget.narrativeActionChat')}</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-600" />
                    <span>{t('bi.budget.narrativeActionAlert')}</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <Wallet className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-600" />
                    <span>{t('bi.budget.narrativeActionCommitments')}</span>
                  </li>
                </ul>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {flash && (
        <p
          className={clsx(
            'mb-3 rounded-lg border px-3 py-2 text-sm',
            flash.ok
              ? 'border-emerald-200 bg-emerald-50 text-emerald-900'
              : 'border-red-200 bg-red-50 text-red-900',
          )}
          role="status"
        >
          {flash.text}
        </p>
      )}

      {list.isError || summary.isError ? (
        <p className="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
          {localizeUserMessage(
            ((list.error || summary.error) as Error | undefined)?.message || t('bi.budget.loadError'),
          )}
        </p>
      ) : null}

      {summary.data?.mixed_currency ? (
        <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          {t('bi.budget.mixedCurrency')}
        </p>
      ) : null}
      {(summary.data?.fx_missing || []).length > 0 ? (
        <p className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-950">
          {t('bi.budget.fxMissing', { count: String(summary.data?.fx_missing?.length || 0) })}
        </p>
      ) : null}

      <div className="mb-4 flex flex-wrap items-end gap-2 rounded-lg border border-slate-100 bg-slate-50/60 p-3">
        <Field label={t('bi.budget.fxFrom')}>
          <input className="input-field max-w-[5rem]" value={fxFrom} onChange={(e) => setFxFrom(e.target.value.toUpperCase())} />
        </Field>
        <Field label={t('bi.budget.fxTo')}>
          <input className="input-field max-w-[5rem]" value={fxTo} onChange={(e) => setFxTo(e.target.value.toUpperCase())} />
        </Field>
        <Field label={t('bi.budget.fxRate')}>
          <input
            className="input-field max-w-[7rem]"
            type="number"
            step="0.0001"
            value={fxRate}
            onChange={(e) => setFxRate(Number(e.target.value))}
          />
        </Field>
        <button type="button" className="btn-secondary text-xs" disabled={fxMut.isPending} onClick={() => fxMut.mutate()}>
          {t('bi.budget.fxSave')}
        </button>
        <p className="w-full text-[11px] text-slate-500">
          {t('bi.budget.fxHint', { count: String(fxQ.data?.rates?.length || 0) })}
        </p>
      </div>

      <section className="mb-4 overflow-hidden rounded-2xl border border-slate-200/80 bg-gradient-to-br from-slate-50/80 via-white to-violet-50/30 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100/80 px-4 py-3 sm:px-5">
          <div className="flex min-w-0 items-start gap-3">
            <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-violet-100 text-violet-700 shadow-sm">
              <Network className="h-4 w-4" />
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-slate-900">{t('bi.budget.sectionCostCenters')}</h2>
              <p className="mt-0.5 text-xs text-slate-500">
                {t('bi.budget.costCenterCount', { count: String(costCenterOptions.length) })}
                {(rollupQ.data?.unassigned_count || 0) > 0
                  ? ` · ${t('bi.budget.unassignedCcCount', { count: String(rollupQ.data?.unassigned_count) })}`
                  : ''}
              </p>
            </div>
          </div>
          <button
            type="button"
            className={clsx(
              'inline-flex min-h-9 items-center gap-1.5 rounded-xl border px-3 py-1.5 text-xs font-medium shadow-sm transition',
              showRollup
                ? 'border-violet-300 bg-violet-50 text-violet-900'
                : 'border-slate-200 bg-white text-slate-700 hover:border-violet-300 hover:bg-violet-50/70',
            )}
            onClick={() => setShowRollup((v) => !v)}
          >
            {showRollup ? t('bi.budget.hideRollup') : t('bi.budget.showRollup')}
          </button>
        </div>

        <div className="space-y-4 px-4 py-4 sm:px-5">
          <div className="rounded-xl border border-slate-200/70 bg-white/80 p-3 shadow-sm sm:p-4">
            <p className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              {t('bi.budget.costCenterAdd')}
            </p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,8rem)_minmax(0,1fr)_minmax(0,14rem)_auto] lg:items-end">
              <Field label={t('bi.budget.costCenterCode')}>
                <input
                  className="input-field"
                  value={ccCode}
                  onChange={(e) => setCcCode(e.target.value)}
                />
              </Field>
              <Field label={t('bi.budget.costCenterName')}>
                <input
                  className="input-field"
                  value={ccName}
                  onChange={(e) => setCcName(e.target.value)}
                />
              </Field>
              <Field label={t('bi.budget.costCenterParent')}>
                <select className="input-field" value={ccParent} onChange={(e) => setCcParent(e.target.value)}>
                  <option value="">{t('bi.budget.costCenterRoot')}</option>
                  {costCenterTreeOptions.map((c) => (
                    <option key={c.id} value={c.id}>
                      {'\u00A0'.repeat(c.depth * 2)}
                      {c.code} — {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <button
                type="button"
                className="btn-primary w-full min-h-10 text-sm lg:w-auto"
                disabled={saveCcMut.isPending || !ccCode.trim() || !ccName.trim()}
                onClick={() => saveCcMut.mutate()}
              >
                {saveCcMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
                {t('bi.budget.costCenterAdd')}
              </button>
            </div>
          </div>

          {showRollup ? (
            <div className="overflow-hidden rounded-xl border border-slate-200/70 bg-white shadow-sm">
              {(rollupQ.data?.flat || []).length === 0 && !(rollupQ.data?.unassigned_count || 0) ? (
                <p className="px-4 py-6 text-center text-sm text-slate-500">{t('bi.budget.rollupEmpty')}</p>
              ) : (
                <div className="max-h-72 overflow-auto">
                  <table className="min-w-full text-sm">
                    <thead className="sticky top-0 z-10 bg-slate-50/95 text-[10px] font-semibold uppercase tracking-wider text-slate-500 backdrop-blur">
                      <tr>
                        <th className="px-3 py-2.5 text-left">{t('bi.budget.costCenter')}</th>
                        <th className="px-3 py-2.5 text-right">{t('bi.budget.allocated')}</th>
                        <th className="px-3 py-2.5 text-right">{t('bi.budget.actual')}</th>
                        <th className="px-3 py-2.5 text-right">{t('bi.budget.remaining')}</th>
                        <th className="hidden px-3 py-2.5 text-right sm:table-cell">{t('bi.budget.usedPct')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(rollupQ.data?.flat || []).map((n) => {
                        const depth = Number(n.depth || 0);
                        const allocated = Number(n.allocated || 0);
                        const actual = Number(n.actual || 0);
                        const pct = allocated > 0 ? Math.round((actual / allocated) * 100) : null;
                        const bar =
                          pct == null
                            ? 'bg-slate-300'
                            : pct >= 100
                              ? 'bg-red-500'
                              : pct >= 80
                                ? 'bg-amber-500'
                                : 'bg-emerald-500';
                        return (
                          <tr
                            key={String(n.id)}
                            className="border-t border-slate-100 transition hover:bg-violet-50/40"
                          >
                            <td className="px-3 py-2.5">
                              <div style={{ paddingLeft: depth * 14 }} className="flex min-w-0 items-center gap-2">
                                <span
                                  className={clsx(
                                    'flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[10px] font-bold',
                                    depth === 0
                                      ? 'bg-violet-100 text-violet-700'
                                      : 'bg-slate-100 text-slate-500',
                                  )}
                                >
                                  {String(n.code || '?').slice(0, 3).toUpperCase()}
                                </span>
                                <div className="min-w-0">
                                  <p className="truncate font-medium text-slate-800">{String(n.name || '')}</p>
                                  <p className="truncate text-[11px] text-slate-400">{String(n.code || '')}</p>
                                </div>
                              </div>
                            </td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-slate-700">
                              {money(n.allocated as number, reportingCurrency || undefined)}
                            </td>
                            <td className="px-3 py-2.5 text-right tabular-nums text-slate-700">
                              {money(n.actual as number, reportingCurrency || undefined)}
                            </td>
                            <td className="px-3 py-2.5 text-right tabular-nums font-medium text-slate-900">
                              {money(n.remaining as number, reportingCurrency || undefined)}
                            </td>
                            <td className="hidden px-3 py-2.5 text-right sm:table-cell">
                              {pct == null ? (
                                <span className="text-slate-400">—</span>
                              ) : (
                                <div className="ml-auto w-16">
                                  <p className="text-[11px] font-semibold tabular-nums text-slate-600">{pct}%</p>
                                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                                    <div
                                      className={clsx('h-full rounded-full', bar)}
                                      style={{ width: `${Math.min(100, pct)}%` }}
                                    />
                                  </div>
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                      {(rollupQ.data?.unassigned_count || 0) > 0 ? (
                        <tr className="border-t border-amber-200/80 bg-amber-50/70">
                          <td className="px-3 py-2.5">
                            <div className="flex min-w-0 items-center gap-2">
                              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-amber-200/80 text-[10px] font-bold text-amber-900">
                                ?
                              </span>
                              <div className="min-w-0">
                                <p className="font-medium text-amber-950">{t('bi.budget.unassignedCc')}</p>
                                <p className="text-[11px] text-amber-800/80">
                                  {t('bi.budget.unassignedCcCount', {
                                    count: String(rollupQ.data?.unassigned_count),
                                  })}
                                </p>
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-amber-950">
                            {money(rollupQ.data?.unassigned?.allocated, reportingCurrency || undefined)}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums text-amber-950">
                            {money(rollupQ.data?.unassigned?.actual, reportingCurrency || undefined)}
                          </td>
                          <td className="px-3 py-2.5 text-right tabular-nums font-medium text-amber-950">
                            {money(rollupQ.data?.unassigned?.remaining, reportingCurrency || undefined)}
                          </td>
                          <td className="hidden px-3 py-2.5 sm:table-cell" />
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ) : null}
        </div>
      </section>

      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card border-l-4 border-l-slate-300 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('bi.budget.kpiAllocated')}</p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
            {money(totals?.allocated, reportingCurrency || undefined)}
          </p>
        </div>
        <div className="card border-l-4 border-l-sky-400 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('bi.budget.kpiActual')}</p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
            {money(totals?.actual, reportingCurrency || undefined)}
          </p>
        </div>
        <div className="card border-l-4 border-l-emerald-400 p-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('bi.budget.kpiRemaining')}</p>
          <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900">
            {money(totals?.remaining, reportingCurrency || undefined)}
          </p>
        </div>
        <div
          className={clsx(
            'card border-l-4 p-4',
            watchCount > 0 ? 'border-l-amber-500 bg-amber-50/40' : 'border-l-emerald-500',
          )}
        >
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{t('bi.budget.kpiWatch')}</p>
          <p
            className={clsx(
              'mt-1 text-lg font-semibold tabular-nums',
              watchCount > 0 ? 'text-amber-900' : 'text-emerald-800',
            )}
          >
            {watchCount}
          </p>
          <p className="mt-1 text-[11px] text-slate-500">
            {t('bi.budget.kindOpex')} {money(opex?.remaining, reportingCurrency || undefined)} ·{' '}
            {t('bi.budget.kindCapex')} {money(capex?.remaining, reportingCurrency || undefined)}
          </p>
        </div>
      </div>

      {(relatedTablesQ.data?.tables?.length ?? 0) > 0 && (
        <div className="rounded-2xl border border-violet-200/70 bg-gradient-to-br from-violet-50/80 via-white to-indigo-50/50 p-4 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div>
              <p className="text-sm font-semibold text-violet-950">{t('bi.budget.relatedTablesTitle')}</p>
              <p className="mt-0.5 text-xs text-slate-600">{t('bi.budget.relatedTablesHint')}</p>
            </div>
            {relatedTablesQ.isFetching ? <Loader2 className="h-4 w-4 animate-spin text-violet-500" /> : null}
          </div>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {(relatedTablesQ.data?.tables || []).map((row) => (
              <li
                key={row.table}
                className="rounded-xl border border-violet-100/80 bg-white/90 px-3 py-2.5 shadow-sm"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900" title={row.table}>
                      {row.table_name}
                    </p>
                    <p className="mt-0.5 truncate text-[11px] text-slate-500">
                      {row.suggested_measure
                        ? t('bi.budget.relatedTablesMeasure', { measure: row.suggested_measure })
                        : t('bi.budget.relatedTablesNoMeasure')}
                    </p>
                  </div>
                  {row.suggested_sql ? (
                    <button
                      type="button"
                      className="shrink-0 rounded-lg border border-violet-200 bg-violet-50 px-2 py-1 text-[11px] font-medium text-violet-800 hover:bg-violet-100"
                      title={t('bi.budget.relatedTablesUseSql')}
                      onClick={() => {
                        openForm({
                          ...emptyForm(year),
                          name: t('bi.budget.relatedTablesDefaultName', { table: row.table_name }),
                          actuals_sql: row.suggested_sql,
                        });
                      }}
                    >
                      {t('bi.budget.relatedTablesUse')}
                    </button>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div
        className={clsx(
          'grid gap-4 items-start',
          form ? 'xl:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]' : 'grid-cols-1',
        )}
      >
        <div className={clsx('min-w-0', form ? 'order-2 xl:order-1' : undefined)}>
          {!items.length && !list.isLoading ? (
            <EmptyState
              emoji="💼"
              titleKey="empty.bi.budget.title"
              descriptionKey="empty.bi.budget.description"
              ctaLabelKey="empty.bi.budget.cta"
              onCtaClick={() => openForm(emptyForm(year))}
            />
          ) : (
            <ResponsiveTable<BiBudgetEnvelope>
              columns={[
                {
                  id: 'name',
                  header: t('bi.budget.name'),
                  mobilePrimary: true,
                  className: 'min-w-[12rem] max-w-[18rem]',
                  cell: (r) => (
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900">{r.name}</p>
                      <p className="text-[11px] text-slate-500">
                        {r.cost_center || '—'} ·{' '}
                        {(() => {
                          const kind = String(r.kind || '').toLowerCase();
                          if (kind === 'opex') return t('bi.budget.kindOpexShort');
                          if (kind === 'capex') return t('bi.budget.kindCapexShort');
                          return t('bi.budget.kindOtherShort');
                        })()}
                      </p>
                    </div>
                  ),
                },
                {
                  id: 'allocated',
                  header: t('bi.budget.allocated'),
                  headerClassName: 'text-right',
                  className: 'whitespace-nowrap text-right tabular-nums',
                  cell: (r) => money(r.allocated, r.currency),
                },
                {
                  id: 'actual',
                  header: t('bi.budget.actual'),
                  headerClassName: 'text-right',
                  className: 'whitespace-nowrap text-right tabular-nums',
                  cell: (r) =>
                    r.actual_error ? (
                      <span className="text-xs text-status-fail" title={r.actual_error}>
                        {t('bi.budget.actualError')}
                      </span>
                    ) : (
                      money(r.actual, r.currency)
                    ),
                },
                {
                  id: 'remaining',
                  header: t('bi.budget.remaining'),
                  headerClassName: 'text-right',
                  className: 'whitespace-nowrap text-right',
                  cell: (r) => (
                    <div className="inline-flex flex-col items-end gap-1">
                      <span className="tabular-nums font-medium text-slate-900">
                        {money(r.remaining, r.currency)}
                      </span>
                      <div className="flex flex-wrap items-center justify-end gap-1.5">
                        {r.health ? (
                          <StatusBadge status={healthStatus(r.health)} label={healthLabel(r.health)} />
                        ) : null}
                        {r.runway_days != null ? (
                          <span className="text-[11px] text-slate-500">
                            {t('bi.budget.runwayDays')}: {r.runway_days}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  ),
                },
                {
                  id: 'used',
                  header: t('bi.budget.usedPct'),
                  headerClassName: 'text-right',
                  className: 'whitespace-nowrap text-right',
                  cell: (r) => {
                    const pct = r.used_pct;
                    const bar =
                      r.health === 'over'
                        ? 'bg-red-500'
                        : r.health === 'watch'
                          ? 'bg-amber-500'
                          : r.health === 'ok'
                            ? 'bg-emerald-500'
                            : 'bg-slate-300';
                    return (
                      <div className="inline-block w-[5.5rem] text-left">
                        <p className="tabular-nums text-xs font-medium text-slate-700">
                          {formatUsedPct(r.used_pct)}
                        </p>
                        {pct != null ? (
                          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
                            <div
                              className={clsx('h-full rounded-full', bar)}
                              style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
                            />
                          </div>
                        ) : null}
                      </div>
                    );
                  },
                },
                {
                  id: 'status',
                  header: t('bi.budget.status'),
                  className: 'whitespace-nowrap',
                  cell: (r) => (
                    <StatusBadge
                      status={r.status === 'approved' ? 'ok' : r.status === 'closed' ? 'neutral' : 'warn'}
                      label={statusLabel(r.status)}
                    />
                  ),
                },
                {
                  id: 'actions',
                  header: t('common.actions'),
                  mobileLabel: t('common.actions'),
                  className: 'min-w-[14rem]',
                  cell: (r) => {
                    const whyPrompt =
                      r.ask_prompt ||
                      t('bi.budget.askWhyDefault', {
                        name: r.name || r.id,
                        year: String(r.fiscal_year || year),
                      });
                    return (
                      <div className="flex flex-wrap gap-1">
                        <button
                          type="button"
                          className="inline-flex min-h-9 items-center rounded-lg px-2 text-xs font-medium text-violet-700 hover:bg-violet-50"
                          onClick={(e) => {
                            e.stopPropagation();
                            openForm({ ...r });
                          }}
                        >
                          {t('common.edit')}
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openChat({ prompt: whyPrompt });
                          }}
                          className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 text-xs font-medium text-indigo-700 hover:bg-indigo-50"
                          title={r.ask_prompt ? undefined : t('bi.budget.askWhyUnavailable')}
                        >
                          <MessageSquare className="h-3 w-3" />
                          {t('bi.budget.askWhy')}
                        </button>
                        <button
                          type="button"
                          className="inline-flex min-h-9 items-center rounded-lg px-2 text-xs font-medium text-amber-800 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-40"
                          disabled={createAlertMut.isPending || !String(r.actuals_sql || '').trim()}
                          title={
                            String(r.actuals_sql || '').trim()
                              ? t('bi.budget.createAlertHint')
                              : t('bi.budget.createAlertNeedsSql')
                          }
                          onClick={(e) => {
                            e.stopPropagation();
                            createAlertMut.mutate(r.id);
                          }}
                        >
                          {t('bi.budget.createAlert')}
                        </button>
                        <button
                          type="button"
                          className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 text-xs font-medium text-sky-700 hover:bg-sky-50 disabled:opacity-40"
                          disabled={refreshOneMut.isPending}
                          onClick={(e) => {
                            e.stopPropagation();
                            refreshOneMut.mutate(r.id);
                          }}
                        >
                          {refreshOneMut.isPending ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : null}
                          {t('bi.budget.refreshOne')}
                        </button>
                        <button
                          type="button"
                          className="inline-flex min-h-9 items-center rounded-lg px-2 text-xs text-status-fail hover:bg-red-50 disabled:opacity-40"
                          disabled={Boolean(r.locked) || delMut.isPending}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (window.confirm(t('bi.budget.deleteConfirm'))) delMut.mutate(r.id);
                          }}
                        >
                          <Trash2 className="mr-0.5 h-3 w-3" />
                          {t('common.delete')}
                        </button>
                      </div>
                    );
                  },
                },
              ]}
              rows={items}
              rowKey={(r) => r.id}
            />
          )}

          <p className="mt-4 flex items-center gap-2 text-xs text-slate-500">
            <Wallet className="h-3.5 w-3.5 shrink-0" />
            <span>{t('bi.budget.footerHint')}</span>
          </p>
        </div>

        {formPanel ? (
          <div className="order-1 min-w-0 xl:order-2 xl:sticky xl:top-4">{formPanel}</div>
        ) : null}
      </div>

      {transferOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="card w-full max-w-md space-y-3 p-4">
            <h3 className="text-sm font-semibold text-slate-900">{t('bi.budget.transfer')}</h3>
            <Field label={t('bi.budget.transferFrom')}>
              <select className="input-field" value={transferFrom} onChange={(e) => setTransferFrom(e.target.value)}>
                {items.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t('bi.budget.transferTo')}>
              <select className="input-field" value={transferTo} onChange={(e) => setTransferTo(e.target.value)}>
                {items.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t('bi.budget.transferAmount')}>
              <input
                className="input-field"
                type="number"
                value={transferAmount}
                onChange={(e) => setTransferAmount(Number(e.target.value))}
              />
            </Field>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-primary"
                disabled={transferMut.isPending || !transferAmount}
                onClick={() => transferMut.mutate()}
              >
                {t('bi.budget.transferConfirm')}
              </button>
              <button type="button" className="btn-secondary" onClick={() => setTransferOpen(false)}>
                {t('common.cancel')}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </PageShell>
  );
}
