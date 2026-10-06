import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { PenLine } from 'lucide-react';
import { ENGINE_ENABLED } from '../engine';
import { Loading, Note, Pill, TableWrap, btnGhost, td, th } from '../admin/ui';
import { Kpi, KpiRow } from '../editorial/kit';
import { BookSearch, Box, FpFrame, TierPill } from './parts';
import BacktestTab from './BacktestTab';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { EmptyHint, Explain, ExplainLabel } from '../components/Explain';
import { NotReadyError, dayName, firstPrintApi, fmtMoney, fmtUnits, monthName, pct, reprintTone, signedPct, trackTone, type Summary } from './api';

/** M10 İlk baskı ve satış tahmini: yayımlanacak kitaplar, ilk satış takibi, geçmiş sınama. Sekme adreste (?sekme=). */

const TABS = [
  { key: 'yeni', label: 'Yayımlanacak kitaplar' },
  { key: 'takip', label: 'İlk satış takibi' },
  { key: 'sinama', label: 'Tahmin ne kadar tutuyor' },
] as const;
type Tab = (typeof TABS)[number]['key'];

export function useSummary() {
  return useQuery({
    queryKey: ['first-print', 'summary'],
    queryFn: firstPrintApi.summary,
    enabled: ENGINE_ENABLED,
    // Rapor hazırlanırken (ilk kurulumda ~15 dk) ekran kendiliğinden dolsun.
    refetchInterval: (q) => (q.state.data && (!q.state.data.ready || q.state.data.status.refreshing) ? 20_000 : false),
  });
}

export function sourceLine(s?: Summary): string {
  if (!s?.meta?.dataEnd) return 'Kaynak: Logo + CRM';
  return `Logo satışı ${dayName(s.meta.dataEnd)}'e kadar · CRM`;
}

