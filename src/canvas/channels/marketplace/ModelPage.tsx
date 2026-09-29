import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../../engine';
import { Loading, Note, Pill, TableWrap, errText, td, th } from '../../admin/ui';
import { Panel } from '../../editorial/kit';
import { fmtDay, fmtInt, fmtMoney } from '../../budget/api';
import SqlInfo, { InfoLabel } from '../../components/SqlInfo';
import { EmptyHint, ExplainLabel } from '../../components/Explain';
import { SourceBar } from '../platformKit';
import { RULE_LABEL, marketplaceApi, modelTone, type ModelKey, type Platform } from './api';
import { useMarketJob, type FrameComponent } from './parts';

const TRACES: ReadonlyArray<{ key: Exclude<ModelKey, 'belirsiz'>; label: string; rule: string }> = [
  { key: 'kendi-magaza', label: 'Kendi mağaza izi', rule: 'Perakende satış faturası, belge alanında platform adı geçen tüketici faturası, panel siparişinin tüketici faturasında bulunması ya da satış olmadan platformdan alınan hizmet faturası.' },
  { key: 'toptan', label: 'Toptan izi', rule: 'Pazar yeri carisine toptan satış faturası.' },
  { key: 'konsinye', label: 'Konsinye izi', rule: 'Uzun süre faturalanmamış sevk irsaliyesi ya da sevkten çok sonra faturalanan sevk.' },
];

