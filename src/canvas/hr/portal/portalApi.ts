import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError } from '../../engine';
import { httpErrorText } from '../../httpError';
import { hrDownload, hrSend, qs, type WithK } from '../hrApi';

/** İK personel portalı uçları (köprü `hr_portal_api.py`): çalışan `/api/v1/hr/portal/*`, İK yönetimi `…/portal/admin/*`. */

const B = '/portal';
const AD = '/portal/admin';
const enc = encodeURIComponent;

export type FieldType = 'text' | 'long_text' | 'enum' | 'date' | 'email' | 'phone' | 'number' | 'file';

export type PersonField = {
  key: string; label: string; type: FieldType; options: string[]; required: boolean;
  showAdmin: boolean; showProfile: boolean; showDirectory: boolean; group: string; sensitive: boolean; sort: number;
  builtin: boolean; active: boolean; updatedBy: string | null; updatedAt: string | null;
};

export type PortalRights = { view: boolean; edit: boolean; sensitive: boolean; portal: boolean; fields: boolean; leave: boolean; leaveSettings: boolean };

export type PortalSettings = {
  docTypes: string[]; postCategories: string[]; docCategories: string[]; faqCategories: string[]; expiryDays: number;
};

export type PortalMeta = {
  me: { username: string; display: string; isAdmin: boolean };
  rights: PortalRights;
  settings: PortalSettings;
  groups: Record<string, string>;
  fieldTypes: Record<FieldType, string>;
  requestStatus: Record<string, string>;
  delivery: Record<string, string>;
  peopleStatus: string[];
  fileMaxMb: number;
  fileAccept: string;
  imageAccept: string;
  mail: { mode: string; modes: Record<string, string>; domains: string[]; linkSet: boolean; hrRecipients: number };
};

export type MailRow = {
  id: number; event: string; refType: string | null; refId: string | null; recipient: string | null; subject: string; body: string;
  state: string; stateLabel: string; tries: number; error: string | null; createdAt: string; sentAt: string | null;
};

export type Value = string | number | null | undefined;

export type PersonFile = { id: string; field: string; filename: string; mime: string | null; size: number; uploadedBy: string | null; uploadedAt: string | null };

export type PersonRow = {
  id: string; idNo: string; adSoyad: string; durum: string; username: string | null;
  data: Record<string, Value>; missing: string[]; hasPhoto: boolean; updatedAt: string | null;
};

export type Person = {
  id: string; idNo: string; adSoyad: string; durum: string; username: string | null;
  data: Record<string, Value>; files: PersonFile[]; updatedBy: string | null; updatedAt: string | null; createdAt: string | null;
};

export type Birthday = { id: string; adSoyad: string; departman: string | null; unvan: string | null; day: number; month: number; inDays: number };

export type Post = {
  id: string; category: string; title: string; body: string; publishDate: string; hasImage: boolean; active: boolean;
  createdBy: string | null; updatedAt: string | null;
};

export type MenuDay = { day: string; items: string[]; updatedBy?: string | null };

export type HrDoc = { id: string; category: string; code: string | null; title: string; filename: string; mime: string | null; size: number; uploadedBy: string | null; uploadedAt: string | null };

export type DocRequest = {
  id: string; username: string; display: string | null; mail: string | null; docType: string; delivery: string; deliveryLabel: string;
  note: string | null; status: string; statusLabel: string; answer: string | null; createdAt: string; handledBy: string | null; handledAt: string | null;
  files?: { id: string; filename: string; size: number }[];
};

export type Faq = { id: string; category: string; question: string; answer: string; sort: number; updatedBy: string | null; updatedAt: string | null };

export type CountRow = { label: string; value: number };

export type Stats = {
  today: string;
  headcount: { active: number; passive: number; total: number };
  joined: { month: number; year: number };
  left: { month: number; year: number; turnoverYearPct: number };
  avgTenureYears: number | null;
  avgAgeYears: number | null;
  by: Partial<Record<'firma' | 'sube' | 'ofis_lokasyon' | 'departman' | 'calisma_sekli' | 'cinsiyet', CountRow[]>>;
  upcoming: { id: string; adSoyad: string; what: string; date: string; inDays: number }[];
  anniversaries: { id: string; adSoyad: string; years: number; day: number }[];
  expiryDays: number;
  completeness: { activeMissingRequired: number; docs: { key: string; label: string; missing: number }[] };
  pendingRequests: number;
} & WithK;

export type Home = {
  me: { display: string; username: string; linked: boolean; unvan: string | null; departman: string | null; hasPhoto: boolean };
  rights: PortalRights;
  /** Açabildiği `sayfa:ik-*` anahtarları; yöneticide ['*']. */
  pages: string[];
  birthdays: Birthday[];
  posts: Post[];
  menuToday: MenuDay | null;
  myOpenRequests: number;
  stats?: Stats;
  onLeave: { id: string; adSoyad: string; departman: string | null; back: string }[];
  leave: { available: number | null; teamWaiting: number };
  leaveStats?: { onLeaveToday: number; waiting: number; highBalance: { id: string; adSoyad: string; balance: number }[]; accrualSoon: { id: string; adSoyad: string; date: string; days: number }[] };
};

