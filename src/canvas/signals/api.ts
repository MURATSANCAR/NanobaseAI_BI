import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';
import type { Kaynaklar } from '../components/sqlInfo';

/** AI fırsatları öneri 15, 16, 19'un köprü uçları: okur sesi (/api/v1/okur-sesi), serbest not sinyali
 *  (/api/v1/not-sinyali), Kampüs «Bugün» (/api/v1/bugun). Metin gelmez; yalnız etiket, sayı ve denetimli özet. */

async function fail(res: Response): Promise<never> {
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}
const enc = encodeURIComponent;

// ------------------------------------------------------------------ okur sesi (öneri 15)

export type VoiceSource = 'site-yorum' | 'trendyol-soru' | 'trendyol-yorum' | 'trendyol-iade';
export type VoiceTopic = 'kargo' | 'baski' | 'icerik' | 'fiyat' | 'ovgu' | 'diger';
export type VoiceLabel = { konu: VoiceTopic | null; konuAdi: string; olasilik: number | null; yontem: 'kural' | 'iade-nedeni' | 'zeki' | 'emin-degil' };
export type VoiceAlert = {
  anahtar: string; ad: string | null; sayi: number; kaynaklar: Record<string, number>; ilk: string | null; guncelleme: string | null;
  durum: 'acik' | 'goruldu' | 'kapandi'; bildirim: string | null; goren: string | null; gorulme: string | null;
};
export type VoiceSummary = {
  bas: string; bit: string; gun: number;
  kaynakKonu: Partial<Record<VoiceSource, Record<VoiceTopic | 'belirsiz', number>>>;
  toplam: Record<VoiceTopic | 'belirsiz', number>;
  konular: Record<VoiceTopic, string>;
  kaynakAdlari: Record<VoiceSource, string>;
  uyarilar: VoiceAlert[];
  uretim: boolean;
  ayarlar: { minProb: number; minMargin: number; defectDays: number; defectMin: number; windowDays: number; iceAlici: number };
  sonKosu: { _at?: string } | null;
  kaynaklar?: Kaynaklar;
};

export const voiceApi = {
  labels: (kaynak: VoiceSource) => send<{ items: Record<string, VoiceLabel>; konular: Record<VoiceTopic, string>; kaynaklar?: Kaynaklar }>('GET', `/api/v1/okur-sesi/labels?kaynak=${enc(kaynak)}`),
  summary: () => send<VoiceSummary>('GET', '/api/v1/okur-sesi/summary'),
  seen: (key: string) => send<VoiceAlert>('POST', `/api/v1/okur-sesi/alerts/${enc(key)}/seen`, {}),
};

// ------------------------------------------------------------------ serbest not sinyali (öneri 16)

export type NoteScreen = 'saha' | 'bayi' | 'musteri';
export type NoteLabel = 'tahsilat' | 'sikayet' | 'siparis' | 'iade' | 'kapanis' | 'yok';
export type NoteSignal = {
  cari: string; gun: number; sayilar: Record<NoteLabel, number>; belirsiz: number; etiketler: Record<NoteLabel, string>;
  sonNotlar: Array<{ kaynak: string; kaynakAdi: string | null; tarih: string | null; etiket: NoteLabel | null; etiketAdi: string; yontem: string | null; olasilik: number | null }>;
  ozet: { metin: string | null; kaynak: 'zeki' | 'kural'; dusen: number; zaman: string | null; guncel: boolean } | null;
  kuralOzeti: string;
  not: string;
  kaynaklar?: Kaynaklar;
};

export const noteApi = {
  view: (code: string, ekran: NoteScreen) => send<NoteSignal>('GET', `/api/v1/not-sinyali/cari/${enc(code)}?ekran=${ekran}`),
  summarize: (code: string, ekran: NoteScreen) => send<NoteSignal>('POST', `/api/v1/not-sinyali/cari/${enc(code)}/ozet?ekran=${ekran}`, {}, 300_000),
};

// ------------------------------------------------------------------ Kampüs «Bugün» (öneri 19)

export type TodayItem = { kaynak: string; baslik: string; sayi: number; link: string; oncelik: 1 | 2 | 3; oncelikAdi: string; detay: string | null };
export type Today = {
  gun: string; items: TodayItem[]; okunamayan: string[]; kuralOzeti: string; modelVar: boolean;
  ozet: { metin: string; dusen: number; zaman: string; guncel: boolean } | null;
};

export const todayApi = {
  get: () => send<Today>('GET', '/api/v1/bugun'),
  summarize: () => send<Today>('POST', '/api/v1/bugun/ozet', {}, 180_000),
};