export default function FirstPrintScreen() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = (TABS.find((t) => t.key === params.get('sekme'))?.key ?? 'yeni') as Tab;
  const setTab = (t: Tab) => setParams(t === 'yeni' ? {} : { sekme: t }, { replace: true });
  const q = useSummary();
  const s = q.data;
  const bt6 = s?.backtest?.['6'];
  const alerts = s?.tracking.filter((r) => r.alert).length ?? null;
  const reprints = s?.tracking.filter((r) => r.reprint && r.reprint.status !== 'yeterli').length ?? 0;

  const aside = (
    <div className="flex flex-col gap-2">
      <BookSearch />
      <Link to="/ilk-baski/yeni" className={`${btnGhost} w-full`}>
        <PenLine aria-hidden className="h-4 w-4" />
        CRM'de kartı olmayan kitap için tahmin
      </Link>
    </div>
  );

  return (
    <FpFrame
      crumb="İlk baskı tahmini"
      title="İlk baskı ve satış tahmini"
      lead="Yeni çıkacak kitabın ilk 6 ve 12 aylık satışını, ona benzeyen ve daha önce çıkmış kitapların gerçek satışından tahmin eder ve ilk baskı adedi önerir. Kitap çıkınca gerçekleşen satış tahminle karşılaştırılır."
      source={sourceLine(s)}
      aside={aside}
    >
      {!ENGINE_ENABLED && <Note tone="warn">Sunucu bağlantısı yok; tahminler gösterilemiyor.</Note>}
      {q.isLoading && <Loading />}
      {q.error && !(q.error instanceof NotReadyError) && <Note tone="err">{(q.error as Error).message}</Note>}
      {s && !s.ready && (
        <Note tone="info">
          {s.status.error
            ? `Tahmin şu an hazırlanamadı: ${s.status.error}`
            : 'Tahmin hazırlanıyor: Logo\'dan 2015\'ten bu yana satış okunuyor ve geçmiş sınama yapılıyor (yaklaşık 15 dakika). Sayfa hazır olunca kendiliğinden dolar.'}
        </Note>
      )}
      {s?.ready && s.status.error && <Note tone="warn">Son yenileme başarısız: {s.status.error} Ekrandaki veri son başarılı okumadır.</Note>}
      {s?.meta.warnings?.map((w) => <Note key={w} tone="warn">{w}</Note>)}

      <KpiRow>
        <Kpi label="Yayımlanacak kitap" value={s?.ready ? fmtUnits(s.upcoming.length) : '—'} help="CRM'de yayın tarihi gelecekte, satışı yok" active={tab === 'yeni'} onClick={() => setTab('yeni')} explain="CRM'de ilk yayın tarihi Logo verisinin son tam ayından sonra olan ve henüz satışı olmayan kitaplar. Karta dokunursanız listesi açılır." info={<SqlInfo k={s?.kaynaklar} alan="kpi.yayimlanacak" label="Yayımlanacak kitap" />} />
        <Kpi label="İlk satış takibinde" value={s?.ready ? fmtUnits(s.tracking.length) : '—'} help={reprints ? `Son 12 ayda çıkan kitaplar · ${fmtUnits(reprints)} kitapta yeniden baskı gerekli` : 'Son 12 ayda çıkan kitaplar'} active={tab === 'takip'} onClick={() => setTab('takip')} explain="Son 12 ayda çıkmış kitaplar. Her birinin gerçekleşen satışı, çıkıştan önce yapılabilecek tahminle karşılaştırılır; elde kalan stok ilk 12 ay dolmadan tükenecekse yeniden baskı uyarısı verilir." info={<SqlInfo k={s?.kaynaklar} alan="kpi.takip" label="İlk satış takibinde" />} />
        <Kpi label="Kötümserin altında" value={alerts === null || !s?.ready ? '—' : fmtUnits(alerts)} help="Gerçekleşen satış kötümser senaryonun da altında" onClick={() => setTab('takip')} explain="Takipteki kitaplardan, bugüne kadarki satışı en kötü senaryonun bile altında kalanlar. Pazarlama için erken uyarıdır." info={<SqlInfo k={s?.kaynaklar} alan="kpi.kotumser" label="Kötümserin altında" />} />
        <Kpi label="Tipik sapma (6 ay)" value={bt6?.model ? pct(bt6.model.mdape) : '—'} help={bt6?.model ? `Geçmişte çıkan ${fmtUnits(bt6.model.n)} kitapta tahminle gerçekleşen arasındaki ortanca fark` : 'Geçmiş sınama'} active={tab === 'sinama'} onClick={() => setTab('sinama')} explain="Geçmişte çıkmış kitaplarda, çıkıştan önce yapılacak tahmin ile gerçekleşen ilk 6 ay satışı arasındaki yüzde farkın ortancası. Kitapların yarısında fark bundan küçüktür." info={<SqlInfo k={s?.kaynaklar} alan="kpi.sapma" label="Tipik sapma (6 ay)" />} />
      </KpiRow>

      {s?.ready && tab === 'yeni' && <UpcomingTab s={s} />}
      {s?.ready && tab === 'takip' && <TrackingTab s={s} />}
      {s?.ready && tab === 'sinama' && <BacktestTab s={s} />}
    </FpFrame>
  );
}

