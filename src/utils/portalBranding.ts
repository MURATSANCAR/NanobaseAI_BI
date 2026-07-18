import { t } from '@/i18n';

export type PortalBranding = {
  brandName: string;
  showPoweredBy: boolean;
};

export const DEFAULT_PORTAL_BRAND = 'NanobaseAI';

export function formatPoweredByLabel(brandName: string): string {
  const name = brandName.trim() || DEFAULT_PORTAL_BRAND;
  return t('ui.poweredBy', { brand: name });
}

export function resolvePortalBranding(input: {
  portal_brand_name?: string | null;
  portal_show_powered_by?: boolean | null;
  brandName?: string | null;
  showPoweredBy?: boolean | null;
}): PortalBranding {
  const brandName =
    String(input.portal_brand_name ?? input.brandName ?? DEFAULT_PORTAL_BRAND).trim() ||
    DEFAULT_PORTAL_BRAND;
  const showPoweredBy =
    input.portal_show_powered_by ?? input.showPoweredBy ?? true;
  return { brandName, showPoweredBy: Boolean(showPoweredBy) && Boolean(brandName) };
}
