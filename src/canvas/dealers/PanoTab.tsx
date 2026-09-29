import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, btnGhost, errText } from '../admin/ui';
import { fmtDay, fmtMoney, fmtPct, fmtShort } from '../field/api';
import { Block, Empty, Stat } from '../field/parts';
import { dealersApi, type Dealer, type DealersMeta } from './api';
import { DealerRow, DistBar, approxNote } from './parts';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { Explain } from '../components/Explain';
import { ShowMoreButton, useShowMore } from '../components/ShowMore';

/** Pano: ilk açılış. Kötüleşen bayilere bakmak tek dokunuş (kart listesi burada), bayi kartı iki. */

export default function PanoTab({ meta, goList }: { meta: DealersMeta; goList: (p: Record<string, string | null>) => void }) {
  const q = useQuery({ queryKey: ['dealers', 'summary'], queryFn: dealersApi.summary, enabled: ENGINE_ENABLED && !!meta.run.gun });
  const s = q.data;
  const limits = useShowMore(s?.limitBekleyen, 5);
  const err = errText(q.error, 'Pano okunamadı; biraz sonra yeniden deneyin.');
  if (!meta.run.gun) return null;
  if (q.isLoading) return <Loading />;
  if (err) return <Note tone="err">{err}</Note>;
  if (!s) return null;
  const showBmt = meta.me.canAll;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1 px-1 text-[11.5px] font-semibold text-canvas-muted">
        Bu göstergeler ne demek?
        <Explain label="Pano göstergeleri" title="Pano göstergeleri">
          Vadesi geçmiş: ödeme günü geçmiş açık bakiye (yaklaşık). 90+ gün: vadesi 90 günden fazla geçmiş kısmı. Riske takılı sipariş: CRM'de risk limiti yüzünden onay bekleyen sipariş sayısı. İlk 10 cari payı: açık bakiyenin en büyük 10 caride toplanan oranı; yükseldikçe alacak birkaç müşteriye bağımlı demektir.
        </Explain>
      </div>
      <div className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        <Stat label="Vadesi geçmiş" info={<SqlInfo k={s.kaynaklar} alan="vadesiGecmis" label="Vadesi geçmiş" />} value={fmtShort(s.vadesiGecmis)} tone={s.vadesiGecmis > 0 ? 'err' : undefined} help={`Yaklaşık · ${fmtDay(s.agingAsof)} itibarıyla`} />
        <Stat label="90+ gün" info={<SqlInfo k={s.kaynaklar} alan="kovalar" label="90+ gün" />} value={fmtShort(s.kovalar.k_90p)} tone={s.kovalar.k_90p > 0 ? 'err' : undefined} help={`${s.kovaCari.k_90p} cari`} />
        <Stat label="Riske takılı sipariş" info={<SqlInfo k={s.kaynaklar} alan="siparisRiskte" label="Riske takılı sipariş" />} value={String(s.siparisRiskte)} tone={s.siparisRiskte ? 'warn' : undefined} help="CRM risk limiti onayı bekleyen" />
        <Stat label="İlk 10 cari payı" info={<SqlInfo k={s.kaynaklar} alan="yogunlasma10" label="İlk 10 cari payı" />} value={fmtPct(s.yogunlasma10)} help="Açık bakiyenin yoğunlaşması" />
      </div>

      <Block
        title="Segment dağılımı"
        action={
          <span className="flex items-center gap-1 text-[11px] font-semibold text-canvas-muted">
            <Explain label="Segment" title="Segment ne demek?">Skor, ödeme gecikmesi, çek-senet olayı, iade oranı, limit doluluğu, sipariş düzensizliği ve tahsilat süresinden kuralla hesaplanır; yükseldikçe risk artar. A en düşük, D en yüksek risk segmentidir. Anahtar hesaplar (zincir, e-ticaret, dağıtıcı) kendi eşikleriyle değerlendirilir. Hareketsiz cari (bakiye yok, 12 ayda alım yok) segment almaz.</Explain>
            Bugün
            <SqlInfo k={s.kaynaklar} alan="segment" label="Segment dağılımı" />
            {s.segment30 && (
              <>
                30 gün önce
                <SqlInfo k={s.kaynaklar} alan="segment30" label="30 gün önceki dağılım" />
              </>
            )}
          </span>
        }
        help={`${s.aktif} etkin cari${s.hareketsiz ? ` · ${s.hareketsiz} hareketsiz (bakiye yok, 12 ayda alım yok)` : ''} · kural sürüm ${s.kural}${
          s.gun30 ? ` · ince çubuk ${fmtDay(s.gun30)} (bugünkü kuralla yeniden puanlandı)` : ''
        }`}
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <div className="mb-1.5 flex items-baseline justify-between gap-2">
              <span className="text-[12.5px] font-extrabold">Kitapçı ve bayi</span>
              <button type="button" className="text-[11.5px] font-bold text-canvas-violet hover:underline" onClick={() => goList({ grup: 'standart', segment: 'C,D' })}>
                C ve D'yi listele
              </button>
            </div>
            <DistBar dist={s.segment} before={s.segment30} group="standart" />
          </div>
          <div>
            <div className="mb-1.5 flex items-baseline justify-between gap-2">
              <span className="text-[12.5px] font-extrabold">Anahtar hesap</span>
              <button type="button" className="text-[11.5px] font-bold text-canvas-violet hover:underline" onClick={() => goList({ grup: 'anahtar', segment: null })}>
                Listele
              </button>
            </div>
            <DistBar dist={s.segment} before={s.segment30} group="anahtar" />
            <p className="mt-1.5 text-[11px] leading-snug text-canvas-muted">Zincir, e-ticaret, dağıtıcı ve cirodan büyük pay alanlar kendi eşikleriyle ölçülür; mahalle kitapçısıyla aynı ölçüye konmaz.</p>
          </div>
        </div>
      </Block>

      <Block title="Alacak yaşlandırması" help={approxNote} action={<SqlInfo k={s.kaynaklar} alan="kovalar" label="Alacak yaşlandırması" />}>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          <Stat label="Gelmemiş" value={fmtShort(s.gelmemis)} />
          {meta.buckets.map((b) => (
            <Stat key={b.key} label={b.label} value={fmtShort(s.kovalar[b.key])} help={`${s.kovaCari[b.key]} cari`} tone={b.key === 'k_90p' && s.kovalar[b.key] > 0 ? 'err' : undefined} />
          ))}
        </div>
        {s.plansiz > 0 && <p className="mt-2 text-[11.5px] text-canvas-muted">Vade planına dağıtılamayan bakiye (plansız): {fmtMoney(s.plansiz)} — kovalara girmez.</p>}
      </Block>

      <Block title="Segmenti düşenler" help="Bir önceki tura göre segmenti kötüleşen bayiler (iki gün de bugünkü kuralla puanlanır).">
        <DealerList items={s.kotulesenler} showBmt={showBmt} empty="Son turda segmenti düşen bayi yok." k={s.kaynaklar} alan="kotulesenler[]" />
      </Block>

      {s.egilimKotu.length > 0 && (
        <Block title="Kötüleşme eğilimi" help="Skoru 30 gün öncesine göre kural eşiğinden fazla artan bayiler (segment henüz değişmemiş olabilir).">
          <DealerList items={s.egilimKotu} showBmt={showBmt} empty="" k={s.kaynaklar} alan="egilimKotu[]" />
        </Block>
      )}

      <Block
        title="Onay bekleyen limit önerileri"
        help="Rakamı kural üretir; satış müdürü onaylar, onaylanan «CRM'e işlenecek» listesine düşer."
        action={
          <span className="flex items-center gap-1">
            <SqlInfo k={s.kaynaklar} alan="limitBekleyen[].onerilen" label="Önerilen limit" />
            <button type="button" className={btnGhost} onClick={() => goList({ sekme: 'limit' })}>
              Hepsi ({s.limitBekleyen.length})
            </button>
          </span>
        }
      >
        {s.limitBekleyen.length === 0 ? (
          <Empty>Onay bekleyen limit önerisi yok.</Empty>
        ) : (
          <>
          <ul className="flex flex-col gap-1">
            {limits.shown.map((p) => (
              <li key={p.id}>
                <Link
                  to={`/bayi-risk/${encodeURIComponent(p.code)}#limit`}
                  className="flex min-h-11 items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2 text-[12.5px] transition-transform duration-150 ease-out active:scale-[0.98]"
                >
                  <span className="min-w-0 truncate font-bold">{p.unvan || p.code}</span>
                  <span className="shrink-0 text-canvas-muted">
                    {p.degisimAd} · <span className="font-mono font-bold tabular-nums text-canvas-ink">{fmtShort(p.onerilen)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <ShowMoreButton more={limits} noun="öneri" />
          </>
        )}
      </Block>

      <Block title="Zeki AI'ya sor" help="Genel bakış soru kutusunda açılır; cevap Logo ve CRM'den okunur.">
        <div className="flex flex-wrap gap-1.5">
          {meta.zekiQuestions.map((z) => (
            <Link
              key={z}
              to={`/genel-bakis?soru=${encodeURIComponent(z)}`}
              className="inline-flex min-h-9 items-center rounded-xl bg-canvas-violet/10 px-2.5 text-[12px] font-bold text-canvas-violet transition-transform duration-150 ease-out active:scale-[0.97]"
            >
              {z}
            </Link>
          ))}
        </div>
      </Block>
    </div>
  );
}

function DealerList({ items, showBmt, empty, k, alan }: { items: Dealer[]; showBmt: boolean; empty: string; k?: Kaynaklar; alan?: string }) {
  const [all, setAll] = useState(false);
  if (items.length === 0) return empty ? <Empty>{empty}</Empty> : null;
  const rows = all ? items : items.slice(0, 5);
  return (
    <>
      <ul className="flex flex-col gap-2">
        {rows.map((d) => (
          <DealerRow key={d.code} d={d} showBmt={showBmt} k={k} alan={alan} />
        ))}
      </ul>
      {items.length > 5 && (
        <button type="button" className={`${btnGhost} mt-2 w-full`} onClick={() => setAll(!all)}>
          {all ? 'İlk 5' : `Hepsini göster (${items.length})`}
        </button>
      )}
    </>
  );
}