function UpcomingTab({ s }: { s: Summary }) {
  const nav = useNavigate();
  const [pub, setPub] = useState('');
  const pubs = useMemo(() => [...new Set(s.upcoming.map((r) => r.publisher).filter(Boolean) as string[])].sort((a, b) => a.localeCompare(b, 'tr')), [s.upcoming]);
  const rows = pub ? s.upcoming.filter((r) => r.publisher === pub) : s.upcoming;
  return (
    <Box
      title="Yayımlanacak kitaplar"
      help={`CRM'de ilk yayın tarihi ${monthName(s.meta.lastFullMonth)} sonrasında olan, satışı henüz olmayan kitaplar. Satırı açınca senaryolar, emsaller ve baskı adedi seçenekleri çıkar.`}
      action={
        pubs.length > 1 ? (
          <label className="flex items-center gap-2 text-[12px] font-semibold">
            <span className="text-canvas-muted">Yayınevi</span>
            <select value={pub} onChange={(e) => setPub(e.target.value)} className="min-h-11 rounded-xl border border-slate-200 bg-white px-2 text-base sm:min-h-9 sm:text-[12.5px]">
              <option value="">Tümü ({fmtUnits(s.upcoming.length)})</option>
              {pubs.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <EmptyHint
          title="Yayımlanacak kitap görünmüyor"
          why="CRM'de ilk yayın tarihi ileride olan ve henüz satışı olmayan kitap kartı yok. Yukarıdaki aramayla herhangi bir kitabı açabilir ya da kartı olmayan kitap için serbest tahmin yapabilirsiniz."
        />
      ) : (
        <TableWrap>
          <thead>
            <tr className="border-b border-slate-100">
              <th className={th}>Kitap</th>
              <th className={th}>Yayın</th>
              <th className={th}>
                <ExplainLabel label="Güven">
                  Tahminin ne kadar sağlam olduğu. Yüksek: en az üç güçlü emsal (CRM emsali, aynı yazar ya da aynı dizi). Orta: bir ya da iki güçlü emsal. Düşük: güçlü emsal yok, tahmin yalnız genel benzerlikten.
                </ExplainLabel>
              </th>
              <th className={`${th} text-right`}>
                <span className="inline-flex items-center gap-1">
                  <InfoLabel k={s.kaynaklar} alan="upcoming[]" label="İlk 6 ay baz tahmin">İlk 6 ay (baz)</InfoLabel>
                  <Explain label="Baz tahmin">En olası satış: gerçekleşenin yarı yarıya üstünde ya da altında kalması beklenen adet.</Explain>
                </span>
              </th>
              <th className={`${th} text-right`}>
                <span className="inline-flex items-center gap-1">
                  <InfoLabel k={s.kaynaklar} alan="upcoming[]" label="Güven aralığı %80">Aralık %80</InfoLabel>
                  <Explain label="Tahmin aralığı">İlk 6 ay satışının %80 olasılıkla bu iki değer arasında kalması beklenir.</Explain>
                </span>
              </th>
              <th className={`${th} text-right`}><InfoLabel k={s.kaynaklar} alan="upcoming[]" label="İlk 12 ay baz tahmin">İlk 12 ay</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={s.kaynaklar} alan="upcoming[]" label="12 ay ciro">12 ay ciro</InfoLabel></th>
              <th className={`${th} text-right`}>
                <span className="inline-flex items-center gap-1">
                  <InfoLabel k={s.kaynaklar} alan="upcoming[]" label="Önerilen ilk baskı ve tükenme olasılığı">Önerilen ilk baskı</InfoLabel>
                  <Explain label="Önerilen ilk baskı">
                    İlk 6 ayın iyimser senaryosu, yayınevinin kullandığı en yakın üst baskı adedine yuvarlanır. Altındaki oran, bu kadar basılırsa stoğun ilk 6 ayda bitme olasılığıdır.
                  </Explain>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.code} className="cursor-pointer border-b border-slate-50 last:border-0 hover:bg-slate-50/70" onClick={() => nav(`/ilk-baski/kitap/${encodeURIComponent(r.code)}`)}>
                <td className={td}>
                  <Link to={`/ilk-baski/kitap/${encodeURIComponent(r.code)}`} className="font-bold text-canvas-ink hover:text-canvas-violet hover:underline" onClick={(e) => e.stopPropagation()}>
                    {r.name}
                  </Link>
                  <div className="text-[11px] text-canvas-muted">{[r.authors, r.publisher].filter(Boolean).join(' · ') || r.code}</div>
                </td>
                <td className={`${td} whitespace-nowrap`}>{monthName(r.firstPub?.slice(0, 7))}</td>
                <td className={td}><TierPill tier={r.tier} /></td>
                <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtUnits(r.base6)}</td>
                <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums text-canvas-muted`}>{fmtUnits(r.low6)} – {fmtUnits(r.high6)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnits(r.base12)}</td>
                <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums`}>{fmtMoney(r.revenue12, true)}</td>
                <td className={`${td} whitespace-nowrap text-right`}>
                  <span className="font-mono font-bold tabular-nums">{fmtUnits(r.print)}</span>
                  <div className="text-[11px] text-canvas-muted">6 ayda tükenme {pct(r.stockout6)}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      )}
    </Box>
  );
}

