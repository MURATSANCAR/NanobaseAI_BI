import { ENGINE_BASE, EngineAuthError, EngineForbiddenError, send } from '../engine';
import { httpErrorText } from '../httpError';

/** M31 Okul tanıtım ve ziyaret köprü istemcisi (`/api/v1/schools/*`). Okul = CRM ziyaret yeri (GUID); ziyaret raporu
 *  M30 ile ortak `semantic_saha_ziyaret` tablosunda. Puan ve rakamlar kuraldan/SQL'den gelir; Zeki AI yalnız metin yazar. */

export type ScorePart = { key: string; label: string; points: number; max: number; note: string };
export type CalendarHit = { from: string; to: string; kind: string; kindLabel?: string; name: string | null; il?: string | null };
export type DealerRef = { code: string | null; name: string | null };

export type SchoolRow = {
  id: string;
  name: string;
  il: string | null;
  ilce: string | null;
  kademe: string | null;
  kurumTuru: string | null;
  okulTuru: string | null;
  students: number | null;
  score: number;
  reason: string;
  lastVisit: string | null;
  dealers: DealerRef[];
  calendar: CalendarHit[];
};

export type SchoolList = {
  items: SchoolRow[];
  total: number;
  page: number;
  pageSize: number;
  scope: 'benim' | 'hepsi';
  mineCount: number;
  asOf: string | null;
  listChanged: string | null;
  warnings: string[];
};

export type Me = {
  username: string;
  display: string;
  admin: boolean;
  all: boolean;
  canVisit: boolean;
  canPlan: boolean;
  canDealer: boolean;
  canUpload: boolean;
  canExport: boolean;
};

export type Upload = { kind: string; label: string; rows: number; source: string | null; sourceDay: string | null; by: string; at: string | null };

export type Meta = {
  weights: Array<{ key: string; label: string; max: number }>;
  roles: Array<{ key: string; label: string }>;
  interest: Array<{ key: string; label: string }>;
  kademeler: Array<{ key: string; label: string }>;
  kurumTurleri: Array<{ key: string; label: string }>;
  contextKinds: Array<{ key: string; label: string }>;
  ils: string[];
  status: { asOf?: string | null; listChanged?: string | null; logoOk?: boolean; warnings?: string[]; schools?: number };
  uploads: Upload[];
  settings: { planSize: number; catalogSize: number; revisitDays: number; dealerMonths: number; conversionMonths: number; historyFrom: string };
  term: string;
  today: string;
  me: Me;
};

export type CrmVisit = {
  id: string | null;
  name: string | null;
  typeLabel: string | null;
  formLabel: string | null;
  statusLabel: string;
  day: string | null;
  dealer: string | null;
  participants: number | null;
  sold: number | null;
  owner: string | null;
  ownerName: string | null;
  done: boolean;
  matchedBy?: 'ad';
};

export type BookRef = { code: string; title: string | null; qty?: number | null };

export type PortalVisit = {
  id: string;
  source: 'portal';
  school: string;
  owner: string;
  ownerName: string;
  mine: boolean;
  state: 'planlandi' | 'yapildi' | 'iptal';
  stateLabel: string;
  at: string | null;
  day: string | null;
  note: string | null;
  hidden: boolean;
  secret: boolean;
  interest: string | null;
  interestLabel: string | null;
  role: string | null;
  roleLabel: string | null;
  books: BookRef[];
  routed: boolean;
  routedDealer: string | null;
  next: string | null;
  nextDay: string | null;
  planId: string | null;
  created: string | null;
  link?: DealerLink | null;
};

export type Order = { id: string | null; no: string | null; typeLabel: string | null; day: string | null; firm: string | null; qty: number | null; amount: number | null };

export type DealerLink = {
  id: string;
  school: string;
  code: string | null;
  name: string | null;
  source: 'gecmis' | 'oneri' | 'elle';
  sourceLabel: string;
  state: 'oneri' | 'onayli' | 'reddedildi';
  stateLabel: string;
  score: number | null;
  reason: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
  createdBy: string | null;
  created: string | null;
  il: string | null;
  ilce: string | null;
  phone: string | null;
  email: string | null;
  channel: string | null;
  schoolName?: string | null;
  schoolIl?: string | null;
  schoolIlce?: string | null;
  kademe?: string | null;
};

export type DealerCandidate = {
  code: string;
  name: string | null;
  channel: string | null;
  il: string | null;
  ilce: string | null;
  phone: string | null;
  email: string | null;
  score: number;
  sameIlce: boolean;
  gradeSales: number;
  linkedSchools: number;
  why: string[];
  warning: string | null;
  linked: boolean;
};

