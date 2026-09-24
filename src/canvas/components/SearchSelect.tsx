import { useCallback, useLayoutEffect, useMemo, useRef, useState, type MutableRefObject } from 'react';
import { Combobox } from '@base-ui/react/combobox';
import { Check, ChevronDown, X } from 'lucide-react';

/**
 * Yazarak aranan seçim kutusu. Kitap adı, yazar, kişi gibi yüzlerce/binlerce seçenekli alanlar için
 * düz `<select>` yerine kullanılır; kısa listeler (durum, sıralama) düz `<select>` kalır.
 *
 * - Base UI Combobox üstünde kurulu: combobox/listbox ARIA rolleri, ↑↓ Enter Esc, Home/End.
 * - Eşleşme Türkçe büyük/küçük harf ve aksan duyarsız (İ/ı, ş/s, ç/c, ğ/g, ö/o, ü/u); kelimeler
 *   sırası fark etmeksizin aranır ("sancar murat" = "Murat Sancar").
 * - Liste sanal: yalnız görünen satırlar çizilir, bütün seçenekler listededir (tavan yok).
 * - Açılış/kapanış animasyonsuz: günde onlarca kez, çoğu klavyeyle açılan bir süzgeç.
 *
 * Değer düz metindir; `''` (tekli) ya da `[]` (çoklu) "seçim yok / Tümü" anlamına gelir.
 */
export type SearchOption = { value: string; label: string };

type Common = {
  options: ReadonlyArray<SearchOption | string>;
  /** Ekran okuyucu adı; görünür etiket varsa onunla aynı olmalı. */
  label: string;
  /** Seçim yokken kutuda görünen metin (ör. "Tümü"). */
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  id?: string;
};
type Single = Common & { multiple?: false; value: string; onChange: (value: string) => void };
type Multiple = Common & { multiple: true; value: string[]; onChange: (value: string[]) => void };
export type SearchSelectProps = Single | Multiple;

/** Türkçe küçük harf + aksansız: "İSTANBUL", "istanbul", "Istanbul", "ıstanbul" aynı anahtara iner. */
export const foldTr = (s: string) =>
  s
    .toLocaleLowerCase('tr')
    .replace(/ı/g, 'i')
    .normalize('NFD')
    .replace(/\p{M}/gu, '');

const coarse = () => typeof window !== 'undefined' && !!window.matchMedia?.('(pointer: coarse)').matches;
const OVERSCAN = 8;

export default function SearchSelect(props: SearchSelectProps) {
  const { label, placeholder = 'Tümü', disabled, className = '', id } = props;
  const options = useMemo<SearchOption[]>(
    () => props.options.map((o) => (typeof o === 'string' ? { value: o, label: o } : o)),
    [props.options],
  );
  // Filtre her tuşta binlerce satırı dolaşır; katlanmış etiketler bir kez hesaplanır.
  const folded = useMemo(() => new Map(options.map((o) => [o, foldTr(o.label)])), [options]);
  const byValue = useMemo(() => new Map(options.map((o) => [o.value, o])), [options]);
  const toOption = useCallback((v: string) => byValue.get(v) ?? { value: v, label: v }, [byValue]);

  const filter = useCallback(
    (item: SearchOption, query: string) => {
      const words = foldTr(query).split(/\s+/).filter(Boolean);
      if (!words.length) return true;
      const hay = folded.get(item) ?? foldTr(item.label);
      return words.every((w) => hay.includes(w));
    },
    [folded],
  );

  const [row] = useState(() => (coarse() ? 44 : 36));
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const reveal = (index: number) => {
    const el = scrollRef.current;
    if (!el || index < 0) return;
    const top = index * row;
    if (top < el.scrollTop) el.scrollTop = top;
    else if (top + row > el.scrollTop + el.clientHeight) el.scrollTop = top + row - el.clientHeight;
  };

  const shared = {
    items: options,
    filter,
    locale: 'tr' as const,
    virtualized: true,
    disabled,
    isItemEqualToValue: (a: SearchOption, b: SearchOption) => a.value === b.value,
    itemToStringLabel: (o: SearchOption) => o.label,
    itemToStringValue: (o: SearchOption) => o.value,
    onItemHighlighted: (item: SearchOption | undefined, d: { reason: string; index: number }) => {
      // Fareyle gezinirken kaydırma yapılmaz; klavye ve açılışta vurgulanan satır görünür tutulur.
      if (item && d.reason !== 'pointer') queueMicrotask(() => reveal(d.index));
    },
  };

  const box =
    `flex min-h-11 w-full min-w-0 items-center gap-1 rounded-xl border border-slate-200 bg-white pl-3 pr-1 text-canvas-ink ` +
    `focus-within:border-canvas-violet focus-within:ring-2 focus-within:ring-violet-200 sm:min-h-10 ${disabled ? 'opacity-60' : ''} ${className}`;
  const input =
    'min-w-[4rem] flex-1 bg-transparent py-1.5 text-base font-semibold !outline-none placeholder:font-semibold placeholder:text-canvas-ink/70 sm:text-[12.5px]';
  const iconBtn =
    'flex h-11 w-9 shrink-0 items-center justify-center rounded-lg text-canvas-muted hover:text-canvas-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-canvas-violet sm:h-8 sm:w-8';

  const popup = (
    <Combobox.Portal>
      <Combobox.Positioner className="z-[90] outline-none" sideOffset={4} collisionPadding={8}>
        <Combobox.Popup className="w-[var(--anchor-width)] min-w-[12rem] max-w-[var(--available-width)] overflow-hidden rounded-xl border border-slate-200 bg-white text-canvas-ink shadow-[0_12px_32px_-12px_rgba(27,31,42,0.25)]">
          <Rows row={row} scrollRef={scrollRef} />
        </Combobox.Popup>
      </Combobox.Positioner>
    </Combobox.Portal>
  );

  if (props.multiple) {
    const value = props.value.map(toOption);
    return (
      <Combobox.Root<SearchOption, true>
        {...shared}
        multiple
        value={value}
        onValueChange={(v) => props.onChange((v ?? []).map((o) => o.value))}
      >
        <Combobox.InputGroup className={`${box} py-1`}>
          <Combobox.Chips className="flex min-w-0 flex-1 flex-wrap items-center gap-1" aria-label={value.length ? `${label}: seçilenler` : undefined}>
            {value.map((o) => (
              <Combobox.Chip
                key={o.value}
                aria-label={o.label}
                className="flex min-h-8 max-w-full items-center gap-0.5 rounded-lg bg-violet-50 pl-2 text-[12px] font-bold text-canvas-ink outline-none focus-within:bg-violet-100 data-[highlighted]:bg-violet-100"
              >
                <span className="truncate">{o.label}</span>
                <Combobox.ChipRemove aria-label={`${o.label} seçimini kaldır`} className="flex h-8 w-8 shrink-0 items-center justify-center text-canvas-muted hover:text-canvas-ink [@media(pointer:coarse)]:h-11 [@media(pointer:coarse)]:w-10">
                  <X className="h-3.5 w-3.5" aria-hidden />
                </Combobox.ChipRemove>
              </Combobox.Chip>
            ))}
            <Combobox.Input id={id} aria-label={label} placeholder={value.length ? 'Ara…' : placeholder} className={input} />
          </Combobox.Chips>
          {value.length > 0 && (
            <Combobox.Clear aria-label={`${label} seçimlerini temizle`} className={iconBtn}>
              <X className="h-4 w-4" aria-hidden />
            </Combobox.Clear>
          )}
          <Combobox.Trigger aria-label={`${label} listesini aç`} className={iconBtn}>
            <ChevronDown className="h-4 w-4" aria-hidden />
          </Combobox.Trigger>
        </Combobox.InputGroup>
        {popup}
      </Combobox.Root>
    );
  }

  const value = props.value ? toOption(props.value) : null;
  return (
    <Combobox.Root<SearchOption>
      {...shared}
      value={value}
      onValueChange={(v) => props.onChange(v?.value ?? '')}
    >
      <Combobox.InputGroup className={box}>
        <Combobox.Input id={id} aria-label={label} placeholder={placeholder} className={input} />
        {value && (
          <Combobox.Clear aria-label={`${label} seçimini temizle`} className={iconBtn}>
            <X className="h-4 w-4" aria-hidden />
          </Combobox.Clear>
        )}
        <Combobox.Trigger aria-label={`${label} listesini aç`} className={iconBtn}>
          <ChevronDown className="h-4 w-4" aria-hidden />
        </Combobox.Trigger>
      </Combobox.InputGroup>
      {popup}
    </Combobox.Root>
  );
}

