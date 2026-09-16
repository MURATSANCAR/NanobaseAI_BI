import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { restrictToParentElement, restrictToVerticalAxis } from '@dnd-kit/modifiers';
import { CSS } from '@dnd-kit/utilities';
import { ArrowUp, Eye, EyeOff, FileSpreadsheet, GripVertical, Info, Loader2, RotateCcw, Sparkles, Zap } from 'lucide-react';
import { EngineAuthError, reportsApi, type ColumnFormat, type ReportColumn, type ReportDraft } from '../engine';
import DbTimingBadge from '../DbTiming';

/** Önizlemede gösterilen satır sayısı; köprüdeki PREVIEW_ROWS ile aynı. Dosyaya tamamı yazılır. */
export const PREVIEW_ROWS = 50;

const nf = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 });
const nf0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const INTEGER = /^(int|integer|bigint|smallint)$/i;
const nf2 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const nf1 = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

const FORMATS: Array<{ v: ColumnFormat; label: string }> = [
  { v: 'auto', label: 'Otomatik' },
  { v: 'text', label: 'Metin' },
  { v: 'number', label: 'Sayı' },
  { v: 'money', label: 'Para ₺' },
  { v: 'percent', label: 'Yüzde %' },
  { v: 'date', label: 'Tarih' },
];

const NUMERIC = /int|float|decimal|number|numeric|double|money|real/i;
const DATE = /date|time/i;

function effectiveFormat(c: ReportColumn, type: string | undefined): ColumnFormat {
  if (c.format !== 'auto') return c.format;
  if (type && DATE.test(type)) return 'date';
  if (type && NUMERIC.test(type)) return 'number';
  return 'text';
}

