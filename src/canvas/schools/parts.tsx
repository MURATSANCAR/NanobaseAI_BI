import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, type QueryClient } from '@tanstack/react-query';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { nf } from '../admin/ui';
import { schoolsApi, type CalendarHit, type ScorePart } from './api';

/** M31 Okul tanıtım ekranlarının ortak parçaları: kabuk, sekme çubuğu, puan, tarih biçimi, ortak sorgular. */

export function SchoolsFrame({
  title,
  lead,
  source,
  presence,
  back,
  aside,
  children,
}: {
  title: string;
  lead?: string;
  source: string;
  presence: string;
  back?: boolean;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Saha satış ve okul', crumb: 'Okul tanıtım', source, presence, detail: back ? title : undefined }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to="/okul-tanitim" className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    Okul tanıtım
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Saha satış ve okul · Okul tanıtım</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[440px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: ReadonlyArray<{ key: T; label: string; badge?: number | null }>; value: T; onChange: (t: T) => void }) {
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Bölüm">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={value === t.key}
            onClick={() => onChange(t.key)}
            className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
              value === t.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
            }`}
          >
            {t.label}
            {t.badge ? (
              <span className={`rounded-md px-1.5 py-0.5 font-mono text-[10.5px] tabular-nums ${value === t.key ? 'bg-white/20' : 'bg-red-50 text-red-700'}`}>{t.badge}</span>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const dayShort = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', weekday: 'short', timeZone: 'UTC' });

/** 'YYYY-MM-DD' → «5 Eki 2026». Gün değerleri İstanbul günüdür; saat dilimi kaydırmasın diye UTC okunur. */
export const fmtDay = (d: string | null | undefined) => (d ? dayFmt.format(new Date(`${d.slice(0, 10)}T00:00:00Z`)) : '—');
export const fmtDayShort = (d: string | null | undefined) => (d ? dayShort.format(new Date(`${d.slice(0, 10)}T00:00:00Z`)) : '—');
export const fmtMoney = (v: number | null | undefined) =>
  v == null ? '—' : `${new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)} ₺`;
export const fmtNum = (v: number | null | undefined) => (v == null ? '—' : nf.format(Math.round(v)));
export const fmtPct = (v: number | null | undefined) => (v == null ? '—' : `%${nf.format(Math.round(v * 100))}`);

/** Bugünden kaç gün önce (son ziyaret için). */
export function daysAgo(d: string | null | undefined, today: string): string {
  if (!d) return 'hiç ziyaret yok';
  const n = Math.round((Date.parse(`${today}T00:00:00Z`) - Date.parse(`${d.slice(0, 10)}T00:00:00Z`)) / 86_400_000);
  if (n <= 0) return 'bugün';
  if (n < 45) return `${n} gün önce`;
  if (n < 365) return `${Math.round(n / 30)} ay önce`;
  return `${(n / 365).toFixed(1).replace('.', ',')} yıl önce`;
}

/** Haftanın pazartesisi (YYYY-MM-DD). */
export function mondayOf(d: string): string {
  const t = new Date(`${d}T00:00:00Z`);
  const wd = (t.getUTCDay() + 6) % 7;
  t.setUTCDate(t.getUTCDate() - wd);
  return t.toISOString().slice(0, 10);
}

export function addDays(d: string, n: number): string {
  const t = new Date(`${d}T00:00:00Z`);
  t.setUTCDate(t.getUTCDate() + n);
  return t.toISOString().slice(0, 10);
}

export function ScoreBadge({ score }: { score: number }) {
  const tone = score >= 60 ? 'bg-canvas-violet text-white' : score >= 35 ? 'bg-canvas-violet/15 text-canvas-violet' : 'bg-slate-100 text-canvas-ink';
  return (
    <span className={`inline-flex h-9 min-w-9 shrink-0 items-center justify-center rounded-xl px-1.5 font-mono text-[13px] font-extrabold tabular-nums ${tone}`} title="Öncelik puanı (0–100)">
      {Math.round(score)}
    </span>
  );
}

/** Puanın bileşenleri: her satır puan / en çok ve açıklama. Kural ekranda yazılı olsun diye. */
export function ScoreParts({ parts }: { parts: ScorePart[] }) {
  return (
    <ul className="space-y-1.5">
      {parts.map((p) => (
        <li key={p.key} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-1">
          <span className="min-w-0 text-[12.5px] font-bold">{p.label}</span>
          <span className="font-mono text-[12px] font-bold tabular-nums">
            {p.points.toLocaleString('tr-TR')} / {p.max}
          </span>
          <span className="col-span-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
            <span className="block h-full rounded-full bg-canvas-violet" style={{ width: `${p.max ? Math.min(100, (p.points / p.max) * 100) : 0}%` }} />
          </span>
          <span className="col-span-2 text-[11.5px] leading-snug text-canvas-muted">{p.note}</span>
        </li>
      ))}
    </ul>
  );
}

export function CalendarNote({ hits }: { hits: CalendarHit[] }) {
  if (!hits.length) return null;
  return (
    <div className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold leading-snug text-amber-800">
      {hits.map((h) => (
        <div key={`${h.from}-${h.name}`}>
          {h.kindLabel ?? (h.kind === 'sinav' ? 'Sınav haftası' : h.kind === 'tatil' ? 'Tatil' : 'Takvim')}: {h.name} · {fmtDay(h.from)}
          {h.to !== h.from ? ` – ${fmtDay(h.to)}` : ''}
          {h.il ? ` (${h.il})` : ''}
        </div>
      ))}
    </div>
  );
}

export const useSchoolsMeta = () =>
  useQuery({ queryKey: ['schools', 'meta'], queryFn: schoolsApi.meta, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });

export const invalidateSchools = (qc: QueryClient) => qc.invalidateQueries({ queryKey: ['schools'] });
