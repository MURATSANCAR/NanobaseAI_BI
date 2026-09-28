import { send } from '../engine';

/** H4 Kurumsal e-posta köprü istemcisi (`/api/v1/mailbox/*`). timas@ genel kutusu yalnız okunur; ileti gövdesi portalda
 *  saklanmaz (her açılışta kutudan okunur). Portal dışarıya ileti göndermez: yanıt taslağı kopyalanır, kutunun kendi
 *  arayüzünden («Kutuda aç») gönderilir. */

const B = '/api/v1/mailbox';
const enc = encodeURIComponent;
const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export type View = 'mine' | 'unit' | 'unassigned' | 'unsure' | 'overdue' | 'archive';
export const VIEW_ORDER: View[] = ['mine', 'unit', 'unassigned', 'unsure', 'overdue', 'archive'];
export type Status = 'yeni' | 'atandi' | 'yanitlandi' | 'kapandi' | 'arsiv';
export type Priority = 'yuksek' | 'normal' | 'dusuk';
export type Role = 'basvuru' | 'ik' | 'spam' | null;

export type Connection = {
  provider: string;
  providerLabel: string;
  mailbox: string | null;
  connected: boolean;
  reason: string | null;
  identity: string | null;
  scopes: string[];
  authMode?: string;
  authLabel?: string;
};

export type LastRun = {
  at?: string;
  ok?: boolean;
  error?: string;
  notConnected?: boolean;
  read?: number;
  new?: number;
  classified?: number;
  replies?: number;
  remaining?: number;
  warnings?: string[];
  llmError?: string;
} | null;

export type Meta = {
  statuses: Record<Status, string>;
  views: Record<View, string>;
  priorities: Record<Priority, string>;
  roles: Record<string, string>;
  events: Record<string, string>;
  transitions: Record<Status, Status[]>;
  connection: Connection;
  lastRun: LastRun;
  settings: { businessHours: string; startDate: string | null; thresholds: Record<string, number>; autoAssign: string[] };
  me: { username: string; display: string; admin: boolean; seeAll: boolean; hr: boolean; canAssign: boolean; canRules: boolean; canApprove: boolean };
};

export type Category = { key: string; label: string; description: string | null; enabled: boolean; role: Role; hrOnly: boolean; autoReply: boolean; sort: number };

export type Overview = {
  counts: Record<View | 'today' | 'pending' | 'historical', number>;
  units: string[];
  categories: Category[];
  rulesVersion: number | null;
};

export type CrmMatch = { id: string; ad: string | null; proje?: number; coklu?: boolean };
export type Attachment = { name: string; size: number; mime: string };

export type Message = {
  id: string;
  receivedAt: string;
  fromName: string | null;
  fromMasked: string | null;
  subject: string | null;
  summary: string | null;
  category: string | null;
  categoryLabel: string | null;
  categoryProb: number | null;
  categoryMargin: number | null;
  categorySource: 'model' | 'kural' | 'insan' | null;
  categoryMethod: string | null;
  unsure: boolean;
  classified: boolean;
  priority: Priority | null;
  priorityProb: number | null;
  status: Status;
  statusLabel: string;
  assignee: string | null;
  unit: string | null;
  suggestedAssignee: string | null;
  suggestedUnit: string | null;
  dueAt: string | null;
  remainingH: number | null;
  overdue: boolean;
  firstReplyAt: string | null;
  closedAt: string | null;
  isHr: boolean;
  historical: boolean;
  crm: { kisi?: CrmMatch; firma?: CrmMatch; aday?: CrmMatch };
  attachments: Attachment[];
  orderRefs: string[];
  boxLabels: string[];
};

export type Application = {
  messageId: string;
  authorName: string | null;
  workTitle: string | null;
  genre: string | null;
  pageEstimate: number | null;
  attachments: Attachment[];
  status: 'yeni' | 'aktarildi' | 'reddedildi';
  intakeRef: string | null;
  intakeNo: string | null;
  crmProjectId: string | null;
  dropped: string[];
};

