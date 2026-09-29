/**
 * CSV indiren her yerin Excel eşi (köprüde `csv_excel.py`). Sunucunun ürettiği CSV: aynı adrese `bicim=xlsx` eklenir,
 * aynı uç, aynı yetki ve erişim kaydı; köprü cevabı Excel'e çevirir. Tarayıcıda üretilen CSV: metin köprüye gönderilir,
 * aynı çeviriden geçer (satırlar birebir, sayı/tarih hücreleri gerçek sayı/tarih).
 */
import { ENGINE_BASE } from '../engine';

export const XLSX_PARAM = 'bicim=xlsx';

/** CSV adresinin Excel eşi. */
export function xlsxUrl(csvUrl: string): string {
  const [base, hash] = csvUrl.split('#', 2);
  return `${base}${base.includes('?') ? '&' : '?'}${XLSX_PARAM}${hash ? `#${hash}` : ''}`;
}

/** «rapor.csv» → «rapor.xlsx». */
export function xlsxName(name: string): string {
  return `${name.replace(/\.csv$/i, '')}.xlsx`;
}

/** Tarayıcıda üretilmiş CSV metnini Excel olarak indirir. */
export async function downloadCsvAsXlsx(csv: string, csvFileName: string): Promise<void> {
  const res = await fetch(`${ENGINE_BASE}/api/v1/export/xlsx`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ csv, filename: csvFileName }),
  });
  if (!res.ok) throw new Error(res.status === 401 ? 'Oturum gerekli.' : 'Excel dosyası üretilemedi.');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = xlsxName(csvFileName);
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
