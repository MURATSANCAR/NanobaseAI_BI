import { ENGINE_BASE, send } from '../engine';

/** M38 Müşteri ilişkileri köprü istemcisi (`/api/v1/musteri/*`). Cari = Logo müşteri carisi (cari kodu); değer ve kayıp
 *  riski Logo'nun faturalı satırından (iki yıl kopyası, kodla birleşir), atama M30'la aynı (CRM sahibi / BMT il), veri
 *  sağlığı CRM'den okunur. Portal CRM'e ve Logo'ya yazmaz; düzeltme CRM'de elle yapılır. */

export type Level = 'kayip' | 'yuksek' | 'orta' | 'dusuk' | 'yok';
export type Reason = { key: string; points: number; label: string };

export type Account = {
  code: string;
  ad: string | null;
  kanal: string | null;
  logoKanal: string | null;
  bolge: string | null;
  temsilci: string | null;
  temsilciAd: string | null;
  bireysel: boolean;
  sonFatura: string | null;
  sonSiparis: string | null;
  sonZiyaret: string | null;
  net12: number | null;
  netOnceki: number | null;
  netYil: number | null;
  degisim: number | null;
  fatura12: number | null;
  aralik: number | null;
  aralikKaynagi: 'kendi' | 'kanal' | 'genel' | 'ayar' | null;
  gunSonAlim: number | null;
  iade12: number | null;
  iadeOnceki: number | null;
  puan: number | null;
  duzey: Level | null;
  duzeyAd: string;
  gecis: string | null;
  nedenler: Reason[];
  ozet: string | null;
  ozetKaynagi: 'kural' | 'zeki' | null;
  segment: string | null;
  dilim: string | null;
  egilim: string | null;
  kesim: string | null;
};

export type Action = {
  id: string;
  code: string;
  cariAd: string | null;
  tur: 'arama' | 'ziyaret' | 'kampanya' | 'diger';
  turAd: string;
  aciklama: string;
  sahip: string;
  termin: string | null;
  durum: 'acik' | 'yapildi' | 'iptal';
  durumAd: string;
  sonucNotu: string | null;
  riskPuani: number | null;
  riskDuzeyi: Level | null;
  onceki30: number | null;
  sonuc30: number | null;
  sonuc90: number | null;
  yazan: string;
  tarih: string;
  olusturma: string | null;
  guncelleyen: string | null;
  guncelleme: string | null;
};

type Rate = { olgun: number; alan: number; oran: number | null };
export type Effect = { toplam: number; gun30: Rate; gun90: Rate; riskli30: Rate; riskli90: Rate };

export type Meta = {
  me: { username: string; display: string; admin: boolean; cari: number; canAll: boolean; canAction: boolean; canMark: boolean; canSecurity: boolean; canExport: boolean; canHealth: boolean };
  weights: Array<{ key: string; max: number; label: string }>;
  levels: Array<{ key: Level; label: string }>;
  actionTypes: Array<{ key: Action['tur']; label: string }>;
  healthTypes: Array<{ key: string; label: string }>;
  healthStates: Array<{ key: string; label: string }>;
  run: { asof: string | null; kesim: string | null; year: number | null; accounts: number | null; assigned: number | null; levels: Record<Level, number> | null; warnings: string[] | null; ms: number | null; _at?: string };
  rules: { riskHigh: number; riskMid: number; lostMinDays: number; lostMultiple: number; minPurchaseDays: number; orderFloorDays: number };
  reps: Array<{ hesap: string; ad: string; cari: number }>;
  kanallar: string[];
  bolgeler: string[];
  zekiQuestions: string[];
};

export type Overview = {
  kpi: { cari: number; aktif: number; net12: number; netYil: number; riskli: number; kayip: number; saglik: number | null };
  kanallar: Array<{ kanal: string; aktif: number; net12: number; netYil: number; riskli: number; kayip: number }>;
  bakilacak: Account[];
  bakilacakToplam: number;
  aksiyon: Effect;
  asof: string | null;
  kesim: string | null;
  kapsam: string;
};

export type Paged<T> = { items: T[]; page: number; size: number; total: number; pages: number };

export type Detail = Account & {
  faturalar: Array<{ tarih: string | null; no: string | null; tutar: number }>;
  kitaplar: Array<{ stok: string; ad: string | null; adet: number; ciro: number }>;
  siparisler: Array<{ no: string | null; tarih: string | null; tutar: number; durum: string; riskte: boolean }>;
  ziyaretler: Array<{ id: string; gerceklesen: string | null; planlanan: string | null; durum: string; notu: string | null; gizliNot: boolean; sahip: string }>;
  aksiyonlar: Action[];
  tahsilat: { bakiye: number | null; vadesi_gecmis: number | null; k_90p: number | null; risk_doluluk: number | null; siparis_riskte: number | null; karsiliksiz_olay_12ay: number | null; son_odeme_tarihi: string | null; asof: string | null } | null;
  sahibim: boolean;
  warnings: string[];
};

export type Finding = {
  id: string;
  tur: string;
  turAd: string;
  varlik: 'account' | 'contact' | 'sistem';
  kayit: string;
  eslesen: string | null;
  code: string | null;
  ad: string | null;
  olasilik: number | null;
  ozet: string | null;
  onem: 'yuksek' | 'orta' | 'dusuk';
  onemAd: string;
  durum: 'acik' | 'crmde_duzeltildi' | 'dogrulandi' | 'kapandi' | 'yoksay';
  durumAd: string;
  not: string | null;
  isaretleyen: string | null;
  isaretZamani: string | null;
  ilk: string | null;
  son: string | null;
  kapanis: string | null;
  crmLink: string | null;
};

