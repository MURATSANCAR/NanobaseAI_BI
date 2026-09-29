import { useState } from 'react';

/**
 * Kısa liste + «Tümünü göster». Özet kutularında ilk birkaç kayıt görünür; geri kalanı sessizce kesilmez, sayısıyla
 * yazılır ve tek dokunuşla açılır (proje kuralı: kullanıcı istemedikçe sayı tavanı yok).
 *
 *   const more = useShowMore(items, 6);
 *   {more.shown.map(…)}
 *   <ShowMoreButton more={more} noun="eser" />
 */
export function useShowMore<T>(items: readonly T[] | null | undefined, first: number) {
  const [all, setAll] = useState(false);
  const list = items ?? [];
  const hidden = Math.max(0, list.length - first);
  return {
    shown: all || hidden === 0 ? list : list.slice(0, first),
    hidden,
    all,
    toggle: () => setAll((v) => !v),
  };
}

export function ShowMoreButton({
  more,
  noun = 'kayıt',
  className = '',
}: {
  more: { hidden: number; all: boolean; toggle: () => void };
  /** Gizli kalanın adı: «+12 eser daha». */
  noun?: string;
  className?: string;
}) {
  if (more.hidden === 0) return null;
  return (
    <button
      type="button"
      onClick={more.toggle}
      aria-expanded={more.all}
      className={`mt-1.5 inline-flex min-h-10 items-center rounded-lg px-1 text-[12px] font-bold text-canvas-violet transition-transform duration-150 ease-out hover:underline active:scale-[0.97] sm:min-h-0 ${className}`}
    >
      {more.all ? 'Daha az göster' : `+${more.hidden.toLocaleString('tr-TR')} ${noun} daha · Tümünü göster`}
    </button>
  );
}
