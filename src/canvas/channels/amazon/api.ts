import { platformClient, qs, type PageOf } from '../platformKit';

/** M41 Amazon ve yurtdışı: /api/v1/channels/amazon/*. Logo + CRM, yalnız okuma; Amazon hesabına hiçbir şey gönderilmez. */

const { send, url } = platformClient('/api/v1/channels/amazon');

export type JobStatus = { running: boolean; step: string | null; error: string | null };
export type ReadMeta = {
  ok?: boolean;
  years?: number[];
  konsinyeYillari?: number[];
  cariler?: string[];
  veriSonu?: string | null;
  doviz?: Record<string, { toplam: number; satis: number; satisTl: number }>;
  yurtdisiKodlari?: string[];
  crmError?: string | null;
  _at?: string | null;
};

export type AmazonMeta = {
  draftTypes: Record<'listeleme' | 'aplus' | 'brief', string>;
  decisions: Record<'girilsin' | 'bekle' | 'girilmesin', string>;
  api: { bagli: boolean; neden: string };
  job: JobStatus;
  read: ReadMeta;
  settings: { yurtdisiKodlari: string[]; yil: number; konsinyeYil: number; konsinyeTipi: number; cariAdlari: string[] };
  modelReady: boolean;
  me: {
    username: string;
    canDraft: boolean;
    canParam: boolean;
    canDecide: boolean;
    canMap: boolean;
    canExport: boolean;
    canImport: boolean;
    pages: Record<'amazon' | 'konsinye' | 'yurtdisi' | 'taslaklar', boolean>;
  };
};

export type Wholesale = {
  eslendi: boolean;
  neden?: string;
  cariler?: string[];
  period?: { yil: number; ayAdi: string };
  donem?: { netCiro: number; netAdet: number; satisAdet: number; iadeAdet: number; iadeOrani: number | null; iskontoOrani: number | null };
  degisim?: number | null;
  cariSatirlari?: Array<{ grup: string; ad: string; netCiro: number; netAdet: number; crmSiparis: Record<string, number> | null }>;
  crmSiparisGun?: number | null;
};

export type Overview = {
  okundu: boolean;
  read: ReadMeta;
  toptan: Wholesale;
  crm: { siparis?: Record<string, number>; tip?: number; haklar?: number; error?: string | null; ulkeHatasi?: string | null };
  adayCariler: { toplam: number; onayli: number; bekleyen: number };
  konsinye?: { sevk: number; iade: number; kalan: number; sevkTutar: number; kitap: number };
  yurtdisi?: { hata?: string; yil?: number; sonAy?: number; netCiro?: number; netAdet?: number; gecenYil?: number; gecenYilAyniDonem?: number; ulkeSayisi?: number;
    ilkUlkeler?: Array<{ ulke: string; netCiro: number }>; dovizToplam?: Record<string, number>; dovizFatura?: { toplam: number; satis: number } };
  haklar?: { kitap: number; sozlesme: number };
  taslak?: number;
  bekleyenKart?: number;
};

export type Candidate = { cariKodu: string; unvan: string | null; kanal: string | null; ulke: string | null; durum: 'onayli' | 'baska-platform' | 'aday' | 'bekliyor' | 'listede-yok' };

export type ConsignRow = { stokKodu: string; ad: string; sevk: number; iade: number; kalan: number; sevkTutar: number; faturalanan: number | null; ilk: string | null; son: string | null; cariler: string[] };

export type Intl = {
  yil: number;
  sonAy: number;
  yillar: number[];
  items: Array<{ cari: string; unvan: string | null; ulke: string; doviz: string; netCiro: number; netAdet: number; dovizNet: number; fatura: number; gecenYil: number; gecenYilAyniDonem: number }>;
  ulkeler: Array<{ ulke: string; netCiro: number; netAdet: number; gecenYil: number; gecenYilAyniDonem: number; cari: number }>;
  dovizToplam: Record<string, number>;
  aylik: Array<{ ay: number; buYil: number; gecenYil: number }>;
  dovizFatura: { toplam?: number; satis?: number; satisTl?: number };
  toplam: { netCiro: number; netAdet: number; gecenYil: number; gecenYilAyniDonem: number };
  kodlar: string[] | null;
  veriSonu: string | null;
};

export type IntlBook = { stokKodu: string; ad: string; netAdet: number; netCiro: number; iadeAdet: number; ulkeler: Array<{ ulke: string; netAdet: number }> };

export type RightsBook = {
  stokKodu: string | null;
  kitap: string | null;
  sozlesmeler: Array<{ id: string; no: string | null; ulke: string | null; firmalar: string | null; bas: string | null; bit: string | null; yurtdisiTaraf: boolean }>;
  ulkeler: string[];
  firmalar: string[];
  yurtdisiNetAdet: number;
};