/** Hücreyi Excel'deki görünüşüyle yazar; değer değişmez. */
export function formatCell(v: unknown, fmt: ColumnFormat, type?: string): string {
  if (v === null || v === undefined || v === '') return '';
  const n = typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' && !Number.isNaN(Number(v)) ? Number(v) : null;
  if (fmt === 'money' && n !== null) return `${nf2.format(n)} ₺`;
  if (fmt === 'percent' && n !== null) return `${nf1.format(n)} %`;
  // Excel'deki biçimle aynı: tam sayı kolonu 0, ondalıklı kolon 2 hane.
  if (fmt === 'number' && n !== null) return type && INTEGER.test(type) ? nf0.format(n) : nf2.format(n);
  if (fmt === 'auto' && typeof v === 'number') return nf.format(v);
  if (fmt === 'date' && typeof v === 'string') {
    const d = new Date(v);
    if (!Number.isNaN(d.getTime())) return d.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Istanbul' });
  }
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

const isRight = (fmt: ColumnFormat) => fmt === 'money' || fmt === 'percent' || fmt === 'number';

const REDUCED_MOTION = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Excel kolon harfi: 0 → A, 26 → AA. */
const letter = (i: number): string => (i < 26 ? String.fromCharCode(65 + i) : letter(Math.floor(i / 26) - 1) + letter(i % 26));

/** Bir düzeltmeden hemen önceki tam durum (elle yapılan kolon değişiklikleri dahil) ve o düzeltmenin notu. */
type Step = { before: { draft: ReportDraft; layout: ReportColumn[] }; note: string; via: 'rules' | 'model'; requery: boolean };

function ColumnRow({
  col,
  index,
  type,
  flash,
  labelError,
  onChange,
  inputRef,
}: {
  col: ReportColumn;
  index: number;
  type?: string;
  flash: boolean;
  labelError: boolean;
  onChange: (c: ReportColumn) => void;
  inputRef: (el: HTMLInputElement | null) => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, transform, transition, isDragging } = useSortable({
    id: col.key,
    // Sürüklenen kart parmağı izler; yer açan komşular kısa kayar. Azaltılmış harekette komşular anında yer değiştirir.
    transition: REDUCED_MOTION ? null : { duration: 200, easing: 'cubic-bezier(0.23, 1, 0.32, 1)' },
  });
  const renamed = col.label !== col.key;
  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), transition }}
      data-flash={flash || undefined}
      data-dragging={isDragging || undefined}
      className={[
        'xd-col group relative flex items-start gap-1.5 rounded-xl border bg-white px-1.5 py-1.5',
        col.hidden ? 'border-dashed border-slate-200 bg-slate-50/80' : 'border-slate-200/80',
        isDragging ? 'z-10 shadow-lg ring-1 ring-canvas-violet/30' : '',
      ].join(' ')}
    >
      <button
        type="button"
        ref={setActivatorNodeRef}
        {...attributes}
        {...listeners}
        aria-label={`${col.label} kolonunu taşı`}
        className="flex h-11 w-7 shrink-0 cursor-grab touch-none items-center justify-center rounded-lg text-slate-400 hover:text-canvas-ink active:cursor-grabbing sm:h-8"
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className={`w-5 shrink-0 text-center font-mono text-[10px] font-bold ${col.hidden ? 'text-slate-300' : 'text-canvas-muted'}`}>
            {col.hidden ? '–' : letter(index)}
          </span>
          <input
            ref={inputRef}
            value={col.label}
            onChange={(e) => onChange({ ...col, label: e.target.value })}
            onBlur={(e) => {
              const v = e.target.value.trim();
              if (!v) onChange({ ...col, label: col.key });
            }}
            aria-label={`${col.key} kolonunun Excel'deki adı`}
            aria-invalid={labelError || undefined}
            spellCheck={false}
            className={[
              'min-w-0 flex-1 rounded-lg border bg-transparent px-2 py-1.5 text-base font-bold outline-none transition-colors duration-150 focus:bg-white sm:py-1 sm:text-[12.5px]',
              labelError ? 'border-red-300 bg-red-50' : 'border-transparent hover:border-slate-200 focus:border-canvas-violet',
              col.hidden ? 'text-slate-400 line-through decoration-slate-300' : 'text-canvas-ink',
            ].join(' ')}
          />
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-0.5 pl-[26px]">
          <select
            value={col.format}
            onChange={(e) => onChange({ ...col, format: e.target.value as ColumnFormat })}
            aria-label={`${col.label} kolonunun biçimi`}
            className="h-9 rounded-md border border-transparent bg-slate-100/80 px-1.5 text-[12px] font-semibold text-canvas-ink outline-none hover:bg-slate-100 focus:border-canvas-violet sm:h-6 sm:text-[11px]"
          >
            {FORMATS.map((f) => (
              <option key={f.v} value={f.v}>
                {f.v === 'auto' ? `Otomatik · ${FORMATS.find((x) => x.v === effectiveFormat(col, type))?.label ?? 'Metin'}` : f.label}
              </option>
            ))}
          </select>
          {renamed && (
            <span className="min-w-0 break-all font-mono text-[10px] leading-tight text-canvas-muted" title="Kaynaktaki kolon adı">
              ← {col.key}
            </span>
          )}
        </div>
      </div>
      <button
        type="button"
        onClick={() => onChange({ ...col, hidden: !col.hidden })}
        aria-pressed={col.hidden}
        aria-label={col.hidden ? `${col.label} kolonunu göster` : `${col.label} kolonunu gizle`}
        title={col.hidden ? 'Göster' : 'Gizle'}
        className={[
          'flex h-11 w-9 shrink-0 items-center justify-center rounded-lg transition-[color,background-color,transform] duration-150 ease-out active:scale-[0.97] sm:h-8 sm:w-8',
          col.hidden ? 'bg-slate-200/70 text-slate-500 hover:text-canvas-ink' : 'text-slate-400 hover:bg-slate-100 hover:text-canvas-ink',
        ].join(' ')}
      >
        {col.hidden ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </li>
  );
}

/** Kolon düzeninde yinelenen görünür adlar; kaydetmeden önce ekranda işaretlenir. */
export function duplicateLabels(layout: ReportColumn[]): Set<string> {
  const seen = new Map<string, number>();
  for (const c of layout) if (!c.hidden) seen.set(c.label.trim().toLocaleLowerCase('tr'), (seen.get(c.label.trim().toLocaleLowerCase('tr')) ?? 0) + 1);
  return new Set(layout.filter((c) => !c.hidden && (seen.get(c.label.trim().toLocaleLowerCase('tr')) ?? 0) > 1).map((c) => c.key));
}

