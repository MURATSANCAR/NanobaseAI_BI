import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Clock } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_ENABLED } from '../engine';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { fmtDay, fmtInt, pazarApi, type Category } from './api';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';
import { Explain } from '../components/Explain';

/** M39 Pazar ve rakip ekranlarının ortak parçaları: kabuk, bölüm çubuğu (yetkiye göre), tazelik şeridi. */

export const ROOT = '/pazar-arastirma';

export const SECTIONS = [
  { to: ROOT, label: 'Özet' },
  { to: `${ROOT}/rakipler`, label: 'Rakipler' },
  { to: `${ROOT}/emsal`, label: 'Emsal bul' },
  { to: `${ROOT}/kategori-esleme`, label: 'Kategori eşlemesi' },
  { to: `${ROOT}/raporlar`, label: 'Sektör raporları' },
] as const;

export function useMeta() {
  return useQuery({ queryKey: ['pazar', 'meta'], queryFn: pazarApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export function useCategories() {
  return useQuery({ queryKey: ['pazar', 'categories'], queryFn: pazarApi.categories, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000 });
}

export function PazarFrame({ presence, aside, badges, children }: {
  presence: string;
  aside?: ReactNode;
  badges?: Record<string, number | null | undefined>;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  const here = pathname.replace(/\/+$/, '');
  const pages = usePageAccess();
  const sections = SECTIONS.filter((s) => canOpenRoute(pages, s.to));
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Müşteri ve pazar', crumb: 'Pazar ve rakip', source: 'CRM + Logo + yüklenen raporlar (okuma)', presence }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Müşteri ve pazar · Pazar araştırması ve rekabet</div>
                <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Pazar ve rakip</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">
                  Rakip yayınevlerinin fiyat, sayfa sayısı ve format aralıkları; Timaş'ın kategori, marka ve kanal büyümesi; yüklenen sektör
                  raporlarındaki rakamlar (sayfa numarasıyla) ve yönetime giden aylık özet. Her rakamın kaynağı yanında yazar; kaynağı olmayan pazar rakamı gösterilmez.
                </p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[440px]">{aside}</div>}
            </header>
            {sections.length > 1 && (
              <nav aria-label="Bölüm" className="-mx-1 overflow-x-auto px-1">
                <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                  {sections.map((s) => {
                    const active = s.to === ROOT ? here === ROOT || here.startsWith(`${ROOT}/ozet`) : here.startsWith(s.to);
                    const badge = badges?.[s.to];
                    return (
                      <Link
                        key={s.to}
                        to={s.to}
                        aria-current={active ? 'page' : undefined}
                        className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                          active ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                        }`}
                      >
                        {s.label}
                        {badge ? (
                          <span className={`rounded-md px-1.5 py-0.5 font-mono text-[10.5px] tabular-nums ${active ? 'bg-white/20' : 'bg-amber-50 text-amber-800'}`}>{badge}</span>
                        ) : null}
                      </Link>
                    );
                  })}
                </div>
              </nav>
            )}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Rakip verisinin yaşı: her ekranın üstünde (yönetici eski veriyle karar vermesin). */
export function FreshnessStrip() {
  const q = useQuery({ queryKey: ['pazar', 'freshness'], queryFn: pazarApi.freshness, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const f = q.data;
  if (!f) return null;
  if (!f.records) {
    return (
      <div className="flex items-start gap-2 rounded-2xl bg-slate-50 px-3 py-2 text-[12px] font-semibold text-canvas-ink">
        <Clock aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-canvas-muted" />
        CRM'deki rakip kitap verisi henüz okunmadı. Kaynaklar yenilenince kayıt sayısı ve son güncelleme burada görünür.
      </div>
    );
  }
  return (
    <div className={`flex items-start gap-2 rounded-2xl px-3 py-2 text-[12px] font-semibold leading-snug ${f.stale ? 'bg-amber-50 text-amber-900' : 'bg-slate-50 text-canvas-ink'}`}>
      {f.stale ? <AlertTriangle aria-hidden className="mt-0.5 h-4 w-4 shrink-0" /> : <Clock aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-canvas-muted" />}
      <span>
        Rakip verisi: <strong>{fmtInt(f.records)}</strong> kayıt, son ekleme/değişiklik <strong>{fmtDay(f.lastChange)}</strong>
        <SqlInfo k={kaynakOf(f)} alan="records" label="Rakip verisinin tazeliği" className="ml-0.5" />
        {f.ageDays !== null && <> ({fmtInt(f.ageDays)} gün önce)</>}
        {f.stale && <> — {f.staleDays} günlük eşiği aştı; karşılaştırmalar bu tarihe göredir</>}. İlk kayıt {fmtDay(f.firstCreated)}.
        {f.snapshotAt && <> Portal CRM'i {fmtDay(f.snapshotAt)} tarihinde okudu.</>}
      </span>
    </div>
  );
}

/** Kategori seçici (TİMAŞ kategori listesi; ağaçsa girintili yol). */
export function CategorySelect({ value, onChange, categories, empty = 'Bütün kategoriler', id, className = '' }: {
  value: string;
  onChange: (v: string) => void;
  categories: Category[];
  empty?: string;
  id?: string;
  className?: string;
}) {
  return (
    <select id={id} value={value} onChange={(e) => onChange(e.target.value)} className={className}>
      <option value="">{empty}</option>
      {categories.map((c) => (
        <option key={c.id} value={c.id}>
          {c.yol}
        </option>
      ))}
    </select>
  );
}

/** Küçük sayı karosu. */
export function Stat({ label, value, help, info, explain }: { label: string; value: ReactNode; help?: ReactNode; info?: ReactNode; explain?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">
        <span className="min-w-0 truncate">{label}</span>
        {explain && <Explain label={label}>{explain}</Explain>}
        {info}
      </div>
      <div className="mt-0.5 truncate font-mono text-[16px] font-bold tabular-nums">{value}</div>
      {help && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}
