import { send } from '../../engine';
import type { Kaynaklar } from '../../components/sqlInfo';

/** M12 Üretim Yönetimi köprü istemcisi (`/api/v1/editorial/production/*`). Kart = CRM üretim kartı (kitap + baskı no);
 *  gerçekleşen üretim ve depo girişi Logo'dan, CRM'de olmayanlar portal kaydından. */

export type Milestone = 'dosya' | 'matbaa' | 'baski' | 'depo';
export type MilestoneSource = 'logo' | 'crm' | 'portal';
export type ProdStage = 'hazirlik' | 'matbaa-secildi' | 'matbaada' | 'yolda' | 'tamam' | 'eski' | 'iptal';

/** `day` boş olabilir: CRM aşaması ilerlemiş ama tarihi girilmemiş. */
export type ActualPoint = { day: string | null; source: MilestoneSource; by?: string | null; note?: string | null };
export type Delay = { milestone: Milestone; label: string; due: string; days: number; level: 'sorumlu' | 'yonetici' };

export type ProdCard = {
  id: string;
  name: string | null;
  idno: string | null;
  bookId: string | null;
  bookTitle: string | null;
  stockCode: string | null;
  printNo: number | null;
  firstPrint: boolean;
  /** CRM kart türü: Yeni Baskı, Baskı Tekrarı, Yenileme. */
  cardKind: string | null;
  /** Üretim tipi: Kitap, Promosyon, Set… */
  kind: string | null;
  printer: string | null;
  crmStatus: string | null;
  /** «Üretimde beklemede» aşamasında bekleme nedeni. */
  waiting: string | null;
  bandrol: string | null;
  editor: string | null;
  designer: string | null;
  qty: number | null;
  qtySuggested: number | null;
  /** CRM'deki kesinleşen (satış) fiyatı. */
  coverPrice: number | null;
  /** Logo'daki matbaa baskı faturası: toplam, adet başı, faturalanan adet, faturayı kesen. */
  price: number | null;
  unitPrice: number | null;
  costQty: number | null;
  costSupplier: string | null;
  priority: string | null;
  created: string | null;
  promised: string | null;
  publication: string | null;
  plan: Partial<Record<Milestone, string | null>>;
  planBasis: 'crm' | 'yayin' | 'logo' | null;
  actual: Partial<Record<Milestone, ActualPoint>>;
  stage: ProdStage;
  stageLabel: string;
  delays: Delay[];
  quality: string | null;
  approval: string | null;
  logoQty: number | null;
  logoMatch: 'no' | 'stok' | null;
};

export type ProdMeta = {
  milestones: Array<{ key: Milestone; label: string }>;
  stages: Array<{ key: ProdStage; label: string }>;
  kinds: Array<{ key: string; label: string }>;
  quality: Array<{ key: string; label: string }>;
  printers: string[];
  settings: { filesDay: number; monthsBefore: number; escalateDays: number; staleDays: number; historyFrom: string };
  me: { username: string; display: string; canWrite: boolean; canApprove: boolean; admin: boolean };
  kaynaklar?: Kaynaklar;
};

export type LeadTime = { from: Milestone; to: Milestone; days: number | null; p25: number | null; p75: number | null; samples: number; negative: number };
export type TemplateOffset = { label: string; days: number | null; p25: number | null; p75: number | null; samples: number };

export type ProdOverview = {
  asOf: string;
  historyFrom: string;
  total: number;
  open: number;
  late: number;
  escalated: number;
  dueSoon: number;
  doneRecent: number;
  byStage: Record<ProdStage, number>;
  leads: Record<string, LeadTime>;
  template: Record<string, TemplateOffset>;
  logoMatched: number;
  logo: { firms: string[]; lastReceipt: string | null; lastOrder: string | null } | null;
  warnings: string[];
  kaynaklar?: Kaynaklar;
};

export type ProdList = { items: ProdCard[]; total: number; page: number; pageSize: number; kaynaklar?: Kaynaklar };

export type ProdEntry = {
  id: string;
  cardId: string;
  kind: string;
  kindLabel: string;
  milestone: Milestone | null;
  milestoneLabel: string | null;
  day: string | null;
  value: string | null;
  valueLabel: string | null;
  note: string | null;
  by: string;
  byName: string;
  at: string | null;
};

export type ProdQuote = {
  id: string;
  cardId: string;
  printer: string;
  unitPrice: number | null;
  totalPrice: number | null;
  deliveryDay: string | null;
  note: string | null;
  by: string;
  byName: string;
  at: string | null;
};

export type PrinterStat = {
  printer: string;
  jobs: number;
  open: number;
  done: number;
  copies: number;
  onTimeRate: number | null;
  measured: number;
  leadDays: number | null;
  leadSamples: number;
  unitPrice: number | null;
  unitSamples: number;
  unitRecent: number | null;
  unitPrevious: number | null;
  unitTrend: number | null;
  qualityRate: number | null;
  qualityMarked: number;
  last: string | null;
  score: number;
  scoreParts: { onTime: number; price: number; quality: number };
  scoreNotes: string[];
};

