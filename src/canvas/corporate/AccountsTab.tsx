import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Search } from 'lucide-react';
import Sheet from '../editorial/studio/reader/Sheet';
import { Loading, Note, Pill, TableWrap, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Pager, Panel, useDebounced } from '../editorial/kit';
import { ENGINE_ENABLED } from '../engine';
import { StagePill } from './parts';
import { corporateApi, fmtDay, fmtMonth, fmtPct, fmtShort, growth, monthName, type Meta } from './api';

function AccountSheet({ refId, meta, onClose }: { refId: string | null; meta: Meta; onClose: () => void }) {
  const qc = useQueryClient();
  const a = useQuery({ queryKey: ['corporate', 'account', refId], queryFn: () => corporateApi.account(refId!), enabled: ENGINE_ENABLED && !!refId });
  const seg = useMutation({
    mutationFn: (s: string | null) => corporateApi.setSegment(refId!, s),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['corporate'] });
      toast.success('Segment kaydedildi.');
    },
    onError: (e) => toast.error(errText(e, 'Segment kaydedilemedi.') ?? ''),
  });
  const x = a.data;
  return (
    <Sheet open={!!refId} onClose={onClose} wide title={x?.unvan ?? refId ?? 'Kurum'}
      subtitle={x ? [x.logoKod, x.il, x.crmRol ? `CRM rolü: ${x.crmRol}` : null, x.temsilci ? `temsilci ${x.temsilci}` : null].filter(Boolean).join(' · ') : undefined}>
      {a.isLoading && <Loading />}
      {a.error && <Note tone="err">{errText(a.error, 'Kurum okunamadı.')}</Note>}
      {x && (
        <div className="flex flex-col gap-4 text-[12.5px]">
          <label className="flex flex-col gap-1">
            <span className={labelCls}>Segment</span>
            <select className={field} value={x.segment ?? ''} disabled={!meta.me.canQuote || seg.isPending} onChange={(e) => seg.mutate(e.target.value || null)}>
              <option value="">Belirsiz</option>
              {Object.entries(meta.segments).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <span className="text-[11px] text-canvas-muted">
              Kaynak: {x.segmentKaynak ? meta.segmentSources[x.segmentKaynak] : 'yok'}
              {x.segmentKaynak === 'oneri' ? ' — seçip kaydederseniz elle onaylanmış olur.' : ''}
            </span>
          </label>
          <section>
            <h3 className="text-[14px] font-extrabold">Alım geçmişi (Logo, KURUM kanalı)</h3>
            {x.window && (
              <p className="text-[11.5px] text-canvas-muted">
                {x.window.year} {x.window.label}: {fmtShort(x.buYil)} · geçen yıl aynı dönem {fmtShort(x.gecenYilAyni)}
                {growth(x.buYil, x.gecenYilAyni) !== null ? ` (${fmtPct(growth(x.buYil, x.gecenYilAyni))})` : ''}. Veri {fmtDay(x.dataEnd)} tarihine kadar.
              </p>
            )}
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[520px] text-[11.5px]">
                <thead>
                  <tr><th className={th}>Yıl</th>{Array.from({ length: 12 }, (_, i) => <th key={i} className={`${th} text-right`}>{monthName(i + 1).slice(0, 3)}</th>)}<th className={`${th} text-right`}>Toplam</th></tr>
                </thead>
                <tbody>
                  {x.yillar.map((y) => (
                    <tr key={y.yil} className="border-t border-slate-100">
                      <td className={td}>{y.yil}</td>
                      {y.aylar.map((v, i) => <td key={i} className={`${td} text-right font-mono tabular-nums ${v > 0 ? 'font-bold' : 'text-canvas-muted'}`}>{v ? fmtShort(v).replace(' ₺', '') : '·'}</td>)}
                      <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtShort(y.ciro)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {x.enCokAy && <p className="mt-1 text-[11.5px] text-canvas-muted">En çok alım yaptığı ay: {monthName(x.enCokAy)}.</p>}
            {x.yillar.length === 0 && <p className="text-[12px] text-canvas-muted">Bu kurumun KURUM kanalında faturalı alımı yok.</p>}
          </section>
          <section>
            <h3 className="text-[14px] font-extrabold">Fırsatlar</h3>
            <ul className="mt-1 flex flex-col gap-1">
              {x.firsatlar.map((o) => (
                <li key={o.id}>
                  <Link to={`/kurumsal-satis/firsat/${o.id}`} className="flex min-h-11 items-center justify-between gap-2 rounded-xl bg-slate-50 px-3 py-2 hover:bg-slate-100">
                    <span className="min-w-0 truncate font-bold">{o.ad}</span>
                    <StagePill stage={o.asama} label={o.asamaLabel} />
                  </Link>
                </li>
              ))}
              {x.firsatlar.length === 0 && <li className="text-canvas-muted">Fırsat yok.</li>}
            </ul>
          </section>
          {x.hatirlatmalar.length > 0 && (
            <section>
              <h3 className="text-[14px] font-extrabold">Dönemsel hatırlatmalar</h3>
              <ul className="mt-1 flex flex-col gap-1">
                {x.hatirlatmalar.map((r) => (
                  <li key={r.id} className="flex items-center justify-between">
                    <span>{fmtMonth(r.donemAyi)} · geçen yıl {fmtShort(r.gecenYilTutar)}</span>
                    <Pill tone={r.durum === 'acik' ? 'warn' : 'muted'}>{r.durumLabel}</Pill>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </Sheet>
  );
}

export default function AccountsTab({ meta }: { meta: Meta }) {
  const [q, setQ] = useState('');
  const dq = useDebounced(q, 250);
  const [segment, setSegment] = useState('');
  const [sort, setSort] = useState('ciro');
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ['corporate', 'accounts', dq, segment, sort, page],
    queryFn: () => corporateApi.accounts({ q: dq, segment, sort, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const d = list.data;
  return (
    <Panel>
      <div className="flex flex-wrap items-end gap-2">
        <label className="relative min-w-[200px] flex-1">
          <span className="sr-only">Ara</span>
          <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-canvas-muted" />
          <input className={`${field} pl-9`} value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} placeholder="Unvan, cari kodu ya da il" />
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Segment</span>
          <select className={field} value={segment} onChange={(e) => { setSegment(e.target.value); setPage(0); }}>
            <option value="">Hepsi</option>
            {Object.entries(meta.segments).map(([k, v]) => <option key={k} value={k}>{v}{d?.segments[k] ? ` (${d.segments[k]})` : ''}</option>)}
            <option value="oneri">ZEKİ AI önerisi (onay bekliyor)</option>
            <option value="bos">Belirsiz{d?.segments.bos ? ` (${d.segments.bos})` : ''}</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className={labelCls}>Sıra</span>
          <select className={field} value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="ciro">Bu yıl alım</option>
            <option value="gecen">Geçen yıl alım</option>
            <option value="son">Son alım</option>
            <option value="ad">Unvan</option>
          </select>
        </label>
      </div>
      <p className="mt-2 text-[11.5px] text-canvas-muted">
        Logo'da özel kod 2 = {meta.settings.channel} olan cariler ve CRM'de kurum rolü/kanalı KURUM olan kartlar. Tutarlar net ciro (faturalı satır, iade düşülmüş).
      </p>
      {list.error && <Note tone="err">{errText(list.error, 'Kurumlar okunamadı.')}</Note>}
      {list.isLoading && <Loading />}
      {d && (
        <div className="mt-3">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Kurum</th>
                <th className={th}>Segment</th>
                <th className={`${th} text-right`}>{d.window ? `${d.window.year} ${d.window.label}` : 'Bu yıl'}</th>
                <th className={`${th} text-right`}>Geçen yıl aynı dönem</th>
                <th className={th}>Son alım</th>
                <th className={th}>Temsilci</th>
              </tr>
            </thead>
            <tbody>
              {d.items.map((a) => (
                <tr key={a.ref} className="cursor-pointer border-t border-slate-100 hover:bg-slate-50" onClick={() => setOpen(a.ref)}>
                  <td className={td}>
                    <button type="button" className="text-left font-bold hover:underline" onClick={() => setOpen(a.ref)}>{a.unvan ?? a.ref}</button>
                    <div className="text-[11px] text-canvas-muted">{[a.logoKod, a.il, a.pasif ? 'pasif cari' : null].filter(Boolean).join(' · ')}</div>
                  </td>
                  <td className={td}>
                    {a.segmentLabel ? <Pill tone={a.segmentKaynak === 'oneri' ? 'warn' : 'muted'}>{a.segmentLabel}{a.segmentKaynak === 'oneri' ? ' ?' : ''}</Pill> : <span className="text-canvas-muted">—</span>}
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtShort(a.buYil)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtShort(a.gecenYilAyni)}</td>
                  <td className={td}>{fmtDay(a.sonAlim)}</td>
                  <td className={td}>{a.temsilci ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
          <Pager page={page} pageSize={d.pageSize} total={d.total} shown={d.items.length} loading={list.isLoading} fetching={list.isFetching} onPage={setPage} />
        </div>
      )}
      <AccountSheet refId={open} meta={meta} onClose={() => setOpen(null)} />
    </Panel>
  );
}
