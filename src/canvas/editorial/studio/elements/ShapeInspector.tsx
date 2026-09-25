import { useEffect, useId, useState } from 'react';
import { AlertTriangle, ArrowDownToLine, ArrowUpToLine, RotateCcw, Shuffle, Trash2 } from 'lucide-react';
import { ghostBtn, press } from '../shared';
import { elementsApi, useElementCatalog } from './api';
import { ColorChips, ColorList, Field, Section, Segmented, Slider, Thumb, Toggle } from './controls';
import { ROLE_LABEL, applyStyle, paintOf, runsText, editRuns, styleOf, styleRuns, swatches, type Swatch } from './model';
import type { Box, CatalogParam, ColorRole, Palette, RoleColors, Run, Shape } from './types';

/** Seçili şeklin özellik paneli: hazır biçim, renkler (boş = kitabın paletinden otomatik), türe özel parametreler,
 *  yazı taşıyan türlerde yazı ve paletten renk, konum/boyut (mm), saydamlık, döndürme, aynalama, katman sırası.
 *  Her değişiklik `onChange(shape)`; telefonda tuval yalnız görüntülediği için konum/boyut da buradan düzenlenir. */

export type ShapeInspectorProps = {
  jobId: string;
  value: Shape;
  onChange: (shape: Shape) => void;
  palette?: Palette | null;
  /** Paletin özeti: palet değişince önizleme ve rol renkleri tazelenir. */
  rev?: string | number | null;
  /** Verilirse «Öne al / Arkaya al» düğmeleri görünür (z'yi çağıran komşu öğeye göre değiştirir). */
  onZ?: (dir: 'front' | 'back') => void;
  /** Verilirse «Sayfadan kaldır» düğmesi görünür. */
  onRemove?: () => void;
  className?: string;
};

const WEIGHTS: { value: number; label: string }[] = [
  { value: 400, label: 'Normal' }, { value: 700, label: 'Kalın' }, { value: 800, label: 'Çok kalın' },
];
const FONTS: { value: 'body' | 'heading'; label: string }[] = [{ value: 'body', label: 'Metin' }, { value: 'heading', label: 'Başlık' }];
const NONE = { hex: '#FFFFFF00', name: 'Yok' };
/** Dönüş 0–360 saklanır; ekranda −180…180. */
const signedDeg = (v: number) => (v > 180 ? v - 360 : v);

