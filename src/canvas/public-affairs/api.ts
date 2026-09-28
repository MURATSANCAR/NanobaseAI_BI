import { ENGINE_BASE, send, type AuthorHeat } from '../engine';

/** M28 Kurumsal ilişkiler köprü istemcisi (`/api/v1/public-affairs/*`). Kişi/kurum kartı, temas notu, hediye programı ve
 *  kamu projeleri portal kaydıdır; CRM kişi, ziyaret yeri, kitap ve sipariş bilgisi yalnız okunur. Kişiye ve kuruma hiçbir
 *  şey gönderilmez; teklif dosyası indirilir, kuruma sorumlu verir. */

const B = '/api/v1/public-affairs';
const enc = encodeURIComponent;
export const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export type Heat = AuthorHeat;
export type Pair = { key: string; label: string };
export type Field = { key: string; label: string; active: boolean };
export type GiftStatus = 'oneri' | 'onayli' | 'sevk' | 'teslim' | 'donus' | 'iptal';
export type Stage = 'fikir' | 'gorusme' | 'teklif' | 'kurum_onayi' | 'uygulama' | 'rapor' | 'kapandi' | 'vazgecildi';

export type Meta = {
  fields: Field[];
  orgKinds: Pair[];
  priorities: Pair[];
  giftStatus: Pair[];
  projectKinds: Pair[];
  stages: Pair[];
  openStages: Stage[];
  proposalStatus: Pair[];
  channels: Pair[];
  tones: Pair[];
  visibility: Pair[];
  kurumTipi: Array<{ key: number; label: string }>;
  roles: Array<{ key: number; label: string }>;
  settings: { contactDays: number; criticalDays: number; giftGapDays: number; orderTypes: number[] };
  month: string;
  me: { username: string; display: string; admin: boolean; canEdit: boolean; canApprove: boolean; canSensitive: boolean; canExport: boolean };
};

export type Person = {
  id: string;
  crmContactId: string | null;
  crmAccountId: string | null;
  name: string;
  orgId: string | null;
  orgName: string | null;
  title: string | null;
  fieldKey: string | null;
  fieldLabel: string | null;
  interests: string[];
  isPublicOfficial: boolean;
  priority: 'kritik' | 'normal';
  priorityLabel: string;
  owner: string | null;
  ownerDisplay: string | null;
  email: string | null;
  phone: string | null;
  city: string | null;
  createdBy: string;
  createdAt: string | null;
  updatedAt: string | null;
  archived: boolean;
};

export type PersonRow = Person & {
  heat: Heat;
  due: boolean;
  dueDays: number;
  openSteps: number;
  lastGift: { book: string | null; month: string; status: GiftStatus } | null;
};

export type Note = {
  id: string;
  personId: string | null;
  orgId: string | null;
  at: string;
  date: string;
  time: string;
  channel: string;
  channelLabel: string;
  tone: string | null;
  toneLabel: string | null;
  topic: string;
  text: string | null;
  visibility: 'herkes' | 'ozel';
  hidden: boolean;
  participants: Array<{ username: string; display: string }>;
  nextStep: string | null;
  nextOn: string | null;
  nextDone: boolean;
  createdBy: string;
  createdDisplay: string | null;
  createdAt: string | null;
  canEdit: boolean;
};

export type CrmContact = {
  crmContactId: string | null;
  name: string | null;
  title: string | null;
  role: number | null;
  roleLabel: string | null;
  crmAccountId: string | null;
  orgName: string | null;
  orgRole: string | null;
  city: string | null;
  unvan: string | null;
  academicTitle: string | null;
  profession: string | null;
  email: string | null;
  phone: string | null;
  personId?: string | null;
};

export type Gift = {
  id: string;
  month: string;
  personId: string;
  personName: string | null;
  personTitle: string | null;
  isPublicOfficial: boolean;
  crmBookId: string;
  bookName: string | null;
  stockCode: string | null;
  author: string | null;
  reason: string | null;
  noteText: string | null;
  status: GiftStatus;
  statusLabel: string;
  legalOk: boolean;
  legalOkBy: string | null;
  crmOrderNo: string | null;
  crmOrderStatus: number | null;
  crmOrderStatusLabel: string | null;
  crmOrderType: number | null;
  crmBookInOrder: boolean | null;
  crmSyncedAt: string | null;
  shippedOn: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  feedback: string | null;
  feedbackAt: string | null;
  createdBy: string;
  createdAt: string | null;
};

