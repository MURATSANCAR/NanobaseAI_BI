import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { BookOpen, Calculator, KeyRound, Link2, RefreshCw, Search, ShieldCheck, Table2 } from 'lucide-react';
import ApiErrorBanner from '@/components/ApiErrorBanner';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import { api, isRunnerConfigured } from '@/api/client';
import type { BiSemanticLayerGaps, BiSlColumn, BiSlConcept, BiSlTable } from '@/api/bi-types';
import { useApiConfig } from '@/context/ApiContext';
import { t } from '@/i18n';

const STATUS_STYLE: Record<string, string> = {
  CERTIFIED: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  CANDIDATE: 'bg-amber-100 text-amber-800 border-amber-200',
  DESCRIBED: 'bg-sky-100 text-sky-800 border-sky-200',
  UNDEFINED: 'bg-slate-100 text-slate-600 border-slate-200',
  SENSE_CONFLICT: 'bg-rose-100 text-rose-800 border-rose-200',
  DEPRECATED: 'bg-slate-200 text-slate-700 border-slate-300',
  REJECTED: 'bg-slate-100 text-slate-500 border-slate-200',
};

function statusLabel(s: string): string {
  switch (s) {
    case 'CERTIFIED':
      return t('bi.sl.certified');
    case 'CANDIDATE':
      return t('bi.sl.candidate');
    case 'DESCRIBED':
      return t('bi.sl.described');
    case 'SENSE_CONFLICT':
      return t('bi.sl.conflict');
    case 'DEPRECATED':
      return t('bi.sl.deprecated');
    default:
      return t('bi.sl.undefined');
  }
}

function StatusChip({ status }: { status: string }) {
  return (
    <span className={clsx('inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-semibold', STATUS_STYLE[status] ?? STATUS_STYLE.UNDEFINED)}>
      {statusLabel(status)}
    </span>
  );
}

function AnnotationForm({
  placeholder,
  onSave,
  busy,
}: {
  placeholder: string;
  onSave: (text: string) => void;
  busy: boolean;
}) {
  const [text, setText] = useState('');
  return (
    <form
      className="mt-2 flex flex-col gap-2 sm:flex-row"
      onSubmit={(e) => {
        e.preventDefault();
        if (!text.trim()) return;
        onSave(text.trim());
        setText('');
      }}
    >
      <input
        className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-violet-400 focus:outline-none"
        placeholder={placeholder}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={busy}
      />
      <button
        type="submit"
        disabled={busy || !text.trim()}
        className="rounded-lg bg-violet-600 px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
      >
        {t('bi.sl.save')}
      </button>
    </form>
  );
}

