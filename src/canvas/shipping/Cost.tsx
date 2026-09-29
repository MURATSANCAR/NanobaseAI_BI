import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Loader2, RefreshCw } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { ENGINE_ENABLED } from '../engine';
import SqlInfo, { InfoLabel } from '../components/SqlInfo';
import { EmptyHint, Explain } from '../components/Explain';
import { Note, Pill, TableWrap, btnGhost, errText, field, label as labelCls, td, th } from '../admin/ui';
import { Kpi, KpiRow, Panel } from '../editorial/kit';
import { fmtDay, fmtInt, fmtMoney, shippingApi, type CostCarrier, type CostGroup, type ShippingCost } from './api';
import { ExportButton, ShippingFrame } from './parts';

/** M44 Kargo maliyeti (/kargo/maliyet?yil=YYYY): Logo'daki kargo ve nakliye gideri (alınan hizmet faturası satırları,
 *  hizmet kodları ayarda), net ciroya oranı, taşıyıcı koduna göre irsaliyeli gönderi ve yaklaşık gönderi başı maliyet.
 *  Tedarikçi grubu (kargo firması / pazar yeri / nakliye) veriden ve ayardan gelir; ekranda sabit eşleme yok. Kargo
 *  faturaları toplu kesildiğinden gönderi başı rakamlar dönem toplamlarının oranıdır. */

const GROUP_COLOR: Record<CostGroup, string> = { kargo: '#7C5CFF', pazarYeri: '#F59E0B', nakliye: '#94a3b8' };
const GROUP_TONE: Record<CostGroup, 'violet' | 'warn' | 'muted'> = { kargo: 'violet', pazarYeri: 'warn', nakliye: 'muted' };
const CARRIER_COLORS = ['#7C5CFF', '#0EA5E9', '#F59E0B', '#10B981', '#EF4444'];
const OTHER_COLOR = '#cbd5e1';
const TOP_CARRIERS = CARRIER_COLORS.length;

const pct2 = new Intl.NumberFormat('tr-TR', { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct1 = new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 1 });
const compact = new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 });
const monthFmt = new Intl.DateTimeFormat('tr-TR', { month: 'short' });

const fmtPct2 = (v: number | null | undefined) => (v === null || v === undefined || !Number.isFinite(v) ? '—' : pct2.format(v));
const fmtCompact = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `${compact.format(v)} ₺`);

function monthLabel(ay: string): string {
  const [y, m] = ay.split('-').map(Number);
  return y && m ? monthFmt.format(new Date(y, m - 1, 1)) : ay;
}

type SeriesKey = { key: string; ad: string; color: string };

/** Aylık irsaliye grafiği: en çok irsaliyesi olan taşıyıcılar ayrı, kalanı «Diğer»; taşıyıcısız irsaliye yok. Anahtar
 *  yapay (`c0`…): taşıyıcı kodunda nokta olursa grafik onu alt alan sanmasın. */
function carrierSeries(d: ShippingCost): { keys: SeriesKey[]; hasOther: boolean; rows: Array<Record<string, string | number>> } {
  const ranked = d.byCarrier.filter((c) => !c.tasiyiciYok && c.irsaliye > 0);
  const main = ranked.slice(0, TOP_CARRIERS);
  const keys = main.map((c, i) => ({ key: `c${i}`, ad: c.ad, color: CARRIER_COLORS[i] }));
  const byKod = new Map(main.map((c, i) => [c.kod, `c${i}`]));
  const hasOther = ranked.length > main.length;
  const rows = d.byMonth.map((m) => {
    const row: Record<string, string | number> = { label: monthLabel(m.ay) };
    for (const k of keys) row[k.key] = 0;
    let other = 0;
    for (const t of m.tasiyici) {
      const key = byKod.get(t.kod);
      if (key) row[key] = Number(row[key]) + t.irsaliye;
      else other += t.irsaliye;
    }
    if (hasOther) row.diger = other;
    return row;
  });
  return { keys, hasOther, rows };
}

