import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../../admin/ui';
import { Kpi, KpiRow, Panel } from '../../editorial/kit';
import { fmtDay, fmtInt, fmtPct } from '../../budget/api';
import { BookCell } from '../platformKit';
import { trendyolApi } from './api';
import { TrendyolData, TrendyolFrame, tl, useTrendyolMeta } from './parts';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint } from '../../components/Explain';
import { ShowMoreButton, useShowMore } from '../../components/ShowMore';

/** En sık üç iade nedeni; gerisi sayısıyla yazılır (sessiz kesme yok). */
function classesText(siniflar: Record<string, { talep: number }>): string {
  const all = Object.entries(siniflar);
  if (!all.length) return '—';
  const head = all.slice(0, 3).map(([k, v]) => `${k} ${v.talep}`).join(' · ');
  return all.length > 3 ? `${head} · +${all.length - 3} neden daha` : head;
}

export default function TrendyolWeekly() {
  const meta = useTrendyolMeta();
  const m = meta.data;
  const [bitis, setBitis] = useState('');
  const [ozet, setOzet] = useState(false);
  const r = useQuery({ queryKey: ['trendyol', 'weekly', bitis, ozet], queryFn: () => trendyolApi.weekly(bitis || undefined, ozet), enabled: ENGINE_ENABLED });
  const d = r.data;
  const orders = useShowMore(d?.siparis.kitaplar, 20);
  const returns = useShowMore(d?.iade.kitaplar, 20);
  return (
    <TrendyolFrame
      title="Haftalık rapor"
      lead="Trendyol mağazasının yedi günlük özeti: kaç paket gitti, ne iade geldi, hangi sorular ve yorumlar bekliyor. «Hafta sonu» boşsa yüklenen dosyalardaki en son gün esas alınır."
      aside={
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Hafta sonu (haftanın son günü)</span>
          <input type="date" className={field} value={bitis} onChange={(e) => setBitis(e.target.value)} />
        </label>
      }
    >
      <TrendyolData meta={m} />
      {r.error && <Note tone="err">{errText(r.error, 'Rapor açılamadı.')}</Note>}
      {r.isLoading && <Loading />}
      {d && (
        <>
          <p className="px-1 text-[12.5px] font-semibold text-canvas-muted">{fmtDay(d.bas)} – {fmtDay(d.bit)}</p>
          <KpiRow>
            <Kpi label="Paket" value={fmtInt(d.siparis.paket)} help={`${fmtInt(d.siparis.adet)} adet · ${tl(d.siparis.tutar)}`}
            info={<SqlInfo k={d?.kaynaklar} alan="siparis" label="Paket" />} />
            <Kpi label="İade talebi" value={fmtInt(d.iade.talep)} help={classesText(d.iade.siniflar)}
            explain="Bu yedi günde açılan iade talepleri. Altta en sık üç iade nedeni yazar; bütün nedenler «Sipariş ve iade» sekmesindedir."
            info={<SqlInfo k={d?.kaynaklar} alan="iade" label="İade talebi" />} />
            <Kpi label="Cevapsız soru" value={fmtInt(d.soru.cevapsiz)} help={`${fmtInt(d.soru.geciken)} geciken (bugün itibarıyla)`}
            explain="Cevapsız ve geciken soru sayıları seçilen haftaya değil, bugüne göredir."
            info={<SqlInfo k={d?.kaynaklar} alan="soru" label="Cevapsız soru" />} />
            <Kpi label="Düşük puanlı yorum" value={fmtInt(d.yorum.dusuk)} help={`Bu hafta ${fmtInt(d.yorum.hafta)} yorum · genel ortalama ${d.yorum.ortalama ?? '—'}`}
            info={<SqlInfo k={d?.kaynaklar} alan="yorum" label="Düşük puanlı yorum" />} />
          </KpiRow>
          <Panel>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Zeki AI özeti <SqlInfo k={d?.kaynaklar} alan="siparis" label="Zeki AI özeti" /></h2>
              {!ozet && <button type="button" className={btnGhost} onClick={() => setOzet(true)}><Sparkles aria-hidden className="h-4 w-4" />Özet yazdır</button>}
            </div>
            {ozet ? (r.isFetching ? <Loading /> : <p className="mt-1 text-[13px] leading-relaxed">{d.ozet ?? 'Özet şu an yazılamadı; biraz sonra sayfayı yenileyip yeniden deneyin.'}</p>) : <p className="text-[12px] text-canvas-muted">İsterseniz Zeki AI bu haftayı birkaç cümleyle özetler; rakamlar yukarıdaki tablolardan gelir. Yazması biraz sürebilir.</p>}
          </Panel>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 lg:gap-4">
            <Panel>
              <h2 className="flex items-center gap-1 mb-2 text-[15px] font-extrabold">En çok sipariş alan kitaplar <SqlInfo k={d?.kaynaklar} alan="siparis" label="En çok sipariş alan kitaplar" /></h2>
              {!d.siparis.kitaplar.length ? <EmptyHint title="Bu hafta sipariş yok" why="Seçilen yedi günde sipariş dosyasında satır bulunamadı. Güncel sipariş dosyasını yükleyin ya da başka bir hafta seçin." /> : (
              <>
              <TableWrap>
                <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="siparis">Adet</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="siparis">Tutar</InfoLabel></th></tr></thead>
                <tbody>
                  {orders.shown.map((b) => (
                    <tr key={b.barkod} className="border-t border-slate-100">
                      <td className={td}><BookCell name={b.ad} code={b.stokKodu} sub={b.barkod} /></td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.adet)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{tl(b.tutar)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              <ShowMoreButton more={orders} noun="kitap" />
              </>
              )}
            </Panel>
            <Panel>
              <h2 className="flex items-center gap-1 mb-2 text-[15px] font-extrabold">En çok iade edilen kitaplar <SqlInfo k={d?.kaynaklar} alan="iade" label="En çok iade edilen kitaplar" /></h2>
              {!d.iade.kitaplar.length ? <EmptyHint title="Bu hafta iade yok" why="Seçilen yedi günde iade talebi bulunamadı." /> : (
              <>
              <TableWrap>
                <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="siparis">İade</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={d?.kaynaklar} alan="siparis">Oran</InfoLabel></th></tr></thead>
                <tbody>
                  {returns.shown.map((b) => (
                    <tr key={b.barkod} className="border-t border-slate-100">
                      <td className={td}><BookCell name={b.ad} code={b.stokKodu} sub={b.barkod} /></td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.iadeAdet)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(b.oran)}</td>
                    </tr>
                  ))}
                </tbody>
              </TableWrap>
              <ShowMoreButton more={returns} noun="kitap" />
              </>
              )}
            </Panel>
          </div>
        </>
      )}
    </TrendyolFrame>
  );
}
