import { Link } from 'react-router-dom';
import { ArrowDownRight, ArrowRight, ArrowUpRight, ChevronRight } from 'lucide-react';
import { fmtDay, fmtPct, fmtShort } from '../field/api';
import { SEGMENTS, TREND_LABEL, segmentTone, worsened, type Dealer, type Dist, type Segment, type Trend } from './api';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

/** Bayi riski ortak parçaları. Telefon önce: liste satırı kart, dokunma hedefi ≥ 44 px, segment harfi her zaman yazılı
 *  (renk tek başına anlam taşımaz). Hareket yalnız basma geri bildirimi (M30 satırlarıyla aynı: 150 ms, ease-out, 0,98). */

const TONE = {
  ok: 'bg-emerald-50 text-emerald-800',
  muted: 'bg-slate-100 text-canvas-ink',
  warn: 'bg-amber-50 text-amber-800',
  err: 'bg-red-50 text-red-700',
} as const;

const BAR = { A: 'bg-emerald-500', B: 'bg-slate-400', C: 'bg-amber-500', D: 'bg-red-600' } as const;

export function SegmentBadge({ segment, skor, size = 'md' }: { segment: Segment | null; skor?: number | null; size?: 'md' | 'lg' }) {
  const big = size === 'lg';
  return (
    <span
      className={`inline-flex shrink-0 flex-col items-center justify-center rounded-xl font-extrabold tabular-nums ${TONE[segmentTone(segment)]} ${
        big ? 'h-14 min-w-14 px-2' : 'h-10 min-w-10 px-1.5'
      }`}
      title={segment ? `Segment ${segment}${skor !== null && skor !== undefined ? ` · skor ${Math.round(skor)}` : ''}` : 'Hareketsiz: bakiye yok, 12 ayda alım yok'}
    >
      <span className={big ? 'text-[22px] leading-none' : 'text-[15px] leading-none'}>{segment ?? '—'}</span>
      {skor !== null && skor !== undefined && <span className={`font-mono ${big ? 'text-[11px]' : 'text-[9.5px]'} leading-tight opacity-80`}>{Math.round(skor)}</span>}
    </span>
  );
}