function TrackingTab({ s }: { s: Summary }) {
  const nav = useNavigate();
  return (
    <Box
      title="İlk satış takibi"
      help={`Son 12 ayda çıkan kitaplar: çıkıştan 2 ay önce yapılabilecek tahmin ile ${monthName(s.meta.lastFullMonth)} sonuna kadar gerçekleşen satış. Sapma, bugüne kadar beklenen satışa göredir; revize tahmin gerçekleşen ilk aylardan kurulur. Kötümser senaryonun da altında kalan kitap pazarlama için uyarıdır. Stok sütunu, elde kalanın ilk 12 ay dolmadan hangi ay tükeneceğini ve ek baskı adedini gösterir.`}
    >
      {s.tracking.length === 0 ? (
        <EmptyHint title="Son 12 ayda çıkan kitap yok" why="Yeni bir kitap çıkıp satışı Logo'ya düştüğünde burada tahminle karşılaştırılarak izlenir." />
      ) : (
        <TableWrap>
          <thead>
            <tr className="border-b border-slate-100">
              <th className={th}>Kitap</th>
              <th className={th}>Çıkış</th>
              <th className={`${th} text-right`}><InfoLabel k={s.kaynaklar} alan="tracking[]" label="Gerçekleşen satış">Gerçekleşen</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={s.kaynaklar} alan="tracking[]" label="Beklenen (bugüne)">Beklenen (bugüne)</InfoLabel></th>
              <th className={`${th} text-right`}>
                <span className="inline-flex items-center gap-1">
                  <InfoLabel k={s.kaynaklar} alan="tracking[]" label="Sapma">Sapma</InfoLabel>
                  <Explain label="Sapma">Gerçekleşen satışın, bugüne kadar satılmış olması beklenen adetten yüzde farkı. Eksi: beklenenin altında.</Explain>
                </span>
              </th>
              <th className={`${th} text-right`}><InfoLabel k={s.kaynaklar} alan="tracking[]" label="İlk 6 ay: ilk tahmin → revize">İlk 6 ay: ilk tahmin → revize</InfoLabel></th>
              <th className={`${th} text-right`}><InfoLabel k={s.kaynaklar} alan="tracking[]" label="İlk 12 ay revize">İlk 12 ay revize</InfoLabel></th>
              <th className={th}>
                <span className="inline-flex items-center gap-1">
                  <InfoLabel k={s.kaynaklar} alan="tracking[]" label="Stok ve yeniden baskı">Stok</InfoLabel>
                  <Explain label="Stok">Elde kalan (depo stoku − bekleyen sipariş) ilk 12 ay dolmadan biterse tükenme ayı ve 12. aya kadar gereken ek baskı adedi.</Explain>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {s.tracking.map((r) => {
              const f6 = r.forecast['6'];
              const f12 = r.forecast['12'];
              const tone = trackTone(r);
              return (
                <tr key={r.code} className="cursor-pointer border-b border-slate-50 last:border-0 hover:bg-slate-50/70" onClick={() => nav(`/ilk-baski/kitap/${encodeURIComponent(r.code)}`)}>
                  <td className={td}>
                    <Link to={`/ilk-baski/kitap/${encodeURIComponent(r.code)}`} className="font-bold text-canvas-ink hover:text-canvas-violet hover:underline" onClick={(e) => e.stopPropagation()}>
                      {r.name}
                    </Link>
                    <div className="text-[11px] text-canvas-muted">{[r.authors, r.publisher].filter(Boolean).join(' · ') || r.code}</div>
                  </td>
                  <td className={`${td} whitespace-nowrap`}>
                    {monthName(r.launch)}
                    <div className="text-[11px] text-canvas-muted">{r.observed} ay veri</div>
                  </td>
                  <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtUnits(r.actual)}</td>
                  <td className={`${td} text-right font-mono tabular-nums text-canvas-muted`}>{fmtUnits(f6.expectedSoFar)}</td>
                  <td className={`${td} whitespace-nowrap text-right`}>
                    <Pill tone={tone}>{signedPct(r.deviation)}</Pill>
                    {r.alert && <div className="mt-0.5 text-[11px] font-semibold text-red-700">Kötümserin altında</div>}
                  </td>
                  <td className={`${td} whitespace-nowrap text-right font-mono tabular-nums`}>
                    {fmtUnits(f6.base)} → <span className="font-bold">{fmtUnits(f6.revised)}</span>
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtUnits(f12?.revised)}</td>
                  <td className={`${td} whitespace-nowrap`}>
                    {r.reprint ? (
                      <>
                        <Pill tone={reprintTone(r.reprint)}>{r.reprint.status === 'yeterli' ? 'Yeterli' : r.reprint.status === 'yok' ? 'Stok yok' : r.reprint.runOutName}</Pill>
                        <div className="mt-0.5 text-[11px] text-canvas-muted">
                          {r.reprint.units ? `+${fmtUnits(r.reprint.units)} baskı` : `elde ${fmtUnits(r.reprint.available)}`}
                        </div>
                      </>
                    ) : (
                      <span className="text-canvas-muted">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </TableWrap>
      )}
    </Box>
  );
}
