import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import Shell, { ZoomStage } from '../stitch/Shell';
import { Pill } from '../admin/ui';
import { ENGINE_ENABLED } from '../engine';
import { BAND_LABEL, inflApi, type Meta, type Relation } from './api';

/** İşbirlikleri ekranlarının ortak kabuğu. Sekme çubuğu ve onay penceresi bütçe ekranınınkiyle aynıdır. */
export { Tabs, AskSheet } from '../budget/parts';

const SECTIONS = [
  { to: '/isbirlikleri', label: 'Pano', exact: true },
  { to: '/isbirlikleri/kisiler', label: 'İçerik üreticileri', also: '/isbirlikleri/kisi' },
  { to: '/isbirlikleri/aday', label: 'Kitaba aday' },
  { to: '/isbirlikleri/rapor', label: 'Rapor' },
  { to: '/isbirlikleri/odemeler', label: 'Ödemeler', fee: true },
] as const;

export function useMeta() {
  return useQuery({ queryKey: ['influencers', 'meta'], queryFn: inflApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export function InflFrame({ title, lead, detail, aside, children }: {
  title: string;
  lead: string;
  detail?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const { pathname } = useLocation();
  const meta = useMeta();
  const path = pathname.replace(/^\/(timas|bi)/, '');
  const active = (s: (typeof SECTIONS)[number]) =>
    'exact' in s ? path === s.to || path === `${s.to}/` : path.startsWith(s.to) || ('also' in s && path.startsWith(s.also));
  const sections = SECTIONS.filter((s) => !('fee' in s) || meta.data?.me.canSeeFee);
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Pazarlama', crumb: 'İşbirlikleri', source: 'Kaynak: portal kaydı · CRM', presence: 'İşbirlikleri', detail }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Pazarlama · İletişim</div>
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-auto">{aside}</div>}
            </header>
            <nav aria-label="İşbirlikleri bölümleri" className="-mx-1 overflow-x-auto px-1">
              <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                {sections.map((s) => (
                  <Link
                    key={s.to}
                    to={s.to}
                    aria-current={active(s) ? 'page' : undefined}
                    className={`inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                      active(s) ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                    }`}
                  >
                    {s.label}
                  </Link>
                ))}
              </div>
            </nav>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** İlişki puanı (0–100) ve bandı. */
export function RelationBadge({ rel }: { rel: Relation }) {
  const tone = rel.band === 'sicak' ? 'bg-emerald-500' : rel.band === 'ilik' ? 'bg-amber-400' : rel.band === 'soguk' ? 'bg-sky-400' : 'bg-slate-300';
  return (
    <span className="inline-flex items-center gap-2" title={`İlişki puanı: yakınlık ${rel.parts.yakinlik} + sıklık ${rel.parts.siklik} + sonuç ${rel.parts.sonuc}`}>
      <span className="relative h-1.5 w-10 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <span className={`absolute inset-y-0 left-0 rounded-full ${tone}`} style={{ width: `${rel.score}%` }} />
      </span>
      <span className="font-mono text-[11.5px] font-bold tabular-nums">{rel.score}</span>
      <span className="text-[11px] text-canvas-muted">{BAND_LABEL[rel.band]}</span>
    </span>
  );
}

/** 0–100 aday puanı. */
export function ScoreBar({ value }: { value: number }) {
  const tone = value >= 70 ? 'bg-emerald-500' : value >= 45 ? 'bg-amber-400' : 'bg-slate-400';
  return (
    <span className="inline-flex min-w-[92px] items-center gap-2" title="Kural puanı (100 üzerinden)">
      <span className="relative h-1.5 w-12 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <span className={`absolute inset-y-0 left-0 rounded-full ${tone}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </span>
      <span className="font-mono text-[12.5px] font-bold tabular-nums">{Math.round(value)}</span>
    </span>
  );
}

export function TopicPills({ keys, meta }: { keys: string[]; meta?: Meta }) {
  if (!keys.length) return <span className="text-[11.5px] text-canvas-muted">konu yok</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {keys.map((k) => <Pill key={k} tone="muted">{meta?.konular[k] ?? k}</Pill>)}
    </span>
  );
}

/** Kısa etiketli değer (özet kutuları). */
export function Fact({ label, value, help, info }: { label: string; value: ReactNode; help?: ReactNode; info?: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="flex items-center gap-1 text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}{info}</div>
      <div className="mt-0.5 break-words text-[13.5px] font-bold">{value}</div>
      {help && <div className="mt-0.5 text-[11px] leading-snug text-canvas-muted">{help}</div>}
    </div>
  );
}

/** Seçenek listesinden çoklu seçim (dokunulabilir düğmeler). */
export function MultiPick({ options, value, onChange }: { options: Record<string, string>; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {Object.entries(options).map(([k, v]) => {
        const on = value.includes(k);
        return (
          <button
            key={k}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== k) : [...value, k])}
            className={`min-h-10 rounded-xl px-3 text-[12px] font-bold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-8 ${
              on ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
            }`}
          >
            {v}
          </button>
        );
      })}
    </div>
  );
}
