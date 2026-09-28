import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** M35 E-ticaret kampanya yönetimi: köprü uçları /api/v1/kampanya/*. Kampanya hiçbir platforma, T-soft'a ya da CRM'e
 *  gönderilmez; onaydan sonra ekip elle kurar ve «Elle kurdum» diye işaretler. */

export type Kanal = 'site' | 'pazar_yeri' | 'bayi' | 'fuar';
export type Durum = 'taslak' | 'onay_bekliyor' | 'onaylandi' | 'yurutuluyor' | 'bitti' | 'iptal';
export type Seviye = 'kirmizi' | 'sari' | 'bilgi';
export type Kontrol = { kod: string; seviye: Seviye; mesaj: string };

export type Item = {
  stok: string;
  sira: number;
  ean: string | null;
  ad: string | null;
  yazar: string | null;
  liste: number | null;
  listeElle: boolean;
  kampanyaFiyati: number | null;
  indirim: number | null;
  kdv: number | null;
  stokAdet: number | null;
  gunlukHiz: number | null;
  tukenme: string | null;
  birimMaliyet: number | null;
  maliyetKaynak: string | null;
  netOnce: number | null;
  netSonra: number | null;
  telifOnce: number | null;
  telifSonra: number | null;
  telifEtkisi: number | null;
  marjOnce: number | null;
  marjSonra: number | null;
  marjOraniOnce: number | null;
  marjOraniSonra: number | null;
  maliyetEksik: boolean;
  kontroller: Kontrol[];
  kirmizi: number;
  sari: number;
  hesap: { listeKaynak?: string; kanalKesinti?: number; kanalKesintiGirildi?: boolean; artis?: number; artisKaynak?: string; telifEsaslari?: string[] };
  adayGerekcesi: string | null;
  hesaplandi: string | null;
};

export type Ozet = {
  kitap: number;
  ortalamaIndirim: number | null;
  marjOraniOnce: number | null;
  marjOraniSonra: number | null;
  marjBilinen: number;
  maliyetEksik: number;
  kirmizi: number;
  sari: number;
  kirmiziKitap: number;
  stokRiski: number;
};

export type Metin = { baslik?: string[]; aciklama?: string[]; banner?: string[]; secili?: Partial<Record<'baslik' | 'aciklama' | 'banner', string | null>>; at?: string };

export type Campaign = {
  /** Sorgu bilgisi (`<SqlInfo k={{…kaynaklar}} …/>`). */
  kaynaklar?: Kaynaklar;
  id: string;
  ad: string;
  kanal: Kanal;
  kanalAdi: string;
  platform: string | null;
  baslangic: string;
  bitis: string;
  durum: Durum;
  durumAdi: string;
  varsayilanIndirim: number | null;
  kanalKesinti: number | null;
  beklenenArtis: number | null;
  butce: number | null;
  hazirlayan: string | null;
  gonderen: string | null;
  onaylayan: string | null;
  onayNotu: string | null;
  crmKampanyaId: string | null;
  kurulumNotu: string | null;
  kurulduBy: string | null;
  kurulduAt: string | null;
  metin: Metin;
  notlar: string | null;
  sonucOzet: string | null;
  sonucAt: string | null;
  uyarilar: { stok: string; ad: string | null; tukenme: string }[];
  createdAt: string | null;
  updatedAt: string | null;
  submittedAt: string | null;
  decidedAt: string | null;
  crmIslenecek: boolean;
  kitaplar?: Item[];
  ozet: Ozet;
  yetki: { duzenle: boolean; karar: boolean; kendisi: boolean };
  bulunamayan?: string[];
  bildirim?: string;
};

