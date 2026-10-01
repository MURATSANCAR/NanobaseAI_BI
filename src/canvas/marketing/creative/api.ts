import { ENGINE_BASE, send } from '../../engine';
import { httpErrorText } from '../../httpError';
import type { Kaynaklar } from '../../components/sqlInfo';

/** M19 Pazarlama görsel ve metin köprü istemcisi (`/api/v1/marketing/creative/*`). Talep → üretim (görsel: stüdyonun
 *  pazarlama kiti; metin: Zeki AI) → tasarım onayı → mesaj onayı → arşiv. Dış kanala hiçbir şey gönderilmez; onaylı
 *  paket indirilir. Düzenleyen kişi oturumdan gelir. */

export type Channel = 'instagram' | 'facebook' | 'x' | 'linkedin' | 'tiktok' | 'youtube' | 'google-ads' | 'meta-ads' | 'site' | 'e-bulten' | 'diger';
export type TextKind = 'baslik' | 'aciklama' | 'reklam-metni' | 'video-senaryosu' | 'influencer-brief' | 'hashtag';
export type ReqState = 'talep' | 'uretimde' | 'tasarim-onayi' | 'mesaj-onayi' | 'onayli' | 'reddedildi' | 'arsiv';
export type Signed = { by: string; at: string | null };

export type Meta = {
  kanallar: Array<{ key: Channel; label: string; formatlar: string[] }>;
  formatlar: Array<{ key: string; label: string }>;
  metinTurleri: Array<{ key: TextKind; label: string }>;
  durumlar: Array<{ key: ReqState; label: string }>;
  sinirlar: Record<string, Record<string, { sinir: number | null; onerilen: number | null }>>;
  hashtagSiniri: Record<string, number>;
  kapakMinPx: number;
  me: { username: string; display: string | null; admin: boolean; talep: boolean; uret: boolean; tasarimOnay: boolean; mesajOnay: boolean; marka: boolean };
};

export type Counts = { gorsel: number; metin: number; onayli: number; bekleyen: number; reddedilen: number };
export type Cover = { kaynak?: string; url?: string | null; w?: number; h?: number; sha256?: string; gonderildi?: string | null; denenen?: string[]; dosyaAdi?: string | null };

export type CreativeRequest = {
  id: string;
  /** M15 pazarlama planı (`/pazarlama/plan/:id`) ve materyal kaydı. */
  planId: string | null;
  materyalId: string | null;
  materyalTur: string | null;
  kampanya: string | null;
  stokKodu: string;
  kitapId: string | null;
  kitapAdi: string;
  yazar: string | null;
  studioJob: string | null;
  studioKind: 'kitap' | 'pazarlama' | null;
  kapak: Cover | null;
  kanal: Channel;
  kanalAdi: string;
  formatlar: string[];
  metinTurleri: TextKind[];
  brief: string | null;
  hedefKitle: string | null;
  ton: string | null;
  gorselBasligi: string | null;
  termin: string | null;
  durum: ReqState;
  durumAdi: string;
  isteyen: string;
  isteyenAd: string | null;
  atanan: string | null;
  etiketler: string[];
  not: string | null;
  olusturma: string;
  guncelleme: string;
  sayilar: Partial<Counts>;
};

export type Issue = { seviye: 'hata' | 'uyari'; kod: string; mesaj: string };
export type Check = {
  karakter: number;
  kelime: number;
  sinir: number | null;
  onerilen: number | null;
  alintilar: Array<{ metin: string; bulundu: boolean }>;
  yasakli: string[];
  sayilar: string[];
  iddia: { karar: string | null; p: number | null; yontem: string; emin: boolean } | null;
  sorunlar: Issue[];
  durum: 'tamam' | 'uyari' | 'hata';
};

export type VisualSetting = { visual: 'cover' | 'page' | 'quote'; headline?: string; effect?: string; color?: string | null; quote?: string; source?: string };

export type Asset = {
  id: string;
  requestId: string;
  stokKodu: string;
  tur: 'gorsel' | 'metin';
  kanal: Channel | null;
  format: string | null;
  formatAdi: string | null;
  metinTuru: TextKind | null;
  metinTuruAdi: string | null;
  varyant: string;
  metin: string | null;
  kaynak: string;
  dogrulama: Check | null;
  ayar: VisualSetting | null;
  genislik: number | null;
  yukseklik: number | null;
  surum: number;
  oncekiId: string | null;
  guncel: boolean;
  studioRef: string | null;
  tasarimOnay: Signed | null;
  mesajOnay: Signed | null;
  red: (Signed & { not: string | null }) | null;
  etiketler: string[];
  olusturan: string;
  olusturma: string;
  onayli: boolean;
  yayinaHazir: boolean;
  dosyaAdi: string;
  kitapAdi?: string;
  yazar?: string | null;
  kampanya?: string | null;
};

