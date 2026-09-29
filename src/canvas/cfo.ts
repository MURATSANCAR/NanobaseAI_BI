import { useQueries } from '@tanstack/react-query';
import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, isAuthBlocked, runSql } from './engine';
import type { DbTiming } from './DbTiming';
import { httpErrorText } from './httpError';
import { msUntilNextRefresh } from './refreshSchedule';
import type { KaynakSorgu, Kaynaklar } from './components/sqlInfo';

/**
 * CFO'nun ekranda görmek istediği rakamlar. Hepsi semantic bridge üzerinden
 * canlı Logo veritabanından okunur; formüller kataloğa doğrulatılmış olanlarla
 * aynıdır (net ciro = fatura seviyesi NETTOTAL, satış TRCODE 7/8/9, iade 2/3).
 *
 * Logo'da her yıl ayrı firma numarası taşır: 2026 → LG_411, 2021-2025 → LG_211.
 */
const NET = 'SUM(CASE WHEN I.[TRCODE] IN (7,8,9) THEN I.[NETTOTAL] ELSE -I.[NETTOTAL] END)';
const SALES_FILTER = 'I.[CANCELLED]=0 AND I.[TRCODE] IN (2,3,7,8,9)';

/** Yıl → Logo firma öneki. Yeni yıl açıldığında buraya bir satır eklenir. */
const PERIOD: Record<number, string> = { 2026: 'LG_411', 2025: 'LG_211', 2024: 'LG_211', 2023: 'LG_211' };
const prefixFor = (year: number) => PERIOD[year] ?? 'LG_411';

const YEAR = new Date().getFullYear();
const PREV = YEAR - 1;

const inv = (year: number) => `[dbo].[${prefixFor(year)}_01_INVOICE]`;
const line = (year: number) => `[dbo].[${prefixFor(year)}_01_STLINE]`;
const card = (year: number) => `[dbo].[${prefixFor(year)}_CLCARD]`;
const range = (year: number) => `I.[DATE_]>='${year}-01-01' AND I.[DATE_]<'${year + 1}-01-01'`;

export type MonthRow = { ay: number; net_ciro: number; fatura: number };
export type TotalsRow = { brut_satis: number; iade_tutari: number; iade_fatura: number; toplam_fatura: number; son_fatura: string };
export type UnitsRow = { satilan_adet: number; baslik_sayisi: number; satir: number };
export type CustomerRow = { cari: string; net_ciro: number };
export type ChannelRow = { trcode: number; net_ciro: number; fatura: number };
export type ItemRow = { urun: string; kod: string; adet: number; net_ciro: number };
export type ReturnItemRow = { urun: string; kod: string; iade_adet: number; iade_tutar: number };