export type MailEvent = { action: string; label: string; by: string; at: string; detail: Record<string, unknown> | null };
export type Template = { id: string; category: string; name: string; body: string };

export type MessageDetail = Message & {
  events: MailEvent[];
  previous: Array<{ id: string; receivedAt: string; subject: string | null; category: string | null; status: string }>;
  application: Application | null;
  role: Role;
  templates: Template[];
  link: string | null;
  body: string | null;
  fromAddress: string | null;
  bodyError: string | null;
  provider: string;
};

export type ListResult = { view: View; items: Message[]; total: number; page: number; pageSize: number; counts: Record<View, number>; units: string[] };

export type Ruleset = {
  version: number;
  status: 'taslak' | 'onayli' | 'arsiv';
  note: string | null;
  createdBy: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  categories: Category[];
  routes: Array<{ category: string; unit: string | null; primary: string | null; backup: string | null; manager: string | null }>;
  sla: Array<{ category: string; remindH: number; escalateH: number; topH: number }>;
  templates: Template[];
};

export type RulesView = {
  active: Ruleset | null;
  draft: Ruleset | null;
  history: Array<{ version: number; status: string; approvedBy: string | null; approvedAt: string | null; createdBy: string; note: string | null }>;
  roles: Record<string, string>;
  businessHours: string;
  defaultSla: { remindH: number; escalateH: number; topH: number };
};

export type ReportCategory = {
  category: string;
  label: string;
  n: number;
  replied: number;
  closed: number;
  open: number;
  overdue: number;
  slaMet: number;
  slaDue: number;
  spam: boolean;
  avgFirstReplyH: number | null;
  avgFirstReplyBizH: number | null;
  avgCloseBizH: number | null;
  slaRate: number | null;
};

export type Report = {
  start: string;
  end: string;
  total: number;
  replied: number;
  slaRate: number | null;
  unsureRate: number | null;
  correctedRate: number | null;
  categories: ReportCategory[];
  people: Array<{ unit: string | null; assignee: string | null; n: number; open: number; replied: number; overdue: number }>;
  weekly: Array<{ week: string; n: number }>;
  businessHours: string;
};

export type Accuracy = {
  n: number;
  agree: number;
  rate: number | null;
  unscored: number;
  labeled: number;
  target: number;
  byCategory: Array<{ category: string; label: string; n: number; agree: number; rate: number }>;
  confusion: Array<{ human: string; humanLabel: string; model: string; modelLabel: string; n: number }>;
};

export type Labeling = {
  items: Array<{ id: string; receivedAt: string; subject: string | null; fromName: string | null; fromMasked: string | null; historical: boolean; attachments: string[] }>;
  total: number;
  page: number;
  pageSize: number;
  labeledByMe: number;
  accuracy: Accuracy;
};

export type IntakeInput = { title: string; authorName: string; summary: string; authorBio: string; pageEstimate: number | null; genre: string };

