import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { fmtDay, fmtShort, scoreTone, type Chip, type Customer } from './api';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';

/** Saha ekranlarının ortak parçaları: kabuk, müşteri kartı, gerekçe çipleri, puan rozeti. Telefon önce (320/390 px):
 *  listeler kart, dokunma hedefleri en az 44 px, geniş tablo yalnız yöneticinin raporunda ve kendi kabında kayar. */

export function FieldFrame({
  crumb,
  title,
  lead,
  source,
  presence,
  back,
  aside,
  children,
}: {
  crumb: string;
  title: string;
  lead?: string;
  source: string;
  presence: string;
  /** Detay sayfasında listeye dönüş. */
  back?: { to: string; label: string };
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Saha satış ve okul', crumb, source, presence, detail: back ? title : undefined }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to={back.to} className="inline-flex min-h-8 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    {back.label}
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Saha satış ve okul</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                {lead && <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>}
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[420px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

const TONE = {
  err: 'bg-red-50 text-red-700',
  warn: 'bg-amber-50 text-amber-800',
  muted: 'bg-slate-100 text-canvas-ink',
} as const;

export function ScoreBadge({ value }: { value: number | null | undefined }) {
  return (
    <span
      className={`inline-flex h-9 min-w-9 shrink-0 items-center justify-center rounded-xl px-1.5 font-mono text-[13px] font-extrabold tabular-nums ${TONE[scoreTone(value)]}`}
      title="Öncelik puanı (kural; bileşenler aşağıda)"
    >
      {value === null || value === undefined ? '—' : Math.round(value)}
    </span>
  );
}

/** Gerekçe çipleri: neden bu müşteri bugün. `limit` verilirse ilk birkaçı, kalanı «+n». */
export function Chips({ chips, limit }: { chips: Chip[]; limit?: number }) {
  if (!chips.length) return null;
  const shown = limit ? chips.slice(0, limit) : chips;
  const rest = chips.length - shown.length;
  return (
    <div className="flex flex-wrap gap-1">
      {shown.map((c) => (
        <span key={c.key} className="inline-flex max-w-full items-center rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-bold leading-snug text-canvas-ink">
          <span className="truncate">{c.label}</span>
        </span>
      ))}
      {rest > 0 && <span className="inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold text-canvas-muted">+{rest}</span>}
    </div>
  );
}

/** Liste satırı: puan, unvan, il, vadesi geçmiş, gerekçe; tamamı brifinge götürür (tek dokunuş). */
export function CustomerRow({ c, showRep, trailing, k, alan = 'items[]' }: { c: Customer; showRep?: boolean; trailing?: ReactNode; k?: Kaynaklar; alan?: string }) {
  return (
    <li className="relative flex items-stretch gap-2">
      <Link
        to={`/saha/musteri/${encodeURIComponent(c.code)}`}
        className="flex min-h-14 min-w-0 flex-1 items-start gap-2.5 rounded-2xl border border-slate-100 bg-white/85 p-3 transition-transform duration-150 ease-out active:scale-[0.98]"
      >
        <ScoreBadge value={c.puan} />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <div className="min-w-0 truncate text-[13.5px] font-extrabold">{c.unvan || c.code}</div>
            <div className="shrink-0 font-mono text-[12px] font-bold tabular-nums text-red-700">{c.vadesiGecmis ? fmtShort(c.vadesiGecmis) : ''}</div>
          </div>
          <div className="mt-0.5 truncate text-[11.5px] text-canvas-muted">
            {[c.il, c.kanal, showRep ? c.temsilciAd || c.temsilci : null, c.sonOdeme ? `son ödeme ${fmtDay(c.sonOdeme)}` : null]
              .filter(Boolean)
              .join(' · ')}
          </div>
          <div className="mt-1.5">
            <Chips chips={c.gerekce} limit={3} />
          </div>
        </div>
        <ChevronRight aria-hidden className="mt-2 h-4 w-4 shrink-0 text-canvas-muted" />
      </Link>
      {k && (
        // «i» bağlantının dışında: dokunuş brifinge götürmesin.
        <span className="flex shrink-0 items-start pt-3">
          <SqlInfo k={k} alan={alan} row={c.code} label={`${c.unvan || c.code}: puan ve alacak`} />
        </span>
      )}
      {trailing}
    </li>
  );
}

export function Stat({ label, value, help, tone, info }: { label: string; value: string; help?: string; tone?: 'err' | 'warn'; info?: ReactNode }) {
  // «137,4 Mn ₺»: rakam büyük, birim küçük; dar telefonda (320 px, kutu içi ~66 px) birim alt satıra iner, kesilmez.
  const m = /^(.*\d)\s+((?:bin|Mn)\s*₺|₺)$/.exec(value);
  const [num, unit] = m ? [m[1], m[2]] : [value, ''];
  return (
    <div className="min-w-0 rounded-2xl border border-slate-100 bg-white/85 p-3">
      <div className="flex items-center gap-0.5 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
        <span className="min-w-0 truncate">{label}</span>
        {info}
      </div>
      <div className={`mt-0.5 flex flex-wrap items-baseline gap-x-1 font-mono text-[17px] font-extrabold leading-tight tabular-nums sm:text-[20px] ${tone === 'err' ? 'text-red-700' : tone === 'warn' ? 'text-amber-800' : ''}`}>
        <span className="min-w-0 break-all">{num}</span>
        {unit && <span className="whitespace-nowrap font-sans text-[11px] font-bold sm:text-[13px]">{unit}</span>}
      </div>
      {help && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-2xl border border-dashed border-slate-200 bg-white/60 px-4 py-8 text-center text-[12.5px] text-canvas-muted">{children}</div>;
}

/** Bölüm başlığı + gövde (brifingin Ödeme · Sipariş · Hedef · Öneri · Notlar bölümleri). */
export function Block({ id, title, help, action, children }: { id?: string; title: string; help?: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-20 rounded-2xl border border-slate-100 bg-white/80 p-3 sm:p-4">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-[15px] font-extrabold tracking-tight">{title}</h2>
          {help && <p className="mt-0.5 text-[11.5px] leading-snug text-canvas-muted">{help}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

/** Anahtar–değer satırı (telefonda iki sütun). */
export function KV({ k, v, tone, info }: { k: string; v: ReactNode; tone?: 'err' | 'warn'; info?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
      <span className="flex min-w-0 items-center gap-0.5 text-[12px] text-canvas-muted">
        {k}
        {info}
      </span>
      <span className={`shrink-0 text-right font-mono text-[12.5px] font-bold tabular-nums ${tone === 'err' ? 'text-red-700' : tone === 'warn' ? 'text-amber-800' : ''}`}>{v}</span>
    </div>
  );
}