/** Aşama 0 — satış modeli tespiti: «Bu kanalın satış modeli: … (kanıt: …)», kanıt satırları, cariler, kesinti ve hakediş yolu. */
export default function ModelPage({ platform, Frame }: { platform: Platform; Frame: FrameComponent }) {
  const api = useMemo(() => marketplaceApi(platform), [platform]);
  const key = useMemo(() => ['pazaryeri', platform, 'model'] as const, [platform]);
  const q = useQuery({ queryKey: key, queryFn: api.model, enabled: ENGINE_ENABLED });
  const d = q.data;
  const job = useMarketJob({ key, job: d?.job, status: api.modelStatus, start: api.modelRefresh, done: 'Satış modeli Logo’dan ölçüldü.' });
  const k = d?.kaynaklar;
  return (
    <Frame
      title="Satış modeli"
      lead="Bu kanalda nasıl sattığımızı tahmin etmiyoruz, Logo’dan ölçüyoruz: pazar yeri carilerine kesilen fatura türleri, faturalanmamış sevk, platformdan alınan hizmet faturaları ve para hareketleri. Sonuç kanıtlarıyla yazılır; kanıt yetmezse ekran «belirsiz» der."
    >
      <SourceBar
        text={<>Logo ve CRM yalnız okunur; pazar yerine bağlanılmaz.{d?.veriSonu ? <> Logo verisi <strong className="text-canvas-ink">{fmtDay(d.veriSonu)}</strong> tarihinde bitiyor.</> : ''}</>}
        at={d?.okumaZamani}
        running={job.running}
        step={job.step}
        error={job.error}
        onRefresh={job.start}
        busy={job.busy}
      />
      {q.error && <Note tone="err">{errText(q.error, 'Satış modeli açılamadı.')}</Note>}
      {q.isLoading && <Loading />}
      {d && (
        <>
          <Panel>
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone={modelTone(d.model, d.guven)}>{d.model === 'belirsiz' ? 'Belirsiz' : d.modelAd.split(' (')[0]}</Pill>
              {d.guven && <Pill tone="muted">{d.guven === 'guclu' ? 'Güçlü kanıt' : 'Zayıf kanıt'}</Pill>}
              {d.donem && <span className="text-[12px] text-canvas-muted">Ölçülen dönem {fmtDay(d.donem.bas)} – {fmtDay(d.donem.bit)}</span>}
              <SqlInfo k={k} alan="cumle" label="Satış modeli" />
            </div>
            <p className="mt-2 max-w-[90ch] text-[15px] font-bold leading-snug sm:text-[17px]">{d.cumle}</p>
            {d.model !== 'belirsiz' && <p className="mt-1 text-[12px] text-canvas-muted">{d.modelAd}</p>}
            <p className="mt-2 text-[11.5px] text-canvas-muted">
              Aranan adlar: {d.desenler.join(', ')} (Yönetim › Platform ve kanallar). Cari farklı adla açılmışsa{' '}
              <Link className="font-bold text-canvas-violet hover:underline" to="/kanallar/eslesme">Cari eşleme</Link> ekranında platforma bağlayın; sonraki ölçümde sayılır.
            </p>
          </Panel>
          {!d.okundu ? (
            <EmptyHint title="Henüz ölçülmedi" why="«Veriyi yenile» Logo’yu ve CRM’i salt okuma ile tarar; birkaç dakika sürebilir." />
          ) : (
            <>
              <div className="grid gap-3 lg:grid-cols-3">
                {TRACES.map((t) => {
                  const ev = d.kanit.filter((e) => e.model === t.key);
                  return (
                    <Panel key={t.key}>
                      <h2 className="flex items-center gap-1 text-[14px] font-extrabold">
                        <ExplainLabel label={t.label}>{t.rule}</ExplainLabel>
                        <SqlInfo k={k} alan="kanit" label={t.label} />
                      </h2>
                      {ev.length ? (
                        <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-4 text-[12.5px] leading-snug">{ev.map((e) => <li key={e.kural}>{e.metin}</li>)}</ul>
                      ) : (
                        <p className="mt-1.5 text-[12.5px] text-canvas-muted">İz yok.</p>
                      )}
                    </Panel>
                  );
                })}
              </div>
              <div className="grid gap-3 lg:grid-cols-2">
                <Panel>
                  <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Kesinti Logo’da nasıl kayıtlı <SqlInfo k={k} alan="kesinti" label="Kesinti" /></h2>
                  <p className="mb-2 text-[12.5px]">{d.kesinti?.cumle}</p>
                  {!!d.kesinti?.kalemler.length && (
                    <TableWrap>
                      <thead><tr><th className={th}>Kalem</th><th className={th}>Hizmet kartı</th><th className={`${th} text-right`}>Satır</th><th className={`${th} text-right`}>Tutar (KDV hariç)</th></tr></thead>
                      <tbody>
                        {d.kesinti.kalemler.map((x) => (
                          <tr key={`${x.kalem}-${x.hizmetKodu}`} className="border-t border-slate-100">
                            <td className={`${td} font-semibold`}>{x.kalemAd}</td>
                            <td className={td}>{x.hizmet}<div className="font-mono text-[11px] text-canvas-muted">{x.hizmetKodu}</div></td>
                            <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.satir)}</td>
                            <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(x.tutar)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </TableWrap>
                  )}
                </Panel>
                <Panel>
                  <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Para nasıl geliyor <SqlInfo k={k} alan="hakedis" label="Hakediş yolu" /></h2>
                  <p className="mb-2 text-[12.5px]">{d.hakedis?.cumle}</p>
                  {!!d.hakedis?.hareketler.length && (
                    <TableWrap>
                      <thead><tr><th className={th}>Hareket</th><th className={th}>Yön</th><th className={`${th} text-right`}>Adet</th><th className={`${th} text-right`}>Tutar</th></tr></thead>
                      <tbody>
                        {d.hakedis.hareketler.map((x) => (
                          <tr key={`${x.modulAd}-${x.turAd}-${x.yon}`} className="border-t border-slate-100">
                            <td className={td}><div className="font-semibold">{x.turAd}</div><div className="text-[11px] text-canvas-muted">{x.modulAd}</div></td>
                            <td className={td}>{x.yon}</td>
                            <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.hareket)}</td>
                            <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(x.tutar)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </TableWrap>
                  )}
                </Panel>
              </div>
              <Panel>
                <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Pazar yeri carileri <SqlInfo k={k} alan="cariler" label="Pazar yeri carileri" /></h2>
                <p className="mb-2 text-[12px] text-canvas-muted">Kurala göre bulunan Logo carileri ve ölçülen dönemdeki fatura türleri. Koda yazılmış cari yoktur.</p>
                {!d.cariler.length ? (
                  <EmptyHint title="Bu platforma bağlanan cari bulunamadı" why="Unvanda platform adı geçen, cari eşlemesinde bu platforma bağlı ya da kanal kodu bu platforma bağlı cari yok." />
                ) : (
                  <TableWrap>
                    <thead><tr><th className={th}>Cari</th><th className={th}>Neden listede</th><th className={th}>Fatura türleri</th><th className={`${th} text-right`}><InfoLabel k={k} alan="cariler">Açık sevk</InfoLabel></th><th className={`${th} text-right`}>Geç faturalanan</th></tr></thead>
                    <tbody>
                      {d.cariler.map((c) => (
                        <tr key={c.kod} className="border-t border-slate-100">
                          <td className={td}><div className="font-semibold">{c.unvan ?? '—'}</div><div className="font-mono text-[11px] text-canvas-muted">{c.kod}{c.kanal ? ` · ${c.kanal}` : ''}</div></td>
                          <td className={td}>
                            <div className="flex flex-wrap gap-1">{c.kurallar.map((r) => <Pill key={r} tone="violet">{RULE_LABEL[r] ?? r}</Pill>)}</div>
                            {c.hesapDisi && <div className="mt-1"><Pill tone="warn">Kanıta katılmadı: {c.hesapDisi}</Pill></div>}
                          </td>
                          <td className={`${td} text-[11.5px]`}>
                            {Object.values(c.faturalar).length
                              ? Object.values(c.faturalar).map((f) => <div key={f.turAd}>{f.turAd}: <span className="font-mono tabular-nums">{fmtInt(f.fatura)}</span> fatura · {fmtMoney(f.tutar)}</div>)
                              : <span className="text-canvas-muted">Fatura yok</span>}
                          </td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.acikSevk)}</td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.gecFaturalanan)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </TableWrap>
                )}
              </Panel>
              <div className="grid gap-3 lg:grid-cols-2">
                <Panel>
                  <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Belgede platform adı geçen faturalar <SqlInfo k={k} alan="belgeMetni" label="Belge metni" /></h2>
                  <p className="mb-2 text-[12px] text-canvas-muted">Tüketiciye kesilen faturada cari tek tek okurdur; platform adı açıklama ya da özel kod alanında geçebilir.</p>
                  {!d.belgeMetni?.length ? <p className="text-[12.5px] text-canvas-muted">Bulunmadı.</p> : (
                    <TableWrap>
                      <thead><tr><th className={th}>Tür</th><th className={th}>Kanal kodu</th><th className={`${th} text-right`}>Fatura</th><th className={`${th} text-right`}>Bir ayda en çok cari</th></tr></thead>
                      <tbody>
                        {d.belgeMetni.map((x) => (
                          <tr key={`${x.turAd}-${x.kanal}`} className="border-t border-slate-100">
                            <td className={td}>{x.turAd}</td><td className={td}>{x.kanal ?? '—'}</td>
                            <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.fatura)}</td>
                            <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(x.enCokCariAy)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </TableWrap>
                  )}
                </Panel>
                <Panel>
                  <h2 className="flex items-center gap-1 text-[15px] font-extrabold">CRM’de platform firmaları <SqlInfo k={k} alan="crm" label="CRM firmaları" /></h2>
                  {d.crm?.hata && <Note tone="warn">CRM okunamadı: {d.crm.hata}</Note>}
                  {!d.crm?.firmalar.length ? <p className="text-[12.5px] text-canvas-muted">Etkin firma kartı bulunmadı.</p> : (
                    <ul className="flex flex-col gap-1.5 text-[12.5px]">
                      {d.crm.firmalar.map((f) => (
                        <li key={f.ad}><span className="font-semibold">{f.ad}</span>{f.logoRef ? <span className="text-canvas-muted"> · Logo bağı var</span> : <span className="text-amber-800"> · Logo bağı yok</span>}
                          <div className="text-[11.5px] text-canvas-muted">{f.siparis.length ? f.siparis.map((s) => `${s.ad}: ${fmtInt(s.sayi)}`).join(' · ') : 'Ölçülen dönemde sipariş yok'}</div></li>
                      ))}
                    </ul>
                  )}
                </Panel>
              </div>
            </>
          )}
        </>
      )}
    </Frame>
  );
}
