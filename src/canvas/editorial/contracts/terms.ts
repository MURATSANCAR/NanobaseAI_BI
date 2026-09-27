import type { Meta, Status, Terms } from './api';
import { day, money, num } from './ui';

/** Şart alanlarının ekrandaki yazılışı ve iki şart arasındaki fark (sunucudaki `contracts_terms` ile aynı kurallar). */

export function show(field: string, v: unknown, meta: Meta, cur = 'TRY'): string {
  if (v == null || v === '' || (Array.isArray(v) && !v.length)) return '—';
  if (field.startsWith('rights.')) return v ? 'Var' : 'Yok';
  if (field.startsWith('rates.') || field === 'discountPct' || field === 'withholdingPct') return `%${num(v as number)}`;
  if (field === 'advance' || field === 'flatFee') return money(v as number, cur);
  if (field === 'openEnded' || field === 'advanceRecoupable') return v ? 'Evet' : 'Hayır';
  if (field === 'start' || field === 'end') return day(v as string);
  if (field === 'kind') return meta.kinds[v as string] ?? String(v);
  if (field === 'paymentType') return meta.paymentTypes[v as string] ?? String(v);
  if (field === 'basis') return meta.bases[v as string] ?? String(v);
  if (field === 'currency') return meta.currencies[v as string] ?? String(v);
  if (field === 'status') return meta.statuses[v as Status] ?? String(v);
  if (field === 'parties')
    return (v as Terms['parties']).map((p) => `${p.name}${p.share != null ? ` (%${num(p.share)})` : ''}`).join('; ');
  if (field === 'books') return (v as Terms['books']).map((b) => b.title).join('; ');
  if (field === 'tiers') return (v as Terms['tiers']).map((t) => `${num(t.from, 0)} adetten %${num(t.rate)}`).join('; ');
  if (typeof v === 'number') return num(v);
  return String(v);
}

/** Şartları düz anahtarlara açar (sunucudaki `flatten` ile aynı): rates.karton, rights.iletim… */
export function flatten(t: Terms, meta: Meta): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of Object.keys(meta.labels)) {
    if (key.includes('.')) {
      const [g, s] = key.split('.');
      const grp = (t as unknown as Record<string, Record<string, unknown>>)[g] ?? {};
      out[key] = g === 'rights' ? !!grp[s] : (grp[s] ?? null);
    } else out[key] = (t as unknown as Record<string, unknown>)[key];
  }
  return out;
}

const norm = (v: unknown) => (v === '' || v === undefined || (Array.isArray(v) && !v.length) ? null : v);
export function changedFields(before: Terms, after: Terms, meta: Meta): Record<string, unknown> {
  const a = flatten(before, meta);
  const b = flatten(after, meta);
  const out: Record<string, unknown> = {};
  for (const k of Object.keys(b)) if (JSON.stringify(norm(a[k])) !== JSON.stringify(norm(b[k]))) out[k] = b[k];
  return out;
}