export type PersonDetail = PersonRow & {
  timeline: Note[];
  gifts: Gift[];
  crm: null | { contact?: CrmContact | null; tags?: string[]; error?: string };
};

export type Org = {
  id: string;
  crmVisitPlaceId: string | null;
  crmAccountId: string | null;
  name: string;
  kind: string;
  kindLabel: string;
  city: string | null;
  owner: string | null;
  ownerDisplay: string | null;
  note: string | null;
  createdBy: string;
  archived: boolean;
  people?: number;
  openProjects?: number;
};

export type Place = {
  id: string | null;
  name: string | null;
  kurumTipi: number | null;
  kurumTipiLabel: string | null;
  kurumTuru: string | null;
  students: number | null;
  teachers: number | null;
  books: number | null;
  totalStudents: number | null;
  cityId: string | null;
  city: string | null;
  district: string | null;
  phone: string | null;
  orgId?: string | null;
};

export type OrgDetail = Org & {
  people: PersonRow[];
  projects: Project[];
  timeline: Note[];
  crm: null | { place?: Place | null; error?: string };
};

export type Book = {
  id: string | null;
  name: string | null;
  stockCode: string | null;
  genres: string | null;
  categories: string | null;
  audience: string | null;
  ages: string | null;
  ageFrom: number | null;
  ageTo: number | null;
  firstPrint: string | null;
  author: string | null;
};

export type ProjectBook = { id: string; name: string | null; stockCode: string | null; qty: number | null };

export type Project = {
  id: string;
  orgId: string | null;
  orgName: string | null;
  orgKind: string | null;
  title: string;
  kind: string;
  kindLabel: string;
  stage: Stage;
  stageLabel: string;
  stageIndex: number;
  open: boolean;
  owner: string | null;
  ownerDisplay: string | null;
  summary: string | null;
  budget: number | null;
  budgetApprovedBy: string | null;
  books: ProjectBook[];
  places: string[];
  orders: string[];
  reachSchools: number | null;
  reachStudents: number | null;
  reachBooks: number | null;
  reachParticipants: number | null;
  press: string[];
  nextStep: string | null;
  nextOn: string | null;
  late: boolean;
  quiet?: boolean;
  lastEvent?: string | null;
  tenderRef: string | null;
  proposalText: string | null;
  proposalStatus: 'yok' | 'hazirlaniyor' | 'hazir' | 'hata';
  proposalStatusLabel: string;
  proposalAt: string | null;
  proposalError: string | null;
  proposalApprovedBy: string | null;
  createdBy: string;
  updatedAt: string | null;
};

export type ProjectEvent = {
  id: string;
  at: string;
  user: string;
  userDisplay: string | null;
  stageFrom: string | null;
  stageTo: string | null;
  stageFromLabel: string | null;
  stageToLabel: string | null;
  note: string | null;
  docRef: string | null;
};

export type ProjectDetail = Project & { events: ProjectEvent[] };

export type ReachFacts = {
  places: number;
  students: number;
  studentsUnknown: number;
  teachers: number;
  teachersUnknown: number;
  bookTitles: number;
  booksPlanned: number | null;
  booksDelivered: number | null;
};

export type Suggestion = {
  bookId: string;
  bookName: string | null;
  stockCode: string | null;
  author: string | null;
  personId: string;
  personName: string;
  personTitle: string | null;
  orgName: string | null;
  fieldLabel: string | null;
  isPublicOfficial: boolean;
  score: number;
  match: number;
  reason: string;
};

export type Home = {
  due: PersonRow[];
  dueTotal: number;
  peopleCounts: { toplam: number; zamani: number; kritik: number };
  projects: Project[];
  projectStages: Record<string, number>;
  lateProjects: number;
  quietProjects: number;
  month: string;
  gifts: Record<GiftStatus, number>;
  giftBooks: number;
  giftPeople: number;
  waitingApproval: number;
  lateSteps: number;
};

export type Report = {
  year: number;
  people: { total: number; critical: number; publicOfficials: number; byField: Array<{ label: string; count: number }> };
  contacts: { notes: number; people: number; orgs: number };
  gifts: { byStatus: Record<GiftStatus, number>; sentBooks: number; sentPeople: number; feedback: number; duplicates: number };
  projects: {
    byStage: Record<string, number>;
    items: Project[];
    reach: { schools: number; students: number; books: number; participants: number };
  };
  crm: { types: Array<{ type: number; label: string; orders: number; books: number }>; excludedStatus?: number[]; error: string | null };
};

