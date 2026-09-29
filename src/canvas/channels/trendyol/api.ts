import { platformClient, qs, type PageOf } from '../platformKit';

/** M40 Trendyol: /api/v1/channels/trendyol/*. Yalnız okuma + panel dosyası; platforma hiçbir şey gönderilmez. */

const { send, url } = platformClient('/api/v1/channels/trendyol');

export type ImportType = 'urun' | 'siparis' | 'iade' | 'soru' | 'yorum';

export type JobStatus = { running: boolean; step: string | null; error: string | null; startedAt: number | null };
export type LogoRead = { veriSonu?: string | null; kitap?: number; barkod?: number; siteBagli?: boolean; siteKopyasi?: string | null; listeKdv?: number; _at?: string | null };
export type LastImport = { id: string; dosya: string | null; satir: number; tarih: string | null; yukleyen: string };

export type TrendyolMeta = {
  types: Record<ImportType, string>;
  stockDiffs: Record<string, string>;
  priceFlags: Record<string, string>;
  claimClasses: string[];
  settings: { minDepo: number; maxIndirim: number; listeKdv: number; vitrinMinStok: number; vitrinGun: number; soruSaat: number };
  api: { bagli: boolean; neden: string };
  job: JobStatus;
  logo: LogoRead;
  imports: Partial<Record<ImportType, LastImport>>;
  modelReady: boolean;
  me: {
    username: string;
    canImport: boolean;
    canDraft: boolean;
    canDecide: boolean;
    canMap: boolean;
    canMargin: boolean;
    canExport: boolean;
    pages: Record<'trendyol' | 'urunler' | 'siparisler' | 'sorular' | 'mutabakat', boolean>;
  };
};

export type Wholesale = {
  eslendi: boolean;
  neden?: string;
  cariler?: string[];
  period?: { yil: number; ayAdi: string; veriSonu: string | null };
  netCiro?: number;
  netAdet?: number;
  iadeOrani?: number | null;
  degisim?: number | null;
  cariSayisi?: number;
};

export type Overview = {
  toptan: Wholesale;
  yuklemeler: Partial<Record<ImportType, LastImport>>;
  urun: { toplam: number; satistaAcik: number };
  stokFarki: Record<string, number>;
  stokFarkiEtiket: Record<string, string>;
  soru: { cevapsiz: number; geciken: number };
  yorum: { ortalama: number | null; dusuk: number; toplam: number };
  siparis: { paket: number; geciken: number; aralik: { bas: string | null; bit: string | null } };
  logo: LogoRead;
};

export type Candidate = { cariKodu: string; unvan: string | null; kanal: string | null; ulke: string | null; durum: 'onayli' | 'baska-platform' | 'aday' | 'bekliyor' | 'listede-yok' };

export type StockRow = {
  barkod: string;
  stokKodu: string | null;
  ad: string;
  satisaAcik: boolean | null;
  durum: string | null;
  trendyolStok: number | null;
  depoStok: number | null;
  fark: string | null;
};

export type PriceRow = {
  barkod: string;
  stokKodu: string | null;
  ad: string;
  trendyolFiyat: number;
  piyasaFiyat: number | null;
  listeFiyat: number | null;
  listeKdvDahil: boolean | null;
  siteFiyat: number | null;
  indirim: number | null;
  siteFarki: number | null;
  birimMaliyet: number | null;
  isaret: string[];
};

export type OrderRow = {
  paketId: string;
  tarih: string | null;
  durum: string | null;
  kargoFirma: string | null;
  kargoDurum: string | null;
  termin: string | null;
  gecikti: boolean;
  barkod: string;
  stokKodu: string | null;
  ad: string;
  adet: number | null;
  tutar: number | null;
};

export type ClaimRow = {
  talepId: string;
  barkod: string;
  stokKodu: string | null;
  ad: string;
  adet: number | null;
  neden: string | null;
  aciklama: string | null;
  sinif: string | null;
  olasilik: number | null;
  yontem: string | null;
  durum: string | null;
  tarih: string | null;
};

export type QuestionRow = {
  id: string;
  barkod: string | null;
  stokKodu: string | null;
  ad: string;
  metin: string;
  cevaplandi: boolean | null;
  tarih: string | null;
  saat: number | null;
  gecikti: boolean;
  taslak: string | null;
  taslakYazan: string | null;
};

export type ReviewRow = { id: string; barkod: string | null; stokKodu: string | null; ad: string; puan: number | null; metin: string | null; tarih: string | null; taslak: string | null };

export type ShowcaseRow = {
  stokKodu: string;
  ad: string;
  satis: number;
  haftalik: number;
  depoStok: number;
  karsilamaHafta: number | null;
  puan: number;
  trendyolAcik: boolean | null;
  trendyolStok: number | null;
};

export type Suggestion = {
  id: string;
  baslik: string;
  payload: { kitaplar?: ShowcaseRow[]; not?: string | null };
  gerekce: string | null;
  durum: 'taslak' | 'onayli' | 'red';
  olusturan: string;
  olusturma: string | null;
  kararVeren: string | null;
  kararNotu: string | null;
};

