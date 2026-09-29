import { Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Explain } from '../components/Explain';
import { Loading, Note, TableWrap, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtDay, fmtInt, fmtKg, fmtMoney, fmtPct, fmtUnit, supplyApi } from './api';
import { ErrorNote, SupplyFrame, Warnings, cellTone, useSupplyMeta } from './parts';

/** M52 Tedarik özeti (/tedarik): önümüzdeki aylar × matbaa yükü, eşik aşımı, bu ay kağıt ihtiyacı, 30 gün ödeme,
 *  faturası görünmeyen baskı, birim maliyet eğilimi, kartı açılmamış baskı ihtiyacı ve gelecek depo girişleri. */
export default function SupplyHome() {
  const nav = useNavigate();
  const meta = useSupplyMeta();
  const ov = useQuery({ queryKey: ['supply', 'overview'], queryFn: supplyApi.overview, enabled: ENGINE_ENABLED });
  const inc = useQuery({ queryKey: ['supply', 'incoming'], queryFn: () => supplyApi.incoming(6), enabled: ENGINE_ENABLED });
  const o = ov.data;
  const me = meta.data?.me;

  return (
    <SupplyFrame
      title="Tedarik ve baskı"
      lead="Önümüzdeki aylarda hangi matbaaya ne kadar baskı işi düştüğü, ne kadar kağıt gerektiği, matbaa ve kağıtçılara ne kadar ödeme yapılacağı ve adet başı baskı bedelinin gidişi tek bakışta. Baskı kartları Üretim yönetiminden okunur; burada kart açılmaz, matbaa atanmaz, CRM'e ve matbaaya bir şey gönderilmez."
      source={o?.logo ? `Logo ${o.logo.yil} · veri sonu ${fmtDay(o.logo.veriSonu)}` : undefined}
    >
      <ErrorNote error={ov.error} fallback="Tedarik özeti okunamadı." />
      <Warnings items={o?.uyarilar} />
      <KpiRow>
        <Kpi
          label="Açık baskı işi"
          value={o ? fmtInt(o.yuk.acikIs) : '—'}
          help={o ? `${fmtInt(o.yuk.acikAdet)} adet · planı geçmiş ve tarihsiz dahil` : 'Baskıdan henüz çıkmamış'}
          onClick={() => nav('/tedarik/yuk')}
          explain="Üretim kartı açık, henüz baskıdan çıkmamış ya da depoya girmemiş (iptal edilmemiş) baskı işleri ve toplam adedi. Plan tarihi geçmiş ya da tarihi olmayan kartlar da sayılır."
          info={<SqlInfo k={o?.kaynaklar} alan="yuk" label="Açık baskı işi ve adet" />}
        />
        <Kpi
          label="Eşik aşımı"
          value={o ? fmtInt(o.cakisma) : '—'}
          help={o ? `${fmtInt(o.cakismaAsim)} tanesi kapasite aşımı; kalanı referansın üstü` : 'Ay × matbaa'}
          active={!!o && o.cakisma > 0}
          onClick={() => nav('/tedarik/yuk?sekme=cakisma')}
          explain="Bir matbaaya bir ayda düşen işin, o matbaa için girilen aylık kapasiteyi (kırmızı) ya da kapasite girilmemişse son 12 ayın en yoğun ayını (amber, yalnız referans) aştığı ay × matbaa sayısı."
          info={<SqlInfo k={o?.kaynaklar} alan="cakisma" label="Eşik aşımı" />}
        />
        <Kpi
          label="Bu ay kağıt"
          value={o ? fmtKg(o.kagit.buAyKg) : '—'}
          help={o ? `${o.kagit.olcu === 'brut' ? 'Brüt (fire dahil)' : 'Net'}; ${fmtInt(o.kagit.kapsam.bos)} kartta kağıt bilgisi yok` : 'Açık kartlardan'}
          onClick={() => nav('/tedarik/kagit')}
          explain="Bu ay baskıya girecek açık kartların CRM'deki kağıt bilgisinden toplanan kağıt ağırlığı. «Brüt» baskı firesi dahil demektir. Kağıt bilgisi girilmemiş kartlar sayılamaz."
          info={<SqlInfo k={o?.kaynaklar} alan="kagit" label="Bu ay kağıt" />}
        />
        {me?.canDebt && o?.odeme30 ? (
          <Kpi
            label="30 gün ödeme"
            value={fmtMoney(o.odeme30.toplam)}
            help={`Matbaa ve kağıtçı · vadesi geçmiş ${fmtMoney(o.odeme30.vadesiGecmis)} (tahmini)`}
            onClick={() => nav('/tedarik/tedarikciler?sekme=odeme')}
            explain="Önümüzdeki 30 günde vadesi gelen matbaa ve kağıtçı ödemeleri, Logo ödeme planından. Logo'da hangi ödemenin hangi faturayı kapattığı tutulmadığından, ödemeler en eski faturadan başlayarak düşülür; rakam tahminidir."
            info={<SqlInfo k={o.kaynaklar} alan="odeme30" label="30 gün ödeme" />}
          />
        ) : (
          <Kpi label="Bekleyen öneri" value={o ? fmtInt(o.oneri) : '—'} help="Yük dengeleme ve kağıt alımı" onClick={() => nav('/tedarik/yuk')}
            explain="Karar bekleyen öneriler: yoğun aydaki işi başka aya ya da matbaaya kaydırma ve zamanında kağıt alma önerileri."
            info={<SqlInfo k={o?.kaynaklar} alan="oneri" label="Bekleyen öneri" />} />
        )}
      </KpiRow>

      {ov.isLoading && <Loading />}
      {o && (
        <Panel>
          <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
            <h2 className="text-[13px] font-extrabold"><InfoLabel k={o.kaynaklar} alan="yuk.satirlar[].hucreler" label="Baskı yükü ve toplam">Baskı yükü — ay × matbaa (adet)</InfoLabel></h2>
            <Link to="/tedarik/yuk" className="text-[12px] font-bold text-canvas-violet hover:underline">
              Ayrıntı ve öneriler
            </Link>
          </div>
          <div className="mt-3">
            <TableWrap>
              <thead>
                <tr className="border-b border-slate-100">
                  <th className={th}>Matbaa</th>
                  {o.yuk.aylar.map((m) => (
                    <th key={m.key} className={`${th} text-right`}>
                      {m.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {o.yuk.satirlar.map((r) => (
                  <tr key={r.matbaa} className="border-b border-slate-50 last:border-0">
                    <td className={`${td} font-bold`}>{r.matbaa}</td>
                    {o.yuk.aylar.map((m) => {
                      const c = r.hucreler[m.key];
                      return (
                        <td key={m.key} className={`${td} text-right`}>
                          <span className={`inline-block min-w-[64px] rounded-lg px-2 py-1 font-mono text-[12px] tabular-nums ${cellTone(c.durum, c.oran)}`}>
                            {c.jobs ? fmtInt(c.adet) : '·'}
                          </span>
                        </td>
                      );
                    })}
                  </tr>
                ))}
                <tr className="bg-slate-50/80">
                  <td className={`${td} font-extrabold`}><InfoLabel k={o.kaynaklar} alan="yuk.toplam" label="Ay toplamı ve geçen yıl">Toplam</InfoLabel></td>
                  {o.yuk.aylar.map((m) => (
                    <td key={m.key} className={`${td} text-right font-mono font-bold tabular-nums`}>
                      {fmtInt(o.yuk.toplam[m.key]?.adet)}
                      {o.yuk.toplam[m.key]?.gecenYil && (
                        <div className="text-[10.5px] font-semibold text-canvas-muted">geçen yıl {fmtInt(o.yuk.toplam[m.key]?.gecenYil?.adet)}</div>
                      )}
                    </td>
                  ))}
                </tr>
              </tbody>
            </TableWrap>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
            <span className="inline-flex items-center gap-1"><span aria-hidden className="h-3 w-3 rounded bg-red-100 ring-1 ring-red-200" />Kapasite aşıldı</span>
            <span className="inline-flex items-center gap-1"><span aria-hidden className="h-3 w-3 rounded bg-amber-100 ring-1 ring-amber-200" />Son 12 ayın en yoğun ayı aşıldı (kapasite girilmemiş)</span>
            <span className="inline-flex items-center gap-1"><span aria-hidden className="h-3 w-3 rounded bg-canvas-violet/25" />Mor koyulaştıkça yük artar</span>
            <span>«·» o ay iş yok</span>
          </div>
        </Panel>
      )}

      <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
        {o && (
          <Panel>
            <h2 className="px-1 text-[13px] font-extrabold"><InfoLabel k={o.kaynaklar} alan="plan">Kartı açılmamış baskı ihtiyacı</InfoLabel></h2>
            <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
              Yakında basılması gerekecek ama henüz üretim kartı açılmamış kitaplar: baskı önerisi raporunda {o.plan.seviyeler.join(' ve ')} görünenler ile ilk baskı kararı onaylanmış yeni kitaplar. Bu yük henüz bir aya ve matbaaya dağıtılmadığı için yukarıdaki tabloda yoktur.
            </p>
            {o.plan.hata && <div className="mt-2"><Note tone="warn">{o.plan.hata}</Note></div>}
            <div className="mt-3 grid grid-cols-2 gap-2">
              <div className="rounded-xl bg-white/80 px-3 py-2">
                <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Baskı önerisi</div>
                <div className="font-mono text-[18px] font-bold tabular-nums">{fmtInt(o.plan.baskiOneri.length)} kitap</div>
                <div className="text-[11px] text-canvas-muted">önerilen {fmtInt(o.plan.baskiOneriAdet)} adet</div>
              </div>
              <div className="rounded-xl bg-white/80 px-3 py-2">
                <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">Onaylı ilk baskı</div>
                <div className="font-mono text-[18px] font-bold tabular-nums">{fmtInt(o.plan.ilkBaski.length)} kitap</div>
                <div className="text-[11px] text-canvas-muted">{fmtInt(o.plan.ilkBaskiAdet)} adet</div>
              </div>
            </div>
            {!o.plan.raporVar && !o.plan.hata && (
              <div className="mt-2"><Note tone="info">Baskı önerisi raporunun verisi henüz hazır değil.</Note></div>
            )}
          </Panel>
        )}
        {inc.data && (
          <Panel>
            <h2 className="px-1 text-[13px] font-extrabold"><InfoLabel k={inc.data.kaynaklar} alan="gecmis" label="Depo girişi">Depo girişi — gerçekleşen ve planlanan (adet)</InfoLabel></h2>
            <p className="mt-1 px-1 text-[11.5px] leading-snug text-canvas-muted">
              Gri kutular son 6 ayda Logo'da üretimden depoya giren adet; mor kutular açık kartların önümüzdeki aylar için planlanan depo girişi.{' '}
              {inc.data.depo?.kapasiteAdet
                ? `Depo kapasitesi ${fmtInt(inc.data.depo.kapasiteAdet)} adet (${inc.data.depo.kaynak}).`
                : 'Depo kapasitesi tanımlı değil; depo ve stok modülünde girilince karşılaştırılır.'}
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {inc.data.gecmis.slice(-6).map((m) => (
                <div key={m.ay} className="min-w-[88px] flex-1 rounded-xl bg-slate-50 px-2.5 py-1.5">
                  <div className="text-[10.5px] font-bold uppercase text-canvas-muted">{m.ayAdi}</div>
                  <div className="font-mono text-[13px] font-bold tabular-nums">{fmtInt(m.adet)}</div>
                </div>
              ))}
              {inc.data.plan.map((m) => (
                <div key={m.ay} className="min-w-[88px] flex-1 rounded-xl bg-canvas-violet/10 px-2.5 py-1.5">
                  <div className="text-[10.5px] font-bold uppercase text-canvas-violet">{m.ayAdi} · plan</div>
                  <div className="font-mono text-[13px] font-bold tabular-nums">{fmtInt(m.adet)}</div>
                </div>
              ))}
            </div>
            {inc.data.planiGecmis.is > 0 && (
              <p className="mt-2 px-1 text-[11.5px] text-canvas-muted">
                Planı geçmiş ya da tarihsiz {fmtInt(inc.data.planiGecmis.is)} kart ({fmtInt(inc.data.planiGecmis.adet)} adet) ayrıca bekliyor.
              </p>
            )}
          </Panel>
        )}
        {me?.canDebt && o?.faturasiz && (
          <Panel>
            <h2 className="px-1 text-[13px] font-extrabold"><InfoLabel k={o.kaynaklar} alan="faturasiz">Fatura eşleşmesi</InfoLabel></h2>
            <p className="mt-1 px-1 text-[12.5px] leading-snug">
              Depoya girmiş ama baskı faturası görünmeyen <b>{fmtInt(o.faturasiz.kart)}</b> kart; hiçbir karta bağlanmayan{' '}
              <b>{fmtInt(o.faturasiz.fatura)}</b> baskı faturası satırı.{' '}
              <Link to="/tedarik/tedarikciler?sekme=fatura" className="font-bold text-canvas-violet hover:underline">
                Listeyi aç
              </Link>
            </p>
          </Panel>
        )}
        {me?.canCost && o?.maliyet && (
          <Panel>
            <div className="flex flex-wrap items-baseline justify-between gap-2 px-1">
              <h2 className="flex items-center gap-1 text-[13px] font-extrabold">
                <InfoLabel k={o.kaynaklar} alan="maliyet">Adet başı baskı bedeli</InfoLabel>
                <Explain label="Adet başı baskı bedeli">Matbaa faturasındaki baskı tutarının basılan adede bölümü, aylara göre (adetle ağırlıklı). Çizgi yalnız gidişi gösterir; değerler «Kırılımlar» sayfasındadır.</Explain>
              </h2>
              <Link to="/tedarik/maliyet" className="text-[12px] font-bold text-canvas-violet hover:underline">
                Kırılımlar
              </Link>
            </div>
            <Spark aylar={o.maliyet.aylar.map((m) => m.key)} seri={o.maliyet.seri} />
            <p className="mt-1 px-1 text-[12px] text-canvas-muted">
              Son yarı {fmtUnit(o.maliyet.sonDonem)} · önceki yarı {fmtUnit(o.maliyet.oncekiDonem)} · değişim {fmtPct(o.maliyet.egilim, true)}
            </p>
          </Panel>
        )}
      </div>
    </SupplyFrame>
  );
}

/** Aylık ağırlıklı birim fiyat kıvılcımı (ölçeksiz, yalnız eğilim). Boş ay atlanır. */
function Spark({ aylar, seri }: { aylar: string[]; seri: Record<string, { agirlikliBirim: number }> }) {
  const pts = aylar.map((m, i) => ({ i, v: seri[m]?.agirlikliBirim })).filter((p): p is { i: number; v: number } => typeof p.v === 'number');
  if (pts.length < 2) return <p className="mt-2 px-1 text-[12px] text-canvas-muted">Eğilim için yeterli ay yok.</p>;
  const lo = Math.min(...pts.map((p) => p.v));
  const hi = Math.max(...pts.map((p) => p.v));
  const w = 300;
  const h = 56;
  const x = (i: number) => (i / Math.max(1, aylar.length - 1)) * (w - 8) + 4;
  const y = (v: number) => (hi === lo ? h / 2 : h - 6 - ((v - lo) / (hi - lo)) * (h - 12));
  const d = pts.map((p, k) => `${k ? 'L' : 'M'}${x(p.i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-2 h-14 w-full" role="img" aria-label="Aylık adet başı baskı bedeli eğilimi">
      <path d={d} fill="none" stroke="currentColor" strokeWidth={2} className="text-canvas-violet" />
      {pts.map((p) => (
        <circle key={p.i} cx={x(p.i)} cy={y(p.v)} r={2.5} className="fill-canvas-violet" />
      ))}
    </svg>
  );
}
