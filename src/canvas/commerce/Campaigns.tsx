import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, Sparkles } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, td, th } from '../admin/ui';
import { Panel } from '../editorial/kit';
import SqlInfo from '../components/SqlInfo';
import type { Kaynaklar } from '../components/sqlInfo';
import { commerceApi, fmtChange, fmtDay, fmtInt, fmtRatio, fmtTl, type Campaign } from './api';
import { useMeta } from './parts';

/** Kampanya sonuçları: hedef ve kontrol grubunun pencere içindeki geçerli site siparişi; dönüşüm farkı ve güven aralığı. */
export default function Campaigns() {
  const q = useQuery({ queryKey: ['commerce', 'campaigns'], queryFn: commerceApi.campaigns, enabled: ENGINE_ENABLED });
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'Kampanyalar açılamadı.')}</Note>;
  const items = q.data?.items ?? [];
  if (!items.length) {
    return <Note tone="info">Henüz kampanya yok. Onaylı bir tetik listesinden «Kampanya sonucu için aç» ile açılır; kontrol grubu olmayan liste ölçülmez.</Note>;
  }
  return <div className="flex flex-col gap-3 lg:gap-4">{items.map((c) => <CampaignCard key={c.id} c={c} k={q.data?.kaynaklar} />)}</div>;
}

function CampaignCard({ c, k }: { c: Campaign; k?: Kaynaklar }) {
  const meta = useMeta();
  const qc = useQueryClient();
  const comment = useMutation({
    mutationFn: () => commerceApi.comment(c.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['commerce', 'campaigns'] }),
    onError: (e) => toast.error(errText(e, 'Yorum alınamadı.') ?? ''),
  });
  const r = c.result;
  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="flex items-center gap-1 text-[15px] font-extrabold">{c.name} <SqlInfo k={k} alan="items" label={`Kampanya sonucu: ${c.name}`} /></h3>
          <p className="text-[11.5px] text-canvas-muted">{fmtDay(c.start)} – {fmtDay(c.end)} · {c.createdBy}</p>
        </div>
        {r && <Pill tone={r.kesin ? 'ok' : 'warn'}>{r.kesin ? 'Kesin' : 'Kesinleşmedi'}</Pill>}
      </div>
      {!r ? (
        <p className="mt-2 text-[12.5px] text-canvas-muted">Sonuç henüz hesaplanmadı.</p>
      ) : (
        <>
          <div className="mt-3">
            <TableWrap>
              <thead>
                <tr><th className={th}>Grup</th><th className={`${th} text-right`}>Kişi</th><th className={`${th} text-right`}>Alışveriş yapan</th><th className={`${th} text-right`}>Oran</th><th className={`${th} text-right`}>Sipariş</th><th className={`${th} text-right`}>Ciro</th><th className={`${th} text-right`}>Kişi başına</th></tr>
              </thead>
              <tbody>
                {([['Hedef', r.hedef, r.lift.hedefOran], ['Kontrol', r.kontrol, r.lift.kontrolOran]] as const).map(([n, g, o]) => (
                  <tr key={n} className="border-t border-slate-100">
                    <td className={`${td} font-bold`}>{n}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(g.kisi)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(g.alan)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtRatio(o, 2)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(g.siparis)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtTl(g.ciro)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{g.kisiBasinaCiro == null ? '—' : `${g.kisiBasinaCiro.toLocaleString('tr-TR', { maximumFractionDigits: 2 })} ₺`}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-[12px] sm:grid-cols-4">
            <div className="rounded-xl bg-slate-50 p-2.5"><dt className="font-bold text-canvas-muted">Dönüşüm farkı (puan)</dt><dd className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{fmtChange(r.lift.fark)}</dd></div>
            <div className="rounded-xl bg-slate-50 p-2.5"><dt className="font-bold text-canvas-muted">%95 güven aralığı</dt><dd className="mt-0.5 font-mono text-[13px] font-bold tabular-nums">{r.lift.alt == null ? '—' : `${fmtRatio(r.lift.alt, 2)} … ${fmtRatio(r.lift.ust, 2)}`}</dd></div>
            <div className="rounded-xl bg-slate-50 p-2.5"><dt className="font-bold text-canvas-muted">Ek alışveriş yapan</dt><dd className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{fmtInt(r.ekAlan)}</dd></div>
            <div className="rounded-xl bg-slate-50 p-2.5"><dt className="font-bold text-canvas-muted">Ek ciro</dt><dd className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{fmtTl(r.ekCiro)}</dd></div>
          </dl>
          <p className="mt-2 text-[12px] font-semibold">
            {r.lift.anlamli ? 'Fark anlamlı: güven aralığı sıfırı içermiyor.' : 'Fark anlamlı değil: güven aralığı sıfırı içeriyor; kampanyaya ek satış yazılamaz.'}
          </p>
          {r.uyarilar.map((w) => <p key={w} className="mt-1 text-[11.5px] text-amber-800">{w}</p>)}
          {c.comment && <p className="mt-2 rounded-xl bg-canvas-violet/5 p-2.5 text-[12.5px] leading-snug">{c.comment}</p>}
          {meta.data?.me.canTrigger && meta.data.modelVar && (
            <button type="button" className={`${btnGhost} mt-2`} onClick={() => comment.mutate()} disabled={comment.isPending}>
              {comment.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <Sparkles aria-hidden className="h-4 w-4" />}
              Zeki AI yorumu
            </button>
          )}
        </>
      )}
    </Panel>
  );
}
