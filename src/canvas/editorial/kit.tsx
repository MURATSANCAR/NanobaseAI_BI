import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import DbTimingBadge, { type DbTiming } from '../DbTiming';
import { btnGhost, nf } from '../admin/ui';
import { Explain } from '../components/Explain';
import PageNumbers, { revealListTop } from '../components/PageNumbers';

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

/**
 * `info`: rakamın sorgu bilgisi düğmesi (`<SqlInfo …/>`); `explain`: göstergenin sade dille anlamı («?»). İkisi de
 * kartın sağ üst köşesinde, tıklanan kartın düğmesinin dışında durur (iç içe düğme olmasın diye).
 */
export function Kpi({
  label,
  value,
  help,
  active,
  onClick,
  info,
  explain,
}: {
  label: string;
  value: string;
  help: string;
  active?: boolean;
  onClick?: () => void;
  info?: ReactNode;
  /** Göstergenin sade dille anlamı; köşede «?» olarak durur (bkz. components/Explain). */
  explain?: ReactNode;
}) {
  const corner = info || explain;
  const body = (
    <>
      <div className={`text-[11px] font-bold uppercase tracking-wide text-canvas-muted ${info && explain ? 'pr-12' : corner ? 'pr-6' : ''}`}>{label}</div>
      <div className="mt-1 font-mono text-[26px] font-bold leading-none tabular-nums tracking-tight sm:text-[30px]">{value}</div>
      <div className="mt-1.5 text-[11.5px] leading-snug text-canvas-muted">{help}</div>
    </>
  );
  const cls = `glass-panel rounded-2xl p-3.5 text-left shadow-glass-float sm:rounded-3xl sm:p-4 ${active ? 'ring-2 ring-canvas-violet' : ''}`;
  const card = !onClick ? (
    <div className={corner ? `${cls} h-full` : cls}>{body}</div>
  ) : (
    <button type="button" onClick={onClick} aria-pressed={active} className={`${cls} transition-transform duration-150 ease-out active:scale-[0.98] ${corner ? 'h-full w-full' : ''}`}>
      {body}
    </button>
  );
  if (!corner) return card;
  return (
    <div className="relative">
      {card}
      <span className="absolute right-3 top-3 flex items-center gap-1 sm:right-3.5 sm:top-3.5">
        {explain && <Explain label={label}>{explain}</Explain>}
        {info}
      </span>
    </div>
  );
}

export function KpiRow({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4 lg:gap-4">{children}</div>;
}

/** `min-w-0`: ızgara hücresinde içindeki geniş tablo (TableWrap, min 640px) kolonu genişletmesin; tablo kendi
 *  kutusunda kaysın, yandaki paneller kırpılmasın. */
export function Panel({ children }: { children: ReactNode }) {
  return <section className="glass-panel min-w-0 rounded-2xl p-3 shadow-glass-float sm:rounded-3xl sm:p-4">{children}</section>;
}

/**
 * Sayfa aralığı, veritabanı süresi, sayfa numaraları ve önceki/sonraki düğmeleri (ZEKI-29). Toplam kayıt sayısı hep
 * yazar, bütün sayfalara numarayla gidilir; veri kesilmez.
 *
 * Sayfa değişince listenin kutusunun başı ekrana gelir (alttan «Sonraki»ye basan kişi yeni sayfanın ortasında kalmasın).
 * `placement="bottom"`: listenin üstünde de sayfalayıcı olan ekranlarda alttaki ikinci kopya; tek sayfalık listede
 * çıkmaz, veritabanı süresini tekrarlamaz.
 */
export function Pager({
  page,
  pageSize,
  total,
  shown,
  loading,
  fetching,
  db,
  onPage,
  placement = 'top',
}: {
  page: number;
  pageSize: number;
  total: number;
  shown: number;
  loading: boolean;
  fetching: boolean;
  db?: DbTiming | null;
  onPage: (p: number) => void;
  placement?: 'top' | 'bottom';
}) {
  const ref = useRef<HTMLDivElement>(null);
  const count = pageSize > 0 ? Math.ceil(total / pageSize) : 0;
  if (placement === 'bottom' && count <= 1) return null;
  const from = page * pageSize + 1;
  const range = total ? `${nf.format(from)}–${nf.format(from + shown - 1)} / ${nf.format(total)}` : loading ? 'Okunuyor…' : 'Kayıt yok';
  const last = (page + 1) * pageSize >= total;
  const go = (p: number) => {
    onPage(p);
    revealListTop(ref.current);
  };
  return (
    <div ref={ref} className="mt-3 flex flex-wrap items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-2 text-[12px] font-semibold text-canvas-muted">
        {fetching && <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />}
        <span className="font-mono tabular-nums">{range}</span>
        {placement === 'top' && <DbTimingBadge timing={db ?? null} />}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <button type="button" className={`${btnGhost} !px-2.5 sm:!px-3.5`} aria-label="Önceki sayfa" disabled={page === 0 || fetching} onClick={() => go(Math.max(0, page - 1))}>
          <ChevronLeft aria-hidden className="h-4 w-4" />
          <span className="hidden sm:inline">Önceki</span>
        </button>
        <PageNumbers page={page} count={count} onPage={go} disabled={fetching} />
        <button type="button" className={`${btnGhost} !px-2.5 sm:!px-3.5`} aria-label="Sonraki sayfa" disabled={last || fetching} onClick={() => go(page + 1)}>
          <span className="hidden sm:inline">Sonraki</span>
          <ChevronRight aria-hidden className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}
