import { mapBackendLabel, formatRegistryPriority } from '@/utils/backendLabels';
import { t } from '@/i18n';

/** Empty / unset `<option>` label (replaces literal em dash). */
export function emptySelectLabel(): string {
  return t('common.none');
}

/** Localized placeholder for missing values in tables and summaries. */
export function emptyDisplayLabel(): string {
  return t('common.none');
}

export const REGISTRY_PRIORITY_OPTIONS = ['P0', 'P1', 'P2'] as const;

export function prioritySelectLabel(priority: string): string {
  if (!priority.trim()) return emptySelectLabel();
  return formatRegistryPriority(priority) || priority;
}

export const HTTP_METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'] as const;

export function httpMethodLabel(method: string): string {
  const raw = String(method ?? '').trim();
  if (!raw) return emptySelectLabel();
  return mapBackendLabel('http.method', raw.toLowerCase(), raw);
}

export function retryCountLabel(n: number): string {
  const key = `run.playwrightRetries${n}` as 'run.playwrightRetries0';
  const label = t(key);
  return label !== key ? label : String(n);
}

/** Localized label for enterprise integration plugin select fields. */
export function integrationSelectLabel(fieldKey: string, value: string): string {
  if (fieldKey === 'healing_mode') {
    return mapBackendLabel('enterprise.integrations.healingMode', value, value);
  }
  return mapBackendLabel(`enterprise.integrations.option.${fieldKey}`, value, value);
}
