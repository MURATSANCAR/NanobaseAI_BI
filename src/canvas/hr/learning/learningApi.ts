import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError } from '../../engine';
import { httpErrorText } from '../../httpError';
import { hrDownload, hrSend, qs, type Job } from '../hrApi';

/** M57 Eğitim ve gelişim uçları (/api/v1/hr/learning/*, /api/v1/hr/visit). İstemci İK-0'ın `hrSend`'ini kullanır. */

const L = '/learning';
const enc = encodeURIComponent;

export type Kind = 'zorunlu' | 'gelisim' | 'zeki';
export type Delivery = 'ic' | 'dis' | 'cevrimici';
export type SessionState = 'planli' | 'yapildi' | 'iptal';
export type Approval = 'bekliyor' | 'yonetici_onayladi' | 'onaylandi' | 'reddedildi';
export type Attendance = 'katildi' | 'gelmedi';
export type Status = 'hic_yok' | 'doldu' | 'dolacak' | 'gecerli';
export type Priority = 'yuksek' | 'orta' | 'dusuk';
export type NeedState = 'acik' | 'onaylandi' | 'reddedildi' | 'karsilandi';

export type Can = { manage: boolean; approve: boolean; budget: boolean; usage: boolean; guides: boolean; export: boolean; page: boolean };

export type Course = {
  id: string; title: string; kind: Kind; kindLabel: string; delivery: Delivery; deliveryLabel: string;
  durationHours: number | null; validityDays: number | null; costPerPerson: number | null; provider: string;
  moduleRoute: string | null; requiredUnits: string[]; requiredUnitNames: string[]; description: string; active: boolean;
  updatedBy: string | null; updatedAt: string | null;
};
export type EmpBrief = { id: string; displayName: string; unitId: string | null; unitName: string | null; title: string; status: string };
export type Enrollment = {
  id: string; sessionId: string; employeeId: string; employee: EmpBrief | null; approval: Approval; approvalLabel: string;
  requestedBy: string | null; requestedAt: string | null; approvedBy: string | null; approvedAt: string | null;
  hrApprovedBy: string | null; hrApprovedAt: string | null; decisionNote: string; attendance: Attendance | null;
  attendanceLabel: string | null; completedAt: string | null;
};
export type SessionCounts = { approved: number; pending: number; attended: number; absent: number; completed: number };
export type Session = {
  id: string; courseId: string; courseTitle: string; courseKind: Kind | null; delivery: Delivery | null; startsAt: string;
  endsAt: string | null; location: string; roomBookingId: string | null; trainer: string; capacity: number | null;
  state: SessionState; stateLabel: string; closedAt: string | null; closedBy: string | null; counts: SessionCounts;
};
export type SessionDetail = Session & { course: Course | null; enrollments?: Enrollment[]; feedback: { invited: number; answered: number } };
export type StatusRow = {
  employeeId: string; displayName: string; unitId: string | null; unitName: string | null; courseId: string; courseTitle: string;
  issuedOn: string | null; expiresOn: string | null; status: Status; statusLabel: string; daysLeft: number | null;
  plannedAt: string | null; plannedSessionId: string | null;
};
export type Certificate = {
  id: string; employeeId: string; courseId: string | null; title: string; courseKind: Kind | null; source: string; sourceLabel: string;
  issuedOn: string | null; expiresOn: string | null; hasFile: boolean; fileName: string | null; fileSize: number | null;
  verified: boolean; verifiedBy: string | null; verifiedAt: string | null; createdAt: string | null; employee?: EmpBrief | null;
};
export type Need = {
  id: string; source: string; sourceLabel: string; text?: string; suggestedCourseId: string | null; suggestedCourseTitle: string | null;
  suggestionReason: string; suggestion: { egitim?: number | null; oncelik?: number | null; method?: string } | null;
  priority: Priority | null; priorityLabel: string | null; state: NeedState; stateLabel: string; courseId: string | null;
  courseTitle: string | null; decidedBy: string | null; decidedAt: string | null; decisionNote: string; createdAt: string | null;
  unitId: string | null; employee?: EmpBrief | null; unitName?: string | null;
};
export type NeedSummary = { courseId: string | null; courseTitle: string; total: number; yuksek: number; orta: number; dusuk: number; belirsiz: number };
export type Question = { key: string; label: string };

