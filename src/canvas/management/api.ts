import { ENGINE_BASE, ENGINE_ENABLED, freshHeaders } from '../engine';

/** Yönetim raporları modülünün köprü uçları: /api/v1/management/*. */

/** Power BI biçim dizeleri: n0 = "#,0", plain = "0", general = biçimsiz ondalık, date = Short Date. */
export type ColumnFormat = 'text' | 'int' | 'dec' | 'money' | 'date' | 'oneri' | 'n0' | 'plain' | 'general';

/** Toplam satırı: sum = Toplam, tukenme = Σ StokAdedi ÷ Σ OrtSatisHizi (Power BI ölçüsü), null = boş. */
export type ColumnTotal = 'sum' | 'tukenme' | null;

export type ReportColumn = {
  key: string;
  label: string;
  group: string;
  format: ColumnFormat;
  total?: ColumnTotal;
  /** Kaynak sorgu kimliği ya da `hesap:<formül adı>` */
  source: string;
};

export type ReportView = {
  id: string;
  title: string;
  hint: string;
  columns: ReportColumn[];
  rows: Array<Array<string | number | null>>;
  filters: string[];
  /** Power BI dosyasında kayıtlı açılış dilimleyicileri; ekran bunları seçili açar. null = boş değer. */
  defaultFilters?: Array<{ key: string; values: Array<string | null> }>;
  /** Sekmenin son kullanıcı açıklaması ve altındaki SQL'ler (ZEKI AI Tahminleme). */
  explain?: ReportExplain;
  /** Bu sekmenin öneri düzeyleri (yoksa raporunki). ZEKI sekmesi "Talep yok" ekler. */
  oneriLevels?: string[];
  /** Satır yokken tabloda gösterilecek metin (ör. tahmin hazırlanıyor). */
  emptyText?: string | null;
};

export type ReportExplain = {
  title: string;
  intro: string[];
  sections: Array<{ title: string; items: string[] }>;
  table?: { caption: string; head: string[]; rows: string[][] };
  notes: string[];
  formulas?: Array<{ name: string; text: string }>;
  sql: Array<{ id: string; title: string; description: string; sql: string }>;
};

export type ReportSnapshot = {
  id: string;
  refreshing: boolean;
  refreshIntervalSeconds: number;
  /** Sunucu saati (epoch sn): geri sayım istemci saatinden bağımsız olsun diye */
  serverTime: number;
  /** `since` ile sorulduysa ve veri değişmediyse true; `data` gelmez */
  unchanged?: boolean;
  hasData?: boolean;
  refreshStartedAt?: number | null;
  nextRefreshAt?: number | null;
  failedAt?: number;
  updatedAt?: number;
  durationMs?: number;
  error?: string | null;
  data?: {
    views: ReportView[];
    oneriLevels: string[];
    sourceStats: Record<string, { rows: number; dbMs: number | null; skipped?: string | null; warning?: string | null }>;
    /** Okunamayan kaynak parçaları (ör. Logo'da henüz açılmamış yıl görünümü); ekranda uyarı olur. */
    warnings?: string[];
    asOf: string;
  };
};

export type ReportSource = {
  id: string;
  connection: 'logo' | 'crm';
  database: string;
  title: string;
  description: string;
  sql: string;
  stats?: { rows: number; dbMs: number | null; skipped?: string | null } | null;
};

export type ReportSources = {
  sources: ReportSource[];
  formulas: Array<{ name: string; text: string }>;
  notes: string[];
};

export type ReportSummary = {
  id: string;
  title: string;
  description: string;
  refreshIntervalSeconds: number;
  updatedAt?: number;
  sources: number;
  views: Array<{ id: string; title: string; rows: number }>;
};

