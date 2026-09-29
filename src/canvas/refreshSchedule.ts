/** Verinin otomatik yenilendiği saatler (İstanbul) — sunucunun hazır cevap tazelemesiyle aynı (`response_cache.REFRESH_TIMES`; kullanıcı kararı 2026-09-29). */
export const REFRESH_TIMES: ReadonlyArray<readonly [number, number]> = [[7, 0], [12, 0]];
/** Açık ekran, sunucunun o saatteki tazelemesini yakalamak için yenileme saatini 5 ve 20 dakika geçe veriyi yeniden ister. */
const PICKUP_MINUTES = [5, 20];
const TZ_PARTS = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/Istanbul', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
});

/** İstanbul saatiyle günün şu anki dakikası ve saniyesi (gün içi saniye). */
function istanbulSecondOfDay(now: number): number {
  const p = Object.fromEntries(TZ_PARTS.formatToParts(new Date(now)).map((x) => [x.type, x.value]));
  return Number(p.hour) * 3600 + Number(p.minute) * 60 + Number(p.second);
}

/** Bir sonraki otomatik yenilemeye kalan süre (ms): her gün 07:05, 07:20, 12:05, 12:20 (İstanbul). */
export function msUntilNextRefresh(now: number = Date.now()): number {
  const sec = istanbulSecondOfDay(now);
  const marks = REFRESH_TIMES.flatMap(([h, m]) => PICKUP_MINUTES.map((d) => h * 3600 + (m + d) * 60)).sort((a, b) => a - b);
  const next = marks.find((t) => t > sec) ?? marks[0] + 86_400;
  return (next - sec) * 1000;
}

const two = (n: number) => String(n).padStart(2, '0');
export const REFRESH_NOTE = `Her gün ${REFRESH_TIMES.map(([h, m]) => `${two(h)}:${two(m)}`).join(' ve ')}'de yenilenir`;