export type Info = {
  kinds: Record<Kind, string>; delivery: Record<Delivery, string>; sessionStates: Record<SessionState, string>;
  approval: Record<Approval, string>; attendance: Record<Attendance, string>; needSources: Record<string, string>;
  needStates: Record<NeedState, string>; priorities: Record<Priority, string>; guideStates: Record<string, string>;
  status: Record<Status, string>; questions: Question[]; themes: string[]; alertDays: number | null; minGroup: number | null;
  accountsConfigured: boolean; accountsError: boolean; modelVar: boolean; can: Can; me: { username: string; display: string };
};

export type Dashboard = {
  counters: {
    overdue: number; never: number; expiring: number | null; alertDays: number | null; sessionsThisMonth: number; awaitingClose: number;
    completionRate: number | null; enrolled: number; completed: number; pendingFeedback: number; pendingApprovals: number;
    unverifiedCertificates: number; openNeeds: number;
  };
  matrix: { unitId: string | null; unitName: string; courseId: string; courseTitle: string; enrolled: number; completed: number; rate: number | null }[];
  attentionByUnit: { unitId: string | null; unitName: string; doldu: number; hic_yok: number; dolacak: number }[];
  attention?: StatusRow[];
};

export type MyEnrollment = {
  id: string; sessionId: string; courseId: string; courseTitle: string; startsAt: string; endsAt: string | null; location: string;
  trainer: string; sessionState: SessionState; approval: Approval; approvalLabel: string; attendance: Attendance | null; completedAt: string | null;
};
export type Me = {
  employee: { id: string; displayName: string; unitName: string | null } | null;
  enrollments: MyEnrollment[]; certificates: Certificate[]; mandatory: StatusRow[];
  feedback: { token: string; sessionId: string; startsAt: string; courseTitle: string }[];
  openSessions: { id: string; courseId: string; courseTitle: string; delivery: Delivery | null; startsAt: string; location: string }[];
  needs: Need[]; can: Can; alertDays: number | null; questions: Question[];
  catalog: { id: string; title: string; kind: Kind; validityDays: number | null }[]; fileMaxMb: number;
};
export type Team = {
  managerKnown: boolean;
  members: (EmpBrief & { completed: number; overdue: number; expiring: number })[];
  pending: (Enrollment & { courseTitle: string; delivery: Delivery | null; startsAt: string })[];
  mandatory: StatusRow[];
};
export type MyUsage = {
  days: number; since: string; screens: { key: string; days: number; visits: number }[]; questions: number;
  actions: { key: string; label: string | null; count: number }[];
};
export type UsageMap = {
  days: number; since: string; minGroup: number | null; modules: { key: string; label: string | null }[];
  totals: Record<string, number>; rows: { key: string; unitId: string | null; unitName: string; employees: number | null; cells: Record<string, number>; merged: boolean }[];
  smallUnits: number; note: string | null;
};
export type Guide = {
  id: string; moduleRoute: string; title: string; body: string; version: number; state: 'taslak' | 'yayinda'; stateLabel: string;
  published: boolean; dirty: boolean; modelDrafted: boolean; approvedBy: string | null; approvedAt: string | null;
  updatedBy: string | null; updatedAt: string | null; votes: { useful: number; notUseful: number };
};
export type GuideRead = { id: string; moduleRoute: string; title: string; body: string; version: number; approvedAt: string | null; myVote: boolean | null };
export type GuideIndex = { id: string; moduleRoute: string; title: string; version: number };
export type FeedbackSummary = {
  responses: number; invited: number; minGroup: number | null; hidden: boolean; questions: Question[];
  averages: Record<string, { avg: number; n: number }>; comments: string[];
  themes: { themes: { theme: string; count: number; summary: string }[]; at: string } | null;
};
export type Spend = {
  year: number; configured: boolean; firm?: string; total: number | null; months: { month: number; amount: number }[];
  accounts: { code: string; name: string; amount: number }[]; dataEnd: string | null;
  budget: { year: number; amount: number; note: string; updatedBy: string | null; updatedAt: string | null } | null;
  ratio: number | null; accountCodes: string[];
};

async function upload<T>(path: string, file: File, params: Record<string, string>): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}/api/v1/hr${path}${qs({ ...params, filename: file.name })}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
    signal: AbortSignal.timeout(300_000),
  });
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    if (res.status === 401) throw new EngineAuthError();
    if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

