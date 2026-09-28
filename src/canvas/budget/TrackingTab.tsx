import { useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, errText, td, th } from '../admin/ui';
import ReasonSheet from '../reason/ReasonSheet';
import { reasonApi } from '../reason/api';
import { Panel } from '../editorial/kit';
import { DEPT, budgetApi, fmtDay, fmtInt, fmtMoney, fmtPct, fmtShort, type GroupTrack, type Plan, type TrackState, type YearEnd } from './api';
import { RatioBar, StatePill } from './parts';

const AY = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];

/** Tahmini yıl sonu kapanışı: gerçekleşen + yılın kalan günleri için tahmin bandı (kitap hedefleri kapsamı). Aralık
 *  önbellekte yoksa yalnız temel tahmin yazılır, aralık uydurulmaz. */
function YearEndPanel({ y }: { y: YearEnd }) {
  const share = (v: number | null) => (v === null || !y.hedefCiro ? null : Math.round((v / y.hedefCiro) * 100));
  const cells: Array<[string, number | null]> = [['Muhafazakâr', y.p10], ['Temel', y.p50], ['İyimser', y.p90]];
  const missing = y.eksikAylar.map((m) => AY[m - 1]).join(', ');
  return (
    <Panel>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[15px] font-extrabold">Tahmini yıl sonu kapanışı</h3>
        <span className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[10.5px] font-extrabold uppercase tracking-wide text-canvas-violet">tahmin</span>
      </div>
      <div className="mt-2 grid grid-cols-1 gap-2 min-[420px]:grid-cols-3">
        {cells.map(([k, v]) => (
          <div key={k} className={`rounded-xl px-3 py-2 ${k === 'Temel' ? 'bg-violet-50/80' : 'bg-slate-50'}`}>
            <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{k}</div>
            <div className="font-mono text-[18px] font-bold tabular-nums">{v === null ? '—' : fmtShort(v) + ' ₺'}</div>
            <div className="text-[11px] text-canvas-muted">
              {v === null ? 'aralık yok' : share(v) === null ? '' : 'hedefin %' + share(v) + '’i'}
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
        {fmtInt(y.kitap)} kitap (hedef cirosunun {y.kapsamPay === null ? '—' : '%' + Math.round(y.kapsamPay * 100)}’i): {fmtDay(y.asof)} itibarıyla
        gerçekleşen {fmtShort(y.gercekCiro)} ₺ + yılın kalan günleri için ZEKİ AI satış tahmini, hedefteki birim fiyatla ciroya
        çevrilir. Aralık aylık tahmin aralıklarının toplamıdır.
        {missing ? ' Tahminin kapsamadığı aylar (' + missing + ') eklenmedi.' : ''}
      </p>
    </Panel>
  );
}

function Summary({ title, g, help }: { title: string; g: GroupTrack; help: string }) {
  return (
    <div className="glass-panel rounded-2xl p-3.5 shadow-glass-float sm:rounded-3xl sm:p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">{title}</div>
        <StatePill state={g.durum} />
      </div>
      <div className="mt-1 font-mono text-[26px] font-bold leading-none tabular-nums tracking-tight">{fmtPct(g.oran, 0)}</div>
      <div className="mt-2">
        <RatioBar ratio={g.oran} state={g.durum} />
      </div>
      <div className="mt-2 grid grid-cols-2 gap-x-2 text-[11.5px] leading-snug text-canvas-muted">
        <span>Gerçekleşen</span>
        <span className="text-right font-mono tabular-nums text-canvas-ink">{fmtShort(g.gercekCiro)} ₺</span>
        <span>Beklenen (bugüne)</span>
        <span className="text-right font-mono tabular-nums">{fmtShort(g.beklenenCiro)} ₺</span>
        <span>Yıllık hedef</span>
        <span className="text-right font-mono tabular-nums">{fmtShort(g.hedefCiro)} ₺</span>
      </div>
      <p className="mt-2 text-[11px] leading-snug text-canvas-muted">{help}</p>
    </div>
  );
}

function GroupTable({ title, rows, threshold }: { title: string; rows: GroupTrack[]; threshold: number }) {
  return (
    <Panel>
      <h3 className="mb-2 text-[15px] font-extrabold">{title}</h3>
      <TableWrap>
        <thead>
          <tr>
            <th className={th}>Ad</th>
            <th className={`${th} text-right`}>Kitap</th>
            <th className={`${th} text-right`}>Yıllık hedef</th>
            <th className={`${th} text-right`}>Beklenen</th>
            <th className={`${th} text-right`}>Gerçekleşen</th>
            <th className={th}>Oran</th>
            <th className={th}>Durum</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.ad} className="border-t border-slate-100">
              <td className={`${td} font-semibold`}>{r.ad}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(r.kitap)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.hedefCiro)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.beklenenCiro)}</td>
              <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(r.gercekCiro)}</td>
              <td className={td}><RatioBar ratio={r.oran} state={r.durum} threshold={threshold} /></td>
              <td className={td}><StatePill state={r.durum} /></td>
            </tr>
          ))}
        </tbody>
      </TableWrap>
    </Panel>
  );
}

