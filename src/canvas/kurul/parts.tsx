import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ArrowDownRight, ArrowRight, ArrowUpRight, ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { styleOf, type Color, type IndState, type Trend } from './api';

/** Kurul ekranlarının ortak kabuğu ve küçük parçaları. Sekme çubuğu, onay penceresi ve form alanları diğer
 *  modüllerinkiyle aynıdır. */
export { Tabs, AskSheet } from '../budget/parts';
export { Empty, SelectInput, TextInput } from '../risk/parts';

export function KurulFrame({ title, lead, back, aside, children }: {
  title: string; lead: string; back?: { to: string; label: string }; aside?: ReactNode; children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Finans ve risk', crumb: 'Kurul', source: 'Kaynak: modüllerin onaylı çıktıları · portal kaydı', presence: 'Kurul' }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to={back.to} className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    {back.label}
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Finans ve risk · Danışma ve yönetim kurulu</div>
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

/** Renk rozeti: nokta + simge + ad. Renk tek başına anlam taşımaz. */
export function ColorBadge({ durum, renk, size = 'sm' }: { durum: IndState; renk: Color | null; size?: 'sm' | 'md' }) {
  const s = styleOf({ durum, renk });
  return (
    <span className={`inline-flex shrink-0 items-center gap-1.5 font-bold ${s.text} ${size === 'md' ? 'text-[12px]' : 'text-[11px]'}`}>
      <span aria-hidden className={`grid h-4 w-4 place-items-center rounded-full font-mono text-[10px] leading-none text-white ${s.dot}`}>{s.glyph}</span>
      {s.label}
    </span>
  );
}

/** Önceki değere göre yön: ok + iyi/kötü rengi. Oran yoksa yalnız ok. */
export function TrendMark({ t, label }: { t: Trend | null; label?: string | null }) {
  if (!t) return null;
  const Icon = t.yon === 'yukari' ? ArrowUpRight : t.yon === 'asagi' ? ArrowDownRight : ArrowRight;
  const tone = t.iyi === null ? 'text-canvas-muted' : t.iyi ? 'text-emerald-700' : 'text-red-700';
  const pct = t.oran === null ? '' : `${t.oran > 0 ? '+' : ''}${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 }).format(t.oran * 100)}%`;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11.5px] font-bold ${tone}`} title={label ?? undefined}>
      <Icon aria-hidden className="h-3.5 w-3.5" />
      <span className="font-mono tabular-nums">{pct || (t.yon === 'sabit' ? 'değişmedi' : '')}</span>
      <span className="sr-only">{t.iyi === null ? '' : t.iyi ? ' (iyileşti)' : ' (kötüleşti)'}{label ? ` — ${label}` : ''}</span>
    </span>
  );
}

/** Son dönemlerin küçük çizgisi (ölçülemeyen dönem boşluk bırakır). Süs değil, eğilim içindir. */
export function Spark({ points }: { points: Array<{ deger: number | null }> }) {
  const vals = points.map((p) => p.deger).filter((v): v is number => v !== null && Number.isFinite(v));
  if (vals.length < 2) return <span className="text-[11px] text-canvas-muted">{vals.length ? 'tek dönem ölçüldü' : 'ölçüm yok'}</span>;
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = hi - lo || 1;
  const W = 220;
  const H = 44;
  const x = (i: number) => (points.length === 1 ? W / 2 : (i / (points.length - 1)) * W);
  const y = (v: number) => H - 4 - ((v - lo) / span) * (H - 8);
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
    <svg viewBox={`0 0 ${W} ${H}`} className="h-11 w-full max-w-[260px]" role="img" aria-label={`Son ${points.length} dönem`}>
      <path d={d} fill="none" className="stroke-canvas-violet" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
