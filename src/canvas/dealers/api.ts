import { ENGINE_BASE, send } from '../engine';
import type { Visit } from '../field/api';

/** M59 Bayi riski köprü istemcisi (`/api/v1/dealers/*`). Cari = Logo müşteri carisi (cari kodu). Skor kuraldan (model yok),
 *  vade/gecikme FIFO yaklaşımı (Logo'da ödeme kapama yok), limitler CRM cari kartından. Portal CRM'e ve Logo'ya yazmaz. */

export type Segment = 'A' | 'B' | 'C' | 'D';
export type Group = 'standart' | 'anahtar';
export type Trend = 'kotulesiyor' | 'iyilesiyor' | 'yatay';
export type BucketKey = 'k_1_30' | 'k_31_60' | 'k_61_90' | 'k_90p';
export type ComponentKey = 'gecikme' | 'cek' | 'iade' | 'limit' | 'duzensizlik' | 'tahsilat_suresi';

export type Reason = { key: ComponentKey; puan: number; aciklama: string };
export type Component = Reason & { deger: number; agirlik: number };

export type Dealer = {
  code: string;
  unvan: string | null;
  kanal: string | null;
  il: string | null;
  bmt: string | null;
  bmtAd: string | null;
  grup: Group | null;
  bakiye: number | null;
  vadesiGecmis: number | null;
  k90: number | null;
  net12: number | null;
  iadeOrani: number | null;
  riskDoluluk: number | null;
  limitGirilmemis: boolean;
  skor: number | null;
  segment: Segment | null;
  oncekiSegment: Segment | null;
  egilim: Trend | null;
  skor30: number | null;
  hareketsiz: boolean;
  sorunlu: boolean;
  siparisRiskte: number;
  cekOlay: number;
  sonOdeme: string | null;
  sonFatura: string | null;
  neden: Reason[];
};

export type Thresholds = { A: number; B: number; C: number };
export type RuleBody = {
  agirliklar: Record<ComponentKey, number>;
  esikler: {
    standart: Thresholds;
    anahtar: Thresholds;
    iadeTavan: number;
    duzensizlikTavan: number;
    dsoHedef: number;
    dsoAralik: number;
    limitEsik: number;
    protestoKatsayi: number;
    egilimEsik: number;
  };
  kapsam: { kanallar: string[]; anahtarKanallar: string[]; anahtarPay: number; bosKanal: boolean };
  limit: { artisOrani: number; artisDoluluk: number; yeniLimitAy: number; yuvarlama: number };
};
export type Rule = RuleBody & {
  id: string;
  surum: number;
  durum: 'taslak' | 'onayda' | 'yururlukte' | 'arsiv';
  durumAd: string;
  gerekce: string | null;
  hazirlayan: string;
  olusturma: string | null;
  gonderen: string | null;
  gonderim: string | null;
  onaylayan: string | null;
  onayZamani: string | null;
  kararNotu: string | null;
};

export type DealersMeta = {
  me: {
    username: string;
    display: string;
    admin: boolean;
    cari: number;
    canAll: boolean;
    canNote: boolean;
    canAction: boolean;
    canLimit: boolean;
    canRule: boolean;
    canRuleApprove: boolean;
    canExport: boolean;
  };
  components: Array<{ key: ComponentKey; label: string; help: string }>;
  segments: Array<{ key: Segment; label: string }>;
  buckets: Array<{ key: BucketKey; label: string }>;
  actionKinds: Array<{ key: string; label: string }>;
  rule: Rule;
  run: {
    gun: string | null;
    dataEnd: string | null;
    agingAsof: string | null;
    scope: number | null;
    clients: number | null;
    assigned: number | null;
    idle: number | null;
    kural: number | null;
    karsilastirma30: string | null;
    kanallar: string[] | null;
    _at?: string;
  };
  bmts: Array<{ hesap: string; ad: string; cari: number }>;
  kanallar: string[];
  iller: string[];
  zekiQuestions: string[];
};

export type Dist = Record<Group, Record<Segment, number>>;

export type Proposal = {
  id: string;
  code: string;
  unvan: string | null;
  bmt: string | null;
  gun: string;
  segment: Segment | null;
  skor: number | null;
  mevcut: { limit_toplam?: number | null; risk_toplam?: number | null; risk_doluluk?: number | null; limit_acik?: number | null; limit_cek?: number | null };
  degisim: 'azalt' | 'artir' | 'tanimla';
  degisimAd: string;
  onerilen: number;
  gerekceKural: string;
  gerekceMetin: string | null;
  gerekceKaynak: 'kural' | 'zeki' | null;
  kuralSurum: number;
  durum: 'oneri' | 'onayli' | 'red' | 'crm_islendi' | 'gecersiz';
  durumAd: string;
  olusturma: string | null;
  kararVeren: string | null;
  kararAt: string | null;
  kararNotu: string | null;
  crmIsleyen: string | null;
  crmIslendiAt: string | null;
};

