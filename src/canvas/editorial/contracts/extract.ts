import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError } from '../../engine';
import { httpErrorText } from '../../httpError';
import type { Kaynaklar } from '../../components/sqlInfo';
import type { Meta, Terms } from './api';

/** Öneri 13 — sözleşme belgesinden şart çıkarma: köprünün `/api/v1/editorial/contracts/extracts` uçları ve
 *  önerinin forma uygulanması (saf; vitest). Değerler belgedeki alıntının kendisinden okunur; forma yalnız insanın
 *  seçtiği alanlar geçer, kaydı insan yapar. */

export type Evidence = { alinti: string; sayfa: string; okuma: 'metin' | 'ocr' | 'yok'; guven?: number | null };
export type Candidate = { deger: string | number | null; kanit: Evidence[]; kaynak: 'kural' | 'zeki' | null; celiski?: Candidate[] | null; ad?: string };
export type RightsItem = { deger: string; alinti: string; kaynak: 'kural' | 'zeki'; sayfa: string; okuma: string; ad?: string; tarih?: string };

export type Suggestion = Partial<{
  paymentType: string;
  basis: string;
  currency: string;
  advance: number;
  flatFee: number;
  withholdingPct: number;
  start: string;
  end: string;
  years: number;
  rates: Record<string, number>;
  rights: Record<string, boolean>;
  language: string;
  territory: string;
  notesLine: string;
  openEnded: boolean;
  gecersiz: string;
}>;

export type ExtractResult = {
  alanlar: Record<string, Candidate>;
  haklar: { dil: RightsItem[]; ulke: RightsItem[]; format: RightsItem[]; bitis: RightsItem | null; munhasirlik: RightsItem | null };
  maliHaklar: Array<{ deger: string; ad: string; kanit: Evidence[]; kaynak: string }>;
  oneri: Suggestion;
  atilan: number;
  kaynak: 'zeki' | 'kural';
  neden: string | null;
  pencere: { sayi: number; butce: number; ortusme: number; okunamayan: string[] };
  okuma: { sayfa: number; ocrSayfa: string[]; okunamayan: string[]; not: string | null; hatalar: string[] };
};

export type Extract = {
  id: string;
  contractKey: string | null;
  filename: string;
  bytes: number;
  status: 'hazirlaniyor' | 'hazir' | 'hata';
  statusLabel: string;
  done: number;
  total: number;
  error: string | null;
  createdBy: string;
  createdAt: string;
  finishedAt: string | null;
  accepted: string[] | null;
  acceptedBy: string | null;
  acceptedAt: string | null;
  result: ExtractResult | null;
};

const BASE = '/api/v1/editorial/contracts/extracts';
const enc = encodeURIComponent;

async function call<T>(path: string, init: { method?: string; body?: unknown; raw?: BodyInit; timeout?: number } = {}): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const method = init.method ?? 'GET';
  const res = await fetch(`${ENGINE_BASE}${BASE}${path}`, {
    method,
    credentials: 'include',
    headers: init.body !== undefined ? { 'Content-Type': 'application/json' } : init.raw ? { 'Content-Type': 'application/octet-stream' } : undefined,
    body: init.raw ?? (init.body !== undefined ? JSON.stringify(init.body) : undefined),
    signal: AbortSignal.timeout(init.timeout ?? 60_000),
  });
  if (res.status === 401) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } | string } | null;
    const detail = j?.detail;
    const msg = typeof detail === 'string' ? detail : detail?.message;
    if (res.status === 403 && typeof detail === 'object' && detail?.code === 'FORBIDDEN') throw new EngineForbiddenError(msg);
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

export const extractApi = {
  upload: (file: File, key?: string) =>
    call<Extract>(`?filename=${enc(file.name)}${key ? `&key=${enc(key)}` : ''}`, { method: 'PUT', raw: file, timeout: 300_000 }),
  get: (id: string) => call<{ item: Extract; model: boolean; kaynaklar?: Kaynaklar }>(`/${enc(id)}`),
  forContract: (key: string) => call<{ items: Extract[]; model: boolean; kaynaklar?: Kaynaklar }>(`?key=${enc(key)}`),
  accepted: (id: string, fields: string[], key?: string) => call<Extract>(`/${enc(id)}/accepted`, { method: 'POST', body: { fields, key } }),
  remove: (id: string) => call<{ ok: boolean }>(`/${enc(id)}`, { method: 'DELETE' }),
  fileUrl: (id: string) => `${ENGINE_BASE}${BASE}/${enc(id)}/file`,
};

