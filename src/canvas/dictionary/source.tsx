import { useEffect, useState } from 'react';
import type { DataSource } from '../engine';

/**
 * Logo ve CRM ayrımı. Veri sözlüğü, eş anlamlılar ve onaylar aynı seçimi paylaşır: birinde "CRM" seçen
 * ötekine geçtiğinde yine CRM'i görür. Seçim yalnız bu tarayıcıda hatırlanır.
 */

export type SourceFilter = 'all' | DataSource;

const KEY = 'zeki.sozluk.kaynak';
const EVENT = 'zeki-sozluk-kaynak';

export const SOURCE_LABEL: Record<DataSource, string> = { logo: 'Logo', crm: 'CRM' };

function read(): SourceFilter {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === 'logo' || v === 'crm' ? v : 'all';
  } catch {
    return 'all';
  }
}

export function useSourceFilter(): [SourceFilter, (v: SourceFilter) => void] {
  const [value, setValue] = useState<SourceFilter>(read);
  useEffect(() => {
    const sync = () => setValue(read());
    window.addEventListener(EVENT, sync);
    return () => window.removeEventListener(EVENT, sync);
  }, []);
  const set = (v: SourceFilter) => {
    setValue(v);
    try {
      window.localStorage.setItem(KEY, v);
    } catch {
      /* gizli pencere: seçim yalnız bu ekranda kalır */
    }
    window.dispatchEvent(new Event(EVENT));
  };
  return [value, set];
}

/** Kaydın kaynağı seçime uyuyor mu? Kaynağı bilinmeyen kayıt yalnız "Tümü"nde görünür. */
export function matchesSource(filter: SourceFilter, source: DataSource | null | undefined): boolean {
  return filter === 'all' || source === filter;
}

const nf = new Intl.NumberFormat('tr-TR');

export function SourceTabs({
  value,
  onChange,
  counts,
  className = '',
}: {
  value: SourceFilter;
  onChange: (v: SourceFilter) => void;
  counts?: Partial<Record<SourceFilter, number>>;
  className?: string;
}) {
  const options: Array<{ id: SourceFilter; label: string }> = [
    { id: 'all', label: 'Tümü' },
    { id: 'logo', label: 'Logo' },
    { id: 'crm', label: 'CRM' },
  ];
  return (
    <div role="radiogroup" aria-label="Veri kaynağı" className={`grid grid-cols-3 gap-1 rounded-xl bg-slate-100/90 p-1 ${className}`}>
      {options.map((o) => {
        const on = value === o.id;
        return (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.id)}
            className={[
              'flex min-h-10 items-center justify-center gap-1.5 rounded-lg px-2 text-[12.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] motion-reduce:transform-none sm:min-h-8',
              on ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink',
            ].join(' ')}
          >
            {o.id !== 'all' && <SourceDot source={o.id} />}
            {o.label}
            {counts?.[o.id] != null && <span className="font-mono text-[11px] font-bold tabular-nums text-canvas-muted">{nf.format(counts[o.id]!)}</span>}
          </button>
        );
      })}
    </div>
  );
}

const TONE: Record<DataSource, { dot: string; badge: string }> = {
  logo: { dot: 'bg-sky-500', badge: 'bg-sky-50 text-sky-700 ring-sky-200/70' },
  crm: { dot: 'bg-fuchsia-500', badge: 'bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-200/70' },
};

function SourceDot({ source }: { source: DataSource }) {
  return <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-full ${TONE[source].dot}`} />;
}

/** Satırın yanındaki küçük etiket: "Logo" ya da "CRM". Kaynak bilinmiyorsa hiçbir şey çizmez. */
export function SourceBadge({ source, className = '' }: { source: DataSource | null | undefined; className?: string }) {
  if (!source) return null;
  return (
    <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[10.5px] font-extrabold ring-1 ring-inset ${TONE[source].badge} ${className}`}>
      {SOURCE_LABEL[source]}
    </span>
  );
}

/** Birden çok tanımı olan terimin kaynakları: tekrarsız ve Logo önce. */
export function sourcesOf(list: Array<{ source?: DataSource | null }>): DataSource[] {
  const set = new Set(list.map((x) => x.source).filter((x): x is DataSource => x === 'logo' || x === 'crm'));
  return (['logo', 'crm'] as DataSource[]).filter((s) => set.has(s));
}
