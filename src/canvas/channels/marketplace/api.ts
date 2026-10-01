import { platformClient, qs, type PageOf } from '../platformKit';

/**
 * Trendyol ve Amazon TR için ortak: Aşama 0 satış modeli tespiti (`…/{platform}/model`) ve Aşama 1 satış/iade
 * mutabakatı + hakediş (`…/{platform}/mutabakat*`). Logo/CRM yalnız okunur; pazar yerine hiçbir şey gönderilmez.
 */

export type Platform = 'trendyol' | 'amazon';
export type ModelKey = 'kendi-magaza' | 'toptan' | 'konsinye' | 'belirsiz';
export type Sinif = 'eslesti' | 'tutar-farki' | 'eksik-fatura' | 'fazla-fatura' | 'bekliyor' | 'iptal';
export type Tur = 'satis' | 'iade';
export type JobStatus = { running: boolean; step: string | null; error: string | null };

export type Evidence = { model: ModelKey; kural: string; metin: string; sayi: number };
export type ModelCari = {
  kod: string;
  unvan: string | null;
  kanal: string | null;
  kurallar: string[];
  /** Yalnız adı tutan, kanal kodu e-ticaret dışı cari: listelenir, kanıta girmez (neden). */
  hesapDisi?: string | null;
  faturalar: Record<string, { turAd: string; fatura: number; tutar: number }>;
  acikSevk: number;
  gecFaturalanan: number;
};
export type ModelView = {
  platform: Platform;
  platformAd: string;
  okundu: boolean;
  okumaZamani?: string | null;
  veriSonu?: string | null;
  donem?: { bas: string; bit: string; yillar: number[] };
  model: ModelKey;
  modelAd: string;
  guven: 'guclu' | 'zayif' | null;
  cumle: string;
  neden?: string | null;
  kanit: Evidence[];
  /** Baskın modelin yanında küçük kalan iz (satış tutarı payıyla). */
  yanIz?: string[];
  modeller: Record<ModelKey, string>;
  desenler: string[];
  ayarlar: { yil: number; konsinyeGun: number; gucluAy: number };
  cariler: ModelCari[];
  kesinti?: { bulundu: boolean; cumle: string; toplam: number; diger?: number; kalemler: Array<{ kalem: string; kalemAd: string; hizmetKodu: string; hizmet: string; satir: number; tutar: number }> };
  hakedis?: { bulundu: boolean; cumle: string; hareketler: Array<{ modulAd: string; turAd: string; yon: string; hareket: number; tutar: number }> };
  belgeMetni?: Array<{ turAd: string; kanal: string | null; fatura: number; enCokCariAy: number; tutar: number }>;
  crm?: { hata: string | null; firmalar: Array<{ ad: string; logoRef: string | null; siparis: Array<{ tip: string; ad: string; sayi: number }> }> };
  panel?: { eslesenFatura: number; eslesenSiparis: number; perakende: number; farkliCari: number } | null;
  job: JobStatus;
};

export type ReconOverview = {
  okundu: boolean;
  yontem: 'siparis-no' | 'barkod-gun-adet' | null;
  counts: Record<Tur, Record<Sinif, number>>;
  amounts: Record<Tur, Record<Sinif, number>>;
  aylik: Array<{ ay: string; panelSatis: number; panelSatisTutar: number; panelIade: number; logoSatisTutar: number; logoIadeTutar: number;
    eslesti: number; tutarFarki: number; farkToplam: number; eksik: number; eksikTutar: number; fazla: number; fazlaTutar: number }>;
  siniflar: Record<Sinif, string>;
  turler: Record<Tur, string>;
  okuma: { bas: string; bit: string; toleransGun: number; panelSiparis: number; fatura: number; alanIsabeti: Record<string, number>; _at?: string | null } | null;
  panelSiparis: number;
  dosyaTurleri: Record<string, string>;
  dosyalar: FileRow[];
  job: JobStatus;
  me: { username: string; canImport: boolean; canExport: boolean };
};

export type ReconItem = {
  tur: Tur;
  siparisNo: string | null;
  tarih: string | null;
  durum: string | null;
  sinif: Sinif;
  neden: string | null;
  panelAdet: number | null;
  panelTutar: number | null;
  logoTutar: number | null;
  fark: number | null;
  yontem: string | null;
  faturalar: Array<{ ref: number; turAd: string; tarih: string | null; tutar: number | null; cari: string | null; alan: string | null }>;
};

