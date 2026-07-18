import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Sparkles, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import ApiErrorBanner from '@/components/ApiErrorBanner';
import EmptyState from '@/components/EmptyState';
import { PageShell } from '@/components/PageShell';
import ResponsiveTable from '@/components/ResponsiveTable';
import { api, isRunnerConfigured } from '@/api/client';
import { useApiConfig } from '@/context/ApiContext';
import type { BiGlossaryEntry } from '@/api/types';
import { getLocale, t } from '@/i18n';

const emptyEntry = (): BiGlossaryEntry => ({
  id: `g-${Date.now().toString(36)}`,
  table: '',
  column: '',
  business_name: '',
  definition: '',
  synonyms: [],
  source: 'operator',
});

function entryKey(e: Pick<BiGlossaryEntry, 'table' | 'column'>) {
  return `${(e.table || '').toLowerCase().split('.').pop()}::${(e.column || '').toLowerCase()}`;
}

type DraftSuggestion = BiGlossaryEntry & { selected: boolean };

export default function BiGlossaryPage() {
  const { config } = useApiConfig();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<BiGlossaryEntry | null>(null);
  const [suggestions, setSuggestions] = useState<DraftSuggestion[] | null>(null);

  const g = useQuery({
    queryKey: ['bi-glossary', config, getLocale()],
    queryFn: () => api.bi.glossary.list(config, getLocale()),
    enabled: isRunnerConfigured(config),
  });

  const saveMut = useMutation({
    mutationFn: (entries: BiGlossaryEntry[]) => api.bi.glossary.save(config, entries),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['bi-glossary'] });
      setDraft(null);
      setSuggestions(null);
    },
  });

  const suggestMut = useMutation({
    mutationFn: () => api.bi.glossary.suggest(config, getLocale()),
    onSuccess: (data) => {
      const rows = (data.suggestions ?? []).map((s) => ({ ...s, selected: true }));
      setSuggestions(rows);
      setDraft(null);
    },
  });

  const delMut = useMutation({
    mutationFn: (id: string) => api.bi.glossary.delete(config, id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['bi-glossary'] }),
  });

  const items = g.data?.entries ?? [];
  const selectedCount = useMemo(
    () => (suggestions ?? []).filter((s) => s.selected).length,
    [suggestions],
  );

  const saveDraft = () => {
    if (!draft?.table || !draft.business_name) return;
    saveMut.mutate([
      ...items.filter((e) => e.id !== draft.id),
      { ...draft, source: draft.source || 'operator' },
    ]);
  };

  const acceptSuggestions = () => {
    if (!suggestions?.length) return;
    const accepted = suggestions
      .filter((s) => s.selected && s.table && s.business_name)
      .map(({ selected: _sel, ...rest }) => ({
        ...rest,
        source: 'llm',
        column: rest.column || undefined,
      }));
    if (!accepted.length) return;
    const acceptedKeys = new Set(accepted.map(entryKey));
    const kept = items.filter((e) => {
      const key = entryKey(e);
      if (!acceptedKeys.has(key)) return true;
      const source = (e.source || '').toLowerCase();
      // Replace schema autos; never drop operator rows (suggest already skipped them).
      return source === 'operator' || source === 'pack';
    });
    saveMut.mutate([...kept, ...accepted]);
  };

  const updateSuggestion = (id: string, patch: Partial<DraftSuggestion>) => {
    setSuggestions((prev) =>
      (prev ?? []).map((row) => (row.id === id ? { ...row, ...patch } : row)),
    );
  };

  return (
    <PageShell pageId="biGlossary" titleKey="bi.glossaryTitle" subtitleKey="bi.glossarySubtitle">
      <ApiErrorBanner error={suggestMut.isError ? (suggestMut.error as Error) : null} />
      <ApiErrorBanner error={saveMut.isError ? (saveMut.error as Error) : null} />

      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        <button
          type="button"
          className="btn-primary flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
          onClick={() => setDraft(emptyEntry())}
        >
          <Plus className="h-4 w-4" /> {t('bi.addGlossary')}
        </button>
        <button
          type="button"
          className="btn-secondary flex min-h-11 w-full items-center justify-center gap-2 sm:w-auto"
          disabled={suggestMut.isPending || saveMut.isPending}
          onClick={() => suggestMut.mutate()}
        >
          <Sparkles className={`h-4 w-4 ${suggestMut.isPending ? 'animate-pulse' : ''}`} />
          {suggestMut.isPending ? t('bi.glossarySuggestLoading') : t('bi.glossarySuggest')}
        </button>
      </div>

      {suggestions ? (
        <section className="card mb-4 border-indigo-200/80 bg-gradient-to-br from-indigo-50/80 via-white to-violet-50/50 p-4 shadow-sm">
          <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">{t('bi.glossarySuggestTitle')}</h2>
              <p className="mt-0.5 text-xs text-slate-600">{t('bi.glossarySuggestHint')}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600"
                onClick={() =>
                  setSuggestions((prev) => (prev ?? []).map((s) => ({ ...s, selected: true })))
                }
              >
                {t('bi.glossarySuggestSelectAll')}
              </button>
              <button
                type="button"
                className="rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-600"
                onClick={() =>
                  setSuggestions((prev) => (prev ?? []).map((s) => ({ ...s, selected: false })))
                }
              >
                {t('bi.glossarySuggestSelectNone')}
              </button>
            </div>
          </div>

          {!suggestions.length ? (
            <p className="text-sm text-slate-500">{t('bi.glossarySuggestEmpty')}</p>
          ) : (
            <ul className="max-h-[min(50dvh,28rem)] space-y-3 overflow-y-auto pr-1">
              {suggestions.map((row) => (
                <li
                  key={row.id}
                  className="rounded-xl border border-slate-200/80 bg-white/90 p-3 shadow-sm"
                >
                  <label className="mb-2 flex items-center gap-2 text-xs font-medium text-slate-700">
                    <input
                      type="checkbox"
                      checked={row.selected}
                      onChange={(e) => updateSuggestion(row.id, { selected: e.target.checked })}
                    />
                    <span className="font-mono text-[11px] text-slate-500">
                      {row.table}
                      {row.column ? `.${row.column}` : ''}
                    </span>
                  </label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <input
                      className="input-field"
                      placeholder={t('bi.businessName')}
                      value={row.business_name}
                      onChange={(e) => updateSuggestion(row.id, { business_name: e.target.value })}
                    />
                    <input
                      className="input-field"
                      placeholder={t('bi.glossarySuggestSynonyms')}
                      value={(row.synonyms ?? []).join(', ')}
                      onChange={(e) =>
                        updateSuggestion(row.id, {
                          synonyms: e.target.value
                            .split(',')
                            .map((s) => s.trim())
                            .filter(Boolean),
                        })
                      }
                    />
                    <input
                      className="input-field sm:col-span-2"
                      placeholder={t('bi.definition')}
                      value={row.definition}
                      onChange={(e) => updateSuggestion(row.id, { definition: e.target.value })}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              className="btn-primary"
              disabled={!selectedCount || saveMut.isPending}
              onClick={acceptSuggestions}
            >
              {t('bi.glossarySuggestAccept', { count: String(selectedCount) })}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setSuggestions(null)}>
              {t('bi.glossarySuggestCancel')}
            </button>
          </div>
        </section>
      ) : null}

      {draft && (
        <div className="card mb-4 grid gap-3 p-4 sm:grid-cols-2">
          <input
            className="input-field"
            placeholder={t('bi.tableName')}
            value={draft.table}
            onChange={(e) => setDraft({ ...draft, table: e.target.value })}
          />
          <input
            className="input-field"
            placeholder={t('bi.columnName')}
            value={draft.column ?? ''}
            onChange={(e) => setDraft({ ...draft, column: e.target.value })}
          />
          <input
            className="input-field"
            placeholder={t('bi.businessName')}
            value={draft.business_name}
            onChange={(e) => setDraft({ ...draft, business_name: e.target.value })}
          />
          <input
            className="input-field sm:col-span-2"
            placeholder={t('bi.definition')}
            value={draft.definition}
            onChange={(e) => setDraft({ ...draft, definition: e.target.value })}
          />
          <div className="flex gap-2 sm:col-span-2">
            <button type="button" className="btn-primary" onClick={saveDraft}>
              {t('bi.saveGlossary')}
            </button>
            <button type="button" className="btn-secondary" onClick={() => setDraft(null)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}

      {!items.length && !g.isLoading && !draft && !suggestions ? (
        <EmptyState
          emoji="📖"
          titleKey="empty.bi.glossary.title"
          descriptionKey="empty.bi.glossary.description"
          ctaLabelKey="empty.bi.glossary.cta"
          onCtaClick={() => setDraft(emptyEntry())}
        />
      ) : (
        <ResponsiveTable<BiGlossaryEntry>
          columns={[
            { id: 'table', header: t('bi.tableName'), mobilePrimary: true, cell: (r) => r.table },
            {
              id: 'column',
              header: t('bi.columnName'),
              mobileLabel: t('bi.columnName'),
              cell: (r) => r.column ?? '—',
            },
            {
              id: 'name',
              header: t('bi.businessName'),
              mobileLabel: t('bi.businessName'),
              cell: (r) => r.business_name,
            },
            {
              id: 'def',
              header: t('bi.definition'),
              mobileLabel: t('bi.definition'),
              cell: (r) => r.definition,
            },
            {
              id: 'actions',
              header: t('common.actions'),
              mobileLabel: t('common.actions'),
              cell: (r) => (
                <div className="flex flex-wrap gap-1">
                  <button
                    type="button"
                    className="inline-flex min-h-10 items-center rounded-lg px-2 text-xs font-medium text-accent"
                    onClick={() => setDraft({ ...r })}
                  >
                    {t('bi.editGlossary')}
                  </button>
                  <button
                    type="button"
                    className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg text-status-fail"
                    onClick={() => delMut.mutate(r.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              ),
            },
          ]}
          rows={items}
          rowKey={(r) => r.id}
        />
      )}
    </PageShell>
  );
}
