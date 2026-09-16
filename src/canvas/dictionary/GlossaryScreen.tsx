import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { BookOpen, Check, ChevronDown, Database, Loader2, PenLine, Search, Sparkles, X } from 'lucide-react';
import Shell from '../stitch/Shell';
import { ScanBadge } from '../DbTiming';
import { railFor } from '../stitch/screens';
import {
  ENGINE_ENABLED,
  EngineAuthError,
  adminApi,
  concepts as fetchConcepts,
  gapsApi,
  type ConceptMapping,
  type ConceptRow,
  type GapColumn,
  type GapDetail,
  type GapItem,
} from '../engine';
import { SourceBadge, SourceTabs, matchesSource, sourcesOf, useSourceFilter } from './source';
import AdminGuard from '../AdminGuard';

/**
 * Veri Sözlüğü. Üç soruya cevap verir, her biri bir bölüm:
 *  1. Terimler — "ciro" dendiğinde ZEKİ neyi hesaplıyor?
 *  2. Tablolar — veritabanında hangi tablo ne tutuyor, kolonları ne anlama geliyor?
 *  3. Eksik açıklamalar — anlamı yazılmamış tablo ve kolonlar; yönetici burada doldurur.
 * Logo her yıl/firma için aynı tabloyu yeniden açar; tablolar kalıp başına tek satır gösterilir.
 */

type Tab = 'terimler' | 'tablolar' | 'eksikler';

const nf = new Intl.NumberFormat('tr-TR');
const compact = new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 });
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
  METRIC: 'Hesap',
  COLUMN: 'Alan',
  DIMENSION_VALUE: 'Değer',
  RELATIONSHIP: 'İlişki',
  DEFAULT_FILTER: 'Varsayılan filtre',
  TEMPORAL: 'Zaman',
  ENTITY: 'Varlık',
};
const TYPE_HELP: Record<string, string> = {
  METRIC: 'Bir tutar ya da sayı hesaplar',
  COLUMN: 'Tablodaki bir alanı gösterir',
  DIMENSION_VALUE: 'Bir alanın belli bir değerine karşılık gelir',
  RELATIONSHIP: 'İki tabloyu birbirine bağlar',
  DEFAULT_FILTER: 'Sorulara kendiliğinden eklenen koşul',
  TEMPORAL: 'Tarih ya da dönem',
  ENTITY: 'Bir iş nesnesi',
};

const eyebrow = 'text-[11px] font-bold uppercase tracking-wide text-canvas-muted';
const press = 'transition-transform duration-150 ease-out active:scale-[0.97]';

/* ------------------------------------------------------------------ küçük parçalar */

function Empty({ children }: { children: ReactNode }) {
  return <div className="flex h-full min-h-32 items-center justify-center p-6 text-center text-[13px] text-canvas-muted">{children}</div>;
}

function Spinner() {
  return (
    <div className="flex h-24 items-center justify-center text-canvas-muted">
      <Loader2 className="h-4 w-4 animate-spin" />
    </div>
  );
}

/** Kolonda görülen değerler: "211 · 8,9 Mn satır". Hassas kolonda hiç gösterilmez. */
function Samples({ c }: { c: GapColumn }) {
  if (c.sensitive) return <span className="text-[11.5px] text-amber-700">Hassas alan, örnek gösterilmez</span>;
  if (!c.topValues.length) return <span className="text-[11.5px] text-canvas-muted">Örnek değer yok</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {c.topValues.slice(0, 6).map(([v, n]) => (
        <span key={v} className="rounded-md bg-slate-100 px-1.5 py-0.5 font-mono text-[11px]">
          {v === '' ? '(boş)' : v}
          <span className="ml-1 text-canvas-muted">{compact.format(n)}</span>
        </span>
      ))}
    </span>
  );
}