export type ImportRow = LastImport & {
  tur: ImportType;
  turAd: string;
  eslesen: number;
  kolonlar: { taninan?: Record<string, string>; atlanan?: string[]; kisiselOlabilir?: string[]; atlananSatir?: number; tekrar?: number };
};

export type Weekly = {
  bas: string;
  bit: string;
  siparis: { paket: number; adet: number; tutar: number; geciken: number; kitaplar: Array<{ stokKodu: string | null; barkod: string; ad: string; adet: number; tutar: number }> };
  iade: { talep: number; siniflar: Record<string, { talep: number; adet: number }>; kitaplar: Array<{ stokKodu: string | null; barkod: string; ad: string; iadeAdet: number; satisAdet: number; oran: number | null }> };
  soru: { cevapsiz: number; geciken: number };
  yorum: { hafta: number; dusuk: number; ortalama: number | null };
  stokFarki: Record<string, number>;
  ozet: string | null;
};

type P = { q?: string; page?: number };

export const trendyolApi = {
  meta: () => send<TrendyolMeta>('GET', '/meta'),
  status: () => send<{ job: JobStatus; logo: LogoRead }>('GET', '/status'),
  refresh: () => send<{ started: boolean; job: JobStatus }>('POST', '/refresh'),
  overview: () => send<Overview>('GET', '/overview'),
  accounts: () => send<{ adayCariler: Candidate[]; desenler: string[] | null; okundu: string | null; onayli: string[]; toptan: Wholesale }>('GET', '/accounts'),
  addAccount: (kod: string) => send<{ durum: string }>('POST', '/cariler/ekle', { kod }),
  products: (p: P & { durum?: string }) => send<PageOf<StockRow>>('GET', `/products${qs(p)}`),
  stockDiff: (p: P & { fark?: string }) =>
    send<PageOf<StockRow> & { counts: Record<string, number>; labels: Record<string, string>; urunSayisi: number; logo: LogoRead }>('GET', `/stock-diff${qs(p)}`),
  priceDiff: (p: P & { isaret?: string }) =>
    send<PageOf<PriceRow> & { counts: Record<string, number>; labels: Record<string, string>; esik: number; listeKdv: number; maliyetBagli: boolean }>('GET', `/price-diff${qs(p)}`),
  orders: (p: P & { durum?: string; bas?: string; bit?: string }) =>
    send<PageOf<OrderRow> & { durumlar: Record<string, { paket: number; adet: number; tutar: number }>; geciken: number; paketSayisi: number; adet: number; tutar: number; aralik: { bas: string | null; bit: string | null } }>(
      'GET',
      `/orders${qs(p)}`,
    ),
  claims: (p: P & { bas?: string; bit?: string; sinif?: string }) =>
    send<PageOf<ClaimRow> & { siniflar: Record<string, { talep: number; adet: number }>; kitaplar: Weekly['iade']['kitaplar']; sinifsiz: number }>('GET', `/claims${qs(p)}`),
  classify: () => send<{ kural: number; zeki: number; eminDegil: number; kalan: number; atlandi: string | null }>('POST', '/claims/classify'),
  questions: (p: P & { cevapsiz?: boolean }) =>
    send<PageOf<QuestionRow> & { cevapsiz: number; geciken: number; toplam: number; bilinmeyen: number; esikSaat: number }>('GET', `/questions${qs(p)}`),
  reviews: (p: P & { maxPuan?: number }) =>
    send<PageOf<ReviewRow> & { ortalama: number | null; dusuk: number; toplam: number; kitaplar: Array<{ stokKodu: string | null; ad: string; yorum: number; ortalama: number | null; dusuk: number }> }>(
      'GET',
      `/reviews${qs(p)}`,
    ),
  draft: (kind: 'questions' | 'reviews', id: string) => send<{ id: string; taslak: string; dusen: number }>('POST', `/${kind}/${encodeURIComponent(id)}/draft`),
  showcase: (p: P) => send<PageOf<ShowcaseRow> & { pencereGun: number; veriSonu: string | null; minStok: number }>('GET', `/showcase${qs(p)}`),
  suggest: (kitaplar: string[], not?: string) => send<Suggestion>('POST', '/showcase/suggest', { kitaplar, not }),
  suggestions: () => send<{ items: Suggestion[] }>('GET', '/suggestions'),
  decide: (id: string, karar: 'onayli' | 'red', not?: string) => send<Suggestion>('POST', `/suggestions/${encodeURIComponent(id)}/decision`, { karar, not }),
  imports: () => send<{ items: ImportRow[]; types: Record<ImportType, string> }>('GET', '/imports'),
  upload: (tur: ImportType, file: File) => send<ImportRow>('POST', `/imports${qs({ tur, filename: file.name })}`, file, 600_000),
  deleteImport: (id: string) => send<{ ok: boolean }>('DELETE', `/imports/${encodeURIComponent(id)}`),
  weekly: (bitis?: string, ozet?: boolean) => send<Weekly>('GET', `/weekly${qs({ bitis, ozet })}`),
  exportUrl: (liste: string, p: Record<string, string | number | boolean | undefined> = {}) => url(`/export/${liste}.xlsx${qs(p)}`),
};
