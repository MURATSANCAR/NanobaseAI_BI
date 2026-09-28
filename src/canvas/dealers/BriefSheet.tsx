import { useEffect, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { Note, Pill, btnGhost, errText } from '../admin/ui';
import Sheet from '../editorial/studio/reader/Sheet';
import { fmtDay, fmtMoney, fmtPct } from '../field/api';
import { KV } from '../field/parts';
import { dealersApi, type BriefOut, type Card } from './api';
import SqlInfo from '../components/SqlInfo';

/** Ziyaret öncesi risk brifi (telefonda tek sayfa). Rakamlar karttan — Zeki AI yalnız kısa özeti ve «konuşulacak üç madde»yi
 *  yazar, metindeki her sayı olgularda geçmek zorunda; geçmezse kural brifi gösterilir. Girdi değişmedikçe model yeniden
 *  çağrılmaz. Skor ve segment brifte yazmaz (bayiye söylenecek bir şey değildir). */

export default function BriefSheet({ open, onClose, card }: { open: boolean; onClose: () => void; card: Card }) {
  const qc = useQueryClient();
  const asked = useRef(false);
  const gen = useMutation({
    mutationFn: (yenile: boolean) => dealersApi.brief(card.code, yenile),
    onSuccess: (r) => {
      if (r.not) toast.warning(r.not);
      void qc.invalidateQueries({ queryKey: ['dealers', 'card', card.code] });
    },
    onError: (e) => toast.error(errText(e, 'Brif hazırlanamadı.') ?? 'Brif hazırlanamadı.'),
  });
  useEffect(() => {
    if (!open) {
      asked.current = false;
      return;
    }
    if (!asked.current && (!card.brif || !card.brif.guncel)) {
      asked.current = true;
      gen.mutate(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, card.brif?.guncel]);

  const b: BriefOut | null = gen.data ?? (card.brif?.guncel ? card.brif : null);
  const l = card.limit;
  return (
    <Sheet open={open} modal onClose={onClose} title={`Risk brifi · ${card.unvan || card.code}`} subtitle={`Logo ${fmtDay(card.dataEnd)} tarihine kadar · vade tutarları yaklaşık`}>
      <div className="flex flex-col gap-3">
        <section className="rounded-2xl bg-slate-50 p-3">
          <KV k="Bakiye" info={<SqlInfo k={card.kaynaklar} alan="bakiye" label="Bakiye" />} v={fmtMoney(card.bakiye)} />
          <KV k="Vadesi geçmiş (yaklaşık)" info={<SqlInfo k={card.kaynaklar} alan="vadesiGecmis" label="Vadesi geçmiş" />} v={fmtMoney(card.vadesiGecmis)} tone={card.vadesiGecmis ? 'err' : undefined} />
          <KV k="90+ gün" info={<SqlInfo k={card.kaynaklar} alan="kovalar" label="90+ gün" />} v={fmtMoney(card.kovalar.k_90p)} tone={card.kovalar.k_90p ? 'err' : undefined} />
          <KV k="Son ödeme" v={card.sonOdeme ? fmtDay(card.sonOdeme) : 'yok (12 ay)'} />
          <KV k="12 ay net alım · iade" info={<SqlInfo k={card.kaynaklar} alan="net12" label="12 ay net alım ve iade" />} v={`${fmtMoney(card.net12)} · ${fmtPct(card.iadeOrani)}`} />
          {(card.karsiliksiz || card.protesto) ? <KV k="Karşılıksız / protesto" info={<SqlInfo k={card.kaynaklar} alan="karsiliksiz" label="Çek/senet olayı" />} v={`${card.karsiliksiz ?? 0} / ${card.protesto ?? 0}`} tone="err" /> : null}
          <KV k="CRM limit · doluluk" info={<SqlInfo k={card.kaynaklar} alan="limit" label="CRM limit ve doluluk" />} v={l.limit_toplam ? `${fmtMoney(l.limit_toplam)} · ${fmtPct(l.risk_doluluk ?? null)}` : card.crmEsi ? 'girilmemiş' : 'CRM eşi yok'} />
          {card.siparisRiskte ? <KV k="Risk onayı bekleyen sipariş" info={<SqlInfo k={card.kaynaklar} alan="siparisRiskte" label="Riskte sipariş" />} v={String(card.siparisRiskte)} tone="warn" /> : null}
        </section>

        {gen.isPending && !b ? (
          <div className="flex items-center gap-2 text-[12.5px] text-canvas-muted">
            <Loader2 aria-hidden className="h-4 w-4 animate-spin" />
            Zeki AI brifi hazırlıyor…
          </div>
        ) : b ? (
          <section className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-2">
              <Pill tone={b.kaynak === 'zeki' ? 'violet' : 'muted'}>{b.kaynak === 'zeki' ? 'Zeki AI' : 'Kural brifi'}</Pill>
              <button type="button" className={`${btnGhost} inline-flex items-center gap-1.5`} disabled={gen.isPending} onClick={() => gen.mutate(true)}>
                <RefreshCw aria-hidden className={`h-4 w-4 ${gen.isPending ? 'animate-spin' : ''}`} />
                Yenile
              </button>
            </div>
            <p className="text-[13.5px] leading-relaxed">
              {b.metin}
              <SqlInfo k={b.kaynaklar} alan="metin" label="Brifteki sayılar" className="ml-0.5" />
            </p>
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Bu ziyarette konuşulacaklar</div>
            <ol className="flex list-decimal flex-col gap-1 pl-5 text-[13px] leading-snug">
              {b.maddeler.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ol>
          </section>
        ) : (
          <Note tone="info">Brif hazırlanamadı; yukarıdaki rakamlar günlük turdan.</Note>
        )}
        <p className="text-[11px] leading-snug text-canvas-muted">
          Vade ve gecikme Logo'da ödeme kapama olmadığı için yaklaşıktır; bayi «ödedim» derse cari ekstresine bakın. Skor ve segment bayiyle paylaşılmaz.
        </p>
      </div>
    </Sheet>
  );
}