export const ACCEPT_FILES = '.pdf,.docx,.odt,.txt,.png,.jpg,.jpeg,.tif,.tiff,.webp';

// ------------------------------------------------------------------------------------------------ öneri → form (saf)

export type Row = {
  /** Kabul kaydındaki alan adı: `advance`, `rates.karton`, `rights.ekitap`, `notesLine` … */
  key: string;
  label: string;
  /** Önerilen değerin ekrandaki yazımı. */
  text: string;
  evidence: Evidence[];
  source: 'kural' | 'zeki' | null;
};

const numText = (v: number, d = 2) => new Intl.NumberFormat('tr-TR', { maximumFractionDigits: d }).format(v);
const dayText = (iso: string) => {
  const [y, m, d] = iso.split('-');
  return y && m && d ? `${d}.${m}.${y}` : iso;
};
/** Biçim hakkı (M54 hak haritası) → sözleşme şartlarındaki mali hak (köprüdeki `FORMAT_TO_RIGHT` ile aynı). */
const FORMAT_TO_RIGHT: Record<string, string> = { 'e-kitap': 'ekitap', sesli: 'sesli', ceviri: 'ceviri' };
const ev = (it: RightsItem): Evidence => ({ alinti: it.alinti, sayfa: it.sayfa, okuma: it.okuma as Evidence['okuma'] });

/** Önerinin ekrandaki satırları: her satır tek alan, değeri ve dayandığı alıntılar. */
export function suggestionRows(r: ExtractResult, meta: Pick<Meta, 'paymentTypes' | 'bases' | 'currencies' | 'rates' | 'rights'>): Row[] {
  const s = r.oneri;
  const a = r.alanlar;
  const cur = s.currency ?? 'TRY';
  const rows: Row[] = [];
  const from = (field: string) => ({ evidence: a[field]?.kanit ?? [], source: a[field]?.kaynak ?? null });
  if (s.paymentType) rows.push({ key: 'paymentType', label: 'Ödeme şekli', text: meta.paymentTypes[s.paymentType] ?? s.paymentType, ...from('paymentType') });
  if (s.basis) rows.push({ key: 'basis', label: 'Telif esası', text: meta.bases[s.basis] ?? s.basis, ...from('basis') });
  for (const [k, v] of Object.entries(s.rates ?? {})) rows.push({ key: `rates.${k}`, label: `${meta.rates[k] ?? k} telifi`, text: `%${numText(v)}`, ...from(`rates.${k}`) });
  if (s.withholdingPct != null) rows.push({ key: 'withholdingPct', label: 'Stopaj oranı', text: `%${numText(s.withholdingPct)}`, ...from('withholdingPct') });
  if (s.advance != null) rows.push({ key: 'advance', label: 'Avans', text: `${numText(s.advance)} ${meta.currencies[cur] ?? cur}`, ...from('advance') });
  if (s.flatFee != null) rows.push({ key: 'flatFee', label: 'Tek ödeme tutarı', text: `${numText(s.flatFee)} ${meta.currencies[cur] ?? cur}`, ...from('flatFee') });
  if (s.currency) rows.push({ key: 'currency', label: 'Para birimi', text: meta.currencies[s.currency] ?? s.currency, ...from('currency') });
  if (s.start) rows.push({ key: 'start', label: 'Başlangıç', text: dayText(s.start), ...from('start') });
  if (s.end) rows.push({ key: 'end', label: 'Bitiş', text: dayText(s.end), ...from('end') });
  if (s.years != null) rows.push({ key: 'years', label: 'Süre', text: `${numText(s.years)} yıl`, ...from('years') });
  if (s.language) rows.push({ key: 'language', label: 'Dil', text: s.language, evidence: r.haklar.dil.map(ev), source: r.haklar.dil[0]?.kaynak ?? null });
  if (s.territory) rows.push({ key: 'territory', label: 'Bölge', text: s.territory, evidence: r.haklar.ulke.map(ev), source: r.haklar.ulke[0]?.kaynak ?? null });
  for (const k of Object.keys(s.rights ?? {})) {
    const m = r.maliHaklar.find((x) => x.deger === k);
    const f = r.haklar.format.find((x) => FORMAT_TO_RIGHT[x.deger] === k);
    rows.push({ key: `rights.${k}`, label: `${meta.rights[k] ?? k} hakkı`, text: 'var', evidence: m ? m.kanit : f ? [ev(f)] : [], source: (m?.kaynak ?? f?.kaynak ?? null) as Row['source'] });
  }
  if (s.notesLine && r.haklar.munhasirlik) {
    rows.push({ key: 'notesLine', label: 'Münhasırlık (nota)', text: r.haklar.munhasirlik.ad ?? r.haklar.munhasirlik.deger, evidence: [ev(r.haklar.munhasirlik)], source: r.haklar.munhasirlik.kaynak });
  }
  return rows;
}

