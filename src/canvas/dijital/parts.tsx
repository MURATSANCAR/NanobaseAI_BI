import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Pill } from '../admin/ui';
import { LISTING_TONE, RIGHT_TONE, type Chip, type Me, type Right } from './api';

/** Dijital yayın ekranlarının ortak kabuğu ve küçük parçaları. Sekme çubuğu ve onay penceresi bütçe ekranınınkiyle aynıdır. */
export { Tabs, AskSheet } from '../budget/parts';

const LINKS = [
  { to: '/dijital-yayin', label: 'Katalog', end: true },
  { to: '/dijital-yayin/firsatlar', label: 'Fırsatlar', end: false },
  { to: '/dijital-yayin/satis', label: 'Satış', end: false, sales: true },
];

export function DigitalFrame({ title, lead, crumb, detail, me, aside, children }: {
  title: string;
  lead: string;
  crumb: 'Dijital yayın' | 'Dijital satış';
  detail?: string;
  me?: Me;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const links = LINKS.filter((l) => !l.sales || !me || me.canSales);
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Dijital ve topluluk', crumb, source: 'Kaynak: CRM · Logo · platform raporları', presence: crumb, detail }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Dijital ve topluluk · Dijital yayın</div>
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
                <nav aria-label="Dijital yayın bölümleri" className="mt-2 flex flex-wrap gap-1.5">
                  {links.map((l) => (
                    <NavLink
                      key={l.to}
                      to={l.to}
                      end={l.end}
                      className={({ isActive }) =>
                        `inline-flex min-h-11 items-center rounded-xl px-3 text-[12.5px] font-extrabold sm:min-h-9 ${isActive ? 'bg-canvas-violet text-white' : 'bg-white/70 text-canvas-ink hover:bg-white'}`
                      }
                    >
                      {l.label}
                    </NavLink>
                  ))}
                </nav>
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

export function RightPill({ value, label }: { value: Right | null | undefined; label?: string | null }) {
  if (!value) return <Pill tone="muted">bilinmiyor</Pill>;
  return <Pill tone={RIGHT_TONE[value] ?? 'muted'}>{label ?? value}</Pill>;
}

/** Platform çipleri: yalnız kullanıcının ya da onaylı raporun girdiği durum; bilinmeyen «bilinmiyor» yazar. */
export function Chips({ items, empty = 'Platform tanımlı değil' }: { items: Chip[]; empty?: string }) {
  if (!items.length) return <span className="text-[11.5px] text-canvas-muted">{empty}</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((c) => (
        <span key={c.platformId} title={c.tarih ? `${c.durumAdi} · ${c.tarih}` : c.durumAdi} className="inline-flex items-center gap-1">
          <span className="text-[11px] font-semibold text-canvas-muted">{c.platform}</span>
          <Pill tone={LISTING_TONE[c.durum]}>{c.durumAdi}</Pill>
        </span>
      ))}
    </span>
  );
}

/** Tıklanan kart listesinin üstündeki satır: kartlardaki rakamların sorgu bilgisi burada (iç içe düğme olmasın diye «i»
 *  kartın içine konmaz; tablo başlığındaki `InfoLabel`'ın karşılığı). */
export function ListHead({ children }: { children: ReactNode }) {
  return <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] font-semibold text-canvas-muted">{children}</div>;
}

/** Kısa etiketli değer (ayrıntı kutuları). `info`: rakamın sorgu bilgisi («i»), etiketin yanında. */
export function Fact({ label, value, help, info }: { label: string; value: ReactNode; help?: ReactNode; info?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
        <span className="min-w-0">{label}</span>
        {info}
      </div>
      <div className="mt-0.5 break-words text-[13.5px] font-bold">{value}</div>
      {help && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}
