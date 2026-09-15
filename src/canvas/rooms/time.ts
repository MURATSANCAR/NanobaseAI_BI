/** Oda takvimi İstanbul saatiyle çalışır; tarayıcının saat dilimi hesaba girmez. */

const TZ = 'Europe/Istanbul';

/** İstanbul'daki bugün, YYYY-AA-GG. */
export function istanbulToday(at = new Date()): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(at);
}

/** İstanbul'da günün kaçıncı dakikası. */
export function istanbulMinutes(at = new Date()): number {
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: TZ, hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).formatToParts(at);
  const h = Number(parts.find((p) => p.type === 'hour')?.value ?? 0);
  const m = Number(parts.find((p) => p.type === 'minute')?.value ?? 0);
  return h * 60 + m;
}

export const toMin = (hhmm: string): number => {
  const [h, m] = hhmm.split(':').map(Number);
  return h * 60 + m;
};

export const toHHMM = (min: number): string => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

/** Takvim günü + n gün. Saat dilimi olmayan düz tarih hesabı. */
export function addDays(day: string, n: number): string {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

const DAY_LABEL = new Intl.DateTimeFormat('tr-TR', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
const DAY_LONG = new Intl.DateTimeFormat('tr-TR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' });

export function dayLabel(day: string, today: string): string {
  if (day === today) return 'Bugün';
  if (day === addDays(today, 1)) return 'Yarın';
  return DAY_LABEL.format(new Date(`${day}T00:00:00Z`));
}

export const dayLong = (day: string): string => DAY_LONG.format(new Date(`${day}T00:00:00Z`));

export function duration(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (!h) return `${m} dk`;
  return m ? `${h} sa ${m} dk` : `${h} saat`;
}