/** Belgede aynı alana farklı değer çıkan alanlar: öneri yok, adaylar alıntılarıyla gösterilir. */
export function conflicts(r: ExtractResult, labels: Record<string, string>): Array<{ key: string; label: string; items: Candidate[] }> {
  return Object.entries(r.alanlar)
    .filter(([, c]) => c.celiski && c.celiski.length > 1)
    .map(([key, c]) => ({ key, label: labels[key] ?? key, items: c.celiski as Candidate[] }));
}

/** Seçilen alanları şartlara uygular; diğer alanlara dokunmaz. Hak ve oran var olanın üstüne eklenir; münhasırlık
 *  notlara bir satır olarak eklenir (aynı satır iki kez eklenmez). */
export function applySuggestion(terms: Terms, s: Suggestion, keys: string[]): Terms {
  const t: Terms = { ...terms, rates: { ...terms.rates }, rights: { ...terms.rights } };
  for (const key of keys) {
    const [group, sub] = key.split('.');
    const rate = sub ? s.rates?.[sub] : undefined;
    if (group === 'rates' && sub && rate != null) t.rates[sub] = rate;
    else if (group === 'rights' && sub && s.rights?.[sub]) t.rights[sub] = true;
    else if (key === 'notesLine' && s.notesLine) {
      if (!t.notes.includes(s.notesLine)) t.notes = t.notes.trim() ? `${t.notes.trim()}\n${s.notesLine}` : s.notesLine;
    } else if (key === 'end' && s.end) {
      t.end = s.end;
      t.openEnded = false;
    } else if (key === 'paymentType' && s.paymentType) t.paymentType = s.paymentType;
    else if (key === 'basis' && s.basis) t.basis = s.basis;
    else if (key === 'currency' && s.currency) t.currency = s.currency;
    else if (key === 'advance' && s.advance != null) t.advance = s.advance;
    else if (key === 'flatFee' && s.flatFee != null) t.flatFee = s.flatFee;
    else if (key === 'withholdingPct' && s.withholdingPct != null) t.withholdingPct = s.withholdingPct;
    else if (key === 'start' && s.start) t.start = s.start;
    else if (key === 'years' && s.years != null) t.years = s.years;
    else if (key === 'language' && s.language) t.language = s.language;
    else if (key === 'territory' && s.territory) t.territory = s.territory;
  }
  return t;
}

/** Formda şu an önerilen değeri taşıyan alanlar (kabul kaydı bunlarla yazılır; insan sonradan değiştirdiyse düşer). */
export function stillApplied(terms: Terms, s: Suggestion, keys: string[]): string[] {
  return keys.filter((key) => {
    const [group, sub] = key.split('.');
    if (group === 'rates') return sub != null && terms.rates[sub] === s.rates?.[sub];
    if (group === 'rights') return sub != null && terms.rights[sub] === true;
    if (key === 'notesLine') return !!s.notesLine && terms.notes.includes(s.notesLine);
    return (terms as unknown as Record<string, unknown>)[key] === (s as Record<string, unknown>)[key];
  });
}
