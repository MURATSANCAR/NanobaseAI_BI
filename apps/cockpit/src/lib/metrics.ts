/**
 * CEO/CFO kokpit metrikleri — bağlı ERP üstünde doğrulanmış iş kuralları:
 *  - INVOICE.TRCODE: 7/8 satış, 9 verilen hizmet, 2/3 satış iadesi, 1 mal alım, 4 alınan hizmet
 *  - STLINE.LINETYPE: 0 malzeme satırı, 2 iskonto satırı (ciro kadar büyük; net = 0 − 2)
 *  - STLINE.OUTCOST = BİRİM maliyet → satır maliyeti AMOUNT*OUTCOST; maliyetlendirme aylık gecikmeli
 *  - CLCARD.SPECODE2 = satış kanalı, ITEMS.SPECODE = yayınevi (imprint)
 *  - Her sorgu CANCELLED = 0 filtreler.
 * SQL, semantik motorun model adlarıyla yazılır (dbo_LG_<firma>_<dönem>_INVOICE ...).
 *
 * Tablo adları seçilen yıla göre kurulur: Logo her yılı ayrı bir firma numarasında tutar, dolayısıyla
 * yıl değiştirmek sorgunun gittiği tabloyu değiştirir. Bir dönem birden çok yıl taşıyabildiği için
 * (211 = 2021–2025) her sorgu ayrıca yılın tarih aralığıyla sınırlanır — yoksa 2023 sorulduğunda beş
 * yılın toplamı döner.
 */
import { runSql } from './engine';
import { model, type Period } from './periods';
import fixture from '../fixtures/cockpit.json';

export type Monthly = { month: number; sales: number; returns: number; purchases: number };
export type Channel = { channel: string; net: number; customers: number };
export type Imprint = { imprint: string; titles: number; net: number; returnRate: number | null; margin: number | null };

export type CockpitData = {
  source: 'live' | 'fixture';
  /** Rakamların köprüde hesaplanmasının üstünden geçen süre. Kokpit her yenilemede köprünün sıcak
   *  önbelleğinden okur; "canlı" etiketinin arkasında kaç saniyelik bir canlılık olduğunu bu söyler. */
  ageSec: number;
  summary: { sales: number; returns: number; purchases: number; invoices: number; lastDate: string };
  lines: { gross: number; discount: number; costedRevenue: number; cost: number; costUntil: string };
  monthly: Monthly[];
  channels: Channel[];
  imprints: Imprint[];
};

/** Seçilen yılın tabloları ve o yıla ait tarih aralığı. */
export function sqlFor(p: Period, year: number) {
  const INV = model(p, 'INVOICE');
  const STL = model(p, 'STLINE');
  const CLC = model(p, 'CLCARD', false);
  const ITM = model(p, 'ITEMS', false);
  const y0 = `${year}-01-01`;
  const y1 = `${year + 1}-01-01`;
  /** Dönem tek bir yılsa aralık zaten tablonun tamamıdır; yine de yazılır — tablo adı yanlış bir
   *  firmaya düşerse sonuç sessizce başka bir yılın rakamı olmasın. */
  const inYear = (col = '"DATE_"') => `${col} >= '${y0}' AND ${col} < '${y1}'`;
  return {
  summary: `
SELECT
  SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE 0 END) AS sales,
  SUM(CASE WHEN "TRCODE" IN (2,3)   THEN "NETTOTAL" ELSE 0 END) AS returns,
  SUM(CASE WHEN "TRCODE" IN (1,4)   THEN "NETTOTAL" ELSE 0 END) AS purchases,
  SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN 1 ELSE 0 END)          AS invoices,
  MAX("DATE_") AS last_date
FROM ${INV}
WHERE "CANCELLED" = 0 AND ${inYear()}`,
  // Bu MSSQL yolunda EXTRACT/DATE_PART/DATE_TRUNC çevrilemiyor; aylar tarih aralığı kovalarıyla alınır
  // ve istemci tarafında (parseMonthly) satıra çevrilir.
  monthly: `
SELECT
${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]
  .map((m) => {
    const from = `${year}-${String(m).padStart(2, '0')}-01`;
    const to = m === 12 ? `${year + 1}-01-01` : `${year}-${String(m + 1).padStart(2, '0')}-01`;
    const inMonth = `"DATE_" >= '${from}' AND "DATE_" < '${to}'`;
    return [
      `  SUM(CASE WHEN ${inMonth} AND "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE 0 END) AS s${m}`,
      `  SUM(CASE WHEN ${inMonth} AND "TRCODE" IN (2,3)   THEN "NETTOTAL" ELSE 0 END) AS r${m}`,
      `  SUM(CASE WHEN ${inMonth} AND "TRCODE" IN (1,4)   THEN "NETTOTAL" ELSE 0 END) AS p${m}`,
    ].join(',\n');
  })
  .join(',\n')}
