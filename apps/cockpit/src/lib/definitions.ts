/**
 * Ekrandaki her göstergenin "nasıl hesaplandığı" — bilgi (i) alanları bunu gösterir.
 * Kaynak: bağlı ERP'nin fatura, hareket, cari ve malzeme tabloları.
 * Rakamlar motordan bağımsız ham T-SQL ile doğrulandı; karşılıkları semantik katalogda sertifikalıdır.
 */
export type MetricInfo = {
  title: string;
  definition: string;
  formula: string;
  sources: string[];
  sql?: string;
  caveats?: string[];
};

const INV = 'LG_411_01_INVOICE (fatura başlığı)';
const STL = 'LG_411_01_STLINE (malzeme hareket satırı)';
const CLC = 'LG_411_CLCARD (cari kart)';
const ITM = 'LG_411_ITEMS (malzeme kartı)';
const ONLY_VALID = 'Yalnız CANCELLED = 0 (iptal edilmemiş) belgeler.';

export const INFO = {
  netRevenue: {
    title: 'Net Ciro',
    definition: '2026 başından veri kesitine kadar satış faturalarının net toplamından satış iadelerinin düşülmesi.',
    formula: 'Net ciro = Σ NETTOTAL (TRCODE 7 perakende satış, 8 toptan satış, 9 verilen hizmet) − Σ NETTOTAL (TRCODE 2 perakende iade, 3 toptan iade)',
    sources: [INV],
    sql: `SELECT SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE 0 END) AS sales,
       SUM(CASE WHEN "TRCODE" IN (2,3) THEN "NETTOTAL" ELSE 0 END) AS returns
FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0`,
    caveats: [ONLY_VALID, 'NETTOTAL fatura net toplamıdır ve KDV içerir (2026 satışlarında KDV payı ≈ %0,5; KDV hariç satış ≈ 917,9 M TL).', 'Döviz faturaları (TRCURR ≠ 0, 74 adet) TL karşılığıyla dahildir.', 'Fatura sayısı = TRCODE 7,8,9 belge adedi.'],
  },
  grossMargin: {
    title: 'Brüt Kâr Marjı',
    definition: 'Maliyetlendirilmiş satış satırlarında satır tutarına göre kâr oranı. Maliyetlendirme aylık gecikmeli çalışır; yalnız OUTCOST ≠ 0 satırlar hesaba girer.',
    formula: 'Marj = 1 − Σ(AMOUNT × OUTCOST) / Σ TOTAL   (LINETYPE 0 malzeme satırı, TRCODE 7,8, OUTCOST ≠ 0)',
    sources: [STL],
    sql: `SELECT SUM(CASE WHEN "LINETYPE" = 0 AND "OUTCOST" <> 0 THEN "TOTAL" ELSE 0 END) AS costed_revenue,
       SUM(CASE WHEN "LINETYPE" = 0 AND "OUTCOST" <> 0 THEN "AMOUNT" * "OUTCOST" ELSE 0 END) AS cost,
       MAX(CASE WHEN "LINETYPE" = 0 AND "OUTCOST" <> 0 THEN "DATE_" END) AS cost_until
FROM dbo_LG_411_01_STLINE WHERE "CANCELLED" = 0 AND "TRCODE" IN (7,8)`,
    caveats: [
      'TOTAL, satırın iskonto ÖNCESİ brüt tutarıdır; iskontolar ayrı satırlarda (LINETYPE 2) tutulur. Bu yüzden marj iskonto öncesi brüt marjdır; iskonto sonrası marj daha düşüktür (2026 için yaklaşık %75).',
      'Maliyet kesiti: OUTCOST işlenmiş son tarih (kartta gösterilir). Sonraki satırlar (≈ 404 M TL) hesaba girmez.',
      ONLY_VALID,
    ],
  },
  returnRate: {
    title: 'İade Oranı (tutar)',
    definition: 'Satış iadelerinin satış tutarına oranı; yanında son kapanan ayın net cirosu ve önceki aya göre değişim.',
    formula: 'İade oranı = Σ NETTOTAL (TRCODE 2,3) / Σ NETTOTAL (TRCODE 7,8,9)',
    sources: [INV],
    caveats: [ONLY_VALID, 'Aylık değişim = (bu ay net − önceki ay net) / önceki ay net; son ay veri kesitine kadar kısmidir.'],
  },
  discountRate: {
    title: 'İskonto Yükü',
    definition: 'Satış faturalarındaki iskonto satırlarının brüt malzeme satırlarına oranı.',
    formula: 'İskonto yükü = Σ TOTAL (LINETYPE 2 iskonto satırı) / Σ TOTAL (LINETYPE 0 malzeme satırı)   (TRCODE 7,8)',
    sources: [STL],
    sql: `SELECT SUM(CASE WHEN "LINETYPE" = 0 THEN "TOTAL" ELSE 0 END) AS gross,
       SUM(CASE WHEN "LINETYPE" = 2 THEN "TOTAL" ELSE 0 END) AS discount
FROM dbo_LG_411_01_STLINE WHERE "CANCELLED" = 0 AND "TRCODE" IN (7,8)`,
    caveats: [ONLY_VALID, 'Satınalma tutarı: TRCODE 1 mal alım + 4 alınan hizmet faturaları (NETTOTAL); alım iadeleri (TRCODE 6, ≈ 20 M TL) düşülmez.'],
  },
  monthly: {
    title: 'Aylık Net Ciro, Satınalma & Nakit Farkı',
    definition: 'Fatura başlığından (INVOICE) ay bazında satış, iade ve alım toplamları. Çubuk net ciro, çizgi alım, kesik çizgi iade, alan ciro − alım farkı.',
    formula: 'Ay = DATE_ takvim ayı. Net ciro = satış (7,8,9) − iade (2,3); alım = mal alım (1) + hizmet (4); fark = net ciro − alım',
    sources: [INV],
    caveats: ['Nakit farkı bir tahsilat/ödeme ölçüsü değildir; fatura tarihine göre tahakkuk bazlıdır.', 'Son ay veri kesitine kadar kısmidir.', ONLY_VALID],
  },
  imprintTitles: {
    title: 'Başlık',
    definition: 'Yayınevinin 2026 içinde satış veya iade hareketi görmüş farklı malzeme (kitap) sayısı.',
    formula: 'COUNT(DISTINCT STOCKREF)   (LINETYPE 0, TRCODE 2,3,7,8)',
    sources: [STL, ITM],
    caveats: ['Yayınevi = malzeme kartındaki özel kod (ITEMS.SPECODE); boş olanlar "(boş)" altında toplanır.'],
  },
  imprintNet: {
    title: 'Net Ciro (yayınevi)',
    definition: 'Yayınevinin satış satır tutarlarından iade satır tutarlarının düşülmesi (satır bazlı, iskonto öncesi).',
    formula: 'Σ TOTAL (TRCODE 7,8) − Σ TOTAL (TRCODE 2,3)   (LINETYPE 0)',
    sources: [STL, ITM],
    caveats: ['Satır bazlı olduğu için üstteki fatura başlığı toplamlarından küçük farklar (≈ %0,6) gösterebilir; iskonto satırları dahil değildir.'],
  },
  imprintMargin: {
    title: 'Brüt Kâr Marjı (yayınevi)',
    definition: 'Yayınevinin maliyetlendirilmiş satış satırlarında marjı; eşikler kural tabanlıdır.',
    formula: '1 − Σ(AMOUNT × OUTCOST) / Σ TOTAL   (TRCODE 7,8, OUTCOST ≠ 0). Rozet: ≥ %70 Yüksek, %55–70 Optimal, < %55 Kritik, maliyet yoksa "Maliyet yok".',
    sources: [STL, ITM],
    caveats: ['İskonto öncesi brüt marjdır (bkz. Brüt Kâr Marjı kartı).'],
  },
  imprintReturn: {
    title: 'İade Oranı (adet)',
    definition: 'Yayınevinin iade edilen adedinin satılan adede oranı.',
    formula: 'Σ AMOUNT (TRCODE 2,3) / Σ AMOUNT (TRCODE 7,8)   (LINETYPE 0). ≥ %15 yüksek iade sayılır.',
    sources: [STL, ITM],
  },
  imprintAdvice: {
    title: 'Kural Tabanlı Uyarı',
    definition: 'Marj ve iade eşiklerinden üretilen deterministik öneri; yapay zekâ üretimi değildir.',
    formula: 'Marj bandı × iade bayrağı (≥ %15) → sabit metin',
    sources: ['Uygulama kuralı (apps/cockpit/src/components/ImprintTable.tsx)'],
  },
  channels: {
    title: 'Kanal Payı',
    definition: 'Cari kartındaki satış kanalı koduna (SPECODE2) göre net ciro ve kanalın toplam içindeki payı; cari sayısı = fatura kesilen farklı cari.',
    formula: 'Net = Σ NETTOTAL (7,8,9) − Σ NETTOTAL (2,3), cari kartı üzerinden gruplanır; pay = kanal net / Σ pozitif kanal netleri',
    sources: [INV, CLC],
    caveats: ['Kanal kodu boş cariler "(boş)" altında; ilk 8 kanal gösterilir.', ONLY_VALID],
  },
  purchases: {
    title: 'Satınalma & Hizmet',
    definition: '2026 mal alım ve alınan hizmet faturalarının net toplamı ve net ciroya oranı.',
    formula: 'Σ NETTOTAL (TRCODE 1 mal alım, 4 alınan hizmet); oran = satınalma / net ciro',
    sources: [INV],
    caveats: ['Alım iadeleri (TRCODE 6) düşülmez; KDV dahildir.', ONLY_VALID],
  },
} satisfies Record<string, MetricInfo>;

export type InfoKey = keyof typeof INFO;