export default function ShapeInspector({ jobId, value, onChange, palette, rev, onZ, onRemove, className = '' }: ShapeInspectorProps) {
  const q = useElementCatalog(jobId, rev);
  const roles = q.data?.roles;
  const item = q.data?.items.find((i) => i.kind === value.kind);
  const sw = swatches(palette, roles);
  const params = value.params ?? {};
  const set = (patch: Partial<Shape>) => onChange({ ...value, ...patch });
  const setParam = (k: string, v: unknown) => onChange({ ...value, params: { ...params, [k]: v } });
  const auto = (r: ColorRole | 'none' | null | undefined) =>
    !r || r === 'none' ? NONE : { hex: paintOf(r, palette, roles) ?? '#FFFFFF', name: ROLE_LABEL[r] };
  const style = styleOf(item, params);
  const name = item?.name ?? value.kind;
  const hasText = item ? item.text : !!value.runs?.length;
  const strokeW = value.stroke_w ?? item?.stroke_w ?? 0.6;
  const opacity = value.opacity ?? 1;

  return (
    <div className={`flex min-w-0 flex-col gap-3 ${className}`}>
      <div className="flex items-center gap-3">
        <Thumb src={elementsApi.previewUrl(jobId, value.kind, 128, style?.value, rev)} alt="" fallback={name} className="h-14 w-14 shrink-0 rounded-xl border border-slate-200" />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[15px] font-extrabold">{style?.label ?? name}</h2>
          <p className="text-[11.5px] text-canvas-muted">Süs / şekil · katman {value.z}</p>
        </div>
      </div>

      {value.overflow && (
        <p className="flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          Yazı şekle sığmıyor. Puntoyu küçültün ya da «Şekle sığdır»ı açın.
        </p>
      )}

      {(onZ || onRemove) && (
        <div className="flex flex-wrap gap-1.5">
          {onZ && (
            <>
              <button type="button" className={ghostBtn} onClick={() => onZ('front')}><ArrowUpToLine className="h-4 w-4" aria-hidden />Öne al</button>
              <button type="button" className={ghostBtn} onClick={() => onZ('back')}><ArrowDownToLine className="h-4 w-4" aria-hidden />Arkaya al</button>
            </>
          )}
          {onRemove && (
            <button type="button" onClick={onRemove}
              className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-rose-200 bg-white/80 px-3.5 text-[13px] font-bold text-rose-700 ${press}`}>
              <Trash2 className="h-4 w-4" aria-hidden />Sayfadan kaldır
            </button>
          )}
        </div>
      )}

      {item && item.styles.length > 1 && (
        <Section title="Hazır biçim">
          <Segmented label="Hazır biçim" value={style?.value ?? null} options={item.styles}
            onChange={(v) => { const st = item.styles.find((s) => s.value === v); if (st) onChange(applyStyle(value, st)); }} />
        </Section>
      )}

      <Section title="Renkler">
        <Field label="Dolgu">
          <ColorChips label="Dolgu rengi" value={value.fill ?? null} swatches={sw} auto={auto(item ? item.roles.fill : 'soft')} onChange={(hex) => set({ fill: hex })} />
        </Field>
        <Field label="Çizgi">
          <ColorChips label="Çizgi rengi" value={value.stroke ?? null} swatches={sw} auto={auto(item ? item.roles.stroke : 'ink')} onChange={(hex) => set({ stroke: hex })} />
        </Field>
        <Slider label="Çizgi kalınlığı" unit="mm" value={strokeW} min={0} max={Math.max(3, strokeW * 2)} step={0.1} hardMin={0} onChange={(v) => set({ stroke_w: v })} />
      </Section>

      {item && item.params.length > 0 && (
        <Section title="Ayarlar">
          <div className="flex flex-col gap-3">
            {item.params.map((p) => (
              <ParamControl key={p.key} param={p} value={params[p.key] ?? p.default} onChange={(v) => setParam(p.key, v)} swatches={sw} palette={palette} roles={roles} />
            ))}
          </div>
        </Section>
      )}

      {hasText && (
        <Section title="Yazı">
          <RunsEditor runs={value.runs ?? []} onChange={(runs) => set({ runs })} swatches={sw}
            autoText={auto(item?.roles.text ?? 'ink')} />
          <Toggle label="Şekle sığdır" checked={value.text_size == null}
            onChange={(fit) => set({ text_size: fit ? null : item?.text_size ?? 18 })} />
          {value.text_size != null && (
            <Slider label="Punto" unit="pt" value={value.text_size} min={6} max={Math.max(72, value.text_size)} step={1} hardMin={1}
              onChange={(v) => set({ text_size: v })} />
          )}
        </Section>
      )}

      <Section title="Konum ve boyut">
        <BoxFields box={value.box} onChange={(box) => set({ box })} />
      </Section>

      <Section title="Görünüm">
        <Slider label="Saydamlık" unit="%" value={Math.round(opacity * 100)} min={0} max={100} step={1} hardMin={0} hardMax={100}
          onChange={(v) => set({ opacity: v / 100 })} format={(v) => `%${v} görünür`} />
        <Slider label="Döndürme" unit="°" value={signedDeg(value.rotate ?? 0)} min={-180} max={180} step={1} hardMin={-180} hardMax={180} onChange={(v) => set({ rotate: v })} />
        <div className="flex flex-wrap gap-1.5">
          <Toggle label="Aynala" checked={!!value.flip} onChange={(flip) => set({ flip })} />
          <button type="button" className={ghostBtn} disabled={!value.rotate} onClick={() => set({ rotate: 0 })}>
            <RotateCcw className="h-4 w-4" aria-hidden />Düz
          </button>
        </div>
        {value.flip && hasText && <p className="text-[11px] text-canvas-muted">Aynalamada şekil döner; üstündeki yazı düz okunur.</p>}
      </Section>
      {!item && q.error && <p className="text-[11px] text-amber-700">Öğe kataloğu okunamadı; türe özel ayarlar gösterilemiyor.</p>}
    </div>
  );
}

/** Katalog parametresinin denetimi (şekil ve efekt panelleri ortak). Renk alanında boş değer «yok» demektir; rol adı
 *  kitabın rengine çevrilip gösterilir. Sayı alanında kaydırıcı katalogdaki min/max'tan, açık uçta makul bir aralıktan
 *  gelir; sayı kutusuna daha büyük değer yazılabilir (sınır yalnız katalogdaki doğrulama sınırı). */
export function ParamControl({ param, value, onChange, swatches: sw, palette, roles, format }: {
  param: CatalogParam; value: unknown; onChange: (v: unknown) => void; swatches: Swatch[]; palette?: Palette | null;
  roles?: RoleColors | null; format?: (v: number) => string;
}) {
  const id = useId();
  if (param.type === 'choice' && param.options) {
    return <Field label={param.label}><Segmented label={param.label} value={String(value ?? '')} options={param.options} onChange={onChange} /></Field>;
  }
  if (param.type === 'bool') return <Toggle label={param.label} checked={!!value} onChange={onChange} />;
  if (param.type === 'color') {
    return (
      <Field label={param.label}>
        <ColorChips label={param.label} value={paintOf(value as string | null, palette, roles)} swatches={sw} auto={NONE} onChange={onChange} />
      </Field>
    );
  }
  if (param.type === 'colors') {
    const list = Array.isArray(value) ? (value as string[]).map((c) => paintOf(c, palette, roles) ?? c) : [];
    return (
      <Field label={`${param.label}${list.length ? ` (${list.length})` : ''}`}>
        <ColorList label={param.label} value={list} swatches={sw} onChange={(v) => onChange(v.length ? v : null)} />
        {!list.length && <p className="text-[11px] text-canvas-muted">Renk seçilmezse harfler kitabın paletinden sırayla boyanır.</p>}
      </Field>
    );
  }
  if (param.type === 'number' || param.type === 'int') {
    const v = typeof value === 'number' ? value : Number(value) || 0;
    const int = param.type === 'int';
    const min = param.min ?? 0;
    const max = param.max ?? Math.max(min + (int ? 10 : 1), Math.abs(v) * 3, typeof param.default === 'number' ? Math.abs(param.default) * 3 : 0);
    const seed = /seed|tohum/i.test(param.key);
    return (
      <div className="flex flex-col gap-1">
        <Slider label={param.label} unit={param.unit} value={v} min={min} max={max} step={param.step ?? (int ? 1 : 0.1)}
          hardMin={param.min} hardMax={param.max} format={format} onChange={(n) => onChange(int ? Math.round(n) : n)} />
        {seed && (
          <button type="button" className={`${ghostBtn} self-start`} onClick={() => onChange(Math.floor(Math.random() * 100000))}>
            <Shuffle className="h-4 w-4" aria-hidden />Yeniden dağıt
          </button>
        )}
      </div>
    );
  }
  return (
    <label htmlFor={id} className="flex flex-col gap-1">
      <span className="text-[12px] font-bold text-canvas-ink">{param.label}</span>
      <input id={id} value={String(value ?? '')} onChange={(e) => onChange(e.target.value)}
        className="h-10 rounded-xl border border-slate-200 bg-white/90 px-3 text-base outline-none focus:border-canvas-violet sm:text-[13px]" />
    </label>
  );
}

/** Düz metin kutusu + seçime biçim. Seçim yoksa biçim bütün yazıya uygulanır. */
function RunsEditor({ runs, onChange, swatches: sw, autoText }: {
  runs: Run[]; onChange: (runs: Run[]) => void; swatches: Swatch[]; autoText: { hex: string; name: string };
}) {
  const id = useId();
  const [sel, setSel] = useState<[number, number]>([0, 0]);
  const text = runsText(runs);
  useEffect(() => setSel(([s, e]) => [Math.min(s, text.length), Math.min(e, text.length)]), [text.length]);
  const ranged = sel[0] !== sel[1];
  const at = runsAt(runs, sel[0], ranged);
  const apply = (patch: Partial<Run>) => onChange(styleRuns(runs, sel[0], sel[1], patch));
  const track = (el: HTMLTextAreaElement) => setSel([el.selectionStart, el.selectionEnd]);

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-[12px] font-bold text-canvas-ink">Metin</label>
      <textarea id={id} value={text} rows={2} onChange={(e) => { onChange(editRuns(runs, e.target.value)); track(e.target); }}
        onSelect={(e) => track(e.currentTarget)}
        className="rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-base outline-none focus:border-canvas-violet sm:text-[13px]" />
      <p className="text-[11px] text-canvas-muted" aria-live="polite">
        {ranged ? `Seçili ${sel[1] - sel[0]} harfe uygulanır.` : 'Seçim yok: biçim bütün yazıya uygulanır. Bir bölümü seçip yalnız ona renk verebilirsiniz.'}
      </p>
      <Field label="Renk">
        <ColorChips label="Yazı rengi" value={at?.color ?? null} swatches={sw} auto={autoText} onChange={(hex) => apply({ color: hex })} />
      </Field>
      <Field label="Kalınlık">
        <Segmented label="Kalınlık" value={at?.weight ?? 400} options={WEIGHTS} onChange={(weight) => apply({ weight })} />
      </Field>
      <Field label="Yazı tipi">
        <Segmented label="Yazı tipi" value={at?.font ?? 'body'} options={FONTS} onChange={(font) => apply({ font })} />
      </Field>
      {text && (
        <p className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-[15px] leading-snug" aria-label="Yazının görünümü">
          {runs.map((r, i) => (
            <span key={i} style={{ color: r.color ?? autoText.hex, fontWeight: r.weight ?? 400 }}>{r.text}</span>
          ))}
        </p>
      )}
    </div>
  );
}

/** Seçimin başındaki (seçim yoksa ilk) parça: denetimlerde o anki biçim gösterilir. */
function runsAt(runs: Run[], pos: number, ranged: boolean): Run | undefined {
  if (!ranged) return runs[0];
  let at = 0;
  for (const r of runs) {
    if (pos < at + r.text.length) return r;
    at += r.text.length;
  }
  return runs[runs.length - 1];
}

function BoxFields({ box, onChange }: { box: Box; onChange: (b: Box) => void }) {
  const fields: { k: keyof Box; label: string }[] = [
    { k: 'x', label: 'Soldan' }, { k: 'y', label: 'Üstten' }, { k: 'w', label: 'Genişlik' }, { k: 'h', label: 'Yükseklik' },
  ];
  return (
    <div className="grid grid-cols-2 gap-2">
      {fields.map((f) => (
        <NumberField key={f.k} label={f.label} value={box[f.k]} min={f.k === 'w' || f.k === 'h' ? 1 : undefined}
          onChange={(v) => onChange({ ...box, [f.k]: v })} />
      ))}
    </div>
  );
}

function NumberField({ label, value, onChange, min }: { label: string; value: number; onChange: (v: number) => void; min?: number }) {
  const id = useId();
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);
  const commit = () => {
    const n = Number(draft.replace(',', '.'));
    if (!Number.isFinite(n)) return setDraft(String(value));
    const v = Math.round((min !== undefined ? Math.max(min, n) : n) * 10) / 10;
    if (v !== value) onChange(v);
    setDraft(String(v));
  };
  return (
    <label htmlFor={id} className="flex flex-col gap-1">
      <span className="text-[11.5px] font-bold text-canvas-ink">{label} <span className="font-normal text-canvas-muted">mm</span></span>
      <input id={id} inputMode="decimal" value={draft} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
        onKeyDown={(e) => e.key === 'Enter' && commit()}
        className="h-10 rounded-xl border border-slate-200 bg-white/90 px-3 font-mono text-base tabular-nums outline-none focus:border-canvas-violet sm:text-[13px]" />
    </label>
  );
}