async function call<T>(path: string, method: 'GET' | 'POST' = 'GET'): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const response = await fetch(`${ENGINE_BASE}/api/v1/management/${path}`, {
    method,
    credentials: 'include',
    headers: method === 'GET' ? freshHeaders() : undefined,
    signal: AbortSignal.timeout(60_000),
  });
  if (!response.ok) {
    if ([401, 403].includes(response.status)) throw new Error('Raporu görmek için oturum açmanız gerekiyor.');
    const body = await response.json().catch(() => null);
    const detail = body?.detail;
    throw new Error(typeof detail === 'string' ? detail : detail?.message || 'Rapor sunucusu yanıt vermedi.');
  }
  return response.json();
}

export const managementApi = {
  list: () => call<{ reports: ReportSummary[] }>('reports'),
  report: (id: string, since?: number) => call<ReportSnapshot>(`reports/${id}${since ? `?since=${since}` : ''}`),
  sources: (id: string) => call<ReportSources>(`reports/${id}/sources`),
  refresh: (id: string) => call<ReportSnapshot & { started: boolean }>(`reports/${id}/refresh`, 'POST'),
};

/** Ekrandaki veriyi koruyarak durumu tazeler: değişmeyen veri yeniden indirilmez. */
export function mergeSnapshot(prev: ReportSnapshot | undefined, next: ReportSnapshot): ReportSnapshot {
  if (next.data || !prev?.data) return next;
  return { ...next, data: prev.data };
}

export const clockOffset = (snap?: ReportSnapshot, receivedAt?: number) =>
  snap?.serverTime && receivedAt ? snap.serverTime - receivedAt / 1000 : 0;

export const ONERI_TONE: Record<string, string> = {
  'Risk/Acil': 'mg-tone-risk',
  Kritik: 'mg-tone-critical',
  'Karar Ver': 'mg-tone-decide',
  'Takip Et': 'mg-tone-watch',
  'Yeterli Stok': 'mg-tone-ok',
  'Talep yok': 'mg-tone-none',
};

const intFmt = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const decFmt = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
const moneyFmt = new Intl.NumberFormat('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const n0Fmt = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const plainFmt = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0, useGrouping: false });
const generalFmt = new Intl.NumberFormat('tr-TR', { maximumSignificantDigits: 15, useGrouping: false });

/** Köprü DAX'ın sonsuz ve NaN sonuçlarını metin taşır (JSON'da sayı değiller). */
export function numberOf(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  if (typeof value === 'number') return value;
  if (value === '∞') return Infinity;
  if (value === '-∞') return -Infinity;
  if (value === 'NaN') return NaN;
  const n = Number(value);
  return Number.isNaN(n) ? null : n;
}

const special = (n: number) => (Number.isNaN(n) ? 'NaN' : n === Infinity ? '∞' : n === -Infinity ? '-∞' : null);

export function formatCell(value: string | number | null | undefined, format: ColumnFormat): string {
  // Power BI boş değeri boş hücre olarak gösterir.
  if (value === null || value === undefined || value === '') return '';
  if (format === 'n0' || format === 'plain' || format === 'general') {
    const n = numberOf(value);
    if (n === null) return String(value);
    return special(n) ?? (format === 'n0' ? n0Fmt : format === 'plain' ? plainFmt : generalFmt).format(n);
  }
  if (format === 'int' || format === 'dec' || format === 'money') {
    const n = typeof value === 'number' ? value : Number(value);
    if (!Number.isFinite(n)) return String(value);
    return (format === 'int' ? intFmt : format === 'dec' ? decFmt : moneyFmt).format(n);
  }
  if (format === 'date') {
    const s = String(value);
    const d = new Date(s.length <= 10 ? `${s}T00:00:00` : s);
    return Number.isNaN(d.getTime()) ? s : d.toLocaleDateString('tr-TR');
  }
  return String(value);
}

export const sinceText = (epochSeconds?: number) => {
  if (!epochSeconds) return 'henüz hazırlanmadı';
  const minutes = Math.round((Date.now() / 1000 - epochSeconds) / 60);
  if (minutes < 1) return 'az önce';
  if (minutes < 60) return `${minutes} dk önce`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} sa önce`;
  return new Date(epochSeconds * 1000).toLocaleString('tr-TR');
};
