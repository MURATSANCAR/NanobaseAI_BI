import { useMemo, useState, type ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Pill, field } from '../../admin/ui';
import { hrApi, type Employee } from '../hrApi';
import { HrFrame } from '../parts';
import { learningApi, STATUS_TONE, type Status } from './learningApi';

/** Eğitim ve gelişim ekranlarının ortak parçaları: çerçeve + alt gezinme, kişi seçici, rehber metni. */

export function useLearningInfo() {
  return useQuery({ queryKey: ['hr', 'learning', 'info'], queryFn: learningApi.info, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

const TABS: { to: string; label: string; need?: 'usage' | 'guides' }[] = [
  { to: '/ik/egitim', label: 'Pano' },
  { to: '/ik/egitim/katalog', label: 'Katalog ve oturumlar' },
  { to: '/ik/egitim/ihtiyaclar', label: 'İhtiyaçlar' },
  { to: '/ik/egitim/kullanim', label: 'Kullanım haritası', need: 'usage' },
  { to: '/ik/egitim/rehberler', label: 'Rehberler' },
];

export function LearningFrame({ crumb, title, lead, aside, detail, back, children }: {
  crumb: string;
  title: string;
  lead: string;
  aside?: ReactNode;
  detail?: string;
  back?: { to: string; label: string };
  children: ReactNode;
}) {
  const info = useLearningInfo();
  const can = info.data?.can;
  return (
    <HrFrame crumb={crumb} title={title} lead={lead} aside={aside} detail={detail} back={back}>
      {!back && (
        <nav aria-label="Eğitim bölümleri" className="-mx-1 overflow-x-auto px-1">
          <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
            {TABS.filter((t) => !t.need || can?.[t.need]).map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end
                className={({ isActive }) =>
                  `inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                    isActive ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                  }`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </div>
        </nav>
      )}
      {children}
    </HrFrame>
  );
}

export function StatusPill({ status, label }: { status: Status; label: string }) {
  return <Pill tone={STATUS_TONE[status]}>{label}</Pill>;
}

/** Çalışan seçici: arama + işaret kutuları. Yalnız etkin çalışanlar; sayı tavanı yok (liste kendi içinde kayar). */
export function EmployeePicker({ value, onChange, exclude }: { value: string[]; onChange: (ids: string[]) => void; exclude?: Set<string> }) {
  const [q, setQ] = useState('');
  const emps = useQuery({ queryKey: ['hr', 'employees', 'aktif'], queryFn: () => hrApi.employees({ status: 'aktif' }), enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const list = useMemo(() => {
    const needle = q.trim().toLocaleLowerCase('tr');
    return (emps.data?.items ?? []).filter(
      (e: Employee) => !exclude?.has(e.id) && (!needle || `${e.displayName} ${e.unitName ?? ''} ${e.title}`.toLocaleLowerCase('tr').includes(needle)),
    );
  }, [emps.data, q, exclude]);
  const picked = new Set(value);
  const toggle = (id: string) => onChange(picked.has(id) ? value.filter((x) => x !== id) : [...value, id]);
  return (
    <div className="flex flex-col gap-2">
      <input className={field} placeholder="Ad, birim ya da unvan ara" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Çalışan ara" />
      <div className="flex items-center justify-between text-[11.5px] text-canvas-muted">
        <span>{value.length} kişi seçili · {list.length} sonuç</span>
        {list.length > 0 && (
          <button type="button" className="font-bold text-canvas-violet hover:underline" onClick={() => onChange([...new Set([...value, ...list.map((e) => e.id)])])}>
            Görünenleri seç
          </button>
        )}
      </div>
      <ul className="max-h-[320px] overflow-y-auto rounded-xl border border-slate-100 bg-white">
        {emps.isLoading && <li className="px-3 py-3 text-[12px] text-canvas-muted">Yükleniyor…</li>}
        {list.map((e) => (
          <li key={e.id}>
            <label className="flex min-h-11 cursor-pointer items-center gap-2.5 border-b border-slate-50 px-3 py-1.5 text-[12.5px] last:border-0 hover:bg-slate-50">
              <input type="checkbox" className="h-4 w-4 accent-canvas-violet" checked={picked.has(e.id)} onChange={() => toggle(e.id)} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-bold">{e.displayName}</span>
                <span className="block truncate text-[11px] text-canvas-muted">{[e.unitName, e.title].filter(Boolean).join(' · ') || '—'}</span>
              </span>
            </label>
          </li>
        ))}
        {emps.data && list.length === 0 && <li className="px-3 py-3 text-[12px] text-canvas-muted">Eşleşen çalışan yok.</li>}
      </ul>
    </div>
  );
}

export { GuideText, parseGuide, fmtDay, fmtWhen } from './guideText';
