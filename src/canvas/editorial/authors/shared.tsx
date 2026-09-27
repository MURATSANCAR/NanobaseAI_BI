import { useMemo } from 'react';
import { queryOptions, useQuery, type QueryClient } from '@tanstack/react-query';
import { ENGINE_ENABLED, authorsApi, peopleApi, type AuthorHeat, type AuthorMeeting, type HeatBand } from '../../engine';
import type { SearchOption } from '../../components/SearchSelect';

/** M7 Yazar ilişkileri ekranlarının ortak parçaları: ısı bantları, tarih biçimi, takvim dosyası, sorgu anahtarları. */

export const BAND: Record<HeatBand, { label: string; pill: string; dot: string }> = {
  sicak: { label: 'Sıcak', pill: 'bg-rose-50 text-rose-700', dot: 'bg-rose-500' },
  ilik: { label: 'Ilık', pill: 'bg-amber-50 text-amber-800', dot: 'bg-amber-400' },
  soguk: { label: 'Soğuk', pill: 'bg-sky-50 text-sky-800', dot: 'bg-sky-400' },
  yok: { label: 'Temas yok', pill: 'bg-slate-100 text-canvas-muted', dot: 'bg-slate-300' },
};

/** CRM'deki iz türleri: ısının yakınlık payına girer (görüşme yoksa ya da daha yeniyse). */
export const TRACE: Record<string, string> = { eser: 'yeni eser kaydı', sozlesme: 'sözleşme başlangıcı' };

/** Ay hücresi: o ayda yapılan görüşme sayısı. 0 boş, 3 ve üstü en koyu. */
export function cellClass(n: number): string {
  if (n <= 0) return 'bg-slate-100/80';
  if (n === 1) return 'bg-canvas-violet/25';
  if (n === 2) return 'bg-canvas-violet/55';
  return 'bg-canvas-violet text-white';
}

const monthFmt = new Intl.DateTimeFormat('tr-TR', { month: 'short', timeZone: 'UTC' });
/** '2026-03' → 'Mar'; ocak ayında yıl da yazılır. */
export function monthLabel(key: string): string {
  const [y, m] = key.split('-').map(Number);
  const name = monthFmt.format(new Date(Date.UTC(y, m - 1, 1))).replace('.', '');
  return m === 1 ? `${name} ${String(y).slice(2)}` : name;
}
export function monthLong(key: string): string {
  const [y, m] = key.split('-').map(Number);
  return new Intl.DateTimeFormat('tr-TR', { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(new Date(Date.UTC(y, m - 1, 1)));
}

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const dayFmtTr = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/Istanbul' });
const weekdayFmt = new Intl.DateTimeFormat('tr-TR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' });
/** 'YYYY-AA-GG' → '12 Eyl 2026' (gün dilimi kaymadan). Saatli değer (CRM tarihleri, zaman damgaları) UTC'dir:
 *  İstanbul gününe çevrilir — CRM «29 Eylül» bitişini `2026-09-28T21:00:00` diye verir. */
export function fmtDay(day: string | null | undefined): string {
  if (!day) return '—';
  if (/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(day)) {
    const iso = day.replace(' ', 'T');
    const t = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : `${iso}Z`);
    if (!Number.isNaN(t.getTime())) return dayFmtTr.format(t);
  }
  const [y, m, d] = day.slice(0, 10).split('-').map(Number);
  return dayFmt.format(new Date(Date.UTC(y, m - 1, d)));
}
export function fmtWeekday(day: string): string {
  const [y, m, d] = day.split('-').map(Number);
  return weekdayFmt.format(new Date(Date.UTC(y, m - 1, d)));
}
export function daysAgo(n: number | null): string {
  if (n === null) return 'hiç görüşülmedi';
  if (n === 0) return 'bugün';
  if (n === 1) return 'dün';
  if (n < 45) return `${n} gün önce`;
  if (n < 365) return `${Math.round(n / 30)} ay önce`;
  return `${Math.floor(n / 365)} yıl önce`;
}