export type Summary = {
  gun: string | null;
  gun30: string | null;
  dataEnd: string | null;
  agingAsof: string | null;
  kural: number;
  cari: number;
  aktif: number;
  hareketsiz: number;
  segment: Dist;
  segment30: Dist | null;
  bakiye: number;
  vadesiGecmis: number;
  kovalar: Record<BucketKey, number>;
  kovaCari: Record<BucketKey, number>;
  plansiz: number;
  gelmemis: number;
  yogunlasma10: number | null;
  siparisRiskte: number;
  sorunlu: number;
  cekOlayCari: number;
  kotulesenler: Dealer[];
  egilimKotu: Dealer[];
  limitBekleyen: Proposal[];
};

export type Action = {
  id: string;
  code: string;
  unvan: string | null;
  tur: string;
  turAd: string;
  sahip: string;
  termin: string | null;
  durum: 'acik' | 'yapildi' | 'iptal';
  durumAd: string;
  notu: string | null;
  olusturan: string;
  olusturma: string | null;
};

export type MonthPoint = { ay: string; satis: number; iade: number; odeme: number; fatura: number };

export type BriefOut = {
  metin: string;
  maddeler: string[];
  kaynak: 'zeki' | 'kural';
  zaman: string | null;
  onbellek: boolean;
  olgular?: string[];
  not?: string | null;
  guncel?: boolean;
};

export type Card = Dealer & {
  gun: string;
  dataEnd: string | null;
  agingAsof: string | null;
  kuralSurum: number;
  fingerprint: string;
  bilesenler: Component[];
  kovalar: Record<BucketKey, number | null>;
  gelmemis: number | null;
  plansiz: number | null;
  satis12: number | null;
  iade12: number | null;
  buyume6: number | null;
  dso: number | null;
  duzensizlik: number | null;
  aktifAy: number | null;
  odeme12: number | null;
  karsiliksiz: number | null;
  protesto: number | null;
  cekTutar: number | null;
  limit: {
    limit_acik?: number | null;
    limit_cek?: number | null;
    limit_toplam?: number | null;
    risk_acik?: number | null;
    risk_cek?: number | null;
    risk_toplam?: number | null;
    risk_siparis?: number | null;
    risk_doluluk?: number | null;
    sorunlu?: boolean;
    kredi_askida?: boolean;
    vade_gun?: number | null;
    ek_limit?: number | null;
  };
  crmEsi: boolean;
  siparisRisktetutar: number | null;
  pay: number | null;
  seri: MonthPoint[];
  oneriler: Proposal[];
  aksiyonlar: Action[];
  ziyaretler: Visit[];
  ziyaretSayisi: number;
  brif: BriefOut | null;
};

export type RiskOrder = {
  no: string | null;
  tarih: string | null;
  tutar: number;
  riskte: boolean;
  sebep: string | null;
  anlikLimit: number | null;
  anlikRisk: number | null;
  onaylayan: string | null;
  reddeden: string | null;
  onayTarihi: string | null;
  redTarihi: string | null;
};
export type History = {
  skor: Array<{ gun: string; skor: number | null; segment: Segment | null; kural: number; vadesiGecmis: number | null; bakiye: number | null }>;
  seri: MonthPoint[];
  crmRisk: { items: RiskOrder[]; error: string | null };
};

export type Preview = {
  mevcut: Dist;
  taslak: Dist;
  degisen: Array<{ code: string; unvan: string | null; eski: Segment | null; yeni: Segment; eskiSkor: number | null; yeniSkor: number | null }>;
  kapsamDisi: number;
  not: string;
};

export type ListParams = {
  segment?: string;
  kanal?: string;
  il?: string;
  bmt?: string;
  q?: string;
  grup?: string;
  egilim?: string;
  durum?: string;
  order?: string;
  page?: number;
  size?: number;
};