export type PlanItem = {
  id: string;
  owner: string;
  ownerName: string;
  term: string;
  week: string;
  day: string | null;
  school: string;
  schoolName: string | null;
  score: number | null;
  reason: string | null;
  aiReason: string | null;
  state: 'oneri' | 'onayli' | 'iptal';
  stateLabel: string;
  note: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  realized: { source: 'portal' | 'crm'; day: string; visitId: string | null } | null;
  conflicts: CalendarHit[];
  il?: string | null;
  ilce?: string | null;
  kademe?: string | null;
  students?: number | null;
  lastVisit?: string | null;
  dealers?: DealerRef[];
};

export type NextStep = { visitId: string; school: string; schoolName: string | null; step: string | null; day: string; late: boolean; owner: string };

export type WeekPlan = {
  week: string;
  weekEnd: string;
  term: string;
  owner: string | null;
  items: PlanItem[];
  nextSteps: NextStep[];
  calendar: Array<{ baslangic: string; bitis: string; tur: string; ad: string; il: string | null }>;
  done: number;
  planned: number;
  days: Array<{ day: string; label: string }>;
};

export type School = {
  id: string;
  code: string | null;
  name: string;
  kurumTipi: string | null;
  kurumTuru: string | null;
  okulTuru: string | null;
  kademe: string | null;
  grades: number[];
  gradesText: string;
  students: number | null;
  teachers: number | null;
  classrooms: number | null;
  libraryBooks: number | null;
  hall: string | null;
  phone: string | null;
  address: string | null;
  il: string | null;
  ilce: string | null;
  owner: string | null;
  ilOwner: string | null;
  changed: string | null;
};

export type CatalogSummary = { id: string; by: string; at: string | null; count: number; total: number | null };

export type SchoolDetail = {
  school: School;
  score: number;
  parts: ScorePart[];
  reason: string;
  lastVisit: string | null;
  inScope: boolean;
  crmVisits: CrmVisit[];
  crmDoneLinked: number;
  crmDoneByName: number;
  portalVisits: PortalVisit[];
  hiddenOthers: number;
  orders: Order[];
  ordersNote: string;
  links: DealerLink[];
  plans: PlanItem[];
  calendar: CalendarHit[];
  catalogs: CatalogSummary[];
  fittingBooks: number;
  logoOk: boolean;
  source: { asOf: string | null; changed: string | null; listChanged: string | null; label: string };
  warnings: string[];
};

export type CatalogItem = {
  code: string;
  title: string | null;
  grades: string;
  pages: number | null;
  price: number | null;
  priceBasis: string | null;
  stock: number | null;
  regionSales: number;
};

export type Catalog = {
  id: string | null;
  grades: number[];
  priceCap: number | null;
  size: number;
  total: number;
  items: CatalogItem[];
  warning?: string;
  dealer?: { name: string | null; il: string | null; ilce: string | null; phone: string | null } | null;
};

export type CatalogInput = { siniflar?: number[]; fiyatUst?: number | null; adet?: number | 'hepsi'; bayi?: string; onizleme?: boolean };

export type VisitInput = {
  durum: 'yapildi' | 'planlandi';
  gerceklesen?: string;
  kisiRolu?: string | null;
  ilgi?: string | null;
  istenenKitaplar?: BookRef[];
  bayiYonlendirildi?: boolean;
  bayi?: string | null;
  eslikEdenBayi?: string | null;
  sonrakiAdim?: string | null;
  sonrakiTarih?: string | null;
  not?: string | null;
  gizli?: boolean;
  planId?: string | null;
};

export type TermReport = {
  term: string;
  from: string;
  to: string;
  owner: string | null;
  il: string | null;
  plans: { planned: number; approved: number; realized: number; rate: number | null };
  visits: { portal: number; crm: number; schools: number };
  orders: { items: Array<{ type: number; label: string; count: number; amount: number }>; total: number; note: string };
  samples: { schools: number; converted: number; note: string };
  conversion: { dealers: number; up: number; down: number; flat: number; before: number; after: number; months: number; pending: number; note: string };
  byIl: Array<{ il: string; schools: number; visited: number; rate: number | null }>;
  byOwner: Array<{ owner: string; name: string; planned: number; realized: number; visits: number }>;
  asOf: string | null;
  warnings: string[];
};

export type ContextState = {
  uploads: Upload[];
  calendar: Array<{ baslangic: string; bitis: string; tur: string; ad: string; il: string | null }>;
  districts: Array<{ il: string; ilce: string; endeks: number; yil: string | null; crmIlceId: string | null }>;
  range: [number, number] | null;
};

export type UploadResult = { upload: string; kind: string; read: number; saved: number; problems: Array<{ satir: number; neden: string }> };

