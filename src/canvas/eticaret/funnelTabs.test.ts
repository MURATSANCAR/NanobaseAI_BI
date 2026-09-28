import { describe, expect, it } from 'vitest';
import { NAV, matchActive, permissionItemFor } from '../nav/navModel';
import { FUNNEL_PATH, FUNNEL_TABS, UNIFIED_FUNNEL, funnelTab } from './funnelTabs';

describe('tek huni ekranı (H3 + M34)', () => {
  it('iki sekme: ürün sayaçları (M34) ve sipariş hunisi (H3); bilinmeyen sekme ilk sekme', () => {
    expect(FUNNEL_TABS.map((t) => t.key)).toEqual(['sayac', 'siparis']);
    expect(funnelTab(null)).toBe('sayac');
    expect(funnelTab('siparis')).toBe('siparis');
    expect(funnelTab('baska')).toBe('sayac');
  });

  it('eski H3 adresi tek ekrana, sipariş sekmesiyle yönlenir; menü ve sayfa yetkisi değişmez', () => {
    expect(UNIFIED_FUNNEL).toBe('/e-ticaret/huni?sekme=siparis');
    expect(permissionItemFor(UNIFIED_FUNNEL)?.id).toBe('eticaret-huni');
    expect(permissionItemFor(FUNNEL_PATH)?.id).toBe('eticaret-huni');
    // Eski adres H3 sayfasının altında kalır: o sayfası olan kişi yönlenmeden önce kapıdan geçer.
    expect(matchActive(NAV, '/eticaret-musteri/huni')?.item.id).toBe('eticaret-musteri');
    // Menüde tek «Huni» öğesi var.
    const funnels = NAV.flatMap((g) => g.items).filter((i) => i.to.includes('huni'));
    expect(funnels.map((i) => i.id)).toEqual(['eticaret-huni']);
  });
});