const SQL = {
  /** İadesi en yüksek başlıklar: yayıncı için doğrudan aksiyon konusu. */
  returnItems: (year: number) =>
    `SELECT TOP 6 IT.[NAME] AS urun, IT.[CODE] AS kod, SUM(L.[AMOUNT]) AS iade_adet, SUM(L.[LINENET]) AS iade_tutar` +
    ` FROM ${line(year)} AS L INNER JOIN [dbo].[${prefixFor(year)}_ITEMS] AS IT ON IT.[LOGICALREF]=L.[STOCKREF]` +
    ` WHERE L.[CANCELLED]=0 AND L.[LINETYPE]=0 AND L.[TRCODE] IN (2,3)` +
    ` AND L.[DATE_]>='${year}-01-01' AND L.[DATE_]<'${year + 1}-01-01'` +
    ` GROUP BY IT.[NAME], IT.[CODE] ORDER BY iade_tutar DESC`,
  months: (year: number) =>
    `SELECT MONTH(I.[DATE_]) AS ay, ${NET} AS net_ciro, COUNT(*) AS fatura FROM ${inv(year)} AS I WHERE ${SALES_FILTER} AND ${range(year)} GROUP BY MONTH(I.[DATE_]) ORDER BY ay`,
  totals: (year: number) =>
    `SELECT SUM(CASE WHEN I.[TRCODE] IN (7,8,9) THEN I.[NETTOTAL] ELSE 0 END) AS brut_satis, SUM(CASE WHEN I.[TRCODE] IN (2,3) THEN I.[NETTOTAL] ELSE 0 END) AS iade_tutari, SUM(CASE WHEN I.[TRCODE] IN (2,3) THEN 1 ELSE 0 END) AS iade_fatura, COUNT(*) AS toplam_fatura, MAX(I.[DATE_]) AS son_fatura FROM ${inv(year)} AS I WHERE ${SALES_FILTER} AND ${range(year)}`,
  units: (year: number) =>
    `SELECT SUM(CASE WHEN L.[TRCODE] IN (7,8,9) THEN L.[AMOUNT] ELSE -L.[AMOUNT] END) AS satilan_adet, COUNT(DISTINCT L.[STOCKREF]) AS baslik_sayisi, COUNT(*) AS satir FROM ${line(year)} AS L WHERE L.[CANCELLED]=0 AND L.[LINETYPE]=0 AND L.[TRCODE] IN (2,3,7,8,9) AND L.[DATE_]>='${year}-01-01' AND L.[DATE_]<'${year + 1}-01-01'`,
  channels: (year: number) =>
    `SELECT I.[TRCODE] AS trcode, ${NET} AS net_ciro, COUNT(*) AS fatura FROM ${inv(year)} AS I WHERE ${SALES_FILTER} AND ${range(year)} GROUP BY I.[TRCODE] ORDER BY net_ciro DESC`,
  customers: (year: number) =>
    `SELECT TOP 5 C.[DEFINITION_] AS cari, ${NET} AS net_ciro FROM ${inv(year)} AS I INNER JOIN ${card(year)} AS C ON C.[LOGICALREF]=I.[CLIENTREF] WHERE ${SALES_FILTER} AND ${range(year)} GROUP BY C.[DEFINITION_] ORDER BY net_ciro DESC`,
  topItem: (year: number) =>
    `SELECT TOP 8 IT.[NAME] AS urun, IT.[CODE] AS kod, SUM(CASE WHEN L.[TRCODE] IN (7,8,9) THEN L.[AMOUNT] ELSE -L.[AMOUNT] END) AS adet, SUM(CASE WHEN L.[TRCODE] IN (7,8,9) THEN L.[LINENET] ELSE -L.[LINENET] END) AS net_ciro FROM ${line(year)} AS L INNER JOIN [dbo].[${prefixFor(year)}_ITEMS] AS IT ON IT.[LOGICALREF]=L.[STOCKREF] WHERE L.[CANCELLED]=0 AND L.[LINETYPE]=0 AND L.[TRCODE] IN (2,3,7,8,9) AND L.[DATE_]>='${year}-01-01' AND L.[DATE_]<'${year + 1}-01-01' GROUP BY IT.[NAME], IT.[CODE] ORDER BY adet DESC`,
};

export type CfoData = {
  ready: boolean;
  authRequired: boolean;
  failed: boolean;
  year: number;
  months: MonthRow[];
  prevMonths: MonthRow[];
  totals: TotalsRow | null;
  units: UnitsRow | null;
  channels: ChannelRow[];
  customers: CustomerRow[];
  items: ItemRow[];
  returnItems: ReturnItemRow[];
  /** Yılın kaç ayı gerçekleşmiş (son fatura tarihine göre). */
  observedMonths: number;
  netYtd: number;
  netPrevSame: number;
  yoyPct: number | null;
  returnPct: number | null;
  /** Özet ne zaman üretildi (arka plan dosyası). */
  generatedAt?: string;
  /** Rakamları üreten sorguların tam metni ("SQL'i göster" bunu gösterir). */
  sql?: string | null;
  /** Rakamların veritabanından gelme süresi (sorguların toplamı). */
  db?: DbTiming | null;
  /** Sorgu bilgisi: her kartın rakamını üreten fiziksel SQL ve hesap (kart başına «i»). */
  kaynaklar?: Kaynaklar | null;
};