export const learningApi = {
  // kişinin kendisi
  me: () => hrSend<Me>('GET', `${L}/me`),
  myUsage: (days = 30) => hrSend<MyUsage>('GET', `${L}/me/usage${qs({ days })}`),
  uploadCertificate: (file: File, meta: { courseId?: string; title?: string; issuedOn?: string; expiresOn?: string }) =>
    upload<Certificate>(`${L}/me/certificates`, file, {
      courseId: meta.courseId ?? '', title: meta.title ?? '', issuedOn: meta.issuedOn ?? '', expiresOn: meta.expiresOn ?? '',
    }),
  myCertificateFile: (id: string, name: string) => hrDownload(`${L}/me/certificates/${enc(id)}/file`, name),
  deleteMyCertificate: (id: string) => hrSend<{ ok: boolean }>('DELETE', `${L}/me/certificates/${enc(id)}`),
  requestSeat: (sessionId: string) => hrSend<{ added: number }>('POST', `${L}/me/enroll/${enc(sessionId)}`),
  withdrawRequest: (enrollmentId: string) => hrSend<{ ok: boolean }>('DELETE', `${L}/me/enrollments/${enc(enrollmentId)}`),
  myNeed: (text: string) => hrSend<Need>('POST', `${L}/me/needs`, { text }),
  feedbackForm: (token: string) => hrSend<{ used: boolean; courseTitle: string; startsAt: string | null; questions: Question[]; note: string }>('GET', `${L}/me/feedback/${enc(token)}`),
  submitFeedback: (token: string, body: { answers: Record<string, number>; comment: string }) => hrSend<{ ok: boolean }>('POST', `${L}/me/feedback/${enc(token)}`, body),
  team: () => hrSend<Team>('GET', `${L}/me/team`),
  teamDecide: (id: string, action: 'onayla' | 'reddet', note = '') => hrSend<Enrollment>('POST', `${L}/me/team/enrollments/${enc(id)}/decide`, { action, note }),
  teamNeed: (employeeId: string, text: string) => hrSend<Need>('POST', `${L}/me/team/needs`, { employeeId, text }),
  guideIndex: () => hrSend<{ items: GuideIndex[] }>('GET', `${L}/me/guides`),
  readGuide: (id: string) => hrSend<GuideRead>('GET', `${L}/me/guides/${enc(id)}`),
  voteGuide: (id: string, useful: boolean) => hrSend<{ ok: boolean }>('POST', `${L}/me/guides/${enc(id)}/vote`, { useful }),

  // İK
  info: () => hrSend<Info>('GET', `${L}/info`),
  dashboard: () => hrSend<Dashboard>('GET', `${L}/dashboard`),
  expiring: (days?: number) => hrSend<{ days: number | null; items: StatusRow[]; total: number }>('GET', `${L}/expiring${qs({ days })}`),
  exportExpiring: (days?: number) => hrDownload(`${L}/export/expiring.csv${qs({ days })}`, 'zorunlu-egitim.csv'),
  courses: (active = false) => hrSend<{ items: Course[] }>('GET', `${L}/courses${qs({ active: active || undefined })}`),
  createCourse: (body: Partial<Course>) => hrSend<Course>('POST', `${L}/courses`, body),
  updateCourse: (id: string, body: Partial<Course>) => hrSend<Course>('PATCH', `${L}/courses/${enc(id)}`, body),
  sessions: (state = '', course = '') => hrSend<{ items: Session[] }>('GET', `${L}/sessions${qs({ state, course })}`),
  session: (id: string) => hrSend<SessionDetail>('GET', `${L}/sessions/${enc(id)}`),
  createSession: (body: { courseId: string; startsAt: string; endsAt?: string; location?: string; trainer?: string; capacity?: number | null; employeeIds?: string[] }) =>
    hrSend<SessionDetail>('POST', `${L}/sessions`, body),
  updateSession: (id: string, body: Record<string, unknown>) => hrSend<SessionDetail>('PATCH', `${L}/sessions/${enc(id)}`, body),
  enroll: (id: string, employeeIds: string[]) => hrSend<{ added: number; skipped: number }>('POST', `${L}/sessions/${enc(id)}/enroll`, { employeeIds }),
  removeEnrollment: (id: string) => hrSend<{ ok: boolean }>('DELETE', `${L}/enrollments/${enc(id)}`),
  decide: (id: string, action: 'onayla' | 'reddet', note = '') => hrSend<Enrollment>('POST', `${L}/enrollments/${enc(id)}/decide`, { action, note }),
  attendance: (id: string, items: { enrollmentId: string; attendance: Attendance | null }[]) =>
    hrSend<{ updated: number }>('POST', `${L}/sessions/${enc(id)}/attendance`, { items }),
  close: (id: string) => hrSend<{ completed: number; absent: number; feedbackInvited: number }>('POST', `${L}/sessions/${enc(id)}/close`),
  feedbackSummary: (id: string) => hrSend<FeedbackSummary>('GET', `${L}/sessions/${enc(id)}/feedback-summary`),
  feedbackThemes: (id: string) => hrSend<Job>('POST', `${L}/sessions/${enc(id)}/feedback-themes`),
  certificates: (employeeId = '', unverified = false) =>
    hrSend<{ items: Certificate[]; total: number }>('GET', `${L}/certificates${qs({ employeeId, unverified: unverified || undefined })}`),
  recordCertificate: (body: { employeeId: string; courseId?: string; title?: string; issuedOn: string; expiresOn?: string }) =>
    hrSend<Certificate>('POST', `${L}/certificates`, body),
  verifyCertificate: (id: string) => hrSend<{ verified: boolean }>('POST', `${L}/certificates/${enc(id)}/verify`),
  deleteCertificate: (id: string) => hrSend<{ ok: boolean }>('DELETE', `${L}/certificates/${enc(id)}`),
  certificateFile: (id: string, name: string) => hrDownload(`${L}/certificates/${enc(id)}/file`, name),
  needs: (state = '') => hrSend<{ items: Need[]; summary: NeedSummary[] }>('GET', `${L}/needs${qs({ state })}`),
  addNeed: (body: { employeeId?: string; unitId?: string; text: string; source: string }) => hrSend<Need>('POST', `${L}/needs`, body),
  decideNeed: (id: string, body: { state: NeedState; courseId?: string | null; priority?: Priority | null; note?: string }) =>
    hrSend<Need>('POST', `${L}/needs/${enc(id)}/decide`, body),
  suggestNeeds: (ids?: string[]) => hrSend<Job>('POST', `${L}/needs/suggest`, { ids: ids ?? [] }),
  usageMap: (days = 30) => hrSend<UsageMap>('GET', `${L}/usage-map${qs({ days })}`),
  guides: () => hrSend<{ items: Guide[] }>('GET', `${L}/guides`),
  createGuide: (body: { moduleRoute: string; title: string; body: string }) => hrSend<Guide>('POST', `${L}/guides`, body),
  updateGuide: (id: string, body: { title?: string; body?: string }) => hrSend<Guide>('PATCH', `${L}/guides/${enc(id)}`, body),
  draftGuide: (body: { moduleRoute: string; label: string; group: string; hint: string; keywords: string[]; notes: string; guideId?: string }) =>
    hrSend<Guide>('POST', `${L}/guides/draft`, body, 300_000),
  publishGuide: (id: string) => hrSend<Guide>('POST', `${L}/guides/${enc(id)}/publish`),
  unpublishGuide: (id: string) => hrSend<{ ok: boolean }>('POST', `${L}/guides/${enc(id)}/unpublish`),
  spend: (year: number) => hrSend<Spend>('GET', `${L}/spend${qs({ year })}`, undefined, 600_000),
  spendAccounts: (year: number) => hrSend<{ items: { code: string; name: string }[]; selected: string[] }>('GET', `${L}/spend/accounts${qs({ year })}`, undefined, 600_000),
  putBudget: (year: number, amount: number, note: string) => hrSend<Spend['budget']>('PUT', `${L}/budget/${year}`, { amount, note }),
};

/** Ekran ziyaret sayacı: aynı gün aynı ekran için sekme başına bir kez. Hata sessizce yutulur (sayım ürün akışını durdurmaz). */
const sent = new Set<string>();
export function recordVisit(route: string): void {
  if (!ENGINE_ENABLED || !route) return;
  const key = `${new Date().toISOString().slice(0, 10)}:${route}`;
  if (sent.has(key)) return;
  sent.add(key);
  void hrSend('POST', '/visit', { route }, 15_000).catch(() => sent.delete(key));
}

const money = new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 });
export const fmtMoney = (n: number | null | undefined) => (n === null || n === undefined ? '—' : money.format(n));
export const pct = (r: number | null | undefined) => (r === null || r === undefined ? '—' : `%${Math.round(r * 100)}`);

/** `datetime-local` alanı → Türkiye saatiyle ISO (köprü saat dilimsizi İstanbul sayar). */
export const localToIso = (v: string) => (v ? `${v}:00` : '');

export const STATUS_TONE: Record<Status, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  doldu: 'err',
  hic_yok: 'err',
  dolacak: 'warn',
  gecerli: 'ok',
};
