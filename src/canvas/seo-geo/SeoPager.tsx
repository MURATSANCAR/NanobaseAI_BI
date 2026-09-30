import { useRef, type CSSProperties } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import PageNumbers, { revealListTop } from '../components/PageNumbers';
import { fmt } from './api';

/**
 * SEO & GEO tablolarının ortak sayfalayıcısı (ZEKI-29): aralık ve toplam, önceki/sonraki, sayfa numaraları.
 * `start` satır ofsetidir (0, size, 2·size…); tek sayfalık listede çıkmaz. Sayfa değişince tablonun kutusunun
 * başı ekrana gelir.
 */
export default function SeoPager({
  start,
  total,
  size,
  onChange,
  style = { marginTop: 12 },
}: {
  start: number;
  total: number;
  size: number;
  onChange: (start: number) => void;
  style?: CSSProperties;
}) {
  const ref = useRef<HTMLDivElement>(null);
  if (total <= size) return null;
  const page = Math.floor(start / size);
  const count = Math.ceil(total / size);
  const go = (s: number) => {
    onChange(s);
    revealListTop(ref.current);
  };
  return (
    <div ref={ref} className="sg-pager" style={style}>
      <span className="sg-mono">
        {fmt(start + 1)}–{fmt(Math.min(total, start + size))} / {fmt(total)}
      </span>
      <div className="sg-pager-nav">
        <button className="sg-button" disabled={start === 0} onClick={() => go(Math.max(0, start - size))} aria-label="Önceki sayfa">
          <ChevronLeft size={16} aria-hidden />
        </button>
        <PageNumbers page={page} count={count} onPage={(p) => go(p * size)} tone="outline" />
        <button className="sg-button" disabled={start + size >= total} onClick={() => go(start + size)} aria-label="Sonraki sayfa">
          <ChevronRight size={16} aria-hidden />
        </button>
      </div>
    </div>
  );
}
