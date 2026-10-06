import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, field } from '../admin/ui';
import { AnalogTable, AuthorBooks, Box, ReprintPanel, ChannelBars, ForecastChart, FpFrame, Legend, ScenarioCards, Segmented, TierPill } from './parts';
import DecisionBox from './DecisionBox';
import MarketContext from './MarketContext';
import SqlInfo from '../components/SqlInfo';
import { sourceLine, useSummary } from './FirstPrintScreen';
import { NotReadyError, fmtMoney, fmtUnits, firstPrintApi, monthName, pct, stockoutText, type Forecast } from './api';

/** Tek kitabın tahmini (/ilk-baski/kitap/:kod). Yayımlanacak kitapta yayın ayı değiştirilebilir (?ay=YYYY-AA);
 *  çıkmış kitapta çıkıştan 2 ay önceki tahmin gerçekleşenle üst üste çizilir. */
export default function BookForecastPage() {
  const { code = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const launch = params.get('ay') || undefined;
  const summary = useSummary();
  const q = useQuery({
    queryKey: ['first-print', 'forecast', code, launch ?? ''],
    queryFn: () => firstPrintApi.forecast(code, launch),
    enabled: ENGINE_ENABLED && !!code,
    retry: (n, e) => e instanceof NotReadyError && n < 30,
    retryDelay: 20_000,
  });
  const fc = q.data;
  return (
    <FpFrame
      back
      crumb={fc?.book.name ?? code}
      title={fc?.book.name ?? 'Kitap tahmini'}
      lead={fc ? <BookLine fc={fc} /> : undefined}
      source={sourceLine(summary.data)}
    >
      {q.isLoading && <Loading />}
      {q.error && <Note tone={q.error instanceof NotReadyError ? 'info' : 'err'}>{(q.error as Error).message}</Note>}
      {fc && (
        <ForecastBody
          fc={fc}
          onLaunch={fc.mode === 'upcoming' ? (m) => setParams(m ? { ay: m } : {}, { replace: true }) : undefined}
          minLaunch={summary.data?.meta.lastFullMonth}
          can={summary.data?.can}
        />
      )}
    </FpFrame>
  );
}

function BookLine({ fc }: { fc: Forecast }) {
  const b = fc.book;
  const bits = [b.authors, b.publisher, b.library, b.series, b.audience, b.pages ? `${fmtUnits(b.pages)} sayfa` : null, b.price ? fmtMoney(b.price) : null].filter(Boolean);
  return <>{bits.join(' · ') || b.code}<SqlInfo k={fc.kaynaklar} alan="book" label="Kitap özellikleri (sayfa, fiyat)" className="ml-0.5" /></>;
}

function nextMonth(ym?: string): string | undefined {
  if (!ym) return undefined;
  let [y, m] = ym.split('-').map(Number);
  m += 1;
  if (m === 13) {
    y += 1;
    m = 1;
  }
  return `${y}-${String(m).padStart(2, '0')}`;
}

export function ForecastBody({ fc, onLaunch, minLaunch, can }: {
  fc: Forecast;
  onLaunch?: (month: string | null) => void;
  minLaunch?: string;
  can?: { decide: boolean; approve: boolean };
}) {
  const [h, setH] = useState<'6' | '12'>('6');
  const hz = fc.horizons[h] ?? fc.horizons['6'];
  const rec = fc.recommendation;
  const launched = fc.mode === 'launched';
  return (
    <div className="flex flex-col gap-3 lg:gap-4">
      {launched && (
        <Note tone="info">
          Bu kitap {monthName(fc.launch)}'da çıktı. Aşağıdaki tahmin, çıkıştan 2 ay önce ({monthName(fc.cutoff)} sonuna kadarki veriyle) yapılabilecek
          tahmindir; siyah çizgi gerçekleşen birikimli satıştır. Revize tahmin: ilk 6 ay {fmtUnits(fc.revised?.['6'])}, ilk 12 ay {fmtUnits(fc.revised?.['12'])}.
          <SqlInfo k={fc.kaynaklar} alan="revised" label="Revize tahmin" className="ml-0.5" />
        </Note>
      )}
      {fc.reprint && (
        <Box
          title="Stok ve yeniden baskı"
          info={<SqlInfo k={fc.kaynaklar} alan="reprint" label="Stok ve yeniden baskı" />}
          help="Elde kalan stokun, gerçekleşen ilk aylardan kurulan 12 aylık revize tahmine göre hangi ay tükeneceği ve ilk 12 ayı karşılamak için kaç adet daha basılması gerektiği."
        >
          <ReprintPanel r={fc.reprint} />
        </Box>
      )}
      {fc.book.salesTarget ? <Note tone="info">CRM'deki ilk yıl satış hedefi: {fmtUnits(fc.book.salesTarget)} adet.<SqlInfo k={fc.kaynaklar} alan="book" label="CRM ilk yıl satış hedefi" className="ml-0.5" /></Note> : null}

      <Box
        info={<SqlInfo k={fc.kaynaklar} alan="horizons" label="Satış senaryoları" />}
        title={`Satış senaryoları · ${fc.launchName} çıkış`}
        help={`Baz en olası satıştır. Kötümser: gerçekleşenin %80 olasılıkla üstünde kalacağı adet; iyimser: %80 olasılıkla altında kalacağı adet. Oranlar geçmişte benzer tahminlerin nasıl gerçekleştiğinden çıkar.${
          onLaunch ? ' Yayın ayını değiştirmek toplamı pek değiştirmez; satışın aylara dağılımını ve emsallerin seçimini değiştirir.' : ''
        }`}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <TierPill tier={fc.horizons['6'].tier} />
            {onLaunch && (
              <label className="flex items-center gap-2 text-[12px] font-semibold">
                <span className="text-canvas-muted">Yayın ayı</span>
                <input
                  type="month"
                  className={`${field} min-h-11 w-auto sm:min-h-9`}
                  value={fc.launch}
                  min={nextMonth(minLaunch)}
                  onChange={(e) => e.target.value && onLaunch(e.target.value)}
                />
              </label>
            )}
          </div>
        }
      >
        <ScenarioCards fc={fc} />
      </Box>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] lg:gap-4">
        <Box
          info={<SqlInfo k={fc.kaynaklar} alan={fc.actual ? 'actual[]' : `horizons.${h}.curve[]`} label="Birikimli satış ve güven aralığı" />}
          title="Birikimli satış"
          help={`Güven aralığı (%80): ilk ${h} ayda ${fmtUnits(hz.band.low)} – ${fmtUnits(hz.band.high)} adet.`}
          action={<Segmented label="Ufuk" value={h} onChange={setH} options={[{ key: '6', label: 'İlk 6 ay' }, { key: '12', label: 'İlk 12 ay' }]} />}
        >
          <ForecastChart h={hz} actual={fc.actual} />
          <Legend actual={!!fc.actual} />
        </Box>
        <Box title="İlk baskı önerisi" help={rec.basis} info={<SqlInfo k={fc.kaynaklar} alan="recommendation" label="İlk baskı önerisi ve seçenekler" />}>
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[34px] font-bold leading-none tabular-nums">{fmtUnits(rec.units)}</span>
            <span className="text-[12.5px] font-semibold text-canvas-muted">adet</span>
          </div>
          <p className="mt-1 text-[12.5px] leading-snug">{stockoutText(rec.stockout6)}</p>
          <div className="mt-3 text-[11px] font-bold uppercase tracking-wide text-canvas-muted">Seçenekler</div>
          <ul className="mt-1 divide-y divide-slate-100 rounded-xl border border-slate-100 bg-white/70">
            {rec.options.map((o) => (
              <li key={o.rule} className="flex items-start justify-between gap-3 px-3 py-2 text-[12.5px]">
                <span className="min-w-0">
                  <span className="font-mono font-bold tabular-nums">{fmtUnits(o.units)}</span>
                  {o.rule === rec.rule && <span className="ml-2 align-middle"><Pill tone="violet">önerilen</Pill></span>}
                  {o.rule === 'baz6' && <span className="ml-2 align-middle"><Pill tone="muted">asgari</Pill></span>}
                  <span className="block text-[11.5px] text-canvas-muted">{o.label}</span>
                </span>
                <span className="shrink-0 text-right text-[11.5px] text-canvas-muted">
                  6 ayda tükenme {pct(o.stockout6)}
                  {o.history?.leftover12 !== undefined && o.history?.leftover12 !== null && (
                    <span className="block">geçmişte 12. ay sonunda elde kalan {pct(o.history.leftover12)}</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11.5px] leading-snug text-canvas-muted">
            Adet basamakları yayınevinin geçmişte kullandığı ilk baskı adetleridir. Adede göre birim maliyeti «Fiyatlama ve maliyet» ekranında hesaplayabilirsiniz.
          </p>
          {fc.mode !== 'free' && <DecisionBox fc={fc} can={can} />}
        </Box>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] lg:gap-4">
        <Box title="Kanal dağılımı" info={<SqlInfo k={fc.kaynaklar} alan="horizons.6.channels[]" label="Kanal dağılımı" />} help={`Emsallerin ilk 6 ayındaki satış payları, baz senaryoya uygulandı${hz.discount !== null ? `; ortalama iskonto ${pct(hz.discount)}` : ''}.`}>
          <ChannelBars h={fc.horizons['6']} />
        </Box>
        <Box title="Gerekçe" help="Tahminin hangi bilgilere dayandığı, kısa maddelerle.">
          <ul className="list-disc space-y-1 pl-5 text-[12.5px] leading-snug">
            {fc.reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </Box>
      </div>

      {fc.author && (
        <Box
          title={`Yazarın önceki kitapları (${fc.author.count})`}
          info={<SqlInfo k={fc.kaynaklar} alan="author" label="Yazarın önceki kitapları" />}
          help="Yazarın daha önce çıkmış ve ilk 6 ayı dolmuş kitapları. Emsallerden çıkan tahmin, yazarın bu kitaplardaki satış düzeyine yaklaştırılır; yazarın kitabı ne kadar çok ve satışları ne kadar tutarlıysa ağırlık o kadar yüksektir. Aynı oran 12 aylık tahmine de uygulanır."
        >
          <AuthorBooks a={fc.author} />
        </Box>
      )}

      <Box title={`Emsal kitaplar (${hz.analogs.length})`} info={<SqlInfo k={fc.kaynaklar} alan={`horizons.${h}.analogs`} label="Emsal kitaplar" />} help="Bu kitaba en çok benzeyen, daha önce çıkmış kitaplar. Tahmin, bunların satışından benzerlik puanına göre ağırlıklandırılarak çıkar. Emsal adına basınca onun tahmini ve gerçekleşeni açılır.">
        <AnalogTable h={hz} />
      </Box>

      <MarketContext
        key={`${fc.book.code}|${fc.book.pages ?? ''}|${fc.book.genre ?? ''}`}
        code={fc.mode === 'free' ? undefined : fc.book.code}
        pages={fc.book.pages}
        genre={fc.book.genre}
      />
    </div>
  );
}
