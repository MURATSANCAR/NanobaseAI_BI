import type { Kaynaklar } from './sqlInfo';

/**
 * Bir uç cevabının sorgu bilgisi (`kaynaklar`). Cevap tipinde alan tanımlı olmasa da (eski tipler) köprü onu
 * ekler; tipi değiştirmeden okumak için. Yoksa undefined — «i» hiç çıkmaz.
 */
export function kaynakOf(data: unknown): Kaynaklar | undefined {
  if (!data || typeof data !== 'object') return undefined;
  const k = (data as { kaynaklar?: unknown }).kaynaklar;
  return k && typeof k === 'object' ? (k as Kaynaklar) : undefined;
}
