/**
 * Kişiye özel pano deposu. Doğrusu sunucuda (`boardApi`, köprü `board.py`);
 * buradaki tarayıcı kaydı yalnız açılışta anında çizmek ve eski panoları
 * sunucuya bir kez taşımak için tutulur.
 */
import type { BoardCardDto, BoardRefresh, SqlResult } from '../engine';

export type ChartKind =
  | 'column'
  | 'bar'
  | 'line'
  | 'area'
  | 'pie'
  | 'donut'
  | 'scatter'
  | 'treemap'
  | 'kpi'
  | 'table';

export type BoardCard = {
  id: string;
  /** Kart başlığı; ilk değeri soru, sonra kişi değiştirebilir. */
  title: string;
  /** Kartı doğuran soru; karşılaştırma isteğinde yeniden sorulur. */
  question?: string;
  /** Kişinin iş notu, başlığın altında. */
  note?: string;
  sql: string;
  chart: ChartKind;
  /** Derinlikli görünüm (sütun, çubuk ve pasta için). */
  depth: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  /** Üst üste binen kartlarda en son tutulan üstte kalır. */
  z?: number;
  /** Kartın altındaki SQL paneli açık mı; kişi kapatana kadar öyle kalır. */
  sqlOpen?: boolean;
  /** Sunucudaki zamanlayıcı: elle, saatlik, her gün refreshAt'ta. */
  refresh?: BoardRefresh;
  refreshAt?: string | null;
  createdAt: string;
};

/** Sunucu kaydını istemci kartına çevirir (sonuç ayrı önbelleğe gider). */
export function fromDto(d: BoardCardDto): BoardCard {
  return {
    id: d.id,
    title: d.title,
    question: d.question || undefined,
    note: d.note || undefined,
    sql: d.sql,
    chart: (d.chart as ChartKind) || 'table',
    depth: Boolean(d.depth),
    x: d.x,
    y: d.y,
    w: d.w,
    h: d.h,
    z: d.z,
    sqlOpen: Boolean(d.sqlOpen),
    refresh: d.refresh || 'manual',
    refreshAt: d.refreshAt,
    createdAt: d.createdAt || new Date().toISOString(),
  };
}

/** Sürükleme ızgarası (px). Kartlar bu adımlarla hizalanır, düzen dağınık durmaz. */
export const GRID = 8;
export const snap = (v: number) => Math.round(v / GRID) * GRID;

/** Bir sonraki "en üstte" değeri. */
export const topZ = (cards: BoardCard[]) => Math.max(20, ...cards.map((c) => c.z ?? 20)) + 1;

const KEY = (user: string) => `timas-pano-v1:${user || 'anonim'}`;

export function loadBoard(user: string): BoardCard[] {
  try {
    const raw = window.localStorage.getItem(KEY(user));
    const parsed = raw ? (JSON.parse(raw) as BoardCard[]) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveBoard(user: string, cards: BoardCard[]): void {
  try {
    window.localStorage.setItem(KEY(user), JSON.stringify(cards));
  } catch {
    /* saklama kapalıysa pano yalnız bu oturumda yaşar */
  }
}

/** Yeni kart için boş yer: en alttaki kartın altına koyar. */
export function nextSlot(cards: BoardCard[], w = 460, h = 300): { x: number; y: number; w: number; h: number } {
  if (!cards.length) return { x: 24, y: 16, w, h };
  const row = cards.filter((c) => c.y === Math.min(...cards.map((k) => k.y)));
  const rightMost = Math.max(...row.map((c) => c.x + c.w));
  if (rightMost + w + 24 < 1600) return { x: rightMost + 20, y: row[0].y, w, h };
  const bottom = Math.max(...cards.map((c) => c.y + c.h));
  return { x: 24, y: bottom + 20, w, h };
}

export const newId = () => `k${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;

/**
 * Kartların son sonucu. Pano açılınca kart bununla anında çizilir, sorgu
 * arka planda tazelenir; kullanıcı açılışta beklemez. Düzen anahtarından
 * ayrı tutulur ki büyük sonuçlar yerleşim kaydını bozmasın.
 */
export type CardResult = SqlResult<Record<string, unknown>> & { at: number };

const RKEY = (user: string) => `timas-pano-sonuc-v1:${user || 'anonim'}`;

export function loadResults(user: string): Record<string, CardResult> {
  try {
    const raw = window.localStorage.getItem(RKEY(user));
    const parsed = raw ? (JSON.parse(raw) as Record<string, CardResult>) : {};
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function saveResult(user: string, id: string, r: CardResult): void {
  try {
    const all = loadResults(user);
    all[id] = r;
    window.localStorage.setItem(RKEY(user), JSON.stringify(all));
  } catch {
    /* sığmazsa önbelleksiz devam: kart yine sorgudan çizilir */
  }
}

export function dropResult(user: string, id: string): void {
  try {
    const all = loadResults(user);
    delete all[id];
    window.localStorage.setItem(RKEY(user), JSON.stringify(all));
  } catch {
    /* yok say */
  }
}