export type Profile = { person: Person | null; fields: PersonField[]; groups: Record<string, string>; manager?: string | null };

export type Directory = { items: { id: string; adSoyad: string; data: Record<string, Value>; hasPhoto: boolean }[]; fields: PersonField[]; total: number; onLeave: Record<string, string> };

export type ImportResult = {
  sheet: string; columns: string[]; ignoredColumns: string[];
  counts: { new: number; update: number; same: number; error: number };
  rows: { row: number; idNo: string; adSoyad: string | null; kind: 'new' | 'update' | 'same' | 'error'; errors: string[]; changed: string[] }[];
  applied: number;
};

async function fail(res: Response): Promise<never> {
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

/** Ham gövdeyle dosya gönderimi (aday dosyası yüklemesiyle aynı biçim: `?filename=` + octet-stream). */
async function sendFile<T>(path: string, file: File, extra: Record<string, string | number | undefined> = {}): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}/api/v1/hr${path}${qs({ filename: file.name, ...extra })}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
    signal: AbortSignal.timeout(300_000),
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

/** Görsel/fotoğraf adresi: `<img>` çerezle aynı kökten yükler. */
export const portalSrc = (path: string) => `${ENGINE_BASE}/api/v1/hr${path}`;

export const portalApi = {
  meta: () => hrSend<PortalMeta>('GET', `${B}/meta`),
  home: () => hrSend<Home>('GET', `${B}/home`),
  me: () => hrSend<Profile>('GET', `${B}/me`),
  myFile: (f: PersonFile) => hrDownload(`${B}/me/files/${enc(f.id)}`, f.filename),
  directory: () => hrSend<Directory>('GET', `${B}/directory`),
  birthdays: () => hrSend<{ today: string; items: Birthday[]; thisMonth: Birthday[]; upcoming: Birthday[] }>('GET', `${B}/birthdays`),
  posts: () => hrSend<{ items: Post[] }>('GET', `${B}/posts`),
  menu: (start?: string, end?: string) => hrSend<{ start: string; end: string; days: MenuDay[] }>('GET', `${B}/menu${qs({ start, end })}`),
  docs: () => hrSend<{ items: HrDoc[] }>('GET', `${B}/docs`),
  docFile: (d: HrDoc) => hrDownload(`${B}/docs/${enc(d.id)}/file`, d.filename),
  myRequests: () => hrSend<{ items: DocRequest[]; defaultMail: string | null }>('GET', `${B}/requests/mine`),
  createRequest: (body: { docType: string; delivery: string; mail?: string; note?: string }) => hrSend<DocRequest>('POST', `${B}/requests`, body),
  cancelRequest: (id: string) => hrSend<{ ok: boolean }>('DELETE', `${B}/requests/${enc(id)}`),
  faq: () => hrSend<{ items: Faq[] }>('GET', `${B}/faq`),
  requestFile: (rid: string, f: { id: string; filename: string }) => hrDownload(`${B}/requests/${enc(rid)}/files/${enc(f.id)}`, f.filename),
  mailPref: () => hrSend<{ off: boolean; mode: string }>('GET', `${B}/me/mail-pref`),
  setMailPref: (off: boolean) => hrSend<{ off: boolean }>('PUT', `${B}/me/mail-pref`, { off }),

  // İK yönetimi
  people: (p: { q?: string; durum?: string; firma?: string; departman?: string; ofis_lokasyon?: string }) =>
    hrSend<{ items: PersonRow[]; total: number }>('GET', `${AD}/people${qs(p)}`),
  person: (id: string) => hrSend<Person>('GET', `${AD}/people/${enc(id)}`),
  createPerson: (body: { data: Record<string, Value>; username?: string | null }) => hrSend<Person>('POST', `${AD}/people`, body),
  updatePerson: (id: string, body: { data: Record<string, Value>; username?: string | null }) => hrSend<Person>('PATCH', `${AD}/people/${enc(id)}`, body),
  deletePerson: (id: string) => hrSend<{ ok: boolean; files: number; archiveId: string }>('DELETE', `${AD}/people/${enc(id)}`),
  uploadPersonFile: (id: string, field: string, file: File) => sendFile<PersonFile>(`${AD}/people/${enc(id)}/files/${enc(field)}`, file),
  personFile: (id: string, f: PersonFile) => hrDownload(`${AD}/people/${enc(id)}/files/${enc(f.id)}`, f.filename),
  deletePersonFile: (id: string, fid: string) => hrSend<{ ok: boolean }>('DELETE', `${AD}/people/${enc(id)}/files/${enc(fid)}`),
  importXlsx: (file: File, apply: boolean) => sendFile<ImportResult>(`${AD}/import`, file, { apply: apply ? 1 : 0 }),
  exportXlsx: (durum = 'hepsi') => hrDownload(`${AD}/export${qs({ durum })}`, 'personel.xlsx'),
  templateXlsx: () => hrDownload(`${AD}/template`, 'personel-sablon.xlsx'),

  fields: () => hrSend<{ items: PersonField[] }>('GET', `${AD}/fields`),
  createField: (body: Partial<PersonField>) => hrSend<PersonField>('POST', `${AD}/fields`, body),
  updateField: (key: string, body: Partial<PersonField>) => hrSend<PersonField>('PATCH', `${AD}/fields/${enc(key)}`, body),
  deleteField: (key: string) => hrSend<{ ok: boolean; cleared: number }>('DELETE', `${AD}/fields/${enc(key)}`),
  saveSettings: (body: Partial<PortalSettings>) => hrSend<PortalSettings>('PUT', `${AD}/settings`, body),

  adminPosts: () => hrSend<{ items: Post[] }>('GET', `${AD}/posts`),
  createPost: (body: Partial<Post>) => hrSend<Post>('POST', `${AD}/posts`, body),
  updatePost: (id: string, body: Partial<Post>) => hrSend<Post>('PATCH', `${AD}/posts/${enc(id)}`, body),
  deletePost: (id: string) => hrSend<{ ok: boolean }>('DELETE', `${AD}/posts/${enc(id)}`),
  uploadPostImage: (id: string, file: File) => sendFile<Post>(`${AD}/posts/${enc(id)}/image`, file),
  deletePostImage: (id: string) => hrSend<Post>('DELETE', `${AD}/posts/${enc(id)}/image`),

  addDoc: (file: File, meta: { title: string; category: string; code?: string }) => sendFile<HrDoc>(`${AD}/docs`, file, meta),
  deleteDoc: (id: string) => hrSend<{ ok: boolean }>('DELETE', `${AD}/docs/${enc(id)}`),

  adminRequests: (status = 'acik') => hrSend<{ items: DocRequest[]; total: number }>('GET', `${AD}/requests${qs({ status })}`),
  handleRequest: (id: string, body: { status: string; answer?: string }) => hrSend<DocRequest>('PATCH', `${AD}/requests/${enc(id)}`, body),
  uploadRequestFile: (id: string, file: File) => sendFile<{ id: string; filename: string; size: number }>(`${AD}/requests/${enc(id)}/files`, file),
  adminRequestFile: (id: string, f: { id: string; filename: string }) => hrDownload(`${AD}/requests/${enc(id)}/files/${enc(f.id)}`, f.filename),
  deleteRequestFile: (id: string, fid: string) => hrSend<{ ok: boolean }>('DELETE', `${AD}/requests/${enc(id)}/files/${enc(fid)}`),
  mail: (before?: number) => hrSend<{ items: MailRow[]; hasMore: boolean; waiting: number; failed24h: number }>('GET', `${AD}/mail${qs({ before })}`),

  saveMenu: (days: MenuDay[]) => hrSend<{ ok: boolean; days: number }>('PUT', `${AD}/menu`, { days }),

  createFaq: (body: Partial<Faq>) => hrSend<Faq>('POST', `${AD}/faq`, body),
  updateFaq: (id: string, body: Partial<Faq>) => hrSend<Faq>('PATCH', `${AD}/faq/${enc(id)}`, body),
  deleteFaq: (id: string) => hrSend<{ ok: boolean }>('DELETE', `${AD}/faq/${enc(id)}`),
};

/* ------------------------------------------------------------------ biçim */

const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];
export const monthName = (m: number) => MONTHS[m - 1] ?? '';
export const dayMonth = (d: number, m: number) => `${d} ${monthName(m)}`;

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' });
const weekdayFmt = new Intl.DateTimeFormat('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' });
/** «2026-09-29» → «29 Eylül 2026» (saat dilimi kaydırmadan). */
export const longDay = (iso: string | null | undefined) => {
  if (!iso) return '—';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return dayFmt.format(new Date(y, m - 1, d));
};
export const weekday = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  return weekdayFmt.format(new Date(y, m - 1, d));
};
/** Yerel gün («YYYY-AA-GG»), UTC'ye kaymadan. */
export const localIso = (dt: Date) =>
  `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;

/** Alan değerinin ekrandaki yazımı. */
export function showValue(f: PersonField | undefined, v: Value): string {
  if (v === null || v === undefined || v === '') return '—';
  if (f?.type === 'date') return longDay(String(v));
  if (f?.key === 'banka_iban_no') return String(v).replace(/(.{4})/g, '$1 ').trim();
  return String(v);
}

export const fileSize = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

export const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toLocaleUpperCase('tr-TR'))
    .join('');