export const mailApi = {
  meta: () => send<Meta>('GET', `${B}/meta`),
  overview: () => send<Overview>('GET', `${B}/overview`),
  badge: () => send<{ mine: number; overdue: number }>('GET', `${B}/badge`),
  messages: (o: { view: View; q?: string; category?: string; page?: number }) =>
    send<ListResult>('GET', `${B}/messages${qs({ view: o.view, q: o.q, category: o.category, page: o.page || undefined })}`),
  message: (id: string) => send<MessageDetail>('GET', `${B}/messages/${enc(id)}`, undefined, 60_000),
  assign: (id: string, assignee: string | null, unit?: string | null) =>
    send<{ assignee: string | null; unit: string | null; status: Status }>('POST', `${B}/messages/${enc(id)}/assign`, { assignee, unit }),
  category: (id: string, category: string) => send<{ category: string }>('POST', `${B}/messages/${enc(id)}/category`, { category }),
  status: (id: string, status: Status, note?: string) => send<{ status: Status }>('POST', `${B}/messages/${enc(id)}/status`, { status, note }),
  draft: (id: string) => send<{ text: string; template: Template | null; link: string | null }>('POST', `${B}/messages/${enc(id)}/draft`, undefined, 180_000),
  application: (id: string, body: Partial<Pick<Application, 'authorName' | 'workTitle' | 'genre' | 'pageEstimate' | 'status'>>) =>
    send<Application>('POST', `${B}/messages/${enc(id)}/application`, body),
  toIntake: (id: string, body: IntakeInput) =>
    send<{ ok: boolean; intake: { id: string; no: string }; files: string[]; skipped: string[] }>('POST', `${B}/messages/${enc(id)}/to-intake`, body, 180_000),
  toHr: (id: string) => send<{ ok: boolean }>('POST', `${B}/messages/${enc(id)}/to-hr`),
  report: (start?: string, end?: string) => send<Report>('GET', `${B}/report${qs({ start, end })}`),
  rules: () => send<RulesView>('GET', `${B}/rules`),
  saveRules: (body: RulesBody) => send<Ruleset>('PUT', `${B}/rules`, body),
  discardDraft: () => send<{ ok: boolean }>('DELETE', `${B}/rules/draft`),
  approveRules: (version: number) => send<Ruleset>('POST', `${B}/rules/approve`, { version }),
  labeling: (page = 0) => send<Labeling>('GET', `${B}/labeling${qs({ page: page || undefined })}`),
  label: (id: string, category: string) => send<{ category: string }>('POST', `${B}/labeling/${enc(id)}`, { category }),
  connection: () => send<Connection & { lastRun: LastRun; lastOkAt: string | null; startAt: string | null }>('GET', `${B}/connection`),
  testConnection: () => send<{ ok: boolean; message: string; ms: number }>('POST', `${B}/connection/test`),
  applications: (status = 'yeni') => send<{ items: Array<Application & { receivedAt: string; fromName: string | null; fromMasked: string | null; subject: string | null; summary: string | null }>; total: number }>('GET', `${B}/applications${qs({ status })}`),
};

export type RulesBody = {
  note?: string | null;
  categories: Array<Pick<Category, 'key' | 'label' | 'description' | 'enabled' | 'role'>>;
  routes: Ruleset['routes'];
  sla: Ruleset['sla'];
  templates: Array<Pick<Template, 'category' | 'name' | 'body'>>;
};

/** Ekrandaki kural düzenini sunucunun beklediği gövdeye çevirir; boş yönlendirme satırı gitmez. */
export function toRulesBody(r: Pick<Ruleset, 'note' | 'categories' | 'routes' | 'sla' | 'templates'>): RulesBody {
  const blank = (s: string | null | undefined) => !s || !s.trim();
  return {
    note: r.note,
    categories: r.categories.map(({ key, label, description, enabled, role }) => ({ key: key.trim().toLowerCase(), label: label.trim(), description, enabled, role })),
    routes: r.routes
      .filter((x) => !(blank(x.unit) && blank(x.primary) && blank(x.backup) && blank(x.manager)))
      .map((x) => ({ category: x.category, unit: x.unit?.trim() || null, primary: x.primary?.trim().toLowerCase() || null, backup: x.backup?.trim().toLowerCase() || null, manager: x.manager?.trim().toLowerCase() || null })),
    sla: r.sla,
    templates: r.templates.filter((t) => t.name.trim() && t.body.trim()).map(({ category, name, body }) => ({ category, name: name.trim(), body })),
  };
}

// ------------------------------------------------------------------ biçim

const nf1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
export const fmtInt = (n: number | null | undefined) => (n === null || n === undefined ? '—' : new Intl.NumberFormat('tr-TR').format(n));

