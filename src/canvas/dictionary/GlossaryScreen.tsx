import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, Database, Loader2, Search } from 'lucide-react';
import Shell from '../stitch/Shell';
import { railFor } from '../stitch/screens';
import {
  ENGINE_ENABLED,
  EngineAuthError,
  concepts as fetchConcepts,
  inventory as fetchInventory,
  type Concept,
  type ConceptMapping,
  type ConceptRow,
  type TableRow,
} from '../engine';

const nf = new Intl.NumberFormat('tr-TR');
const norm = (s: string) =>
  s
    .toLocaleLowerCase('tr')
    .replace(/[ıİ]/g, 'i')
    .replace(/[şŞ]/g, 's')
    .replace(/[ğĞ]/g, 'g')
    .replace(/[üÜ]/g, 'u')
    .replace(/[öÖ]/g, 'o')
    .replace(/[çÇ]/g, 'c');

const TYPE_LABEL: Record<string, string> = {
  METRIC: 'Metrik',
  COLUMN: 'Kolon',
  DIMENSION_VALUE: 'Değer',
  RELATIONSHIP: 'İlişki',
  DEFAULT_FILTER: 'Varsayılan filtre',
  TEMPORAL: 'Zaman',
  ENTITY: 'Varlık',
};
const TYPE_TONE: Record<string, string> = {
  METRIC: 'bg-canvas-violet/12 text-canvas-violet',
  COLUMN: 'bg-sky-50 text-sky-700',
  DIMENSION_VALUE: 'bg-emerald-50 text-emerald-700',
  RELATIONSHIP: 'bg-amber-50 text-amber-700',
  DEFAULT_FILTER: 'bg-slate-100 text-slate-600',
};

function Pill({ type }: { type: string }) {
  return (
    <span className={['rounded px-1.5 py-0.5 text-[9.5px] font-bold', TYPE_TONE[type] ?? 'bg-slate-100 text-slate-600'].join(' ')}>
      {TYPE_LABEL[type] ?? type}
    </span>
  );
}

/** Güven çubuğu: 0-1 arası değer. */
function Confidence({ v }: { v?: number }) {
  const pct = Math.round((v ?? 0) * 100);
  const tone = pct >= 80 ? 'bg-canvas-mint' : pct >= 60 ? 'bg-canvas-violet' : 'bg-canvas-amber';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
        <div className={['h-full rounded-full', tone].join(' ')} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-[10px] font-bold tabular-nums text-canvas-muted">%{pct}</span>
    </div>
  );
}

