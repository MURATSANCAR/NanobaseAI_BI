import { useId, type ReactNode } from 'react';
import { press } from '../shared';
import { elementsApi, useElementCatalog } from './api';
import { Section, Thumb, useDebounced } from './controls';
import { EFFECT_LABEL, paintOf, roleColor, setEffectStyle, swatches } from './model';
import { ParamControl } from './ShapeInspector';
import { EFFECT_STYLES, type Effect, type Palette, type RoleColors } from './types';

/** «Efekt yazı» paneli: hazır stiller (kitabın paleti ve fontlarıyla sunucu önizlemesi), seçili stilin ayarları
 *  (katalogdaki parametreler: kavis, dalga sayısı, dış çizgi, gölge, derinlik, patlama, harf renkleri) ve değerleri
 *  anında gösteren yerel önizleme. Her değişiklik `onChange(effect)`; «Düz yazı» → `onChange(null)`. Kaydetme
 *  çağıranın otomatik kayıt sırasından geçer. */

export type EffectTextPanelProps = {
  jobId: string;
  /** Serbest yazının `effect` alanı; null → düz yazı. */
  value: Effect | null;
  onChange: (effect: Effect | null) => void;
  palette?: Palette | null;
  /** Önizlemede görünen yazı (serbest yazının metni). */
  text?: string;
  /** Harflerin ana rengi (serbest yazının ilk parçasının rengi); yoksa paletin metin rengi. */
  textColor?: string | null;
  /** Paletin özeti: palet değişince stil önizlemeleri ve rol renkleri tazelenir. */
  rev?: string | number | null;
  className?: string;
};

const n1 = (v: number) => new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(v);
const curveText = (v: number) => (v === 0 ? 'düz' : v > 0 ? `yukarı ${n1(v)}` : `aşağı ${n1(-v)}`);

export default function EffectTextPanel({ jobId, value, onChange, palette, text, textColor, rev, className = '' }: EffectTextPanelProps) {
  const q = useElementCatalog(jobId, rev);
  const roles = q.data?.roles;
  const sample = (text ?? '').trim() || 'Merhaba!';
  // Stil karoları yalnız örnek gösterir: yazının ilk satırı (üstteki canlı önizleme tamamını gösterir). Karo küçük
  // olduğundan ilk 40 harf yeter; bu yalnız görünüm, kaydedilen yazıya dokunmaz.
  const tileText = Array.from(sample.split('\n')[0]).slice(0, 40).join('');
  const previewText = useDebounced(tileText, 400);
  const sw = swatches(palette, roles);
  const p = value?.params ?? {};
  const spec = (s: string) => q.data?.effects.find((e) => e.style === s);
  const set = (k: string, v: unknown) => value && onChange({ style: value.style, params: { ...value.params, [k]: v } });
  const params = value ? spec(value.style)?.params ?? [] : [];
  const color = paintOf(textColor, palette, roles) || roleColor(palette, 'accent', roles);

  return (
    <div className={`flex min-w-0 flex-col gap-3 ${className}`}>
      <Section title="Efekt yazı">
        <LivePreview effect={value} text={sample} color={color} palette={palette} roles={roles} />
        <div role="radiogroup" aria-label="Efekt stili" className="grid grid-cols-3 gap-1.5">
          <StyleTile label="Düz yazı" on={!value} onClick={() => onChange(null)}>
            <span className="flex h-full items-center justify-center text-[15px] font-extrabold text-canvas-ink">Aa</span>
          </StyleTile>
          {EFFECT_STYLES.map((s) => (
            <StyleTile key={s} label={spec(s)?.name ?? EFFECT_LABEL[s]} on={value?.style === s}
              onClick={() => onChange(setEffectStyle(s, value, spec(s), palette, roles))}>
              <Thumb src={elementsApi.effectPreviewUrl(jobId, s, 240, previewText, rev)} alt="" fallback={EFFECT_LABEL[s]} className="h-full w-full" />
            </StyleTile>
          ))}
        </div>
      </Section>

      {value && params.length > 0 && (
        <Section title={`${spec(value.style)?.name ?? EFFECT_LABEL[value.style]} ayarları`}>
          <div className="flex flex-col gap-3">
            {params.map((prm) => (
              <ParamControl key={prm.key} param={prm} value={p[prm.key] !== undefined ? p[prm.key] : prm.default}
                onChange={(v) => set(prm.key, v)} swatches={sw} palette={palette} roles={roles}
                format={prm.key === 'curve' ? curveText : undefined} />
            ))}
          </div>
        </Section>
      )}
      {value && q.error && <p className="text-[11px] text-amber-700">Efekt ayarları okunamadı; stil kitabın varsayılanlarıyla çizilir.</p>}
      <p className="text-[11px] leading-snug text-canvas-muted">Üstteki önizleme ayarları anında gösterir; sayfadaki kesin hâli kitabın yazı tipiyle dizilir.</p>
    </div>
  );
}

function StyleTile({ label, on, onClick, children }: { label: string; on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" role="radio" aria-checked={on} onClick={onClick}
      className={`flex flex-col gap-1 rounded-xl border p-1 text-center ${press} ${on ? 'border-canvas-violet bg-violet-50/60 ring-2 ring-canvas-violet/25' : 'border-slate-200 bg-white/80'}`}>
      <span className="block aspect-[2/1] w-full overflow-hidden rounded-lg bg-white">{children}</span>
      <span className="text-[11px] font-bold leading-tight">{label}</span>
    </button>
  );
}

