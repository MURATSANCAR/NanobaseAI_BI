import type { ReactNode } from 'react';
import { AlertTriangle, BadgeCheck, CircleDashed, Loader2, Sparkles } from 'lucide-react';
import { Progress, ago, ghostBtn, gradientBtn } from '../shared';
import type { MkTask, Signed } from './api';

/** Pazarlama kitinin ortak parçaları. Yeni hareket yok: basışta stüdyonun `press` küçülmesi ve ilerleme çubuğu
 *  (shared.tsx) kullanılır; sekme değişimi anlıktır (sık kullanılır). */

export const field =
  'w-full min-w-0 rounded-xl border border-slate-200 bg-white/90 px-3 py-2 text-[13px] text-canvas-ink outline-none focus:border-canvas-violet';
export const label = 'text-[11px] font-bold uppercase tracking-wide text-canvas-muted';
export { ghostBtn, gradientBtn };

/** Onay rozeti: kim, ne zaman. */
export function Approval({ approved, what = 'Onaylı' }: { approved: Signed | null | undefined; what?: string }) {
  if (!approved) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-[11.5px] font-bold text-amber-700">
        <CircleDashed className="h-3.5 w-3.5" aria-hidden />Onay bekliyor
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-1 text-[11.5px] font-bold text-emerald-700"
      title={`${approved.by} · ${ago(approved.at)}`}>
      <BadgeCheck className="h-3.5 w-3.5" aria-hidden />{what} · {approved.by}
    </span>
  );
}

/** Üretim düğmesi + arka plan işinin durumu (ilerleme, hata). */
export function Generate({ task, has, onRun, pending, what }: {
  task: MkTask | undefined; has: boolean; onRun: () => void; pending: boolean; what: string;
}) {
  const running = task?.status === 'running' || pending;
  const [n, t] = task?.progress ?? [0, 0];
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={has ? ghostBtn : gradientBtn} disabled={running} onClick={onRun}>
          {running ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden /> : <Sparkles className="h-4 w-4" aria-hidden />}
          {running ? 'Zeki AI yazıyor…' : has ? 'Yeniden üret' : `${what} üret`}
        </button>
        {running && task?.step && <span className="text-[12px] text-canvas-muted">{task.step}{t ? ` · ${n}/${t}` : ''}</span>}
      </div>
      {running && t > 0 && <Progress value={n} total={t} />}
      {task?.status === 'failed' && task.error && (
        <p className="flex items-start gap-1.5 text-[12px] text-rose-700"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />{task.error}</p>
      )}
    </div>
  );
}

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-[14px] font-extrabold text-canvas-ink">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Satır satır liste düzenleyici (her satır bir madde). */
export function Lines({ value, onChange, rows = 4, placeholder, ariaLabel }: {
  value: string[]; onChange: (v: string[]) => void; rows?: number; placeholder?: string; ariaLabel: string;
}) {
  return (
    <textarea className={field} rows={Math.max(rows, value.length + 1)} aria-label={ariaLabel} placeholder={placeholder}
      value={value.join('\n')} onChange={(e) => onChange(e.target.value.split('\n'))} />
  );
}

export const tidy = (v: string[]) => v.map((x) => x.trim()).filter(Boolean);

/** Panoya kopyala; http'de (müşteri VM'i) Clipboard API kapalıdır, gizli metin alanıyla eski yol denenir. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* eski yola düş */
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.position = 'fixed';
  ta.style.top = '-1000px';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}