const EMPTY: Omit<CfoData, 'ready' | 'authRequired' | 'failed'> = {
  year: YEAR,
  months: [],
  prevMonths: [],
  totals: null,
  units: null,
  channels: [],
  customers: [],
  items: [],
  returnItems: [],
  observedMonths: 0,
  netYtd: 0,
  netPrevSame: 0,
  yoyPct: null,
  returnPct: null,
};

type RawSets = {
  months: MonthRow[];
  prevMonths: MonthRow[];
  totals: TotalsRow | null;
  units: UnitsRow | null;
  channels: ChannelRow[];
  customers: CustomerRow[];
  items: ItemRow[];
  returnItems: ReturnItemRow[];
  generatedAt?: string;
  sql?: string | null;
  db?: DbTiming | null;
  /** Geçen yılın gün düzeyinde eş dönemi (tek satır); yoksa aylık kırpmaya düşülür. */
  prevSameDate?: Array<{ net_ciro: number | null; fatura?: number; son_fatura?: string }>;
  /** Sorgu adı → köprünün koşturduğu sorgunun kaydı (fiziksel SQL, satır, süre, zaman). */
  sources?: Record<string, KaynakSorgu | null | undefined>;
};

/* ----------------------------------------------------------- sorgu bilgisi */

const SOURCE_TITLES: Record<string, string> = {
  months: 'Aylık net ciro · bu yıl',
  prevMonths: 'Aylık net ciro · geçen yıl',
  prevSameDate: 'Geçen yıl eş dönem (gün düzeyinde)',
  totals: 'Satış ve iade toplamları · bu yıl',
  units: 'Satılan adet, satır ve başlık · bu yıl',
  channels: 'Fatura türüne göre net ciro · bu yıl',
  customers: 'En büyük 5 cari · bu yıl',
  items: 'En çok satan 8 başlık · bu yıl',
  returnItems: 'İadesi en yüksek başlıklar · bu yıl',
};

const NET_RULE =
  'Net ciro = Σ fatura net tutarı (satış: TRCODE 7, 8, 9) − Σ fatura net tutarı (iade: TRCODE 2, 3); iptal faturalar hariç.';