export type Suggestion = PrinterStat & { quote: ProdQuote | null; why: string[] };

export type LogoOrder = { no: string | null; date: string | null; planned: number | null; planEnd: string | null; status: string | null; item: string | null; firm: string | null };
export type LogoReceipt = { no: string | null; date: string | null; qty: number | null; planned: boolean };
export type LogoCost = { no: string | null; date: string | null; supplier: string | null; qty: number | null; total: number | null };
export type StudioLink = { job: string; title: string | null; status: string; ready: boolean; when: string | null };

export type ProdDetail = ProdCard & {
  entries: ProdEntry[];
  quotes: ProdQuote[];
  suggestions: Suggestion[];
  logoOrders: LogoOrder[];
  logoReceipts: LogoReceipt[];
  logoCosts: LogoCost[];
  studio: StudioLink[];
  crmDates: Array<{ key: string; label: string; day: string | null; plan: boolean }>;
  kaynaklar?: Kaynaklar;
};

export type PrintersReport = { items: PrinterStat[]; priceRef: number | null; historyFrom: string; kaynaklar?: Kaynaklar };

export type CalendarPlan = {
  publication: string;
  rule: { day: number; monthsBefore: number };
  plan: Record<Milestone, string | null>;
  expected: { baski: string | null; depo: string | null };
  extra: Array<{ key: string; label: string; day: string }>;
  risk: string[];
  leads: Record<string, LeadTime>;
  template: Record<string, TemplateOffset>;
  kaynaklar?: Kaynaklar;
};

export type PrintExit = {
  book: string;
  items: Array<{
    cardId: string;
    printNo: number | null;
    qty: number | null;
    stage: ProdStage;
    planned: string | null;
    actual: string | null;
    source: MilestoneSource | null;
    depot: string | null;
    depotPlanned: string | null;
  }>;
};

const P = '/api/v1/editorial/production';
const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
};

export type ListFilter = { durum?: string; matbaa?: string; q?: string; tur?: string; urun?: string; page?: number };

export const productionApi = {
  meta: () => send<ProdMeta>('GET', `${P}/meta`, undefined, 60_000),
  overview: () => send<ProdOverview>('GET', `${P}/overview`, undefined, 180_000),
  cards: (f: ListFilter) => send<ProdList>('GET', `${P}/cards${qs({ durum: f.durum, matbaa: f.matbaa, q: f.q, tur: f.tur, urun: f.urun, page: f.page })}`, undefined, 180_000),
  card: (id: string) => send<ProdDetail>('GET', `${P}/cards/${encodeURIComponent(id)}`, undefined, 120_000),
  addEntry: (id: string, b: { kind: string; milestone?: Milestone; day?: string; value?: string; note?: string }) =>
    send<ProdEntry>('POST', `${P}/cards/${encodeURIComponent(id)}/entries`, b, 30_000),
  deleteEntry: (id: string) => send<{ ok: boolean }>('DELETE', `${P}/entries/${encodeURIComponent(id)}`, undefined, 30_000),
  addQuote: (id: string, b: { printer: string; unitPrice?: string; totalPrice?: string; deliveryDay?: string; note?: string }) =>
    send<ProdQuote>('POST', `${P}/cards/${encodeURIComponent(id)}/quotes`, b, 30_000),
  deleteQuote: (id: string) => send<{ ok: boolean }>('DELETE', `${P}/quotes/${encodeURIComponent(id)}`, undefined, 30_000),
  approve: (id: string, b: { printer: string; note?: string }) => send<ProdEntry>('POST', `${P}/cards/${encodeURIComponent(id)}/approve`, b, 30_000),
  delays: () => send<{ items: ProdCard[]; escalateDays: number; kaynaklar?: Kaynaklar }>('GET', `${P}/delays`, undefined, 180_000),
  printers: () => send<PrintersReport>('GET', `${P}/printers`, undefined, 180_000),
  calendar: (publication: string) => send<CalendarPlan>('GET', `${P}/calendar${qs({ publication })}`, undefined, 180_000),
  printExit: (book: string) => send<PrintExit>('GET', `${P}/print-exit${qs({ book })}`, undefined, 180_000),
  newPrints: () => send<NewPrints>('GET', `${P}/new-prints`, undefined, 30_000),
};

/** Kampüs «Matbaadan yeni çıkanlar»: son `days` günde baskısı gerçekleşen kitaplar (yeniden eskiye). */
export type NewPrints = {
  items: Array<{
    cardId: string;
    bookId: string | null;
    title: string | null;
    stockCode?: string | null;
    printNo: number | null;
    firstPrint: boolean;
    day: string;
    depot: string | null;
    /** T-soft ürün görseli (stok koduyla); ürün sitede yoksa null. */
    cover?: string | null;
  }>;
  days: number;
  ready: boolean;
  asOf: string | null;
};
