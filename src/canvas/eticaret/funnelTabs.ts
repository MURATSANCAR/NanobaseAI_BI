/** Tek huni ekranının sekmeleri (README «hemen düzeltilecekler» 9): M34 ürün sayaçları + H3 sipariş hunisi. */

export const FUNNEL_PATH = '/e-ticaret/huni';

export const FUNNEL_TABS = [
  { key: 'sayac', label: 'Ürün sayaçları', hint: 'Tüm zamanlar · Logo son dönem' },
  { key: 'siparis', label: 'Sipariş hunisi', hint: 'Son 7/30/90 gün · site siparişleri' },
] as const;
export type FunnelTab = (typeof FUNNEL_TABS)[number]['key'];

/** Adres çubuğundaki `sekme`; bilinmeyen değer ilk sekme. */
export const funnelTab = (raw: string | null): FunnelTab => (raw === 'siparis' ? 'siparis' : 'sayac');

/** Eski H3 adresi (/eticaret-musteri/huni) buraya yönlenir. */
export const UNIFIED_FUNNEL = `${FUNNEL_PATH}?sekme=siparis`;
