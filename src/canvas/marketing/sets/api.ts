import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../../engine';
import { httpErrorText } from '../../httpError';

/** M53 Set, hediye ve promosyon ekranının köprü uçları: /api/v1/marketing/sets*, /gift-offers*, /promo-items.
 *  Maliyet ve marj alanları kişinin «Set maliyeti ve marjı» yetkisi yoksa köprüden hiç gelmez (alanlar undefined olur). */

export type SetStatus = 'oneri' | 'taslak' | 'onayda' | 'kart-bekliyor' | 'satista' | 'kapanacak' | 'kapandi';
export type OfferStatus = 'taslak' | 'onayda' | 'onaylandi' | 'gonderildi' | 'kazanildi' | 'kaybedildi';

export type SetItem = {
  stok: string;
  ad: string | null;
  adet: number;
  liste: number | null;
  listeLogo?: number | null;
  kdv: number | null;
  maliyet?: number | null;
  maliyetKaynak?: string | null;
  stokAdet: number | null;
  kaynak?: string;
  kaynakAdi?: string;
};

export type SetRow = {
  id: string;
  ad: string;
  tur: string;
  turAdi: string;
  kaynak: string;
  kaynakAdi: string;
  crmKitapId: string | null;
  stokKodu: string | null;
  durum: SetStatus;
  durumAdi: string;
  sezonId: string | null;
  sezonAdi: string | null;
  kanal: string[];
  setFiyati: number | null;
  listeToplami: number | null;
  listeToplamiLogo: number | null;
  eksikFiyat: number;
  indirim: number | null;
  netGelir?: number | null;
  maliyetToplami?: number | null;
  eksikMaliyet?: number | null;
  ambalajTuru: string | null;
  ambalajBirimMaliyet?: number | null;
  marj?: number | null;
  marjOrani?: number | null;
  hedefAdet: number | null;
  gerekce: string | null;
  tanitim: string | null;
  brief: string | null;
  notlar: string | null;
  bilesenKaynak: string | null;
  crm: Record<string, unknown>;
  oneriId: string | null;
  bilesenSayisi: number;
  bilesenler: SetItem[] | null;
  bilesenStokMin: number | null;
  stok: number | null;
  son12Adet: number | null;
  son12Ciro: number | null;
  olusturan: string | null;
  gonderen: string | null;
  onaylayan: string | null;
  kararNotu: string | null;
  createdAt: string | null;
  decidedAt: string | null;
};

export type Page<T> = { items: T[]; total: number; page: number; pageSize: number };

export type SetsPage = Page<SetRow> & {
  summary: { toplam: number; satista: number; satissiz: number; marjBilinmiyor: number; onayda: number; kartBekliyor: number; oneri: number };
  dataEnd: string | null;
  window: [string, string];
};

export type PriceCalc = {
  listeToplami: number | null;
  eksikFiyat: number;
  indirim: number | null;
  kdvYontemi: 'liste' | 'adet';
  kdvBilinmeyen: number;
  netGelir?: number | null;
  maliyetToplami?: number | null;
  eksikMaliyet?: number;
  marj?: number | null;
  marjOrani?: number | null;
  marjUyari?: boolean;
  marjMesaj?: string | null;
  altSinir: number | null;
  setFiyati: number | null;
  bilesenler: SetItem[];
};

export type Suggestion = {
  id: string;
  tur: string;
  turAdi: string;
  ad: string;
  kuralAdi: string;
  aciklama: string | null;
  gerekce: string | null;
  skor: number;
  listeToplami: number | null;
  onerilenFiyat: number | null;
  indirim: number | null;
  marj?: number | null;
  marjOrani?: number | null;
  marjMesaj?: string | null;
  stokMin: number | null;
  yasMin: number | null;
  yasMax: number | null;
  turler: string | null;
  sezonAdi: string | null;
  durum: string;
  durumAdi: string;
  setId: string | null;
  bilesenler: (SetItem & { yazar?: string | null; son12Adet?: number | null })[];
};

export type OfferLine = { stok: string; ad: string | null; yazar?: string | null; adet: number; liste: number; kdv: number | null };
export type OfferOption = {
  no: number;
  tur: 'set' | 'paket' | 'kitap';
  ad: string;
  kalemler: OfferLine[];
  birimListe: number;
  indirim: number;
  birimNet: number;
  toplamNet: number;
  butceFarki: number;
  birimMaliyet?: number | null;
  marj?: number | null;
  marjOrani?: number | null;
};

export type Offer = {
  id: string;
  firmaId: string;
  firmaAdi: string | null;
  firmaKodu: string | null;
  adet: number;
  kisiBasiButce: number;
  secenekler: OfferOption[];
  secili: number[];
  kademeler: { adet: number; indirim: number }[];
  mektup: string | null;
  gecerlilik: string | null;
  durum: OfferStatus;
  durumAdi: string;
  sezon: string | null;
  notlar: string | null;
  hazirlayan: string | null;
  gonderen: string | null;
  onaylayan: string | null;
  kararNotu: string | null;
  m32FirsatId: string | null;
  gunKaldi?: number | null;
};