const P = '/api/v1/dealers';
const enc = encodeURIComponent;
export const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const dealersApi = {
  meta: () => send<DealersMeta>('GET', `${P}/meta`, undefined, 60_000),
  summary: () => send<Summary>('GET', `${P}/summary`, undefined, 120_000),
  list: (p: ListParams) => send<{ items: Dealer[]; count: number; page: number; size: number; vadesiGecmis: number }>('GET', `${P}/list${qs(p)}`),
  exportUrl: (p: ListParams) => `${ENGINE_BASE}${P}/list/export.csv${qs({ ...p, page: undefined, size: undefined })}`,
  card: (code: string) => send<Card>('GET', `${P}/${enc(code)}`, undefined, 120_000),
  history: (code: string) => send<History>('GET', `${P}/${enc(code)}/history`, undefined, 120_000),
  brief: (code: string, yenile = false) => send<BriefOut>('POST', `${P}/${enc(code)}/brief${yenile ? '?yenile=true' : ''}`, {}, 180_000),
  addNote: (code: string, b: { notu: string; sozOdemeTarihi?: string | null; sozOdemeTutari?: number | null; sonrakiAdim?: string; gizli?: boolean }) =>
    send<Visit>('POST', `${P}/${enc(code)}/notes`, b),
  actions: (p: { code?: string; durum?: string; sahip?: string }) => send<{ items: Action[]; count: number }>('GET', `${P}/actions${qs(p)}`),
  addAction: (b: { code: string; tur: string; sahip?: string; termin?: string | null; notu?: string }) => send<Action>('POST', `${P}/actions`, b),
  updateAction: (id: string, b: { durum?: string; termin?: string | null; notu?: string }) => send<Action>('PATCH', `${P}/actions/${enc(id)}`, b),
  limits: (p: { durum?: string; code?: string }) => send<{ items: Proposal[]; count: number; states: Array<{ key: string; label: string }> }>('GET', `${P}/limits${qs(p)}`),
  approveLimit: (id: string, note?: string) => send<Proposal>('POST', `${P}/limits/${enc(id)}/approve`, { note }),
  rejectLimit: (id: string, note: string) => send<Proposal>('POST', `${P}/limits/${enc(id)}/reject`, { note }),
  crmDone: (id: string) => send<Proposal>('POST', `${P}/limits/${enc(id)}/crm-done`, {}),
  rules: () => send<{ items: Rule[] }>('GET', `${P}/rules`),
  createRule: (b: Partial<RuleBody> & { gerekce?: string }) => send<Rule>('POST', `${P}/rules`, b),
  editRule: (id: string, b: Partial<RuleBody> & { gerekce?: string }) => send<Rule>('PATCH', `${P}/rules/${enc(id)}`, b),
  previewRule: (id: string) => send<Preview>('POST', `${P}/rules/${enc(id)}/preview`, {}, 120_000),
  submitRule: (id: string) => send<Rule>('POST', `${P}/rules/${enc(id)}/submit`, {}),
  approveRule: (id: string, note?: string) => send<Rule>('POST', `${P}/rules/${enc(id)}/approve`, { note }),
  rejectRule: (id: string, note: string) => send<Rule>('POST', `${P}/rules/${enc(id)}/reject`, { note }),
};

/* ------------------------------------------------------------------ biçim (saf; testli) */

export const SEGMENTS: Segment[] = ['A', 'B', 'C', 'D'];

/** Segment rengi: A sakin, B nötr, C uyarı, D kırmızı. Renk tek başına anlam taşımaz; harf her zaman yazılır. */
export function segmentTone(s: Segment | null | undefined): 'ok' | 'muted' | 'warn' | 'err' {
  return s === 'A' ? 'ok' : s === 'C' ? 'warn' : s === 'D' ? 'err' : 'muted';
}

/** Segment düştü mü (A → D yönünde). */
export function worsened(now: Segment | null | undefined, before: Segment | null | undefined): boolean {
  if (!now || !before) return false;
  return SEGMENTS.indexOf(now) > SEGMENTS.indexOf(before);
}

export const TREND_LABEL: Record<Trend, string> = { kotulesiyor: 'Kötüleşiyor', iyilesiyor: 'İyileşiyor', yatay: 'Yatay' };

/** Ağırlık toplamı (kural formunda anlık uyarı için). */
export function weightSum(w: Partial<Record<ComponentKey, number>>): number {
  return Object.values(w).reduce((a: number, b) => a + (Number.isFinite(b) ? (b as number) : 0), 0);
}

/** Eşikler artan mı (A < B < C) ve 0–100 arası mı. */
export function thresholdsOk(t: Thresholds): boolean {
  return t.A >= 0 && t.C <= 100 && t.A < t.B && t.B < t.C;
}

/** Dağılımdaki toplam (gruplar birlikte). */
export function distTotal(d: Dist | null | undefined, s?: Segment): number {
  if (!d) return 0;
  return (Object.values(d) as Array<Record<Segment, number>>).reduce((a, g) => a + (s ? g[s] ?? 0 : SEGMENTS.reduce((x, k) => x + (g[k] ?? 0), 0)), 0);
}