export type Params = { pazar: string; ad: string; ulkeler: string[]; doviz: string | null; kurKaynagi: string | null; kdvOrani: number | null; kargoBirim: number | null; komisyonOrani: number | null; not: string | null; giren: string; tarih: string | null };

export type Draft = {
  id: string;
  stokKodu: string;
  kitap: string | null;
  pazar: string;
  dil: string;
  tur: 'listeleme' | 'aplus' | 'brief';
  turAd: string;
  metin: Record<string, unknown>;
  dusen: Array<{ cumle: string; neden: string }>;
  durum: 'taslak' | 'kullanildi';
  yazan: string;
  tarih: string | null;
};

export type MarketCard = {
  id: string;
  pazar: string;
  gostergeler: {
    ulkeler: string[];
    yillar: Record<string, { netCiro: number; netAdet: number }>;
    cariSayisi: number;
    kitaplar: Array<{ stokKodu: string; ad: string; netAdet: number }>;
    hakSatilanKitap: number;
    parametre: Params | null;
    veriSonu: string | null;
    not: string;
  };
  gerekce: string | null;
  not: string | null;
  hazirlayan: string;
  tarih: string | null;
  karar: 'girilsin' | 'bekle' | 'girilmesin' | null;
  kararAd: string | null;
  kararNotu: string | null;
  kararVeren: string | null;
};

type P = { q?: string; page?: number };

export const amazonApi = {
  meta: () => send<AmazonMeta>('GET', '/meta'),
  status: () => send<{ job: JobStatus; read: ReadMeta }>('GET', '/status'),
  refresh: () => send<{ started: boolean }>('POST', '/refresh'),
  overview: () => send<Overview>('GET', '/overview'),
  accounts: () => send<{ adayCariler: Candidate[]; desenler: string[] | null; okundu: string | null; onayli: string[]; toptan: Wholesale }>('GET', '/accounts'),
  addAccount: (kod: string) => send<{ durum: string }>('POST', '/cariler/ekle', { kod }),
  books: (p: P & { yil?: number }) => send<PageOf<{ stokKodu: string; ad: string; satisAdet: number; iadeAdet: number; netAdet: number; netCiro: number; iadeOrani: number | null }>>('GET', `/books${qs(p)}`),
  consignment: (p: P) =>
    send<PageOf<ConsignRow> & { toplam: Overview['konsinye']; cariler: Array<{ cari: string; sevk: number; iade: number; kalan: number; kitap: number }>; yillar: number[] | null; eslenenCariler: string[]; veriSonu: string | null; faturalananBagli: boolean }>(
      'GET',
      `/consignment${qs(p)}`,
    ),
  international: (p: { yil?: number; ulke?: string }) => send<Intl>('GET', `/international${qs(p)}`),
  intlBooks: (p: P & { yil?: number; ulke?: string }) => send<PageOf<IntlBook> & { yil: number }>('GET', `/international/books${qs(p)}`),
  rights: (p: P & { ulke?: string }) =>
    send<PageOf<RightsBook> & { ulkeler: Record<string, number>; sozlesme: number; crmHata: string | null; ulkeHatasi: string | null; okundu: string | null }>('GET', `/rights${qs(p)}`),
  params: () => send<{ items: Params[] }>('GET', '/params'),
  setParams: (pazar: string, b: Partial<Omit<Params, 'pazar' | 'giren' | 'tarih'>>) => send<Params>('PUT', `/params/${encodeURIComponent(pazar)}`, b),
  deleteParams: (pazar: string) => send<{ ok: boolean }>('DELETE', `/params/${encodeURIComponent(pazar)}`),
  drafts: (p: P & { stok?: string; pazar?: string }) => send<PageOf<Draft> & { turler: Record<string, string> }>('GET', `/drafts${qs(p)}`),
  createDraft: (b: { stokKodu: string; pazar: string; dil: string; tur: string }) => send<Draft>('POST', '/drafts', b, 300_000),
  setDraft: (id: string, durum: 'taslak' | 'kullanildi') => send<Draft>('PUT', `/drafts/${encodeURIComponent(id)}`, { durum }),
  cards: () => send<{ items: MarketCard[]; decisions: Record<string, string> }>('GET', '/market-cards'),
  createCard: (b: { pazar: string; ulkeler: string[]; not?: string }) => send<MarketCard>('POST', '/market-cards', b, 180_000),
  decideCard: (id: string, karar: string, not?: string) => send<MarketCard>('POST', `/market-cards/${encodeURIComponent(id)}/decision`, { karar, not }),
  exportUrl: (liste: string, p: Record<string, string | number | undefined> = {}) => url(`/export/${liste}.xlsx${qs(p)}`),
};