export type ScorePoint = { tarih: string; puan: number; etkin: number | null; bulgulu: number | null; sayilar: Record<string, number> };

export type Health = Paged<Finding> & {
  sayilar: Record<string, Record<string, number>>;
  puan: ScorePoint | null;
  onceki: ScorePoint | null;
  veriDurumu: Record<string, number> | null;
  crmKanal: Record<string, number> | null;
  kisi: number | null;
  zeki: { decided?: number; waiting?: number; note?: string } | null;
  tarih: string | null;
  warnings: string[];
};

export type AccountQuery = { kanal?: string; bolge?: string; temsilci?: string; risk?: string; segment?: string; q?: string; sort?: string; p?: number; size?: number };

const P = '/api/v1/musteri';
const enc = encodeURIComponent;
export const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const musteriApi = {
  meta: () => send<Meta>('GET', `${P}/meta`, undefined, 60_000),
  overview: (temsilci?: string) => send<Overview>('GET', `${P}/overview${qs({ temsilci })}`, undefined, 120_000),
  accounts: (p: AccountQuery) => send<Paged<Account> & { toplam: { net12: number; riskli: number } }>('GET', `${P}/accounts${qs(p)}`),
  accountsCsvUrl: (p: AccountQuery) => `${ENGINE_BASE}${P}/accounts/export.csv${qs({ ...p, p: undefined, size: undefined })}`,
  account: (code: string) => send<Detail>('GET', `${P}/accounts/${enc(code)}`, undefined, 180_000),
  monthly: (code: string) => send<{ code: string; kesim: string; items: Array<{ ay: string; satis: number; iade: number; net: number }> }>('GET', `${P}/accounts/${enc(code)}/monthly`, undefined, 180_000),
  summary: (code: string) => send<{ metin: string; kaynak: 'zeki' | 'kural'; not: string | null }>('POST', `${P}/accounts/${enc(code)}/summary`, {}, 180_000),
  phone: (code: string) => send<{ code: string; telefon: string | null }>('GET', `${P}/accounts/${enc(code)}/phone`, undefined, 60_000),
  addAction: (code: string, b: { tur: Action['tur']; aciklama: string; termin?: string | null; sahip?: string }) => send<Action>('POST', `${P}/accounts/${enc(code)}/actions`, b),
  updateAction: (id: string, b: Partial<{ durum: Action['durum']; sonucNotu: string; termin: string | null; aciklama: string; sahip: string }>) =>
    send<Action>('PATCH', `${P}/actions/${enc(id)}`, b),
  actions: (p: { durum?: string; temsilci?: string; musteri?: string }) => send<{ items: Action[]; etki: Effect }>('GET', `${P}/actions${qs(p)}`),
  myPortfolio: (q?: string) => send<{ asof: string | null; kesim: string | null; count: number; buHafta: number; items: Account[]; acikAksiyon: Action[] }>('GET', `${P}/my-portfolio${qs({ q })}`),
  health: (p: { tur?: string; durum?: string; onem?: string; q?: string; p?: number; size?: number }) => send<Health>('GET', `${P}/health${qs(p)}`, undefined, 120_000),
  healthCsvUrl: (p: { tur?: string; durum?: string; onem?: string; q?: string }) => `${ENGINE_BASE}${P}/health/export.csv${qs(p)}`,
  mark: (id: string, b: { durum: 'crmde_duzeltildi' | 'yoksay' | 'acik'; not?: string }) => send<Finding>('POST', `${P}/health/${enc(id)}/mark`, b),
  scoreHistory: (gun = 365) => send<{ items: ScorePoint[] }>('GET', `${P}/health/score-history${qs({ gun })}`),
  segments: () => send<{ items: Array<{ id: string; ad: string; boyut: number; deger: number | null; pay: number | null; tarih: string }>; kural: string }>('GET', `${P}/segments`),
};

/* ------------------------------------------------------------------ biçim (saf; testli) */

/** Düzeyin tonu: kayıp ve yüksek kırmızı, orta sarı. */
export function levelTone(l: Level | null | undefined): 'err' | 'warn' | 'muted' {
  return l === 'kayip' || l === 'yuksek' ? 'err' : l === 'orta' ? 'warn' : 'muted';
}

/** Değişim oranı: +0,12 → «+%12», −0,345 → «−%35», null → «—». */
export function fmtChange(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—';
  // Yarım değer sıfırdan uzağa yuvarlanır (−%34,5 → −%35); 0,345×100 kayan noktada 34,4999… çıkar.
  const n = Math.sign(v) * Math.round(Math.abs(v) * 100 + 1e-9);
  return `${n > 0 ? '+' : n < 0 ? '−' : ''}%${Math.abs(n)}`;
}

/** Aralığın kaynağı (ekranda açıklama): carinin kendi alımları ya da kanal/genel medyanı. */
export const INTERVAL_SOURCE: Record<string, string> = {
  kendi: 'kendi alımlarından',
  kanal: 'alımı az; kanalının medyanı',
  genel: 'alımı az; bütün carilerin medyanı',
  ayar: 'varsayılan',
};

/** Aylık seriden çubuk yükseklikleri (0–1); negatif ay (iade fazlası) 0 çubuk + işaret. */
export function barHeights(values: number[]): number[] {
  const max = Math.max(0, ...values);
  return values.map((v) => (max > 0 && v > 0 ? v / max : 0));
}

/** «2026-08» → «Ağu 26». */
export function fmtMonth(ym: string): string {
  const [y, m] = ym.split('-').map(Number);
  if (!y || !m) return ym;
  const names = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];
  return `${names[m - 1]} ${String(y).slice(2)}`;
}