FROM ${INV}
WHERE "CANCELLED" = 0`,
  lines: `
SELECT
  SUM(CASE WHEN "LINETYPE" = 0 THEN "TOTAL" ELSE 0 END) AS gross,
  SUM(CASE WHEN "LINETYPE" = 2 THEN "TOTAL" ELSE 0 END) AS discount,
  SUM(CASE WHEN "LINETYPE" = 0 AND "OUTCOST" <> 0 THEN "TOTAL" ELSE 0 END)              AS costed_revenue,
  SUM(CASE WHEN "LINETYPE" = 0 AND "OUTCOST" <> 0 THEN "AMOUNT" * "OUTCOST" ELSE 0 END) AS cost,
  MAX(CASE WHEN "LINETYPE" = 0 AND "OUTCOST" <> 0 THEN "DATE_" END)                     AS cost_until
FROM ${STL}
WHERE "CANCELLED" = 0 AND "TRCODE" IN (7,8) AND ${inYear()}`,
  channels: `
SELECT
  COALESCE(NULLIF(c."SPECODE2", ''), '(boş)') AS channel,
  SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE -i."NETTOTAL" END) AS net,
  COUNT(DISTINCT i."CLIENTREF") AS customers
FROM ${INV} i
JOIN ${CLC} c ON c."LOGICALREF" = i."CLIENTREF"
WHERE i."CANCELLED" = 0 AND i."TRCODE" IN (2,3,7,8,9) AND ${inYear('i."DATE_"')}
GROUP BY COALESCE(NULLIF(c."SPECODE2", ''), '(boş)')
ORDER BY net DESC
LIMIT 8`,
  imprints: `
SELECT
  COALESCE(NULLIF(it."SPECODE", ''), '(boş)') AS imprint,
  COUNT(DISTINCT sl."STOCKREF") AS titles,
  SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."TOTAL" ELSE -sl."TOTAL" END) AS net,
  SUM(CASE WHEN sl."TRCODE" IN (2,3) THEN sl."AMOUNT" ELSE 0 END) AS ret_qty,
  SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."AMOUNT" ELSE 0 END) AS sold_qty,
  SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."AMOUNT" * sl."OUTCOST" ELSE 0 END) AS cost,
  SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."TOTAL" ELSE 0 END) AS costed_revenue
