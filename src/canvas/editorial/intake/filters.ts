import type { IntakeCard } from '../../engine';

/**
 * Yazar giriş panosunun süzgeçleri. Durum adres çubuğunda durur (paylaşılan bağlantı aynı görünümü açar);
 * süzme tarayıcıda yapılır, çünkü pano bütün projeleri tek cevapta getirir.
 *
 * Süzgeç seçimi (2026-09-29, canlı CRM, pano kapsamındaki 2.112 proje): marka 2.110 dolu, proje türü 2.112,
 * başvuru tarihi 2.112, editör 1.407 (boşu «Editör atanmamış» diye ayrı seçenek; o da bir adım). Adım
 * hesaplanan değerdir, her süren projede var. Kitaplık (902), dizi (749) ve oluşturma kanalı (985) yarıdan
 * az dolu olduğu için süzgeç değil: seçildiğinde projelerin çoğunu sessizce dışarıda bırakırdı.
 */

/** Alanı boş kayıtların seçenek değeri («Editör atanmamış» gibi). */
export const NONE = '-';

export type Facet = 'brand' | 'editor' | 'step' | 'type' | 'year';

export type IntakeFilters = {
  q: string;
  brand: string;
  editor: string;
  step: string;
  type: string;
  year: string;
  late: boolean;
  mine: boolean;
};

/** Adres çubuğundaki adlar. */
export const PARAM: Record<keyof IntakeFilters, string> = {
  q: 'ara',
  brand: 'marka',
  editor: 'editor',
  step: 'adim',
  type: 'tur',
  year: 'yil',
  late: 'geciken',
  mine: 'benim',
};

export const FACETS: Facet[] = ['brand', 'editor', 'step', 'type', 'year'];

export function readFilters(p: URLSearchParams): IntakeFilters {
  const s = (k: keyof IntakeFilters) => (p.get(PARAM[k]) ?? '').trim();
  return {
    q: s('q'),
    brand: s('brand'),
    editor: s('editor'),
    step: s('step'),
    type: s('type'),
    year: s('year'),
    late: p.get(PARAM.late) === '1',
    mine: p.get(PARAM.mine) === '1',
  };
}

/** Tek süzgeci değiştirir; boş değer ve kapalı düğme adresten silinir. Diğer parametreler (evre vb.) korunur. */
export function withFilter(p: URLSearchParams, key: keyof IntakeFilters, value: string | boolean): URLSearchParams {
  const n = new URLSearchParams(p);
  const v = typeof value === 'boolean' ? (value ? '1' : '') : value.trim();
  if (v) n.set(PARAM[key], v);
  else n.delete(PARAM[key]);
  return n;
}

export function withoutFilters(p: URLSearchParams): URLSearchParams {
  const n = new URLSearchParams(p);
  for (const k of Object.values(PARAM)) n.delete(k);
  return n;
}

export const valueOf: Record<Facet, (c: IntakeCard) => string> = {
  brand: (c) => c.brand || NONE,
  editor: (c) => c.editor || NONE,
  step: (c) => (c.step ? String(c.step) : NONE),
  type: (c) => c.projectType || NONE,
  year: (c) => (c.createdOn || '').slice(0, 4) || NONE,
};

export function matchText(c: IntakeCard, q: string): boolean {
  if (!q) return true;
  const t = q.toLocaleLowerCase('tr');
  return [c.name, c.author, c.editor].some((v) => (v || '').toLocaleLowerCase('tr').includes(t));
}

/** Kart bütün süzgeçlere uyuyor mu; `skip` verilen süzgeç yok sayılır (o süzgecin seçenek sayıları için). */
export function matches(c: IntakeCard, f: IntakeFilters, skip?: Facet | 'late' | 'mine'): boolean {
  if (!matchText(c, f.q)) return false;
  for (const k of FACETS) if (k !== skip && f[k] && valueOf[k](c) !== f[k]) return false;
  if (skip !== 'late' && f.late && !c.late) return false;
  if (skip !== 'mine' && f.mine && !c.mine) return false;
  return true;
}

export type FacetOption = { value: string; count: number };

/**
 * Bir süzgecin seçenekleri ve sayıları: diğer süzgeçler uygulanmış kartlarda o değeri taşıyan kart sayısı.
 * Seçili değer o an hiç kartta yoksa bile listede kalır (sayısı 0), yoksa seçim ekranda görünmez olurdu.
 */
export function facetOptions(cards: IntakeCard[], f: IntakeFilters, facet: Facet): FacetOption[] {
  const counts = new Map<string, number>();
  for (const c of cards) {
    if (!matches(c, f, facet)) continue;
    const v = valueOf[facet](c);
    counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  if (f[facet] && !counts.has(f[facet])) counts.set(f[facet], 0);
  const rows = [...counts.entries()].map(([value, count]) => ({ value, count }));
  const tr = (a: string, b: string) => a.localeCompare(b, 'tr');
  const noneFirst = (a: FacetOption, b: FacetOption) => Number(b.value === NONE) - Number(a.value === NONE);
  if (facet === 'step') return rows.sort((a, b) => Number(a.value) - Number(b.value));
  if (facet === 'year') return rows.sort((a, b) => noneFirst(b, a) || tr(b.value, a.value));
  // Editör adıyla aranır (kişi bulunur); marka ve tür en kalabalıktan.
  if (facet === 'editor') return rows.sort((a, b) => noneFirst(a, b) || tr(a.value, b.value));
  return rows.sort((a, b) => noneFirst(b, a) || b.count - a.count || tr(a.value, b.value));
}

/** Açık süzgeç sayısı (arama dahil). */
export function activeCount(f: IntakeFilters): number {
  return [f.q, ...FACETS.map((k) => f[k])].filter(Boolean).length + Number(f.late) + Number(f.mine);
}
