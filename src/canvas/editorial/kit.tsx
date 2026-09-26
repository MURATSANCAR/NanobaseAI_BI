import { useEffect, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import DbTimingBadge, { type DbTiming } from '../DbTiming';
import { btnGhost, nf } from '../admin/ui';

/** Editoryal Süreç (M1–M8) ekranlarının ortak parçaları. */

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

/** Modül ekranının kabuğu: üst şerit, başlık ve kaydırılan gövde. */
export function ModuleFrame({
  route,
  crumb,
  title,
  lead,
  source,
  presence = 'Kaynak: CRM',
  aside,
  children,
}: {
  route: string;
  crumb: string;
  title: string;
  lead: string;
  source: string;
  /** Üst şeridin sağındaki kısa durum; verilmezse kaynak adı. */
  presence?: string;
  /** Başlığın sağ üstüne yerleşen öge (ör. kitap arama). */
  aside?: ReactNode;
  children: ReactNode;
}) {
  // Menüde olmayan detay sayfası (stüdyo işi, kapak…): kırıntının son halkası iş adı + bölüm.
  const { pathname } = useLocation();
  const onDetail = pathname.replace(/\/+$/, '') !== route;
  const detail = onDetail ? [title, crumb].filter((x, i, a) => x && a.indexOf(x) === i).join(' · ') || undefined : undefined;
  return (
    <Shell
      head={{ tenant: 'Timaş Yayınları', section: 'Editoryal', crumb, source, presence, detail }}
    >
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
              {route !== '/editoryal' ? (
                <Link to="/editoryal" className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline">
                  <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                  Masam
                </Link>
              ) : (
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Editoryal Süreç</div>
              )}
              <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
              <p className="mt-1 max-w-[70ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export function Kpi({ label, value, help, active, onClick }: { label: string; value: string; help: string; active?: boolean; onClick?: () => void }) {
  const body = (
    <>
      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-1 font-mono text-[26px] font-bold leading-none tabular-nums tracking-tight sm:text-[30px]">{value}</div>
      <div className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">{help}</div>
    </>
  );
  const cls = `glass-panel rounded-2xl p-3.5 text-left shadow-glass-float sm:rounded-3xl sm:p-4 ${active ? 'ring-2 ring-canvas-violet' : ''}`;
  if (!onClick) return <div className={cls}>{body}</div>;
  return (
    <button type="button" onClick={onClick} aria-pressed={active} className={`${cls} transition-transform duration-150 ease-out active:scale-[0.98]`}>
      {body}
    </button>
  );
}

export function KpiRow({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4 lg:gap-4">{children}</div>;
}

export function Panel({ children }: { children: ReactNode }) {
  return <section className="glass-panel rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">{children}</section>;
}

/** Sayfa aralığı, veritabanı süresi ve önceki/sonraki düğmeleri. */
export function Pager({
  page,
  pageSize,
  total,
  shown,
  loading,
  fetching,
  db,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  shown: number;
  loading: boolean;
  fetching: boolean;
  db?: DbTiming | null;
  onPage: (p: number) => void;
}) {
  const from = page * pageSize + 1;
  const range = total ? `${nf.format(from)}–${nf.format(from + shown - 1)} / ${nf.format(total)}` : loading ? 'Okunuyor…' : 'Kayıt yok';
  const last = (page + 1) * pageSize >= total;
  return (
    <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2 text-[12px] font-semibold text-canvas-muted">
        {fetching && <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />}
        <span className="font-mono tabular-nums">{range}</span>
        <DbTimingBadge timing={db ?? null} />
      </div>
      <div className="flex gap-1.5">
        <button type="button" className={btnGhost} disabled={page === 0 || fetching} onClick={() => onPage(Math.max(0, page - 1))}>
          <ChevronLeft aria-hidden className="h-4 w-4" />
          Önceki
        </button>
        <button type="button" className={btnGhost} disabled={last || fetching} onClick={() => onPage(page + 1)}>
          Sonraki
          <ChevronRight aria-hidden className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
