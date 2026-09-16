/**
 * "Veritabanında 1,24 sn'de geldi" etiketi. Değer köprünün ölçtüğü gerçek yürütme süresidir (dbMs):
 * yalnız kaynaktan satır beklenen süre. Önbellekten gelen cevapta ilk yürütmenin süresi gösterilir ve
 * ne zaman hesaplandığı açıkça yazılır. Süre ölçülmediyse sayı uydurulmaz.
 *
 * Tek alan sözleşmesi (backend `db_timing`): { dbMs, cached, computedAt (epoch sn), dbParts? }.
 */
export type DbPart = { name: string; source?: string | null; ms: number | null; cached?: boolean };

export type DbTiming = {
  dbMs?: number | null;
  cached?: boolean | null;
  /** Epoch saniye (köprü) ya da ISO metni. */
  computedAt?: number | string | null;
  dbParts?: DbPart[] | null;
  /** Birden çok sorgunun toplamıysa sorgu sayısı. */
  queries?: number | null;
};

const dec = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** 340 → "340 ms", 1240 → "1,24 sn", 83000 → "1 dk 23 sn". */
export function formatDbMs(ms: number): string {
  if (ms < 1000) return `${Math.max(0, Math.round(ms))} ms`;
  if (ms < 60_000) return `${dec.format(ms / 1000)} sn`;
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)} dk ${s % 60} sn`;
}

/** Türkçe bulunma eki: "340 ms'de", "1,24 sn'de" (birimler kısaltma okunuşuyla "-de" alır). */
const withSuffix = (t: string) => `${t}'de`;

function epochMs(v: DbTiming['computedAt']): number | null {
  if (v == null || v === '') return null;
  if (typeof v === 'number') return v > 1e12 ? v : v * 1000;
  const t = Date.parse(v);
  return Number.isFinite(t) ? t : null;
}

export function ago(ms: number, now = Date.now()): string {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  if (s < 45) return 'az önce';
  if (s < 3600) return `${Math.max(1, Math.round(s / 60))} dk önce`;
  if (s < 86_400) return `${Math.round(s / 3600)} sa önce`;
  return `${Math.round(s / 86_400)} gün önce`;
}

/** Etiketin düz metni; ekran okuyucu ve title için de kullanılır. null: gösterilecek bilgi yok. */
export function dbTimingText(t: DbTiming | null | undefined, now = Date.now()): string | null {
  if (!t) return null;
  const ms = typeof t.dbMs === 'number' && Number.isFinite(t.dbMs) ? t.dbMs : null;
  let head = ms == null ? 'Veritabanı süresi ölçülmedi' : `Veritabanında ${withSuffix(formatDbMs(ms))} geldi`;
  if (ms != null && t.queries && t.queries > 1) head += ` (${t.queries} sorgu)`;
  const at = epochMs(t.computedAt);
  if (t.cached) return at ? `${head} · önbellekten, ${ago(at, now)} hesaplandı` : `${head} · önbellekten`;
  if (at && now - at > 90_000) return `${head} · ${ago(at, now)}`;
  return head;
}

function partsText(parts: DbPart[] | null | undefined): string | null {
  if (!parts || parts.length < 2) return null;
  const label = (p: DbPart) => (p.source === 'crm' ? 'CRM' : p.source === 'logo' ? 'Logo' : p.name);
  return parts.map((p) => `${label(p)} ${p.ms == null ? 'ölçülmedi' : formatDbMs(p.ms)}`).join(' · ');
}

type Props = { timing: DbTiming | null | undefined; className?: string; tone?: 'muted' | 'onDark' };

/** Küçük, tek satırlık bilgi etiketi. Dar ekranda kelime kırarak sarar; taşma yapmaz. */
export default function DbTimingBadge({ timing, className = '', tone = 'muted' }: Props) {
  const text = dbTimingText(timing);
  if (!text) return null;
  const parts = partsText(timing?.dbParts);
  const color = tone === 'onDark' ? 'text-white/75' : 'text-canvas-muted';
  return (
    <span
      className={`inline-flex min-w-0 max-w-full items-center gap-1 text-[11px] font-medium leading-snug ${color} ${className}`}
      title={parts ? `${text} — ${parts}` : text}
      role="note"
      aria-label={parts ? `${text}. Parçalar: ${parts}` : text}
    >
      <svg aria-hidden="true" className="h-3 w-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
      </svg>
      <span className="min-w-0 break-words tabular-nums">
        {text}
        {parts && <span className="opacity-80"> ({parts})</span>}
      </span>
    </span>
  );
}

/** Canlı sorgu olmayan, şema taramasında okunmuş değerler için dürüst etiket. */
export function ScanBadge({ scannedAt, className = '' }: { scannedAt?: string | null; className?: string }) {
  const at = epochMs(scannedAt ?? null);
  const text = at
    ? `Şema taramasında veritabanından okundu · ${ago(at)} · süre ölçülmedi`
    : 'Şema taramasında okundu · süre ölçülmedi';
  return (
    <span className={`inline-flex min-w-0 max-w-full items-center gap-1 text-[11px] font-medium leading-snug text-canvas-muted ${className}`} role="note" aria-label={text} title={text}>
      <svg aria-hidden="true" className="h-3 w-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <ellipse cx="12" cy="5" rx="8" ry="3" />
        <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      </svg>
      <span className="min-w-0 break-words">{text}</span>
    </span>
  );
}
