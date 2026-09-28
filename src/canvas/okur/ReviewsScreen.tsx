import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Check, Copy, Loader2, RefreshCw, Sparkles, Star } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Note, Pill, btnGhost, btnPrimary, errText, field } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { REVIEW_TONE, fmtDay, fmtInt, okurApi, type OkurMeta, type Review, type ReviewState } from './api';
import { OkurFrame } from './parts';
import { ReaderVoicePanel, TopicChip, useVoiceLabels } from '../signals/ReaderVoice';
import type { VoiceLabel } from '../signals/api';

/** M37 «Yorum cevapları»: sitedeki okur yorumları (anlık, yorumcu adı olmadan), Zeki AI cevap taslağı, düzenleme ve
 *  «cevaplandı» işareti. Cevap sitede elle girilir; portal T-soft'a yazmaz. Yorum metni saklanmaz, taslak saklanır. */
export default function ReviewsScreen() {
  const [params, setParams] = useSearchParams();
  const durum = (params.get('durum') ?? 'cevapsiz') as ReviewState | 'hepsi';
  const meta = useQuery({ queryKey: ['okur', 'meta'], queryFn: okurApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ['okur', 'reviews', durum],
    queryFn: () => okurApi.reviews(durum === 'hepsi' ? '' : durum),
    enabled: ENGINE_ENABLED,
  });
  // Köprüdeki kısa önbelleği atlayıp siteden yeniden okur; sonra liste tazelenir.
  const reread = useMutation({
    mutationFn: () => okurApi.reviews('', true),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['okur', 'reviews'] }),
    onError: (e) => toast.error(errText(e, 'Siteden okunamadı.') ?? ''),
  });
  const topics = useVoiceLabels('site-yorum');
  const n = list.data?.sayilar;
  const k = list.data?.kaynaklar;
  const setDurum = (d: string) => {
    const p = new URLSearchParams(params);
    if (d === 'cevapsiz') p.delete('durum');
    else p.set('durum', d);
    setParams(p, { replace: true });
  };
  return (
    <OkurFrame
      crumb="Yorum cevapları"
      title="Okur yorumlarına cevap"
      lead="Sitedeki okur yorumları ve Zeki AI'ın cevap taslağı. Yorumcunun adı okunmaz; metindeki e-posta ve telefon gizlenir. Cevabı sitede siz girersiniz, sonra burada «cevaplandı» işaretlersiniz."
      source="Kaynak: site yorumları (yalnız okuma) · portal kaydı"
      aside={
        <div className="flex flex-wrap justify-start gap-2 lg:justify-end">
          <Link to="/seo-geo/yorumlar" className={btnGhost}>Yorum sayıları (SEO)</Link>
          <button type="button" className={btnGhost} disabled={list.isFetching || reread.isPending} onClick={() => reread.mutate()}>
            <RefreshCw aria-hidden className={`h-4 w-4 ${reread.isPending ? 'animate-spin' : ''}`} />
            Siteden yeniden oku
          </button>
        </div>
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {list.error && <Note tone="err">{errText(list.error, 'Yorumlar okunamadı.')}</Note>}
      <ReaderVoicePanel sources={['site-yorum']} />
      {n && (
        <KpiRow>
          <Kpi label="Cevapsız" value={fmtInt(n.cevapsiz)} help="Sitede cevabı olmayan, taslağı da yok" active={durum === 'cevapsiz'} onClick={() => setDurum('cevapsiz')} info={<SqlInfo k={k} alan="sayilar" label="Cevapsız yorum" />} />
          <Kpi label="Taslak hazır" value={fmtInt(n.taslak)} help="Sitede girilmeyi bekliyor" active={durum === 'taslak'} onClick={() => setDurum('taslak')} info={<SqlInfo k={k} alan="sayilar" label="Taslak hazır" />} />
          <Kpi label="Cevaplandı" value={fmtInt(n.cevaplandi)} help="Sitede cevap var ya da işaretlendi" active={durum === 'cevaplandi'} onClick={() => setDurum('cevaplandi')} info={<SqlInfo k={k} alan="sayilar" label="Cevaplandı" />} />
          <Kpi label="Toplam yorum" value={fmtInt(n.toplam)} help={list.data?.seo ? `SEO gece özeti: ${fmtInt(list.data.seo.yorum)} yorum, ${fmtInt(list.data.seo.urun)} ürün` : 'Sitedeki bütün yorumlar'} active={durum === 'hepsi'} onClick={() => setDurum('hepsi')} info={<SqlInfo k={k} alan={list.data?.seo ? 'seo' : 'sayilar'} label="Toplam yorum ve SEO özeti" />} />
        </KpiRow>
      )}
      <Panel>
        {list.data && <p className="mb-2 flex items-center gap-1 text-[11.5px] text-canvas-muted">Yorumlar, puanlar ve durum<SqlInfo k={k} alan="items" label="Yorum listesi ve puanlar" /></p>}
        {list.isLoading && <div className="py-8 text-center text-[12px] text-canvas-muted">Site yorumları okunuyor…</div>}
        {list.data && !list.data.items.length && <div className="py-8 text-center text-[12.5px] text-canvas-muted">Bu süzgeçte yorum yok.</div>}
        <div className="flex flex-col gap-2">
          {meta.data && list.data?.items.map((r) => <ReviewCard key={r.id} r={r} meta={meta.data} topic={topics.data?.items[r.id]} />)}
        </div>
      </Panel>
    </OkurFrame>
  );
}