type Page<T> = { items: T[]; total: number; page: number; pageSize: number };

export const paApi = {
  meta: () => send<Meta>('GET', `${B}/meta`),
  home: () => send<Home>('GET', `${B}/home`),
  people: (p: { q?: string; field?: string; priority?: string; scope?: string; org?: string; archived?: boolean; order?: string } = {}) =>
    send<{ items: PersonRow[]; total: number; counts: Home['peopleCounts'] }>('GET', `${B}/people${qs(p)}`),
  person: (id: string) => send<PersonDetail>('GET', `${B}/people/${enc(id)}`),
  addPerson: (b: Record<string, unknown>) => send<Person & { created: boolean }>('POST', `${B}/people`, b),
  updatePerson: (id: string, b: Record<string, unknown>) => send<Person>('PATCH', `${B}/people/${enc(id)}`, b),
  suggestField: (id: string) =>
    send<{ fieldKey: string | null; candidate?: string | null; probability?: number | null; sure?: boolean; reason: string | null }>(
      'POST',
      `${B}/people/${enc(id)}/suggest-field`,
      {},
      90_000,
    ),
  addPersonNote: (id: string, b: Record<string, unknown>) => send<Note>('POST', `${B}/people/${enc(id)}/notes`, b),
  addOrgNote: (id: string, b: Record<string, unknown>) => send<Note>('POST', `${B}/orgs/${enc(id)}/notes`, b),
  updateNote: (id: string, b: Record<string, unknown>) => send<Note>('PATCH', `${B}/notes/${enc(id)}`, b),
  deleteNote: (id: string) => send<{ ok: boolean }>('DELETE', `${B}/notes/${enc(id)}`),
  orgs: (p: { q?: string; kind?: string; archived?: boolean } = {}) => send<{ items: Org[]; total: number }>('GET', `${B}/orgs${qs(p)}`),
  org: (id: string) => send<OrgDetail>('GET', `${B}/orgs/${enc(id)}`),
  addOrg: (b: Record<string, unknown>) => send<Org & { created: boolean }>('POST', `${B}/orgs`, b),
  updateOrg: (id: string, b: Record<string, unknown>) => send<Org>('PATCH', `${B}/orgs/${enc(id)}`, b),
  crmContacts: (p: { q?: string; role?: number | ''; page?: number }) => send<Page<CrmContact>>('GET', `${B}/crm/contacts${qs(p)}`),
  crmPlaces: (p: { q?: string; kurumTipi?: number | ''; il?: string; page?: number }) => send<Page<Place>>('GET', `${B}/crm/places${qs(p)}`),
  crmCities: () => send<{ items: Array<{ id: string; name: string }> }>('GET', `${B}/crm/cities`),
  cityStats: (il: string, kurumTipi: number) =>
    send<{ places: number; students: number; studentsUnknown: number; kurumTipiLabel: string | null }>('GET', `${B}/crm/city-stats${qs({ il, kurumTipi })}`),
  crmRoles: () => send<{ personRoles: Array<{ id: string; name: string; people: number }>; decisionMakers: number }>('GET', `${B}/crm/roles`),
  crmBooks: (p: { q?: string; page?: number; month?: string }) => send<Page<Book>>('GET', `${B}/crm/books${qs(p)}`),
  gifts: (p: { month?: string; status?: string; person?: string } = {}) =>
    send<{ items: Gift[]; total: number; counts: Record<GiftStatus, number>; books: number; people: number }>('GET', `${B}/gifts${qs(p)}`),
  addGift: (b: Record<string, unknown>) => send<Gift>('POST', `${B}/gifts`, b),
  updateGift: (id: string, b: Record<string, unknown>) => send<Gift>('PATCH', `${B}/gifts/${enc(id)}`, b),
  approveGifts: (b: { ids: string[]; decision?: 'onay' | 'geri'; legalOk?: string[] }) =>
    send<{ done: string[]; skipped: Array<{ id: string; reason: string }> }>('POST', `${B}/gifts/approve`, b),
  suggest: (b: { bookIds?: string[]; month?: string; all?: boolean }) =>
    send<{ items: Suggestion[]; total: number; books: Array<{ id: string; name: string | null; author: string | null; stockCode: string | null }>; people: number }>(
      'POST',
      `${B}/gifts/suggest`,
      b,
      120_000,
    ),
  draftNote: (id: string) => send<Gift>('POST', `${B}/gifts/${enc(id)}/draft-note`, {}, 120_000),
  projects: (p: { stage?: string; kind?: string; org?: string; q?: string; scope?: string; closed?: boolean } = {}) =>
    send<{ items: Project[]; total: number; stages: Record<string, number> }>('GET', `${B}/projects${qs(p)}`),
  project: (id: string) => send<ProjectDetail>('GET', `${B}/projects/${enc(id)}`),
  addProject: (b: Record<string, unknown>) => send<Project>('POST', `${B}/projects`, b),
  updateProject: (id: string, b: Record<string, unknown>) => send<ProjectDetail>('PATCH', `${B}/projects/${enc(id)}`, b),
  approveProject: (id: string, what: 'budget' | 'proposal', decision: 'onay' | 'geri' = 'onay') =>
    send<ProjectDetail>('POST', `${B}/projects/${enc(id)}/approve`, { what, decision }),
  draftProposal: (id: string) => send<ProjectDetail & { started: boolean }>('POST', `${B}/projects/${enc(id)}/draft-proposal`, {}),
  projectReport: (id: string) =>
    send<{ project: ProjectDetail; facts: ReachFacts | null; places: Place[]; missingOrders?: string[]; crmError: string | null }>(
      'GET',
      `${B}/projects/${enc(id)}/report`,
      undefined,
      120_000,
    ),
  proposalPdfUrl: (id: string) => `${ENGINE_BASE}${B}/projects/${enc(id)}/proposal.pdf`,
  report: (year?: number) => send<Report>('GET', `${B}/report${qs({ year })}`, undefined, 120_000),
  reportPdfUrl: (year?: number) => `${ENGINE_BASE}${B}/report/export.pdf${qs({ year })}`,
  fields: () => send<{ items: Field[] }>('GET', `${B}/fields`),
  addField: (label: string) => send<Field>('POST', `${B}/fields`, { label }),
  updateField: (key: string, b: { label?: string; active?: boolean }) => send<Field>('PATCH', `${B}/fields/${enc(key)}`, b),
};

