import { useState, type ReactNode } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CalendarX2, History, X } from 'lucide-react';
import { assignApi, type AssignConflict, type EditorLoadInfo, type EditorTask, type TaskStatus } from '../../engine';
import { Note, Pill, btnGhost, btnPrimary, errText, field, label, nf } from '../../admin/ui';
import { assignKeys, taskHistoryOptions } from '../queries';
import './assign.css';

/** M2 editör atama ekranlarının ortak parçaları: yan pencere, yük göstergesi, çakışma listesi, görev düzenleme. */

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const shortFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', timeZone: 'UTC' });

/** "2026-09-27" → "27 Eyl 2026". Tarih yalnız gün; saat dilimi kaydırmasın diye UTC okunur. */
export const day = (iso: string | null | undefined) => (iso ? dayFmt.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`)) : '—');
export const shortDay = (iso: string | null | undefined) => (iso ? shortFmt.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`)) : '—');

export function todayIso(): string {
  const d = new Date();
  return new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())).toISOString().slice(0, 10);
}

export function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

export const daysBetween = (a: string, b: string) => Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / 86_400_000);

export const STATUS_ORDER: TaskStatus[] = ['sirada', 'calisiyor', 'beklemede', 'tamamlandi'];
export const STATUS_LABEL: Record<TaskStatus, string> = {
  sirada: 'Sırada',
  calisiyor: 'Çalışılıyor',
  beklemede: 'Beklemede',
  tamamlandi: 'Tamamlandı',
  iptal: 'İptal',
};
const STATUS_TONE: Record<TaskStatus, 'muted' | 'violet' | 'warn' | 'ok' | 'err'> = {
  sirada: 'muted',
  calisiyor: 'violet',
  beklemede: 'warn',
  tamamlandi: 'ok',
  iptal: 'err',
};

export function StatusPill({ status }: { status: TaskStatus }) {
  return <Pill tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Pill>;
}

