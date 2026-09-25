import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { History, RotateCcw } from 'lucide-react';
import { studioPlanApi, type Plan, type PlanHistoryItem } from '../../engine';
import { btnGhost } from '../../admin/ui';
import { ConfirmDialog } from './dialogs';

/** Sürüm geçmişi: sunucu her yazımda önceki planı saklar (silinmez). «Bu sürüme dön» o sürümü yeni sürüm
 *  olarak geri yükler; aradaki sürümler de geçmişte kalır, yani dönüş de geri alınabilir. */

const fmt = (at: string) => {
  const d = new Date(at);
  return Number.isNaN(d.getTime()) ? at : new Intl.DateTimeFormat('tr-TR', { dateStyle: 'short', timeStyle: 'short' }).format(d);
};

export default function HistoryPanel({ job, rev, online, onRestored }: {
  job: string;
  rev: number;
  online: <T,>(fn: (rev: number) => Promise<T>) => Promise<T>;
  onRestored: (p: Plan) => void;
}) {
  const q = useQuery({
    queryKey: ['studio', 'plan', 'history', job, rev],
    queryFn: async () => {
      const r = await studioPlanApi.history(job);
      const list = Array.isArray(r) ? r : r.history ?? [];
      return [...list].sort((a, b) => b.rev - a.rev);
    },
    staleTime: 10_000,
  });
  const [ask, setAsk] = useState<PlanHistoryItem | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const restore = async (h: PlanHistoryItem) => {
    setBusy(true); setErr(null);
    try {
      const p = await online(() => studioPlanApi.restore(job, h.rev));
      onRestored(p);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] text-canvas-muted">Her kayıt ayrı bir sürümdür; hiçbiri silinmez. Şu an: sürüm {rev}.</p>
      {q.isLoading && <p className="text-[12px] text-canvas-muted">Yükleniyor…</p>}
      {q.error && <p className="text-[12px] font-semibold text-rose-700">{(q.error as Error).message}</p>}
      <ol className="flex flex-col gap-1.5">
        {(q.data ?? []).map((h) => (
          <li key={h.rev} className="flex items-start justify-between gap-2 rounded-xl bg-white/70 px-2.5 py-2 text-[12px]">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 font-bold"><History className="h-3.5 w-3.5 text-canvas-muted" aria-hidden />Sürüm {h.rev}{h.rev === rev ? ' · şu an' : ''}</div>
              <div className="text-canvas-muted">{fmt(h.at)} · {h.by}</div>
              {h.what && <div className="mt-0.5 leading-snug">{h.what}</div>}
            </div>
            {h.rev !== rev && (
              <button type="button" className={`${btnGhost} shrink-0`} disabled={busy} onClick={() => setAsk(h)}>
                <RotateCcw className="h-4 w-4" aria-hidden />Bu sürüme dön
              </button>
            )}
          </li>
        ))}
      </ol>
      {err && <p className="text-[12px] font-semibold text-rose-700">{err}</p>}
      <ConfirmDialog open={!!ask} title={`Sürüm ${ask?.rev ?? ''}'e dönülsün mü?`} confirm="Bu sürüme dön"
        body="Bekleyen değişiklikler önce kaydedilir; sonra o sürüm yeni bir sürüm olarak geri yüklenir. Şimdiki hâl geçmişte kalır, istenirse ona da dönülebilir."
        onClose={() => setAsk(null)} onConfirm={() => { const h = ask; setAsk(null); if (h) void restore(h); }} />
    </div>
  );
}
