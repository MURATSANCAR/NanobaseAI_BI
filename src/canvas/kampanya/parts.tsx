import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Pill } from '../admin/ui';
import { fmtDay, fmtPct } from '../budget/api';
import { STATUS_TONE, span, type Calendar, type Durum, type Kontrol } from './api';

/** Kampanya ekranlarının ortak parçaları: kabuk, durum etiketi, kontrol rozetleri, takvim şeridi. */

export function KampanyaFrame({ title, lead, back, source, presence, aside, children }: {
  title: string;
  lead: string;
  back?: { to: string; label: string };
  source: string;
  presence: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb: 'Kampanyalar', source, presence, detail: back ? title : undefined }}>
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Dijital ve topluluk · E-ticaret</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[440px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export function StatusPill({ durum, label }: { durum: Durum; label: string }) {
  return <Pill tone={STATUS_TONE[durum]}>{label}</Pill>;
}

const SEV_CLS: Record<Kontrol['seviye'], string> = {
  kirmizi: 'bg-red-50 text-red-700',
  sari: 'bg-amber-50 text-amber-800',
  bilgi: 'bg-slate-100 text-canvas-muted',
};

/** Kontrollerin kısa listesi: kırmızı ve sarı her zaman, bilgi yalnız `all` ile. */
export function Checks({ items, all = false }: { items: Kontrol[]; all?: boolean }) {
  const shown = all ? items : items.filter((k) => k.seviye !== 'bilgi');
  if (!shown.length) return <span className="text-[11.5px] font-semibold text-emerald-700">Sorun yok</span>;
  return (
    <ul className="flex flex-col gap-1">
      {shown.map((k, i) => (
        <li key={`${k.kod}-${i}`} className={`rounded-md px-1.5 py-0.5 text-[11.5px] font-semibold leading-snug ${SEV_CLS[k.seviye]}`}>{k.mesaj}</li>
      ))}
    </ul>
  );
}

/** Marj: bilinmiyorsa «hesaplanamaz» (sıfır yazılmaz). */
export function Margin({ v, pct }: { v: number | null; pct: number | null }) {
  if (v === null || pct === null) return <span className="text-[11.5px] font-semibold text-canvas-muted">hesaplanamaz</span>;
  return <span className={`font-mono tabular-nums ${v < 0 ? 'font-bold text-red-700' : ''}`}>{fmtPct(pct)}</span>;
}

const BAR: Record<string, string> = {
  kampanya: 'bg-canvas-violet text-white',
  platform: 'bg-sky-100 text-sky-900',
  ozel_gun: 'bg-amber-100 text-amber-900',
  fuar: 'bg-emerald-100 text-emerald-900',
};

/** Yaklaşan günlerin takvim şeridi: özel günler, platform dönemleri, fuarlar ve kampanyalar; çakışmalar altta. */
export function CalendarStrip({ cal, onOpen }: { cal: Calendar; onOpen?: (id: string) => void }) {
  const rows: { key: string; label: string; cls: string; at: [number, number]; title: string; id?: string }[] = [];
  for (const k of cal.kampanyalar) {
    const at = span(cal.from, cal.to, k.baslangic, k.bitis);
    if (at) rows.push({ key: k.id, label: k.ad, cls: BAR.kampanya, at, title: `${k.ad} · ${k.durumAdi} · ${fmtDay(k.baslangic)} – ${fmtDay(k.bitis)}`, id: k.id });
  }
  for (const d of cal.items) {
    const at = span(cal.from, cal.to, d.baslangic, d.bitis);
    if (at) rows.push({ key: d.id, label: d.ad, cls: BAR[d.tur] ?? BAR.platform, at, title: `${d.ad} · ${fmtDay(d.baslangic)}${d.bitis !== d.baslangic ? ` – ${fmtDay(d.bitis)}` : ''}${d.neden ? ` · ${d.neden}` : ''}` });
  }
  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-between text-[11px] font-bold text-canvas-muted">
        <span>{fmtDay(cal.from)}</span>
        <span>{fmtDay(cal.to)}</span>
      </div>
      {rows.length === 0 ? (
        <div className="rounded-xl bg-slate-50 px-3 py-3 text-[12px] text-canvas-muted">Bu aralıkta kampanya ya da özel gün yok.</div>
      ) : (
        <ul className="flex flex-col gap-1">
          {rows.map((r) => (
            <li key={r.key} className="relative h-8 rounded-lg bg-slate-50">
              {r.id && onOpen ? (
                <button type="button" title={r.title} onClick={() => onOpen(r.id!)}
                  className={`absolute top-0 flex h-8 min-w-[2.25rem] items-center overflow-hidden rounded-lg px-2 text-left text-[11.5px] font-bold ${r.cls}`}
                  style={{ left: `${r.at[0]}%`, width: `${r.at[1]}%` }}>
                  <span className="truncate">{r.label}</span>
                </button>
              ) : (
                <div title={r.title} className={`absolute top-0 flex h-8 min-w-[2.25rem] items-center overflow-hidden rounded-lg px-2 text-[11.5px] font-bold ${r.cls}`}
                  style={{ left: `${r.at[0]}%`, width: `${r.at[1]}%` }}>
                  <span className="truncate">{r.label}</span>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-2 text-[11px] font-semibold text-canvas-muted">
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-canvas-violet" />Kampanya</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-amber-200" />Özel gün</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-sky-200" />Platform dönemi</span>
        <span className="inline-flex items-center gap-1"><i className="h-2.5 w-2.5 rounded-sm bg-emerald-200" />Fuar</span>
      </div>
      {cal.cakismalar.filter((c) => c.tur === 'kampanya').map((c, i) => (
        <div key={i} className="rounded-xl bg-amber-50 px-3 py-2 text-[12px] font-semibold text-amber-800">{c.mesaj}</div>
      ))}
    </div>
  );
}