export type Page<T> = { items: T[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar };

export type CalItem = {
  id: string;
  tur: 'platform' | 'ozel_gun' | 'fuar';
  ad: string;
  baslangic: string;
  bitis: string;
  kaynak: string;
  platform?: string | null;
  notlar?: string | null;
  kesinlik?: string;
  neden?: string;
  kitapSayisi?: number;
  silinir: boolean;
};
export type Calendar = {
  /** Sorgu bilgisi (`<SqlInfo k={{…kaynaklar}} …/>`). */
  kaynaklar?: Kaynaklar;
  from: string;
  to: string;
  items: CalItem[];
  kampanyalar: { id: string; ad: string; kanal: Kanal; platform: string | null; baslangic: string; bitis: string; durum: Durum; durumAdi: string }[];
  cakismalar: { tur: 'kampanya' | 'denk'; a: string; b: string; mesaj: string }[];
};

export type RefreshStatus = {
  running: boolean;
  step: string | null;
  error: string | null;
  dataEnd: string | null;
  last: { ok?: boolean; error?: string; sn?: number; warnings?: string[]; _at?: string } | null;
  fiyatKaydi: { urun?: number; gun?: number; ilkGun?: string; sonGun?: string } | null;
};

export type Overview = {
  /** Sorgu bilgisi (`<SqlInfo k={{…kaynaklar}} …/>`). */
  kaynaklar?: Kaynaklar;
  sayilar: Record<Durum, number>;
  kitapSayisi: number;
  status: RefreshStatus;
  takvim: Calendar;
  onayBekleyen: Campaign[];
  yurutulen: Campaign[];
  kanallar: Record<Kanal, string>;
  durumlar: Record<Durum, string>;
  kurallar: Record<string, string>;
  varsayilanKurallar: string[];
  takvimTurleri: Record<string, string>;
  metinTurleri: Record<'baslik' | 'aciklama' | 'banner', { ad: string; sinir: number }>;
  ayarlar: { listPriceSource: string; costSource: string; marginMinPct: number | null; hizAy: number; stokAy: number; dususPct: number;
    adayMarjMinPct: number | null; sezonOncesiGun: number; sonraGun: number; fiyatGun: number; takvimGun: number };
  kanalCari: Record<string, number>;
  maliyetSaglayici: boolean;
  platformBagli: boolean;
  window: { hizAy?: number; son?: [string, string]; gun?: number };
  me: { username: string; display: string; admin: boolean; canEdit: boolean; canApprove: boolean; canCopy: boolean; canExport: boolean };
};

export type Candidate = {
  stok: string;
  ad: string | null;
  yazar: string | null;
  ean: string | null;
  stokAdet: number;
  stokAy: number | null;
  dusus: number | null;
  adetSon: number | null;
  adetOnceki: number | null;
  sezonlar: string[];
  liste: number | null;
  marjOrani: number | null;
  hak: string | null;
  puan: number;
  gerekce: string;
};
export type Candidates = Page<Candidate> & {
  kurallar: string[];
  esikler: { stokAy: number; dususPct: number; hizAy: number; sezonOncesiGun: number; marjMinPct: number | null; indirim: number };
  sezonlar: string[];
  dataEnd: string | null;
};

export type BookHit = { stok: string; ad: string | null; yazar: string | null; ean: string | null; stokAdet: number; liste: number | null; adet12: number };

export type Donem = {
  bas: string;
  bit: string;
  gun: number;
  gunToplam: number;
  adet: number | null;
  iade: number | null;
  tutar: number | null;
  gunlukAdet: number | null;
  iadeOrani: number | null;
  marj: number | null;
  marjOrani: number | null;
  maliyetKapsami: number | null;
};
export type Learning = {
  id: string;
  kampanyaId: string;
  kampanya: string | null;
  kanal: Kanal | null;
  ozet: string;
  tur: string | null;
  indirim: number | null;
  satisDegisimi: number | null;
  iadeDegisimi: number | null;
  marjDegisimi: number | null;
  yazan: string | null;
  tarih: string | null;
};
export type Results = {
  /** Sorgu bilgisi (`<SqlInfo k={{…kaynaklar}} …/>`). */
  kaynaklar?: Kaynaklar;
  id: string;
  durum: Durum;
  logoKesim: string | null;
  kaynak: string | null;
  donemler: Partial<Record<'once' | 'kampanya' | 'sonra', Donem>>;
  degisim: { satis: number | null; iadePuan: number | null; marjPuan: number | null };
  kitaplar: { stok: string; ad: string | null; indirim: number | null; onceAdet: number; kampanyaAdet: number; sonraAdet: number; kampanyaIade: number; kampanyaTutar: number; degisim: number | null }[];
  seri: { gun: string; adet: number; tutar: number; donem: 'once' | 'kampanya' | 'sonra' }[];
  notlar: string[];
  ozet: string | null;
  ozetAt: string | null;
  ogrenimler: Learning[];
  crmEtki?: { satir: number; siparis: number; adet: number; indirim: number; tutar: number } | null;
  crmEtkiHata?: string;
};

export type CrmCampaign = {
  id: string;
  ad: string | null;
  baslangic: string | null;
  bitis: string | null;
  mecra: string | null;
  tip: string | null;
  ekIskonto: number | null;
  netIskonto: number | null;
  asgariTutar: number | null;
  asgariAdet: number | null;
  hediyeAdet: number | null;
  vadeli: boolean;
  herkes: boolean;
  aciklama: string | null;
  etkin: boolean;
  etki: { satir: number; siparis: number; adet: number; indirim: number; tutar: number } | null;
  tur: { tur: string; turAdi: string; yontem: string; olasilik: number | null } | null;
};

const B = '/api/v1/kampanya';

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401) throw new EngineAuthError();
  const detail = async () => {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    return typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  };
  if (res.status === 403) throw new EngineForbiddenError((await detail()) || 'Bu işleme yetkiniz yok.');
  if (!res.ok) throw new Error((await detail()) || httpErrorText(res.status));
  return (await res.json()) as T;
}

