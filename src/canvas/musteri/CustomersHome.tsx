import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Block, Empty, FieldFrame, Stat } from '../field/parts';
import { fmtDay, fmtMoney, fmtPct, fmtShort } from '../field/api';
import { musteriApi, type Meta } from './api';
import { AccountRow, SubNav } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { ShowMoreButton, useShowMore } from '../components/ShowMore';

/** M38 Müşteri ilişkileri — özet (ilk açılış). Kanal bazında aktif cari, son 12 ay değer, riskli cari, veri sağlığı puanı ve
 *  Logo kesim tarihi; altında «bu hafta bakılacak cariler» (risk × değer). Temsilci yalnız kendi portföyünü görür. */

export function useMusteriMeta() {
  return useQuery({ queryKey: ['musteri', 'meta'], queryFn: musteriApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
}

export function RepPicker({ meta, value, onChange }: { meta: Meta | undefined; value: string; onChange: (v: string) => void }) {
  if (!meta?.me.canAll) return null;
  return (
    <label className="flex flex-col gap-1">
      <span className={labelCls}>Temsilci</span>
      <select className={field} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Bütün temsilciler</option>
        {meta.reps.map((r) => (
          <option key={r.hesap} value={r.hesap}>
            {r.ad} ({r.cari})
          </option>
        ))}
      </select>
    </label>
  );
}

export function RunNotes({ meta }: { meta: Meta }) {
  return (
    <>
      {!meta.run.asof && <Note tone="warn">Müşteri verisi henüz hazırlanmadı: ilk gece turu koştuğunda ekran dolar (her gün 04:15).</Note>}
      {(meta.run.warnings ?? []).map((w) => (
        <Note key={w} tone="warn">
          {w}
        </Note>
      ))}
      {!meta.me.canAll && meta.run.asof && meta.me.cari === 0 && (
        <Note tone="info">CRM'de size atanmış müşteri yok. Müşteriler, CRM'deki cari sahibi ya da ilin müşteri temsilcisi alanından size bağlanır; eksikse CRM yöneticinizden atama isteyin.</Note>
      )}
    </>
  );
}

export default function CustomersHome() {
  const [params, setParams] = useSearchParams();
  const meta = useMusteriMeta();
  const m = meta.data;
  const temsilci = m?.me.canAll ? (params.get('temsilci') ?? '') : '';
  const ov = useQuery({ queryKey: ['musteri', 'overview', temsilci], queryFn: () => musteriApi.overview(temsilci), enabled: ENGINE_ENABLED && !!m?.run.asof });
  const seg = useQuery({ queryKey: ['musteri', 'segments'], queryFn: musteriApi.segments, enabled: ENGINE_ENABLED && !!m?.run.asof && !!m?.me.canAll });
  const o = ov.data;
  const segs = useShowMore(seg.data?.items, 6);
  const err = errText(meta.error ?? ov.error, 'Müşteri özeti açılamadı.');

  return (
    <FieldFrame
      crumb="Müşteri ilişkileri"
      title="Müşteri ilişkileri"
      lead="Müşterilerinizin (cari) son 12 aydaki alımını, bizden alımı bırakma (kayıp) riskini nedenleriyle ve yazdığınız aksiyonların sonucunu gösterir. Satış Logo faturalarından, atama ve sipariş CRM'den okunur; portal CRM'e yazmaz."
      source={m?.run.kesim ? `Logo ${fmtDay(m.run.kesim)} tarihine kadar · CRM canlı` : 'Logo + CRM'}
      presence={m?.run.asof ? `Veri ${fmtDay(m.run.asof)}` : 'Hazırlanmadı'}
      aside={<RepPicker meta={m} value={temsilci} onChange={(v) => setParams(v ? { temsilci: v } : {}, { replace: true })} />}
    >
      <SubNav meta={m} />
      {!ENGINE_ENABLED && <Note tone="warn">Bu ekranın veri bağlantısı kurulmamış; sayılar açılamaz. Lütfen sistem yöneticinize bildirin.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {(meta.isLoading || ov.isLoading) && <Loading />}
      {m && <RunNotes meta={m} />}
      {o && m && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Aktif cari" info={<SqlInfo k={o.kaynaklar} alan="kpi" label="Aktif cari" />} value={o.kpi.aktif.toLocaleString('tr-TR')} help={`${o.kpi.cari.toLocaleString('tr-TR')} cari listede`} explain="Son 12 ayda en az bir faturası olan müşteri (cari) sayısı. Altında listedeki bütün cariler yazar." />
            <Stat label="Son 12 ay net" info={<SqlInfo k={o.kaynaklar} alan="kpi" label="Son 12 ay net" />} value={fmtShort(o.kpi.net12)} help={`Logo kesimine kadar`} />
            <Stat label="Bu yıl net" info={<SqlInfo k={o.kaynaklar} alan="kpi" label="Bu yıl net" />} value={fmtShort(o.kpi.netYil)} help={`1 Ocak – ${fmtDay(o.kesim)}`} />
            <Stat label="Yüksek risk" info={<SqlInfo k={o.kaynaklar} alan="kpi" label="Yüksek risk" />} value={String(o.kpi.riskli)} tone={o.kpi.riskli ? 'err' : undefined} explain={`Kayıp riski puanı ${m.rules.riskHigh} ve üstü olan cariler: alımları olağan düzeninden sapmış, bizden almayı bırakabilecek müşteriler. Puanın nasıl hesaplandığı sayfanın altında yazar.`} />
            <Stat label="Kayıp" info={<SqlInfo k={o.kaynaklar} alan="kpi" label="Kayıp" />} value={String(o.kpi.kayip)} tone={o.kpi.kayip ? 'warn' : undefined} help={`Olağan aralığın ${m.rules.lostMultiple} katı, en az ${m.rules.lostMinDays} gün alımsız`} explain="Her zamanki alım aralığının çok üstünde süredir alım yapmayan, fiilen kaybedilmiş sayılan cariler." />
            <Stat label="Veri sağlığı" info={<SqlInfo k={o.kaynaklar} alan="kpi.saglik" label="Veri sağlığı puanı" />} value={o.kpi.saglik === null ? '—' : `${o.kpi.saglik.toLocaleString('tr-TR')} / 100`} help="Bulgusu olmayan etkin CRM carisi payı" explain="CRM'deki cari kayıtlarının ne kadarının temiz olduğu (Logo bağı, sahibi, tekrar kaydı gibi bir sorunu olmayanların payı). Ayrıntısı «Veri sağlığı» sekmesindedir." />
          </div>

          <Block
            title="Bu hafta bakılacak cariler"
            help="Yüksek risk ve kayıp düzeyindeki cariler; riski yüksek ve cirosu büyük olan önde. Kartın solundaki sayı kayıp riski puanıdır (0–100), altındaki etiketler nedenleridir."
            action={
              o.bakilacakToplam > o.bakilacak.length ? (
                <span className="flex items-center gap-1">
                <SqlInfo k={o.kaynaklar} alan="bakilacakToplam" label="Bakılacak cariler" />
                <Link className="text-[12px] font-extrabold text-canvas-violet hover:underline" to={`/musteri-iliskileri/cariler?risk=riskli${temsilci ? `&temsilci=${temsilci}` : ''}`}>
                  Tümü ({o.bakilacakToplam})
                </Link>
                </span>
              ) : (
                <SqlInfo k={o.kaynaklar} alan="bakilacakToplam" label="Bakılacak cariler" />
              )
            }
          >
            {o.bakilacak.length === 0 ? (
              <Empty title="Bu hafta bakılacak cari yok">Yüksek risk ya da kayıp düzeyinde cari bulunmuyor.</Empty>
            ) : (
              <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
                {o.bakilacak.map((a) => (
                  <AccountRow key={a.code} a={a} showRep={m.me.canAll} k={o.kaynaklar} alan="bakilacak[]" />
                ))}
              </ul>
            )}
          </Block>

          <Block title="Kanallar" help="Logo'daki satış kanalı başına. Aktif cari: son 12 ayda faturası olan cari. Kanal adına dokununca o kanalın carileri listelenir.">
            <div className="overflow-x-auto rounded-2xl border border-slate-100 bg-white/80">
              <table className="w-full min-w-[560px] text-[12.5px]">
                <thead>
                  <tr>
                    <th className={th}>Kanal</th>
                    <th className={`${th} text-right`}><InfoLabel k={o.kaynaklar} alan="kanallar" label="Aktif cari">Aktif cari</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={o.kaynaklar} alan="kanallar" label="Son 12 ay net">Son 12 ay net</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={o.kaynaklar} alan="kanallar" label="Bu yıl net">Bu yıl net</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={o.kaynaklar} alan="kanallar" label="Yüksek risk">Yüksek risk</InfoLabel></th>
                    <th className={`${th} text-right`}><InfoLabel k={o.kaynaklar} alan="kanallar" label="Kayıp">Kayıp</InfoLabel></th>
                  </tr>
                </thead>
                <tbody>
                  {o.kanallar.map((k) => (
                    <tr key={k.kanal} className="border-t border-slate-100">
                      <td className={td}>
                        <Link className="font-bold hover:underline" to={`/musteri-iliskileri/cariler?kanal=${encodeURIComponent(k.kanal)}${temsilci ? `&temsilci=${temsilci}` : ''}`}>
                          {k.kanal}
                        </Link>
                      </td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{k.aktif.toLocaleString('tr-TR')}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(k.net12)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(k.netYil)}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{k.riskli}</td>
                      <td className={`${td} text-right font-mono tabular-nums`}>{k.kayip}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Block>

          <Block title="Aksiyonların sonucu" action={<SqlInfo k={o.kaynaklar} alan="aksiyon" label="Aksiyon etkisi" />} help="Yazılan aksiyondan sonraki 30 ve 90 günde carinin yeniden alım yapıp yapmadığı (Logo; pencere dolunca ölçülür).">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Aksiyon" value={String(o.aksiyon.toplam)} />
              <Stat label="30 günde alan" value={fmtPct(o.aksiyon.gun30.oran)} help={`${o.aksiyon.gun30.alan} / ${o.aksiyon.gun30.olgun} olgun`} />
              <Stat label="90 günde alan" value={fmtPct(o.aksiyon.gun90.oran)} help={`${o.aksiyon.gun90.alan} / ${o.aksiyon.gun90.olgun} olgun`} />
              <Stat label="Riskliyken yazılan, 90 gün" value={fmtPct(o.aksiyon.riskli90.oran)} help={`${o.aksiyon.riskli90.alan} / ${o.aksiyon.riskli90.olgun} olgun`} />
            </div>
          </Block>

          {seg.data && seg.data.items.length > 0 && (
            <Block title="En değerli segmentler" help={seg.data.kural} action={<SqlInfo k={seg.data.kaynaklar} alan="items" label="Segmentler" />}>
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {segs.shown.map((s) => (
                  <li key={s.id}>
                    <Link
                      to={`/musteri-iliskileri/cariler?segment=${encodeURIComponent(s.ad)}`}
                      className="flex min-h-14 flex-col rounded-2xl border border-slate-100 bg-white/85 p-3 transition-transform duration-150 ease-out active:scale-[0.98]"
                    >
                      <span className="truncate text-[13px] font-extrabold">{s.ad}</span>
                      <span className="mt-0.5 text-[11.5px] text-canvas-muted">
                        {s.boyut} cari · {fmtShort(s.deger)} · payı {fmtPct(s.pay)}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              <ShowMoreButton more={segs} noun="segment" />
            </Block>
          )}

          <Block title="Kayıp riski nasıl hesaplanır" help="Puan (0–100) sabit bir kuralla hesaplanır; Zeki AI puan vermez. Süreler Logo verisinin bittiği güne göre ölçülür, bu yüzden veri gecikse de herkes riskli görünmez.">
            <ul className="flex flex-col gap-1 text-[12.5px]">
              {m.weights.map((w) => (
                <li key={w.key} className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
                  <span className="min-w-0">{w.label}</span>
                  <span className="shrink-0 font-mono font-bold tabular-nums">en çok {w.max}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
              Yüksek ≥ {m.rules.riskHigh}, orta ≥ {m.rules.riskMid}. Olağan alım aralığı, carinin son 24 aydaki alımları arasındaki sürenin ortancasıdır; {m.rules.minPurchaseDays} günden az alımı olan cari için kanalının ortancası kullanılır. Risk puanı cariye kendiliğinden bir sonuç doğurmaz (limit ya da fiyat değişmez).
            </p>
          </Block>
        </>
      )}
    </FieldFrame>
  );
}