FROM ${STL} sl
JOIN ${ITM} it ON it."LOGICALREF" = sl."STOCKREF"
WHERE sl."CANCELLED" = 0 AND sl."LINETYPE" = 0 AND sl."TRCODE" IN (2,3,7,8) AND ${inYear('sl."DATE_"')}
GROUP BY COALESCE(NULLIF(it."SPECODE", ''), '(boş)')
ORDER BY net DESC
LIMIT 8`,
  };
}

const n = (v: unknown): number => (v == null ? 0 : Number(v));
const s = (v: unknown): string => (v == null ? '' : String(v));

/** s1..s12 / r1..r12 / p1..p12 kovalarını aylık satırlara çevirir; veri olmayan aylar atılır. */
function parseMonthly(row: Record<string, unknown>): Monthly[] {
  const out: Monthly[] = [];
  for (let m = 1; m <= 12; m++) {
    const sales = n(row[`s${m}`]);
    const returns = n(row[`r${m}`]);
    const purchases = n(row[`p${m}`]);
    if (sales === 0 && returns === 0 && purchases === 0) continue;
    out.push({ month: m, sales, returns, purchases });
  }
  return out;
}

export async function loadLive(p: Period, year: number): Promise<CockpitData> {
  const SQL = sqlFor(p, year);
  const [summary, monthly, lines, channels, imprints] = await Promise.all([
    runSql(SQL.summary),
    runSql(SQL.monthly),
    runSql(SQL.lines),
    runSql(SQL.channels),
    runSql(SQL.imprints),
  ]);
  const sm = summary.records[0] ?? {};
  const ln = lines.records[0] ?? {};
  // Beş sorgunun en eskisi tablonun yaşıdır: bir kartı taze gösterip yanındakini eski göstermek
  // okuyanı yanıltır, ekran tek bir ana aittir.
  const ageSec = Math.max(...[summary, monthly, lines, channels, imprints].map((r) => r.ageSec ?? 0));
  return {
    source: 'live',
    ageSec,
    summary: { sales: n(sm.sales), returns: n(sm.returns), purchases: n(sm.purchases), invoices: n(sm.invoices), lastDate: s(sm.last_date) },
    lines: { gross: n(ln.gross), discount: n(ln.discount), costedRevenue: n(ln.costed_revenue), cost: n(ln.cost), costUntil: s(ln.cost_until) },
    monthly: parseMonthly(monthly.records[0] ?? {}),
    channels: channels.records.map((r) => ({ channel: s(r.channel), net: n(r.net), customers: n(r.customers) })),
    imprints: imprints.records.map((r) => {
      const sold = n(r.sold_qty);
      const costed = n(r.costed_revenue);
      return {
        imprint: s(r.imprint),
        titles: n(r.titles),
        net: n(r.net),
        returnRate: sold > 0 ? n(r.ret_qty) / sold : null,
        margin: costed > 0 ? 1 - n(r.cost) / costed : null,
      };
    }),
  };
}

export function loadFixture(): CockpitData {
  const f = fixture as Omit<CockpitData, 'source' | 'ageSec'> & { channels: (Channel & { soldQty?: number; returnQty?: number })[] };
  return { source: 'fixture', ...f, ageSec: 0, channels: f.channels.map(({ channel, net, customers }) => ({ channel, net, customers })) };
}

export type DataMode = 'live' | 'fixture' | 'auto';

/** auto: motor cevap veriyorsa canlı, veremiyorsa fixture (arayüzde "önbellek" etiketiyle). */
export async function loadCockpit(mode: DataMode, p: Period, year: number): Promise<CockpitData> {
  if (mode === 'fixture') return loadFixture();
  if (mode === 'live') return loadLive(p, year);
  try {
    return await loadLive(p, year);
  } catch {
    return loadFixture();
  }
}

/** Türetilmiş göstergeler — kartların tamamı bunlardan beslenir. */
export function derive(d: CockpitData) {
  const netRevenue = d.summary.sales - d.summary.returns;
  const returnRate = d.summary.sales > 0 ? d.summary.returns / d.summary.sales : null;
  const discountRate = d.lines.gross > 0 ? d.lines.discount / d.lines.gross : null;
  const grossMargin = d.lines.costedRevenue > 0 ? 1 - d.lines.cost / d.lines.costedRevenue : null;
  const months = d.monthly.filter((m) => m.sales > 0);
  const last = months[months.length - 1];
  const prev = months[months.length - 2];
  const lastNet = last ? last.sales - last.returns : null;
  const momChange = last && prev ? (last.sales - last.returns) / (prev.sales - prev.returns) - 1 : null;
  const channelTotal = d.channels.reduce((a, c) => a + Math.max(c.net, 0), 0);
  return { netRevenue, returnRate, discountRate, grossMargin, lastNet, momChange, lastMonth: last?.month ?? null, channelTotal };
}