export const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;
/** Stok kodunda «/» olabilir: yol parçası parça parça kodlanır. */
const encPath = (s: string) => s.split('/').map(enc).join('/');

export type NewCampaign = { ad: string; kanal: Kanal; platform?: string; baslangic: string; bitis: string; varsayilanIndirim?: number | null; kanalKesinti?: number | null };

export const kampanyaApi = {
  overview: () => send<Overview>('GET', '/overview'),
  status: () => send<RefreshStatus>('GET', '/status'),
  refresh: () => send<RefreshStatus & { started: boolean }>('POST', '/refresh', {}),
  calendar: (from: string, to: string) => send<Calendar>('GET', `/calendar${qs({ from, to })}`),
  addCalendar: (b: { tur: string; ad: string; baslangic: string; bitis: string; platform?: string; notlar?: string }) => send<CalItem>('POST', '/calendar', b),
  removeCalendar: (id: string) => send<{ ok: boolean }>('DELETE', `/calendar/${enc(id)}`),
  list: (p: { durum?: string; kanal?: string; q?: string; page?: number }) => send<Page<Campaign> & { sayilar: Record<Durum, number> }>('GET', `/campaigns${qs(p)}`),
  get: (id: string) => send<Campaign>('GET', `/campaigns/${enc(id)}`),
  create: (b: NewCampaign) => send<Campaign>('POST', '/campaigns', b),
  update: (id: string, b: Record<string, unknown>) => send<Campaign>('PATCH', `/campaigns/${enc(id)}`, b),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/campaigns/${enc(id)}`),
  addItems: (id: string, kitaplar: { stok: string; indirim?: number | null; kampanyaFiyati?: number | null; gerekce?: string }[]) =>
    send<Campaign>('POST', `/campaigns/${enc(id)}/items`, { kitaplar }),
  updateItem: (id: string, stok: string, b: { indirim?: number | null; kampanyaFiyati?: number | null; liste?: number | null }) =>
    send<Campaign>('PATCH', `/campaigns/${enc(id)}/items/${encPath(stok)}`, b),
  removeItem: (id: string, stok: string) => send<Campaign>('DELETE', `/campaigns/${enc(id)}/items/${encPath(stok)}`),
  simulate: (id: string, indirim?: number | null) => send<Campaign>('POST', `/campaigns/${enc(id)}/simulate`, { indirim: indirim ?? null }),
  submit: (id: string) => send<Campaign>('POST', `/campaigns/${enc(id)}/submit`, {}),
  withdraw: (id: string) => send<Campaign>('POST', `/campaigns/${enc(id)}/withdraw`, {}),
  decide: (id: string, karar: 'onay' | 'geri', not?: string) => send<Campaign>('POST', `/campaigns/${enc(id)}/decision`, { karar, not }),
  cancel: (id: string, not: string) => send<Campaign>('POST', `/campaigns/${enc(id)}/cancel`, { not }),
  copy: (id: string, tur: 'baslik' | 'aciklama' | 'banner') =>
    send<{ tur: string; secenekler: string[]; dusenSayisi: number; sinir: number }>('POST', `/campaigns/${enc(id)}/copy`, { tur }, 300_000),
  candidates: (p: { campaign_id?: string; kurallar?: string; q?: string; page?: number }) => send<Candidates>('GET', `/candidates${qs(p)}`),
  books: (q: string) => send<Page<BookHit>>('GET', `/books${qs({ q })}`),
  results: (id: string) => send<Results>('GET', `/campaigns/${enc(id)}/results`),
  refreshResults: (id: string) => send<Results>('POST', `/campaigns/${enc(id)}/results/refresh`, {}, 600_000),
  summary: (id: string) => send<{ ozet: string; dusenSayisi: number }>('POST', `/campaigns/${enc(id)}/summary`, {}, 300_000),
  learnings: (p: { kanal?: string; page?: number }) => send<Page<Learning>>('GET', `/learnings${qs(p)}`),
  addLearning: (id: string, b: { ozet: string; tur?: string }) => send<{ id: string }>('POST', `/campaigns/${enc(id)}/learnings`, b),
  removeLearning: (lid: string) => send<{ ok: boolean }>('DELETE', `/learnings/${enc(lid)}`),
  crmCampaigns: (p: { page?: number; etkin?: boolean }) => send<Page<CrmCampaign>>('GET', `/crm-campaigns${qs(p)}`),
  exportUrl: (id: string, ic = false) => `${ENGINE_BASE}${B}/campaigns/${enc(id)}/export.xlsx${ic ? '?ic=true' : ''}`,
};

/* ------------------------------------------------------------------ saf yardımcılar (vitest) */

export const STATUS_TONE: Record<Durum, 'ok' | 'warn' | 'muted' | 'violet' | 'err'> = {
  taslak: 'muted',
  onay_bekliyor: 'warn',
  onaylandi: 'violet',
  yurutuluyor: 'ok',
  bitti: 'muted',
  iptal: 'err',
};

/** «%30», «30» ya da «0,3» → 0,30; boş null; 0–95 dışı null. 1 ve üstü yüzde sayılır («1» = %1). */
export function pctToRatio(s: string): number | null {
  const t = s.replace(/[%\s]/g, '').replace(',', '.');
  if (!t) return null;
  const n = Number(t);
  if (!Number.isFinite(n) || n < 0 || n > 95) return null;
  return n >= 1 ? n / 100 : n;
}

/** «45,50» ya da «45.50» → 45,5; boş ya da sıfır/eksi null. */
export function parseMoney(s: string): number | null {
  const t = s.replace(/[₺\s]/g, '');
  if (!t) return null;
  const norm = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t;
  const n = Number(norm);
  return Number.isFinite(n) && n > 0 ? n : null;
}

/** Kitabın en ağır kontrol seviyesi (tablo satırının rengi). */
export function worst(k: Kontrol[]): Seviye | null {
  if (k.some((x) => x.seviye === 'kirmizi')) return 'kirmizi';
  if (k.some((x) => x.seviye === 'sari')) return 'sari';
  return k.length ? 'bilgi' : null;
}

/** Takvim şeridinde bir aralığın konumu (yüzde): [sol, genişlik]; pencere dışına taşan kısım kırpılır. */
export function span(from: string, to: string, a: string, b: string): [number, number] | null {
  const d = (x: string) => Date.UTC(+x.slice(0, 4), +x.slice(5, 7) - 1, +x.slice(8, 10));
  const lo = d(from);
  const hi = d(to) + 86_400_000;
  const s = Math.max(lo, d(a));
  const e = Math.min(hi, d(b) + 86_400_000);
  if (e <= s) return null;
  const total = hi - lo;
  return [((s - lo) / total) * 100, ((e - s) / total) * 100];
}

/** Bugünden `days` gün sonrası, YYYY-AA-GG (yerel gün). */
export function isoPlus(days: number, base = new Date()): string {
  const x = new Date(base.getFullYear(), base.getMonth(), base.getDate() + days);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${x.getFullYear()}-${p(x.getMonth() + 1)}-${p(x.getDate())}`;
}
