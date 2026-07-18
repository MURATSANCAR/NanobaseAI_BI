import { t } from '@/i18n';
import { emptyDisplayLabel } from '@/utils/comboboxLabels';

const VENDOR_REPLACEMENTS: [RegExp, string][] = [
  [/playwright/gi, 'NanobaseAI'],
  [/maestro/gi, 'NanobaseAI'],
  [/httpx/gi, 'NanobaseAI'],
  [/selenium/gi, 'NanobaseAI'],
  [/cypress/gi, 'NanobaseAI'],
  [/pytest/gi, 'NanobaseAI'],
  [/deerflow/gi, 'NanobaseAI'],
  [/tavily/gi, 'NanobaseAI'],
  [/supabase/gi, 'NanobaseAI'],
  [/hostinger/gi, 'NanobaseAI'],
  [/power\s*bi/gi, 'NanobaseAI'],
  [/oracle\s*bi/gi, 'NanobaseAI'],
  [/apache\s*superset/gi, 'NanobaseAI'],
  [/superset-ui/gi, 'NanobaseAI'],
  [/\bsuperset\b/gi, 'NanobaseAI'],
  [/apache/gi, 'NanobaseAI'],
  [/openai/gi, 'NanobaseAI'],
  [/github/gi, 'NanobaseAI'],
  [/gitlab/gi, 'NanobaseAI'],
  [/postgresql/gi, 'NanobaseAI'],
  [/postgres/gi, 'NanobaseAI'],
  [/mysql/gi, 'NanobaseAI'],
  [/sqlite/gi, 'NanobaseAI'],
  [/librechat/gi, 'NanobaseAI'],
  [/vite/gi, 'NanobaseAI'],
  [/runner/gi, 'NanobaseAI'],
  [/\bllm\b/gi, 'NanobaseAI'],
];

/** Map runtime platform codes to user-facing NanobaseAI labels. */
export function brandPlatform(platform?: string | null): string {
  const p = (platform || '').toLowerCase().trim();
  if (!p) return t('brand.default');
  if (p === 'web' || p.includes('playwright') || p.includes('browser')) return t('brand.web');
  if (p === 'api' || p.includes('httpx') || p.includes('backend')) return t('brand.api');
  return brandText(platform);
}

/** Map suite tier codes to localized labels. */
export function brandTier(tier?: string | null): string {
  const raw = (tier || '').toLowerCase().trim();
  if (!raw) return emptyDisplayLabel();
  const key = `tier.${raw}`;
  const val = t(key);
  return val !== key ? val : brandText(tier || '');
}

/** Strip vendor/tool names from any user-visible string. */
export function brandText(value?: string | null): string {
  if (!value) return t('brand.default');
  let out = value;
  for (const [pattern, replacement] of VENDOR_REPLACEMENTS) {
    out = out.replace(pattern, replacement);
  }
  return out;
}