export type Settlement = {
  yuklendi: boolean;
  okundu: boolean;
  cumle?: string;
  kalemAd: Record<string, string>;
  kalemler?: Array<{ kalem: string; ad: string; satir: number; tutar: number }>;
  kesintiToplam?: number;
  aylik?: Array<{ ay: string; satis: number; iade: number; kesinti: number; odeme: number; net: number; logoKesinti: number | null; logoTahsilat: number | null }>;
  siparis?: number;
  logoFaturasiYok?: Array<{ siparisNo: string; satis: number; iade: number; kesinti: number; net: number; mutabakat: string | null }>;
  logoKesinti?: { bulundu: boolean; cumle: string; toplam?: number; kalemler?: Array<{ kalem: string; ad: string; satir: number; tutar: number }> };
  logoTahsilat?: { bulundu: boolean; cumle: string; toplam?: number; hareketler?: Array<{ modulAd: string; turAd: string; hareket: number; tutar: number }> };
  belgeler?: { toplam: number; logodaVar: number; logodaYok: string[] };
  odemeTakvimi?: Array<{ tarih: string; tutar: number }>;
};

export type FileRow = {
  id: string;
  tur: string;
  turAd: string;
  dosya: string | null;
  satir: number;
  yukleyen: string;
  tarih: string | null;
  kolonlar: { atlanan?: string[]; kisiselOlabilir?: string[]; atlananSatir?: number; eksiyeCevrilen?: string[]; bicim?: string | null };
};

export function marketplaceApi(platform: Platform) {
  const { send, url } = platformClient(`/api/v1/channels/${platform}`);
  return {
    model: () => send<ModelView>('GET', '/model'),
    modelRefresh: () => send<{ started: boolean; job: JobStatus }>('POST', '/model/refresh'),
    modelStatus: () => send<{ job: JobStatus }>('GET', '/model/status'),
    recon: () => send<ReconOverview>('GET', '/mutabakat'),
    reconItems: (p: { tur?: string; sinif?: string; q?: string; page?: number }) =>
      send<PageOf<ReconItem> & { yontem: string | null; okundu: boolean }>('GET', `/mutabakat/liste${qs(p)}`),
    settlement: () => send<Settlement>('GET', '/mutabakat/hakedis'),
    reconRefresh: () => send<{ started: boolean; job: JobStatus }>('POST', '/mutabakat/refresh'),
    reconStatus: () => send<{ job: JobStatus }>('GET', '/mutabakat/status'),
    upload: (tur: string, file: File) => send<FileRow>('POST', `/mutabakat/dosyalar${qs({ tur, filename: file.name })}`, file, 600_000),
    deleteFile: (id: string) => send<{ ok: boolean }>('DELETE', `/mutabakat/dosyalar/${encodeURIComponent(id)}`),
    exportUrl: (liste: 'liste' | 'hakedis-faturasiz', p: Record<string, string | undefined> = {}) => url(`/mutabakat/export/${liste}.xlsx${qs(p)}`),
  };
}

/** Modelin rozet rengi: belirsiz uyarı, zayıf kanıt nötr, güçlü kanıt onay. */
export function modelTone(model: ModelKey, guven: ModelView['guven']): 'ok' | 'warn' | 'muted' {
  if (model === 'belirsiz') return 'warn';
  return guven === 'guclu' ? 'ok' : 'muted';
}

/** Mutabakat sınıfının rengi. */
export function sinifTone(s: Sinif): 'ok' | 'warn' | 'err' | 'muted' | 'violet' {
  if (s === 'eslesti') return 'ok';
  if (s === 'tutar-farki') return 'warn';
  if (s === 'eksik-fatura' || s === 'fazla-fatura') return 'err';
  if (s === 'bekliyor') return 'violet';
  return 'muted';
}

/** Eşleşen belge alanı isabetleri: «siparis:docode» → «DOCODE (sipariş) 12». Büyükten küçüğe. */
export function fieldHits(h: Record<string, number> | null | undefined): Array<{ alan: string; tur: string; sayi: number }> {
  return Object.entries(h ?? {})
    .map(([k, sayi]) => {
      const [tur, alan] = k.split(':');
      return { alan: (alan ?? k).toUpperCase(), tur: tur === 'belge' ? 'kesinti belgesi' : 'sipariş', sayi };
    })
    .sort((a, b) => b.sayi - a.sayi);
}

/** İşaretli tutar (₺): eksi «−» ile, kuruşsuz binlik ayraçlı. */
export const tlSigned = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : `${v < 0 ? '−' : ''}${Math.abs(v).toLocaleString('tr-TR', { maximumFractionDigits: 2, minimumFractionDigits: 2 })} ₺`;

export const RULE_LABEL: Record<string, string> = {
  ad: 'Unvanda platform adı',
  'esleme-onayli': 'Cari eşlemesinde onaylı',
  'esleme-aday': 'Cari eşlemesinde aday',
  kanal: 'Kanal kodu bu platforma bağlı',
};
