import { useState } from 'react';
import { Check, Minus, X } from 'lucide-react';
import { useCan } from '../useAdmin';
import { errText } from '../admin/ui';
import { mqApi, type Verdict } from '../model-quality/api';

/**
 * Zeki AI cevabının altındaki «Doğru / Kısmen / Yanlış» (M50). Tek dokunuş hükmü kaydeder; Kısmen/Yanlış'ta isteğe
 * bağlı kısa not alanı açılır (not aynı kaydı günceller). Hüküm model ekibinin kuyruğuna düşer, `sl_query_log.validated`
 * da güncellenir. Yetki `ozellik:zeki.geri-bildirim` yoksa ya da cevabın kaydı yoksa hiç görünmez.
 *
 * Giriş animasyonu yok: günde onlarca cevabın altında görünür. Yalnız basma geri bildirimi (scale 0.97) var.
 * `key={queryId}` ile kullanın: yeni cevapta durum sıfırlanır.
 */
const OPTIONS: Array<{ v: Verdict; label: string; icon: typeof Check; on: string }> = [
  { v: 'dogru', label: 'Doğru', icon: Check, on: 'bg-emerald-600 text-white ring-emerald-600' },
  { v: 'kismen', label: 'Kısmen', icon: Minus, on: 'bg-amber-500 text-white ring-amber-500' },
  { v: 'yanlis', label: 'Yanlış', icon: X, on: 'bg-red-600 text-white ring-red-600' },
];

export default function AnswerFeedback({ queryId, className = '' }: { queryId?: string | null; className?: string }) {
  const allowed = useCan('zeki.geri-bildirim');
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [noteSent, setNoteSent] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!queryId || !allowed) return null;

  const send = async (v: Verdict, comment?: string) => {
    setBusy(true);
    setError(null);
    try {
      const out = await mqApi.feedback({ queryId, verdict: v, comment });
      setVerdict(v);
      setMessage(out.message);
      if (comment) setNoteSent(true);
    } catch (e) {
      setError(errText(e, 'Kaydedilemedi.') ?? 'Kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  };

  const pick = (v: Verdict) => {
    if (busy || v === verdict) return;
    setNoteSent(false);
    void send(v, note.trim() || undefined);
  };

  const askNote = verdict === 'kismen' || verdict === 'yanlis';
  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div role="group" aria-label="Bu cevap doğru mu?" className="flex flex-wrap items-center gap-1.5">
        <span className="mr-0.5 text-[11.5px] font-bold text-muted">Bu cevap doğru mu?</span>
        {OPTIONS.map(({ v, label, icon: Icon, on }) => (
          <button
            key={v}
            type="button"
            aria-pressed={verdict === v}
            disabled={busy}
            onClick={() => pick(v)}
            className={[
              'inline-flex min-h-11 items-center gap-1 rounded-full px-3 text-[11.5px] font-extrabold ring-1',
              'transition-[background-color,color,transform] duration-150 ease-out active:scale-[0.97]',
              'motion-reduce:transition-none motion-reduce:active:scale-100 disabled:opacity-60 sm:min-h-7',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet/60',
              verdict === v ? on : 'bg-white text-ink ring-slate-200 hover:bg-slate-50',
            ].join(' ')}
          >
            <Icon aria-hidden className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>
      {askNote && !noteSent && (
        <form
          className="flex w-full max-w-[560px] flex-col gap-1.5 sm:flex-row sm:items-start"
          onSubmit={(e) => {
            e.preventDefault();
            if (note.trim() && verdict) void send(verdict, note.trim());
          }}
        >
          <label className="sr-only" htmlFor={`fb-note-${queryId}`}>Neresi yanlış?</label>
          <textarea
            id={`fb-note-${queryId}`}
            rows={2}
            maxLength={2000}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="İsteğe bağlı: neresi eksik ya da yanlış? Örn. iptal faturalar düşülmemiş."
            className="min-h-[44px] w-full resize-y rounded-xl border border-slate-200 bg-white px-3 py-2 text-base font-medium outline-none focus:border-violet sm:text-[12px]"
          />
          <button
            type="submit"
            disabled={busy || !note.trim()}
            className="inline-flex min-h-11 shrink-0 items-center justify-center rounded-xl bg-violet px-3.5 text-[12px] font-extrabold text-white transition-transform duration-150 ease-out active:scale-[0.97] disabled:opacity-50 disabled:active:scale-100 sm:min-h-9"
          >
            Notu gönder
          </button>
        </form>
      )}
      {(message || error) && (
        <p role="status" className={`text-[11.5px] font-semibold ${error ? 'text-red-600' : 'text-muted'}`}>
          {error ?? (noteSent ? 'Not eklendi. ' + (message ?? '') : message)}
        </p>
      )}
    </div>
  );
}