export type Job = {
  id: string;
  tur: 'gorsel' | 'metin';
  durum: 'suruyor' | 'bitti' | 'hata';
  ilerleme: [number, number, string?] | null;
  sonuc: { uretilen?: number; atlanan?: Array<{ varyant?: string; format?: string; neden: string }>; elenen?: Array<{ tur: string; neden: string; metin?: string }>; uyari?: number; kapak?: Cover;
    palet?: string[]; kaynaklar?: Array<{ key: string; label: string; kind: string }>; alintilar?: string[] } | null;
  hata: string | null;
  olusturan: string;
  baslangic: string;
  bitis: string | null;
};

export type RequestDetail = CreativeRequest & { varliklar: Asset[]; isler: Job[]; kaynaklar?: Kaynaklar };
export type Page<T> = { items: T[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar };

export type Book = {
  kitap_id: string | null;
  ad: string;
  stok_kodu: string;
  yazar: string | null;
  isbn: string | null;
  turler: string | null;
  yas_bas: number | null;
  yas_bit: number | null;
  hashtag: string | null;
  ozet: string | null;
  spot: string | null;
  onemli_cumle: string | null;
  sosyal_medya: string | null;
  anahtar_kelimeler: string | null;
  alintilar: string[];
  etkin: boolean;
};
export type BookInfo = {
  kitap: Book;
  studioIsleri: Array<{ id: string; title: string | null; createdAt: number | null; createdBy: string | null }>;
  kapakKaynaklari: { crm: boolean; crmKokAyarli: boolean; eticaret: boolean };
};
export type BookHit = { kitapId: string; ad: string; stokKodu: string; yazar: string | null; isbn: string | null };

export type Summary = {
  yeniTalep: number;
  tasarimBekleyen: number | null;
  mesajBekleyen: number | null;
  bana: number;
  terminiYaklasan: Array<{ id: string; kitapAdi: string; termin: string; isteyen: string; atanan: string | null; durum: ReqState }>;
  kaynaklar?: Kaynaklar;
};

/** Onaylı M15 planında henüz talebe dönüşmemiş görsel/metin materyali. */
export type PendingMaterial = { materyalId: string; planId: string; planAdi: string; tur: string; turAdi: string;
  stokKodu: string | null; termin: string | null; metin: string; kanal: Channel };

export type BrandFile = { id: string; ad: string; dosya: string; tur: 'logo' | 'font'; boyut: number; lisans?: string | null; yukleyen: string; zaman: string };
export type Brand = { surum: number; palet: string[]; logolar: BrandFile[]; yaziTipleri: BrandFile[]; kurallar: string; yukleyen: string | null; zaman: string | null };
export type Banned = { id: string; kalip: string; aciklama: string | null; ekleyen: string; zaman: string };

export type NewRequest = {
  stokKodu: string;
  kanal: Channel;
  formatlar: string[];
  metinTurleri: TextKind[];
  brief?: string;
  hedefKitle?: string;
  ton?: string;
  gorselBasligi?: string;
  termin?: string;
  kampanya?: string;
  etiketler?: string[];
  atanan?: string;
  studioJob?: string;
};

const P = '/api/v1/marketing/creative';
const qs = (o: Record<string, string | number | undefined | null | boolean>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
};
const id = encodeURIComponent;

/** Ham gövdeli yükleme (kapak, marka dosyası). */
async function put<T>(path: string, file: File): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, { method: 'PUT', credentials: 'include', body: file, signal: AbortSignal.timeout(180_000) });
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

export type ArchiveFilter = { stok?: string; etiket?: string; kanal?: string; format?: string; tur?: string; durum?: string; q?: string; baslangic?: string; bitis?: string; page?: number };