export type PromoItem = {
  stok: string;
  ad: string | null;
  tur: string;
  turAdi: string;
  crmTip: string | null;
  promosyonTipi: string | null;
  stokAdet: number | null;
  son12Adet: number | null;
  son12Ciro: number | null;
  bedelsizCikis: number | null;
};

export type Season = { id: string; ad: string; tarih: string | null; sonraki: string | null; gunKaldi: number | null };
export type Packaging = { tur: string; kod: number; birim: number | null; tarih: string | null; kayit: number };

export type RefreshStatus = {
  running: boolean;
  step: string | null;
  error: string | null;
  dataEnd: string | null;
  last: { ok?: boolean; error?: string; warnings?: string[]; _at?: string; sn?: number };
  basket: { asof?: string; cift?: number; siparis?: number; enAz?: number; donem?: [string, string] };
};

export type SetsMeta = {
  types: Record<string, string>;
  statuses: Record<SetStatus, string>;
  suggestionTypes: Record<string, string>;
  offerStatuses: Record<OfferStatus, string>;
  promoTypes: Record<string, string>;
  costSource: string;
  costSourceLabel: string;
  costProvider: boolean;
  settings: { marginMinPct: number | null; basketMinOrders: number; basketMonths: number; giftOptions: number; offerValidDays: number; listPriceSource: string };
  giftTiers: { adet: number; indirim: number }[];
  alerts: { tur: string; mesaj: string; set?: string; teklif?: string }[];
  packaging: Packaging[];
  seasons: Season[];
  discount: { indirim: number | null; n: number };
  status: RefreshStatus;
  me: { username: string; display: string; admin: boolean; canWrite: boolean; canApprove: boolean; canApproveOffer: boolean; canSeeCost: boolean; canExport: boolean };
};

export type Book = { stok: string; ad: string | null; yazar: string | null; liste: number | null; stokAdet: number | null; son12Adet: number | null; tip: string | null };
export type Account = { id: string; unvan: string | null; kod: string | null };

const B = '/api/v1/marketing';

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

export type ItemInput = { stok: string; adet: number };