/** Olasılık yüzdesi: 0.934 → «%93». Olasılık yoksa (düz metin yedek yolu) «olasılık yok». */
export const probText = (p: number | null | undefined) => (p === null || p === undefined ? 'olasılık yok' : `%${Math.round(p * 100)}`);

/** SLA'ya kalan iş saati: pozitif «6 sa kaldı», negatif «3,5 sa geçti», null boş. */
export function remainingText(h: number | null | undefined): string | null {
  if (h === null || h === undefined) return null;
  if (Math.abs(h) < 0.05) return 'süre doldu';
  return h > 0 ? `${nf1.format(h)} iş saati kaldı` : `${nf1.format(-h)} iş saati geçti`;
}

export const hoursText = (h: number | null | undefined) => (h === null || h === undefined ? '—' : `${nf1.format(h)} sa`);
export const pctText = (r: number | null | undefined) => (r === null || r === undefined ? '—' : `%${nf1.format(r * 100)}`);

const dtf = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
const df = new Intl.DateTimeFormat('tr-TR', { timeZone: 'Europe/Istanbul', day: 'numeric', month: 'long', year: 'numeric' });
export const fmtWhen = (iso: string | null | undefined) => (iso ? dtf.format(new Date(iso)) : '—');
export const fmtDay = (iso: string | null | undefined) => (iso ? df.format(new Date(iso.length === 10 ? `${iso}T12:00:00` : iso)) : '—');

export const fmtSize = (b: number) => (b >= 1_048_576 ? `${nf1.format(b / 1_048_576)} MB` : b >= 1024 ? `${Math.round(b / 1024)} kB` : `${b} B`);

/** Gönderenin ekrandaki adı: başlıktaki ad, yoksa maskeli adres. */
export const senderText = (m: Pick<Message, 'fromName' | 'fromMasked'>) => m.fromName || m.fromMasked || 'Bilinmeyen gönderen';

/** CRM rozeti: kişi (olası yazar), firma, aday. Birden çok kayıt eşleştiyse belirtilir. */
export function crmBadges(crm: Message['crm']): Array<{ key: string; text: string }> {
  const out: Array<{ key: string; text: string }> = [];
  if (crm.kisi) out.push({ key: 'kisi', text: (crm.kisi.proje ? 'Yazar adayı' : 'CRM kişisi') + (crm.kisi.coklu ? ' (birden çok kayıt)' : '') });
  if (crm.firma) out.push({ key: 'firma', text: 'Bayi / kurum' + (crm.firma.coklu ? ' (birden çok kayıt)' : '') });
  if (crm.aday) out.push({ key: 'aday', text: 'CRM adayı' });
  return out;
}

export const PRIORITY_TONE: Record<Priority, string> = {
  yuksek: 'bg-red-50 text-red-700',
  normal: 'bg-slate-100 text-canvas-ink',
  dusuk: 'bg-slate-50 text-canvas-muted',
};

export const STATUS_TONE: Record<Status, string> = {
  yeni: 'bg-canvas-violet/10 text-canvas-violet',
  atandi: 'bg-amber-50 text-amber-800',
  yanitlandi: 'bg-emerald-50 text-emerald-700',
  kapandi: 'bg-slate-100 text-canvas-ink',
  arsiv: 'bg-slate-50 text-canvas-muted',
};

/** «Son okuma» satırı: kutu bağlı değilse nedeni, hata varsa hatayı, yoksa zamanı ve sayıları söyler. */
export function lastRunText(c: Connection | undefined, r: LastRun): string {
  if (!c) return 'Durum okunuyor';
  if (!c.connected) return `Kutu bağlı değil: ${c.reason ?? 'ayar eksik'}`;
  if (!r?.at) return 'Kutu henüz okunmadı';
  if (r.ok === false) return `Son okuma başarısız (${fmtWhen(r.at)}): ${r.error ?? '?'}`;
  return `Son okuma ${fmtWhen(r.at)} · ${fmtInt(r.new ?? 0)} yeni ileti`;
}