/** Kart başına hesap metni ve girdileri (sorgu adları ya da başka hesap). Hesap `shape()` ve `cfoData()`'dadır. */
const FORMULAS: Record<string, { text: string; inputs: string[] }> = {
  netYtd: { text: `Yılbaşından net ciro = Σ aylık net ciro. ${NET_RULE}`, inputs: ['months'] },
  netPrevSame: {
    text:
      'Geçen yıl aynı dönem = geçen yılın 1 Ocak gününden, bu yılın son fatura gününün geçen yıldaki karşılığına kadar ' +
      'net ciro (gün düzeyinde). Bu sorgu yoksa geçen yılın ilk N ayı (N = bu yıl gerçekleşen ay sayısı).',
    inputs: ['prevSameDate', 'prevMonths'],
  },
  c1: {
    text:
      'Net ciro kartı: büyük rakam yılbaşından net ciro; rozet artış = net ciro ÷ geçen yıl aynı dönem − 1; aylık ' +
      'ortalama = net ciro ÷ gerçekleşen ay; «N / 12 ay» gerçekleşen ay = verisi olan en büyük ay numarası; «Veri» son ' +
      'fatura günü.',
    inputs: ['hesap:netYtd', 'hesap:netPrevSame', 'totals'],
  },
  c2: {
    text:
      `Aylık seyir: son tam ay = verisi olan son aydan önceki ay; yüzde = bu ayın net cirosu ÷ geçen yılın aynı ayı − 1; ` +
      `çizgi ve son üç ay aylık net ciro. ${NET_RULE}`,
    inputs: ['months', 'prevMonths'],
  },
  c3: {
    text:
      'Kanal dağılımı fatura türüdür: Toptan = TRCODE 8, Perakende = 7, Diğer = 9, İade = 2 + 3 (mutlak değer); ' +
      'ortadaki toplam dördünün toplamı; iade oranı = iade tutarı ÷ brüt satış (satış faturaları toplamı).',
    inputs: ['channels', 'totals'],
  },
  c4: {
    text:
      'En büyük cari: net cirosu en yüksek 5 cari (cari kartı adına göre). Pay = carinin net cirosu ÷ yılbaşından net ' +
      'ciro; ilk 5 payı = ilk 5 carinin toplamı ÷ yılbaşından net ciro.',
    inputs: ['customers', 'hesap:netYtd'],
  },
  c5: {
    text:
      'Kanıt: fatura = bu yılın satış ve iade faturası sayısı; satır = malzeme satırı sayısı; başlık = farklı stok ' +
      'sayısı; cari = listelenen cari sayısı. Süre bütün sorguların veritabanı süresinin toplamıdır.',
    inputs: ['totals', 'units', 'customers'],
  },
  main: {
    text:
      'Özet cümlesi: net ciro ve artış Net ciro kartıyla aynı hesap; iade oranı = iade tutarı ÷ brüt satış. Satılan ' +
      'adet = Σ miktar (satış 7, 8, 9) − Σ miktar (iade 2, 3), malzeme satırları; fatura = satış ve iade faturası ' +
      'sayısı; iade faturası = TRCODE 2, 3 fatura sayısı.',
    inputs: ['hesap:c1', 'totals', 'units'],
  },
  sticker: {
    text: 'En çok satan: net adedi en yüksek başlık; adet ve net ciro aynı satırdan (satış − iade, malzeme satırları).',
    inputs: ['items'],
  },
  ghost: {
    text: 'İade: iade faturalarının (TRCODE 2, 3) tutarı; oran = iade tutarı ÷ brüt satış; iade faturası sayısı.',
    inputs: ['channels', 'totals'],
  },
};

/** Alan (kart) → hesap. Ekran `<SqlInfo k={c.kaynaklar} alan="c1" …>` ile ister. */
const CARD_FIELDS = ['c1', 'c2', 'c3', 'c4', 'c5', 'main', 'sticker', 'ghost'] as const;

/** Sorgu kayıtlarından (köprünün `/run_sql` cevabındaki fiziksel SQL) kartların sorgu bilgisi. Kayıt yoksa sessiz
 *  kalmaz: pencere nedenini yazar. */
export function cfoKaynaklar(given: RawSets['sources'], dataEnd?: string | null): Kaynaklar {
  const sources: Kaynaklar['sources'] = {};
  for (const [name, s] of Object.entries(given ?? {})) {
    if (!s?.sql) continue;
    const id = `cfo.${name}`;
    sources[id] = { ...s, id, title: SOURCE_TITLES[name] ?? s.title, origin: [] };
  }
  const has = (ref: string) => (ref.startsWith('hesap:') ? true : Boolean(sources[`cfo.${ref}`]));
  const formulas: Kaynaklar['formulas'] = {};
  for (const [name, f] of Object.entries(FORMULAS)) {
    formulas[name] = {
      name,
      text: f.text,
      inputs: f.inputs.filter(has).map((r) => (r.startsWith('hesap:') ? r : `cfo.${r}`)),
    };
  }
  const fields: Kaynaklar['fields'] = {};
  for (const c of CARD_FIELDS) fields[c] = `hesap:${c}`;
  const empty = Object.keys(sources).length === 0;
  return {
    sources,
    formulas,
    fields,
    dataEnd: dataEnd ?? null,
    ...(empty
      ? { error: 'Özet henüz sorgu bilgisini taşımıyor; özet yeniden üretilince (birkaç dakika içinde) görünür.' }
      : {}),
  };
}

