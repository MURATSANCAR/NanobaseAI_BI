import { api, type ApiConfig } from '@/api/client';
import { t } from '@/i18n';

/** Download BI export with user-visible error feedback. Returns true on success. */
export async function biDownloadSafe(
  config: ApiConfig,
  path: string,
  filename: string,
  sqlBody?: string,
): Promise<boolean> {
  try {
    await api.bi.download(config, path, filename, sqlBody);
    return true;
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err);
    window.alert(`${t('bi.exportFailed')}\n${detail}`);
    return false;
  }
}
