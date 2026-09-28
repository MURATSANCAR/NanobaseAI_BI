import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnPrimary, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtDay, fmtInt, fmtMoney, fmtPct, fmtShort } from '../budget/api';
import { channelsApi } from './api';
import { ChannelsFrame, DataBar, PeriodPicker, signedPct, useChannelsMeta, usePeriod } from './parts';

/** M42 D2C büyüme (/kanallar/d2c): timas.com.tr'nin payı, sitede pazar yerlerine göre oransal güçlü kitaplar, site
 * müşterisi özeti (site sipariş verisi bağlıysa) ve D2C'ye özel set önerisi (taslak; hiçbir yere gönderilmez). */

const STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'err' | 'muted' | 'violet' }> = {
  taslak: { label: 'Karar bekliyor', tone: 'warn' },
  onayli: { label: 'Onaylandı', tone: 'ok' },
  red: { label: 'Reddedildi', tone: 'err' },
};

export default function D2CGrowth() {
  const qc = useQueryClient();
  const meta = useChannelsMeta();
  const m = meta.data;
  const { yil, ay, set } = usePeriod(m);
  const [pick, setPick] = useState<Set<string>>(new Set());
  const q = useQuery({
    queryKey: ['channels', 'd2c', yil, ay],
    queryFn: () => channelsApi.d2c({ yil, ay }),
    enabled: ENGINE_ENABLED && !!m && !!yil && !!m.years.length,
  });
  const make = useMutation({
    mutationFn: () => channelsApi.suggestSet([...pick], { yil, ay }),
    onSuccess: () => {
      setPick(new Set());
      qc.invalidateQueries({ queryKey: ['channels', 'd2c'] });
      qc.invalidateQueries({ queryKey: ['channels', 'suggestions'] });
      toast.success('D2C set önerisi taslak olarak kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Öneri oluşturulamadı.') ?? ''),
  });
  const d = q.data;
  const s = d?.site;
  const toggle = (code: string) =>
    setPick((cur) => {
      const n = new Set(cur);
      if (n.has(code)) n.delete(code);
      else n.add(code);
      return n;
    });
  return (
    <ChannelsFrame
      title="D2C büyüme"
      lead="timas.com.tr'nin e-ticaret ve şirket içindeki payı, sitede pazar yerlerine göre oransal olarak daha iyi satan kitaplar ve D2C'ye özel set önerisi. Site fiyat savaşı değil müşteri ilişkisi kanalıdır."
      aside={<PeriodPicker meta={m} yil={yil} ay={ay} onChange={set} />}
    >
      <DataBar meta={m} yil={yil} />
      {q.error && <Note tone="err">{errText(q.error, 'D2C görünümü açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <>
          {!d.eslendi && (
            <Note tone="warn">
              {d.not} <Link to="/kanallar/eslesme" className="font-bold underline">Cari eşleme</Link> ekranında sitenin carisini ya da bireysel müşterilerin kanal kodunu timas.com.tr'ye bağlayın.
            </Note>
          )}
          <KpiRow>
            <Kpi label="D2C net ciro" value={`${fmtShort(d.d2c?.donem.netCiro ?? 0)} ₺`} help={`Geçen yıla göre ${signedPct(d.d2c?.degisim ?? null)} · Logo faturalı satır`} />
            <Kpi label="E-ticaret içindeki pay" value={fmtPct(d.d2c?.payEticaret ?? null)} help={`E-ticaret ${fmtShort(d.toplam.eticaret.netCiro)} ₺`} />
            <Kpi label="Şirket içindeki pay" value={fmtPct(d.d2c?.paySirket ?? null)} help={`Şirket ${fmtShort(d.toplam.sirket.netCiro)} ₺`} />
            <Kpi label="Adette D2C payı" value={fmtPct(d.genelD2cPay ?? null)} help="Site ÷ (site + pazar yerleri), net adet" />
          </KpiRow>

          <Panel>
            <h2 className="text-[15px] font-extrabold">Site müşterisi</h2>
            {!s?.bagli ? (
              <p className="mt-1 text-[12px] text-canvas-muted">{s?.neden ?? 'Site sipariş verisi bağlı değil.'} Bağlanınca tekrar alım oranı, müşteri başına ciro ve sepet ortalaması burada görünür (müşteri kimliği anahtarlıdır, kişisel alan okunmaz).</p>
            ) : (
              <>
                <div className="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-5">
                  {[
                    ['Sipariş', fmtInt(s.siparis ?? 0)],
                    ['Site cirosu', `${fmtShort(s.ciro ?? 0)} ₺`],
                    ['Müşteri', fmtInt(s.musteri ?? 0)],
                    ['Tekrar alan', fmtPct(s.tekrarOrani ?? null)],
                    ['Müşteri başına', fmtMoney(s.musteriBasinaCiro ?? null)],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl bg-white/70 px-3 py-2">
                      <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{k}</div>
                      <div className="font-mono text-[18px] font-bold tabular-nums">{v}</div>
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-[11.5px] text-canvas-muted">{s.not}</p>
              </>
            )}
          </Panel>

          {d.eslendi && (
            <Panel>
              <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
                <div>
                  <h2 className="text-[15px] font-extrabold">Sitede oransal güçlü kitaplar</h2>
                  <p className="text-[12px] text-canvas-muted">
                    Kitabın site payı, bütün kitaplardaki site payının en az {String(d.esik.indeks).replace('.', ',')} katı ve sitede en az {fmtInt(d.esik.minAdet)} net adet (Yönetim ayarı).
                  </p>
                </div>
                {m?.me.canSuggest && (
                  <button type="button" className={btnPrimary} onClick={() => make.mutate()} disabled={make.isPending || !d.kitaplar.length}>
                    {make.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                    {pick.size ? `${pick.size} kitapla set önerisi` : 'İlk 5 kitapla set önerisi'}
                  </button>
                )}
              </div>
              {!d.kitaplar.length ? <Note tone="info">Eşiği geçen kitap yok.</Note> : (
                <TableWrap>
                  <thead>
                    <tr>
                      {m?.me.canSuggest && <th className={th}><span className="sr-only">Seç</span></th>}
                      <th className={th}>Kitap</th>
                      <th className={`${th} text-right`}>Site net adet</th>
                      <th className={`${th} text-right`}>Pazar yeri net adet</th>
                      <th className={`${th} text-right`}>Site payı</th>
                      <th className={`${th} text-right`}>Genel payın katı</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.kitaplar.map((b) => (
                      <tr key={b.stokKodu} className="border-t border-slate-100">
                        {m?.me.canSuggest && (
                          <td className={td}>
                            <input type="checkbox" className="h-5 w-5 accent-canvas-violet" checked={pick.has(b.stokKodu)} onChange={() => toggle(b.stokKodu)} aria-label={`${b.ad || b.stokKodu} seç`} />
                          </td>
                        )}
                        <td className={td}><div className="font-semibold">{b.ad || b.stokKodu}</div><div className="font-mono text-[11px] text-canvas-muted">{b.stokKodu}</div></td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.d2cAdet)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.pazarYeriAdet)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(b.d2cPay)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{b.indeks.toLocaleString('tr-TR', { maximumFractionDigits: 1 })}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              )}
            </Panel>
          )}

          {!!d.oneriler?.length && (
            <Panel>
              <h2 className="text-[15px] font-extrabold">D2C önerileri</h2>
              <p className="mb-2 text-[12px] text-canvas-muted">Karar Kanal karnesi ekranında verilir; onay portal kaydıdır, siteye gönderilmez.</p>
              <ul className="flex flex-col gap-2">
                {d.oneriler.map((o) => (
                  <li key={o.id} className="rounded-xl bg-white/70 px-3 py-2">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <Pill tone={STATUS[o.durum]?.tone ?? 'muted'}>{STATUS[o.durum]?.label ?? o.durum}</Pill>
                      <span className="text-[13px] font-bold">{o.baslik}</span>
                    </div>
                    <div className="text-[11.5px] text-canvas-muted">{o.olusturan} · {fmtDay(o.olusturma)}{o.kararVeren && ` · ${o.kararVeren} karar verdi${o.kararNotu ? `: ${o.kararNotu}` : ''}`}</div>
                    {typeof o.payload.hesap === 'string' && <p className="mt-1 text-[12px] leading-snug">{o.payload.hesap}</p>}
                    {o.gerekce && <p className="mt-1 text-[12px] leading-snug text-canvas-muted">Zeki AI: {o.gerekce}</p>}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </>
      )}
    </ChannelsFrame>
  );
}