/** Ham sonuç kümelerinden ekranın beklediği özet. Hem arka plandaki dosya
 *  hem canlı sorgular bu fonksiyondan geçer; hesap tek yerde. */
function shape(r: RawSets): CfoData {
  const observedMonths = r.months.length ? Math.max(...r.months.map((x) => x.ay)) : 0;
  const netYtd = r.months.reduce((a, x) => a + (x.net_ciro ?? 0), 0);
  // Gün düzeyinde eş dönem varsa o: aylık kırpma son ayın tamamını alıp artışı düşük gösterir.
  const sameDay = r.prevSameDate?.[0]?.net_ciro;
  const netPrevSame = typeof sameDay === 'number'
    ? sameDay
    : r.prevMonths.filter((x) => x.ay <= observedMonths).reduce((a, x) => a + (x.net_ciro ?? 0), 0);
  return {
    ready: true,
    authRequired: false,
    failed: false,
    year: YEAR,
    months: r.months,
    prevMonths: r.prevMonths,
    totals: r.totals,
    units: r.units,
    channels: r.channels,
    customers: r.customers,
    items: r.items,
    returnItems: r.returnItems,
    generatedAt: r.generatedAt,
    sql: r.sql ?? null,
    db: r.db ?? null,
    kaynaklar: cfoKaynaklar(r.sources, r.totals?.son_fatura?.slice(0, 10) ?? null),
    observedMonths,
    netYtd,
    netPrevSame,
    yoyPct: netPrevSame > 0 ? (netYtd / netPrevSame - 1) * 100 : null,
    returnPct: r.totals && r.totals.brut_satis > 0 ? (r.totals.iade_tutari / r.totals.brut_satis) * 100 : null,
  };
}

/** Arka planda üretilen özet. Ekran açılışında sorgu koşmasın diye önce bu
 *  okunur; yoksa ya da erişilemezse canlı sorgulara düşülür. */