function Deviations({ year, planId }: { year: number; planId: string }) {
  const [status, setStatus] = useState('acik');
  const [page, setPage] = useState(0);
  const [why, setWhy] = useState<{ id: string; title: string } | null>(null);
  const q = useQuery({
    queryKey: ['budget', 'deviations', year, status, page],
    queryFn: () => budgetApi.deviations(year, { status, page }),
    enabled: ENGINE_ENABLED,
    placeholderData: keepPreviousData,
  });
  const items = (q.data?.items ?? []).filter((d) => d.planId === planId || status !== 'acik');
  return (
    <Panel>
      <div className="mb-2 flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-[15px] font-extrabold">Uyarılar</h3>
          <p className="text-[12px] text-canvas-muted">Saatlik denetimde açılır, eşiğin üstüne çıkınca kendiliğinden kapanır. Satış uyarıları pazarlama planı, dağılım ve saha modüllerine gider.</p>
        </div>
        <div className="flex gap-1 rounded-xl bg-slate-100 p-1">
          {[['acik', 'Açık'], ['kapandi', 'Kapanan'], ['bilgi', 'Hedef güncellemeleri']].map(([k, l]) => (
            <button key={k} type="button" onClick={() => { setStatus(k); setPage(0); }}
              className={`min-h-9 rounded-lg px-2.5 text-[12px] font-extrabold ${status === k ? 'bg-white shadow-sm' : 'text-canvas-muted'}`}>{l}</button>
          ))}
        </div>
      </div>
      {q.isLoading ? <Loading /> : q.error ? <Note tone="err">{errText(q.error, 'Uyarılar okunamadı.')}</Note> : !items.length ? (
        <Note tone="ok">{status === 'acik' ? 'Açık uyarı yok.' : 'Kayıt yok.'}</Note>
      ) : (
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Konu</th>
              <th className={th}>Tür</th>
              <th className={`${th} text-right`}>Beklenen</th>
              <th className={`${th} text-right`}>Gerçekleşen</th>
              <th className={`${th} text-right`}>Oran</th>
              <th className={th}>Kime gider</th>
              <th className={th}>İlk görülme</th>
              <th className={th}><span className="sr-only">Neden</span></th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} className="border-t border-slate-100">
                <td className={`${td} max-w-[320px] font-semibold`}>{d.label}</td>
                <td className={td}>
                  <Pill tone={d.kind === 'gider' ? 'err' : d.kind === 'revizyon' ? 'violet' : 'warn'}>
                    {d.kind === 'gider' ? 'Bütçe aşımı' : d.kind === 'revizyon' ? 'Hedef güncellendi' : { kitap: 'Kitap', yayinevi: 'Yayınevi', toplam: 'Şirket', segment: 'Segment', merkez: 'Departman' }[d.scope]}
                  </Pill>
                </td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(d.expected)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(d.actual)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(d.ratio, 0)}</td>
                <td className={`${td} text-[11.5px] text-canvas-muted`}>{d.modules.length ? d.modules.join(', ') : 'Bütçe sorumlusu'}</td>
                <td className={`${td} whitespace-nowrap text-[11.5px] text-canvas-muted`}>{fmtDay(d.firstAt)}</td>
                <td className={td}>
                  {(d.kind === 'satis' || d.kind === 'gider') && (
                    <button type="button" className={`${btnGhost} !min-h-9 !px-2.5`} onClick={() => setWhy({ id: d.id, title: d.label ?? d.key })}>
                      Neden?
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
      {q.data && q.data.total > q.data.pageSize && (
        <div className="mt-2 flex items-center justify-end gap-2 text-[12px] font-semibold text-canvas-muted">
          <span className="font-mono tabular-nums">{page * q.data.pageSize + 1}–{Math.min(q.data.total, (page + 1) * q.data.pageSize)} / {q.data.total}</span>
          <button type="button" className="min-h-9 rounded-lg bg-slate-100 px-3" disabled={page === 0} onClick={() => setPage(page - 1)}>Önceki</button>
          <button type="button" className="min-h-9 rounded-lg bg-slate-100 px-3" disabled={(page + 1) * q.data.pageSize >= q.data.total} onClick={() => setPage(page + 1)}>Sonraki</button>
        </div>
      )}
      <ReasonSheet target={why} load={reasonApi.budget} onClose={() => setWhy(null)} />
    </Panel>
  );
}

export default function TrackingTab({ plan, trackable, onFilter }: { plan: Plan; trackable: boolean; onFilter: (d: TrackState) => void }) {
  const q = useQuery({
    queryKey: ['budget', 'tracking', plan.year, plan.id],
    queryFn: () => budgetApi.tracking(plan.year, plan.id),
    enabled: ENGINE_ENABLED && trackable,
  });
  if (!trackable) {
    return <Note tone="info">{plan.year} dönemi için Logo'da henüz gerçekleşme yok. Plan onaylandıktan sonra yıl başladığında izleme kendiliğinden açılır.</Note>;
  }
  if (q.isLoading) return <Loading />;
  if (q.error) return <Note tone="err">{errText(q.error, 'İzleme hesaplanamadı.')}</Note>;
  const d = q.data;
  if (!d?.sirket || !d.kitapHedefleri) return <Note tone="info">Bu plan için izleme verisi yok.</Note>;
  const esik = d.esik ?? 0.8;
  const counts = d.durumlar;
  const chart = (d.aylar ?? []).map((m) => ({ ay: AY[m.ay - 1], Hedef: Math.round(m.hedef), Gerçekleşen: m.gercek === null ? null : Math.round(m.gercek) }));

  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      {plan.status !== 'onayli' && <Note tone="info">Bu plan henüz yürürlükte değil; aşağıdaki izleme «onaylansaydı» görünümüdür, uyarı açmaz.</Note>}
      <p className="px-1 text-[12px] font-semibold text-canvas-muted">
        {fmtDay(d.asof)} itibarıyla · yılın %{Math.round((d.gecenPay ?? 0) * 100)}'i geçti · eşik %{Math.round(esik * 100)} · beklenen, hedefin taban dönemdeki aylık satış dağılımına göre bugüne düşen payıdır.
        {d.uyariKapsam && (
          <> Kitap uyarısı hedef cirosunun %{Math.round(d.uyariKapsam.pay * 100)}'ini oluşturan {fmtInt(d.uyariKapsam.kitap)} kitap için açılır; bunların {fmtInt(d.uyariKapsam.sapma)}'i eşik altında. Diğer kitapların durumu Kitap hedefleri listesinde.</>
        )}
      </p>
      {d.yilSonu && <YearEndPanel y={d.yilSonu} />}
      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4 lg:gap-4">
        <Summary title="Şirket satışı" g={d.sirket} help="Kitap hedefleri + yeni kitap programı; gerçekleşende planda olmayan kitapların satışı da var." />
        <Summary title="Kitap hedefleri" g={d.kitapHedefleri} help="Yalnız planda adıyla hedefi olan kitaplar." />
        <div className="glass-panel rounded-2xl p-3.5 shadow-glass-float sm:rounded-3xl sm:p-4">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Kitap durumu</div>
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            {(['sapma', 'izle', 'iyi', 'baslamadi'] as TrackState[]).map((k) => (
              <button key={k} type="button" onClick={() => onFilter(k)}
                className="flex min-h-11 flex-col items-start rounded-xl bg-white/70 px-2.5 py-1.5 text-left transition-transform duration-150 ease-out active:scale-[0.97]">
                <StatePill state={k} />
                <span className="mt-0.5 font-mono text-[18px] font-bold tabular-nums">{fmtInt(counts?.[k] ?? 0)}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="glass-panel rounded-2xl p-3.5 shadow-glass-float sm:rounded-3xl sm:p-4">
          <div className="text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Departman bütçesi</div>
          <div className="mt-1 font-mono text-[26px] font-bold leading-none tabular-nums tracking-tight">{fmtPct(d.gider?.kullanim ?? null, 0)}</div>
          <div className="mt-2 grid grid-cols-2 gap-x-2 text-[11.5px] leading-snug text-canvas-muted">
            <span>Gerçekleşen</span>
            <span className="text-right font-mono tabular-nums text-canvas-ink">{fmtShort(d.gider?.gercek ?? 0)} ₺</span>
            <span>Dönem bütçesi</span>
            <span className="text-right font-mono tabular-nums">{fmtShort(d.gider?.butceDonem ?? 0)} ₺</span>
            <span>Yıllık bütçe</span>
            <span className="text-right font-mono tabular-nums">{fmtShort(d.gider?.butce ?? 0)} ₺</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${DEPT.asim.pill}`}>{d.gider?.asim ?? 0} kalem aşıldı</span>
            <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-bold ${DEPT.yaklasti.pill}`}>{d.gider?.yaklasti ?? 0} kalem sınırda</span>
          </div>
        </div>
      </div>

      <Panel>
        <h3 className="text-[15px] font-extrabold">Ay ay net ciro: hedef ve gerçekleşen</h3>
        <p className="mb-2 text-[12px] text-canvas-muted">
          Hedef, planın toplam cirosunun aylara dağılımıdır. Planda olmayan kitapların satışı gerçekleşene dahil ({fmtShort(d.hedefDisi?.ciro ?? 0)} ₺, {fmtInt(d.hedefDisi?.kitap ?? 0)} kitap).
          {(d.aylar ?? []).some((m) => m.gecen > 0 && m.gecen < 1) && ' Verinin bittiği ay yarımdır.'}
        </p>
        <div className="h-[260px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chart} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="ay" tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <YAxis tickFormatter={(v: number) => fmtShort(v)} tick={{ fontSize: 11 }} width={56} tickLine={false} axisLine={false} />
              <Tooltip formatter={(v) => (typeof v === 'number' ? fmtMoney(v) : '—')} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Hedef" fill="#c4b5fd" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="Gerçekleşen" fill="#6d28d9" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Panel>

      <Deviations year={plan.year} planId={plan.id} />
      {d.segmentler && <GroupTable title="Yeni kitap ve backlist" rows={d.segmentler} threshold={esik} />}
      {d.yayinevleri && <GroupTable title="Yayınevlerine göre" rows={d.yayinevleri} threshold={esik} />}
    </div>
  );
}
