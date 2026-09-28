import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../../engine';
import { httpErrorText } from '../../httpError';
import type { Task } from '../api';

/** M16 Lansman uçları: /api/v1/marketing/launches*. */

export type LaunchStatus = 'hazirlik' | 'yayinda' | 'izleme' | 'kapandi';
export type Tone = 'kirmizi' | 'sari' | 'yesil';

export type Depot = {
  deger: number | null;
  kaynak: 'crm' | 'logo' | null;
  kaynakAdi: string | null;
  tarih: string | null;
  /** Logo depo görünümünün son okuması (lansman penceresi bittiyse de her gün okunur). */
  logo?: number | null;
  logoGun?: string | null;
};
export type Signal = {
  gun: number;
  siparis: number | null;
  fatura: number | null;
  hedef: number | null;
  oranFatura: number | null;
  oranSiparis: number | null;
  oranEsas: 'fatura' | 'siparis';
  oran: number | null;
  bekleyen: number | null;
  /** CRM «Bekleyen Ürün» son okuması (eski özetlerde yok). */
  bekleyenUrun?: number | null;
  depo: Depot;
  dagilim: { adet: number; bayi: number; siparis: number } | null;
  stokCatismasi: boolean;
  dagilimYok: boolean;
  hedefAltinda: boolean;
  gecikenMadde: number;
  veriSonuLogo: string | null;
};

export type LaunchHead = {
  id: string;
  planId: string;
  stokKodu: string;
  crmKitapId: string | null;
  baslik: string;
  yayinGunu: string;
  yayinGunuKaynagi: string;
  yayinGunuKaynakAdi: string;
  durum: LaunchStatus;
  durumAdi: string;
  gun: number | null;
  sahip: string | null;
  okuma: string | null;
  renk: Tone | null;
  sinyal: Signal | null;
  uyarilar: string[];
  kapak: string | null;
  gecikenMadde?: number;
  /** Kural eşikli risk bayrağı (liste ucu); cümle kuraldan ya da gece Zeki AI'dan (denetimli). */
  risk?: LaunchRisk;
};

export type RiskLevel = 'yuksek' | 'orta' | 'yok';
export type LaunchRisk = {
  duzey: RiskLevel;
  duzeyAdi: string;
  nedenler: Array<{ kod: string; ad: string; metin: string }>;
  notlar: string[];
  cumle: string | null;
  cumleKaynak: 'zeki' | 'kural';
  kuralCumlesi: string | null;
};

export type LaunchTask = Task & { launchId?: string | null };

export type ReviewRow = { anahtar: string; ad: string; deger: number | null; birim: string; kaynak: string; para?: boolean };
export type Review = {
  id: string;
  gun: 7 | 30;
  rakam: { gun: number; pencere: { bas: string; bit: string }; satirlar: ReviewRow[]; veriSonuLogo: string | null; eksikGun: number; yapilmayan: Array<{ is: string; tarih: string; durum: string }>; sql: Record<string, string | string[]> };
  ozet: string | null;
  oneriler: string[];
  dogrulama: { dusenSayisi?: number } | null;
  durum: 'rakam' | 'hazir' | 'karar';
  karar: string | null;
  kararAdi: string | null;
  gerekce: string | null;
  kararVeren: string | null;
  kararZamani: string | null;
  hazirlayan: string;
  hazirlama: string | null;
};

export type Launch = LaunchHead & {
  tasks: LaunchTask[];
  materials: Array<{ id: string; tur: string; turAdi: string; metin: string; surum: number }>;
  plan: { id: string; durum: string | null; durumAdi: string | null; baslik: string | null };
  reviews: Review[];
  ozet: { adaylar?: Record<string, string>; hatalar?: string[]; veriSonuLogo?: string };
};

export type LaunchMeta = {
  statuses: Record<LaunchStatus, string>;
  dateSources: Record<string, string>;
  decisions: Record<string, string>;
  tones: Record<string, string>;
  channels: Record<string, string>;
  taskStatuses: Record<string, string>;
  settings: { openDays: number; preDays: number; alertRatio: number; dailyHour: number };
  lastRun: { tarih?: string; hataSayisi?: number } | null;
  webWatch: boolean;
  modelReady: boolean;
  me: { username: string; canWrite: boolean; canSeeBudget: boolean; canDecide: boolean; canExport: boolean };
};

export type TodayTask = LaunchTask & { lansman: string; lansmanBaslik: string; yayinGunu: string; stokKodu: string; sorumluEtkin: string | null; gecikti: boolean };

export type TrackRow = {
  gun: string;
  d: number;
  gelecek: boolean;
  siparis: number | null;
  dagilim: number | null;
  fatura: number | null;
  ciro: number | null;
  hedef: number | null;
  bekleyen: number | null;
  bekleyenUrun: number | null;
  depo: number | null;
  siparisKum: number | null;
  faturaKum: number | null;
  hedefKum: number | null;
  emsalKum: number | null;
};

export type Tracking = {
  gun: number;
  seri: TrackRow[];
  sinyal: Signal | null;
  uyarilar: string[];
  toplam: { siparis: number; fatura: number; hedef: number; ciro: number | null; emsal7: number | null; emsal30: number | null };
  dagilim: { adet: number; bayi: number; siparis: number; bas: string; bit: string } | null;
  depo: Depot | null;
  emsal: { items: Array<{ stokKodu: string; ad: string | null; ilkGun: string | null; ilk7: number | null; ilk30: number | null }>; ort7: number | null; ort30: number | null; not: string | null };
  veriSonu: { logo: string | null; crm: string | null };
  sql: Record<string, string | string[]>;
  okumaHatalari: string[];
};

