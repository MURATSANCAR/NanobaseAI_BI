import { ENGINE_BASE, ENGINE_ENABLED } from '../engine';

/**
 * İstemci tarafında üretilen dosyanın (CSV, yazdırma PDF'i) dışa aktarma bildirimi (M49 erişim kaydı). Sunucu tarafı
 * dışa aktarmalar köprünün kapısında kendiliğinden kaydedilir; tarayıcıda üretilenler buradan bildirilir. Bildirim
 * aktarımı beklemez ve durdurmaz: hata sessizce yutulur.
 */
export function notifyExport(what: string, format: 'csv' | 'pdf' | 'xlsx' | 'docx' | 'png' | 'json', rows?: number): void {
  if (!ENGINE_ENABLED) return;
  try {
    void fetch(`${ENGINE_BASE}/api/v1/data-security/export-notice`, {
      method: 'POST',
      credentials: 'include',
      keepalive: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ what, format, rows: rows ?? null, page: window.location.pathname }),
    }).catch(() => undefined);
  } catch {
    /* bildirim yan üründür */
  }
}