export const setsApi = {
  meta: () => send<SetsMeta>('GET', '/sets/meta'),
  status: () => send<RefreshStatus>('GET', '/sets/status'),
  refresh: (basket = false) => send<RefreshStatus & { started: boolean }>('POST', `/sets/refresh${qs({ basket: basket || undefined })}`, {}),
  list: (p: { durum?: string; tur?: string; sezon?: string; q?: string; sort?: string; page?: number }) => send<SetsPage>('GET', `/sets${qs(p)}`),
  get: (id: string) => send<SetRow>('GET', `/sets/${enc(id)}`),
  create: (b: { ad: string; tur: string; bilesenler: ItemInput[]; setFiyati?: number | null }) => send<SetRow>('POST', '/sets', b),
  update: (id: string, b: Record<string, unknown>) => send<SetRow>('PATCH', `/sets/${enc(id)}`, b),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/sets/${enc(id)}`),
  items: (id: string, bilesenler: ItemInput[]) => send<SetRow>('PUT', `/sets/${enc(id)}/items`, { bilesenler }),
  price: (id: string, b: { setFiyati?: number | null; indirim?: number; ambalajBirimMaliyet?: number | null; bilesenler?: ItemInput[] }) =>
    send<PriceCalc>('POST', `/sets/${enc(id)}/price`, b),
  submit: (id: string) => send<SetRow>('POST', `/sets/${enc(id)}/submit`, {}),
  withdraw: (id: string) => send<SetRow>('POST', `/sets/${enc(id)}/withdraw`, {}),
  approve: (id: string, note?: string) => send<SetRow>('POST', `/sets/${enc(id)}/approve`, { note }),
  reject: (id: string, note: string) => send<SetRow>('POST', `/sets/${enc(id)}/reject`, { note }),
  text: (id: string, kind: 'tanitim' | 'brief') => send<{ text: string; dusenSayisi?: number }>('POST', `/sets/${enc(id)}/text`, { kind }, 300_000),
  cardTodo: (id: string) =>
    send<{ ad: string; setTipi: string; satisKanallari: string[]; onerilenFiyat: number | null; hedefAdet: number | null; ambalaj: string | null;
      sezon: string | null; barkod: string; adimlar: string[]; bilesenler: { stok: string; ad: string | null; adet: number; kdv: number | null; stokAdet: number | null }[];
      eslenmis: string | null }>('GET', `/sets/${enc(id)}/card-todo`),
  cardUrl: (id: string, fmt: 'csv' | 'pdf') => `${ENGINE_BASE}${B}/sets/${enc(id)}/card-todo.${fmt}`,
  link: (id: string, stokKodu: string) => send<SetRow>('POST', `/sets/${enc(id)}/link`, { stokKodu }),
  books: (q: string) => send<Page<Book>>('GET', `/sets/books${qs({ q })}`),
  pairs: (p: { q?: string; page?: number }) =>
    send<Page<{ a: string; b: string; adA: string | null; adB: string | null; siparis: number; lift: number | null }> & { meta: RefreshStatus['basket'] }>(
      'GET', `/sets/basket-pairs${qs(p)}`),
  suggestions: (p: { yas?: number | null; tema?: string; butce_min?: number | null; butce_max?: number | null; tur?: string; durum?: string; page?: number }) =>
    send<Page<Suggestion> & { indirim: { indirim: number | null; n: number } }>('GET', `/sets/suggestions${qs(p)}`),
  adopt: (sid: string) => send<SetRow>('POST', `/sets/suggestions/${enc(sid)}/adopt`, {}),
  dismiss: (sid: string) => send<{ id: string }>('POST', `/sets/suggestions/${enc(sid)}/dismiss`, {}),
  offers: (p: { durum?: string; q?: string; page?: number }) => send<Page<Offer> & { summary: Record<OfferStatus, number> }>('GET', `/gift-offers${qs(p)}`),
  offer: (id: string) => send<Offer>('GET', `/gift-offers/${enc(id)}`),
  accounts: (q: string) => send<Page<Account>>('GET', `/gift-offers/accounts${qs({ q })}`),
  history: (accountId: string) =>
    send<{ items: { no: string | null; hediyeTutari: number | null; toplam: number | null; tarih: string | null; durum: string }[] }>(
      'GET', `/gift-offers/accounts/${enc(accountId)}/history`),
  createOffer: (b: { firmaId: string; adet: number; kisiBasiButce: number; sezon?: string }) => send<Offer>('POST', '/gift-offers', b),
  updateOffer: (id: string, b: Record<string, unknown>) => send<Offer>('PATCH', `/gift-offers/${enc(id)}`, b),
  letter: (id: string) => send<{ text: string; dusenSayisi?: number }>('POST', `/gift-offers/${enc(id)}/letter`, {}, 300_000),
  submitOffer: (id: string) => send<Offer>('POST', `/gift-offers/${enc(id)}/submit`, {}),
  withdrawOffer: (id: string) => send<Offer>('POST', `/gift-offers/${enc(id)}/withdraw`, {}),
  approveOffer: (id: string, note?: string) => send<Offer>('POST', `/gift-offers/${enc(id)}/approve`, { note }),
  rejectOffer: (id: string, note: string) => send<Offer>('POST', `/gift-offers/${enc(id)}/reject`, { note }),
  offerPdfUrl: (id: string) => `${ENGINE_BASE}${B}/gift-offers/${enc(id)}/document.pdf`,
  promo: (p: { stok?: string; tur?: string; q?: string; page?: number }) =>
    send<Page<PromoItem> & { summary: Record<string, number>; window: [string, string] }>('GET', `/promo-items${qs(p)}`),
};

/* ------------------------------------------------------------------ saf yardımcılar (vitest) */

export const EDITABLE: SetStatus[] = ['oneri', 'taslak'];
export const canEditSet = (s: SetStatus) => EDITABLE.includes(s);

export const STATUS_TONE: Record<SetStatus, 'ok' | 'warn' | 'muted' | 'violet' | 'err'> = {
  oneri: 'violet',
  taslak: 'muted',
  onayda: 'warn',
  'kart-bekliyor': 'violet',
  satista: 'ok',
  kapanacak: 'warn',
  kapandi: 'muted',
};

export const OFFER_TONE: Record<OfferStatus, 'ok' | 'warn' | 'muted' | 'violet' | 'err'> = {
  taslak: 'muted',
  onayda: 'warn',
  onaylandi: 'violet',
  gonderildi: 'violet',
  kazanildi: 'ok',
  kaybedildi: 'err',
};

/** Bileşen listesine kitap ekler; aynı kod varsa adedi artar. */
export function addItem(items: ItemInput[], stok: string, adet = 1): ItemInput[] {
  const i = items.findIndex((x) => x.stok === stok);
  if (i < 0) return [...items, { stok, adet }];
  return items.map((x, n) => (n === i ? { ...x, adet: x.adet + adet } : x));
}

/** «%20» ya da «20» → 0,20; boşsa null; 0–95 dışı null. */
export function pctToRatio(s: string): number | null {
  const t = s.replace(/[%\s]/g, '').replace(',', '.');
  if (!t) return null;
  const n = Number(t);
  return Number.isFinite(n) && n >= 0 && n <= 95 ? n / 100 : null;
}
