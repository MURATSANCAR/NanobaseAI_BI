import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';
import type { Catalog, CatalogGroup, CatalogItem, CatalogParam, ColorRole } from './types';

/** Öğeler ve efekt yazı uçları (köprü: /api/v1/editorial/studio/jobs/{job}/plan/…). engine.ts'teki `send` ile
 *  aynı kurallar: adres ENGINE_BASE, oturum çerezi (credentials: include), 401/403 → EngineAuthError, motorun
 *  Türkçe hata metni olduğu gibi taşınır. Yalnız okuyan uçlar var; şekil ve efekt sayfa PUT'uyla kaydedilir. */

const base = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}/plan`;

async function getJson<T>(path: string, timeoutMs = 30_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method: 'GET',
    credentials: 'include',
    headers: freshHeaders(),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || `Zeki AI ${res.status}`);
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | null | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== null && v !== undefined && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const elementsApi = {
  catalog: async (job: string): Promise<Catalog> => normalizeCatalog(await getJson<unknown>(`${base(job)}/elements/catalog`)),
  /** Kitabın paleti ve fontlarıyla küçük PNG. `rev` yalnız tarayıcı önbelleğini tazeler (palet değişince). */
  previewUrl: (job: string, kind: string, w: number, style?: string | null, rev?: string | number | null) =>
    `${ENGINE_BASE}${base(job)}/elements/${encodeURIComponent(kind)}/preview${qs({ w, style, r: rev })}`,
  effectPreviewUrl: (job: string, style: string, w: number, text: string, rev?: string | number | null) =>
    `${ENGINE_BASE}${base(job)}/effects/${encodeURIComponent(style)}/preview${qs({ w, text, r: rev })}`,
};

/** Katalog bir iş boyunca değişmez; bir kez okunur. */
export function useElementCatalog(jobId: string) {
  return useQuery({
    queryKey: ['studio', 'elements', 'catalog', jobId],
    queryFn: () => elementsApi.catalog(jobId),
    enabled: !!jobId,
    staleTime: 30 * 60_000,
    gcTime: 60 * 60_000,
    retry: 1,
  });
}

// ---------------------------------------------------------------- katalog biçimi
// Motor kataloğu liste ya da tür→tanım sözlüğü olarak verebilir; alan adlarında küçük farklar (label/name,
// ratio/aspect, has_text/text) burada tek biçime indirilir. Bilinmeyen alan atılmaz, yalnız okunmaz.

type Raw = Record<string, unknown>;
const isObj = (v: unknown): v is Raw => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown, d = '') => (typeof v === 'string' ? v : v == null ? d : String(v));
const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
const ROLES: ColorRole[] = ['accent', 'soft', 'ink'];
const role = (v: unknown): ColorRole | null => (ROLES.includes(v as ColorRole) ? (v as ColorRole) : null);

function options(v: unknown): { value: string; label: string }[] {
  if (Array.isArray(v)) {
    return v.map((o) => (isObj(o) ? { value: str(o.value ?? o.id ?? o.key), label: str(o.label ?? o.name ?? o.value ?? o.id) } : { value: str(o), label: str(o) }));
  }
  if (isObj(v)) return Object.entries(v).map(([value, label]) => ({ value, label: str(label, value) }));
  return [];
}

function param(key: string, raw: unknown): CatalogParam {
  const o: Raw = isObj(raw) ? raw : { default: raw };
  const opts = options(o.options ?? o.choices ?? o.values);
  const def = o.default;
  let type = str(o.type) as CatalogParam['type'];
  if (!['choice', 'number', 'int', 'bool', 'color', 'text'].includes(type)) {
    type = opts.length ? 'choice'
      : typeof def === 'boolean' ? 'bool'
      : typeof def === 'number' ? (Number.isInteger(def) && !o.step ? 'int' : 'number')
      : typeof def === 'string' && /^#[0-9a-f]{3,8}$/i.test(def) ? 'color'
      : 'text';
  }
  return {
    key, type, options: opts.length ? opts : undefined, default: def,
    label: str(o.label ?? o.name, key), min: num(o.min), max: num(o.max), step: num(o.step), unit: o.unit ? str(o.unit) : undefined,
  };
}

function params(v: unknown): CatalogParam[] {
  if (Array.isArray(v)) return v.filter(isObj).map((p) => param(str(p.key ?? p.name ?? p.id), p)).filter((p) => p.key);
  if (isObj(v)) return Object.entries(v).map(([k, p]) => param(k, p));
  return [];
}

function item(kind: string, o: Raw): CatalogItem {
  const roles = isObj(o.roles) ? o.roles : isObj(o.colors) ? o.colors : {};
  const ps = params(o.params ?? o.parameters);
  // Biçim seçenekleri ya ayrı alanda ya da `style` parametresinin seçeneklerinde.
  let styles = options(o.styles ?? o.variants);
  if (!styles.length) styles = ps.find((p) => p.key === 'style')?.options ?? [];
  const aspect = num(o.aspect) ?? num(o.ratio) ?? (Array.isArray(o.box) && num(o.box[0]) && num(o.box[1]) ? (o.box[0] as number) / (o.box[1] as number) : undefined);
  return {
    kind,
    name: str(o.name ?? o.label ?? o.title, kind),
    group: str(o.group, 'Diğer'),
    aspect: aspect && aspect > 0 ? aspect : 0,
    full_page: o.full_page === true || o.page === true,
    roles: { fill: role(roles.fill), stroke: role(roles.stroke), text: role(roles.text ?? roles.ink) },
    params: ps.filter((p) => p.key !== 'style'),
    text: o.text === true || o.has_text === true || o.carries_text === true,
    styles,
    stroke_w: num(o.stroke_w),
    text_size: num(o.text_size),
  };
}

export function normalizeCatalog(raw: unknown): Catalog {
  const root: Raw = isObj(raw) ? raw : { items: raw };
  const src = root.items ?? root.kinds ?? root.catalog ?? root.elements ?? (isObj(raw) && !root.groups ? raw : []);
  const items: CatalogItem[] = Array.isArray(src)
    ? src.filter(isObj).map((o) => item(str(o.kind ?? o.id ?? o.key), o)).filter((i) => i.kind)
    : isObj(src) ? Object.entries(src).filter(([, o]) => isObj(o)).map(([k, o]) => item(k, o as Raw)) : [];
  // Gruplar: verildiyse o sırayla; verilmediyse öğelerde geçtiği sırayla.
  const given: CatalogGroup[] = Array.isArray(root.groups)
    ? root.groups.map((g) => (isObj(g) ? { id: str(g.id ?? g.key ?? g.name), name: str(g.name ?? g.label ?? g.id) } : { id: str(g), name: str(g) }))
    : isObj(root.groups) ? Object.entries(root.groups).map(([id, name]) => ({ id, name: str(name, id) })) : [];
  const groups = [...given];
  for (const it of items) {
    if (!groups.some((g) => g.id === it.group)) {
      const byName = groups.find((g) => g.name === it.group);
      if (byName) it.group = byName.id;
      else groups.push({ id: it.group, name: it.group });
    }
  }
  return { groups: groups.filter((g) => items.some((i) => i.group === g.id)), items };
}
