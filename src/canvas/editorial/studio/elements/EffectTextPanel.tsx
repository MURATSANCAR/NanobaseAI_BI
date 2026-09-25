import { useId, type ReactNode } from 'react';
import { press } from '../shared';
import { elementsApi } from './api';
import { ColorChips, ColorList, Field, Section, Slider, Thumb, useDebounced } from './controls';
import { EFFECT_LABEL, roleColor, setEffectStyle, swatches } from './model';
import { EFFECT_STYLES, type Effect, type EffectParams, type EffectStyle, type Palette } from './types';

/** «Efekt yazı» paneli: hazır stiller (kitabın paleti ve fontlarıyla sunucu önizlemesi), seçili stilin ayarları
 *  (kavis, dış çizgi, gölge, patlama, harf renkleri) ve değerleri anında gösteren yerel önizleme. Her değişiklik
 *  `onChange(effect)`; «Düz yazı» → `onChange(null)`. Kaydetme çağıranın otomatik kayıt sırasından geçer. */

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
  /** Palet değişince stil önizlemelerini tazelemek için. */
  rev?: string | number | null;
  className?: string;
};

/** Stil başına gösterilen ayarlar. */
const CONTROLS: Record<EffectStyle, (keyof EffectParams | 'outline_group' | 'shadow_group')[]> = {
  burst: ['burst_fill', 'burst_stroke', 'angle'],
  wave: ['curve', 'outline_group'],
  arc: ['curve', 'outline_group'],
  shadow: ['shadow_group'],
  outline: ['outline_group'],
  stacked: ['shadow_group'],
  bounce: ['colors'],
  rainbow: ['colors'],
};

const n1 = (v: number) => new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(v);

export default function EffectTextPanel({ jobId, value, onChange, palette, text, textColor, rev, className = '' }: EffectTextPanelProps) {
  const sample = (text ?? '').trim() || 'Merhaba!';
  // Stil karoları yalnız örnek gösterir: yazının ilk satırından en çok 40 harf (üstteki canlı önizleme tamamını gösterir).
  const tileText = Array.from(sample.split('\n')[0]).slice(0, 40).join('');
  const previewText = useDebounced(tileText, 400);
  const sw = swatches(palette);
  const p = value?.params ?? {};
  const set = (patch: EffectParams) => value && onChange({ style: value.style, params: { ...value.params, ...patch } });
  const controls = value ? CONTROLS[value.style] : [];

  return (
    <div className={`flex min-w-0 flex-col gap-3 ${className}`}>
      <Section title="Efekt yazı">
        <LivePreview effect={value} text={sample} color={textColor || roleColor(palette, 'ink')} />
        <div role="radiogroup" aria-label="Efekt stili" className="grid grid-cols-3 gap-1.5">
          <StyleTile label="Düz yazı" on={!value} onClick={() => onChange(null)}>
            <span className="flex h-full items-center justify-center text-[15px] font-extrabold text-canvas-ink">Aa</span>
          </StyleTile>
          {EFFECT_STYLES.map((s) => (
            <StyleTile key={s} label={EFFECT_LABEL[s]} on={value?.style === s} onClick={() => onChange(setEffectStyle(s, value, palette))}>
              <Thumb src={elementsApi.effectPreviewUrl(jobId, s, 240, previewText, rev)} alt="" fallback={EFFECT_LABEL[s]} className="h-full w-full" />
            </StyleTile>
          ))}
        </div>
      </Section>

      {value && controls.length > 0 && (
        <Section title={`${EFFECT_LABEL[value.style]} ayarları`}>
          <div className="flex flex-col gap-3">
            {controls.includes('curve') && (
              <Slider label={value.style === 'wave' ? 'Dalga' : 'Kavis'} value={p.curve ?? 0} min={-1} max={1} step={0.05}
                hardMin={-1} hardMax={1} format={(v) => (v === 0 ? 'düz' : v > 0 ? `yukarı ${n1(v)}` : `aşağı ${n1(-v)}`)}
                onChange={(v) => set({ curve: v })} />
            )}
            {controls.includes('outline_group') && (
              <>
                <Field label="Dış çizgi rengi">
                  <ColorChips label="Dış çizgi rengi" value={p.outline ?? null} swatches={sw} onChange={(hex) => set({ outline: hex ?? undefined, outline_w: hex ? p.outline_w ?? 0.8 : 0 })} />
                </Field>
                <Slider label="Dış çizgi kalınlığı" unit="mm" value={p.outline_w ?? 0} min={0} max={3} step={0.1} hardMin={0} onChange={(v) => set({ outline_w: v })} />
              </>
            )}
            {controls.includes('shadow_group') && (
              <>
                <Field label={value.style === 'stacked' ? 'Katman rengi' : 'Gölge rengi'}>
                  <ColorChips label="Gölge rengi" value={p.shadow ?? null} swatches={sw} onChange={(hex) => hex && set({ shadow: hex })} />
                </Field>
                <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2">
                  <Slider label="Sağa kayma" unit="mm" value={p.shadow_dx ?? 0} min={-3} max={3} step={0.1} onChange={(v) => set({ shadow_dx: v })} />
                  <Slider label="Aşağı kayma" unit="mm" value={p.shadow_dy ?? 0} min={-3} max={3} step={0.1} onChange={(v) => set({ shadow_dy: v })} />
                </div>
              </>
            )}
            {controls.includes('burst_fill') && (
              <Field label="Patlama dolgusu">
                <ColorChips label="Patlama dolgusu" value={p.burst_fill ?? null} swatches={sw} onChange={(hex) => hex && set({ burst_fill: hex })} />
              </Field>
            )}
            {controls.includes('burst_stroke') && (
              <Field label="Patlama çizgisi">
                <ColorChips label="Patlama çizgisi" value={p.burst_stroke ?? null} swatches={sw} onChange={(hex) => hex && set({ burst_stroke: hex })} />
              </Field>
            )}
            {controls.includes('angle') && (
              <Slider label="Eğim" unit="°" value={p.angle ?? 0} min={-30} max={30} step={1} hardMin={-180} hardMax={180} onChange={(v) => set({ angle: v })} />
            )}
            {controls.includes('colors') && (
              <Field label={`Harf renkleri · sırayla döner${p.colors?.length ? ` (${p.colors.length})` : ''}`}>
                <ColorList label="Harf renkleri" value={p.colors ?? []} swatches={sw} onChange={(colors) => set({ colors })} />
                {!p.colors?.length && <p className="text-[11px] text-amber-700">En az bir renk seçin; seçilmezse harfler metin renginde kalır.</p>}
              </Field>
            )}
          </div>
        </Section>
      )}
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

export function LivePreview({ effect, text, color }: { effect: Effect | null; text: string; color: string }) {
  const uid = useId().replace(/:/g, '');
  const chars = Array.from(text);
  const p = effect?.params ?? {};
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
        className="block h-auto w-full rounded-xl border border-slate-200 bg-white">
        {body}
      </svg>
    </figure>
  );
}
