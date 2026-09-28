import { type ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { ChevronLeft, Download, Loader2, RefreshCw } from 'lucide-react';
import Shell, { ZoomStage } from '../stitch/Shell';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import { Note, btnGhost } from '../admin/ui';
import { fmtDay } from '../budget/api';

/** M40 Trendyol ve M41 Amazon ekranlarının ortak parçaları: istek, kabuk, bölüm bağlantıları, veri şeridi. */

export type PageOf<T> = { items: T[]; total: number; page: number; pageSize: number };

async function fail(res: Response): Promise<never> {
  if (res.status === 401) throw new EngineAuthError();
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

/** `/api/v1/channels/<platform>` altındaki uçlara istek. Dosya gövdesi (yükleme) ham gider. */
export function platformClient(base: string) {
  async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 180_000): Promise<T> {
    if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
    const raw = body instanceof Blob;
    const res = await fetch(`${ENGINE_BASE}${base}${path}`, {
      method,
      credentials: 'include',
      headers: {
        ...(method === 'GET' ? freshHeaders() : {}),
        ...(body === undefined ? {} : { 'Content-Type': raw ? 'application/octet-stream' : 'application/json' }),
      },
      body: body === undefined ? undefined : raw ? (body as Blob) : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) return fail(res);
    return (await res.json()) as T;
  }
  const url = (path: string) => `${ENGINE_BASE}${base}${path}`;
  return { send, url };
}

export const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export type Section = { to: string; label: string; page: string; end?: boolean };

export function PlatformFrame({ area, crumb, source, title, lead, sections, pages, aside, back, children }: {
  area: string;
  crumb: string;
  source: string;
  title: string;
  lead: string;
  sections: ReadonlyArray<Section>;
  pages?: Record<string, boolean>;
  aside?: ReactNode;
  back?: { to: string; label: string };
  children: ReactNode;
}) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Platform', crumb, source, presence: crumb, detail: title }}>
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
                  <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Platform · {area}</div>
                )}
                <h1 className="mt-0.5 break-words text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">{title}</h1>
                <p className="mt-1 max-w-[76ch] text-[12.5px] leading-snug text-canvas-muted">{lead}</p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[460px]">{aside}</div>}
            </header>
            <nav aria-label={`${area} bölümleri`} className="-mx-1 overflow-x-auto px-1">
              <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1">
                {sections.filter((s) => !pages || pages[s.page] !== false).map((s) => (
                  <NavLink
                    key={s.to}
                    to={s.to}
                    end={s.end}
                    className={({ isActive }) =>
                      `inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
                        isActive ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
                      }`
                    }
                  >
                    {s.label}
                  </NavLink>
                ))}
              </div>
            </nav>
            {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

/** Kaynak şeridi: son okuma, okuma durumu, hata ve yenile düğmesi. */
export function SourceBar({ text, at, running, step, error, onRefresh, busy }: {
  text: ReactNode;
  at?: string | null;
  running?: boolean;
  step?: string | null;
  error?: string | null;
  onRefresh?: () => void;
  busy?: boolean;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-white/70 px-3 py-2 text-[12px] font-semibold text-canvas-muted">
      <span className="min-w-0">
        {text}
        {at && <> · Son okuma {fmtDay(at)}</>}
        {running && <> · Okunuyor: {step ?? '…'}</>}
        {error && !running && <span className="text-red-700"> · Son okuma: {error}</span>}
      </span>
      {onRefresh && (
        <button type="button" className={btnGhost} onClick={onRefresh} disabled={!!running || busy}>
          {running || busy ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
          Veriyi yenile
        </button>
      )}
    </div>
  );
}

export function ExportLink({ href, show }: { href: string; show: boolean }) {
  if (!show) return null;
  return (
    <a className={btnGhost} href={href}>
      <Download aria-hidden className="h-4 w-4" />
      Excel
    </a>
  );
}

/** Seçilebilir süzgeç düğmeleri (sayılarıyla). */
export function Chips<T extends string>({ items, value, onChange }: {
  items: ReadonlyArray<{ key: T; label: string; count?: number | null }>;
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((i) => (
        <button
          key={i.key || 'hepsi'}
          type="button"
          aria-pressed={value === i.key}
          onClick={() => onChange(i.key)}
          className={`inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2.5 text-[12px] font-bold transition-colors duration-150 sm:min-h-9 ${
            value === i.key ? 'bg-canvas-violet text-white' : 'bg-slate-100 text-canvas-ink hover:bg-slate-200'
          }`}
        >
          {i.label}
          {i.count !== undefined && i.count !== null && <span className="font-mono tabular-nums opacity-80">{i.count.toLocaleString('tr-TR')}</span>}
        </button>
      ))}
    </div>
  );
}

/** Metin + kitap kodu hücresi. */
export function BookCell({ name, code, sub }: { name?: string | null; code?: string | null; sub?: string | null }) {
  return (
    <>
      <div className="font-semibold">{name || code || '—'}</div>
      <div className="font-mono text-[11px] text-canvas-muted">{[code, sub].filter(Boolean).join(' · ') || '—'}</div>
    </>
  );
}

export const yesNo = (v: boolean | null | undefined) => (v === true ? 'Evet' : v === false ? 'Hayır' : 'Bilinmiyor');