/** Yan pencere: masaüstünde sağdan, telefonda alttan. Odak, Esc ve dış tıklama base-ui'da. */
export function Sheet({
  open,
  onOpenChange,
  title,
  sub,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  sub?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="as-scrim" />
        <Dialog.Popup className="as-sheet font-canvas text-canvas-ink">
          <div className="flex items-start justify-between gap-3 px-4 pb-2 pt-4 sm:px-5 sm:pt-5">
            <div className="min-w-0">
              <Dialog.Title className="break-words text-[18px] font-extrabold leading-snug tracking-tight">{title}</Dialog.Title>
              {sub && <Dialog.Description className="mt-1 text-[12px] leading-snug text-canvas-muted">{sub}</Dialog.Description>}
            </div>
            <Dialog.Close
              aria-label="Kapat"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-100 transition-transform duration-150 ease-out active:scale-[0.95] sm:h-10 sm:w-10"
            >
              <X aria-hidden className="h-4 w-4" />
            </Dialog.Close>
          </div>
          <div className="as-sheet-body">{children}</div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/** İş yükü: açık görev / kapasite. Kapasite yazılmamışsa yüzde yok, yalnız sayı. */
export function LoadMeter({ load, compact }: { load: EditorLoadInfo; compact?: boolean }) {
  const pct = load.pct;
  const tone = pct == null ? 'bg-slate-300' : pct > 100 ? 'bg-red-500' : pct >= 85 ? 'bg-amber-400' : 'bg-canvas-mint';
  return (
    <div className="min-w-0">
      <div className="flex items-baseline justify-between gap-2 text-[11.5px]">
        <span className="font-semibold text-canvas-muted">
          {load.capacity ? `${nf.format(load.open)} / ${nf.format(load.capacity)} görev` : `${nf.format(load.open)} açık görev`}
        </span>
        <span className={`font-mono font-bold tabular-nums ${pct != null && pct > 100 ? 'text-red-600' : ''}`}>
          {pct != null ? `%${nf.format(pct)}` : 'kapasite yok'}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden>
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct == null ? 0 : Math.min(100, pct)}%` }} />
      </div>
      {!compact && (load.overdue > 0 || load.undated > 0 || load.pages > 0) && (
        <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-canvas-muted">
          {load.overdue > 0 && <span className="font-bold text-red-600">{nf.format(load.overdue)} gecikmiş</span>}
          {load.undated > 0 && <span>{nf.format(load.undated)} terminsiz</span>}
          {load.pages > 0 && <span>{nf.format(load.pages)} sayfa</span>}
        </div>
      )}
    </div>
  );
}

export function ConflictList({ items }: { items: AssignConflict[] }) {
  if (!items.length) return null;
  return (
    <ul className="mt-1.5 space-y-1">
      {items.map((c, i) => (
        <li key={i} className="flex items-start gap-1.5 text-[11.5px] font-semibold leading-snug text-amber-800">
          {c.kind === 'izin' ? <CalendarX2 aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" /> : <AlertTriangle aria-hidden className="mt-px h-3.5 w-3.5 shrink-0" />}
          <span>{c.text}</span>
        </li>
      ))}
    </ul>
  );
}

const ACTION_TEXT: Record<string, string> = { atandi: 'Atandı', 'panoya-alindi': 'Panoya alındı', guncellendi: 'Güncellendi' };
const FIELD_TEXT: Record<string, string> = { status: 'Durum', start: 'Başlangıç', due: 'Termin', pages: 'Sayfa', note: 'Not' };

function changeText(k: string, v: unknown): string | null {
  if (k === 'reason' || v == null) return null;
  if (k === 'note') return 'Not değişti';
  if (!Array.isArray(v)) return null;
  const [a, b] = v as [unknown, unknown];
  const f = (x: unknown) => (x == null ? '—' : k === 'status' ? STATUS_LABEL[x as TaskStatus] ?? String(x) : k === 'start' || k === 'due' ? day(String(x)) : String(x));
  return `${FIELD_TEXT[k] ?? k}: ${f(a)} → ${f(b)}`;
}

function TaskHistory({ id }: { id: string }) {
  const q = useQuery(taskHistoryOptions(id));
  if (q.isLoading) return <p className="text-[12px] text-canvas-muted">Geçmiş okunuyor…</p>;
  const items = q.data?.items ?? [];
  if (!items.length) return <p className="text-[12px] text-canvas-muted">Kayıt yok.</p>;
  return (
    <ol className="space-y-2">
      {items.map((h, i) => {
        const d = h.detail ?? {};
        const lines = h.action === 'guncellendi' ? Object.entries(d).map(([k, v]) => changeText(k, v)).filter(Boolean) : [];
        return (
          <li key={i} className="rounded-xl bg-slate-50 px-3 py-2 text-[12px]">
            <div className="flex flex-wrap justify-between gap-x-2">
              <span className="font-extrabold">{ACTION_TEXT[h.action] ?? h.action}</span>
              <span className="text-canvas-muted">
                {h.actor} · {new Date(h.at).toLocaleString('tr-TR', { dateStyle: 'medium', timeStyle: 'short' })}
              </span>
            </div>
            {h.action === 'atandi' && (
              <div className="mt-0.5 text-canvas-muted">
                {String(d.editor ?? '')} · termin {day(String(d.due ?? ''))}
                {d.force ? ' · çakışmaya rağmen' : ''}
              </div>
            )}
            {lines.map((l) => (
              <div key={l} className="mt-0.5 text-canvas-muted">
                {l}
              </div>
            ))}
            {typeof d.reason === 'string' && d.reason && <div className="mt-0.5">Gerekçe: {d.reason}</div>}
          </li>
        );
      })}
    </ol>
  );
}

/** Görevin durumu, tarihleri, sayfası ve notu. Termin değişirse gerekçe istenir; geçmiş altta. */
export function TaskEditor({ task, onDone }: { task: EditorTask; onDone?: (t: EditorTask) => void }) {
  const qc = useQueryClient();
  const [status, setStatus] = useState<TaskStatus>(task.status);
  const [start, setStart] = useState(task.start ?? '');
  const [due, setDue] = useState(task.due ?? '');
  const [pages, setPages] = useState(task.pages != null ? String(task.pages) : '');
  const [note, setNote] = useState(task.note ?? '');
  const [reason, setReason] = useState('');
  const [showLog, setShowLog] = useState(false);
  const dueChanged = (due || null) !== (task.due || null);
  const needReason = dueChanged && !!task.due;
  const save = useMutation({
    mutationFn: () => {
      const body: Parameters<typeof assignApi.updateTask>[1] = {};
      if (status !== task.status) body.status = status;
      if ((start || null) !== (task.start || null)) body.start = start || null;
      if (dueChanged) body.due = due || null;
      const pg = pages.trim() === '' ? null : Number(pages);
      if (pg !== task.pages) body.pages = pg;
      if ((note.trim() || null) !== (task.note || null)) body.note = note.trim() || null;
      if (reason.trim()) body.reason = reason.trim();
      return assignApi.updateTask(task.id, body);
    },
    onSuccess: (t) => {
      qc.invalidateQueries({ queryKey: assignKeys.all });
      setReason('');
      onDone?.(t);
    },
  });
  const err = errText(save.error, 'Görev kaydedilemedi.');
  const bad = !!(start && due && due < start);
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!bad && !(needReason && !reason.trim())) save.mutate();
      }}
    >
      <fieldset>
        <legend className={label}>Durum</legend>
        <div className="mt-1 grid grid-cols-2 gap-1.5 sm:grid-cols-5">
          {([...STATUS_ORDER, 'iptal'] as TaskStatus[]).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatus(s)}
              aria-pressed={status === s}
              className={`min-h-11 rounded-xl border px-2 text-[12px] font-extrabold transition-transform duration-150 ease-out active:scale-[0.97] sm:min-h-9 ${status === s ? 'border-canvas-violet bg-canvas-violet/10 text-canvas-violet' : 'border-slate-200 bg-white'}`}
            >
              {STATUS_LABEL[s]}
            </button>
          ))}
        </div>
      </fieldset>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <label className="block">
          <span className={label}>Başlangıç</span>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={`${field} mt-1`} />
        </label>
        <label className="block">
          <span className={label}>Termin</span>
          <input type="date" value={due} min={start || undefined} onChange={(e) => setDue(e.target.value)} className={`${field} mt-1`} />
        </label>
        <label className="col-span-2 block sm:col-span-1">
          <span className={label}>Tahmini sayfa</span>
          <input inputMode="numeric" pattern="[0-9]*" value={pages} onChange={(e) => setPages(e.target.value.replace(/\D/g, ''))} className={`${field} mt-1`} />
        </label>
      </div>
      {bad && <Note tone="err">Termin, başlangıçtan önce olamaz.</Note>}
      {needReason && (
        <label className="block">
          <span className={label}>Termin neden değişiyor?</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ör. yazar metni geç teslim etti" className={`${field} mt-1`} required />
        </label>
      )}
      <label className="block">
        <span className={label}>Not</span>
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} className={`${field} mt-1 resize-y`} />
      </label>
      {err && <Note tone="err">{err}</Note>}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button type="button" className={btnGhost} onClick={() => setShowLog((v) => !v)} aria-expanded={showLog}>
          <History aria-hidden className="h-4 w-4" />
          Geçmiş
        </button>
        <button type="submit" className={btnPrimary} disabled={save.isPending || bad || (needReason && !reason.trim())}>
          {save.isPending ? 'Kaydediliyor…' : 'Kaydet'}
        </button>
      </div>
      {showLog && <TaskHistory id={task.id} />}
    </form>
  );
}

/** Proje künyesinin tek satırlık özeti (kategori, durum, kurul onayı). */
export function projectMeta(p: {
  kitaplik: { name: string | null } | null;
  marka: { name: string | null } | null;
  status: string | null;
  boardApproved?: string | null;
  pages?: number | null;
  author?: string | null;
}): string {
  return [
    p.author && `Yazar: ${p.author}`,
    p.kitaplik?.name ? `Kitaplık: ${p.kitaplik.name}` : p.marka?.name ? `Marka: ${p.marka.name}` : 'Kategori girilmemiş',
    p.boardApproved && `Kurul onayı ${day(p.boardApproved)}`,
    p.pages ? `~${nf.format(p.pages)} sayfa` : null,
  ]
    .filter(Boolean)
    .join(' · ');
}