export default function ExcelDraft({
  draft,
  layout,
  onChange,
}: {
  draft: ReportDraft;
  layout: ReportColumn[];
  /** Taslak ya da düzen değişti (elle, cümleyle ya da geri alarak). */
  onChange: (draft: ReportDraft, layout: ReportColumn[]) => void;
}) {
  const [instruction, setInstruction] = useState('');
  const [steps, setSteps] = useState<Step[]>([]);
  const [flash, setFlash] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<{ added: string[]; dropped: string[] } | null>(null);
  const inputs = useRef(new Map<string, HTMLInputElement>());
  const flashTimer = useRef<number | undefined>(undefined);

  useEffect(() => () => window.clearTimeout(flashTimer.current), []);

  const types = useMemo(() => Object.fromEntries(draft.columns.map((c) => [c.name, c.type])), [draft.columns]);
  const visible = layout.filter((c) => !c.hidden);
  const dupes = duplicateLabels(layout);
  const total = draft.rowCount ?? draft.records.length;
  const rows = draft.records.slice(0, PREVIEW_ROWS);
  const sample = total > rows.length;

  const markChanged = (keys: string[]) => {
    window.clearTimeout(flashTimer.current);
    setFlash(new Set(keys));
    flashTimer.current = window.setTimeout(() => setFlash(new Set()), 1400);
  };

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const onDragEnd = (e: DragEndEvent) => {
    if (!e.over || e.active.id === e.over.id) return;
    const from = layout.findIndex((c) => c.key === e.active.id);
    const to = layout.findIndex((c) => c.key === e.over!.id);
    if (from < 0 || to < 0) return;
    onChange(draft, arrayMove(layout, from, to));
  };

  const setColumn = (c: ReportColumn) => onChange(draft, layout.map((x) => (x.key === c.key ? c : x)));

  const refine = useMutation({
    mutationFn: (text: string) => reportsApi.refine({ question: draft.question, instruction: text, columns: layout }),
    onSuccess: (res, text) => {
      const next: ReportDraft = res.requery
        ? {
            ...draft,
            question: res.question,
            sql: res.sql ?? '',
            columns: res.columns ?? [],
            records: res.records ?? [],
            rowCount: res.rowCount,
            summary: res.summary ?? '',
            layout: res.layout,
            dbMs: res.dbMs,
            cached: res.cached,
            computedAt: res.computedAt,
            dbParts: res.dbParts,
          }
        : { ...draft, layout: res.layout };
      const before = new Map(layout.map((c) => [c.key, c]));
      const changed = res.layout
        .filter((c, i) => {
          const b = before.get(c.key);
          return !b || b.label !== c.label || b.hidden !== c.hidden || b.format !== c.format || layout[i]?.key !== c.key;
        })
        .map((c) => c.key);
      setSteps((h) => [...h, { before: { draft, layout }, note: res.changes.length ? res.changes.join(' · ') : text, via: res.via, requery: res.requery }]);
      setNotice(res.added.length || res.dropped.length ? { added: res.added, dropped: res.dropped } : null);
      setInstruction('');
      onChange(next, res.layout);
      markChanged(changed);
    },
  });

  const undo = () => {
    const last = steps[steps.length - 1];
    if (!last) return;
    setSteps((h) => h.slice(0, -1));
    setNotice(null);
    onChange(last.before.draft, last.before.layout);
  };

  const submit = () => {
    const t = instruction.trim();
    if (t && !refine.isPending) refine.mutate(t);
  };

  const suggestions = useMemo(() => {
    const last = visible[visible.length - 1];
    const out: string[] = [];
    if (last && visible.length > 1) out.push(`${last.label} kolonunu gizle`);
    if (last && visible.length > 1) out.push(`${last.label} kolonunu başa al`);
    out.push('Yalnız bu ayı göster');
    out.push('En yüksekten düşüğe sırala');
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout]);

  const errText = refine.error instanceof EngineAuthError ? 'Oturum gerekli.' : refine.error ? (refine.error as Error).message : null;
  const hiddenCount = layout.length - visible.length;
  const version = steps.length + 1;

  return (
    <section aria-label="Excel önizlemesi" className="space-y-3">
      {/* Başlık */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-sm">
            <FileSpreadsheet className="h-[18px] w-[18px]" />
          </span>
          <div className="min-w-0">
            <div className="text-[13.5px] font-extrabold leading-tight">Excel önizlemesi</div>
            <div className="text-[11.5px] tabular-nums text-canvas-muted">
              {nf.format(total)} satır · {visible.length} kolon{hiddenCount ? ` · ${hiddenCount} gizli` : ''}
            </div>
            <DbTimingBadge timing={draft} />
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="rounded-lg bg-slate-100 px-2 py-1 text-[11px] font-bold tabular-nums text-canvas-ink">Sürüm {version}</span>
          <button
            type="button"
            onClick={undo}
            disabled={!steps.length || refine.isPending}
            className="flex min-h-11 items-center gap-1 rounded-lg px-2.5 text-[11.5px] font-bold text-canvas-ink transition-[background-color,transform] duration-150 hover:bg-slate-100 active:scale-[0.97] disabled:opacity-40 disabled:active:scale-100 sm:min-h-8"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Geri al
          </button>
        </div>
      </div>

      {/* Örnek uyarısı */}
      <div role="note" className="flex gap-2.5 rounded-xl border border-sky-100 bg-sky-50/80 px-3 py-2.5 text-[12.5px] leading-snug text-sky-900">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-sky-600" />
        {sample ? (
          <span>
            <b>Yalnız ilk {rows.length} satır örnek olarak gösteriliyor.</b> Onayladığınızda Excel'e{' '}
            <b className="tabular-nums">{nf.format(total)} satırın tamamı</b> bu kolon düzeniyle yazılır. Hücre değerleri değiştirilemez;
            rakamlar kaynaktaki rakamlardır.
          </span>
        ) : (
          <span>
            Sonucun tamamı (<b className="tabular-nums">{nf.format(total)} satır</b>) gösteriliyor. Excel'e aynı satırlar bu kolon düzeniyle yazılır.
            Rapor her çalıştığında soru yeniden sorulur; satır sayısı o günün verisine göre değişebilir.
          </span>
        )}
      </div>

      {notice && (notice.dropped.length > 0 || notice.added.length > 0) && (
        <div className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] leading-snug text-amber-900">
          {notice.dropped.length > 0 && <div>Yeni sonuçta artık olmayan kolonlar düştü: {notice.dropped.join(', ')}.</div>}
          {notice.added.length > 0 && <div>Yeni sonuçla gelen kolonlar sona eklendi: {notice.added.join(', ')}.</div>}
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
        {/* Kolonlar */}
        {/* Telefonda önce veri görünür, kolon düzeni altta; geniş ekranda düzen solda. */}
        <div className="order-2 min-w-0 rounded-2xl border border-slate-200/70 bg-slate-50/60 p-2 lg:order-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-2 px-1.5 pb-1.5 pt-0.5">
            <span className="text-[11px] font-extrabold uppercase tracking-[.12em] text-canvas-muted">Kolonlar</span>
            <span className="text-[11px] text-canvas-muted">Sürükle · yeniden adlandır · gizle</span>
          </div>
          {/* Düzeltme sürerken düzen kilitli: yanıt eski düzenin üstüne kurulur, aradaki değişiklik ezilirdi. */}
          <fieldset disabled={refine.isPending} className="min-w-0 transition-opacity duration-150 disabled:opacity-60">
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={onDragEnd} modifiers={[restrictToVerticalAxis, restrictToParentElement]}>
              <SortableContext items={layout.map((c) => c.key)} strategy={verticalListSortingStrategy}>
                <ul className="relative space-y-1">
                  {layout.map((c) => (
                    <ColumnRow
                      key={c.key}
                      col={c}
                      index={visible.findIndex((v) => v.key === c.key)}
                      type={types[c.key]}
                      flash={flash.has(c.key)}
                      labelError={dupes.has(c.key)}
                      onChange={setColumn}
                      inputRef={(el) => {
                        if (el) inputs.current.set(c.key, el);
                        else inputs.current.delete(c.key);
                      }}
                    />
                  ))}
                </ul>
              </SortableContext>
            </DndContext>
          </fieldset>
          {dupes.size > 0 && <p className="px-1.5 pt-1.5 text-[11.5px] font-semibold text-red-700">İki kolon aynı adı taşıyamaz; birini değiştirin.</p>}
        </div>

        {/* Sayfa */}
        <div className="order-1 min-w-0 lg:order-2">
          <div
            aria-busy={refine.isPending}
            className="xd-sheet relative overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
          >
            {visible.length === 0 ? (
              <div className="px-4 py-10 text-center text-[12.5px] text-canvas-muted">Görünür kolon kalmadı. En az bir kolonu gösterin.</div>
            ) : rows.length === 0 ? (
              <div className="px-4 py-10 text-center text-[12.5px] text-canvas-muted">Soru satır döndürmedi. Aşağıdan soruyu değiştirmeyi deneyin.</div>
            ) : (
              <div className="max-h-[min(420px,60vh)] overflow-auto overscroll-contain">
                <table className="w-max min-w-full border-separate border-spacing-0 text-[12px]">
                  <thead className="sticky top-0 z-[1]">
                    <tr>
                      <th aria-hidden className="sticky left-0 z-[2] h-6 w-10 border-b border-r border-slate-200 bg-slate-100" />
                      {visible.map((c, i) => (
                        <th
                          key={c.key}
                          aria-hidden
                          className="h-6 border-b border-r border-slate-200 bg-slate-100 px-2 text-center font-mono text-[10px] font-semibold text-slate-500"
                        >
                          {letter(i)}
                        </th>
                      ))}
                    </tr>
                    <tr>
                      <th scope="col" className="sticky left-0 z-[2] w-10 border-b border-r border-slate-200 bg-slate-100 font-mono text-[10px] font-semibold text-slate-500">
                        1
                      </th>
                      {visible.map((c) => {
                        const fmt = effectiveFormat(c, types[c.key]);
                        return (
                          <th
                            key={c.key}
                            scope="col"
                            data-flash={flash.has(c.key) || undefined}
                            className={`xd-head whitespace-nowrap border-b border-r border-[#6a4cf0] px-2.5 py-1.5 font-bold text-white ${isRight(fmt) ? 'text-right' : 'text-left'}`}
                          >
                            <button
                              type="button"
                              onClick={() => inputs.current.get(c.key)?.focus()}
                              className="w-full rounded text-inherit outline-none focus-visible:ring-2 focus-visible:ring-white/70"
                              title="Adını düzenle"
                            >
                              {c.label || c.key}
                            </button>
                          </th>
                        );
                      })}
                    </tr>
                  </thead>
                  <tbody className="xd-body">
                    {rows.map((r, ri) => (
                      <tr key={ri} className="hover:bg-violet-50/40">
                        <th scope="row" className="sticky left-0 border-b border-r border-slate-200 bg-slate-50 px-1 text-center font-mono text-[10px] font-medium text-slate-500">
                          {ri + 2}
                        </th>
                        {visible.map((c) => {
                          const fmt = effectiveFormat(c, types[c.key]);
                          return (
                            <td
                              key={c.key}
                              className={`max-w-[320px] truncate whitespace-nowrap border-b border-r border-slate-100 px-2.5 py-1 ${
                                isRight(fmt) ? 'text-right font-mono tabular-nums' : ''
                              }`}
                            >
                              {formatCell(r[c.key], fmt, types[c.key])}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {refine.isPending && (
              <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center pt-12">
                <span className="flex items-center gap-2 rounded-full bg-white/95 px-3 py-1.5 text-[12px] font-bold text-canvas-ink shadow-md ring-1 ring-slate-200">
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-canvas-violet" />
                  Değişiklik uygulanıyor…
                </span>
              </div>
            )}
          </div>
          {/* Sayfa sekmesi */}
          <div className="flex items-center justify-between gap-2 px-1 pt-1.5 text-[11px] text-canvas-muted">
            <span className="flex items-center gap-1.5">
              <span className="rounded-b-md border-x border-b border-slate-200 bg-white px-2.5 py-0.5 font-bold text-emerald-700 shadow-sm">Rapor</span>
            </span>
            <span className="tabular-nums">
              {sample ? `${rows.length} / ${nf.format(total)} satır gösteriliyor` : `${nf.format(total)} satır`}
            </span>
          </div>
        </div>
      </div>

      {/* Cümleyle düzeltme */}
      <div className="rounded-2xl border border-slate-200/80 bg-white/90 p-2.5 shadow-sm focus-within:border-canvas-violet/60">
        <label htmlFor="xd-refine" className="flex items-center gap-1.5 px-1 text-[11px] font-extrabold uppercase tracking-[.12em] text-canvas-muted">
          <Sparkles className="h-3.5 w-3.5 text-canvas-violet" />
          Değişiklik iste
        </label>
        <div className="mt-1.5 flex items-end gap-2">
          <textarea
            id="xd-refine"
            rows={2}
            value={instruction}
            disabled={refine.isPending}
            onChange={(e) => setInstruction(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="Örn. “iade kolonunu gizle”, “tutar adını Net Ciro yap”, “yalnız Ağustos'u göster”"
            className="min-h-11 flex-1 resize-none rounded-xl bg-transparent px-1.5 py-1 text-base font-medium outline-none placeholder:text-slate-400 disabled:opacity-60 sm:text-[13px]"
          />
          <button
            type="button"
            onClick={submit}
            disabled={!instruction.trim() || refine.isPending}
            aria-label="Değişikliği uygula"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-canvas-violet text-white shadow-md transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-40 disabled:active:scale-100 sm:h-9 sm:w-9"
          >
            {refine.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-4 w-4" />}
          </button>
        </div>
        {!instruction && !refine.isPending && (
          <div className="mt-2 flex flex-wrap gap-1.5 px-0.5">
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setInstruction(s)}
                className="min-h-9 rounded-full bg-slate-100 px-2.5 text-[11.5px] font-semibold text-canvas-ink transition-colors duration-150 hover:bg-violet-100 hover:text-canvas-violet sm:min-h-7"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {errText && <div className="mt-2 rounded-lg bg-red-50 px-2.5 py-1.5 text-[12px] font-semibold text-red-700">{errText}</div>}
        <p aria-live="polite" className="mt-2 px-1 text-[11px] leading-snug text-canvas-muted">
          {refine.isPending
            ? 'Uygulanıyor… Kolon komutları anında biter; veri değişiyorsa model soruyu yeniden yazar ve veri yeniden çekilir, bu bir dakikayı bulabilir.'
            : 'Kolon adı, sırası, biçimi ve gizleme anında uygulanır. Filtre, dönem ya da yeni ölçü soruyu değiştirir ve veri yeniden çekilir.'}
        </p>
      </div>

      {/* Değişiklik geçmişi */}
      {steps.length > 0 && (
        <ol className="space-y-1 border-l-2 border-slate-100 pl-3" aria-label="Değişiklik geçmişi">
          {steps
            .map((st, i) => ({ st, i }))
            .reverse()
            .map(({ st, i }) => (
              <li key={i} className={`text-[12px] leading-snug ${i === steps.length - 1 ? 'text-canvas-ink' : 'text-canvas-muted'}`}>
                <span className="mr-1.5 font-mono text-[10.5px] font-bold tabular-nums">S{i + 2}</span>
                {st.note}
                {st.requery ? (
                  <span className="ml-1.5 rounded bg-violet-50 px-1 text-[10px] font-bold text-canvas-violet">veri yenilendi</span>
                ) : st.via === 'rules' ? (
                  <span className="ml-1.5 inline-flex items-center gap-0.5 rounded bg-emerald-50 px-1 text-[10px] font-bold text-emerald-700">
                    <Zap className="h-2.5 w-2.5" />
                    anında
                  </span>
                ) : null}
              </li>
            ))}
          <li className="text-[12px] text-canvas-muted">
            <span className="mr-1.5 font-mono text-[10.5px] font-bold">S1</span>İlk önizleme
          </li>
        </ol>
      )}
    </section>
  );
}