// ---------------------------------------------------------------- yerel önizleme
// Değerleri sunucuya gitmeden gösterir (kaydırıcı sürüklenirken). Ölçek: 1 mm ≈ 4 birim; yazı 40 birim.

const K = 4;
const W = 320;
const H = 132;

export function LivePreview({ effect, text, color, palette, roles }: {
  effect: Effect | null; text: string; color: string; palette?: Palette | null; roles?: RoleColors | null;
}) {
  const uid = useId().replace(/:/g, '');
  const chars = Array.from(text);
  // Rol adları («sun», «white») kitabın rengine çevrilir; boş renk «yok».
  const raw = effect?.params ?? {};
  const c = (v: unknown) => paintOf(typeof v === 'string' ? v : null, palette, roles) ?? undefined;
  const p = {
    ...raw, outline: c(raw.outline), shadow: c(raw.shadow), burst_fill: c(raw.burst_fill), burst_stroke: c(raw.burst_stroke),
    colors: Array.isArray(raw.colors) ? raw.colors.map((x) => c(x) ?? color) : undefined,
  };
  const cy = 78;
  const font = { fontFamily: '"Plus Jakarta Sans", system-ui, sans-serif', fontWeight: 800, fontSize: Math.max(18, Math.min(44, 520 / Math.max(6, chars.length))) };
  const outline = p.outline && (p.outline_w ?? 0) > 0 ? { stroke: p.outline, strokeWidth: (p.outline_w ?? 0) * K * 2, paintOrder: 'stroke' as const, strokeLinejoin: 'round' as const } : {};
  const cols = p.colors?.length ? p.colors : [color];
  const style = effect?.style;

  let body: ReactNode;
  if (style === 'arc' || style === 'wave') {
    const a = (p.curve ?? 0) * (style === 'arc' ? 70 : 22);
    const d = style === 'arc'
      ? `M 24 ${cy + a / 2} Q ${W / 2} ${cy - a * 1.5} ${W - 24} ${cy + a / 2}`
      : `M 8 ${cy} Q 48 ${cy - a} 88 ${cy} T 168 ${cy} T 248 ${cy} T 328 ${cy}`;
    body = (
      <>
        <path id={`p${uid}`} d={d} fill="none" />
        <text {...font} fill={color} {...outline} textAnchor="middle">
          <textPath href={`#p${uid}`} startOffset="50%">{text}</textPath>
        </text>
      </>
    );
  } else if (style === 'shadow' || style === 'stacked') {
    const dx = (p.shadow_dx ?? 0) * K;
    const dy = (p.shadow_dy ?? 0) * K;
    const layers = style === 'stacked' ? [4, 3, 2, 1] : [1];
    body = (
      <>
        {layers.map((i) => (
          <text key={i} x={W / 2 + dx * (style === 'stacked' ? i / 2 : 1)} y={cy + dy * (style === 'stacked' ? i / 2 : 1)} {...font}
            fill={p.shadow ?? '#000'} opacity={style === 'stacked' ? 1 - (i - 1) * 0.15 : 1} textAnchor="middle">{text}</text>
        ))}
        <text x={W / 2} y={cy} {...font} fill={color} textAnchor="middle">{text}</text>
      </>
    );
  } else if (style === 'bounce' || style === 'rainbow') {
    const amp = style === 'bounce' ? 7 : 0;
    let k = 0;
    body = (
      <text x={W / 2} y={cy} {...font} textAnchor="middle">
        {chars.map((c, i) => {
          const white = /\s/.test(c);
          const fill = white ? color : cols[k++ % cols.length];
          const dy = i === 0 ? -amp / 2 : i % 2 ? amp : -amp;
          return <tspan key={i} dy={amp ? dy : undefined} fill={fill}>{c}</tspan>;
        })}
      </text>
    );
  } else if (style === 'burst') {
    const spikes = 14;
    const rx = W / 2 - 14;
    const ry = H / 2 - 8;
    const pts = Array.from({ length: spikes * 2 }, (_, i) => {
      const t = (i / (spikes * 2)) * Math.PI * 2;
      const r = i % 2 ? 0.78 : 1;
      return `${(W / 2 + Math.cos(t) * rx * r).toFixed(1)},${(H / 2 + Math.sin(t) * ry * r).toFixed(1)}`;
    }).join(' ');
    body = (
      <g transform={`rotate(${p.angle ?? 0} ${W / 2} ${H / 2})`}>
        <polygon points={pts} fill={p.burst_fill ?? '#FAC775'} stroke={p.burst_stroke ?? color} strokeWidth={2.4} strokeLinejoin="round" />
        <text x={W / 2} y={H / 2 + font.fontSize * 0.35} {...font} fontSize={font.fontSize * 0.8} fill={color} textAnchor="middle">{text}</text>
      </g>
    );
  } else {
    body = <text x={W / 2} y={cy} {...font} fill={color} {...outline} textAnchor="middle">{text}</text>;
  }

  return (
    <figure className="m-0">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Önizleme: ${effect ? EFFECT_LABEL[effect.style] : 'düz yazı'} — ${text}`}
        className="block h-auto w-full rounded-xl border border-slate-200 bg-slate-100">
        {body}
      </svg>
    </figure>
  );
}
