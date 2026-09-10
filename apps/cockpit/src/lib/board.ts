/**
 * Masanın düzeni: hangi kart, hangi sırada, hangi genişlikte.
 *
 * Masa daha önce elle dizilmiş bir JSX bloğuydu — okuyan kişi neyi önce görmek istediğini
 * söyleyemiyordu. Burada düzen bir veri: kartların sırası, boyu ve sohbetten iliştirilmiş olanlar
 * tek bir listede duruyor, ve o liste tarayıcıda saklanıyor.
 *
 * Saklama şimdilik tarayıcıda: kişi bazında kayıt için sistemde bir kullanıcı kavramı yok
 * (portalın kendi girişi kapalı). Şema bunu bilerek kurulu — `Board` olduğu gibi bir sunucu
 * kaydına yazılabilir, tek değişecek olan `load`/`save`.
 */

export type Span = 1 | 2 | 4;          // 4'lük ızgarada kaç sütun kaplar

/** Masanın kendi kartları: verisi zaten yüklü, sadece nereye konacağı sorulur. */
export type BuiltinId =
  | 'netRevenue' | 'grossMargin' | 'returnRate' | 'discountRate'
  | 'cashflow' | 'imprints' | 'channels' | 'purchases';

export type Tile =
  | { id: string; kind: 'builtin'; builtin: BuiltinId; span: Span }
  /** Sohbetten iliştirilen kart: sorunun kendisi, çalıştıracağı SQL ve nasıl çizileceği. */
  | { id: string; kind: 'pinned'; span: Span; title: string; question: string; sql: string;
      chart: string; xKey?: string; yKey?: string; labelKey?: string; valueKey?: string;
      format?: string; pinnedAt: number };

export type Board = { version: 2; tiles: Tile[] };

const KEY = 'timas-cockpit-board-v2';

export const DEFAULT_BOARD: Board = {
  version: 2,
  tiles: [
    { id: 'b-netRevenue', kind: 'builtin', builtin: 'netRevenue', span: 1 },
    { id: 'b-grossMargin', kind: 'builtin', builtin: 'grossMargin', span: 1 },
    { id: 'b-returnRate', kind: 'builtin', builtin: 'returnRate', span: 1 },
    { id: 'b-discountRate', kind: 'builtin', builtin: 'discountRate', span: 1 },
    { id: 'b-cashflow', kind: 'builtin', builtin: 'cashflow', span: 4 },
    { id: 'b-imprints', kind: 'builtin', builtin: 'imprints', span: 4 },
    { id: 'b-channels', kind: 'builtin', builtin: 'channels', span: 2 },
    { id: 'b-purchases', kind: 'builtin', builtin: 'purchases', span: 2 },
  ],
};

/** Kaydedilmiş düzen ile bugünkü kart listesini uzlaştırır.
 *
 *  Bir sürüm yeni bir kart getirdiğinde eski düzende o kart yoktur; kaydı yok sayıp varsayılana
 *  dönmek kişinin işini siler, körü körüne yüklemek yeni kartı görünmez yapar. Doğrusu: kaydedilen
 *  sıra korunur, yeni kartlar sona eklenir, artık var olmayanlar düşer. */
export function reconcile(saved: Board | null): Board {
  if (!saved || saved.version !== 2 || !Array.isArray(saved.tiles)) return DEFAULT_BOARD;
  const known = new Set(DEFAULT_BOARD.tiles.map((t) => (t as { builtin: string }).builtin));
  const tiles = saved.tiles.filter(
    (t) => t.kind === 'pinned' || (t.kind === 'builtin' && known.has(t.builtin)),
  );
  const present = new Set(tiles.filter((t) => t.kind === 'builtin').map((t) => (t as { builtin: string }).builtin));
  for (const t of DEFAULT_BOARD.tiles) {
    if (t.kind === 'builtin' && !present.has(t.builtin)) tiles.push(t);
  }
  return { version: 2, tiles };
}

export function load(): Board {
  try {
    const raw = localStorage.getItem(KEY);
    return reconcile(raw ? (JSON.parse(raw) as Board) : null);
  } catch {
    return DEFAULT_BOARD;          // bozuk ya da erişilemez depo, boş ekrandan iyidir
  }
}

export function save(board: Board): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(board));
  } catch {
    /* özel pencere ya da dolu depo: düzen bu oturumda yaşar, ekran yine çalışır */
  }
}

export function move(tiles: Tile[], from: string, to: string): Tile[] {
  const a = tiles.findIndex((t) => t.id === from);
  const b = tiles.findIndex((t) => t.id === to);
  if (a < 0 || b < 0 || a === b) return tiles;
  const next = tiles.slice();
  const [moved] = next.splice(a, 1);
  next.splice(b, 0, moved);
  return next;
}

/** Aynı soru iki kez iliştirilmesin: kimliği sorunun kendisinden türetiyoruz. */
export function pinId(question: string, sql: string): string {
  let h = 0;
  for (const ch of `${question}|${sql}`) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return `p-${(h >>> 0).toString(36)}`;
}

export const SPANS: Span[] = [1, 2, 4];
export const SPAN_LABEL: Record<Span, string> = { 1: 'çeyrek', 2: 'yarım', 4: 'tam' };
