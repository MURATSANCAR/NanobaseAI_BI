import { useQuery } from '@tanstack/react-query';
import { ListChecks, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { fieldApi, fmtDay } from './api';
import SqlInfo from '../components/SqlInfo';

/** Sabah brifi: Bugün sekmesinin en üstünde, telefonda tek bakışta okunan 4–5 cümle. Rakamlar ve sıra kuraldan gelir;
 *  «Zeki AI» etiketi yalnız model metni sayı denetiminden geçtiyse görünür, değilse «Kurala göre özet» yazar. Brif
 *  okunamazsa kart hiç görünmez (liste zaten altta). */
export default function MorningBrief({ temsilci }: { temsilci: string }) {
  const q = useQuery({
    queryKey: ['field', 'today-brief', temsilci],
    queryFn: () => fieldApi.todayBrief({ temsilci: temsilci || undefined }),
    enabled: ENGINE_ENABLED,
    staleTime: 5 * 60_000,
  });
  if (q.isLoading) {
    return (
      <section aria-label="Günün özeti" aria-busy="true" className="rounded-2xl border border-slate-100 bg-white/85 p-3.5">
        <div className="h-3 w-24 rounded bg-slate-100" />
        <div className="mt-2.5 space-y-2">
          <div className="h-3 w-full rounded bg-slate-100" />
          <div className="h-3 w-11/12 rounded bg-slate-100" />
          <div className="h-3 w-2/3 rounded bg-slate-100" />
        </div>
      </section>
    );
  }
  const b = q.data;
  if (!b || !b.metin) return null;
  const zeki = b.kaynak === 'zeki';
  return (
    <section aria-label="Günün özeti" className="rounded-2xl border border-canvas-violet/15 bg-white/90 p-3.5 shadow-sm">
      <div className="mb-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10.5px] font-extrabold uppercase tracking-wide ${zeki ? 'bg-canvas-violet/10 text-canvas-violet' : 'bg-slate-100 text-canvas-ink'}`}>
          {zeki ? <Sparkles aria-hidden className="h-3 w-3" /> : <ListChecks aria-hidden className="h-3 w-3" />}
          {zeki ? 'Zeki AI · günün özeti' : 'Kurala göre özet'}
        </span>
        <span className="text-[11px] text-canvas-muted">{fmtDay(b.gun)}{b.dataEnd ? ` · veri ${fmtDay(b.dataEnd)}` : ''}</span>
        <SqlInfo k={b.kaynaklar} alan="metin" label="Günün özetindeki sayılar" />
      </div>
      <p className="text-[14px] leading-relaxed text-canvas-ink [overflow-wrap:anywhere]">{b.metin}</p>
    </section>
  );
}
