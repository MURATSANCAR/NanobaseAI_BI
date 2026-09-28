import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, Download, Info } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import Sheet from '../editorial/studio/reader/Sheet';
import SqlCode from '../management/SqlCode';
import { Note, Pill, btnGhost, errText } from '../admin/ui';
import { fmtDay } from '../budget/api';
import { ENGINE_ENABLED } from '../engine';
import { STATE_TONE, n0, stockApi, type Item, type StockState } from './api';

/** Depo ve stok ekranlarının ortak kabuğu ve küçük parçaları. Menü alanı «Lojistik» (M43, M44 ve M52 ortak). */

export function StockFrame({ crumb, title, lead, source, back, aside, children }: {
  crumb: string;
  title: string;
  lead: string;
  source: string;
  back?: { to: string; label: string };
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Lojistik', crumb, source, presence: 'Logo + CRM, salt okunur', detail: back ? title : undefined }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to={back.to} className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    {back.label}
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Lojistik · Depo ve stok</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="flex w-full shrink-0 flex-wrap gap-2 lg:w-auto lg:justify-end">{aside}</div>}
            </header>
            {!ENGINE_ENABLED && <Note tone="warn">Veri bağlantısı bu derlemede tanımlı değil.</Note>}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Logo verisinin bittiği gün: donmuş kopyada «bugünkü stok» iddia edilmez (analiz §8). */
export function DataDay({ day, extra }: { day: string | null | undefined; extra?: ReactNode }) {
  return (
    <div className="rounded-2xl bg-white/70 px-3 py-2 text-[12px] font-semibold leading-snug text-canvas-muted">
      {day ? (
        <>
          Stok ve satış Logo verisinin son günü <strong className="text-canvas-ink">{fmtDay(day)}</strong> itibarıyladır; tükenme tarihi bu günden sayılır.
          CRM raf stoğu ve depo hattı canlıdır.
        </>
      ) : (
        'Logo verisinin son günü okunamadı.'
      )}
      {extra ? <> {extra}</> : null}
    </div>
  );
}

export function StatePill({ state, label }: { state: StockState; label: string }) {
  return <Pill tone={STATE_TONE[state]}>{label}</Pill>;
}

export function BookCell({ it }: { it: Pick<Item, 'stokKodu' | 'ad' | 'yayinevi'> }) {
  return (
    <Link to={`/stok/${encodeURIComponent(it.stokKodu)}`} className="group block min-w-0">
      <span className="block break-words font-bold group-hover:text-canvas-violet group-hover:underline">{it.ad ?? it.stokKodu}</span>
      <span className="block font-mono text-[11px] text-canvas-muted">
        {it.stokKodu}
        {it.yayinevi ? ` · ${it.yayinevi}` : ''}
      </span>
    </Link>
  );
}

/** Kaynak paneli (ⓘ): hesabın kuralı ve çalışan SQL'in kendisi. SQL yalnız «SQL'i göster» yetkisiyle görünür. */
export function SourcesButton({ rules }: { rules: Array<[string, string]> }) {
  const [open, setOpen] = useState(false);
  const q = useQuery({ queryKey: ['stock', 'sources'], queryFn: stockApi.sources, enabled: open && ENGINE_ENABLED, staleTime: 60_000 });
  return (
    <>
      <button type="button" className={btnGhost} onClick={() => setOpen(true)} aria-label="Nasıl hesaplandı">
        <Info aria-hidden className="h-4 w-4" />
        Nasıl hesaplandı
      </button>
      <Sheet open={open} modal onClose={() => setOpen(false)} title="Nasıl hesaplandı" subtitle="Kurallar ve kaynak sorgular. Logo ve CRM yalnız okunur." wide>
        <div className="flex flex-col gap-4 text-[12.5px] leading-snug">
          <dl className="flex flex-col gap-2">
            {rules.map(([k, v]) => (
              <div key={k}>
                <dt className="font-extrabold">{k}</dt>
                <dd className="text-canvas-muted">{v}</dd>
              </div>
            ))}
          </dl>
          {q.error && <Note tone="err">{errText(q.error, 'Kaynaklar okunamadı.')}</Note>}
          {q.data?.sources.map((s) => (
            <section key={s.id} className="flex flex-col gap-1">
              <div className="font-extrabold">
                {s.baslik} <span className="font-semibold text-canvas-muted">· {s.baglanti}</span>
              </div>
              <div className="text-canvas-muted">{s.aciklama}</div>
              {s.sql && <SqlCode sql={s.sql} label={s.baslik} />}
            </section>
          ))}
        </div>
      </Sheet>
    </>
  );
}

export function ExportLink({ href, show }: { href: string; show: boolean }) {
  if (!show) return null;
  return (
    <a className={btnGhost} href={href} download>
      <Download aria-hidden className="h-4 w-4" />
      Excel
    </a>
  );
}

/** Satır içi süzgeç çipleri (yatay kaydırılır, sayfa taşmaz). */
export function Chips<T extends string>({ items, value, onChange, label }: {
  items: ReadonlyArray<{ key: T; label: string; count?: number | null }>;
  value: T;
  onChange: (k: T) => void;
  label: string;
}) {
  return (
    <div className="-mx-1 overflow-x-auto px-1" role="group" aria-label={label}>
      <div className="flex w-max gap-1.5">
        {items.map((f) => (
          <button
            key={f.key || 'hepsi'}
            type="button"
            aria-pressed={value === f.key}
            onClick={() => onChange(f.key)}
            className={`inline-flex min-h-11 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-[12px] font-bold transition-[transform,background-color,color] duration-150 ease-out active:scale-[0.97] sm:min-h-8 ${
              value === f.key ? 'bg-canvas-ink text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
            }`}
          >
            {f.label}
            {f.count !== undefined && f.count !== null && <span className="font-mono text-[11px] tabular-nums opacity-70">{n0(f.count)}</span>}
          </button>
        ))}
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-8 text-center text-[12.5px] text-canvas-muted">{children}</div>;
}

export const num = 'text-right font-mono tabular-nums';

/** Durum çubuğu altında «ilk okuma sürebilir» notu: Logo'nun ilk taraması dakikalar sürebilir. */
export function Loading({ what }: { what: string }) {
  return <Empty>{what} okunuyor… İlk okuma Logo ve CRM'den birkaç dakika sürebilir; sonra beş dakika önbellekten gelir.</Empty>;
}
