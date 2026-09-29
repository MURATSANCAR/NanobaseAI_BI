import { useState, type ReactNode } from 'react';
import Shell, { ZoomStage } from '../stitch/Shell';
import Sheet from '../editorial/studio/reader/Sheet';
import { btnGhost, btnPrimary, field, label as labelCls } from '../admin/ui';
import { TRACK, fmtPct, type TrackState } from './api';

/** Bütçe ekranının ortak parçaları: kabuk, sekme çubuğu, oran çubuğu, onay/gerekçe penceresi, sayı alanı. */

export function BudgetFrame({ source, presence, aside, children }: { source: string; presence: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <Shell head={{ tenant: 'Timaş Yayınları', section: 'Finans ve risk', crumb: 'Bütçe ve hedefler', source, presence }}>
      <main className="absolute bottom-2 left-2 right-2 top-16 overflow-y-auto overscroll-contain sm:bottom-6 sm:left-6 sm:right-6 sm:top-[84px]">
        <ZoomStage>
          <div className="mx-auto flex w-full max-w-[1760px] flex-col gap-3 pb-6 lg:gap-4">
            <header className="relative z-20 flex flex-col gap-3 px-1 lg:flex-row lg:items-start lg:justify-between lg:gap-6">
              <div className="min-w-0">
                <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-violet">Finans ve risk · Bütçe planlama ve kontrolü</div>
                <h1 className="mt-0.5 text-[22px] font-extrabold leading-tight tracking-tight sm:text-[28px]">Bütçe ve satış hedefleri</h1>
                <p className="mt-1 max-w-[72ch] text-[12.5px] leading-snug text-canvas-muted">
                  Kitap bazlı satış hedeflerini, yeni kitap programını ve departman bütçesini planlar. Onaylanan plan Logo gerçekleşmesiyle izlenir;
                  hedefin gerisinde kalan kitap ve bütçesini aşan gider kalemi için uyarı açılır.
                </p>
              </div>
              {aside && <div className="w-full shrink-0 lg:w-[480px]">{aside}</div>}
            </header>
            {children}
          </div>
        </ZoomStage>
      </main>
    </Shell>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: ReadonlyArray<{ key: T; label: string; badge?: number | null }>; value: T; onChange: (t: T) => void }) {
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <div className="flex w-max min-w-full gap-1 rounded-2xl bg-slate-100 p-1" role="tablist" aria-label="Bölüm">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={value === t.key}
            onClick={() => onChange(t.key)}
            className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 ${
              value === t.key ? 'bg-canvas-violet text-white shadow-md' : 'text-canvas-ink hover:bg-white/70'
            }`}
          >
            {t.label}
            {t.badge ? (
              <span className={`rounded-md px-1.5 py-0.5 font-mono text-[10.5px] tabular-nums ${value === t.key ? 'bg-white/20' : 'bg-red-50 text-red-700'}`}>{t.badge}</span>
            ) : null}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Gerçekleşme ÷ beklenen. Çubuk 150%'de doyar; eşik çizgisi işaretli. */
export function RatioBar({ ratio, state, threshold = 0.8 }: { ratio: number | null; state: TrackState; threshold?: number }) {
  const w = ratio === null ? 0 : Math.max(0, Math.min(1.5, ratio)) / 1.5;
  return (
    <div className="flex min-w-[120px] items-center gap-2">
      <div className="relative h-2 flex-1 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <div className={`absolute inset-y-0 left-0 rounded-full ${TRACK[state].bar}`} style={{ width: `${w * 100}%` }} />
        <div className="absolute inset-y-0 w-px bg-slate-400" style={{ left: `${(threshold / 1.5) * 100}%` }} />
        <div className="absolute inset-y-0 w-px bg-slate-600" style={{ left: `${(1 / 1.5) * 100}%` }} />
      </div>
      <span className="w-12 text-right font-mono text-[11.5px] font-bold tabular-nums">{fmtPct(ratio, 0)}</span>
    </div>
  );
}

export function StatePill({ state }: { state: TrackState }) {
  const s = TRACK[state];
  return <span className={`inline-flex shrink-0 items-center rounded-md px-1.5 py-0.5 text-[11px] font-bold ${s.pill}`}>{s.label}</span>;
}

/** Sayı alanı: Türkçe yazımı kabul eder (1.250,5). */
export function NumField({ id, label, value, onChange, suffix, help, info }: {
  id: string; label: string; value: string; onChange: (v: string) => void; suffix?: string; help?: string;
  /** Kutudaki önerilen değerin sorgu bilgisi (`<SqlInfo …/>`); etiketin yanında. */
  info?: ReactNode;
}) {
  return (
    <label htmlFor={id} className="flex flex-col gap-1">
      {info ? (
        <span className="flex items-center gap-1"><span className={labelCls}>{label}</span>{info}</span>
      ) : (
        <span className={labelCls}>{label}</span>
      )}
      <span className="relative flex items-center">
        <input id={id} inputMode="decimal" autoComplete="off" className={`${field} font-mono tabular-nums ${suffix ? 'pr-9' : ''}`} value={value} onChange={(e) => onChange(e.target.value)} />
        {suffix && <span className="pointer-events-none absolute right-3 text-[12px] font-bold text-canvas-muted">{suffix}</span>}
      </span>
      {help && <span className="text-[11px] leading-snug text-canvas-muted">{help}</span>}
    </label>
  );
}

/** Onay / gerekçe penceresi. `required` ise metin boşken düğme kapalı. */
export function AskSheet({ open, title, message, confirm, danger, input, required, busy, onClose, onConfirm }: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirm: string;
  danger?: boolean;
  input?: string;
  required?: boolean;
  busy?: boolean;
  onClose: () => void;
  onConfirm: (text: string) => void;
}) {
  const [text, setText] = useState('');
  return (
    <Sheet open={open} modal onClose={() => { setText(''); onClose(); }} title={title}>
      <div className="flex flex-col gap-3 text-[13px] leading-snug">
        <div>{message}</div>
        {input && (
          <label className="flex flex-col gap-1">
            <span className={labelCls}>{input}</span>
            <textarea className={`${field} min-h-[96px]`} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
        )}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={btnGhost} onClick={() => { setText(''); onClose(); }}>Vazgeç</button>
          <button
            type="button"
            className={danger ? `${btnPrimary} !bg-red-600` : btnPrimary}
            disabled={busy || (required && !text.trim())}
            onClick={() => { onConfirm(text.trim()); setText(''); }}
          >
            {confirm}
          </button>
        </div>
      </div>
    </Sheet>
  );
}