function ColumnRow({
  table,
  col,
  onAnnotate,
  onRetire,
  busy,
}: {
  table: BiSlTable;
  col: BiSlColumn;
  onAnnotate: (tablePattern: string, column: string | null, text: string) => void;
  onRetire: (id: string) => void;
  busy: boolean;
}) {
  const [open, setOpen] = useState(false);
  const certified = col.concepts.filter((c) => c.status === 'CERTIFIED');
  const candidates = col.concepts.filter((c) => c.status !== 'CERTIFIED' && c.status !== 'REJECTED');
  return (
    <li className={clsx('rounded-xl border px-3 py-2', col.status === 'UNDEFINED' ? 'border-dashed border-slate-300 bg-white/50' : 'border-slate-200 bg-white/80')}>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="font-mono text-sm font-semibold text-slate-800 hover:underline" onClick={() => setOpen((v) => !v)}>
          {col.name}
        </button>
        <span className="text-xs text-slate-500">{col.type}</span>
        {col.isPrimaryKey ? <KeyRound className="h-3.5 w-3.5 text-amber-600" aria-label={t('bi.sl.pk')} /> : null}
        {col.ref ? (
          <span className="inline-flex items-center gap-1 text-xs text-violet-700">
            <Link2 className="h-3 w-3" /> {col.ref}
          </span>
        ) : null}
        <StatusChip status={col.status} />
        {certified.map((c) => (
          <span key={c.id} className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-xs text-emerald-800" title={c.formula ?? `${c.operator ?? ''} ${(c.values ?? []).join(', ')}`}>
            “{c.term}” {c.values?.length ? `→ ${c.values.join(', ')}` : c.formula ? '→ ƒ' : ''}
          </span>
        ))}
        {candidates.slice(0, 3).map((c) => (
          <span key={c.id} className="rounded-md bg-amber-50 px-1.5 py-0.5 text-xs text-amber-800" title={`${c.status} ${c.formula ?? (c.values ?? []).join(', ')}`}>
            “{c.term}”?
          </span>
        ))}
      </div>
      {col.description ? (
        <p className="mt-1 flex items-start gap-2 text-xs text-slate-600">
          <span className="mt-px rounded bg-slate-100 px-1 text-[10px] text-slate-500">{t('bi.sl.fromSource')}</span>
          <span className="flex-1">{col.description}</span>
        </p>
      ) : null}
      {(col.derived ?? []).map((d, i) => (
        <p key={`d${i}`} className="mt-1 flex items-start gap-2 text-xs text-slate-500">
          <span className="mt-px rounded bg-indigo-50 px-1 text-[10px] text-indigo-600">{t('bi.sl.fromData')}</span>
          <span className="flex-1">{d}</span>
        </p>
      ))}
      {col.annotations.map((a) => (
        <p key={a.id} className="mt-1 flex items-start gap-2 text-xs text-slate-700">
          <BookOpen className="mt-0.5 h-3 w-3 shrink-0 text-sky-600" />
          <span className="flex-1">
            {a.text} <span className="text-slate-400">— {a.author}</span>
          </span>
          <button type="button" className="text-slate-400 hover:text-rose-600" onClick={() => onRetire(a.id)} disabled={busy}>
            {t('bi.sl.retire')}
          </button>
        </p>
      ))}
      {open ? (
        <div className="mt-2 space-y-2 border-t border-slate-100 pt-2">
          {col.topValues && col.topValues.length > 0 ? (
            <p className="text-xs text-slate-600">
              <span className="font-semibold">{t('bi.sl.topValues')}:</span>{' '}
              {col.topValues.map(([v, n]) => (
                <span key={v} className="mr-1 inline-block rounded bg-slate-100 px-1 font-mono">
                  {v}
                  {n ? <span className="text-slate-400">×{n}</span> : null}
                </span>
              ))}
              {col.distinct != null ? <span className="text-slate-400"> · {col.distinct} distinct</span> : null}
            </p>
          ) : null}
          <AnnotationForm placeholder={t('bi.sl.annotatePlaceholder')} onSave={(text) => onAnnotate(table.tablePattern, col.name, text)} busy={busy} />
        </div>
      ) : null}
    </li>
  );
}

/** Sertifikalı ölçüler ve her zaman uygulanan varsayılan filtreler — sohbetin arkasındaki sözleşme.
 *  Ölçü = formül + kapsam; varsayılan filtre = o varlığa her sorguda eklenen koşul. */