export const creativeApi = {
  meta: () => send<Meta>('GET', `${P}/meta`, undefined, 30_000),
  summary: () => send<Summary>('GET', `${P}/summary`, undefined, 30_000),
  books: (q: string, page = 0) => send<Page<BookHit>>('GET', `${P}/books${qs({ q, page })}`, undefined, 60_000),
  book: (stok: string) => send<BookInfo>('GET', `${P}/books/${id(stok)}`, undefined, 60_000),
  requests: (f: { durum?: string; kanal?: string; stok?: string; atanan?: string; q?: string; page?: number }) =>
    send<Page<CreativeRequest>>('GET', `${P}/requests${qs(f)}`, undefined, 60_000),
  create: (b: NewRequest) => send<CreativeRequest>('POST', `${P}/requests`, b, 60_000),
  pending: () => send<{ items: PendingMaterial[]; kaynaklar?: Kaynaklar }>('GET', `${P}/materials/pending`, undefined, 60_000),
  fromMaterial: (mid: string) => send<CreativeRequest>('POST', `${P}/from-material/${id(mid)}`, {}, 60_000),
  request: (rid: string, history = false) => send<RequestDetail>('GET', `${P}/requests/${id(rid)}${qs({ gecmis: history })}`, undefined, 60_000),
  update: (rid: string, b: Partial<NewRequest> & { durum?: string; not?: string }) => send<CreativeRequest>('PATCH', `${P}/requests/${id(rid)}`, b, 30_000),
  uploadCover: (rid: string, f: File) => put<CreativeRequest>(`${P}/requests/${id(rid)}/cover${qs({ filename: f.name })}`, f),
  coverUrl: (rid: string, w = 320) => `${ENGINE_BASE}${P}/requests/${id(rid)}/cover?w=${w}`,
  produce: (rid: string, b: { formatlar?: string[]; varyantlar?: VisualSetting[] } = {}) => send<{ job: string }>('POST', `${P}/requests/${id(rid)}/produce`, b, 30_000),
  copy: (rid: string, b: { turler?: TextKind[]; platform?: string; adet?: number; sure?: number } = {}) => send<{ job: string }>('POST', `${P}/requests/${id(rid)}/copy`, b, 30_000),
  headlines: (rid: string) => send<{ items: Array<{ metin: string; dogrulama: Check }> }>('POST', `${P}/requests/${id(rid)}/headlines`, {}, 180_000),
  zipUrl: (rid: string) => `${ENGINE_BASE}${P}/requests/${id(rid)}/zip`,
  archive: (f: ArchiveFilter) => send<Page<Asset>>('GET', `${P}/assets${qs(f)}`, undefined, 60_000),
  versions: (aid: string) => send<{ items: Asset[] }>('GET', `${P}/assets/${id(aid)}/versions`, undefined, 30_000),
  reviseText: (aid: string, metin: string) => send<Asset>('PUT', `${P}/assets/${id(aid)}`, { metin }, 30_000),
  reviseVisual: (aid: string, b: Partial<VisualSetting> & { tumFormatlar?: boolean }) => send<{ job: string; hedef: number }>('PUT', `${P}/assets/${id(aid)}`, b, 30_000),
  approve: (aid: string, seviye: 'tasarim' | 'mesaj') => send<Asset>('POST', `${P}/assets/${id(aid)}/approve`, { seviye }, 30_000),
  withdraw: (aid: string, seviye: 'tasarim' | 'mesaj') => send<Asset>('POST', `${P}/assets/${id(aid)}/withdraw`, { seviye }, 30_000),
  reject: (aid: string, not: string) => send<Asset>('POST', `${P}/assets/${id(aid)}/reject`, { not }, 30_000),
  fileUrl: (aid: string, w = 0) => `${ENGINE_BASE}${P}/assets/${id(aid)}/file${w ? `?w=${w}` : ''}`,
  downloadUrl: (aid: string) => `${ENGINE_BASE}${P}/assets/${id(aid)}/file?download=1`,
  check: (b: { metin: string; platform?: string; tur?: string; stokKodu?: string }) => send<Check>('POST', `${P}/check`, b, 120_000),
  brand: () => send<Brand>('GET', `${P}/brand`, undefined, 30_000),
  saveBrand: (b: Partial<Pick<Brand, 'palet' | 'logolar' | 'yaziTipleri' | 'kurallar'>>) => send<Brand>('PUT', `${P}/brand`, b, 30_000),
  uploadBrandFile: (tur: 'logo' | 'font', f: File, lisans = '') => put<Brand>(`${P}/brand/files${qs({ tur, filename: f.name, lisans })}`, f),
  brandFileUrl: (fid: string) => `${ENGINE_BASE}${P}/brand/files/${id(fid)}`,
  banned: () => send<{ items: Banned[] }>('GET', `${P}/banned-phrases`, undefined, 30_000),
  saveBanned: (items: Array<{ kalip: string; aciklama?: string | null }>) => send<{ items: Banned[] }>('PUT', `${P}/banned-phrases`, { items }, 30_000),
};

export const STATE_TONE: Record<ReqState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  talep: 'muted',
  uretimde: 'violet',
  'tasarim-onayi': 'warn',
  'mesaj-onayi': 'warn',
  onayli: 'ok',
  reddedildi: 'err',
  arsiv: 'muted',
};

/** Pano sütunları (reddedilen ve arşivdekiler süzgeçle görünür). */
export const BOARD: ReqState[] = ['talep', 'uretimde', 'tasarim-onayi', 'mesaj-onayi', 'onayli'];

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: 'short', timeZone: 'Europe/Istanbul' });
export const fmtDay = (iso: string | null | undefined) => (iso ? dayFmt.format(new Date(iso.length === 10 ? `${iso}T12:00:00+03:00` : iso)) : '—');

/** Termine kalan gün (bugün 0, geçmiş eksi); termin yoksa null. */
export function daysLeft(iso: string | null | undefined, now = new Date()): number | null {
  if (!iso) return null;
  const t = new Date(`${iso.slice(0, 10)}T00:00:00+03:00`).getTime();
  const today = new Date(new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul' }).format(now) + 'T00:00:00+03:00').getTime();
  return Math.round((t - today) / 86_400_000);
}
