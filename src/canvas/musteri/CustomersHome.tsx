import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Block, Empty, FieldFrame, Stat } from '../field/parts';
import { fmtDay, fmtMoney, fmtPct, fmtShort } from '../field/api';
import { musteriApi, type Meta } from './api';
import { AccountRow, SubNav } from './parts';

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
        <Note tone="info">CRM'de size atanmış müşteri carisi yok. Atama CRM'deki cari sahibi (BMT) ya da ilin müşteri temsilcisi alanından gelir.</Note>
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
  const err = errText(meta.error ?? ov.error, 'Müşteri özeti açılamadı.');

  return (
    <FieldFrame
      crumb="Müşteri ilişkileri"
      title="Müşteri ilişkileri"
      lead="Carinin son 12 ay değeri, nedenleri yazılı kayıp riski ve aksiyonların sonucu. Satış Logo'nun faturalı satırından (iki yıl kopyası cari koduyla birleşir), atama ve sipariş CRM'den okunur. Portal CRM'e yazmaz."
      source={m?.run.kesim ? `Logo ${fmtDay(m.run.kesim)} tarihine kadar · CRM canlı` : 'Logo + CRM'}
      presence={m?.run.asof ? `Veri ${fmtDay(m.run.asof)}` : 'Hazırlanmadı'}
      aside={<RepPicker meta={m} value={temsilci} onChange={(v) => setParams(v ? { temsilci: v } : {}, { replace: true })} />}
    >
      <SubNav meta={m} />
      {!ENGINE_ENABLED && <Note tone="warn">ZEKİ AI bağlantısı bu derlemede tanımlı değil.</Note>}
      {err && <Note tone="err">{err}</Note>}
      {(meta.isLoading || ov.isLoading) && <Loading />}
      {m && <RunNotes meta={m} />}
      {o && m && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Aktif cari" value={o.kpi.aktif.toLocaleString('tr-TR')} help={`${o.kpi.cari.toLocaleString('tr-TR')} cari listede`} />
            <Stat label="Son 12 ay net" value={fmtShort(o.kpi.net12)} help={`Logo kesimine kadar`} />
            <Stat label="Bu yıl net" value={fmtShort(o.kpi.netYil)} help={`1 Ocak – ${fmtDay(o.kesim)}`} />
            <Stat label="Yüksek risk" value={String(o.kpi.riskli)} tone={o.kpi.riskli ? 'err' : undefined} />
            <Stat label="Kayıp" value={String(o.kpi.kayip)} tone={o.kpi.kayip ? 'warn' : undefined} help={`Olağan aralığın ${m.rules.lostMultiple} katı, en az ${m.rules.lostMinDays} gün alımsız`} />
            <Stat label="Veri sağlığı" value={o.kpi.saglik === null ? '—' : `${o.kpi.saglik.toLocaleString('tr-TR')} / 100`} help="Bulgusu olmayan etkin CRM carisi payı" />
          </div>

          <Block
            title="Bu hafta bakılacak cariler"
            help="Yüksek risk ve kayıp düzeyindeki cariler, risk × değer sırasıyla. Nedenler kuraldan; puan bileşenleri aşağıda."
            action={
              o.bakilacakToplam > o.bakilacak.length ? (
                <Link className="text-[12px] font-extrabold text-canvas-violet hover:underline" to={`/musteri-iliskileri/cariler?risk=riskli${temsilci ? `&temsilci=${temsilci}` : ''}`}>
                  Tümü ({o.bakilacakToplam})
                </Link>
              ) : undefined
            }
          >
            {o.bakilacak.length === 0 ? (
              <Empty>Yüksek risk ya da kayıp düzeyinde cari yok.</Empty>
            ) : (
              <ul className="grid grid-cols-1 gap-2 lg:grid-cols-2">
                {o.bakilacak.map((a) => (
                  <AccountRow key={a.code} a={a} showRep={m.me.canAll} />
                ))}
              </ul>
            )}
          </Block>

          <Block title="Kanallar" help="Logo özel kod 2 (kanal) başına. Aktif = son 12 ayda faturası olan cari.">
            <TableWrap>
              <table className="w-full min-w-[560px] text-[12.5px]">
                <thead>
                  <tr>
                    <th className={th}>Kanal</th>
                    <th className={`${th} text-right`}>Aktif cari</th>
                    <th className={`${th} text-right`}>Son 12 ay net</th>
                    <th className={`${th} text-right`}>Bu yıl net</th>
                    <th className={`${th} text-right`}>Yüksek risk</th>
                    <th className={`${th} text-right`}>Kayıp</th>
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
            </TableWrap>
          </Block>

          <Block title="Aksiyonların sonucu" help="Yazılan aksiyondan sonraki 30 ve 90 günde carinin yeniden alım yapıp yapmadığı (Logo; pencere dolunca ölçülür).">
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <Stat label="Aksiyon" value={String(o.aksiyon.toplam)} />
              <Stat label="30 günde alan" value={fmtPct(o.aksiyon.gun30.oran)} help={`${o.aksiyon.gun30.alan} / ${o.aksiyon.gun30.olgun} olgun`} />
              <Stat label="90 günde alan" value={fmtPct(o.aksiyon.gun90.oran)} help={`${o.aksiyon.gun90.alan} / ${o.aksiyon.gun90.olgun} olgun`} />
              <Stat label="Riskliyken yazılan, 90 gün" value={fmtPct(o.aksiyon.riskli90.oran)} help={`${o.aksiyon.riskli90.alan} / ${o.aksiyon.riskli90.olgun} olgun`} />
            </div>
          </Block>

          {seg.data && seg.data.items.length > 0 && (
            <Block title="En değerli segmentler" help={seg.data.kural}>
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {seg.data.items.slice(0, 6).map((s) => (
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
            </Block>
          )}

          <Block title="Kayıp riski nasıl hesaplanır" help="Kural puanı (0–100); model puan vermez. Süre Logo kesim tarihine göre ölçülür, donmuş veri herkesi riskli göstermez.">
            <ul className="flex flex-col gap-1 text-[12.5px]">
              {m.weights.map((w) => (
                <li key={w.key} className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
                  <span className="min-w-0">{w.label}</span>
                  <span className="shrink-0 font-mono font-bold tabular-nums">en çok {w.max}</span>
                </li>
              ))}
            </ul>
            <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
              Yüksek ≥ {m.rules.riskHigh}, orta ≥ {m.rules.riskMid}. Olağan alım aralığı carinin son 24 aydaki alım günlerinin medyanıdır; {m.rules.minPurchaseDays} günden az alımı olan cari için kanalının medyanı kullanılır. Risk puanı cariye kendiliğinden bir sonuç doğurmaz (limit ya da fiyat değişmez).
            </p>
          </Block>
        </>
      )}
    </FieldFrame>
  );
}
