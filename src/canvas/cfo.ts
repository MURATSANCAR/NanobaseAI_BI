import { useQueries } from '@tanstack/react-query';
import { ENGINE_ENABLED, EngineAuthError, runSql } from './engine';

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

/** Altı sorgu paralel gider; motor tarafında 5 dakikalık önbellek var. */
export function useCfoData(): CfoData {
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
      enabled: ENGINE_ENABLED,
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });

  const [months, prev, totals, units, channels, customers, items, returnItems] = q;
  const authRequired = q.some((r) => r.error instanceof EngineAuthError);
  // Tek bir sorgu patlarsa ekranın tamamı düşmesin: gelen veriyle çiz, gelmeyeni
  // boş bırak. Önceden `every(isSuccess)` bekleniyordu ve bir hata her kartı
  // "Yükleniyor"da donduruyordu.
  // Gelen ilk sonuçla çizmeye başla: yavaş kalan tek sorgu bütün kartları
  // bekletmesin. Eksik kart kendi boş durumunu gösterir.
  const ready = ENGINE_ENABLED && !authRequired && q.some((r) => r.isSuccess);
  const failed = !authRequired && ENGINE_ENABLED && q.every((r) => r.isError);

  if (!ready) return { ...EMPTY, ready: false, authRequired, failed };

  const m = (months.data?.records ?? []) as unknown as MonthRow[];
  const p = (prev.data?.records ?? []) as unknown as MonthRow[];
  const t = ((totals.data?.records ?? [])[0] ?? null) as unknown as TotalsRow | null;
  const u = ((units.data?.records ?? [])[0] ?? null) as unknown as UnitsRow | null;

  const observedMonths = m.length ? Math.max(...m.map((r) => r.ay)) : 0;
  const netYtd = m.reduce((a, r) => a + (r.net_ciro ?? 0), 0);
  const netPrevSame = p.filter((r) => r.ay <= observedMonths).reduce((a, r) => a + (r.net_ciro ?? 0), 0);

  return {
    ready: true,
    authRequired: false,
    failed: false,
    year: YEAR,
    months: m,
    prevMonths: p,
    totals: t,
    units: u,
    channels: (channels.data?.records ?? []) as unknown as ChannelRow[],
    customers: (customers.data?.records ?? []) as unknown as CustomerRow[],
    items: (items.data?.records ?? []) as unknown as ItemRow[],
    returnItems: (returnItems.data?.records ?? []) as unknown as ReturnItemRow[],
    observedMonths,
    netYtd,
    netPrevSame,
    yoyPct: netPrevSame > 0 ? (netYtd / netPrevSame - 1) * 100 : null,
    returnPct: t && t.brut_satis > 0 ? (t.iade_tutari / t.brut_satis) * 100 : null,
  };
}
