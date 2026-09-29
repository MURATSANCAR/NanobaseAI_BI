/**
 * Kullanıcının yazdığı Türkçe sayıyı çözer. Tutar alanları bunu kullanır; «7.500» yazan kişi 7,5 ₺ kaydetmesin.
 *
 * - Virgül varsa virgül ondalık, noktalar binlik ayracıdır: «12.500,50» → 12500.5
 * - Virgül yoksa ve sayı binlik gruplarıyla yazılmışsa noktalar binliktir: «7.500» → 7500, «1.250.000» → 1250000
 * - Öteki yazımlar olduğu gibi okunur: «7.5» → 7.5, «0.125» → 0.125, «7500» → 7500
 * Boşluk, ₺, TL ve % atılır. Çözülemezse `null`.
 */
export function normalizeTrNumber(raw: string): string {
  const t = raw.trim().replace(/\s|₺|%/g, '').replace(/TL$/i, '');
  if (t.includes(',')) return t.replace(/\./g, '').replace(',', '.');
  // 0 ile başlayan («0.125») binlik olamaz; oran ya da ondalıktır.
  if (/^-?[1-9]\d{0,2}(\.\d{3})+$/.test(t)) return t.replace(/\./g, '');
  return t;
}

export function parseTrNumber(raw: string | null | undefined): number | null {
  if (raw == null) return null;
  const t = normalizeTrNumber(String(raw));
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}
