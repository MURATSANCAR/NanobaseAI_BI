import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { FileText, Mail } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { InfoLabel } from '../components/SqlInfo';
import { EmptyHint, Explain } from '../components/Explain';
import { Loading, Note, TableWrap, btnGhost, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import { KIND_LABEL, fmtDay, fmtInt, fmtMoney, fmtPct, fmtUnit, supplyApi } from './api';
import { CardLine, DraftSheet, ErrorNote, SupplyFrame, useDraft, useSupplyMeta } from './parts';

/** M52 Tedarikçi sayfası (/tedarik/tedarikci/:cari): açık işler + borç ve ödeme (FIFO) + faturalar + karne bir arada. */
export default function Supplier() {
  const { cari = '' } = useParams();
  const meta = useSupplyMeta();
  const me = meta.data?.me;
  const q = useQuery({ queryKey: ['supply', 'supplier', cari], queryFn: () => supplyApi.supplier(cari), enabled: ENGINE_ENABLED && !!cari });
  const d = q.data;
  const draft = useDraft();
  const ag = d?.yaslandirma;
  return (
    <SupplyFrame
      title={d?.unvan ?? 'Tedarikçi'}
      lead={d ? `${d.kod} · ${KIND_LABEL[d.tur] ?? d.tur}${d.crmMatbaa.length ? ` · CRM'de ${d.crmMatbaa.join(', ')}` : ''}. Bu tedarikçideki açık işler, borç ve ödemeler, faturalar ve teslim karnesi.` : 'Logo carisi'}
      back={{ to: '/tedarik/tedarikciler', label: 'Tedarikçiler' }}
      source={d?.logo ? `Logo ${d.logo.yil} · veri sonu ${fmtDay(d.logo.veriSonu)}` : undefined}
    >
      <ErrorNote error={q.error} fallback="Tedarikçi okunamadı." />
      {q.isLoading && <Loading />}
      {d && (
        <>
          {d.crmMatbaa.length === 0 && d.tur !== 'kagit' && (
            <Note tone="info">Bu cari henüz CRM'deki bir matbaa adıyla eşlenmedi; bu yüzden açık iş ve karne görünmüyor. Eşlemeyi «Tedarikçiler» ekranının «Matbaa ↔ cari» sekmesinden yapabilirsiniz.</Note>
          )}
          {d.borcGorunur && ag ? (
            <Panel>
              <h2 className="flex items-center gap-1 px-1 text-[13px] font-extrabold">
                <InfoLabel k={d.kaynaklar} alan="yaslandirma">Borç ve ödeme (tahmini)</InfoLabel>
                <Explain label="Borç ve ödeme" title="Kutular ne gösterir?">
                  <span className="block"><b>Bakiye:</b> bu tedarikçiye borcumuz (bu yıl başından alacak − borç).</span>
                  <span className="block"><b>Vadesi geçmiş / gelmemiş:</b> ödeme planındaki satırların ödeme günü geçmiş ya da gelmemiş kısmı; alttaki kutular kaç gün geçtiğine ya da kaldığına göre ayrılır.</span>
                  <span className="block"><b>Vade planı olmayan:</b> bakiyenin Logo'da ödeme planına bağlanmamış kısmı.</span>
                  Logo'da ödemeler faturaya bağlanmadığından tutarlar yaklaşıktır.
                </Explain>
              </h2>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Box label="Bakiye" value={fmtMoney(ag.bakiye)} />
                <Box label="Vadesi geçmiş" value={fmtMoney(ag.vadesiGecmis)} warn={ag.vadesiGecmis > 0} />
                <Box label="Vadesi gelmemiş" value={fmtMoney(ag.gelmemis)} />
                <Box label="Vade planı olmayan" value={fmtMoney(ag.plansiz)} />
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                <Box label="1–30 gün geçmiş" value={fmtMoney(ag.k_1_30)} />
                <Box label="31–60 gün geçmiş" value={fmtMoney(ag.k_31_60)} />
                <Box label="61–90 gün geçmiş" value={fmtMoney(ag.k_61_90)} />
                <Box label="90+ gün geçmiş" value={fmtMoney(ag.k_90p)} />
                <Box label="30 gün içinde" value={fmtMoney(ag.g_0_30)} />
                <Box label="31–60 gün içinde" value={fmtMoney(ag.g_31_60)} />
                <Box label="61–90 gün içinde" value={fmtMoney(ag.g_61_90)} />
                <Box label="90 günden sonra" value={fmtMoney(ag.g_90p)} />
              </div>
              {ag.acikSatir.length > 0 && (
                <div className="mt-3">
                  <TableWrap>
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className={th}>Vade</th>
                        <th className={th}>Fatura</th>
                        <th className={`${th} text-right`}>Plan tutarı</th>
                        <th className={`${th} text-right`}>Açık</th>
                        <th className={`${th} text-right`}>Gün</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ag.acikSatir.map((l, i) => (
                        <tr key={`${l.vade}-${i}`} className="border-b border-slate-50 last:border-0">
                          <td className={td}>{fmtDay(l.vade)}</td>
                          <td className={td}>{l.faturaNo ? `${l.faturaNo} · ${fmtDay(l.faturaTarihi)}` : '—'}</td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(l.tutar)}</td>
                          <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtMoney(l.acik)}</td>
                          <td className={`${td} text-right font-mono tabular-nums ${l.gun > 0 ? 'text-red-700' : ''}`}>
                            {l.gun > 0 ? `${l.gun} gün geçti` : `${-l.gun} gün var`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </TableWrap>
                </div>
              )}
              <p className="mt-2 px-1 text-[11.5px] leading-snug text-canvas-muted">{d.fifoNotu}</p>
            </Panel>
          ) : (
            !d.borcGorunur && <Note tone="info">Borç, ödeme ve fatura tutarları «tedarikçi borç» yetkisiyle görünür.</Note>
          )}

          <Panel>
            <h2 className="px-1 text-[13px] font-extrabold"><InfoLabel k={d.kaynaklar} alan="acikIsler" label="Açık işler">{`Açık işler (${fmtInt(d.acikIsler.length)})`}</InfoLabel></h2>
            <div className="mt-2">
              {d.acikIsler.length === 0 ? (
                <EmptyHint title="Bu matbaada açık iş yok" why="Bu tedarikçiye atanmış, baskıdan henüz çıkmamış üretim kartı bulunmuyor." />
              ) : (
                d.acikIsler.map((c) => (
                  <CardLine
                    key={c.id}
                    c={c}
                    right={
                      me?.canDecide ? (
                        <span className="flex gap-1.5">
                          <button type="button" className={btnGhost} disabled={draft.make.isPending} onClick={() => draft.make.mutate({ tur: 'sartname', kartId: c.id })} aria-label="Şartname taslağı hazırla" title="Şartname taslağı hazırla">
                            <FileText aria-hidden className="h-4 w-4" />
                          </button>
                          {c.gecikme > 0 && (
                            <button type="button" className={btnGhost} disabled={draft.make.isPending} onClick={() => draft.make.mutate({ tur: 'eskalasyon', kartId: c.id })} aria-label="Gecikme yazısı taslağı hazırla" title="Gecikme yazısı taslağı hazırla">
                              <Mail aria-hidden className="h-4 w-4" />
                            </button>
                          )}
                        </span>
                      ) : undefined
                    }
                  />
                ))
              )}
            </div>
          </Panel>

          {d.karne.length > 0 && (
            <Panel>
              <h2 className="flex items-center gap-1 px-1 text-[13px] font-extrabold">
                <InfoLabel k={d.kaynaklar} alan="karne">Karne (Üretim yönetimi)</InfoLabel>
                <Explain label="Karne" title="Karne ne gösterir?">
                  <span className="block"><b>Zamanında teslim:</b> planlanan baskı tarihinde ya da daha önce basılan işlerin oranı; «ölçüm», iki tarihi de bilinen iş sayısıdır.</span>
                  <span className="block"><b>Dosya → depo:</b> baskı dosyasının matbaaya gitmesinden kitabın depoya girmesine kadar geçen ortanca gün.</span>
                </Explain>
              </h2>
              <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {d.karne.map((k) => (
                  <div key={k.printer} className="contents">
                    <Box label={`${k.printer} · iş`} value={`${fmtInt(k.jobs)} (${fmtInt(k.open)} süren)`} />
                    <Box label="Zamanında teslim" value={`${fmtPct(k.onTimeRate)} · ${fmtInt(k.measured)} ölçüm`} />
                    <Box label="Dosya → depo" value={k.leadDays === null ? '—' : `${k.leadDays} gün`} />
                    {d.maliyetGorunur ? (
                      <Box label="Adet başı baskı (12 ay)" value={`${fmtUnit(k.unitRecent ?? k.unitPrice)} · ${fmtPct(k.unitTrend ?? null, true)}`} />
                    ) : (
                      <Box label="Kalite" value={fmtPct(k.qualityRate)} />
                    )}
                  </div>
                ))}
              </div>
            </Panel>
          )}

          {d.borcGorunur && d.faturalar && (
            <Panel>
              <h2 className="px-1 text-[13px] font-extrabold"><InfoLabel k={d.kaynaklar} alan="faturalar" label="Alış faturaları">{`Alış faturaları — son 12 ay (${fmtInt(d.faturalar.length)})`}</InfoLabel></h2>
              {d.alis && <p className="mt-1 px-1 text-[12px] text-canvas-muted"><InfoLabel k={d.kaynaklar} alan="alis" label="Alış toplamları">{`Bu yıl ${fmtMoney(d.alis.buYil)} · son 12 ay ${fmtMoney(d.alis.son12)} (KDV dahil)`}</InfoLabel></p>}
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className={th}>Tarih</th>
                      <th className={th}>Fatura</th>
                      <th className={th}>Tür</th>
                      <th className={th}>Açıklama</th>
                      <th className={`${th} text-right`}>Tutar (KDV dahil)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.faturalar.map((f, i) => (
                      <tr key={`${f.no}-${i}`} className="border-b border-slate-50 last:border-0">
                        <td className={`${td} whitespace-nowrap`}>{fmtDay(f.tarih)}</td>
                        <td className={td}>{f.no ?? '—'}</td>
                        <td className={td}>{f.tur === 4 ? 'Hizmet' : 'Mal'}</td>
                        <td className={td}>{f.aciklama ?? ''}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(f.tutar)}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
            </Panel>
          )}

          {d.bitenIsler.length > 0 && (
            <Panel>
              <h2 className="px-1 text-[13px] font-extrabold"><InfoLabel k={d.kaynaklar} alan="bitenIsler" label="Depoya giren işler">{`Depoya giren işler (${fmtInt(d.bitenIsler.length)})`}</InfoLabel></h2>
              <div className="mt-2">
                {d.bitenIsler.map((c) => (
                  <CardLine
                    key={c.id}
                    c={c}
                    right={
                      <span className="text-[11px] text-canvas-muted">
                        depo {fmtDay(c.depo)}
                        {d.maliyetGorunur && c.birimFiyat != null ? ` · ${fmtUnit(c.birimFiyat)}/adet` : ''}
                      </span>
                    }
                  />
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
      <DraftSheet draft={draft.draft} onClose={draft.close} />
    </SupplyFrame>
  );
}

function Box({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className={`mt-0.5 break-words font-mono text-[14px] font-bold tabular-nums ${warn ? 'text-red-700' : ''}`}>{value}</div>
    </div>
  );
}
