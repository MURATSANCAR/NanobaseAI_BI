import type { ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ChevronLeft, FileSpreadsheet } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Note, Pill, btnGhost } from '../admin/ui';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { fmtDay, fmtInt, shippingApi, type ExportList, type Freshness, type Meta, type Order } from './api';

/** Kargo ekranlarının ortak kabuğu ve küçük parçaları. Menü tek; alt ekranlar arasında üstte kısa bir bağlantı şeridi. */

const LINKS = [
  { to: '/kargo', label: 'Günlük hat', end: true },
  { to: '/kargo/hatalar', label: 'Entegrasyon hataları' },
  { to: '/kargo/bekleyen', label: 'Teslim bekleyen' },
  { to: '/kargo/firmalar', label: 'Firma karnesi', need: 'firmalar' as const },
  { to: '/kargo/mutabakat', label: 'Mutabakat', need: 'mutabakat' as const },
];

export function ShippingFrame({ title, lead, crumb, detail, back, aside, meta, children }: {
  title: string;
  lead: string;
  crumb: string;
  /** Detay sayfasında kırıntının son halkası. */
  detail?: string;
  back?: boolean;
  aside?: ReactNode;
  meta?: Meta;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Lojistik', crumb, source: 'Kaynak: CRM sipariş ve kargo kaydı · Logo', presence: 'Kargo', detail }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                {back ? (
                  <Link to="/kargo" className="inline-flex min-h-11 items-center gap-1 text-[11px] font-bold uppercase tracking-wide text-canvas-violet hover:underline sm:min-h-0">
                    <ChevronLeft aria-hidden className="h-3.5 w-3.5" />
                    Kargo
                  </Link>
                ) : (
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Lojistik · Kargo</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            {meta && <SubNav meta={meta} />}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

function SubNav({ meta }: { meta: Meta }) {
  const links = LINKS.filter((l) => !l.need || meta.me[l.need]);
  return (
    <nav aria-label="Kargo ekranları" className="-mx-1 overflow-x-auto px-1">
      <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.end}
            className={({ isActive }) =>
              `inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                isActive ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
              }`
            }
          >
            {l.label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

/** Kargo kaydının veri sonu; eskiyse uyarı. Her ekranda yazılır (0 satır «gecikme yok» demek değildir). */
/** `k`: cevabın sorgu bilgisi; kayıt sayısı ve okunamayan değer sayıları «i» ile kargo kaydı sorgusuna bağlanır. */
export function FreshNote({ f, k }: { f: Freshness | undefined; k?: Kaynaklar }) {
  if (!f) return null;
  const unread = Object.entries(f.okunamayan).filter(([, n]) => n > 0);
  const labels: Record<string, string> = { irsTarihi: 'irsaliye tarihi', teslimTarihi: 'teslim tarihi', tutar: 'tutar', desi: 'desi', sevk_adeti: 'sevk adedi', agirlik: 'ağırlık' };
  return (
    <Note tone={f.eski ? 'warn' : 'info'}>
      {k && <SqlInfo k={k} alan="kargoVeri" label="Kargo kayıtları" className="mr-1" />}
      Kargo kayıtları: {fmtInt(f.kayit)} kayıt, veri sonu {fmtDay(f.veriSonu)}
      {f.sonKayit ? ` (son kayıt ${fmtDay(f.sonKayit)})` : ''}.
      {f.tarihsiz > 0 && ` Tarihi okunamayan ${fmtInt(f.tarihsiz)} kayıt dönem hesaplarına girmez.`}
      {unread.length > 0 && ` Okunamayan değer: ${unread.map(([k, n]) => `${labels[k] ?? k} ${fmtInt(n)}`).join(', ')}.`}
      {f.not && <span className="block">{f.not}</span>}
    </Note>
  );
}

export function ExportButton({ list, params, can, label = 'Excel' }: { list: ExportList; params?: Record<string, string | number | undefined>; can: boolean; label?: string }) {
  if (!can) return null;
  return (
    <a className={btnGhost} href={shippingApi.exportUrl(list, params)}>
      <FileSpreadsheet aria-hidden className="h-4 w-4" />
      {label}
    </a>
  );
}

const STATUS_TONE: Record<number, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  100000000: 'ok',
  100000015: 'ok',
  100000014: 'violet',
  100000011: 'warn',
  100000012: 'warn',
  100000013: 'warn',
  100000001: 'err',
};

export function StatusPill({ o }: { o: Pick<Order, 'durum' | 'durumAdi'> }) {
  return <Pill tone={STATUS_TONE[o.durum] ?? 'muted'}>{o.durumAdi}</Pill>;
}

/** Sipariş satırı (liste kartı): telefonda alt alta, geniş ekranda sütunlu. Tıklayınca gönderi kartı. */
export function OrderRow({ o, extra }: { o: Order; extra?: ReactNode }) {
  return (
    <Link
      to={`/kargo/gonderi/${o.id}`}
      className="grid grid-cols-1 gap-2 rounded-2xl border border-slate-100 bg-white/80 p-3 transition-colors duration-150 hover:border-canvas-violet/40 active:scale-[0.99] md:grid-cols-[minmax(0,1fr)_170px_150px] md:items-center"
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1.5">
          <StatusPill o={o} />
          {o.tipAdi && <span className="text-[11px] font-semibold text-canvas-muted">{o.tipAdi}</span>}
          {o.il && <span className="text-[11px] font-semibold text-canvas-muted">· {o.il}</span>}
        </div>
        <div className="mt-1 break-words font-mono text-[13px] font-extrabold">{o.no ?? '—'}</div>
        <div className="line-clamp-1 break-words text-[12px] text-canvas-muted">{o.musteri ?? 'Müşteri yok'}{o.cariKodu ? ` · ${o.cariKodu}` : ''}</div>
        {extra}
      </div>
      <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-0.5">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted md:hidden">Kargo</span>
        <span className="text-[12.5px] font-bold">{o.firma ?? 'Firma seçilmemiş'}</span>
        <span className="font-mono text-[11.5px] text-canvas-muted">{o.takipNo ?? 'takip no yok'}</span>
      </div>
      <div className="flex flex-wrap items-center gap-2 md:flex-col md:items-start md:gap-0.5">
        <span className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted md:hidden">Tarih</span>
        <span className="font-mono text-[12px] tabular-nums">{fmtDay(o.asamalar.sevk ?? o.tarih)}</span>
        <span className="text-[11px] text-canvas-muted">{o.asamalar.sevk ? 'sevk' : 'sipariş'}</span>
      </div>
    </Link>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="py-8 text-center text-[12.5px] text-canvas-muted">{children}</div>;
}