/** Metriğin hesabı ve hangi koşullarla çalıştığı. Sözlüğün asıl cevabı bu. */
function Formula({ m }: { m: ConceptMapping }) {
  const conds = m.extra?.conditions ?? [];
  return (
    <div className="rounded-2xl bg-slate-900 p-3.5 text-slate-100">
      <div className="mb-1.5 text-[10px] font-bold tracking-wide text-slate-400">NASIL HESAPLANIYOR</div>
      <div className="font-mono text-[12px] leading-relaxed">{m.formula ?? `${m.entity ?? ''}.${m.column ?? ''}`}</div>
      {conds.length > 0 && (
        <div className="mt-2 border-t border-white/10 pt-2">
          <div className="mb-1 text-[10px] font-bold text-slate-400">KOŞULLAR</div>
          {conds.map((c) => (
            <div key={c} className="font-mono text-[11px] text-slate-300">
              {c}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConceptDetail({ row }: { row: ConceptRow }) {
  const c = row.concept;
  const sup = c.explain?.support ?? {};
  const breakdown = Object.entries(c.explain?.breakdown ?? {});
  const LABEL: Record<string, string> = {
    profile_fit: 'Veriye uygunluk',
    validated_sql: 'Doğrulanmış sorgu',
    semantic_similarity: 'Anlam yakınlığı',
    physical_context_fit: 'Tablo bağlamı',
    question_correlation: 'Soru ilişkisi',
    execution_consistency: 'Tutarlı çalışma',
  };

  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-extrabold tracking-tight text-canvas-ink">{c.term}</h2>
          <Pill type={c.semantic_type} />
          <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-[9.5px] font-bold text-emerald-700">{c.status}</span>
        </div>
        <div className="mt-1.5">
          <Confidence v={c.confidence} />
        </div>
      </div>

      {(row.mappings ?? []).map((m) => (
        <Formula key={m.id ?? m.formula ?? m.column ?? 'm'} m={m} />
      ))}

      {(row.mappings ?? []).length > 0 && (
        <div className="grid grid-cols-2 gap-3 text-[12px]">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Tablo</div>
            <div className="font-semibold">{row.mappings?.[0]?.entity ?? '—'}</div>
          </div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Kolon</div>
            <div className="font-semibold">{row.mappings?.[0]?.column ?? '—'}</div>
          </div>
        </div>
      )}

      {(c.synonyms?.length ?? 0) > 0 && (
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Eş anlamlılar</div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {c.synonyms?.map((s) => (
              <span key={s} className="rounded-lg bg-slate-100 px-2 py-0.5 text-[11px] font-semibold">
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {c.explain?.human_reason && (
        <div className="rounded-2xl border border-canvas-violet/20 bg-canvas-violet/[0.06] p-3">
          <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-violet">Onay gerekçesi</div>
          <p className="mt-1 text-[12.5px] leading-snug text-canvas-ink">{c.explain.human_reason}</p>
          {c.explain.human_certified_by && (
            <div className="mt-1 text-[10.5px] text-canvas-muted">Onaylayan: {c.explain.human_certified_by}</div>
          )}
        </div>
      )}

      {c.explain?.schema_drift && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3">
          <div className="text-[10px] font-bold uppercase tracking-wide text-amber-700">Şema uyarısı</div>
          <p className="mt-1 font-mono text-[11.5px] text-amber-800">{c.explain.schema_drift}</p>
        </div>
      )}

      <div>
        <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Dayanak</div>
        <div className="mt-1 flex flex-wrap gap-3 text-[11.5px]">
          <span>
            Belge <strong>{sup.doc ?? 0}</strong>
          </span>
          <span>
            İnsan <strong>{sup.human ?? 0}</strong>
          </span>
          <span>
            Model <strong>{sup.llm ?? 0}</strong>
          </span>
          <span>
            Doğrulanmış sorgu <strong>{sup.validated_queries ?? 0}</strong>
          </span>
        </div>
      </div>

      {breakdown.length > 0 && (
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Güven kırılımı</div>
          <div className="mt-1.5 space-y-1">
            {breakdown.map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="w-[140px] shrink-0 text-[11px] text-canvas-muted">{LABEL[k] ?? k}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-canvas-violet/70" style={{ width: `${Math.round(v * 100)}%` }} />
                </div>
                <span className="w-9 text-right font-mono text-[10px] tabular-nums text-canvas-muted">
                  {Math.round(v * 100)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-4 border-t border-slate-100 pt-3 text-[11px] text-canvas-muted">
        <span>Sürüm {c.version ?? '—'}</span>
        <span>Alan {c.domain ?? '—'}</span>
        {c.updated_at && <span>Güncelleme {c.updated_at.slice(0, 10)}</span>}
      </div>
    </div>
  );
}

function TableDetail({ t }: { t: TableRow }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="font-mono text-lg font-extrabold tracking-tight text-canvas-ink">{t.tableName}</h2>
        {t.description && <p className="mt-1 text-[13px] text-canvas-muted">{t.description}</p>}
      </div>
      <div className="grid grid-cols-3 gap-3 text-[12px]">
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Satır</div>
          <div className="font-mono font-bold tabular-nums">{nf.format(t.rowCount ?? 0)}</div>
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Kolon</div>
          <div className="font-mono font-bold tabular-nums">{nf.format(t.columnCount ?? t.columns?.length ?? 0)}</div>
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Anahtar</div>
          <div className="font-mono text-[11px] font-bold">{(t.primaryKey ?? []).join(', ') || '—'}</div>
        </div>
      </div>
      {(t.columns?.length ?? 0) > 0 && (
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-canvas-muted">Kolonlar</div>
          <div className="max-h-[46vh] overflow-auto rounded-xl border border-slate-200">
            <table className="w-full border-collapse text-[11.5px]">
              <tbody>
                {t.columns?.map((c) => (
                  <tr key={c.name} className="border-b border-slate-100 last:border-0 odd:bg-slate-50/60">
                    <td className="px-2 py-1 font-mono font-semibold">{c.name}</td>
                    <td className="px-2 py-1 text-canvas-muted">{c.type}</td>
                    <td className="px-2 py-1 text-right">
                      {c.isPrimaryKey && <span className="rounded bg-canvas-violet/10 px-1.5 text-[9.5px] font-bold text-canvas-violet">PK</span>}
                      {c.sensitive && <span className="ml-1 rounded bg-amber-50 px-1.5 text-[9.5px] font-bold text-amber-700">hassas</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Veri Sözlüğü. Solda arama ve liste, sağda detay. İki sekme: iş terimleri
 * (nasıl hesaplandığı, hangi koşullarla, kim onayladı) ve tablolar (açıklama,
 * satır sayısı, kolonlar).
 */
export default function GlossaryScreen() {
  const [tab, setTab] = useState<'terim' | 'tablo'>('terim');
  const [q, setQ] = useState('');
  const [type, setType] = useState<string>('');
  const [sel, setSel] = useState<string>('');

  const conceptsQ = useQuery({
    queryKey: ['sozluk-kavramlar'],
    queryFn: () => fetchConcepts('CERTIFIED', 400),
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const tablesQ = useQuery({
    queryKey: ['sozluk-tablolar'],
    queryFn: fetchInventory,
    enabled: ENGINE_ENABLED && tab === 'tablo',
    staleTime: 10 * 60_000,
    retry: false,
  });

  const authRequired = conceptsQ.error instanceof EngineAuthError || tablesQ.error instanceof EngineAuthError;
  const rows = useMemo(() => conceptsQ.data?.items ?? [], [conceptsQ.data]);
  const types = useMemo(() => [...new Set(rows.map((r) => r.concept.semantic_type))].sort(), [rows]);

  const filteredConcepts = useMemo(() => {
    const n = norm(q.trim());
    return rows.filter((r) => {
      if (type && r.concept.semantic_type !== type) return false;
      if (!n) return true;
      const hay = [
        r.concept.term,
        ...(r.concept.synonyms ?? []),
        r.mappings?.[0]?.formula ?? '',
        r.mappings?.[0]?.entity ?? '',
        r.mappings?.[0]?.column ?? '',
      ].join(' ');
      return norm(hay).includes(n);
    });
  }, [rows, q, type]);

  const filteredTables = useMemo(() => {
    const list = tablesQ.data?.tables ?? [];
    const n = norm(q.trim());
    const base = n
      ? list.filter((t) => norm(`${t.tableName} ${t.description ?? ''} ${t.entity ?? ''}`).includes(n))
      : list;
    return [...base].sort((a, b) => (b.rowCount ?? 0) - (a.rowCount ?? 0)).slice(0, 300);
  }, [tablesQ.data, q]);

  const selectedConcept = filteredConcepts.find((r) => r.concept.id === sel) ?? filteredConcepts[0];
  const selectedTable = filteredTables.find((t) => t.tableName === sel) ?? filteredTables[0];
  const loading = tab === 'terim' ? conceptsQ.isLoading : tablesQ.isLoading;

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Yapay Zeka Raporları',
        crumb: 'Veri Sözlüğü',
        source: tab === 'terim' ? `${nf.format(rows.length)} terim` : `${nf.format(tablesQ.data?.tables?.length ?? 0)} tablo`,
        presence: 'canlı',
        zoom: '%100',
      }}
      rail={railFor('/veri-sozlugu')}
    >
      <main className="absolute inset-x-0 bottom-6 top-[84px] px-6">
        <div className="mx-auto flex h-full w-full max-w-[1760px] gap-4">
          {/* Sol: arama ve liste */}
          <div className="glass-panel flex w-[380px] shrink-0 flex-col rounded-3xl p-4 shadow-glass-float">
            <div className="flex gap-1.5">
              {(['terim', 'tablo'] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => {
                    setTab(t);
                    setSel('');
                  }}
                  className={[
                    'flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-[12px] font-bold transition',
                    tab === t ? 'bg-canvas-violet/15 text-canvas-violet' : 'text-canvas-muted hover:bg-white/80',
                  ].join(' ')}
                >
                  {t === 'terim' ? <BookOpen className="h-3.5 w-3.5" /> : <Database className="h-3.5 w-3.5" />}
                  {t === 'terim' ? 'İş terimleri' : 'Tablolar'}
                </button>
              ))}
            </div>

            <div className="mt-3 flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2">
              <Search className="h-3.5 w-3.5 text-canvas-muted" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={tab === 'terim' ? 'Terim, formül veya kolon ara…' : 'Tablo veya açıklama ara…'}
                className="w-full bg-transparent text-[12.5px] font-semibold outline-none placeholder:text-canvas-muted/70"
              />
            </div>

            {tab === 'terim' && types.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                <button
                  type="button"
                  onClick={() => setType('')}
                  className={['rounded-lg px-2 py-0.5 text-[10.5px] font-bold', !type ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-muted'].join(' ')}
                >
                  Hepsi
                </button>
                {types.map((t) => (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setType(type === t ? '' : t)}
                    className={['rounded-lg px-2 py-0.5 text-[10.5px] font-bold', type === t ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-muted'].join(' ')}
                  >
                    {TYPE_LABEL[t] ?? t}
                  </button>
                ))}
              </div>
            )}

            <div className="mt-2 text-[10.5px] font-semibold text-canvas-muted">
              {tab === 'terim' ? `${filteredConcepts.length} terim` : `${filteredTables.length} tablo`}
            </div>

            <div className="mt-1.5 flex-1 space-y-1 overflow-auto pr-1">
              {loading && (
                <div className="flex h-24 items-center justify-center text-canvas-muted">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              )}
              {!loading && authRequired && <div className="p-3 text-[12px] text-canvas-muted">Oturum gerekli.</div>}

              {tab === 'terim' &&
                filteredConcepts.map((r) => (
                  <button
                    key={r.concept.id}
                    type="button"
                    onClick={() => setSel(r.concept.id)}
                    className={[
                      'flex w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left transition',
                      selectedConcept?.concept.id === r.concept.id ? 'bg-white shadow-sm' : 'hover:bg-white/70',
                    ].join(' ')}
                  >
                    <span className="min-w-0 flex-1 truncate text-[12.5px] font-semibold">{r.concept.term}</span>
                    <Pill type={r.concept.semantic_type} />
                  </button>
                ))}

              {tab === 'tablo' &&
                filteredTables.map((t) => (
                  <button
                    key={t.tableName}
                    type="button"
                    onClick={() => setSel(t.tableName)}
                    className={[
                      'flex w-full flex-col rounded-xl px-2.5 py-2 text-left transition',
                      selectedTable?.tableName === t.tableName ? 'bg-white shadow-sm' : 'hover:bg-white/70',
                    ].join(' ')}
                  >
                    <span className="truncate font-mono text-[11.5px] font-bold">{t.tableName}</span>
                    <span className="flex items-center justify-between gap-2">
                      <span className="min-w-0 truncate text-[11px] text-canvas-muted">{t.description ?? '—'}</span>
                      <span className="shrink-0 font-mono text-[10px] tabular-nums text-canvas-muted">
                        {nf.format(t.rowCount ?? 0)}
                      </span>
                    </span>
                  </button>
                ))}
            </div>
          </div>

          {/* Sağ: detay */}
          <div className="glass-card min-w-0 flex-1 overflow-auto rounded-3xl p-6 shadow-canvas-card">
            {loading ? (
              <div className="flex h-full items-center justify-center text-canvas-muted">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            ) : tab === 'terim' ? (
              selectedConcept ? (
                <ConceptDetail row={selectedConcept} />
              ) : (
                <div className="text-[13px] text-canvas-muted">Eşleşen terim yok.</div>
              )
            ) : selectedTable ? (
              <TableDetail t={selectedTable} />
            ) : (
              <div className="text-[13px] text-canvas-muted">Eşleşen tablo yok.</div>
            )}
          </div>
        </div>
      </main>
    </Shell>
  );
}

export type { Concept };
