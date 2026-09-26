import { useQuery } from '@tanstack/react-query';
import { ENGINE_BASE, EngineAuthError, freshHeaders } from '../../../engine';
import {
  COLOR_ROLES, EFFECT_STYLES, type Catalog, type CatalogEffect, type CatalogGroup, type CatalogItem, type CatalogParam,
  type CatalogStyle, type ColorRole, type EffectStyle, type RoleColors, type Run,
} from './types';

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
  /** `key` paletin özeti: palet değişince rol renkleri yeniden okunur (tarayıcı önbelleği atlanır). */
  catalog: async (job: string, key?: string | number | null): Promise<Catalog> =>
    normalizeCatalog(await getJson<unknown>(`${base(job)}/elements/catalog${qs({ r: key })}`)),
  /** Kitabın paleti ve fontlarıyla küçük PNG. `style` hazır biçimin anahtarı (`CatalogStyle.value`). `rev` yalnız
   *  tarayıcı önbelleğini tazeler (palet değişince; çağıran paletin özetini verir, planın her sürümünü değil). */
  previewUrl: (job: string, kind: string, w: number, style?: string | null, rev?: string | number | null) =>
    `${ENGINE_BASE}${base(job)}/elements/${encodeURIComponent(kind)}/preview${qs({ w, style, r: rev })}`,
  effectPreviewUrl: (job: string, style: string, w: number, text: string, rev?: string | number | null) =>
    `${ENGINE_BASE}${base(job)}/effects/${encodeURIComponent(style)}/preview${qs({ w, text, r: rev })}`,
};

/** Katalog bir iş boyunca değişmez (rol renkleri paletle değişir: anahtara paletin özeti girer). */
export function useElementCatalog(jobId: string, paletteKey?: string | number | null) {
  return useQuery({
    queryKey: ['studio', 'elements', 'catalog', jobId, paletteKey ?? ''],
    queryFn: () => elementsApi.catalog(jobId, paletteKey),
    enabled: !!jobId,
    staleTime: 30 * 60_000,
    gcTime: 60 * 60_000,
    retry: 1,
    placeholderData: (prev) => prev,
  });
}

// ---------------------------------------------------------------- katalog biçimi
// Motorun (`elements.catalog`) çıktısı:
//   {groups: [{key, name, kinds}], kinds: [{kind, name, group, text, box: {w, ratio, place}, fill, stroke, stroke_w,
//    params: {anahtar: {label, type, default, choices: [{value, label}], min, max, step}}, runs,
//    presets: [{key, name, params, box}]}], effects: [{style, name, sample, box, params}], roles: [{key, name, hex}],
//    fonts}
// Ekrandaki biçim `types.ts` → Catalog. Tek dönüşüm burası; alan adı farkı başka yerde kapatılmaz.

type Raw = Record<string, unknown>;
const isObj = (v: unknown): v is Raw => !!v && typeof v === 'object' && !Array.isArray(v);
const str = (v: unknown, d = '') => (typeof v === 'string' ? v : v == null ? d : String(v));
const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
const role = (v: unknown): ColorRole | 'none' | null => (v === 'none' ? 'none' : COLOR_ROLES.includes(v as ColorRole) ? (v as ColorRole) : null);
const TYPES: CatalogParam['type'][] = ['choice', 'number', 'int', 'bool', 'color', 'colors', 'text'];
const PLACES = ['center', 'page', 'corner'] as const;
const place = (v: unknown) => (PLACES.includes(v as (typeof PLACES)[number]) ? (v as (typeof PLACES)[number]) : undefined);

function options(v: unknown): { value: string; label: string }[] {
  if (!Array.isArray(v)) return [];
  return v.map((o) => (isObj(o) ? { value: str(o.value ?? o.key), label: str(o.label ?? o.name ?? o.value) } : { value: str(o), label: str(o) }));
}

function param(key: string, o: Raw): CatalogParam {
  const opts = options(o.choices);
  const t = str(o.type) as CatalogParam['type'];
  return {
    key, type: TYPES.includes(t) ? t : opts.length ? 'choice' : 'text', options: opts.length ? opts : undefined, default: o.default,
    label: str(o.label, key), min: num(o.min), max: num(o.max), step: num(o.step),
  };
}

const params = (v: unknown): CatalogParam[] => (isObj(v) ? Object.entries(v).filter(([, p]) => isObj(p)).map(([k, p]) => param(k, p as Raw)) : []);

function runs(v: unknown): Run[] {
  return Array.isArray(v) ? v.filter(isObj).map((r) => ({ ...(r as Run), text: str(r.text) })) : [];
}

function presetBox(v: unknown): CatalogStyle['box'] {
  if (!isObj(v)) return null;
  return { w: num(v.w), ratio: num(v.ratio), place: place(v.place) };
}

function item(o: Raw): CatalogItem {
  const box = isObj(o.box) ? o.box : {};
  const styles: CatalogStyle[] = Array.isArray(o.presets)
    ? o.presets.filter(isObj).map((p) => ({ value: str(p.key), label: str(p.name, str(p.key)), params: isObj(p.params) ? p.params : {}, box: presetBox(p.box) }))
    : [];
  const text = o.text === true;
  return {
    kind: str(o.kind),
    name: str(o.name, str(o.kind)),
    group: str(o.group, 'diger'),
    aspect: num(box.ratio) ?? 1,
    width: num(box.w) ?? 0.4,
    place: place(box.place) ?? 'center',
    full_page: box.place === 'page',
    roles: { fill: role(o.fill), stroke: role(o.stroke), text: 'ink' },
    params: params(o.params),
    text,
    runs: text ? runs(o.runs) : [],
    styles,
    stroke_w: num(o.stroke_w),
    text_size: num(o.text_size) ?? null,
  };
}

function effect(o: Raw): CatalogEffect | null {
  const style = str(o.style) as EffectStyle;
  if (!EFFECT_STYLES.includes(style)) return null;
  return { style, name: str(o.name, style), sample: str(o.sample), params: params(o.params) };
}

export function normalizeCatalog(raw: unknown): Catalog {
  const root: Raw = isObj(raw) ? raw : {};
  const items = (Array.isArray(root.kinds) ? root.kinds : []).filter(isObj).map(item).filter((i) => i.kind);
  const groups: CatalogGroup[] = (Array.isArray(root.groups) ? root.groups : []).filter(isObj)
    .map((g) => ({ id: str(g.key), name: str(g.name, str(g.key)) }));
  for (const it of items) if (!groups.some((g) => g.id === it.group)) groups.push({ id: it.group, name: 'Diğer' });
  const effects = (Array.isArray(root.effects) ? root.effects : []).filter(isObj).map(effect).filter((e): e is CatalogEffect => !!e);
  const roles: RoleColors = {};
  for (const r of Array.isArray(root.roles) ? root.roles : []) {
    if (!isObj(r)) continue;
    const k = role(r.key);
    if (k && k !== 'none' && typeof r.hex === 'string') roles[k] = { name: str(r.name, k), hex: r.hex };
  }
  return { groups: groups.filter((g) => items.some((i) => i.group === g.id)), items, effects, roles };
}
