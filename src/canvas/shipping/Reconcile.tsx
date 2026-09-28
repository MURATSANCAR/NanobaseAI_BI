import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtDay, fmtInt, fmtMoney, fmtPct, previousMonth, shippingApi } from './api';
import { Empty, ExportButton, FreshNote, ShippingFrame } from './parts';

/** M44 Kargo mutabakatı (/kargo/mutabakat?ay=YYYY-AA): kargo firmasının gönderi kaydı toplamı ↔ Logo'daki kargo faturası
 *  (eşlenen cariler), mükerrer takip numarası, tutarı okunamayan kayıt; Logo sevk ↔ CRM sevkiyat eşleşme oranı.
 *  Fark gerekçesini Zeki AI yalnız verilen rakamlarla özetler; itiraz kararı finansındır. */

export default function Reconcile() {
  const [params, setParams] = useSearchParams();
  const ay = params.get('ay') ?? previousMonth();
  const meta = useQuery({ queryKey: ['shipping', 'meta'], queryFn: shippingApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const allowed = !!meta.data?.me.mutabakat;
  const rec = useQuery({ queryKey: ['shipping', 'reconcile', ay], queryFn: () => shippingApi.reconcile(ay), enabled: ENGINE_ENABLED && allowed });
  const [summary, setSummary] = useState<string | null>(null);
  const [showCandidates, setShowCandidates] = useState(false);
  const cand = useQuery({ queryKey: ['shipping', 'candidates'], queryFn: shippingApi.candidates, enabled: ENGINE_ENABLED && allowed && showCandidates });
  const sum = useMutation({
    mutationFn: () => shippingApi.reconcileSummary(ay),
    onSuccess: (r) => {
      setSummary(r.metin);
      if (!r.metin) toast.message(r.not ?? 'Zeki AI özeti alınamadı.');
    },
    onError: (e) => toast.error(errText(e, 'Özet alınamadı.') ?? ''),
  });
  const d = rec.data;
  return (
    <ShippingFrame
      crumb="Kargo mutabakatı"
      title="Kargo mutabakatı"
      lead="Ay sonunda kargo firmasının faturasını gönderi kaydıyla karşılaştırmak için: firma bazında kargo kaydı tutarı, Logo'daki alınan hizmet faturası (KDV hariç ve dahil), fark, mükerrer takip numarası. Logo'daki gerçekleşen sevkin CRM sevkiyatıyla eşleşme oranı da buradadır."
      meta={meta.data}
      aside={
        meta.data && allowed && (
          <div className="flex flex-wrap items-end justify-start gap-2 lg:justify-end">
            <label className="flex w-44 flex-col gap-1">
              <span className={labelCls}>Ay</span>
              <input className={field} type="month" value={ay} onChange={(e) => { setSummary(null); setParams(e.target.value ? { ay: e.target.value } : {}, { replace: true }); }} />
            </label>
            <ExportButton list="mutabakat" params={{ ay }} can={meta.data.me.disaAktar} label="Excel'e al" />
          </div>
        )
      }
    >
      {meta.data && !allowed && <Note tone="warn">Mutabakat kargo maliyetini görme yetkisi ister; rolünüzde yok.</Note>}
      {rec.isLoading && <Note tone="info">Logo kargo faturaları, Logo sevk ve CRM sevkiyatı okunuyor…</Note>}
      {rec.error && <Note tone="err">{errText(rec.error, 'Mutabakat okunamadı.')}</Note>}
      {d && (
        <>
          <KpiRow>
            <Kpi label="Gönderi" value={fmtInt(d.toplam.gonderi)} help={`${fmtDay(d.baslangic)} – ${fmtDay(d.bitis)}`} />
            <Kpi label="Kargo kaydı tutarı" value={fmtMoney(d.toplam.crmTutar)} help="Kargo firmasının gönderi kaydından" />
            <Kpi label="Logo kargo faturası" value={fmtMoney(d.toplam.logoKdvHaric)} help="KDV hariç, eşlenen carilerde" />
            <Kpi label="Logo carisi eşlenmemiş" value={fmtInt(d.toplam.eslenmeyenFirma)} help="Gönderisi olan firma" onClick={() => setShowCandidates(true)} />
          </KpiRow>
          {d.notlar.map((n) => <Note key={n} tone="warn">{n}</Note>)}
          <FreshNote f={d.kargoVeri} />
          <Panel>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <h2 className="text-[14px] font-extrabold">Firma bazında</h2>
              <button type="button" className={btnGhost} disabled={sum.isPending} onClick={() => sum.mutate()}>
                {sum.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
                Zeki AI fark özeti
              </button>
            </div>
            {summary && <p className="mt-2 whitespace-pre-line rounded-xl bg-canvas-violet/5 px-3 py-2 text-[12.5px]">{summary}</p>}
            {d.items.length === 0 ? (
              <Empty>Bu ayda kargo kaydı da Logo faturası da yok.</Empty>
            ) : (
              <div className="mt-2">
                <TableWrap>
                  <thead>
                    <tr>
                      <th className={th}>Firma</th>
                      <th className={`${th} text-right`}>Gönderi</th>
                      <th className={`${th} text-right`}>Kargo kaydı</th>
                      <th className={`${th} text-right`}>Logo (KDV hariç)</th>
                      <th className={`${th} text-right`}>Fark</th>
                      <th className={`${th} text-right`}>Logo (KDV dahil)</th>
                      <th className={`${th} text-right`}>Mükerrer</th>
                      <th className={`${th} text-right`}>Tutarı okunamayan</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((r) => (
                      <tr key={r.firma} className="border-t border-slate-100">
                        <td className={td}>
                          <div className="font-bold">{r.firma}</div>
                          {r.logoEslendi ? <span className="font-mono text-[11px] text-canvas-muted">{r.logoCariler.join(', ')}</span> : <Pill tone="warn">Logo carisi eşlenmemiş</Pill>}
                        </td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.gonderi)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.crmTutar)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.logoKdvHaric)}</td>
                        <td className={`${td} text-right font-mono font-bold tabular-nums ${r.farkKdvHaric && r.farkKdvHaric > 0 ? 'text-red-700' : ''}`}>{fmtMoney(r.farkKdvHaric)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.logoKdvDahil)}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{r.mukerrer ? `${fmtInt(r.mukerrer)} · ${fmtMoney(r.mukerrerTutar)}` : '—'}</td>
                        <td className={`${td} text-right font-mono tabular-nums`}>{r.tutarOkunamayan ? fmtInt(r.tutarOkunamayan) : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </TableWrap>
              </div>
            )}
            <p className="mt-2 text-[11.5px] text-canvas-muted">Fark = Logo faturası − kargo kaydı tutarı. Kargo kaydındaki tutarın KDV dahil mi hariç mi olduğu ölçülecek; iki fark birlikte okunmalı.</p>
          </Panel>
          {d.sevk && (
            <Panel>
              <h2 className="text-[14px] font-extrabold">Logo sevk ↔ CRM sevkiyat</h2>
              <p className="max-w-[80ch] text-[11.5px] text-canvas-muted">Logo'da gerçekleşen sevk: satış irsaliyesi satırları (çıkış). CRM'de Logo'ya aktarıldı işaretli sevkiyatlar, fatura numarasıyla eşlenir.</p>
              <div className="mt-2 grid grid-cols-2 gap-2 lg:grid-cols-4">
                <Fact label="Logo irsaliye" value={`${fmtInt(d.sevk.logoIrsaliye)} (${fmtInt(d.sevk.logoFaturali)} faturalı)`} />
                <Fact label="Logo satır / adet" value={`${fmtInt(d.sevk.logoSatir)} / ${fmtInt(d.sevk.logoAdet)}`} />
                <Fact label="CRM sevkiyat" value={fmtInt(d.sevk.crmSevkiyat)} />
                <Fact label="Eşleşen" value={`${fmtInt(d.sevk.eslesen)} · ${fmtPct(d.sevk.eslesmeOrani)}`} />
              </div>
              {d.sevk.eslesmeyen.length > 0 && (
                <details className="mt-2 text-[12px]">
                  <summary className="cursor-pointer font-bold text-canvas-violet">Eşleşmeyen {fmtInt(d.sevk.eslesmeyen.length)} fatura numarası</summary>
                  <p className="mt-1 break-words font-mono text-[11.5px] leading-relaxed text-canvas-muted">{d.sevk.eslesmeyen.join(' · ')}</p>
                </details>
              )}
            </Panel>
          )}
          <Panel>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="text-[14px] font-extrabold">Logo carisi eşleme</h2>
                <p className="max-w-[80ch] text-[11.5px] text-canvas-muted">
                  Mutabakat için her kargo firmasının Logo cari kodu yönetim ekranındaki «Kargo firması → Logo cari kodları» ayarına yazılır. Aşağıdaki liste son 12 ayda hizmet faturası kesen ve ünvanı kargoya benzeyen carilerdir; eşlemeyi siz onaylarsınız.
                </p>
              </div>
              <button type="button" className={btnGhost} onClick={() => setShowCandidates((x) => !x)}>
                {showCandidates ? 'Gizle' : 'Aday carileri göster'}
              </button>
            </div>
            {showCandidates && (
              <div className="mt-2">
                {cand.isLoading && <Empty>Logo okunuyor…</Empty>}
                {cand.error && <Note tone="err">{errText(cand.error, 'Adaylar okunamadı.')}</Note>}
                {cand.data && !cand.data.items.length && <Empty>Aday cari bulunamadı (ipuçları: {cand.data.ipuclari.join(', ')}).</Empty>}
                {cand.data && cand.data.items.length > 0 && (
                  <TableWrap>
                    <thead>
                      <tr>
                        <th className={th}>Cari kodu</th>
                        <th className={th}>Ünvan</th>
                        <th className={`${th} text-right`}>Fatura</th>
                        <th className={`${th} text-right`}>KDV hariç (12 ay)</th>
                        <th className={th}>Son fatura</th>
                        <th className={th}>Durum</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cand.data.items.map((c) => (
                        <tr key={c.cari ?? c.unvan ?? ''} className="border-t border-slate-100">
                          <td className={`${td} font-mono`}>{c.cari}</td>
                          <td className={td}>{c.unvan}</td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.fatura)}</td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(c.kdvHaric)}</td>
                          <td className={`${td} font-mono tabular-nums`}>{fmtDay(c.son)}</td>
                          <td className={td}>{c.eslenmis ? <Pill tone="ok">Eşlenmiş</Pill> : <Pill tone="muted">Eşlenmemiş</Pill>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </TableWrap>
                )}
              </div>
            )}
          </Panel>
        </>
      )}
    </ShippingFrame>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/80 px-3 py-2">
      <div className="text-[10.5px] font-bold uppercase tracking-wide text-canvas-muted">{label}</div>
      <div className="mt-0.5 break-words font-mono text-[13px] font-bold tabular-nums">{value}</div>
    </div>
  );
}
