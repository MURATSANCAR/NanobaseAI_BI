/**
 * Sayfa numaraları (ZEKI-29): «1 … 4 5 6 … 20». Bütün sayfalara erişilir; ilk ve son sayfa her zaman görünür,
 * aradakiler «…» ile kısalır. Telefonda yalnız ilk, geçerli ve son sayfa (sığsın diye); sm'den itibaren komşular da.
 * Sayfa sıfırdan sayılır (API'lerin `page` alanı gibi), ekranda birden yazılır.
 */

/** Gösterilecek sayfalar; `gap` = atlanan aralık. Tek sayfalık boşluk «…» yerine sayfanın kendisiyle dolar. */
export function pageItems(page: number, count: number, radius: number): Array<number | 'gap'> {
  if (count <= 0) return [];
  const want = new Set<number>([0, count - 1]);
  for (let i = page - radius; i <= page + radius; i++) if (i >= 0 && i < count) want.add(i);
  const sorted = [...want].sort((a, b) => a - b);
  const out: Array<number | 'gap'> = [];
  sorted.forEach((n, i) => {
    const prev = sorted[i - 1];
    if (prev !== undefined && n - prev === 2) out.push(prev + 1);
    else if (prev !== undefined && n - prev > 2) out.push('gap');
    out.push(n);
  });
  return out;
}

const nf = new Intl.NumberFormat('tr-TR');

const base =
  'inline-flex min-h-10 min-w-10 items-center justify-center rounded-xl px-2 font-mono text-[12.5px] font-extrabold tabular-nums transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-50 disabled:active:scale-100 motion-reduce:transition-none motion-reduce:active:scale-100 sm:min-h-8 sm:min-w-8';
const TONE = {
  /** Portal düğmeleriyle aynı yumuşak zemin (admin/ui btnGhost). */
  soft: { idle: 'bg-slate-100 text-canvas-ink hover:bg-slate-200', on: 'bg-canvas-violet text-white shadow-sm' },
  /** Beyaz, kenarlıklı düğme dili (SEO & GEO, yönetim raporları). */
  outline: { idle: 'border border-slate-200 bg-white text-canvas-ink hover:bg-violet-50', on: 'border border-canvas-violet bg-canvas-violet text-white' },
} as const;

function Row({ items, page, onPage, disabled, tone, className }: { items: Array<number | 'gap'>; page: number; onPage: (p: number) => void; disabled?: boolean; tone: keyof typeof TONE; className: string }) {
  return (
    <ol className={`${className} items-center gap-1`}>
      {items.map((n, i) =>
        n === 'gap' ? (
          <li key={`gap-${i}`} aria-hidden className="px-0.5 text-[12px] font-bold text-canvas-muted">
            …
          </li>
        ) : (
          <li key={n}>
            <button
              type="button"
              aria-label={`Sayfa ${nf.format(n + 1)}`}
              aria-current={n === page ? 'page' : undefined}
              disabled={disabled && n !== page}
              onClick={() => n !== page && onPage(n)}
              className={`${base} ${n === page ? TONE[tone].on : TONE[tone].idle}`}
            >
              {nf.format(n + 1)}
            </button>
          </li>
        ),
      )}
    </ol>
  );
}

export default function PageNumbers({
  page,
  count,
  onPage,
  disabled,
  tone = 'soft',
}: {
  /** Sıfırdan sayılan geçerli sayfa. */
  page: number;
  /** Toplam sayfa sayısı. */
  count: number;
  onPage: (p: number) => void;
  /** Yeni sayfa okunurken: geçerli dışındaki numaralar beklesin. */
  disabled?: boolean;
  tone?: keyof typeof TONE;
}) {
  if (count <= 1) return null;
  return (
    <nav aria-label="Sayfalar" className="flex items-center">
      <Row items={pageItems(page, count, 0)} page={page} onPage={onPage} disabled={disabled} tone={tone} className="flex sm:hidden" />
      <Row items={pageItems(page, count, 1)} page={page} onPage={onPage} disabled={disabled} tone={tone} className="hidden sm:flex" />
    </nav>
  );
}

/**
 * Alttaki sayfalayıcıyla sayfa değişince liste başı ekranda kalsın: en yakın kaydırılan kap, listenin kutusunun
 * başına alınır (kabuk kökü kaydırılmaz). Kutunun başı zaten görünüyorsa bir şey yapılmaz.
 */
export function revealListTop(from: HTMLElement | null) {
  if (!from) return;
  const host = (from.closest('section, [data-list-top]') as HTMLElement | null) ?? from.parentElement;
  if (!host) return;
  let scroller: HTMLElement | null = host.parentElement;
  while (scroller) {
    const oy = getComputedStyle(scroller).overflowY;
    if ((oy === 'auto' || oy === 'scroll') && scroller.scrollHeight > scroller.clientHeight) break;
    scroller = scroller.parentElement;
  }
  if (!scroller) return;
  const top = host.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
  if (top < 0) scroller.scrollTop += top - 12;
}