export type LaunchEvent = {
  id: string | null;
  crmId: string | null;
  kaynak: 'crm' | 'elle';
  ad: string | null;
  tur: string | null;
  tarih: string | null;
  yer: string | null;
  katilimci: number | null;
  satilan: number | null;
  gelir: number | null;
  gider: number | null;
  durumAdi: string | null;
  portal: null | { id: string };
  not?: string | null;
};

export type MediaItem = { id: string | null; kaynak: 'elle' | 'web'; kaynakAdi: string | null; mecra: string | null; baslik: string; url: string | null; tarih: string | null; ton: string | null; tonAdi: string | null };
export type Job = { id: string; tur: string; durum: 'bekliyor' | 'calisiyor' | 'bitti' | 'hata'; adim: string | null; hata: string | null; sonuc: Record<string, unknown> | null };

const B = '/api/v1/marketing/launches';

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

const enc = encodeURIComponent;
const qs = (o: Record<string, string | number | undefined>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => v !== undefined && v !== '' && p.set(k, String(v)));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const launchApi = {
  meta: () => send<LaunchMeta>('GET', '/meta'),
  list: (p: { frm?: string; to?: string; durum?: string; kim?: string }) => send<{ items: LaunchHead[]; total: number }>('GET', qs(p)),
  today: (kim: string) => send<{ items: TodayTask[]; tarih: string }>('GET', `/today${qs({ kim })}`),
  candidates: () => send<{ items: Array<{ id: string; baslik: string; stokKodu: string; yayinTarihi: string; sahip: string | null }> }>('GET', '/candidates'),
  create: (planId: string) => send<Launch>('POST', '', { planId }, 180_000),
  get: (id: string) => send<Launch>('GET', `/${enc(id)}`),
  update: (id: string, b: { sahip?: string; yayinGunu?: string; yayinGunuKaynagi?: string; durum?: 'kapandi' | 'acik' }) => send<Launch>('PATCH', `/${enc(id)}`, b),
  task: (id: string, tid: string, b: { durum?: string; kanitUrl?: string | null; sorumlu?: string | null }) => send<{ task: LaunchTask }>('PUT', `/${enc(id)}/tasks/${enc(tid)}`, b),
  addTask: (id: string, b: { is: string; tarih: string; sorumlu?: string; kanal?: string }) => send<{ task: LaunchTask }>('POST', `/${enc(id)}/tasks`, b),
  refresh: (id: string) => send<{ lansman: Launch }>('POST', `/${enc(id)}/refresh`, {}, 600_000),
  tracking: (id: string, gun: number) => send<Tracking>('GET', `/${enc(id)}/tracking${qs({ gun })}`),
  events: (id: string) => send<{ items: LaunchEvent[]; toplam: Record<string, number | null>; uyarilar: string[] }>('GET', `/${enc(id)}/events`, undefined, 180_000),
  saveEvent: (id: string, b: Record<string, unknown>, eid?: string) =>
    eid ? send<{ event: LaunchEvent }>('PUT', `/${enc(id)}/events/${enc(eid)}`, b) : send<{ event: LaunchEvent }>('POST', `/${enc(id)}/events`, b),
  deleteEvent: (id: string, eid: string) => send<{ ok: boolean }>('DELETE', `/${enc(id)}/events/${enc(eid)}`),
  media: (id: string) => send<{ items: MediaItem[]; ton: Record<string, number>; webAcik: boolean }>('GET', `/${enc(id)}/media`),
  addMedia: (id: string, b: Record<string, unknown>) => send<{ media: MediaItem }>('POST', `/${enc(id)}/media`, b),
  deleteMedia: (id: string, mid: string) => send<{ ok: boolean }>('DELETE', `/${enc(id)}/media/${enc(mid)}`),
  crmTodo: (id: string) => send<{ items: Array<{ nereye: string; ne: string | null; tarih: string | null; alanlar: Record<string, string | number | null> }>; uyarilar: string[] }>('GET', `/${enc(id)}/crm-todo`, undefined, 180_000),
  reviews: (id: string) => send<{ items: Review[]; jobs: Job[] }>('GET', `/${enc(id)}/reviews`),
  draft: (id: string, gun: number) => send<{ review: Review; job: Job }>('POST', `/${enc(id)}/reviews/${gun}/draft`, {}, 180_000),
  decide: (id: string, gun: number, karar: string, gerekce: string) => send<{ review: Review }>('POST', `/${enc(id)}/reviews/${gun}/decide`, { karar, gerekce }),
  pdfUrl: (id: string) => `${ENGINE_BASE}${B}/${enc(id)}/export.pdf`,
};

export const TONE_CLASS: Record<Tone, string> = {
  kirmizi: 'bg-red-50 text-red-700 ring-red-200',
  sari: 'bg-amber-50 text-amber-800 ring-amber-200',
  yesil: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
};
export const TONE_LABEL: Record<Tone, string> = { kirmizi: 'Müdahale gerekli', sari: 'Dikkat', yesil: 'Yolunda' };

/** D−7 … D+30 etiketi. */
export const dLabel = (g: number | null | undefined) => (g === null || g === undefined ? '—' : g === 0 ? 'Yayın günü' : g < 0 ? `D${g}` : `D+${g}`);
