import type { MapFields, MapItem } from '../royalty/api';

/** Hak haritasının ekran metni (saf; test edilir). */

export const MAP_ORDER: Array<keyof MapFields> = ['format', 'dil', 'ulke', 'bitis', 'munhasirlik'];

export const itemsOf = (f: MapFields, k: keyof MapFields): MapItem[] => {
  const v = f[k];
  return Array.isArray(v) ? v : v ? [v] : [];
};

export const isEmptyMap = (f: MapFields) => MAP_ORDER.every((k) => !itemsOf(f, k).length);

/** Değerin gösterimi: tarih yerel biçimde, biçim/münhasırlık adıyla, diğerleri metindeki yazımıyla. */
export const shown = (x: MapItem) => (x.tarih ? new Date(`${x.tarih}T00:00:00`).toLocaleDateString('tr-TR') : x.ad ?? x.deger);

export const mapSummary = (f: MapFields) => MAP_ORDER.flatMap((k) => itemsOf(f, k).map(shown)).join(' · ');

export const usesModel = (f: MapFields) => MAP_ORDER.some((k) => itemsOf(f, k).some((x) => x.kaynak === 'zeki'));

/** Onaydan önce bir değeri çıkarma (liste alanında o öğe, tek değerli alanda alan boşalır). */
export function dropItem(f: MapFields, k: keyof MapFields, i: number): MapFields {
  const v = f[k];
  return { ...f, [k]: Array.isArray(v) ? v.filter((_, j) => j !== i) : null };
}