export function TrendMark({ egilim, prev, now }: { egilim: Trend | null; prev?: Segment | null; now?: Segment | null }) {
  const dropped = worsened(now, prev);
  if (!egilim && !dropped) return null;
  const Icon = egilim === 'kotulesiyor' || dropped ? ArrowUpRight : egilim === 'iyilesiyor' ? ArrowDownRight : ArrowRight;
  const tone = egilim === 'kotulesiyor' || dropped ? 'text-red-700' : egilim === 'iyilesiyor' ? 'text-emerald-700' : 'text-canvas-muted';
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-bold ${tone}`}>
      <Icon aria-hidden className="h-3.5 w-3.5" />
      {dropped ? `${prev} → ${now}` : TREND_LABEL[egilim as Trend]}
    </span>
  );
}

/** Liste satırı: segment + skor, unvan, vadesi geçmiş, üç baskın bileşen; tamamı bayi kartına götürür (tek dokunuş). */
export function DealerRow({ d, showBmt, k, alan = 'items[]' }: { d: Dealer; showBmt?: boolean; k?: Kaynaklar; alan?: string }) {
  return (
    <li className="flex items-stretch gap-2">
      <Link
        to={`/bayi-risk/${encodeURIComponent(d.code)}`}
        className="flex min-h-14 min-w-0 flex-1 items-start gap-2.5 rounded-2xl border border-slate-100 bg-white/85 p-3 transition-transform duration-150 ease-out active:scale-[0.98]"
      >
        <SegmentBadge segment={d.segment} skor={d.skor} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <div className="min-w-0 truncate text-[13.5px] font-extrabold">{d.unvan || d.code}</div>
            <div className="shrink-0 font-mono text-[12px] font-bold tabular-nums text-red-700">{d.vadesiGecmis ? fmtShort(d.vadesiGecmis) : ''}</div>
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11.5px] text-canvas-muted">
            <span className="truncate">
              {[d.il, d.kanal, d.grup === 'anahtar' ? 'anahtar hesap' : null, showBmt ? d.bmtAd || d.bmt || 'temsilcisiz' : null, d.sonOdeme ? `son ödeme ${fmtDay(d.sonOdeme)}` : null]
                .filter(Boolean)
                .join(' · ')}
            </span>
            <TrendMark egilim={d.egilim} prev={d.oncekiSegment} now={d.segment} />
            {d.sorunlu && <span className="rounded-md bg-red-50 px-1.5 text-[10.5px] font-bold text-red-700">CRM: sorunlu</span>}
            {d.hareketsiz && <span className="rounded-md bg-slate-100 px-1.5 text-[10.5px] font-bold">hareketsiz</span>}
          </div>
          {d.neden.length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1">
              {d.neden.map((n) => (
                <span key={n.key} className="inline-flex max-w-full items-center rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-bold leading-snug text-canvas-ink">
                  <span className="truncate">{n.aciklama}</span>
                </span>
              ))}
            </div>
          )}
        </div>
        <ChevronRight aria-hidden className="mt-2 h-4 w-4 shrink-0 text-canvas-muted" />
      </Link>
      {k && (
        <span className="flex shrink-0 items-start pt-3">
          <SqlInfo k={k} alan={alan} row={d.code} label={`${d.unvan || d.code}: skor ve alacak`} />
        </span>
      )}
    </li>
  );
}

/** Segment dağılımı: yığılmış çubuk + sayılar. `before` verilirse altında ince çubuk (30 gün önce, bugünkü kuralla). */
export function DistBar({ dist, before, group }: { dist: Dist; before?: Dist | null; group: 'standart' | 'anahtar' }) {
  const g = dist[group];
  const total = SEGMENTS.reduce((a, s) => a + (g[s] ?? 0), 0);
  const b = before?.[group];
  const bt = b ? SEGMENTS.reduce((a, s) => a + (b[s] ?? 0), 0) : 0;
  return (
    <div className="min-w-0">
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-slate-100" role="img" aria-label={SEGMENTS.map((s) => `${s} ${g[s] ?? 0}`).join(', ')}>
        {total > 0 && SEGMENTS.map((s) => <span key={s} className={BAR[s]} style={{ width: `${((g[s] ?? 0) / total) * 100}%` }} />)}
      </div>
      {b && bt > 0 && (
        <div className="mt-1 flex h-1.5 w-full overflow-hidden rounded-full bg-slate-100 opacity-60" aria-hidden>
          {SEGMENTS.map((s) => (
            <span key={s} className={BAR[s]} style={{ width: `${((b[s] ?? 0) / bt) * 100}%` }} />
          ))}
        </div>
      )}
      <div className="mt-1.5 grid grid-cols-4 gap-1">
        {SEGMENTS.map((s) => {
          const diff = b ? (g[s] ?? 0) - (b[s] ?? 0) : null;
          return (
            <div key={s} className="min-w-0 rounded-lg bg-slate-50 px-1.5 py-1 text-center">
              <div className="text-[11px] font-extrabold">{s}</div>
              <div className="font-mono text-[14px] font-extrabold tabular-nums">{g[s] ?? 0}</div>
              {diff !== null && diff !== 0 && (
                <div className={`font-mono text-[10.5px] font-bold tabular-nums ${diff > 0 && (s === 'C' || s === 'D') ? 'text-red-700' : 'text-canvas-muted'}`}>
                  {diff > 0 ? `+${diff}` : diff}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Oran çubuğu (0–1): limit doluluğu, bileşen değeri. */
export function Meter({ value, tone = 'violet' }: { value: number | null | undefined; tone?: 'violet' | 'err' | 'warn' }) {
  const w = value === null || value === undefined ? 0 : Math.max(0, Math.min(1, value));
  const c = tone === 'err' ? 'bg-red-600' : tone === 'warn' ? 'bg-amber-500' : 'bg-canvas-violet';
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100" aria-hidden>
      <div className={`h-full ${c}`} style={{ width: `${w * 100}%` }} />
    </div>
  );
}

export const approxNote = 'Yaklaşık: Logo\'da ödeme kapama kullanılmıyor; bakiye en yeni vadelerden geriye dağıtıldı (FIFO).';

export const pct = (v: number | null | undefined) => fmtPct(v);
