import { useParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Download, RefreshCw } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo from '../components/SqlInfo';
import { Loading, Note, TableWrap, btnGhost, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { evApi, fmtDay, fmtInt, fmtMoney, fmtPct, fmtRange, fmtRatio } from './api';
import { Block, EventsFrame } from './parts';

/** Fuar sonucu: fuar kanalı net satış (Logo, faturalı satır), CRM fuar/etkinlik/imza siparişleri, gider (portal + CRM),
 *  bütçe, geçen yılla karşılaştırma, veri sonu. Yorum cümleleri rakamlardan kuralla yazılır. */
export default function FairResult() {
  const { id = '' } = useParams();
  const qc = useQueryClient();
  const meta = useQuery({ queryKey: ['ev', 'meta'], queryFn: evApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const q = useQuery({ queryKey: ['ev', 'result', id], queryFn: () => evApi.result(id), enabled: ENGINE_ENABLED && !!id });
  const refresh = useMutation({
    mutationFn: () => evApi.result(id, true),
    onSuccess: (d) => {
      qc.setQueryData(['ev', 'result', id], d);
      qc.invalidateQueries({ queryKey: ['ev', 'fair', id] });
      toast.success(d.result.complete ? 'Sonuç yeniden hesaplandı.' : 'Kaynaklardan biri okunamadı; sonuç kaydedilmedi.');
    },
    onError: (e) => toast.error(errText(e, 'Sonuç hesaplanamadı.') ?? ''),
  });
  const m = meta.data;
  const f = q.data?.fair;
  const r = q.data?.result;
  const deg = r?.prev?.degisim ?? null;

  return (
    <EventsFrame
      crumb="Fuar ve etkinlik"
      title={f ? `${f.name} — sonuç` : 'Fuar sonucu'}
      lead={f ? `${fmtRange(f.startsOn, f.endsOn)} · ${[f.venue, f.city].filter(Boolean).join(', ') || f.kindLabel}` : undefined}
      source={`Logo ${m?.settings.channel ?? 'FUAR'} kanalı · CRM sipariş`}
      presence={r ? `veri sonu ${fmtDay(r.dataEnd)}` : '…'}
      detail={f ? `${f.name} · sonuç` : undefined}
      back={{ to: `/etkinlikler/fuar/${encodeURIComponent(id)}`, label: 'Fuar kartı' }}
      nav={false}
      aside={
        <div className="flex flex-wrap gap-2 lg:justify-end">
          <button type="button" className={btnGhost} disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            <RefreshCw aria-hidden className={`h-4 w-4 ${refresh.isPending ? 'animate-spin' : ''}`} />
            Yeniden hesapla
          </button>
          {m?.me.canExport && r?.complete && (
            <a className={btnGhost} href={evApi.pdfUrl(id)}>
              <Download aria-hidden className="h-4 w-4" />
              PDF
            </a>
          )}
        </div>
      }
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone="err">{errText(q.error, 'Sonuç açılamadı.')}</Note>}
      {r && (
        <>
          {r.warnings.map((w) => <Note key={w} tone="warn">{w}</Note>)}
          {r.cached && <p className="px-1 text-[11.5px] text-canvas-muted">Kayıtlı sonuç ({fmtDay(r.computedAt.slice(0, 10))} hesaplandı). Güncel veri için «Yeniden hesapla».</p>}
          <KpiRow>
            <Kpi label="Net satış" value={fmtMoney(r.netCiro)} help={`${fmtInt(r.netAdet)} adet · ${r.kitapSayisi} kitap (${r.channel ?? 'fuar'} kanalı)`} info={<SqlInfo k={q.data?.kaynaklar} alan="result.netCiro" label="Net satış" />} />
            <Kpi label="Geçen yıla göre" value={deg !== null ? `${deg >= 0 ? '+' : ''}${fmtPct(deg, 1)}` : '—'}
              help={r.prev ? `${r.prev.label}: ${fmtMoney(r.prev.netCiro)}` : 'Karşılaştırma yok'} info={<SqlInfo k={q.data?.kaynaklar} alan="result.prev" label="Geçen yıla göre" />} />
            <Kpi label="Gider" value={fmtMoney(r.toplamGider)} help={r.butce != null ? `Bütçe ${fmtMoney(r.butce)} · fark ${fmtMoney(r.butceFarki)}` : 'Bütçe girilmedi'} info={<SqlInfo k={q.data?.kaynaklar} alan="result.toplamGider" label="Gider" />} />
            <Kpi label="1 ₺ gidere satış" value={fmtRatio(r.roi)} help="Net satış ÷ toplam gider" info={<SqlInfo k={q.data?.kaynaklar} alan="result.roi" label="1 ₺ gidere satış" />} />
          </KpiRow>

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3 lg:gap-4">
            <div className="flex min-w-0 flex-col gap-3 lg:col-span-2 lg:gap-4">
              <Block title="Özet" info={<SqlInfo k={q.data?.kaynaklar} alan="result.netCiro" label={`Fuar satışı ${fmtDay(r.window.from)} – ${fmtDay(r.window.to)}${r.clientCodes.length ? `, cariler ${r.clientCodes.join(', ')}` : ''}`} />}>
                <ul className="flex list-disc flex-col gap-1 pl-5 text-[13px] leading-snug">
                  {r.summary.map((s) => <li key={s}>{s}</li>)}
                </ul>
              </Block>
              <Block title={`Kitaplar (${r.books.length})`} info={<SqlInfo k={q.data?.kaynaklar} alan="result.books" label="Kitaplar" />} help="Net satışa göre. Planlanan adet kitap listesinden; geçen yıl temel dönemden.">
                {r.books.length === 0 ? <p className="text-[12.5px] text-canvas-muted">Bu günlerde fuar kanalında satış yok.</p> : (
                  <TableWrap>
                    <thead>
                      <tr>
                        <th className={th}>Kitap</th>
                        <th className={`${th} text-right`}>Adet</th>
                        <th className={`${th} text-right`}>Net satış</th>
                        <th className={`${th} text-right`}>Planlanan</th>
                        <th className={`${th} text-right`}>Geçen yıl</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.books.map((b) => (
                        <tr key={b.stokKodu} className="border-t border-slate-100">
                          <td className={td}><div className="max-w-[320px] truncate font-bold">{b.ad ?? b.stokKodu}</div><div className="font-mono text-[10.5px] text-canvas-muted">{b.stokKodu}</div></td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.adet)}</td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(b.ciro)}</td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.planlanan)}</td>
                          <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.gecenYilAdet)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </TableWrap>
                )}
                {r.unsoldPlanned.length > 0 && (
                  <p className="mt-2 text-[12px] text-canvas-muted">
                    Planlanıp hiç satılmayan: {r.unsoldPlanned.map((u) => `${u.ad ?? u.stokKodu} (${fmtInt(u.planlanan)})`).join(', ')}
                  </p>
                )}
              </Block>
            </div>
            <div className="flex min-w-0 flex-col gap-3 lg:gap-4">
              <Block title="CRM siparişleri" info={<SqlInfo k={q.data?.kaynaklar} alan="result.orders" label="CRM siparişleri" />} help="Sipariş tarihi fuar günlerinde olan fuar, etkinlik ve imza siparişleri (iptal ve birleştirilenler hariç).">
                {r.orders.length === 0 && <p className="text-[12.5px] text-canvas-muted">Sipariş yok.</p>}
                <ul className="flex flex-col gap-1 text-[12.5px]">
                  {r.orders.map((o) => (
                    <li key={o.tip} className="flex justify-between gap-2"><span>{o.ad} · {o.adet}</span><span className="font-mono tabular-nums">{fmtMoney(o.tutar)}</span></li>
                  ))}
                </ul>
              </Block>
              <Block title="Gider" info={<SqlInfo k={q.data?.kaynaklar} alan="result.costs" label="Gider" />}>
                <ul className="flex flex-col gap-1 text-[12.5px]">
                  {Object.entries(r.costs.byKind).map(([k, v]) => (
                    <li key={k} className="flex justify-between gap-2"><span>{k}</span><span className="font-mono tabular-nums">{fmtMoney(v)}</span></li>
                  ))}
                  {r.costs.crm > 0 && <li className="flex justify-between gap-2"><span>CRM etkinlik kaydındaki gider</span><span className="font-mono tabular-nums">{fmtMoney(r.costs.crm)}</span></li>}
                  <li className="flex justify-between gap-2 border-t border-slate-100 pt-1 font-bold"><span>Toplam</span><span className="font-mono tabular-nums">{fmtMoney(r.toplamGider)}</span></li>
                </ul>
              </Block>
              <Block title="CRM etkinlikleri" info={<SqlInfo k={q.data?.kaynaklar} alan="result.crmEvents" label="CRM etkinlikleri" />} help="Karta bağlı kayıtlar: katılımcı ve satılan adet CRM'de girildiği gibi.">
                {r.crmEvents.length === 0 && <p className="text-[12.5px] text-canvas-muted">Karta CRM etkinliği bağlanmadı.</p>}
                <ul className="flex flex-col gap-1 text-[12px]">
                  {r.crmEvents.map((e) => (
                    <li key={e.id}>{fmtDay(e.baslangic)} · {e.ad} · {e.durum}{e.katilimci != null ? ` · ${fmtInt(e.katilimci)} katılımcı` : ''}{e.satilan != null ? ` · ${fmtInt(e.satilan)} satılan` : ''}</li>
                  ))}
                </ul>
              </Block>
              <Block title="Cariler" info={<SqlInfo k={q.data?.kaynaklar} alan="result.clients" label="Cariler" />} help="Fuar kanalı satışının cari kırılımı.">
                <ul className="flex flex-col gap-1 text-[12px]">
                  {r.clients.map((c) => (
                    <li key={c.kod} className="flex justify-between gap-2"><span className="min-w-0 truncate"><span className="font-mono">{c.kod}</span> {c.ad}</span><span className="shrink-0 font-mono tabular-nums">{fmtMoney(c.ciro)}</span></li>
                  ))}
                </ul>
              </Block>
            </div>
          </div>
        </>
      )}
    </EventsFrame>
  );
}