/** Kapsama çubuğu: tanımlı kolon oranı. */
function Coverage({ done, total, className = '' }: { done: number; total: number; className?: string }) {
  const pct = total ? Math.round((done / total) * 100) : 100;
  const tone = pct >= 90 ? 'bg-emerald-500' : pct >= 50 ? 'bg-canvas-violet' : 'bg-amber-500';
  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <span className="h-1.5 w-full min-w-10 overflow-hidden rounded-full bg-slate-200/80">
        <span className={`block h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="w-9 shrink-0 text-right font-mono text-[11px] font-bold tabular-nums text-canvas-muted">%{pct}</span>
    </span>
  );
}

/* ------------------------------------------------------------------ terimler */

function ConceptDetail({ row }: { row: ConceptRow }) {
  const c = row.concept;
  const maps = row.mappings ?? [];
  const sup = c.explain?.support ?? {};
  return (
    <div className="space-y-5">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={eyebrow}>{TYPE_HELP[c.semantic_type] ?? 'Terim'}</span>
          {sourcesOf(maps).map((src) => (
            <SourceBadge key={src} source={src} />
          ))}
        </div>
        <h2 className="mt-1 text-2xl font-extrabold tracking-tight text-canvas-ink">{c.term}</h2>
        {(c.synonyms?.length ?? 0) > 0 && (
          <p className="mt-1 text-[13px] text-canvas-muted">
            Aynı anlamda: <span className="font-semibold text-canvas-ink">{c.synonyms?.join(', ')}</span>
          </p>
        )}
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white/80 p-4">
        <div className="text-[13px] font-semibold text-canvas-ink">
          Bir soruda “{c.term}” geçtiğinde ZEKİ {maps.length > 1 ? 'şu tanımlardan uygun olanı' : 'şunu'} kullanır:
        </div>
        <div className="mt-3 space-y-3">
          {maps.map((m: ConceptMapping) => (
            <div key={m.id ?? `${m.entity}.${m.column}.${m.formula}`} className="rounded-xl bg-slate-900 p-3.5 text-slate-100">
              <div className="font-mono text-[12.5px] leading-relaxed">{m.formula ?? `${m.entity ?? ''}.${m.column ?? ''}`}</div>
              <div className="mt-1.5 flex flex-wrap items-center gap-x-1 gap-y-1 text-[11px] text-slate-400">
                <SourceBadge source={m.source} className="mr-1" />
                Tablo <span className="font-mono text-slate-300">{m.entity ?? m.table_pattern ?? '—'}</span>
                {m.column && (
                  <>
                    {' · '}alan <span className="font-mono text-slate-300">{m.column}</span>
                  </>
                )}
              </div>
              {(m.extra?.conditions?.length ?? 0) > 0 && (
                <div className="mt-2 border-t border-white/10 pt-2">
                  <div className="text-[11px] font-bold text-slate-400">Yalnız şu koşulla</div>
                  {m.extra?.conditions?.map((x) => (
                    <div key={x} className="font-mono text-[11.5px] text-slate-300">
                      {x}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {c.explain?.human_reason && (
        <div className="rounded-2xl border border-canvas-violet/20 bg-canvas-violet/[0.06] p-3.5">
          <div className="text-[12px] font-bold text-canvas-violet">
            {c.explain.human_certified_by ? `${c.explain.human_certified_by} onayladı` : 'Onay notu'}
          </div>
          <p className="mt-1 text-[13px] leading-snug text-canvas-ink">{c.explain.human_reason}</p>
        </div>
      )}

      {c.explain?.schema_drift && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3.5">
          <div className="text-[12px] font-bold text-amber-800">Tablo yapısı değişmiş olabilir</div>
          <p className="mt-1 font-mono text-[11.5px] text-amber-800">{c.explain.schema_drift}</p>
        </div>
      )}

      <details className="group rounded-2xl border border-slate-200 bg-white/60 p-3.5">
        <summary className="flex cursor-pointer list-none items-center justify-between text-[12.5px] font-bold text-canvas-muted">
          Neden güveniyoruz?
          <ChevronDown className="h-4 w-4 transition-transform duration-200 group-open:rotate-180" />
        </summary>
        <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
          {[
            ['Güven', `%${Math.round((c.confidence ?? 0) * 100)}`],
            ['Belge', sup.doc ?? 0],
            ['İnsan onayı', sup.human ?? 0],
            ['Doğrulanmış sorgu', sup.validated_queries ?? 0],
          ].map(([k, v]) => (
            <div key={k as string} className="rounded-xl bg-slate-50 p-2">
              <div className="text-[11px] text-canvas-muted">{k}</div>
              <div className="font-mono text-[14px] font-bold tabular-nums">{v}</div>
            </div>
          ))}
        </div>
        <div className="mt-2 text-[11px] text-canvas-muted">
          Sürüm {c.version ?? '—'}
          {c.updated_at ? ` · son değişiklik ${c.updated_at.slice(0, 10)}` : ''}
        </div>
      </details>
    </div>
  );
}

/* ------------------------------------------------------------------ yazma: açıklama formu */

function DescribeForm({
  initial = '',
  placeholder,
  onSave,
  onCancel,
  saving,
  error,
}: {
  initial?: string;
  placeholder: string;
  onSave: (text: string) => void;
  onCancel?: () => void;
  saving: boolean;
  error: string | null;
}) {
  const [text, setText] = useState(initial);
  return (
    <form
      className="mt-2 space-y-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) onSave(text.trim());
      }}
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        placeholder={placeholder}
        className="w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-base outline-none focus:border-canvas-violet sm:text-[13px]"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && text.trim()) onSave(text.trim());
          if (e.key === 'Escape' && onCancel) onCancel();
        }}
      />
      {error && <div className="text-[12px] font-semibold text-red-700">{error}</div>}
      <div className="flex flex-wrap gap-2">
        <button
          type="submit"
          disabled={!text.trim() || saving}
          className={`inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-canvas-violet px-3.5 text-[12.5px] font-extrabold text-white shadow-sm disabled:opacity-50 sm:min-h-9 ${press}`}
        >
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          Kaydet
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className={`min-h-11 rounded-xl bg-slate-100 px-3.5 text-[12.5px] font-bold sm:min-h-9 ${press}`}>
            Vazgeç
          </button>
        )}
      </div>
    </form>
  );
}

function useDescribe(tablePattern: string) {
  const qc = useQueryClient();
  const done = () => {
    void qc.invalidateQueries({ queryKey: ['sozluk-kaliplar'] });
    void qc.invalidateQueries({ queryKey: ['sozluk-kalip', tablePattern] });
  };
  const describe = useMutation({
    mutationFn: ({ column, text }: { column: string | null; text: string }) => gapsApi.describe(tablePattern, column, text),
    onSuccess: done,
  });
  const accept = useMutation({ mutationFn: (id: string) => gapsApi.accept(id), onSuccess: done });
  const dismiss = useMutation({ mutationFn: (id: string) => gapsApi.dismiss(id), onSuccess: done });
  return { describe, accept, dismiss };
}

const errOf = (e: unknown) => (e ? (e instanceof EngineAuthError ? 'Oturum gerekli.' : (e as Error).message || 'Kaydedilemedi.') : null);

/** Açıklaması eksik bir kolon: ne olduğu, örnek değerleri, varsa ZEKİ'nin önerisi ve yazma alanı. */
function MissingColumn({ c, tablePattern, canWrite }: { c: GapColumn; tablePattern: string; canWrite: boolean }) {
  const { describe, accept, dismiss } = useDescribe(tablePattern);
  const [writing, setWriting] = useState(false);
  const busy = describe.isPending || accept.isPending || dismiss.isPending;
  return (
    <li className="rounded-2xl border border-slate-200 bg-white/85 p-3.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="font-mono text-[13px] font-extrabold">{c.name}</span>
        <span className="text-[11px] text-canvas-muted">
          {c.type}
          {c.isPrimaryKey ? ' · anahtar' : ''}
          {c.ref ? ` · ${c.ref} ile bağlı` : ''}
        </span>
      </div>
      <div className="mt-1.5">
        <Samples c={c} />
      </div>

      {c.suggestion && (
        <div className="mt-3 rounded-xl border border-canvas-violet/20 bg-canvas-violet/[0.06] p-3">
          <div className="flex items-center gap-1.5 text-[11.5px] font-bold text-canvas-violet">
            <Sparkles className="h-3.5 w-3.5" />
            ZEKİ'nin tahmini
          </div>
          <p className="mt-1 text-[13px] leading-snug text-canvas-ink">{c.suggestion.text}</p>
          {canWrite && !writing && (
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => accept.mutate(c.suggestion!.id)}
                className={`inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-canvas-violet px-3 text-[12px] font-extrabold text-white disabled:opacity-50 sm:min-h-8 ${press}`}
              >
                {accept.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                Doğru, kaydet
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setWriting(true)}
                className={`inline-flex min-h-11 items-center gap-1.5 rounded-xl bg-white px-3 text-[12px] font-bold disabled:opacity-50 sm:min-h-8 ${press}`}
              >
                <PenLine className="h-3.5 w-3.5" />
                Düzeltip kaydet
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => dismiss.mutate(c.suggestion!.id)}
                className={`inline-flex min-h-11 items-center gap-1.5 rounded-xl px-3 text-[12px] font-bold text-canvas-muted hover:text-canvas-ink disabled:opacity-50 sm:min-h-8 ${press}`}
              >
                <X className="h-3.5 w-3.5" />
                Yanlış
              </button>
            </div>
          )}
        </div>
      )}

      {canWrite && (writing || !c.suggestion) ? (
        <DescribeForm
          initial={writing ? (c.suggestion?.text ?? '') : ''}
          placeholder="Bu alan ne anlama geliyor? Kodları varsa yazın: 1 = satış, 2 = iade…"
          saving={describe.isPending}
          error={errOf(describe.error)}
          onSave={(text) => describe.mutate({ column: c.name, text })}
          onCancel={writing ? () => setWriting(false) : undefined}
        />
      ) : null}
      {(accept.error || dismiss.error) && <div className="mt-2 text-[12px] font-semibold text-red-700">{errOf(accept.error ?? dismiss.error)}</div>}
    </li>
  );
}

/** Tablonun kendi açıklaması: yoksa yazma alanı, varsa düzenle düğmesi. */
function TableDescription({ d, canWrite }: { d: GapDetail; canWrite: boolean }) {
  const { describe } = useDescribe(d.tablePattern);
  const [editing, setEditing] = useState(false);
  useEffect(() => setEditing(false), [d.tablePattern]);
  if (editing || (!d.description && canWrite)) {
    return (
      <div className="rounded-2xl border border-amber-200 bg-amber-50/70 p-3.5">
        <div className="text-[12.5px] font-bold text-amber-900">{d.description ? 'Tablo açıklamasını düzenle' : 'Bu tablonun ne tuttuğu yazılmamış'}</div>
        <DescribeForm
          initial={d.description ?? ''}
          placeholder="Örn. Stok hareket satırları: her irsaliye ya da fatura kaleminin miktarı ve tutarı"
          saving={describe.isPending}
          error={errOf(describe.error)}
          onSave={(text) => describe.mutate({ column: null, text }, { onSuccess: () => setEditing(false) })}
          onCancel={editing ? () => setEditing(false) : undefined}
        />
      </div>
    );
  }
  return (
    <div className="flex items-start justify-between gap-3">
      <p className={`text-[14px] leading-snug ${d.description ? 'text-canvas-ink' : 'italic text-canvas-muted'}`}>
        {d.description ?? 'Bu tablonun ne tuttuğu henüz yazılmamış.'}
      </p>
      {canWrite && d.description && (
        <button type="button" onClick={() => setEditing(true)} className={`inline-flex min-h-11 shrink-0 items-center gap-1 rounded-lg px-2 text-[12px] font-bold text-canvas-muted hover:text-canvas-ink sm:min-h-8 ${press}`}>
          <PenLine className="h-3.5 w-3.5" />
          Düzenle
        </button>
      )}
    </div>
  );
}

function TableDetail({ tablePattern, mode, canWrite }: { tablePattern: string; mode: 'tablolar' | 'eksikler'; canWrite: boolean }) {
  const q = useQuery({
    queryKey: ['sozluk-kalip', tablePattern],
    queryFn: () => gapsApi.detail(tablePattern),
    enabled: ENGINE_ENABLED,
    staleTime: 60_000,
    retry: false,
  });
  const [showCopies, setShowCopies] = useState(false);
  useEffect(() => setShowCopies(false), [tablePattern]);

  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <Empty>{errOf(q.error) ?? 'Tablo okunamadı.'}</Empty>;
  const d = q.data;
  const total = d.missing.length + d.described.length;

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className={eyebrow}>{d.source === 'crm' ? 'CRM tablosu' : d.source === 'logo' ? 'Logo tablosu' : 'Tablo'}</span>
          <SourceBadge source={d.source} />
        </div>
        <h2 className="break-all font-mono text-xl font-extrabold tracking-tight text-canvas-ink">{d.example}</h2>
        <TableDescription d={d} canWrite={canWrite} />
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-canvas-muted">
          <span>
            <strong className="font-mono tabular-nums text-canvas-ink">{nf.format(d.rows)}</strong> satır
          </span>
          <span>
            <strong className="font-mono tabular-nums text-canvas-ink">{nf.format(total)}</strong> alan
          </span>
          {d.tables.length > 1 && (
            <button type="button" onClick={() => setShowCopies((v) => !v)} className="inline-flex min-h-11 items-center gap-1 font-semibold hover:text-canvas-ink sm:min-h-0">
              {nf.format(d.tables.length)} yıl/firma kopyası
              <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${showCopies ? 'rotate-180' : ''}`} />
            </button>
          )}
        </div>
        {showCopies && (
          <div className="flex flex-wrap gap-1.5">
            {d.tables.map((t) => (
              <span key={t.name} className="rounded-lg bg-slate-100 px-2 py-0.5 font-mono text-[11px]">
                {t.name} <span className="text-canvas-muted">{compact.format(t.rows)}</span>
              </span>
            ))}
          </div>
        )}
        <Coverage done={d.described.length} total={total} className="max-w-xs pt-1" />
        <ScanBadge scannedAt={d.scannedAt} />
      </div>

      {d.missing.length > 0 && (
        <section>
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-[15px] font-extrabold">Anlamı yazılmamış {nf.format(d.missing.length)} alan</h3>
            <span className="text-[12px] text-canvas-muted">
              {canWrite ? 'Doldurdukça ZEKİ bu alanları sorularda doğru kullanır.' : 'Açıklama yazmak yöneticilere açık.'}
            </span>
          </div>
          <ul className="space-y-2">
            {d.missing.map((c) => (
              <MissingColumn key={c.name} c={c} tablePattern={d.tablePattern} canWrite={canWrite} />
            ))}
          </ul>
        </section>
      )}

      {mode === 'tablolar' && d.described.length > 0 && (
        <section>
          <h3 className="mb-2 text-[15px] font-extrabold">Açıklaması olan {nf.format(d.described.length)} alan</h3>
          <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white/80">
            <table className="w-full min-w-[560px] border-collapse text-[12.5px]">
              <thead>
                <tr className="bg-slate-50 text-left">
                  <th className="px-3 py-2 font-bold text-canvas-muted">Alan</th>
                  <th className="px-3 py-2 font-bold text-canvas-muted">Anlamı</th>
                  <th className="px-3 py-2 font-bold text-canvas-muted">Örnek değerler</th>
                </tr>
              </thead>
              <tbody>
                {d.described.map((c) => (
                  <tr key={c.name} className="border-t border-slate-100 align-top">
                    <td className="px-3 py-2">
                      <div className="font-mono font-bold">{c.name}</div>
                      <div className="text-[11px] text-canvas-muted">
                        {c.type}
                        {c.isPrimaryKey ? ' · anahtar' : ''}
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      {c.description ?? '—'}
                      {c.status !== 'DESCRIBED' && (
                        <span className="ml-1.5 rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-bold text-emerald-700">
                          {c.status === 'CERTIFIED' ? 'terimde kullanılıyor' : 'terim adayı'}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <Samples c={c} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {mode === 'eksikler' && d.missing.length === 0 && !(!d.description && canWrite) && (
        <Empty>Bu tablonun bütün alanları açıklanmış.</Empty>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ ekran */

export default function GlossaryScreen() {
  return (
    <AdminGuard rail="/veri-sozlugu" crumb="Veri Sözlüğü">
      <GlossaryScreenInner />
    </AdminGuard>
  );
}

function GlossaryScreenInner() {
  const [tab, setTab] = useState<Tab>('terimler');
  const [q, setQ] = useState('');
  const [sel, setSel] = useState('');
  const [type, setType] = useState('');
  const [showEmpty, setShowEmpty] = useState(false);
  const [onlySuggested, setOnlySuggested] = useState(false);
  const [source, setSource] = useSourceFilter();
  const detailRef = useRef<HTMLDivElement | null>(null);

  const conceptsQ = useQuery({
    queryKey: ['sozluk-kavramlar'],
    queryFn: () => fetchConcepts('CERTIFIED', 5000),
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const gapsQ = useQuery({ queryKey: ['sozluk-kaliplar'], queryFn: gapsApi.list, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000, retry: false });
  const meQ = useQuery({ queryKey: ['admin', 'me'], queryFn: adminApi.me, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000, retry: false });
  const canWrite = !!meQ.data?.isAdmin;

  /** Aynı terim her dönem/tablo için ayrı onaylı kayıtla gelebilir; listede tek satır, tanımlar detayda. */
  const terms = useMemo(() => {
    const mKey = (m: ConceptMapping) => `${m.entity ?? m.table_pattern ?? ''}.${m.column ?? ''}.${m.formula ?? ''}`;
    const by = new Map<string, ConceptRow>();
    for (const r of conceptsQ.data?.items ?? []) {
      const k = `${norm(r.concept.term)}|${r.concept.semantic_type}`;
      const cur = by.get(k);
      if (!cur) {
        by.set(k, { concept: { ...r.concept }, mappings: [...(r.mappings ?? [])] });
        continue;
      }
      const seen = new Set((cur.mappings ?? []).map(mKey));
      for (const m of r.mappings ?? []) if (!seen.has(mKey(m))) (cur.mappings = [...(cur.mappings ?? []), m]), seen.add(mKey(m));
      const synonyms = [...new Set([...(cur.concept.synonyms ?? []), ...(r.concept.synonyms ?? [])])];
      const best = (r.concept.confidence ?? 0) > (cur.concept.confidence ?? 0) ? r.concept : cur.concept;
      cur.concept = { ...best, synonyms };
    }
    return [...by.values()].sort((a, b) => a.concept.term.localeCompare(b.concept.term, 'tr'));
  }, [conceptsQ.data]);
  const types = useMemo(() => [...new Set(terms.map((r) => r.concept.semantic_type))].sort(), [terms]);

  const n = norm(q.trim());
  const shownTerms = useMemo(
    () =>
      terms.filter((r) => {
        if (type && r.concept.semantic_type !== type) return false;
        if (source !== 'all' && !sourcesOf(r.mappings ?? []).includes(source)) return false;
        if (!n) return true;
        const m = r.mappings?.[0];
        return norm([r.concept.term, ...(r.concept.synonyms ?? []), m?.formula ?? '', m?.entity ?? '', m?.column ?? ''].join(' ')).includes(n);
      }),
    [terms, type, n, source],
  );

  const items = gapsQ.data?.items ?? [];
  const summary = gapsQ.data?.summary;
  const shownTables = useMemo(
    () =>
      items.filter((t) => {
        if (!matchesSource(source, t.source)) return false;
        if (tab === 'tablolar' && !showEmpty && t.rows === 0) return false;
        if (tab === 'eksikler') {
          if (t.rows === 0 && !showEmpty) return false;
          if (!t.missing && !t.tableMissing) return false;
          if (onlySuggested && !t.suggestions) return false;
        }
        return !n || norm(`${t.example} ${t.tablePattern} ${t.description ?? ''}`).includes(n);
      }),
    [items, tab, showEmpty, onlySuggested, n, source],
  );

  /** Seçim düğmelerindeki sayılar, ötekiler (tür, boş tablo, arama) uygulanmış hâliyle. */
  const sourceCounts = useMemo(() => {
    if (tab === 'terimler') {
      const base = terms.filter((r) => !type || r.concept.semantic_type === type);
      const has = (src: 'logo' | 'crm') => base.filter((r) => sourcesOf(r.mappings ?? []).includes(src)).length;
      return { all: base.length, logo: has('logo'), crm: has('crm') };
    }
    const base = items.filter((t) => {
      if (t.rows === 0 && !showEmpty) return false;
      if (tab === 'eksikler' && (!(t.missing || t.tableMissing) || (onlySuggested && !t.suggestions))) return false;
      return true;
    });
    return { all: base.length, logo: base.filter((t) => t.source === 'logo').length, crm: base.filter((t) => t.source === 'crm').length };
  }, [tab, terms, type, items, showEmpty, onlySuggested]);

  const selectedTerm = shownTerms.find((r) => r.concept.id === sel) ?? shownTerms[0];
  const selectedTable: GapItem | undefined = shownTables.find((t) => t.tablePattern === sel) ?? shownTables[0];
  const authRequired = conceptsQ.error instanceof EngineAuthError || gapsQ.error instanceof EngineAuthError;
  const loading = tab === 'terimler' ? conceptsQ.isLoading : gapsQ.isLoading;

  const pick = (id: string) => {
    setSel(id);
    if (window.innerWidth >= 768) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    requestAnimationFrame(() => detailRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' }));
  };

  const described = summary ? summary.columns - summary.missingColumns : 0;
  const TABS: Array<{ id: Tab; icon: typeof BookOpen; title: string; help: string; stat: ReactNode }> = [
    {
      id: 'terimler',
      icon: BookOpen,
      title: 'Terimler',
      help: '“Ciro”, “iade” gibi kelimeleri ZEKİ nasıl hesaplıyor',
      stat: conceptsQ.data ? `${nf.format(terms.length)} onaylı terim` : '…',
    },
    {
      id: 'tablolar',
      icon: Database,
      title: 'Tablolar',
      help: 'Logo ve CRM tabloları ne tutuyor, alanları ne demek',
      stat: summary ? `${nf.format(items.filter((t) => t.rows > 0).length)} dolu tablo` : '…',
    },
    {
      id: 'eksikler',
      icon: PenLine,
      title: 'Eksik açıklamalar',
      help: 'Anlamı yazılmamış alanlar; doldurdukça cevaplar iyileşir',
      stat: summary ? `%${Math.round((described / Math.max(1, summary.columns)) * 100)} açıklamalı` : '…',
    },
  ];

  return (
    <Shell
      head={{
        tenant: 'Timaş Yayınları',
        section: 'Yapay Zeka Raporları',
        crumb: 'Veri Sözlüğü',
        source: TABS.find((t) => t.id === tab)?.title ?? '',
        presence: 'canlı',
        zoom: '%100',
      }}
      rail={railFor('/veri-sozlugu')}
    >
      <main className="absolute bottom-2 left-14 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-[92px] sm:right-6 sm:top-[84px]">
        <div className="mx-auto flex min-h-full w-full max-w-[1760px] flex-col gap-3 pb-4 md:gap-3">
          {/* Başlık ve bölüm seçimi tek satırda: çalışma alanına yer kalsın */}
          <div className="flex shrink-0 flex-col gap-2 lg:flex-row lg:items-center lg:justify-between lg:gap-4">
            <div className="min-w-0">
              <h1 className="text-[20px] font-extrabold leading-tight tracking-tight text-canvas-ink">Veri Sözlüğü</h1>
              <p className="text-[12.5px] text-canvas-muted">{TABS.find((t) => t.id === tab)?.help}</p>
            </div>
            <div role="tablist" className="glass-panel -mx-1 flex gap-1 overflow-x-auto rounded-2xl p-1 shadow-glass-float [scrollbar-width:none] lg:mx-0 [&::-webkit-scrollbar]:hidden">
              {TABS.map((t) => {
                const on = tab === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    role="tab"
                    aria-selected={on}
                    onClick={() => {
                      setTab(t.id);
                      setSel('');
                      setQ('');
                    }}
                    className={[
                      'flex min-h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-xl px-3 text-left sm:min-h-10',
                      press,
                      on ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:bg-white/60 hover:text-canvas-ink',
                    ].join(' ')}
                  >
                    <t.icon className={`h-4 w-4 ${on ? 'text-canvas-violet' : ''}`} />
                    <span className="text-[13px] font-extrabold">{t.title}</span>
                    <span className="text-[11.5px] font-semibold text-canvas-muted">{t.stat}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-1 flex-col gap-3 md:min-h-[max(560px,calc(100dvh-190px))] md:flex-row md:gap-4">
            {/* Sol: arama ve liste */}
            <div className="glass-panel flex max-h-[46vh] w-full shrink-0 flex-col rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4 md:max-h-[calc(100dvh-190px)] md:w-[360px]">
              <label className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white/90 px-3 py-2">
                <Search className="h-3.5 w-3.5 shrink-0 text-canvas-muted" />
                <input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder={tab === 'terimler' ? 'Terim ara: ciro, iade, stok…' : 'Tablo adı ya da açıklama ara…'}
                  className="w-full bg-transparent text-base font-semibold outline-none placeholder:text-canvas-muted/70 sm:text-[12.5px]"
                />
              </label>

              <SourceTabs value={source} onChange={(v) => { setSource(v); setSel(''); }} counts={sourceCounts} className="mt-2" />

              {tab === 'terimler' && types.length > 1 && (
                <div className="-mx-1 mt-2 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                  {['', ...types].map((t) => (
                    <button
                      key={t || 'hepsi'}
                      type="button"
                      onClick={() => setType(t)}
                      className={[
                        'min-h-9 shrink-0 whitespace-nowrap rounded-lg px-2.5 text-[12px] font-bold sm:min-h-7',
                        type === t ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-muted',
                      ].join(' ')}
                    >
                      {t ? (TYPE_LABEL[t] ?? t) : 'Hepsi'}
                    </button>
                  ))}
                </div>
              )}

              {tab !== 'terimler' && (
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-canvas-muted">
                  <label className="flex min-h-9 cursor-pointer items-center gap-1.5 sm:min-h-0">
                    <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} className="h-3.5 w-3.5 accent-[#7c5cff]" />
                    Boş tabloları da göster
                  </label>
                  {tab === 'eksikler' && (summary?.suggestions ?? 0) > 0 && (
                    <label className="flex min-h-9 cursor-pointer items-center gap-1.5 sm:min-h-0">
                      <input type="checkbox" checked={onlySuggested} onChange={(e) => setOnlySuggested(e.target.checked)} className="h-3.5 w-3.5 accent-[#7c5cff]" />
                      Yalnız ZEKİ'nin tahmini olanlar
                    </label>
                  )}
                </div>
              )}

              <div className="mt-2 text-[11.5px] font-semibold text-canvas-muted">
                {tab === 'terimler' ? `${nf.format(shownTerms.length)} terim` : `${nf.format(shownTables.length)} tablo`}
                {tab === 'eksikler' && ' · en çok kullanılan üstte'}
              </div>

              <div className="mt-1.5 flex-1 space-y-1 overflow-auto pr-1">
                {loading && <Spinner />}
                {!loading && authRequired && <Empty>Oturum gerekli.</Empty>}
                {!loading && !authRequired && (tab === 'terimler' ? conceptsQ.error : gapsQ.error) && (
                  <Empty>{errOf(tab === 'terimler' ? conceptsQ.error : gapsQ.error)}</Empty>
                )}

                {tab === 'terimler' &&
                  shownTerms.map((r) => (
                    <button
                      key={r.concept.id}
                      type="button"
                      onClick={() => pick(r.concept.id)}
                      className={[
                        'flex min-h-11 w-full items-center gap-2 rounded-xl px-2.5 py-2 text-left sm:min-h-0',
                        selectedTerm?.concept.id === r.concept.id ? 'bg-white shadow-sm' : 'hover:bg-white/70',
                      ].join(' ')}
                    >
                      <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">{r.concept.term}</span>
                      {source === 'all' && sourcesOf(r.mappings ?? []).map((src) => <SourceBadge key={src} source={src} />)}
                      <span className="shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-bold text-canvas-muted">
                        {TYPE_LABEL[r.concept.semantic_type] ?? r.concept.semantic_type}
                      </span>
                    </button>
                  ))}

                {tab !== 'terimler' &&
                  shownTables.map((t) => (
                    <button
                      key={t.tablePattern}
                      type="button"
                      onClick={() => pick(t.tablePattern)}
                      className={[
                        'flex min-h-11 w-full flex-col gap-0.5 rounded-xl px-2.5 py-2 text-left sm:min-h-0',
                        selectedTable?.tablePattern === t.tablePattern ? 'bg-white shadow-sm' : 'hover:bg-white/70',
                      ].join(' ')}
                    >
                      <span className={`truncate text-[13px] font-semibold ${t.description ? '' : 'italic text-canvas-muted'}`}>
                        {t.description ?? 'Açıklama yok'}
                      </span>
                      <span className="flex items-center justify-between gap-2">
                        <span className="flex min-w-0 items-center gap-1.5">
                          {source === 'all' && <SourceBadge source={t.source} />}
                          <span className="min-w-0 truncate font-mono text-[11px] text-canvas-muted">{t.example}</span>
                        </span>
                        <span className="shrink-0 font-mono text-[11px] tabular-nums text-canvas-muted">{compact.format(t.rows)} satır</span>
                      </span>
                      {tab === 'eksikler' && (
                        <span className="mt-0.5 flex flex-wrap gap-1">
                          {t.tableMissing && <span className="rounded bg-amber-50 px-1.5 text-[11px] font-bold text-amber-700">tablo açıklaması yok</span>}
                          {t.missing > 0 && (
                            <span className="rounded bg-slate-100 px-1.5 text-[11px] font-bold text-canvas-ink">
                              {nf.format(t.missing)}/{nf.format(t.columns)} alan eksik
                            </span>
                          )}
                          {t.suggestions > 0 && (
                            <span className="rounded bg-canvas-violet/10 px-1.5 text-[11px] font-bold text-canvas-violet">{nf.format(t.suggestions)} tahmin</span>
                          )}
                        </span>
                      )}
                    </button>
                  ))}

                {!loading && !authRequired && (tab === 'terimler' ? shownTerms.length === 0 : shownTables.length === 0) && (
                  <Empty>{q ? 'Aramaya uyan kayıt yok.' : tab === 'eksikler' ? 'Eksik açıklama kalmadı.' : 'Kayıt yok.'}</Empty>
                )}
              </div>
            </div>

            {/* Sağ: detay */}
            <div
              ref={detailRef}
              className="glass-card min-w-0 shrink-0 scroll-mt-2 rounded-2xl p-4 shadow-canvas-card sm:rounded-3xl sm:p-6 md:max-h-[calc(100dvh-190px)] md:flex-1 md:shrink md:overflow-auto"
            >
              {loading ? (
                <Spinner />
              ) : tab === 'terimler' ? (
                selectedTerm ? <ConceptDetail row={selectedTerm} /> : <Empty>Soldan bir terim seçin.</Empty>
              ) : selectedTable ? (
                <TableDetail key={selectedTable.tablePattern} tablePattern={selectedTable.tablePattern} mode={tab} canWrite={canWrite} />
              ) : (
                <Empty>Soldan bir tablo seçin.</Empty>
              )}
            </div>
          </div>
        </div>
      </main>
    </Shell>
  );
}
