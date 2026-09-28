import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Pill, field, label as labelCls } from '../admin/ui';
import { LEVEL_STYLE, VALUE_TONE, fmtLeft, leftTone, type Level, type Measure, type RiskMeta, type ValueState } from './api';

/** Risk ve uyum ekranlarının ortak kabuğu ve küçük parçaları. Sekme çubuğu, onay penceresi ve dosya seçici diğer
 *  modüllerinkiyle aynıdır. */
export { Tabs, AskSheet } from '../budget/parts';
export { FilePick, Fact } from '../tenders/parts';

export function RiskFrame({ title, lead, back, aside, children }: { title: string; lead: string; back?: boolean; aside?: ReactNode; children: ReactNode }) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Finans ve risk', crumb: 'Risk ve uyum', source: 'Kaynak: portal kaydı · Logo · CRM', presence: 'Risk ve uyum' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to="/risk-uyum?sekme=kayit" className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    Risk kaydı
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Finans ve risk · Risk yönetimi ve uyum</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export function LevelPill({ level, score, meta }: { level: Level | null; score: number | null; meta?: RiskMeta }) {
  if (!level || !score) return <Pill tone="muted">puanlanmadı</Pill>;
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold ${LEVEL_STYLE[level].pill}`}>
      <span className="font-mono tabular-nums">{score}</span>
      {meta?.seviyeler[level] ?? level}
    </span>
  );
}

export function ValuePill({ state, meta }: { state: ValueState | undefined; meta?: RiskMeta }) {
  const s = state ?? 'olculemedi';
  return <Pill tone={VALUE_TONE[s]}>{meta?.degerDurumlari[s] ?? s}</Pill>;
}

export function LeftPill({ days, warn }: { days: number | null | undefined; warn?: number }) {
  return <Pill tone={leftTone(days, warn)}>{fmtLeft(days)}</Pill>;
}

/** Son 12 ölçümün küçük çizgisi. Eşikler kesik çizgi; ölçülemeyen nokta boşluk bırakır. Süs değil, eğilim içindir. */
export function Spark({ points, sari, kirmizi }: { points: Measure[]; sari?: number | null; kirmizi?: number | null }) {
  const vals = points.map((p) => p.deger).filter((v): v is number => v !== null && Number.isFinite(v));
  if (vals.length < 2) return <span className="text-[11px] text-canvas-muted">{vals.length ? 'tek ölçüm' : 'ölçüm yok'}</span>;
  const lines = [sari, kirmizi].filter((v): v is number => v !== null && v !== undefined);
  const lo = Math.min(...vals, ...lines);
  const hi = Math.max(...vals, ...lines);
  const span = hi - lo || 1;
  const W = 120;
  const H = 32;
  const x = (i: number) => (points.length === 1 ? W / 2 : (i / (points.length - 1)) * W);
  const y = (v: number) => H - 3 - ((v - lo) / span) * (H - 6);
  let d = '';
  let pen = false;
  points.forEach((p, i) => {
    if (p.deger === null || !Number.isFinite(p.deger)) {
      pen = false;
      return;
    }
    d += `${pen ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.deger).toFixed(1)} `;
    pen = true;
  });
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-8 w-[120px]" role="img" aria-label={`Son ${points.length} ölçüm`}>
      {sari !== null && sari !== undefined && <line x1="0" x2={W} y1={y(sari)} y2={y(sari)} className="stroke-amber-400" strokeDasharray="3 3" strokeWidth="1" />}
      {kirmizi !== null && kirmizi !== undefined && <line x1="0" x2={W} y1={y(kirmizi)} y2={y(kirmizi)} className="stroke-red-400" strokeDasharray="3 3" strokeWidth="1" />}
      <path d={d} fill="none" className="stroke-canvas-violet" strokeWidth="1.8" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

export function TextInput({ id, label, value, onChange, type = 'text', placeholder, help, area }: {
  id: string; label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string; help?: string; area?: boolean;
}) {
  return (
    <label htmlFor={id} className="flex min-w-0 flex-col gap-1">
      <span className={labelCls}>{label}</span>
      {area ? (
        <textarea id={id} className={`${field} min-h-[88px]`} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} />
      ) : (
        <input id={id} type={type} className={field} value={value} placeholder={placeholder} autoComplete="off" onChange={(e) => onChange(e.target.value)} />
      )}
      {help && <span className="text-[11px] leading-snug text-canvas-muted">{help}</span>}
    </label>
  );
}

export function SelectInput({ id, label, value, onChange, options, empty }: {
  id: string; label: string; value: string; onChange: (v: string) => void; options: Record<string, string>; empty?: string;
}) {
  return (
    <label htmlFor={id} className="flex min-w-0 flex-col gap-1">
      <span className={labelCls}>{label}</span>
      <select id={id} className={field} value={value} onChange={(e) => onChange(e.target.value)}>
        {empty !== undefined && <option value="">{empty}</option>}
        {Object.entries(options).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </label>
  );
}

/** 1–5 seçici (olasılık, etki, kritiklik): büyük dokunma alanı, sayı yazılı. */
export function ScalePick({ label, value, onChange, hints }: { label: string; value: number | null; onChange: (v: number) => void; hints?: [string, string] }) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-1">
      <legend className={labelCls}>{label}</legend>
      <div className="mt-1 grid grid-cols-5 gap-1" role="radiogroup" aria-label={label}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={value === n}
            onClick={() => onChange(n)}
            className={`min-h-11 rounded-xl font-mono text-[14px] font-bold tabular-nums transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${
              value === n ? 'bg-canvas-violet text-white shadow-md' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
            }`}
          >
            {n}
          </button>
        ))}
      </div>
      {hints && (
        <div className="flex justify-between text-[10.5px] text-canvas-muted">
          <span>{hints[0]}</span>
          <span>{hints[1]}</span>
        </div>
      )}
    </fieldset>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl bg-white/60 px-4 py-6 text-center text-[12.5px] leading-snug text-canvas-muted">{children}</div>;
}