const P = '/api/v1/schools';
const qs = (o: Record<string, string | number | undefined | null>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export type ListFilter = { il?: string; ilce?: string; kademe?: string; tur?: string; oncelik?: string; q?: string; kapsam?: string; sirala?: string; page?: number };

export const schoolsApi = {
  meta: () => send<Meta>('GET', `${P}/meta`, undefined, 180_000),
  list: (f: ListFilter) => send<SchoolList>('GET', `${P}${qs(f)}`, undefined, 180_000),
  card: (id: string) => send<SchoolDetail>('GET', `${P}/${enc(id)}`, undefined, 180_000),
  advice: (id: string) => send<{ text: string; ai: boolean }>('POST', `${P}/${enc(id)}/advice`, {}, 120_000),
  plan: (hafta: string, opts: { sahip?: string; hepsi?: boolean } = {}) =>
    send<WeekPlan>('GET', `${P}/plan${qs({ hafta, sahip: opts.sahip, hepsi: opts.hepsi ? 1 : undefined })}`, undefined, 180_000),
  generate: (b: { hafta: string; adet?: number; il?: string; ilce?: string; kademe?: string; sahip?: string }) =>
    send<{ created: number; candidates: number; week: string; owner: string; skippedRecent: number }>('POST', `${P}/plan/generate`, b, 180_000),
  patchPlan: (id: string, b: { gun?: string; durum?: 'oneri' | 'iptal'; not?: string }) => send<PlanItem>('PATCH', `${P}/plan/${enc(id)}`, b, 30_000),
  approvePlan: (id: string) => send<PlanItem>('POST', `${P}/plan/${enc(id)}/approve`, {}, 30_000),
  addPlan: (id: string, b: { gun: string; not?: string }) => send<PlanItem>('POST', `${P}/${enc(id)}/plan`, b, 30_000),
  dealers: (id: string) =>
    send<{ links: DealerLink[]; candidates: DealerCandidate[]; logoOk: boolean; months: number; rule: string }>('GET', `${P}/${enc(id)}/dealers`, undefined, 120_000),
  addDealer: (id: string, code: string, not?: string) => send<DealerLink>('POST', `${P}/${enc(id)}/dealers`, { code, not }, 30_000),
  decideDealer: (id: string, link: string, approve: boolean, not?: string) =>
    send<DealerLink>('POST', `${P}/${enc(id)}/dealers/${enc(link)}/${approve ? 'approve' : 'reject'}`, { not }, 30_000),
  queue: () => send<{ items: DealerLink[]; total: number }>('GET', `${P}/dealer-queue`, undefined, 120_000),
  catalog: (id: string, b: CatalogInput) => send<Catalog>('POST', `${P}/${enc(id)}/catalog`, b, 120_000),
  visits: (id: string) => send<{ portal: PortalVisit[]; crm: CrmVisit[] }>('GET', `${P}/${enc(id)}/visits`, undefined, 60_000),
  addVisit: (id: string, b: VisitInput) => send<PortalVisit>('POST', `${P}/${enc(id)}/visits`, b, 30_000),
  suggest: (id: string, note: string) =>
    send<{ fields: Partial<VisitInput>; ai: boolean; message?: string }>('POST', `${P}/${enc(id)}/visits/suggest`, { not: note }, 120_000),
  nextDone: (visitId: string) => send<{ ok: boolean }>('POST', `${P}/visits/${enc(visitId)}/next-done`, {}, 30_000),
  term: (donem: string, f: { il?: string; sahip?: string } = {}) => send<TermReport>('GET', `${P}/report/term${qs({ donem, ...f })}`, undefined, 180_000),
  context: () => send<ContextState>('GET', `${P}/context`, undefined, 60_000),
  upload: (b: { tur: string; kaynak: string; kaynakTarihi?: string; csv?: string; xlsx?: string }) =>
    send<UploadResult>('POST', `${P}/context/upload`, b, 120_000),
};

/** Katalog PDF'ini indirir (oturum çerezli istek → dosya). */
export async function downloadCatalog(id: string): Promise<void> {
  const res = await fetch(`${ENGINE_BASE}${P}/catalogs/${enc(id)}.pdf`, { credentials: 'include', signal: AbortSignal.timeout(120_000) });
  if (res.status === 401) throw new EngineAuthError();
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } } | null;
    if (res.status === 403 && j?.detail?.code === 'FORBIDDEN') throw new EngineForbiddenError(j.detail.message);
    throw new Error(j?.detail?.message || httpErrorText(res.status));
  }
  const blob = await res.blob();
  const m = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = m ? m[1] : 'kitap-onerileri.pdf';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