/* ------------------------------------------------------------------ biçimler */

export const nf = new Intl.NumberFormat('tr-TR');
export const fmtInt = (n: number | null | undefined) => (n === null || n === undefined ? '—' : nf.format(n));
export const fmtMoney = (n: number | null | undefined) =>
  n === null || n === undefined ? '—' : `${new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 2 }).format(n)} ₺`;

const monthFmt = new Intl.DateTimeFormat('tr-TR', { month: 'long', year: 'numeric', timeZone: 'UTC' });
/** '2026-09' → 'Eylül 2026'. */
export function fmtMonth(key: string): string {
  const [y, m] = key.split('-').map(Number);
  if (!y || !m) return key;
  return monthFmt.format(new Date(Date.UTC(y, m - 1, 1)));
}

/** Ay anahtarını `delta` ay kaydırır ('2026-12', 1 → '2027-01'). */
export function shiftMonth(key: string, delta: number): string {
  const [y, m] = key.split('-').map(Number);
  const d = new Date(Date.UTC(y, m - 1 + delta, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

/** Türkçe tutar yazımı → sayı ('125.000,50' → 125000.5); boş ya da geçersizse null. */
export function parseAmount(s: string): number | null {
  const t = s.trim().replace(/\s|₺/g, '');
  if (!t) return null;
  const n = Number(t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : t);
  return Number.isFinite(n) ? n : null;
}

/** Aşama çubuğu için açık aşamalar (kapandı/vazgeçildi ayrı). */
export const STAGE_FLOW: Stage[] = ['fikir', 'gorusme', 'teklif', 'kurum_onayi', 'uygulama', 'rapor'];

export const GIFT_TONE: Record<GiftStatus, string> = {
  oneri: 'bg-slate-100 text-canvas-ink',
  onayli: 'bg-violet-50 text-violet-800',
  sevk: 'bg-sky-50 text-sky-800',
  teslim: 'bg-emerald-50 text-emerald-800',
  donus: 'bg-emerald-100 text-emerald-900',
  iptal: 'bg-red-50 text-red-700',
};

/** Hediye satırından sonraki elle geçilebilen durumlar (sunucudaki `GIFT_NEXT` ile aynı; onay ayrı düğme). */
export const GIFT_NEXT: Record<GiftStatus, GiftStatus[]> = {
  oneri: ['iptal'],
  onayli: ['sevk', 'iptal', 'oneri'],
  sevk: ['teslim', 'donus'],
  teslim: ['donus'],
  donus: [],
  iptal: ['oneri'],
};