export default function ShippingCostScreen() {
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const asked = Number(params.get('yil')) || undefined;
  const meta = useQuery({ queryKey: ['shipping', 'meta'], queryFn: shippingApi.meta, enabled: ENGINE_ENABLED, staleTime: 60_000 });
  const allowed = !!meta.data?.me.maliyetSayfa;
  const key = ['shipping', 'cost', asked ?? 'bu-yil'];
  const cost = useQuery({
    queryKey: key,
    queryFn: () => shippingApi.cost(asked),
    enabled: ENGINE_ENABLED && allowed,
    placeholderData: (prev) => prev,
  });
  const refresh = useMutation({
    mutationFn: () => shippingApi.cost(asked, true),
    onSuccess: (r) => qc.setQueryData(key, r),
    onError: (e) => toast.error(errText(e, 'Yenilenemedi.') ?? ''),
  });
  const d = cost.data;
  const year = asked ?? d?.period.yil ?? new Date().getFullYear();
  const years = d?.yillar.length ? [...d.yillar].sort((a, b) => b - a) : [year];
  const t = d?.totals;
  const empty = !!d && d.bySupplier.length === 0 && d.byCarrier.length === 0;
  return (
    <ShippingFrame
      crumb="Kargo maliyeti"
      title="Kargo maliyeti"
      lead="Kargoya ve nakliyeye yılda ne ödediğimizi, bunun cironun yüzde kaçı olduğunu ve bir gönderinin bize yaklaşık kaça mal olduğunu gösterir. Rakamlar Logo'daki kargo ve nakliye faturalarından ve satış irsaliyelerinden gelir; tutarlar KDV hariçtir."
      meta={meta.data}
      aside={
        meta.data && allowed && (
          <div className="flex flex-wrap items-end justify-start gap-2 lg:justify-end">
            <label className="flex w-32 flex-col gap-1">
              <span className={labelCls}>Yıl</span>
              <select className={field} value={year} onChange={(e) => setParams(e.target.value ? { yil: e.target.value } : {}, { replace: true })}>
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <button type="button" className={btnGhost} disabled={refresh.isPending || !d} onClick={() => refresh.mutate()}>
              {refresh.isPending ? <Loader2 aria-hidden className="h-4 w-4 animate-spin" /> : <RefreshCw aria-hidden className="h-4 w-4" />}
              Verileri yenile
            </button>
            <ExportButton list="maliyet" params={{ yil: year }} can={meta.data.me.disaAktar} />
          </div>
        )
      }
    >
      {!ENGINE_ENABLED && <Note tone="warn">Bu kurulumda veri bağlantısı tanımlı değil.</Note>}
      {meta.error && <Note tone="err">{errText(meta.error, 'Kargo ekranı bilgisi okunamadı.')}</Note>}
      {meta.data && !allowed && (
        <Note tone="warn">Bu ekran, kargo maliyetini görme yetkisi ister ve rolünüzde bu yetki yok. Gerekirse yöneticinizden yetki isteyin.</Note>
      )}
      {cost.isLoading && <Note tone="info">Logo'daki kargo ve nakliye faturaları, satış irsaliyeleri ve net ciro okunuyor…</Note>}
      {cost.error && <Note tone="err">{errText(cost.error, 'Kargo maliyeti okunamadı.')}</Note>}
      {d && t && (
        <>
          <p className="px-1 text-[11.5px] text-canvas-muted">
            {d.period.yil} · {fmtDay(d.period.baslangic)} – {fmtDay(d.period.bitis)} · son satış faturası {fmtDay(d.dataEnd)} · son kargo faturası {fmtDay(d.giderSonu)} · son irsaliye {fmtDay(d.irsaliyeSonu)}
            {cost.isFetching && !cost.isLoading && ' · yenileniyor…'}
          </p>
          <KpiRow>
            <Kpi
              label="Kargo ve nakliye gideri"
              value={fmtCompact(t.gider)}
              help={`KDV hariç · ${fmtInt(t.fatura)} fatura, ${fmtInt(t.tedarikci)} tedarikçi`}
              explain={
                <>
                  Logo'da bize kesilen hizmet faturalarında, hizmet kodu kargo ve nakliye gideri olarak tanımlı satırların toplamı ({d.hizmetKodlari.join(', ') || 'kod tanımlı değil'}). Pazar yerlerinin kestiği kargo bedeli de buradadır. Tutar KDV hariçtir; tam tutar {fmtMoney(t.gider)}.
                </>
              }
              info={<SqlInfo k={d.kaynaklar} alan="totals.gider" label="Kargo ve nakliye gideri" />}
            />
            <Kpi
              label="Cironun yüzdesi"
              value={fmtPct2(t.oran)}
              help={`Net ciro ${fmtCompact(t.netCiro)}`}
              explain="Kargo ve nakliye gideri ÷ net ciro. Net ciro: aynı yılın satış faturaları eksi iade faturaları, KDV hariç."
              info={<SqlInfo k={d.kaynaklar} alan="totals.oran" label="Cironun yüzdesi" />}
            />
            <Kpi
              label="İrsaliyeli gönderi"
              value={fmtInt(t.irsaliye)}
              help={`Taşıyıcısız ${fmtInt(t.tasiyiciYok)} irsaliye sayılmadı`}
              explain="Satış irsaliyelerinden taşıyıcı kodu dolu olanların sayısı. Taşıyıcı kodu boş irsaliyeler mağaza kasa satışıdır, kargoya çıkmaz; gönderi sayılmaz."
              info={<SqlInfo k={d.kaynaklar} alan="totals.irsaliye" label="İrsaliyeli gönderi" />}
            />
            <Kpi
              label="Gönderi başı (yaklaşık)"
              value={fmtMoney(t.irsaliyeBasi)}
              help="Gider ÷ irsaliyeli gönderi"
              explain="Kargo firmaları faturayı gönderi gönderi değil, dönemin toplamı olarak keser; bu yüzden gideri tek tek gönderiye bağlayamıyoruz ve yılın toplam giderini yılın irsaliyeli gönderisine bölüyoruz. Faturası henüz gelmemiş aylar varsa rakam olduğundan düşük görünür."
              info={<SqlInfo k={d.kaynaklar} alan="totals.irsaliyeBasi" label="Gönderi başı" />}
            />
          </KpiRow>
          {d.notes.length > 0 && (
            <Note tone="info">
              <ul className="flex list-disc flex-col gap-1 pl-4">
                {d.notes.map((n) => <li key={n}>{n}</li>)}
              </ul>
            </Note>
          )}
          {empty ? (
            <EmptyHint
              title={`${d.period.yil} yılında kargo gideri de irsaliye de yok`}
              why="Başka bir yıl seçin. Faturalar henüz Logo'ya işlenmemiş olabilir ya da yönetim ekranındaki «Kargo gideri hizmet kodları» ayarı bu yılın kodlarıyla uyuşmuyor olabilir."
            />
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 xl:grid-cols-2 xl:gap-4">
                <CostChart d={d} />
                <SlipChart d={d} />
              </div>
              <CarrierTable d={d} />
              <MarketplaceTable d={d} />
              <SupplierTable d={d} />
            </>
          )}
        </>
      )}
    </ShippingFrame>
  );
}

function GroupRules() {
  return (
    <Explain label="Gider grupları" title="Gider nasıl gruplanıyor?">
      <span className="block">Her tedarikçi veriye bakılarak bir gruba girer:</span>
      <span className="mt-1 block"><b>Pazar yeri:</b> tedarikçinin vergi numarası, aynı yıl kargoyla mal gönderdiğimiz bir müşterinin vergi numarasıyla aynı. Yani hem müşterimiz hem de bize kargo faturası kesiyor.</span>
      <span className="mt-1 block"><b>Kargo firması:</b> carisi yönetim ekranındaki «Kargo firması → Logo cari kodları» ayarında tanımlı.</span>
      <span className="mt-1 block"><b>Nakliye ve diğer:</b> ikisi de değil (nakliyeci, palet taşıma, kurye, kişiler).</span>
    </Explain>
  );
}

function CostChart({ d }: { d: ShippingCost }) {
  const rows = d.byMonth.map((m) => ({ label: monthLabel(m.ay), kargo: m.kargo ?? 0, pazarYeri: m.pazarYeri ?? 0, nakliye: m.nakliye ?? 0, oran: m.oran }));
  const groups = Object.keys(GROUP_COLOR) as CostGroup[];
  return (
    <Panel>
      <h2 className="flex flex-wrap items-center gap-1 text-[14px] font-extrabold">
        <InfoLabel k={d.kaynaklar} alan="byMonth[]" label="Aylık gider ve cironun yüzdesi">Aylık gider</InfoLabel>
        <GroupRules />
      </h2>
      <p className="text-[11.5px] text-canvas-muted">Çubuk: ayın kargo ve nakliye gideri (KDV hariç, gruba göre). Çizgi: o ayın gideri ÷ o ayın net cirosu (sağ eksen).</p>
      {rows.length === 0 ? (
        <EmptyHint title="Bu yıl gider ayı yok" why="Bu yıl için Logo'da kargo gideri faturası bulunamadı." />
      ) : (
        <div className="mt-2 h-64 w-full sm:h-72" role="img" aria-label="Aylık kargo ve nakliye gideri, gruba göre; cironun yüzdesi çizgisi">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 0, left: -8, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={8} />
              <YAxis yAxisId="left" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={56} tickFormatter={(v: number) => fmtCompact(v)} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={44} tickFormatter={(v: number) => pct1.format(v)} />
              <Tooltip formatter={(v, _n, item) => (typeof v === 'number' ? (item.dataKey === 'oran' ? fmtPct2(v) : fmtMoney(v)) : '—')} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {groups.map((g) => (
                <Bar key={g} yAxisId="left" dataKey={g} name={d.groups[g]} stackId="gider" fill={GROUP_COLOR[g]} maxBarSize={36} isAnimationActive={false} />
              ))}
              <Line yAxisId="right" dataKey="oran" name="Cironun yüzdesi" stroke="#1B1F2A" strokeWidth={2} dot={{ r: 2.5 }} connectNulls={false} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}

function SlipChart({ d }: { d: ShippingCost }) {
  const s = carrierSeries(d);
  return (
    <Panel>
      <h2 className="flex flex-wrap items-center gap-1 text-[14px] font-extrabold">
        <InfoLabel k={d.kaynaklar} alan="byMonth[]" label="Aylık irsaliye, taşıyıcıya göre">Aylık irsaliye, taşıyıcıya göre</InfoLabel>
        <Explain label="Aylık irsaliye">Satış irsaliyesindeki taşıyıcı koduna göre ayın gönderileri. En çok gönderisi olan {TOP_CARRIERS} taşıyıcı ayrı, kalanı «Diğer». Taşıyıcı kodu boş irsaliyeler (mağaza kasa satışı) yok.</Explain>
      </h2>
      <p className="text-[11.5px] text-canvas-muted">Taşıyıcı adı, irsaliyedeki kodun CRM'deki kargo firması karşılığıdır; karşılığı yoksa kodun kendisi.</p>
      {s.keys.length === 0 ? (
        <EmptyHint title="Bu yıl taşıyıcılı irsaliye yok" why="Satış irsaliyelerinin taşıyıcı kodu boş; mağaza satışları kargoya çıkmaz." />
      ) : (
        <div className="mt-2 h-64 w-full sm:h-72" role="img" aria-label="Aylık irsaliye sayısı, taşıyıcıya göre">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={s.rows} margin={{ top: 8, right: 4, left: -12, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#e2e8f0" />
              <XAxis dataKey="label" tick={{ fontSize: 10 }} tickLine={false} axisLine={false} minTickGap={8} />
              <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={52} allowDecimals={false} tickFormatter={(v: number) => compact.format(v)} />
              <Tooltip formatter={(v) => (typeof v === 'number' ? fmtInt(v) : '—')} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {s.keys.map((k) => (
                <Bar key={k.key} dataKey={k.key} name={k.ad} stackId="irsaliye" fill={k.color} maxBarSize={36} isAnimationActive={false} />
              ))}
              {s.hasOther && <Bar dataKey="diger" name="Diğer" stackId="irsaliye" fill={OTHER_COLOR} maxBarSize={36} isAnimationActive={false} />}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  );
}

function HeadWithHelp({ k, alan, label, children }: { k: ShippingCost['kaynaklar']; alan: string; label: string; children: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <InfoLabel k={k} alan={alan}>{label}</InfoLabel>
      <Explain label={label}>{children}</Explain>
    </span>
  );
}

function CarrierStatus({ c }: { c: CostCarrier }) {
  if (c.tasiyiciYok) return <Pill tone="muted">Kargo yok</Pill>;
  if (c.eslendi) return <Pill tone="ok">Eşlendi</Pill>;
  return (
    <span className="flex flex-col items-start gap-1">
      <Pill tone="warn">Eşlenmemiş</Pill>
      <Link to="/kargo/mutabakat?adaylar=1" className="inline-flex min-h-11 items-center text-[11.5px] font-bold text-canvas-violet hover:underline sm:min-h-0">
        Aday carileri gör
      </Link>
    </span>
  );
}

function CarrierTable({ d }: { d: ShippingCost }) {
  const k = d.kaynaklar;
  return (
    <Panel>
      <h2 className="flex flex-wrap items-center gap-1 text-[14px] font-extrabold">
        <InfoLabel k={k} alan="byCarrier[]">Taşıyıcılar</InfoLabel>
        <Explain label="Taşıyıcılar" title="Bu tablo nasıl okunur?">
          Her satır bir taşıyıcıdır: satış irsaliyesindeki taşıyıcı kodu, CRM'deki kargo firmasıyla eşlenir (aynı firmaya düşen kodlar tek satırdır). Taşıyıcının Logo carisi yönetim ayarında tanımlıysa o carinin yıl gideri irsaliye sayısına bölünür. Pazar yeri üzerinden giden gönderinin kargo bedelini çoğu zaman pazar yeri fatura eder; o gönderilerin maliyeti aşağıdaki «Pazar yerleri» tablosundadır.
        </Explain>
      </h2>
      <div className="mt-2">
        <TableWrap>
          <thead>
            <tr>
              <th className={th}>Taşıyıcı</th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="byCarrier[]">İrsaliye</InfoLabel></th>
              <th className={`${th} text-right`}>
                <HeadWithHelp k={k} alan="byCarrier[]" label="Pazar yerine giden">Alıcısı pazar yeri olan irsaliye sayısı. Bu gönderilerin kargo bedeli çoğunlukla pazar yerinin faturasındadır.</HeadWithHelp>
              </th>
              <th className={th}>Logo carisi</th>
              <th className={`${th} text-right`}><InfoLabel k={k} alan="byCarrier[]">Gider</InfoLabel></th>
              <th className={`${th} text-right`}>
                <HeadWithHelp k={k} alan="byCarrier[]" label="İrsaliye başı">Eşlenen carilerin yıl gideri ÷ taşıyıcının irsaliye sayısı. Faturalar toplu kesildiğinden yaklaşıktır; cari eşlenmemişse hesaplanmaz.</HeadWithHelp>
              </th>
              <th className={th}>
                <span className="inline-flex items-center gap-1">
                  Durum
                  <Explain label="Durum">Eşlendi: taşıyıcının Logo carisi yönetim ayarında tanımlı. Eşlenmemiş: cari bilinmiyor; kargo mutabakatı ekranındaki aday carilerden doğru olanı seçip «Kargo firması → Logo cari kodları» ayarına yazabilirsiniz. Kargo yok: taşıyıcı kodu boş irsaliye (mağaza kasa satışı).</Explain>
                </span>
              </th>
            </tr>
          </thead>
          <tbody>
            {d.byCarrier.map((c) => (
              <tr key={c.kod} className="border-t border-slate-100">
                <td className={td}>
                  <div className="font-bold">{c.ad}</div>
                  {!c.tasiyiciYok && <div className="break-words font-mono text-[11px] text-canvas-muted">{c.kodlar.join(', ')}</div>}
                </td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(c.irsaliye)}</td>
                <td className={`${td} text-right font-mono tabular-nums`}>
                  {c.pazarYeriIrsaliye ? fmtInt(c.pazarYeriIrsaliye) : '—'}
                  {c.pazarYerleri.length > 0 && (
                    <div className="max-w-[220px] break-words text-right font-sans text-[11px] text-canvas-muted">
                      {c.pazarYerleri.map((p) => `${p.unvan} ${fmtInt(p.irsaliye)}`).join(' · ')}
                    </div>
                  )}
                </td>
                <td className={td}>
                  {c.eslenenCariler.length ? (
                    c.eslenenCariler.map((e) => (
                      <div key={e.cari} className="min-w-0">
                        <span className="font-mono text-[11.5px]">{e.cari}</span>
                        {e.unvan && <span className="block break-words text-[11px] text-canvas-muted">{e.unvan}</span>}
                      </div>
                    ))
                  ) : (
                    <span className="text-canvas-muted">—</span>
                  )}
                </td>
                <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(c.gider)}</td>
                <td className={`${td} text-right font-mono font-bold tabular-nums`}>{fmtMoney(c.irsaliyeBasi)}</td>
                <td className={td}><CarrierStatus c={c} /></td>
              </tr>
            ))}
          </tbody>
        </TableWrap>
      </div>
    </Panel>
  );
}

function MarketplaceTable({ d }: { d: ShippingCost }) {
  const k = d.kaynaklar;
  return (
    <Panel>
      <h2 className="flex flex-wrap items-center gap-1 text-[14px] font-extrabold">
        <InfoLabel k={k} alan="marketplaces[]">Pazar yerleri</InfoLabel>
        <Explain label="Pazar yerleri" title="Pazar yeri kargosu neden pazar yerinin faturasında?">
          Pazar yeri üzerinden satılan siparişi çoğu zaman pazar yerinin anlaşmalı kargosu taşır ve bedelini pazar yeri bize fatura eder. Bu yüzden irsaliyedeki taşıyıcı ile faturayı kesen firma farklıdır. Pazar yeri, bize kargo faturası kesen ve aynı zamanda kargoyla mal gönderdiğimiz müşteri olarak veriden bulunur (aynı vergi numarası). Gönderi başı = pazar yerinin kargo faturası ÷ o pazar yerine kestiğimiz irsaliye; yaklaşıktır.
        </Explain>
      </h2>
      {d.marketplaces.length === 0 ? (
        <EmptyHint title="Bu yıl pazar yeri kargo faturası yok" why="Kargo gideri faturası kesenlerden hiçbiri, aynı yıl kargoyla mal gönderdiğimiz bir müşteriyle aynı vergi numarasını taşımıyor." />
      ) : (
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Pazar yeri</th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="marketplaces[]">Kargo faturası</InfoLabel></th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="marketplaces[]">İrsaliye</InfoLabel></th>
                <th className={`${th} text-right`}>
                  <HeadWithHelp k={k} alan="marketplaces[]" label="Başka taşıyıcı">Pazar yerine giden ama taşıyıcısı başka bir tedarikçinin carisine eşlenmiş irsaliye; bedeli o tedarikçinin faturasında olduğu için bu satıra sayılmadı.</HeadWithHelp>
                </th>
                <th className={`${th} text-right`}>
                  <HeadWithHelp k={k} alan="marketplaces[]" label="Gönderi başı">Pazar yerinin kargo faturası ÷ pazar yerine sayılan irsaliye. Faturalar toplu kesildiğinden yaklaşıktır.</HeadWithHelp>
                </th>
              </tr>
            </thead>
            <tbody>
              {d.marketplaces.map((m) => (
                <tr key={m.cariler.join(',')} className="border-t border-slate-100">
                  <td className={td}>
                    <div className="font-bold">{m.unvan}</div>
                    <div className="break-words font-mono text-[11px] text-canvas-muted">{m.cariler.join(', ')}</div>
                    {m.kodlar.length > 0 && (
                      <div className="mt-0.5 break-words text-[11px] text-canvas-muted">{m.kodlar.map((x) => `${x.ad} ${fmtInt(x.irsaliye)}`).join(' · ')}</div>
                    )}
                  </td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(m.gider)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(m.irsaliye)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{m.baskaTasiyici ? fmtInt(m.baskaTasiyici) : '—'}</td>
                  <td className={`${td} text-right font-mono font-bold tabular-nums`}>
                    {m.sapma ? (
                      <span className="inline-flex items-center justify-end gap-1 font-sans text-[11.5px] font-semibold text-canvas-muted">
                        hesaplanmadı
                        <Explain label="Gönderi başı hesaplanmadı">Bu pazar yerinin kargo gideri öteki pazar yerlerine göre çok küçük ya da çok büyük (ortancadan 10 kat sapıyor). Kargo bedeli büyük olasılıkla başka bir hesaba yazılıyor ya da fatura tek seferlik; bu yüzden gönderi başı rakam yanıltıcı olurdu.</Explain>
                      </span>
                    ) : fmtMoney(m.gonderiBasi)}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
    </Panel>
  );
}

function SupplierTable({ d }: { d: ShippingCost }) {
  const k = d.kaynaklar;
  const t = d.totals;
  return (
    <Panel>
      <h2 className="flex flex-wrap items-center gap-1 text-[14px] font-extrabold">
        <InfoLabel k={k} alan="bySupplier[]">Tedarikçiler</InfoLabel>
        <GroupRules />
      </h2>
      <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
        {(Object.keys(GROUP_COLOR) as CostGroup[]).map((g) => (
          <span key={g} className="inline-flex items-center gap-1.5">
            <span aria-hidden className="h-2.5 w-2.5 rounded-full" style={{ background: GROUP_COLOR[g] }} />
            {d.groups[g]} <b className="font-mono tabular-nums">{fmtMoney(t[g])}</b>
            <SqlInfo k={k} alan={`totals.${g}`} label={d.groups[g]} />
          </span>
        ))}
      </div>
      {d.bySupplier.length === 0 ? (
        <EmptyHint title="Bu yıl kargo gideri faturası yok" why={`Ayardaki hizmet kodlarıyla (${d.hizmetKodlari.join(', ') || 'tanımlı değil'}) alınan hizmet faturası bulunamadı. Kodları yönetim ekranındaki «Kargo gideri hizmet kodları» ayarından kontrol edin.`} />
      ) : (
        <div className="mt-2">
          <TableWrap>
            <thead>
              <tr>
                <th className={th}>Tedarikçi</th>
                <th className={th}>Grup</th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="bySupplier[]">Gider</InfoLabel></th>
                <th className={`${th} text-right`}>
                  <HeadWithHelp k={k} alan="bySupplier[]" label="Pay">Tedarikçinin gideri ÷ yılın toplam kargo ve nakliye gideri.</HeadWithHelp>
                </th>
                <th className={`${th} text-right`}><InfoLabel k={k} alan="bySupplier[]">Fatura</InfoLabel></th>
                <th className={th}>Hizmet kodları</th>
              </tr>
            </thead>
            <tbody>
              {d.bySupplier.map((s) => (
                <tr key={s.cari} className="border-t border-slate-100">
                  <td className={td}>
                    <div className="break-words font-bold">{s.unvan ?? s.cari}</div>
                    <div className="font-mono text-[11px] text-canvas-muted">{s.cari}</div>
                  </td>
                  <td className={td}><Pill tone={GROUP_TONE[s.grup]}>{s.grupAdi}</Pill></td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtMoney(s.gider)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtPct2(s.pay)}</td>
                  <td className={`${td} text-right font-mono tabular-nums`}>{fmtInt(s.fatura)}</td>
                  <td className={td}>
                    {s.hizmetler.map((h) => (
                      <div key={h.kod} className="text-[11.5px]">
                        <span className="font-mono">{h.kod}</span>
                        {h.ad && <span className="text-canvas-muted"> · {h.ad}</span>}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableWrap>
        </div>
      )}
    </Panel>
  );
}