async function fetchSnapshot(): Promise<RawSets> {
  const res = await fetch(`${ENGINE_BASE}/metrics/cfo.json`, {
    credentials: 'include',
    signal: AbortSignal.timeout(12_000),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) throw new Error(httpErrorText(res.status));
  const j = (await res.json()) as Partial<RawSets> & {
    generatedAt?: string;
    db?: DbTiming | null;
    kaynakSorgulari?: RawSets['sources'];
  };
  return {
    months: j.months ?? [],
    prevMonths: j.prevMonths ?? [],
    totals: (j.totals as unknown as TotalsRow[] | undefined)?.[0] ?? (j.totals as TotalsRow | null) ?? null,
    units: (j.units as unknown as UnitsRow[] | undefined)?.[0] ?? (j.units as UnitsRow | null) ?? null,
    channels: j.channels ?? [],
    customers: j.customers ?? [],
    items: j.items ?? [],
    returnItems: j.returnItems ?? [],
    generatedAt: j.generatedAt,
    // Üretici SQL yazmıyorsa (eski sürüm) ekranda düğme kapalı kalır; metin uydurulmaz.
    sql: j.sql ?? null,
    // Eski üretici süre yazmıyordu: o durumda "ölçülmedi" denir, sayı uydurulmaz.
    db: j.db ?? { dbMs: null, computedAt: j.generatedAt ?? null },
    // Eski üretici bu alanı yazmıyordu: yoksa aylık kırpmaya düşülür.
    prevSameDate: j.prevSameDate,
    // Sorgu başına köprünün kaydı (fiziksel SQL); eski üretici yazmıyorsa pencere nedenini söyler.
    sources: j.kaynakSorgulari,
  };
}

/**
 * Önce arka plandaki özet okunur (tek istek, anlık). Ulaşılamazsa sekiz sorgu
 * canlı koşar; böylece özet üretici durursa ekran boş kalmaz.
 */
export function useCfoData(): CfoData {
  const snap = useQuery({
    queryKey: ['cfo-snapshot', YEAR],
    queryFn: fetchSnapshot,
    enabled: ENGINE_ENABLED,
    staleTime: 60_000,
    refetchInterval: () => (isAuthBlocked() ? false : msUntilNextRefresh()),   // 07:00 ve 12:00 (İstanbul)
    retry: false,
  });
  const snapFailed = snap.isError && !(snap.error instanceof EngineAuthError);

  const q = useQueries({
    queries: [
      { key: 'months', sql: SQL.months(YEAR) },
      { key: 'prev', sql: SQL.months(PREV) },
      { key: 'totals', sql: SQL.totals(YEAR) },
      { key: 'units', sql: SQL.units(YEAR) },
      { key: 'channels', sql: SQL.channels(YEAR) },
      { key: 'customers', sql: SQL.customers(YEAR) },
      { key: 'items', sql: SQL.topItem(YEAR) },
      { key: 'returnItems', sql: SQL.returnItems(YEAR) },
    ].map((it) => ({
      queryKey: ['cfo', it.key, YEAR],
      queryFn: () => runSql<Record<string, unknown>>(it.sql),
      enabled: ENGINE_ENABLED && snapFailed,
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });

  if (snap.data) return shape(snap.data);

  const authRequired = snap.error instanceof EngineAuthError || q.some((r) => r.error instanceof EngineAuthError);
  if (authRequired) return { ...EMPTY, ready: false, authRequired: true, failed: false };
  if (!snapFailed) return { ...EMPTY, ready: false, authRequired: false, failed: false };

  const NAMES = ['months', 'prevMonths', 'totals', 'units', 'channels', 'customers', 'items', 'returnItems'] as const;
  const [months, prev, totals, units, channels, customers, items, returnItems] = q;
  const ready = q.some((r) => r.isSuccess);
  if (!ready) return { ...EMPTY, ready: false, authRequired: false, failed: q.every((r) => r.isError) };

  const rec = <T,>(r: (typeof q)[number]) => ((r.data?.records ?? []) as unknown as T[]);
  const done = q.filter((r) => r.data);
  const measured = done.map((r) => r.data?.dbMs).filter((v): v is number => typeof v === 'number');
  const stamps = done.map((r) => Number(r.data?.computedAt)).filter((v) => Number.isFinite(v) && v > 0);
  const db: DbTiming = {
    dbMs: measured.length === done.length && done.length ? measured.reduce((a, v) => a + v, 0) : null,
    cached: done.some((r) => r.data?.cached),
    computedAt: stamps.length ? Math.min(...stamps) : null,
    queries: done.length,
  };
  // Gösterilen/kopyalanan metin köprünün koşturduğu fiziksel SQL'dir (mantıksal metin SSMS'te aynı sonucu vermez).
  const physical = NAMES.map((name, i) => [name, q[i].data?.physicalSql] as const).filter(([, t]) => Boolean(t));
  const sources: RawSets['sources'] = {};
  NAMES.forEach((name, i) => {
    sources[name] = q[i].data?.kaynaklar?.sources?.sorgu;
  });
  return shape({
    db,
    sql: physical.length ? physical.map(([name, t]) => `-- ${name}\n${t}`).join('\n\n') : null,
    sources,
    months: rec<MonthRow>(months),
    prevMonths: rec<MonthRow>(prev),
    totals: rec<TotalsRow>(totals)[0] ?? null,
    units: rec<UnitsRow>(units)[0] ?? null,
    channels: rec<ChannelRow>(channels),
    customers: rec<CustomerRow>(customers),
    items: rec<ItemRow>(items),
    returnItems: rec<ReturnItemRow>(returnItems),
  });
}