/** Sabit satır yüksekliğiyle pencereleme: süzülmüş listenin tamamı kaydırılabilir, yalnız görünen kısım çizilir. */
function Rows({ row, scrollRef }: { row: number; scrollRef: MutableRefObject<HTMLDivElement | null> }) {
  const items = Combobox.useFilteredItems<SearchOption>();
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [view, setView] = useState({ top: 0, height: 0 });
  const total = items.length * row;

  useLayoutEffect(() => {
    if (!el) return;
    const read = () => setView({ top: el.scrollTop, height: el.clientHeight });
    read();
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, [el, total]);

  const attach = (node: HTMLDivElement | null) => {
    scrollRef.current = node;
    setEl(node);
  };

  const first = Math.max(0, Math.floor(view.top / row) - OVERSCAN);
  const last = Math.min(items.length, Math.ceil((view.top + (view.height || row * 10)) / row) + OVERSCAN);

  return (
    <>
      <Combobox.Status className="sr-only">{items.length ? `${items.length.toLocaleString('tr-TR')} sonuç` : ''}</Combobox.Status>
      <Combobox.Empty className="px-3 py-3 text-[12.5px] text-canvas-muted empty:hidden">Eşleşen kayıt yok.</Combobox.Empty>
      <Combobox.List className="outline-none">
        {items.length > 0 && (
          <div
            role="presentation"
            ref={attach}
            onScroll={(e) => {
              const t = e.currentTarget;
              setView({ top: t.scrollTop, height: t.clientHeight });
            }}
            className="overflow-y-auto overscroll-contain"
            style={{ height: `min(${total}px, 22.5rem, var(--available-height, 22.5rem))` }}
          >
            <div role="presentation" className="relative w-full" style={{ height: total }}>
              {items.slice(first, last).map((item, i) => {
                const index = first + i;
                return (
                  <Combobox.Item
                    key={item.value}
                    index={index}
                    value={item}
                    aria-setsize={items.length}
                    aria-posinset={index + 1}
                    className="absolute left-0 top-0 flex w-full cursor-default select-none items-center gap-2 px-3 text-[13px] font-semibold outline-none data-[highlighted]:bg-violet-50 data-[selected]:text-canvas-violet sm:text-[12.5px]"
                    style={{ height: row, transform: `translateY(${index * row}px)` }}
                  >
                    <span className="min-w-0 flex-1 truncate" title={item.label}>
                      {item.label}
                    </span>
                    <Combobox.ItemIndicator className="shrink-0">
                      <Check className="h-4 w-4" aria-hidden />
                    </Combobox.ItemIndicator>
                  </Combobox.Item>
                );
              })}
            </div>
          </div>
        )}
      </Combobox.List>
    </>
  );
}
