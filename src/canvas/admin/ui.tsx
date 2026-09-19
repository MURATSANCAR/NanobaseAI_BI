import type { ReactNode } from 'react';
import { EngineAuthError } from '../engine';

export const nf = new Intl.NumberFormat('tr-TR');
const dtf = new Intl.DateTimeFormat('tr-TR', {
  timeZone: 'Europe/Istanbul',
  day: '2-digit',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});
export const fmtDate = (iso: string | null | undefined) => (iso ? dtf.format(new Date(iso)) : '—');

/** systemd zaman damgası ("Tue 2026-09-15 08:25:29 +03") → okunur; boş/"n/a" ise tire. */
export const fmtUnitTime = (v: string | null | undefined) => {
  if (!v || v === 'n/a') return '—';
  const m = v.match(/(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2})/);
  if (!m) return v;
  const d = new Date(`${m[1]}T${m[2]}:00+03:00`);
  return Number.isNaN(d.getTime()) ? v : dtf.format(d);
};

export const errText = (e: unknown, fallback: string) =>
  e instanceof EngineAuthError ? 'Oturum gerekli.' : e ? (e as Error).message || fallback : null;

export const btn =
  'inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl px-3.5 py-2 text-[12.5px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-50 disabled:active:scale-100 sm:min-h-0';
export const btnGhost = `${btn} bg-slate-100 text-canvas-ink hover:bg-slate-200`;
export const btnPrimary = `${btn} bg-canvas-violet text-white shadow-md`;
export const field =
  'w-full rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-base font-semibold outline-none focus:border-canvas-violet sm:text-[12.5px]';
export const label = 'text-[11px] font-bold uppercase tracking-wide text-canvas-muted';

export function Section({ title, help, action, children }: { title: string; help?: string; action?: ReactNode; children?: ReactNode }) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-xl font-extrabold tracking-tight">{title}</h2>
          {help && <p className="mt-0.5 text-[12.5px] text-canvas-muted">{help}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-2xl border border-slate-100 bg-white/80 p-4 ${className}`}>{children}</div>;
}

export function Note({ tone, children }: { tone: 'ok' | 'warn' | 'err' | 'info'; children: ReactNode }) {
  const cls = {
    ok: 'bg-emerald-50 text-emerald-700',
    warn: 'bg-amber-50 text-amber-800',
    err: 'bg-red-50 text-red-700',
    info: 'bg-slate-50 text-canvas-ink',
  }[tone];
  return <div className={`rounded-xl px-3 py-2 text-[12px] font-semibold leading-snug ${cls}`}>{children}</div>;
}

export function Pill({ tone, children }: { tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet'; children: ReactNode }) {
  const cls = {
    ok: 'bg-emerald-50 text-emerald-700',
    warn: 'bg-amber-50 text-amber-800',
    err: 'bg-red-50 text-red-700',
    muted: 'bg-slate-100 text-canvas-ink',
    violet: 'bg-canvas-violet/10 text-canvas-violet',
  }[tone];
  return <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${cls}`}>{children}</span>;
}

export function Loading() {
  return <div className="py-10 text-center text-[12px] text-canvas-muted">Yükleniyor…</div>;
}

/** Tablo sarmalayıcı: telefonda kendi içinde yatay kayar, sayfa kaymaz. */
export function TableWrap({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-2xl border border-slate-100 bg-white/80">
      <table className="w-full min-w-[640px] text-[12px]">{children}</table>
    </div>
  );
}

export const th = 'whitespace-nowrap px-3 py-2 text-left text-[11px] font-bold uppercase tracking-wide text-canvas-muted';
export const td = 'px-3 py-2 align-top';

export const ACTION_LABEL: Record<string, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  create: { label: 'Oluşturdu', tone: 'ok' },
  update: { label: 'Güncelledi', tone: 'violet' },
  delete: { label: 'Sildi', tone: 'err' },
  run: { label: 'Çalıştırdı', tone: 'muted' },
  test: { label: 'Denedi', tone: 'muted' },
  approve: { label: 'Onayladı', tone: 'ok' },
  reject: { label: 'Reddetti', tone: 'err' },
  correct: { label: 'Düzeltti', tone: 'warn' },
};

export const FIELD_LABEL: Record<string, string> = {
  title: 'Başlık',
  note: 'Not',
  question: 'Soru',
  chart: 'Grafik',
  refresh: 'Tazeleme',
  refreshAt: 'Tazeleme saati',
  when: 'Plan',
  recipients: 'Alıcılar',
  fmt: 'Biçim',
  status: 'Durum',
  condition: 'Koşul',
  threshold: 'Eşik',
  text: 'Metin',
  column: 'Kolon',
  owner: 'Sahibi',
  rows: 'Satır',
  error: 'Hata',
  to: 'Alıcı',
  ok: 'Başarılı',
  message: 'Sonuç',
  secret: 'Gizli değer',
};

export const show = (v: unknown): string => {
  if (v === null || v === undefined || v === '') return '—';
  if (Array.isArray(v)) return v.length ? v.join(', ') : '—';
  if (typeof v === 'boolean') return v ? 'evet' : 'hayır';
  if (typeof v === 'number') return nf.format(v);
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
};
