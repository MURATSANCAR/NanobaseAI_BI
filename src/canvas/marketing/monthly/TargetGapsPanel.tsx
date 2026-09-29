import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, btnGhost, errText } from '../../admin/ui';
import { fmtMoney, fmtPct, fmtStamp } from '../api';
import { Block } from '../parts';
import SqlInfo from '../../components/SqlInfo';
import { monthApi, type TargetGaps } from './api';

/** Öneri 17 (M18): «hedefin altında kalan kitaplara bu ay iş planlanmamış». Liste kuraldır (bütçe modülünün açık kitap
 *  sapması, ay planı kalemleri ve bu aya düşen plan işleri); paragrafı istenirse Zeki AI yazar (denetimli). Karar müdürde.
 *  Telefonda tablo yerine kart listesi; tutar yalnız bütçe görme yetkisinde. */
export default function TargetGapsPanel({ ay, canSeeBudget }: { ay: string; canSeeBudget: boolean }) {
  const qc = useQueryClient();
  const key = ['mkt', 'target-gaps', ay];
  const q = useQuery({ queryKey: key, queryFn: () => monthApi.targetGaps(ay), enabled: ENGINE_ENABLED && !!ay });
  const explain = useMutation({
    mutationFn: () => monthApi.targetGapsExplain(ay),
    onSuccess: (g: TargetGaps) => { qc.setQueryData(key, g); toast.success('Zeki AI paragrafı hazır.'); },
    onError: (e) => toast.error(errText(e, 'Paragraf yazılamadı.') ?? ''),
  });
  const g = q.data;
  return (
    <Block
      title="Hedefin altında, bu ay işi planlanmamış kitaplar"
      help="Bütçe planında satış hedefinin gerisinde kaldığı uyarısı olan, ama bu ayın planında kalemi ya da bu aya düşen pazarlama işi olmayan kitaplar. Hangi kitaba iş açılacağına siz karar verirsiniz."
      info={<SqlInfo k={g?.kaynaklar} alan="items[]" label="Hedef açığı listesi" />}
      action={g && g.plansiz > 0 && g.modelVar ? (
        <button type="button" className={btnGhost} disabled={explain.isPending} onClick={() => explain.mutate()}>
          {explain.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
          {g.paragrafKaynak === 'zeki' ? 'Özeti yenile' : 'Zeki AI ile özetle'}
        </button>
      ) : undefined}
    >
      {q.error && <Note tone="err">{errText(q.error, 'Hedef açığı okunamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {g && (
        <div className="flex flex-col gap-2.5">
          <div className="grid grid-cols-3 gap-2 text-center">
            {[{ l: 'Hedef altı', n: g.hedefAlti, a: 'hedefAlti' }, { l: 'Bu ay planlı', n: g.planli, a: 'planli' }, { l: 'Planlanmamış', n: g.plansiz, a: 'plansiz' }].map(({ l, n, a }) => (
              <div key={l} className="relative rounded-xl bg-white/70 px-2 py-2">
                <span className="absolute right-1 top-1"><SqlInfo k={g.kaynaklar} alan={a} label={l} /></span>
                <div className="font-mono text-[20px] font-bold tabular-nums leading-none">{n}</div>
                <div className="mt-1 break-words text-[11px] font-bold leading-tight text-canvas-muted">{l}</div>
              </div>
            ))}
          </div>
          <div className="rounded-xl bg-slate-50 p-2.5">
            <p className="break-words text-[12.5px] leading-snug">{g.paragraf}</p>
            <div className="mt-1 text-[11px] font-bold text-canvas-muted">
              {g.paragrafKaynak === 'zeki'
                ? `Zeki AI · ${fmtStamp(g.paragrafZaman)}${g.paragrafDusen ? ` · denetimde ${g.paragrafDusen} cümle düştü` : ''}`
                : g.eskiParagraf ? 'Kurala göre · liste değiştiği için önceki Zeki AI paragrafı gösterilmiyor' : 'Kurala göre'}
            </div>
          </div>
          {g.items.length > 0 && (
            <ul className="flex flex-col gap-1.5">
              {g.items.map((x) => (
                <li key={x.stokKodu} className="flex min-h-11 flex-wrap items-center justify-between gap-x-3 gap-y-0.5 rounded-xl border border-slate-100 bg-white/80 px-3 py-2">
                  <div className="min-w-0 flex-1">
                    <div className="break-words text-[12.5px] font-semibold leading-snug">{x.ad}</div>
                    <div className="font-mono text-[11px] text-canvas-muted">{x.stokKodu}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-3 text-right text-[12px] tabular-nums">
                    <span><span className="text-canvas-muted">hedefe oran </span><b>{fmtPct(x.oran)}</b></span>
                    {canSeeBudget && <span><span className="text-canvas-muted">eksik </span><b>{fmtMoney(x.eksik)}</b></span>}
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="text-[11px] leading-snug text-canvas-muted">{g.kaynak}</p>
        </div>
      )}
    </Block>
  );
}
