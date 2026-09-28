import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, TableWrap, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { commerceApi, fmtChange, fmtDay, fmtInt, fmtRatio, fmtTl, type Period } from './api';
import { Delta, ROOT, SegmentPill } from './parts';

const PERIODS: Array<{ key: Period; label: string }> = [
  { key: 'dun', label: 'Dün' },
  { key: 'hafta', label: 'Son 7 gün' },
  { key: 'ay', label: 'Bu ay' },
];

/** Sabah özeti (telefon öncelikli): sipariş, site cirosu, sepet, yeni/tekrar müşteri; Logo kanal cirosuyla uzlaşma; en çok satan 10. */
export default function CommerceHome() {
  const [period, setPeriod] = useState<Period>('dun');
  const q = useQuery({ queryKey: ['commerce', 'overview', period], queryFn: () => commerceApi.overview(period), enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const o = q.data;

  const tabs = (
    <div role="tablist" aria-label="Dönem" className="flex w-full gap-1 rounded-2xl bg-slate-100 p-1 sm:w-max">
      {PERIODS.map((p) => (
        <button
          key={p.key}
          type="button"
          role="tab"
          aria-selected={period === p.key}
          onClick={() => setPeriod(p.key)}
          className={`min-h-11 flex-1 rounded-xl px-3 text-[12.5px] font-extrabold transition-colors duration-150 sm:min-h-9 sm:flex-none ${
            period === p.key ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:bg-white/60'
          }`}
        >
          {p.label}
        </button>
      ))}
    </div>
  );

  if (q.isLoading) return <div className="flex flex-col gap-3">{tabs}<Loading /></div>;
  if (q.error) return <div className="flex flex-col gap-3">{tabs}<Note tone="err">{errText(q.error, 'Özet açılamadı.')}</Note></div>;
  if (!o) return null;
  if (!o.freshness.okAt) {
    return (
      <Note tone="info">
        Site siparişleri henüz okunmadı. Gece turu her gün 02:50'de okur; yetkisi olan kişi «Veri ve eşikler» bölümünden hemen başlatabilir.
        {o.freshness.error ? ` Son deneme: ${o.freshness.error}` : ''}
      </Note>
    );
  }
  const c = o.cur;
  const lg = o.logo;
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {tabs}
        <span className="text-[11.5px] font-semibold text-canvas-muted">
          {o.period.label}: {fmtDay(o.period.from)}{o.period.to !== o.period.from ? ` – ${fmtDay(o.period.to)}` : ''} · veri {fmtDay(o.freshness.okAt)}
          <SqlInfo k={o.kaynaklar} alan="freshness" label="Site okuması" className="ml-1" />
          {o.freshness.stale && <span className="text-amber-800"> (güncel değil)</span>}
        </span>
      </div>

      {o.freshness.error && <Note tone="err">Son okuma başarısız: {o.freshness.error}</Note>}
      {o.drop.uyari && (
        <Note tone="warn">
          {fmtDay(o.drop.gun)} günü {fmtInt(o.drop.siparis)} sipariş geldi; önceki dört haftanın aynı günü ortalaması {fmtInt(o.drop.ortalama)}
          ({fmtChange(o.drop.dusus != null ? -o.drop.dusus : null)}).
          <SqlInfo k={o.kaynaklar} alan="drop" label="Sipariş düşüşü uyarısı" className="ml-1" />
        </Note>
      )}

      <KpiRow>
        <Kpi label="Sipariş" value={fmtInt(c.siparis)} help={`Önceki döneme ${fmtChange(o.change.siparis)} · iptal/iade ${fmtInt(c.iptal)}`}
          info={<SqlInfo k={o.kaynaklar} alan="cur" label="Sipariş" />} />
        <Kpi label="Site cirosu" value={fmtTl(c.ciro)} help={`Önceki döneme ${fmtChange(o.change.ciro)} · sitenin kendi tutarı`}
          info={<SqlInfo k={o.kaynaklar} alan="cur" label="Site cirosu" />} />
        <Kpi label="Sepet ortalaması" value={fmtTl(c.sepet)} help={`Önceki döneme ${fmtChange(o.change.sepet)}`}
          info={<SqlInfo k={o.kaynaklar} alan="cur" label="Sepet ortalaması" />} />
        <Kpi label="Müşteri" value={fmtInt(c.musteri)} help={`Yeni ${fmtInt(c.yeni)} · tekrar ${fmtInt(c.tekrar)} · misafir sipariş ${fmtInt(c.misafir)}`}
          info={<SqlInfo k={o.kaynaklar} alan="cur" label="Müşteri" />} />
      </KpiRow>

      <div className="grid gap-3 lg:grid-cols-[1.1fr_1fr] lg:gap-4">
        <Panel>
          <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Site cirosu ve Logo e-ticaret kanalı <SqlInfo k={o.kaynaklar} alan="logo" label="Site cirosu ve Logo uzlaşması" /></h2>
          {!lg.bagli ? (
            <p className="mt-1 text-[12.5px] text-canvas-muted">{lg.neden}</p>
          ) : (
            <>
              <p className="mt-0.5 text-[11.5px] text-canvas-muted">
                {lg.ayAdi} {lg.yil}{lg.kismiAy ? ` (Logo verisi ${fmtDay(lg.veriSonu)} tarihine kadar)` : ''}. {lg.ayKaydi ?? ''}
              </p>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-[12px]">
                <div className="rounded-xl bg-slate-50 p-2.5"><dt className="font-bold text-canvas-muted">Site</dt><dd className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{fmtTl(lg.siteCiro)}</dd></div>
                <div className="rounded-xl bg-slate-50 p-2.5"><dt className="font-bold text-canvas-muted">Logo net</dt><dd className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{fmtTl(lg.netCiro)}</dd></div>
                <div className="rounded-xl bg-slate-50 p-2.5"><dt className="font-bold text-canvas-muted">Fark</dt><dd className="mt-0.5 font-mono text-[15px] font-bold tabular-nums">{fmtTl(lg.fark)}</dd><dd className="text-[11px] text-canvas-muted">{fmtChange(lg.farkOrani)}</dd></div>
              </dl>
              <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">{lg.not}</p>
            </>
          )}
        </Panel>
        <Panel>
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">Müşteri segmentleri <SqlInfo k={o.kaynaklar} alan="segments" label="Müşteri segmentleri" /></h2>
            <Link to={`${ROOT}/musteriler`} className="inline-flex min-h-11 items-center gap-1 text-[12px] font-extrabold text-canvas-violet sm:min-h-0">
              Matris <ArrowRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          </div>
          <ul className="mt-2 divide-y divide-slate-100 text-[12.5px]">
            {o.segments.map((s) => (
              <li key={s.segment} className="flex items-center justify-between gap-2 py-1.5">
                <Link to={`${ROOT}/musteriler?segment=${s.segment}`} className="min-h-11 content-center sm:min-h-0"><SegmentPill segment={s.segment} label={s.label} /></Link>
                <span className="font-mono tabular-nums text-canvas-muted">{fmtInt(s.musteri)} · {fmtRatio(s.pay, 0)} · {fmtTl(s.ciro)}</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <Panel>
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">En çok satan 10 kitap <SqlInfo k={o.kaynaklar} alan="top" label="En çok satan kitaplar" /></h2>
        {o.top.length === 0 ? (
          <p className="mt-1 text-[12.5px] text-canvas-muted">Bu dönemde satırlı sipariş yok.</p>
        ) : (
          <div className="mt-2">
            <TableWrap>
              <thead><tr><th className={th}>Kitap</th><th className={`${th} text-right`}><InfoLabel k={o.kaynaklar} alan="top">Adet</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={o.kaynaklar} alan="top">Sipariş</InfoLabel></th><th className={`${th} text-right`}><InfoLabel k={o.kaynaklar} alan="top">Tutar</InfoLabel></th></tr></thead>
              <tbody>
                {o.top.map((b) => (
                  <tr key={b.barkod} className="border-t border-slate-100">
                    <td className={td}><div className="font-bold">{b.ad ?? '—'}</div><div className="font-mono text-[11px] text-canvas-muted">{b.barkod}</div></td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.adet)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(b.siparis)}</td>
                    <td className={`${td} text-right font-mono tabular-nums`}>{fmtTl(b.tutar)}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
          </div>
        )}
        <p className="mt-2 text-[11.5px] text-canvas-muted">
          Önceki dönem ({fmtDay(o.period.prevFrom)}{o.period.prevTo !== o.period.prevFrom ? ` – ${fmtDay(o.period.prevTo)}` : ''}):{' '}
          {fmtInt(o.prev.siparis)} sipariş, {fmtTl(o.prev.ciro)}; bu dönem <Delta value={o.change.ciro} text={fmtChange(o.change.ciro)} /> ciro.
          <SqlInfo k={o.kaynaklar} alan="prev" label="Önceki dönem" className="ml-1" />
        </p>
      </Panel>
    </div>
  );
}
