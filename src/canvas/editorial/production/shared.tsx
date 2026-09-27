import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { fmtDay } from '../authors/shared';
import { productionApi, type Delay, type Milestone, type MilestoneSource, type ProdCard, type ProdStage } from './api';

/** M12 Üretim yönetimi ekranlarının ortak parçaları: dönüm noktası zinciri, kaynak etiketi, biçimler, sorgu anahtarları. */

/** Gerçekleştiği sırayla (CRM aşama sırası: matbaa belirleme → baskıya hazır → matbaada → depo girişi). */
export const POINTS: Array<{ key: Milestone; short: string; label: string }> = [
  { key: 'matbaa', short: 'Matbaa', label: 'Matbaa belirlendi' },
  { key: 'dosya', short: 'Dosya', label: 'Baskı dosyası matbaada' },
  { key: 'baski', short: 'Baskı', label: 'Baskı çıkışı' },
  { key: 'depo', short: 'Depo', label: 'Depo girişi' },
];

export const SOURCE_LABEL: Record<MilestoneSource, string> = { logo: 'Logo', crm: 'CRM', portal: 'Portal' };

export const STAGE_TONE: Record<ProdStage, string> = {
  hazirlik: 'bg-slate-100 text-canvas-ink',
  'matbaa-secildi': 'bg-sky-50 text-sky-800',
  matbaada: 'bg-canvas-violet/10 text-canvas-violet',
  yolda: 'bg-amber-50 text-amber-800',
  tamam: 'bg-emerald-50 text-emerald-700',
  eski: 'bg-slate-100 text-canvas-muted',
  iptal: 'bg-slate-100 text-canvas-muted line-through',
};

export { fmtDay };

const money = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 2 });
const unit = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
export const fmtMoney = (v: number | null | undefined) => (v === null || v === undefined ? '—' : money.format(v));
export const fmtUnit = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${unit.format(v)} ₺`);
export const fmtPct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `%${Math.round(v * 100)}`);

/** Bir noktanın ekrandaki durumu: gerçekleşti, gecikti, sırada (planı var), planı yok. */
export type PointState = 'done' | 'late' | 'planned' | 'none';

export function pointState(card: Pick<ProdCard, 'actual' | 'plan' | 'delays'>, key: Milestone): PointState {
  if (card.actual[key]) return 'done';
  if (card.delays.some((d) => d.milestone === key)) return 'late';
  if (card.plan[key]) return 'planned';
  return 'none';
}

/** Kartın en büyük gecikmesi (gün) ve seviyesi; gecikme yoksa null. */
export function worstDelay(delays: Delay[]): Delay | null {
  return delays.reduce<Delay | null>((w, d) => (w === null || d.days > w.days ? d : w), null);
}

/** Kartın sıradaki (gerçekleşmemiş ilk) noktası ve planlanan tarihi. */
export function nextPoint(card: Pick<ProdCard, 'actual' | 'plan'>): { key: Milestone; label: string; due: string | null } | null {
  for (const p of POINTS) if (!card.actual[p.key]) return { key: p.key, label: p.label, due: card.plan[p.key] ?? null };
  return null;
}

export function daysText(n: number): string {
  if (n === 0) return 'bugün';
  return n === 1 ? '1 gün' : `${n} gün`;
}

/** Varsayılan hedef yayın tarihi: iki ay sonrasının ilk günü (15 kuralıyla dosya teslimi bir sonraki ayın 15'i). */
export function defaultPublication(now = new Date()): string {
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 2, 1));
  return d.toISOString().slice(0, 10);
}

export const productionMeta = () =>
  queryOptions({ queryKey: ['production', 'meta'], queryFn: productionApi.meta, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000 });

export function useProductionMeta() {
  return useQuery(productionMeta());
}

export function invalidateProduction(qc: QueryClient): Promise<void> {
  return qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'production' && q.queryKey[1] !== 'meta' });
}

/** Dönüm noktası zinciri: dört nokta yan yana; gerçekleşen dolu, geciken kırmızı, planlanan boş halka. */
export function Chain({ card, compact }: { card: Pick<ProdCard, 'actual' | 'plan' | 'delays'>; compact?: boolean }) {
  return (
    <ol className="grid grid-cols-4 gap-1" aria-label="Üretim adımları">
      {POINTS.map((p, i) => {
        const st = pointState(card, p.key);
        const a = card.actual[p.key];
        const day = a ? a.day : (card.plan[p.key] ?? null);
        const dot =
          st === 'done'
            ? 'border-emerald-500 bg-emerald-500'
            : st === 'late'
              ? 'border-rose-500 bg-rose-100'
              : st === 'planned'
                ? 'border-canvas-violet/60 bg-white'
                : 'border-slate-300 bg-slate-100';
        const text = st === 'late' ? 'text-rose-700' : st === 'done' ? 'text-canvas-ink' : 'text-canvas-muted';
        const state = { done: 'gerçekleşti', late: 'gecikti', planned: 'planlandı', none: 'planı yok' }[st];
        return (
          <li key={p.key} className="min-w-0" aria-label={`${p.label}: ${state}${day ? `, ${fmtDay(day)}` : ''}`}>
            <div className="flex items-center gap-1">
              <span aria-hidden className={`h-2.5 w-2.5 shrink-0 rounded-full border-2 ${dot}`} />
              {i < POINTS.length - 1 && <span aria-hidden className={`h-0.5 flex-1 rounded ${st === 'done' ? 'bg-emerald-300' : 'bg-slate-200'}`} />}
            </div>
            <div className={`mt-0.5 truncate text-[10.5px] font-bold uppercase tracking-wide ${text}`}>{p.short}</div>
            {!compact && (
              <div className={`truncate font-mono text-[11px] tabular-nums ${text}`}>
                {day ? fmtDay(day).replace(/ \d{4}$/, '') : st === 'done' ? 'tarihsiz' : '—'}
                {st === 'planned' || st === 'late' ? <span className="sr-only"> (plan)</span> : null}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
