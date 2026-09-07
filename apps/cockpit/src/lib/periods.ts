/**
 * Hangi yılın verisi nerede duruyor.
 *
 * Logo bir yılı bir "firma" olarak tutar: 2026 `LG_411_*` tablolarında, 2021–2025 `LG_211_*`
 * tablolarında, 2018 `LG_181_*` tablolarında. Yani ekranda yıl değiştirmek, sorgunun hangi tabloya
 * gideceğini değiştirmek demektir — tarih filtresi değil. Kokpit tek bir yılı (411) sabit yazdığı
 * sürece geri kalan her yıl, veritabanında dururken, ekranda yok gibiydi.
 *
 * Eşleme buraya yazılmaz; veritabanının kendi dönem tablosundan okunur. Müşteri yeni bir yıl açtığında
 * ekran onu kendiliğinden görür.
 */
import { runSql } from './engine';

export type Period = {
  /** Logo firma numarası — tablo adındaki ilk sayı: LG_<firm>_<period>_INVOICE */
  firm: string;
  /** Dönem numarası — tablo adındaki ikinci sayı */
  period: string;
  /** Bu dönemin kapsadığı yıllar; 211 gibi bir dönem beş yılı birden taşıyabilir */
  years: number[];
  from: string;
  to: string;
};

/** Model adı: köprü tabloları `dbo_LG_411_01_INVOICE` biçiminde tanır. */
export function model(p: Period, table: string, periodic = true): string {
  return periodic ? `dbo_LG_${p.firm}_${p.period}_${table}` : `dbo_LG_${p.firm}_${table}`;
}

const PERIODS_SQL = `
SELECT "FIRMNR" AS firm, "NR" AS period, "BEGDATE" AS beg, "ENDDATE" AS end_
FROM dbo_L_CAPIPERIOD
ORDER BY "BEGDATE"`;

function yearsBetween(from: string, to: string): number[] {
  const a = new Date(from).getFullYear();
  const b = new Date(to).getFullYear();
  if (!Number.isFinite(a) || !Number.isFinite(b) || b < a) return [];
  return Array.from({ length: b - a + 1 }, (_, i) => a + i);
}

/** Logo firma numarasını tablo adındaki haliyle yazar: 15 → "015", 411 → "411". */
function firmCode(v: unknown): string {
  const n = Number(v);
  return Number.isFinite(n) ? String(n).padStart(3, '0') : String(v ?? '');
}

export async function loadPeriods(): Promise<Period[]> {
  const res = await runSql(PERIODS_SQL);
  const rows = res.records
    .map((r) => {
      const from = String(r.beg ?? '').slice(0, 10);
      const to = String(r.end_ ?? '').slice(0, 10);
      return {
        firm: firmCode(r.firm),
        period: String(Number(r.period ?? 1)).padStart(2, '0'),
        years: yearsBetween(from, to),
        from,
        to,
      };
    })
    .filter((p) => p.firm && p.years.length);
  return rows.sort((a, b) => a.from.localeCompare(b.from));
}

/**
 * Seçilebilecek yıllar, yeniden eskiye.
 *
 * Aynı yıl birden çok firmada bulunabilir — müşteride 2015 hem 015 hem 105 numarasında duruyor,
 * eski bir taşımanın artığı. Yıl bir kez listelenir ve en son açılmış firma kazanır: aynı yılı iki
 * kez göstermek, okuyana iki farklı 2015 varmış gibi gelir.
 */
export function yearIndex(periods: Period[]): Map<number, Period> {
  const out = new Map<number, Period>();
  for (const p of periods) for (const y of p.years) out.set(y, p);
  return out;
}

export function yearsOf(periods: Period[]): number[] {
  return [...yearIndex(periods).keys()].sort((a, b) => b - a);
}

/** Varsayılan yıl: elde veri olan en yeni yıl. Sabit bir yıl yazmak, yıl dönümünde ekranı boşaltır. */
export function latestYear(periods: Period[]): number | null {
  return yearsOf(periods)[0] ?? null;
}
