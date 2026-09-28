import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, MessageSquareText, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { btnGhost, errText } from '../admin/ui';
import { noteApi, type NoteLabel, type NoteScreen, type NoteSignal } from './api';
import { activeLabels } from './format';

/** Serbest not sinyali (öneri 16): carinin son notlarının etiketi (tahsilat sözü, şikâyet, sipariş niyeti, iade talebi,
 *  kapanış sinyali) ve iki cümlelik özet. Yalnız bilgi: hiçbir skora girmez. Gizli not okunmaz. Telefonda tek sütun. */

const LABEL_CLASS: Record<NoteLabel, string> = {
  tahsilat: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  sikayet: 'bg-red-50 text-red-800 ring-red-200',
  siparis: 'bg-sky-50 text-sky-800 ring-sky-200',
  iade: 'bg-amber-50 text-amber-900 ring-amber-200',
  kapanis: 'bg-rose-100 text-rose-900 ring-rose-300',
  yok: 'bg-slate-100 text-slate-700 ring-slate-200',
};

const fmt = (iso: string | null) => (iso ? new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString('tr-TR', { day: 'numeric', month: 'short', timeZone: 'UTC' }) : 'tarihsiz');

export default function NoteSignalCard({ code, screen }: { code: string; screen: NoteScreen }) {
  const qc = useQueryClient();
  const key = ['not-sinyali', screen, code];
  const q = useQuery({ queryKey: key, queryFn: () => noteApi.view(code, screen), enabled: ENGINE_ENABLED && !!code, staleTime: 60_000, retry: false });
  const redo = useMutation({
    mutationFn: () => noteApi.summarize(code, screen),
    onSuccess: (v: NoteSignal) => { qc.setQueryData(key, v); toast.success('Not özeti yenilendi.'); },
    onError: (e) => toast.error(errText(e, 'Özet yazılamadı.') ?? ''),
  });
  const v = q.data;
  if (q.error || !v) return null;                 // ekranın asıl işini bozmaz; yetkisizse hiç görünmez
  const counts = activeLabels(v.sayilar);
  const summary = v.ozet?.metin ?? null;
  return (
    <section aria-label="Not sinyali" className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 text-[13px] font-extrabold">
          <MessageSquareText aria-hidden className="h-4 w-4 text-canvas-violet" />
          Notlardan sinyal
        </div>
        {v.sonNotlar.length > 0 && (
          <button type="button" className={btnGhost} disabled={redo.isPending} onClick={() => redo.mutate()}>
            {redo.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
            Özeti yenile
          </button>
        )}
      </div>
      {v.sonNotlar.length === 0 ? (
        <p className="mt-1 text-[12px] text-canvas-muted">Bu cari için okunabilir not yok.</p>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {counts.length === 0 && <span className="text-[12px] text-canvas-muted">Son {v.gun} günde belirgin sinyal yok.</span>}
            {counts.map((k) => (
              <span key={k} className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-bold ring-1 ring-inset ${LABEL_CLASS[k]}`}>
                {v.etiketler[k]} <span className="font-mono tabular-nums">{v.sayilar[k]}</span>
              </span>
            ))}
            {v.belirsiz > 0 && <span className="rounded-md bg-white px-1.5 py-0.5 text-[11.5px] font-bold text-canvas-muted ring-1 ring-inset ring-slate-200">Belirsiz {v.belirsiz}</span>}
          </div>
          <p className="mt-2 break-words text-[12.5px] leading-snug">{summary ?? v.kuralOzeti}</p>
          <div className="mt-0.5 text-[11px] text-canvas-muted">
            {v.ozet?.kaynak === 'zeki' ? 'Zeki AI özeti' : 'Kurala göre özet'}
            {v.ozet && !v.ozet.guncel ? ' · yeni not var, özet eski' : ''}
            {v.ozet?.dusen ? ` · denetimde ${v.ozet.dusen} cümle düştü` : ''}
          </div>
          <ol className="mt-2 flex flex-col gap-1">
            {v.sonNotlar.map((n, i) => (
              <li key={`${n.kaynak}-${i}`} className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11.5px]">
                <span className="font-mono tabular-nums text-canvas-muted">{fmt(n.tarih)}</span>
                <span className="text-canvas-muted">{n.kaynakAdi}</span>
                <span className={`rounded-md px-1.5 py-0.5 font-bold ring-1 ring-inset ${n.etiket ? LABEL_CLASS[n.etiket] : 'bg-white text-canvas-muted ring-slate-200'}`}>
                  {n.etiketAdi}{n.yontem === 'zeki' ? ' · Zeki AI' : ''}
                </span>
              </li>
            ))}
          </ol>
        </>
      )}
      <p className="mt-2 text-[10.5px] leading-snug text-canvas-muted">{v.not} Gizli işaretli not okunmaz.</p>
    </section>
  );
}
