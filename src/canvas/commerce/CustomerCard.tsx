import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Eye, Loader2 } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { commerceApi, fmtDay, fmtInt, fmtTl } from './api';
import { CommerceFrame, ROOT, SegmentPill, useMeta } from './parts';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { Explain } from '../components/Explain';

const CONSENT: Record<string, { label: string; tone: 'ok' | 'err' | 'muted' }> = {
  izinli: { label: 'İzinli', tone: 'ok' }, ret: { label: 'Ret', tone: 'err' }, bilinmiyor: { label: 'Bilinmiyor', tone: 'muted' },
};

/** Müşteri kartı: bütün siparişler ve iadeler, segment geçişleri, aldığı kategoriler, izin (okur veri tabanından). Kişi
 * bilgisi yalnız yetkiyle, düğmeye basınca siteden o an okunur ve kayda geçer. */
export default function CustomerCard() {
  const { key = '' } = useParams();
  const meta = useMeta();
  const [personal, setPersonal] = useState(false);
  const q = useQuery({ queryKey: ['commerce', 'customer', key, personal], queryFn: () => commerceApi.customer(key, personal), enabled: ENGINE_ENABLED && !!key });
  const c = q.data;
  return (
    <CommerceFrame presence={c ? c.etiket : 'Müşteri'}>
      <Link to={`${ROOT}/musteriler`} className={`${btnGhost} self-start`}><ArrowLeft aria-hidden className="h-4 w-4" />Müşterilere dön</Link>
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Müşteri kartı açılamadı.')}</Note>}
      {c && (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="font-mono text-[18px] font-extrabold">{c.etiket}</h2>
            <SegmentPill segment={c.segment} label={c.segmentLabel} />
            {c.uye ? <Pill tone="muted">Üye{c.uyelik ? ` · ${fmtDay(c.uyelik)}` : ''}</Pill> : c.misafir ? <Pill tone="muted">Misafir</Pill> : null}
            {c.il && <Pill tone="muted">{c.il}</Pill>}
          </div>
          <KpiRow>
            <Kpi label="Geçerli sipariş" value={fmtInt(c.siparis)} help={`İptal/iade ${fmtInt(c.iadeIptal)}`} info={<SqlInfo k={c.kaynaklar} alan="siparis" label="Geçerli sipariş" />} />
            <Kpi label="Site cirosu" value={fmtTl(c.ciro)} help={`R ${c.r ?? '—'} · F ${c.f ?? '—'} · M ${c.m ?? '—'}`} explain="Müşterinin sitedeki geçerli siparişlerinin toplam tutarı. Altındaki R, F, M puanları (1–5) sırasıyla son siparişin yakınlığını, sipariş sıklığını ve harcama büyüklüğünü gösterir; yüksek puan daha iyidir." info={<SqlInfo k={c.kaynaklar} alan="ciro" label="Site cirosu ve R, F, M puanı" />} />
            <Kpi label="İlk sipariş" value={fmtDay(c.ilkSiparis)} help="Geçerli sipariş" />
            <Kpi label="Son sipariş" value={fmtDay(c.sonSiparis)} help={`Segmentte ${fmtDay(c.segmentTarihi)} tarihinden beri`} />
          </KpiRow>

          <div className="grid gap-3 lg:grid-cols-[1fr_1.4fr] lg:gap-4">
            <div className="flex flex-col gap-3 lg:gap-4">
              <Panel>
                <h3 className="flex items-center gap-1 text-[15px] font-extrabold">İzin<Explain label="İzin">Müşterinin e-posta, SMS, arama ve KVKK izinleri; okur veri tabanından gelir. Herhangi bir kayıtta ret varsa ret sayılır.</Explain></h3>
                {c.izin ? (
                  <ul className="mt-2 space-y-1 text-[12.5px]">
                    {(['email', 'sms', 'call', 'kvkk'] as const).map((ch) => (
                      <li key={ch} className="flex items-center justify-between gap-2">
                        <span>{meta.data?.channels[ch] ?? ch}</span>
                        <Pill tone={CONSENT[c.izin![ch]].tone}>{CONSENT[c.izin![ch]].label}</Pill>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-[12.5px] text-canvas-muted">Okur veri tabanında henüz eşleşmedi (gece turundan sonra bağlanır).</p>
                )}
                {c.okur && <Link to={`/okurlar/kisi/${c.okur}`} className="mt-2 inline-flex min-h-11 items-center text-[12px] font-extrabold text-canvas-violet sm:min-h-0">Okur kartını aç →</Link>}
                <p className="mt-2 text-[11.5px] text-canvas-muted">Karar okur veri tabanının kuralıdır: herhangi bir kayıtta ret varsa ret.</p>
              </Panel>
              <Panel>
                <h3 className="text-[15px] font-extrabold">Kişi bilgisi</h3>
                {c.kisisel ? (
                  c.kisisel.bulunamadi ? <p className="mt-1 text-[12.5px] text-canvas-muted">Sitede bu müşteriyle eşleşen kayıt okunamadı.</p> : (
                    <dl className="mt-2 space-y-1 text-[12.5px]">
                      <div><dt className="inline font-bold">Ad: </dt><dd className="inline">{c.kisisel.ad ?? '—'}</dd></div>
                      <div><dt className="inline font-bold">E-posta: </dt><dd className="inline break-all">{c.kisisel.eposta ?? '—'}</dd></div>
                      <div><dt className="inline font-bold">Telefon: </dt><dd className="inline">{c.kisisel.cep ?? '—'}</dd></div>
                    </dl>
                  )
                ) : meta.data?.me.canPersonal ? (
                  <button type="button" className={`${btnGhost} mt-2`} onClick={() => setPersonal(true)} disabled={q.isFetching}>
                    {q.isFetching ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Eye aria-hidden className="h-4 w-4" />}Siteden oku (kayda geçer)
                  </button>
                ) : (
                  <p className="mt-1 text-[12.5px] text-canvas-muted">Kişi bilgisi yalnız okur kişisel veri yetkisiyle görülür.</p>
                )}
              </Panel>
              <Panel>
                <h3 className="flex items-center gap-1 text-[15px] font-extrabold">Aldığı kategoriler <SqlInfo k={c.kaynaklar} alan="kategoriler" label="Aldığı kategoriler" /></h3>
                {c.kategoriler.length ? (
                  <ul className="mt-2 space-y-0.5 text-[12.5px]">
                    {c.kategoriler.map((k) => <li key={k.id} className="flex justify-between gap-2"><span>{k.ad}</span><span className="font-mono tabular-nums">{fmtInt(k.adet)}</span></li>)}
                  </ul>
                ) : <p className="mt-1 text-[12.5px] text-canvas-muted">Kategori bilgisi yok (kitap profilinde düğüm yok ya da barkod eşleşmedi).</p>}
              </Panel>
              {c.gecisler.length > 0 && (
                <Panel>
                  <h3 className="text-[15px] font-extrabold">Segment geçişleri</h3>
                  <ul className="mt-2 space-y-0.5 text-[12.5px]">
                    {c.gecisler.map((g, i) => <li key={i}>{fmtDay(g.at)}: {g.fromLabel} → <strong>{g.toLabel}</strong></li>)}
                  </ul>
                </Panel>
              )}
            </div>
            <Panel>
              <h3 className="flex items-center gap-1 text-[15px] font-extrabold">Siparişler <SqlInfo k={c.kaynaklar} alan="siparisler" label="Siparişler" /></h3>
              <div className="mt-2">
                <TableWrap>
                  <thead><tr><th className={th}>Tarih</th><th className={th}>Sipariş</th><th className={th}>Durum</th><th className={th}>Kitaplar</th><th className={`${th} text-right`}><InfoLabel k={c.kaynaklar} alan="siparisler">Tutar</InfoLabel></th></tr></thead>
                  <tbody>
                    {c.siparisler.map((o) => (
                      <tr key={o.no} className={`border-t border-slate-100 ${o.gecerli ? '' : 'text-canvas-muted'}`}>
                        <td className={`${td} whitespace-nowrap`}>{fmtDay(o.tarih)}</td>
                        <td className={`${td} font-mono`}>{o.no}{o.kupon ? <div className="text-[11px]">Kupon {o.kupon}</div> : null}</td>
                        <td className={td}>{o.gecerli ? (o.durum ?? '—') : <Pill tone="err">{o.durum ?? 'İptal/iade'}</Pill>}</td>
                        <td className={td}>{o.satirlar.map((s, i) => <div key={i}>{s.ad ?? s.barkod ?? '—'} × {fmtInt(s.adet)}</div>)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtTl(o.tutar)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
            </Panel>
          </div>
        </>
      )}
    </CommerceFrame>
  );
}