function Stars({ n }: { n: number | null }) {
  if (!n) return <span className="text-[11.5px] text-canvas-muted">puansız</span>;
  return (
    <span className="inline-flex items-center gap-0.5" aria-label={`${n} yıldız`}>
      {[1, 2, 3, 4, 5].map((i) => <Star key={i} aria-hidden className={`h-3.5 w-3.5 ${i <= n ? 'fill-amber-400 text-amber-400' : 'text-slate-300'}`} />)}
    </span>
  );
}

function ReviewCard({ r, meta, topic }: { r: Review; meta: OkurMeta; topic?: VoiceLabel }) {
  const qc = useQueryClient();
  const [text, setText] = useState(r.taslak ?? '');
  const [open, setOpen] = useState(false);
  const can = meta.me.canReview;
  const done = (msg: string) => {
    qc.invalidateQueries({ queryKey: ['okur', 'reviews'] });
    toast.success(msg);
  };
  const draft = useMutation({
    mutationFn: () => okurApi.draftReview(r.id),
    onSuccess: (x) => { setText(x.taslak ?? ''); setOpen(true); done('Cevap taslağı hazır; gözden geçirin.'); },
    onError: (e) => toast.error(errText(e, 'Taslak üretilemedi.') ?? ''),
  });
  const mark = useMutation({
    mutationFn: (durum: ReviewState) => okurApi.markReview(r.id, { durum, taslak: text, productId: r.productId }),
    onSuccess: (x) => done(x.durum === 'cevaplandi' ? 'Cevaplandı olarak işaretlendi.' : 'Taslak kaydedildi.'),
    onError: (e) => toast.error(errText(e, 'Kaydedilemedi.') ?? ''),
  });
  const busy = draft.isPending || mark.isPending;
  return (
    <article className="rounded-2xl border border-slate-100 bg-white/80 p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Pill tone={REVIEW_TONE[r.durum]}>{r.durumAdi}</Pill>
        {!r.onayli && <Pill tone="muted">Sitede onay bekliyor</Pill>}
        <Stars n={r.puan} />
        <TopicChip label={topic} />
        <span className="font-mono text-[11.5px] tabular-nums text-canvas-muted">{fmtDay(r.tarih)}</span>
      </div>
      <div className="mt-1 break-words text-[13.5px] font-extrabold leading-snug">{r.urun ?? `Ürün ${r.productId ?? '—'}`}</div>
      {r.baslik && <div className="mt-0.5 break-words text-[12.5px] font-bold">{r.baslik}</div>}
      <p className="mt-1 whitespace-pre-wrap break-words text-[12.5px] leading-snug text-canvas-ink/90">{r.metin || 'Metin yok.'}</p>
      {(open || r.taslak) && (
        <div className="mt-2 rounded-xl bg-slate-50 p-2">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">
            <span>Cevap taslağı {r.taslakKaynak === 'zeki' ? '· Zeki AI' : ''}{r.taslakYazan ? ` · ${r.taslakYazan}` : ''}</span>
            {text && (
              <button type="button" className="inline-flex min-h-11 items-center gap-1 text-canvas-violet sm:min-h-0"
                onClick={() => navigator.clipboard?.writeText(text).then(() => toast.success('Kopyalandı.'), () => toast.error('Kopyalanamadı.'))}>
                <Copy aria-hidden className="h-3.5 w-3.5" />
                Kopyala
              </button>
            )}
          </div>
          <textarea className={`${field} min-h-[96px]`} value={text} disabled={!can} onChange={(e) => setText(e.target.value)} />
        </div>
      )}
      {can && r.durum !== 'cevaplandi' && (
        <div className="mt-2 flex flex-wrap justify-end gap-2">
          {meta.modelVar && (
            <button type="button" className={btnGhost} disabled={busy || !r.metin} onClick={() => draft.mutate()}>
              {draft.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              {r.taslak ? 'Yeni taslak' : 'Zeki AI taslağı'}
            </button>
          )}
          {!open && !r.taslak && <button type="button" className={btnGhost} onClick={() => setOpen(true)}>Elle yaz</button>}
          {(open || r.taslak) && (
            <button type="button" className={btnGhost} disabled={busy || !text.trim()} onClick={() => mark.mutate('taslak')}>Taslağı kaydet</button>
          )}
          <button type="button" className={btnPrimary} disabled={busy} onClick={() => mark.mutate('cevaplandi')}>
            <Check aria-hidden className="h-4 w-4" />
            Sitede cevaplandı
          </button>
        </div>
      )}
      {can && r.durum === 'cevaplandi' && !r.sitedeCevap && (
        <div className="mt-2 flex justify-end">
          <button type="button" className={btnGhost} disabled={busy} onClick={() => mark.mutate(r.taslak ? 'taslak' : 'cevapsiz')}>İşareti geri al</button>
        </div>
      )}
    </article>
  );
}
