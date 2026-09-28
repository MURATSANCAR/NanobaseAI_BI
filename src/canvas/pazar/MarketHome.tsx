import { useState } from 'react';
import { Link } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { ArrowRight, FileText } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, errText, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { canOpenRoute, usePageAccess } from '../useAdmin';
import { STATUS_TONE, fmtDay, fmtGrowth, fmtInt, fmtNum, fmtPct, fmtTlShort, lastMonth, pazarApi, type Dimension, type OwnMarket, type Overview } from './api';
import { ROOT, useMeta } from './parts';
import { BriefView } from './BriefEditor';
import SqlInfo from '../components/SqlInfo';
import { kaynakOf } from '../components/kaynakOf';

/** Özet: yönetim özeti, TİMAŞ iç göstergeleri (Logo, sell-in), onaylı sektör rakamları, eşleme kapsamı. Telefonda okunur. */
export default function MarketHome({ overview, loading, error }: { overview?: Overview; loading: boolean; error: unknown }) {
  const meta = useMeta();
  const pages = usePageAccess();
  if (loading) return <Loading />;
  if (error) return <Note tone="err">{errText(error, 'Özet açılamadı.')}</Note>;
  if (!overview) return null;
  const o = overview;
  const t = o.own.total;
  const cov = o.mapping.coverage;
  const canReports = canOpenRoute(pages, `${ROOT}/raporlar`);
  const canRivals = canOpenRoute(pages, `${ROOT}/rakipler`);
  const me = meta.data?.me;
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      <KpiRow>
        <Kpi
          info={<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="TİMAŞ net ciro" />}
          label="TİMAŞ net ciro"
          value={t ? fmtTlShort(t.ytdCiro) : '—'}
          help={t ? `${o.own.period?.bitis ? `1 Oca – ${fmtDay(o.own.period.bitis)}` : o.own.yil} · önceki yılın aynı dönemine ${fmtGrowth(t.ciroBuyume)}` : o.own.empty ?? 'Logo satışı okunmadı'}
        />
        <Kpi info={<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Rakip kayıt" />} label="Rakip kayıt" value={fmtInt(o.freshness.records)} help={`${fmtInt(o.publishers)} yayınevi · CRM'de ${fmtInt(o.freshness.crmLinks)} emsal bağı`} />
        <Kpi
          info={<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Eşlenmiş rakip" />}
          label="Eşlenmiş rakip"
          value={cov.records ? fmtPct(cov.approved / cov.records, 0) : '—'}
          help={`${fmtInt(cov.approved)} / ${fmtInt(cov.records)} kaydın kategorisi onaylı · ${fmtInt((o.mapping.counts.oneri ?? 0) + (o.mapping.counts.belirsiz ?? 0))} öneri bekliyor`}
        />
        <Kpi info={<SqlInfo k={kaynakOf(o)} alan="_hepsi" label="Onaylı pazar rakamı" />} label="Onaylı pazar rakamı" value={fmtInt(o.figures.length)} help={o.pendingFigures ? `${fmtInt(o.pendingFigures)} rakam onay bekliyor` : 'Sektör raporlarından, sayfa numarasıyla'} />
      </KpiRow>

      <div className="grid gap-3 lg:grid-cols-[1.25fr_1fr] lg:gap-4">
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
              Yönetim özeti
              <SqlInfo k={kaynakOf(o)} alan="brief" label="Yönetim özetinin olguları" />
            </h2>
            <div className="flex flex-wrap items-center gap-2">
              {o.pendingBrief && (
                <Link to={`${ROOT}/ozet/${o.pendingBrief.donem}`} className="inline-flex min-h-11 items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
                  <Pill tone={STATUS_TONE[o.pendingBrief.durum]}>{o.pendingBrief.durumAd}</Pill> {o.pendingBrief.donemAd}
                </Link>
              )}
              {me?.canWrite && !o.pendingBrief && (
                <Link to={`${ROOT}/ozet/${lastMonth()}`} className="inline-flex min-h-11 items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
                  Geçen ayın özeti <ArrowRight aria-hidden className="h-3.5 w-3.5" />
                </Link>
              )}
            </div>
          </div>
          {o.brief ? (
            <>
              <p className="mt-1 text-[11.5px] font-semibold text-canvas-muted">
                {o.brief.donemAd} · {o.brief.onaylayan} onayladı, {fmtDay(o.brief.onaylandiAt)} · kurul paketine gönderildi
              </p>
              <div className="mt-2 max-h-[520px] overflow-y-auto pr-1">
                <BriefView md={o.brief.taslak} sources={o.brief.kaynaklar} compact />
              </div>
              <Link to={`${ROOT}/ozet/${o.brief.donem}`} className="mt-2 inline-flex min-h-11 items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
                Kaynaklarıyla aç <ArrowRight aria-hidden className="h-3.5 w-3.5" />
              </Link>
            </>
          ) : (
            <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">
              Onaylı özet yok. Zeki AI her ayın ilk haftası geçen ayın taslağını yazar; her cümle bir kaynağa bağlıdır, onay yönetimdedir.
            </p>
          )}
        </Panel>

        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
              Onaylı pazar rakamları
              <SqlInfo k={kaynakOf(o)} alan="figures" label="Onaylı pazar rakamları" />
            </h2>
            {canReports && (
              <Link to={`${ROOT}/raporlar`} className="inline-flex min-h-11 items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
                Raporlar <ArrowRight aria-hidden className="h-3.5 w-3.5" />
              </Link>
            )}
          </div>
          {o.figures.length === 0 ? (
            <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">
              Kaynak yok: pazar büyüklüğü ve kategori payı için onaylı sektör raporu rakamı yok. Rapor yüklenip rakamları onaylanınca burada
              kaynak ve sayfa numarasıyla görünür; portal tahmin üretmez.
            </p>
          ) : (
            <ul className="mt-2 divide-y divide-slate-100">
              {o.figures.slice(0, 12).map((f) => (
                <li key={f.id} className="flex items-start justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <div className="text-[12.5px] font-bold leading-snug">{f.gosterge}</div>
                    <div className="mt-0.5 flex items-center gap-1 text-[11px] text-canvas-muted">
                      <FileText aria-hidden className="h-3 w-3 shrink-0" />
                      <span className="truncate">{f.raporKaynak} · s. {f.sayfa}{f.donem ? ` · ${f.donem}` : ''}</span>
                    </div>
                  </div>
                  <div className="shrink-0 text-right font-mono text-[13px] font-bold tabular-nums">
                    {fmtNum(f.deger)} <span className="text-[11px] font-semibold text-canvas-muted">{f.birim}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {o.figures.length > 12 && <p className="mt-1 text-[11.5px] text-canvas-muted">İlk 12 rakam; tamamı raporların sayfasında ({fmtInt(o.figures.length)}).</p>}
          <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">{o.disTarama}</p>
        </Panel>
      </div>

      <OwnMarketPanel initial={o.own} k={kaynakOf(o)} />

      {canRivals && (
        <Panel>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
              Rakip verisi
              <SqlInfo k={kaynakOf(o)} alan="freshness" label="Yıl başına rakip kayıt" />
            </h2>
            <Link to={`${ROOT}/rakipler`} className="inline-flex min-h-11 items-center gap-1 text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
              Fiyat ve format matrisi <ArrowRight aria-hidden className="h-3.5 w-3.5" />
            </Link>
          </div>
          <p className="mt-1 text-[12.5px] leading-snug text-canvas-muted">{o.freshness.note}</p>
          {o.freshness.byYear.length > 0 && (
            <div className="mt-3 flex items-end gap-1 overflow-x-auto pb-1" role="img" aria-label="Rakip kayıtlarının CRM'e eklendiği yıllar">
              {(() => {
                const max = Math.max(...o.freshness.byYear.map((y) => y.kayit), 1);
                return o.freshness.byYear.map((y) => (
                  <div key={y.yil} className="flex min-w-[34px] flex-1 flex-col items-center gap-1">
                    <span className="font-mono text-[10px] tabular-nums text-canvas-muted">{fmtInt(y.kayit)}</span>
                    <div className="w-full rounded-t-md bg-canvas-violet/70" style={{ height: `${Math.max(4, (y.kayit / max) * 88)}px` }} />
                    <span className="font-mono text-[10.5px] tabular-nums">{y.yil}</span>
                  </div>
                ));
              })()}
            </div>
          )}
          <p className="mt-1 text-[11px] text-canvas-muted">Kayıtların CRM'e eklendiği yıl. {o.watchlist ? `${fmtInt(o.watchlist)} yayınevi izleniyor.` : ''}</p>
        </Panel>
      )}
    </div>
  );
}

function OwnMarketPanel({ initial, k }: { initial: OwnMarket; k?: ReturnType<typeof kaynakOf> }) {
  const [boyut, setBoyut] = useState<Dimension>('kategori');
  const [yil, setYil] = useState<number | undefined>(undefined);
  const q = useQuery({
    queryKey: ['pazar', 'own', boyut, yil ?? null],
    queryFn: () => pazarApi.ownMarket(boyut, yil),
    enabled: ENGINE_ENABLED && (boyut !== 'kategori' || yil !== undefined),
    placeholderData: keepPreviousData,
  });
  const m = boyut === 'kategori' && yil === undefined ? initial : (q.data ?? initial);
  const [all, setAll] = useState(false);
  const rows = all ? m.rows : m.rows.slice(0, 15);
  const dims: Array<[Dimension, string]> = [['kategori', 'Kategori'], ['yayinevi', 'Yayınevi (marka)'], ['kanal', 'Kanal']];
  return (
    <Panel>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1 text-[15px] font-extrabold">
          TİMAŞ iç göstergeleri
          <SqlInfo k={boyut === "kategori" && yil === undefined ? k : kaynakOf(q.data)} alan="_hepsi" label="TİMAŞ iç göstergeleri" />
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="Kırılım" className="flex gap-1 rounded-xl bg-slate-100 p-1">
            {dims.map(([k, l]) => (
              <button
                key={k}
                type="button"
                aria-pressed={boyut === k}
                onClick={() => { setBoyut(k); setAll(false); }}
                className={`min-h-11 rounded-lg px-2.5 text-[12px] font-extrabold transition-colors duration-150 sm:min-h-8 ${boyut === k ? 'bg-white text-canvas-ink shadow-sm' : 'text-canvas-muted hover:text-canvas-ink'}`}
              >
                {l}
              </button>
            ))}
          </div>
          {m.years.length > 1 && (
            <select aria-label="Yıl" value={m.yil ?? ''} onChange={(e) => setYil(Number(e.target.value))} className="min-h-11 rounded-xl border border-slate-200 bg-white/90 px-2 text-base font-semibold sm:min-h-8 sm:text-[12.5px]">
              {m.years.map((y) => <option key={y} value={y}>{y}</option>)}
            </select>
          )}
        </div>
      </div>
      <p className="mt-1 text-[11.5px] leading-snug text-canvas-muted">
        {m.period?.bitis ? <>1 Ocak – {fmtDay(m.period.bitis)} {m.yil}, önceki yılın aynı dönemiyle karşılaştırma. </> : null}
        {m.note}
      </p>
      {m.empty ? (
        <Note tone="info">{m.empty}</Note>
      ) : (
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr className="border-b border-slate-100">
                <th className={th}>{m.boyutAd ?? 'Kırılım'}</th>
                <th className={`${th} text-right`}>Net ciro</th>
                <th className={`${th} text-right`}>Önceki yıl</th>
                <th className={`${th} text-right`}>Büyüme</th>
                <th className={`${th} text-right`}>Adet büyümesi</th>
                <th className={`${th} text-right`}>TİMAŞ içi pay</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.anahtar} className="border-b border-slate-50 last:border-0">
                  <td className={`${td} font-semibold`}>{r.ad}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtTlShort(r.ytdCiro)}</td>
                  <td className={`${td} text-right font-mono tabular-nums text-canvas-muted`}>{fmtTlShort(r.oncekiYtdCiro)}</td>
                  <td className={`${td} text-right font-mono tabular-nums ${r.ciroBuyume === null ? '' : r.ciroBuyume >= 0 ? 'text-emerald-700' : 'text-red-700'}`}>{fmtGrowth(r.ciroBuyume)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtGrowth(r.adetBuyume)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct(r.pay)}</td>
                </tr>
              ))}
              {m.total && (
                <tr className="bg-slate-50/80 font-bold">
                  <td className={td}>Toplam</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtTlShort(m.total.ytdCiro)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtTlShort(m.total.oncekiYtdCiro)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtGrowth(m.total.ciroBuyume)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtGrowth(m.total.adetBuyume)}</td>
                  <td className={`${td} text-right`} />
                </tr>
              )}
            </tbody>
          </TableWrap>
          {m.rows.length > 15 && (
            <button type="button" onClick={() => setAll((v) => !v)} className="mt-2 min-h-11 text-[12.5px] font-extrabold text-canvas-violet hover:underline sm:min-h-0">
              {all ? 'İlk 15 satırı göster' : `Tümünü göster (${fmtInt(m.rows.length)} satır)`}
            </button>
          )}
          {m.missingPrev && <p className="mt-1 text-[11.5px] text-canvas-muted">Önceki yılın satışı okunmadı; büyüme hesaplanamıyor.</p>}
        </div>
      )}
    </Panel>
  );
}