/** İstanbul'da bugünün tarihi ve şimdiki saat (yarım saate yuvarlanmış), form varsayılanı için. */
export function nowLocal(): { date: string; time: string } {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '00';
  const min = Number(get('minute')) < 30 ? '00' : '30';
  return { date: `${get('year')}-${get('month')}-${get('day')}`, time: `${get('hour')}:${min}` };
}

/** Son 12 ay (İstanbul), eskiden yeniye 'YYYY-AA'; köprünün ay anahtarlarıyla aynı. */
export function lastMonths(n = 12): string[] {
  const { date } = nowLocal();
  let [y, m] = date.split('-').map(Number);
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    out.push(`${y}-${String(m).padStart(2, '0')}`);
    m -= 1;
    if (m === 0) {
      y -= 1;
      m = 12;
    }
  }
  return out.reverse();
}

export function HeatPill({ heat, compact }: { heat: AuthorHeat; compact?: boolean }) {
  const b = BAND[heat.band];
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-bold ${b.pill}`}>
      <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${b.dot}`} />
      {compact ? b.label : `${b.label} · ${heat.score}`}
    </span>
  );
}

/** Randevuyu takvime eklemek için .ics dosyası (Outlook, Google, Apple Takvim açar). */
export function downloadIcs(m: AuthorMeeting, who: string): void {
  const start = new Date(m.startsAt);
  const end = new Date(start.getTime() + (m.minutes ?? 60) * 60_000);
  const stamp = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const esc = (s: string) => s.replace(/\\/g, '\\\\').replace(/\n/g, '\\n').replace(/[,;]/g, (c) => `\\${c}`);
  const where = [m.roomName, m.location].filter(Boolean).join(' · ');
  const lines = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Timas//Yazar iliskileri//TR', 'CALSCALE:GREGORIAN', 'BEGIN:VEVENT',
    `UID:${m.id}@yazar-iliskileri`, `DTSTAMP:${stamp(new Date())}`, `DTSTART:${stamp(start)}`, `DTEND:${stamp(end)}`,
    `SUMMARY:${esc(`${who}: ${m.topic}`)}`,
    ...(where ? [`LOCATION:${esc(where)}`] : []),
    `DESCRIPTION:${esc(`${m.channelLabel}${m.nextStep ? `\nSıradaki adım: ${m.nextStep}` : ''}`)}`,
    'END:VEVENT', 'END:VCALENDAR',
  ];
  const url = URL.createObjectURL(new Blob([lines.join('\r\n')], { type: 'text/calendar;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `randevu-${m.date}.ics`;
  a.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const authorsMetaOptions = () =>
  queryOptions({ queryKey: ['authors', 'meta'], queryFn: authorsApi.meta, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000 });

export function useAuthorsMeta() {
  return useQuery(authorsMetaOptions());
}

/** Portal kullanıcıları (CRM rehberi): sorumlu editör ve katılımcı seçimi. */
export function usePeopleOptions(): { options: SearchOption[]; byUser: Map<string, string> } {
  const q = useQuery({ queryKey: ['people', 'directory'], queryFn: peopleApi.list, enabled: ENGINE_ENABLED, staleTime: 10 * 60_000 });
  return useMemo(() => {
    const items = (q.data?.items ?? []).filter((p) => p.username);
    const options = items
      .map((p) => ({ value: p.username.toLowerCase(), label: [p.name, p.title].filter(Boolean).join(' · ') || p.username }))
      .sort((a, b) => a.label.localeCompare(b.label, 'tr'));
    return { options, byUser: new Map(items.map((p) => [p.username.toLowerCase(), p.name || p.username])) };
  }, [q.data]);
}

/** Bir kayıt değişince ilişkili bütün görünümler yeniden okunur (kart, liste, ısı, ajanda, Kişiler bölümü). */
export function invalidateAuthors(qc: QueryClient): Promise<void> {
  return qc.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'authors' });
}
