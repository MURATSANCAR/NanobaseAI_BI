import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, CalendarCheck, Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { todayApi, type Today } from '../signals/api';
import { shouldAskModel, todayText, urgentCount } from '../signals/format';

/** Kampüs kişisel «Bugün» özeti (öneri 19), bildirim zilinin yanında. Maddeler kuraldır (uyarılar, e-posta atamaları ve
 *  yanıt süresi, ajanda, onay kuyrukları, saha bildirimi, okur sesi), köprüde kişinin yetkisiyle süzülür; her madde ilgili
 *  ekrana gider. Panel açılınca Zeki AI üç cümle özet yazar (denetimli, gün içinde girdi aynıysa yeniden yazılmaz); model
 *  yoksa ya da yazamazsa kural özeti görünür. Rozet yalnız acil madde sayısıdır. */

const DOT: Record<1 | 2 | 3, string> = { 1: 'bg-coral', 2: 'bg-amber-400', 3: 'bg-slate-300' };

export default function TodayBrief() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ['bugun'], queryFn: todayApi.get, enabled: ENGINE_ENABLED, staleTime: 5 * 60_000, retry: false });
  const write = useMutation({
    mutationFn: todayApi.summarize,
    onSuccess: (d: Today) => qc.setQueryData(['bugun'], d),
  });
  const asked = useRef(false);
  const d = q.data;

  // Panel açıldığında bir kez: özet yoksa ya da eskidiyse Zeki AI'dan iste (kişi özeti görmek için açtı).
  useEffect(() => {
    if (!open || !d || asked.current || write.isPending) return;
    if (shouldAskModel(d)) {
      asked.current = true;
      write.mutate();
    }
  }, [open, d, write]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (!ENGINE_ENABLED || q.error) return null;
  const urgent = urgentCount(d?.items);
  const { text, byModel } = d ? todayText(d) : { text: '', byModel: false };

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        title="Bugün"
        aria-label={urgent ? `Bugün (${urgent} acil iş)` : 'Bugün'}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="kp-press relative flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-white hover:text-ink sm:h-9 sm:w-9"
      >
        <CalendarCheck className="h-4 w-4" />
        {urgent > 0 && <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-coral ring-2 ring-white" />}
      </button>
      {open && (
        <>
          <button type="button" aria-label="Bugün panelini kapat" onClick={() => setOpen(false)} className="fixed inset-0 z-40 cursor-default" />
          {/* Telefonda ekranın iki kenarına oturur (düğme sağda değil, taşmasın); geniş ekranda düğmenin altında. */}
          <div role="dialog" aria-label="Bugün" className="glass-panel fixed inset-x-2 top-[4.5rem] z-50 rounded-2xl p-3 shadow-glass-float sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 sm:w-[380px]">
            <div className="mb-2 flex items-center justify-between">
              <span className="kp-display text-xs font-bold uppercase tracking-wider text-ink">Bugün</span>
              <span className="kp-mono text-[11px] text-muted">yalnız yetkili olduğun ekranlar</span>
            </div>
            {!d ? (
              <p className="text-xs text-muted">Yükleniyor…</p>
            ) : (
              <>
                <div className="rounded-xl border border-violet/20 bg-white/90 p-2.5">
                  <p className="text-xs leading-relaxed text-ink">{text}</p>
                  <div className="mt-1 flex items-center gap-1.5 text-[11px] text-muted">
                    {write.isPending && <Loader2 aria-hidden className="h-3 w-3 animate-spin" />}
                    {write.isPending ? 'Zeki AI özetliyor…' : byModel ? `Zeki AI${d.ozet?.dusen ? ` · denetimde ${d.ozet.dusen} cümle düştü` : ''}` : 'Kurala göre özet'}
                  </div>
                </div>
                {d.items.length > 0 && (
                  <ul className="mt-2 max-h-72 space-y-1.5 overflow-y-auto">
                    {d.items.map((x, i) => (
                      <li key={`${x.kaynak}-${i}`}>
                        <Link
                          to={x.link}
                          onClick={() => setOpen(false)}
                          className="kp-press flex min-h-11 items-center gap-2 rounded-xl border border-slate-200/70 bg-white/80 px-2.5 py-2 text-xs hover:bg-white"
                        >
                          <span aria-hidden className={`h-2 w-2 shrink-0 rounded-full ${DOT[x.oncelik]}`} />
                          <span className="min-w-0 flex-1">
                            <span className="block font-bold text-ink">{x.baslik}</span>
                            {x.detay && <span className="block truncate text-[11px] text-muted">{x.detay}</span>}
                          </span>
                          <span className="kp-mono shrink-0 font-bold tabular-nums text-ink">{x.sayi}</span>
                          <ArrowRight aria-hidden className="h-3.5 w-3.5 shrink-0 text-violet" />
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
                {d.okunamayan.length > 0 && <p className="mt-2 text-[11px] text-muted">Okunamayan: {d.okunamayan.join(', ')}.</p>}
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
