/**
 * Kişiye özel pano deposu. Kartlar kullanıcı adına göre saklanır; giriş yapan
 * kişi kendi panosunu görür. Kayıt tarayıcıda tutulur, sunucuya taşınacaksa
 * değişecek tek yer bu dosyadır.
 */
import type { SqlResult } from '../engine';

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
  /** Kartı doğuran soru; başlık olarak da kullanılır. */
  title: string;
  sql: string;
  chart: ChartKind;
  /** Derinlikli görünüm (sütun, çubuk ve pasta için). */
  depth: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  createdAt: string;
};

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