function GapsSection({ data }: { data?: BiSemanticLayerGaps }) {
  const [open, setOpen] = useState(true);
  const gaps = data?.gaps ?? [];
  if (!data || (gaps.length === 0 && (data.unmeasuredWindows?.length ?? 0) === 0)) return null;
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4">
      <button type="button" className="flex w-full items-center justify-between text-left" onClick={() => setOpen((v) => !v)}>
        <h2 className="text-sm font-semibold text-slate-800">
          {t('bi.sl.gapsTitle')} <span className="ml-2 font-normal text-slate-500">{t('bi.sl.gapsWindow', { d: String(data.days) })}</span>
        </h2>
        <span className="text-xs text-slate-500">{gaps.length}</span>
      </button>
      {open ? (
        <>
          <p className="mt-1 text-xs text-slate-500">{t('bi.sl.gapsNote')}</p>
          {data.unmeasuredWindows?.length ? (
            <p className="mt-2 rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-800">
              {t('bi.sl.gapsUnmeasured', { e: data.unmeasuredWindows.join(', ') })}
            </p>
          ) : null}
          <ul className="mt-3 space-y-2">
            {gaps.map((g) => (
              <li key={`${g.kind}:${g.term}`} className="rounded-lg border border-slate-200 px-3 py-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className={`rounded px-1.5 py-0.5 text-[11px] ${g.kind === 'qualifier' ? 'bg-violet-100 text-violet-700' : 'bg-rose-100 text-rose-700'}`}>
                    {g.kind === 'qualifier' ? t('bi.sl.gapQualifier') : t('bi.sl.gapUndefined')}
                  </span>
                  <span className="font-medium text-slate-800">{g.term}</span>
                  <span className="text-xs text-slate-500">×{g.count}</span>
                </div>
                {g.questions?.length ? (
                  <div className="mt-1 space-y-0.5 text-xs text-slate-500">
                    {g.questions.map((q, i) => <div key={i}>“{q}”</div>)}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function CatalogSection({ items }: { items: BiSlConcept[] }) {
  const [open, setOpen] = useState(true);
  const metrics = items.filter((x) => x.concept.semantic_type === 'METRIC');
  const filters = items.filter((x) => x.concept.semantic_type === 'DEFAULT_FILTER');
  const values = items.filter((x) => x.concept.semantic_type === 'DIMENSION_VALUE');
  if (items.length === 0) return null;
  const target = (m: BiSlConcept['mappings'][number]) =>
    m.formula ?? `${m.entity}.${m.column ?? ''}${m.values?.length ? ` ${m.operator ?? 'IN'} (${m.values.join(', ')})` : ''}`;
  return (
    <section className="rounded-2xl border border-white/70 bg-white/70 p-3">
      <button type="button" className="flex w-full items-center gap-2 text-left" onClick={() => setOpen((v) => !v)}>
        <Calculator className="h-4 w-4 text-violet-600" />
        <h2 className="text-sm font-semibold text-slate-800">{t('bi.sl.catalogTitle')}</h2>
        <span className="text-xs text-slate-500">
          {metrics.length} ölçü · {values.length} değer · {filters.length} varsayılan filtre
        </span>
      </button>
      {open ? (
        <div className="mt-2 grid gap-3 md:grid-cols-2">
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t('bi.sl.metrics')}</h3>
            <ul className="mt-1 space-y-1">
              {metrics.map((x) => (
                <li key={x.concept.id} className="rounded-lg border border-emerald-200 bg-emerald-50/60 px-2 py-1 text-xs">
                  <span className="font-semibold text-slate-800">{x.concept.term}</span>
                  {x.concept.synonyms.length > 0 ? (
                    <span className="ml-1 text-slate-500">({x.concept.synonyms.join(', ')})</span>
                  ) : null}
                  <div className="mt-0.5 break-all font-mono text-[11px] text-slate-700">{x.mappings.map(target).join(' | ')}</div>
                  {x.mappings.some((m) => (m.extra as { conditions?: string[] } | undefined)?.conditions?.length) ? (
                    <div className="text-[11px] text-slate-500">
                      {t('bi.sl.scope')}: {x.mappings.flatMap((m) => ((m.extra as { conditions?: string[] } | undefined)?.conditions ?? [])).join('; ')}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
          <div className="space-y-3">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t('bi.sl.defaultFilters')}</h3>
              <ul className="mt-1 space-y-1">
                {filters.map((x) => (
                  <li key={x.concept.id} className="rounded-lg border border-slate-200 bg-white px-2 py-1 font-mono text-[11px] text-slate-700">
                    {x.mappings.map(target).join(' | ')}
                  </li>
                ))}
                {filters.length === 0 ? <li className="text-xs text-slate-500">—</li> : null}
              </ul>
            </div>
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t('bi.sl.values')}</h3>
              <ul className="mt-1 flex flex-wrap gap-1">
                {values.map((x) => (
                  <li key={x.concept.id} className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-800" title={x.mappings.map(target).join(' | ')}>
                    {x.concept.term} → {x.mappings[0]?.values?.join(', ')}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

export default function BiSemanticLayerPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [onlyUndefined, setOnlyUndefined] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const [explainTerm, setExplainTerm] = useState('');
  const [explainQuery, setExplainQuery] = useState('');
  const enabled = isRunnerConfigured(config);

  const sourcesQ = useQuery({ queryKey: ['bi-sources', config], queryFn: () => api.bi.sources.list(config), enabled, staleTime: 30_000 });
  const datasourceId = sourcesQ.data?.active_id || sourcesQ.data?.sources?.[0]?.id || undefined;

  const statusQ = useQuery({ queryKey: ['bi-sl-status', datasourceId, config], queryFn: () => api.bi.semanticLayer.status(config, datasourceId), enabled });
  const invQ = useQuery({ queryKey: ['bi-sl-inventory', datasourceId, config], queryFn: () => api.bi.semanticLayer.inventory(config, datasourceId), enabled });
  const conceptsQ = useQuery({
    queryKey: ['bi-sl-concepts', datasourceId, config],
    queryFn: () => api.bi.semanticLayer.concepts(config, { datasource_id: datasourceId, status: 'CERTIFIED' }),
    enabled,
  });
  const gapsQ = useQuery({
    queryKey: ['bi-sl-gaps', datasourceId, config],
    queryFn: () => api.bi.semanticLayer.gaps(config, datasourceId),
    enabled,
    staleTime: 60_000,
  });
  const explainQ = useQuery({
    queryKey: ['bi-sl-explain', explainQuery, datasourceId, config],
    queryFn: () => api.bi.semanticLayer.explain(config, explainQuery, datasourceId),
    enabled: enabled && explainQuery.length > 1,
  });

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['bi-sl-inventory'] });
    void qc.invalidateQueries({ queryKey: ['bi-sl-status'] });
    void qc.invalidateQueries({ queryKey: ['bi-sl-gaps'] });
  };

  const annotateMut = useMutation({
    mutationFn: (body: { tablePattern: string; column: string | null; text: string }) =>
      api.bi.semanticLayer.addAnnotation(config, { datasource_id: datasourceId, ...body }),
    onSuccess: (r) => {
      setErr(null);
      setMsg(t('bi.sl.saved', { n: String((r.candidates?.created ?? 0) + (r.candidates?.evidence ?? 0)) }));
      invalidate();
    },
    onError: (e: Error) => setErr(e),
  });
  const retireMut = useMutation({
    mutationFn: (id: string) => api.bi.semanticLayer.retireAnnotation(config, id, datasourceId),
    onSuccess: () => invalidate(),
    onError: (e: Error) => setErr(e),
  });
  const certifyMut = useMutation({
    mutationFn: () => api.bi.semanticLayer.certifyRun(config, datasourceId),
    onSuccess: (r) => {
      const rep = (r.report ?? {}) as { certified?: number; catalog_version?: number };
      setMsg(t('bi.sl.certifyDone', { c: String(rep.certified ?? 0), v: String(rep.catalog_version ?? '') }));
      invalidate();
    },
    onError: (e: Error) => setErr(e),
  });
  const pipelineMut = useMutation({
    mutationFn: () => api.bi.semanticLayer.pipeline(config, { datasource_id: datasourceId }),
    onSuccess: (r) => {
      const rep = (r.report ?? {}) as { certify?: { certified?: number; catalog_version?: number } };
      setMsg(t('bi.sl.pipelineDone', { c: String(rep.certify?.certified ?? 0), v: String(rep.certify?.catalog_version ?? '') }));
      invalidate();
    },
    onError: (e: Error) => setErr(e),
  });

  const busy = annotateMut.isPending || retireMut.isPending || certifyMut.isPending || pipelineMut.isPending;
  const q = search.trim().toLowerCase();
  const tables = useMemo(() => {
    const all = invQ.data?.tables ?? [];
    return all
      .map((tbl) => {
        let cols = tbl.columns;
        if (onlyUndefined) cols = cols.filter((c) => c.status === 'UNDEFINED');
        if (q) {
          const tableHit = tbl.tableName.toLowerCase().includes(q) || tbl.entity.toLowerCase().includes(q);
          cols = tableHit ? cols : cols.filter((c) => c.name.toLowerCase().includes(q) || c.concepts.some((x) => x.term.toLowerCase().includes(q)) || (c.description ?? '').toLowerCase().includes(q));
        }
        return { ...tbl, columns: cols };
      })
      .filter((tbl) => tbl.columns.length > 0 || (!q && !onlyUndefined));
  }, [invQ.data, onlyUndefined, q]);

  const status = statusQ.data;
  return (
    <PageShell pageId="biSchema" titleKey="bi.sl.title" subtitleKey="bi.sl.subtitle" maxWidth="max-w-7xl">
      <ApiErrorBanner error={err ?? invQ.error ?? statusQ.error} />
      {msg ? <p className="rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{msg}</p> : null}

      <section className="grid gap-3 md:grid-cols-4">
        {(['CERTIFIED', 'CANDIDATE', 'SENSE_CONFLICT', 'DEPRECATED'] as const).map((k) => (
          <div key={k} className="rounded-2xl border border-white/70 bg-white/70 p-3 shadow-sm">
            <div className="text-2xl font-semibold text-slate-800">{status?.status?.[k] ?? 0}</div>
            <div className="mt-1">
              <StatusChip status={k} />
            </div>
          </div>
        ))}
      </section>
      <section className="flex flex-wrap items-center gap-3 rounded-2xl border border-white/70 bg-white/70 p-3 text-xs text-slate-600">
        <ShieldCheck className="h-4 w-4 text-emerald-600" />
        <span>
          {t('bi.sl.version')}: {status?.version ? `v${status.version.version} · ${status.version.certified_count}` : t('bi.sl.noVersion')}
        </span>
        <span>·</span>
        <span>{t('bi.sl.queries', { t: String(status?.queries?.total ?? 0), v: String(status?.queries?.validated ?? 0), d: String(status?.queries?.deterministic ?? 0) })}</span>
        <span className="flex-1" />
        <button type="button" onClick={() => certifyMut.mutate()} disabled={busy || !enabled} className="rounded-lg border border-violet-300 bg-white px-3 py-1.5 text-xs font-semibold text-violet-700 disabled:opacity-50">
          {certifyMut.isPending ? t('bi.sl.running') : t('bi.sl.runCertify')}
        </button>
        <button type="button" onClick={() => pipelineMut.mutate()} disabled={busy || !enabled} className="inline-flex items-center gap-1 rounded-lg bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50">
          <RefreshCw className={clsx('h-3.5 w-3.5', pipelineMut.isPending && 'animate-spin')} /> {pipelineMut.isPending ? t('bi.sl.running') : t('bi.sl.runPipeline')}
        </button>
      </section>
      {status?.unresolved && Object.keys(status.unresolved).length > 0 ? (
        <section className="rounded-2xl border border-amber-200 bg-amber-50/70 p-3 text-xs text-amber-900">
          <span className="font-semibold">{t('bi.sl.unresolved')}:</span>{' '}
          {Object.entries(status.unresolved).map(([term, n]) => (
            <button key={term} type="button" className="mr-1 rounded bg-white px-1.5 py-0.5 font-mono hover:bg-amber-100" onClick={() => { setExplainTerm(term); setExplainQuery(term); }}>
              {term} ×{n}
            </button>
          ))}
        </section>
      ) : null}

      <section className="rounded-2xl border border-white/70 bg-white/70 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-800">{t('bi.sl.explainTitle')}</h2>
          <input className="min-w-[200px] flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm" placeholder={t('bi.sl.explainPlaceholder')} value={explainTerm} onChange={(e) => setExplainTerm(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') setExplainQuery(explainTerm.trim()); }} />
          <button type="button" className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-white" onClick={() => setExplainQuery(explainTerm.trim())}>
            {t('bi.sl.explainRun')}
          </button>
        </div>
        {explainQ.data ? (
          <div className="mt-2 space-y-1 text-xs text-slate-700">
            {explainQ.data.certified.length === 0 ? <p>{t('bi.sl.noCertified')}</p> : null}
            {explainQ.data.certified.map((c) => {
              const sup = ((c.concept.explain as Record<string, unknown> | undefined)?.support ?? {}) as { validated_queries?: number; doc?: number; human?: number };
              return (
                <div key={c.concept.id} className="rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1">
                  <span className="font-semibold">“{c.concept.term}”</span> → {c.mappings.map((m) => m.formula ?? `${m.entity}.${m.column} ${m.operator ?? ''} (${m.values.join(', ')})`).join(' | ')}
                  <span className="ml-2 text-emerald-700">{t('bi.sl.support', { v: String(sup.validated_queries ?? 0), d: String(sup.doc ?? 0), h: String(sup.human ?? 0) })}</span>
                  <span className="ml-2 text-slate-400">v{c.concept.version} · {Math.round((c.concept.confidence ?? 0) * 100)}%</span>
                </div>
              );
            })}
            {explainQ.data.otherSenses.map((c) => (
              <div key={c.id} className="rounded-lg border border-amber-200 bg-amber-50 px-2 py-1">
                <StatusChip status={c.status} /> <span className="ml-1">“{c.term}” · {c.semantic_type}</span>
              </div>
            ))}
          </div>
        ) : null}
      </section>

      <GapsSection data={gapsQ.data} />

      <CatalogSection items={conceptsQ.data?.items ?? []} />

      <section className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[240px] flex-1">
          <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input className="w-full rounded-xl border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm" placeholder={t('bi.sl.search')} value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <label className="inline-flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={onlyUndefined} onChange={(e) => setOnlyUndefined(e.target.checked)} /> {t('bi.sl.onlyUndefined')}
        </label>
        <span className="text-xs text-slate-500">
          {invQ.data ? `${invQ.data.tableCount} ${t('bi.sl.tables').toLowerCase()} · ${invQ.data.columnCount} ${t('bi.sl.columns')} · ${invQ.data.undefinedColumns} ${t('bi.sl.undefinedCount')}` : null}
        </span>
      </section>
      <p className="text-xs text-slate-500">{t('bi.sl.layerNote')}</p>

      {invQ.isLoading ? null : !invQ.data || invQ.data.tables.length === 0 ? (
        <EmptyState emoji="🧭" titleKey="bi.sl.tables" descriptionKey="bi.sl.empty" />
      ) : (
        <div className="space-y-3">
          {tables.map((tbl) => (
            <article key={tbl.tablePattern} className="rounded-2xl border border-white/70 bg-white/70 p-3 shadow-sm">
              <header className="flex flex-wrap items-center gap-2">
                <Table2 className="h-4 w-4 text-violet-600" />
                <span className="font-mono text-sm font-semibold text-slate-800">{tbl.tableName}</span>
                <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">{tbl.tablePattern}</span>
                <span className="text-xs text-slate-500">
                  {tbl.columns.length} {t('bi.sl.columns')} · {tbl.undefinedColumns} {t('bi.sl.undefinedCount')}
                  {tbl.rowCount != null ? ` · ${tbl.rowCount.toLocaleString('tr-TR')} ${t('bi.sl.rows')}` : ''}
                </span>
              </header>
              {tbl.description ? <p className="mt-1 text-xs text-slate-600">{tbl.description}</p> : null}
              {tbl.annotations.map((a) => (
                <p key={a.id} className="mt-1 flex items-start gap-2 text-xs text-slate-700">
                  <BookOpen className="mt-0.5 h-3 w-3 shrink-0 text-sky-600" />
                  <span className="flex-1">
                    {a.text} <span className="text-slate-400">— {a.author}</span>
                  </span>
                  <button type="button" className="text-slate-400 hover:text-rose-600" onClick={() => retireMut.mutate(a.id)} disabled={busy}>
                    {t('bi.sl.retire')}
                  </button>
                </p>
              ))}
              <AnnotationForm placeholder={t('bi.sl.annotateTablePlaceholder')} onSave={(text) => annotateMut.mutate({ tablePattern: tbl.tablePattern, column: null, text })} busy={busy} />
              <ul className="mt-3 grid gap-2 md:grid-cols-2">
                {tbl.columns.map((col) => (
                  <ColumnRow key={col.name} table={tbl} col={col} busy={busy} onAnnotate={(tp, column, text) => annotateMut.mutate({ tablePattern: tp, column, text })} onRetire={(id) => retireMut.mutate(id)} />
                ))}
              </ul>
            </article>
          ))}
        </div>
      )}
    </PageShell>
  );
}
