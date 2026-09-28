import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** İnsan Kaynakları ekranlarının köprü uçları: İK-0 (/api/v1/hr/*) ve M55 işe alım (/api/v1/hr/recruit/*).
 *  M56–M58 aynı istemciyi kullanır; kendi uçlarını `hrSend` ile çağırır. */

const B = '/api/v1/hr';

async function fail(res: Response): Promise<never> {
  const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
  const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  throw new Error(msg || httpErrorText(res.status));
}

export async function hrSend<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

async function upload<T>(path: string, file: File): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}${qs({ filename: file.name })}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
    signal: AbortSignal.timeout(300_000),
  });
  if (!res.ok) return fail(res);
  return (await res.json()) as T;
}

/** Dosya indirme (çerezle). Tarayıcıya kaydettirir; bağlantı paylaşılmaz. */
export async function hrDownload(path: string, fallbackName: string): Promise<void> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, { credentials: 'include', signal: AbortSignal.timeout(120_000) });
  if (!res.ok) return fail(res);
  const blob = await res.blob();
  const cd = res.headers.get('Content-Disposition') || '';
  const m = /filename\*=UTF-8''([^;]+)|filename="([^"]+)"/.exec(cd);
  const name = m ? decodeURIComponent(m[1] || m[2]) : fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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

/* ------------------------------------------------------------------ İK-0 türleri */

export type Employee = {
  id: string; username: string | null; adGuid: string | null; crmSystemUserId: string | null; displayName: string;
  unitId: string | null; unitName: string | null; managerId: string | null; title: string; startDate: string | null;
  endDate: string | null; status: 'aktif' | 'ayrildi'; statusLabel: string; source: Record<string, string>;
  updatedBy: string | null; updatedAt: string | null;
};
export type Unit = {
  id: string; name: string; parentId: string | null; managerEmployeeId: string | null; crmBusinessUnitId: string | null;
  adOu: string | null; active: boolean; employees: number; updatedBy: string | null; updatedAt: string | null;
};
export type SyncPreview = {
  employees: Array<{ crmSystemUserId: string; id?: string; displayName: string; username: string; unitName: string; lastLogon: string | null;
    action: 'yeni' | 'degisti' | 'ayni'; changes: Record<string, { once: unknown; sonra: unknown }> }>;
  departed: Array<{ id: string; displayName: string; username: string | null; unitName: string | null }>;
  units: Array<{ crmBusinessUnitId: string; name: string; action: 'yeni' | 'degisti' | 'ayni'; enabledUsers: number; employees: number; crmManagerId: string | null }>;
  teams: Array<{ teamId: string; team: string; members: number }>;
  stats: { crmEnabled: number; crmInteractive: number; adChecked: boolean; matched: number; units: number; unitsWithManager: number;
    new: number; changed: number; departed: number; unitsNew: number };
  notes: string[];
};
export type Notice = { id: string; audience: 'aday' | 'calisan'; version: number; title: string; body: string; publishedAt: string; publishedBy: string | null };
export type Consent = {
  id: string; subjectType: 'aday' | 'calisan'; subjectId: string; purpose: string; purposeLabel: string; noticeVersion: number | null;
  givenAt: string; channel: string | null; channelLabel: string | null; evidence: string; recordedBy: string | null;
  withdrawnAt: string | null; withdrawnBy: string | null; active: boolean;
};
export type RetentionRow = { dataClass: string; label: string; hint: string; keepDays: number | null; legalBasis: string; approvedBy: string | null; approvedAt: string | null };
export type PurgeRun = { id: number; at: string; dataClass: string; label: string; purged: number; ids: string[]; error: string | null; actor: string | null };
export type AccessRow = { id: number; at: string; username: string; subjectType: string; subjectId: string; action: string; purpose: string };
export type Page<T> = { items: T[]; hasMore: boolean; next: number | null };
export type Job = { id: string; kind: string; subjectId: string; state: 'calisiyor' | 'bitti' | 'hata'; progress: number; total: number;
  result: Record<string, unknown> | null; error: string | null; startedAt: string; finishedAt: string | null };
export type HrMeta = {
  me: { username: string; display: string; isAdmin: boolean; keys: string[] };
  settings: { slaDays: number | null; fileMaxMb: number; adminSeesPersonal: boolean; alertRecipients: number };
  purposes: Record<string, { label: string; hint: string; subject: string }>;
  dataClasses: Record<string, { label: string; hint: string }>;
  channels: Record<string, string>;
  audiences: Record<string, string>;
  employeeStatus: Record<string, string>;
  modelVar: boolean;
};

export const hrApi = {
  meta: () => hrSend<HrMeta>('GET', '/meta'),
  job: (id: string) => hrSend<Job>('GET', `/jobs/${enc(id)}`),
  employees: (p: { status?: string; q?: string; unit?: string } = {}) => hrSend<{ items: Employee[]; total: number }>('GET', `/employees${qs(p)}`),
  createEmployee: (b: Partial<Employee>) => hrSend<Employee>('POST', '/employees', b),
  updateEmployee: (id: string, b: Partial<Employee>) => hrSend<Employee>('PATCH', `/employees/${enc(id)}`, b),
  syncPreview: () => hrSend<SyncPreview>('POST', '/employees/sync-preview', {}, 300_000),
  syncApply: (kinds: string[]) =>
    hrSend<{ applied: Record<string, number>; stats: SyncPreview['stats']; notes: string[] }>('POST', '/employees/sync-apply', { kinds }, 300_000),
  units: () => hrSend<{ items: Unit[] }>('GET', '/units'),
  createUnit: (b: Partial<Unit>) => hrSend<Unit>('POST', '/units', b),
  updateUnit: (id: string, b: Partial<Unit>) => hrSend<Unit>('PATCH', `/units/${enc(id)}`, b),
  notices: (audience = '') => hrSend<{ items: Notice[] }>('GET', `/notices${qs({ audience })}`),
  publishNotice: (b: { audience: string; title: string; body: string }) => hrSend<Notice>('POST', '/notices', b),
  consents: (p: { subjectType?: string; subjectId?: string } = {}) => hrSend<{ items: Consent[] }>('GET', `/consents${qs(p)}`),
  addConsent: (b: { subjectType: string; subjectId: string; purpose: string; channel: string; evidence?: string; givenAt?: string }) =>
    hrSend<Consent>('POST', '/consents', b),
  withdrawConsent: (id: string) => hrSend<Consent>('POST', `/consents/${enc(id)}/withdraw`, {}),
  retention: () => hrSend<{ items: RetentionRow[] }>('GET', '/retention'),
  putRetention: (items: Array<{ dataClass: string; keepDays: number | null; legalBasis: string }>) =>
    hrSend<{ items: RetentionRow[] }>('PUT', '/retention', { items }),
  purgePreview: () => hrSend<{ items: Array<{ key: string; label: string; due: number | null; error: string | null }> }>('GET', '/purge/preview'),
  purgeRuns: (before?: number) => hrSend<Page<PurgeRun>>('GET', `/purge/runs${qs({ before })}`),
  accessLog: (p: { subjectId?: string; user?: string; before?: number } = {}) => hrSend<Page<AccessRow>>('GET', `/access-log${qs(p)}`),
};

/* ------------------------------------------------------------------ M55 türleri */

export type Stage = 'basvurdu' | 'on_eleme' | 'mulakat' | 'teklif' | 'sonuc';
export type Outcome = 'ise_alindi' | 'ret' | 'cekildi';
export type PositionState = 'taslak' | 'onayda' | 'acik' | 'beklemede' | 'kapandi';
export type Warning = { line?: number; label: string; text?: string; source: 'kural' | 'zeki'; probability?: number | null };

export type Position = {
  id: string; title: string; unitId: string | null; unitName: string; hiringManager: string | null; team: string[];
  competencies: string[]; note: string; postingText: string; postingWarnings: Warning[];
  interviewKit: Array<{ competency: string; questions: string[]; criteria: string }>;
  state: PositionState; stateLabel: string; submittedBy: string | null; submittedAt: string | null; approvedBy: string | null;
  approvedAt: string | null; reviewNote: string; openedAt: string | null; closedAt: string | null; createdBy: string | null;
  createdAt: string; updatedAt: string; counts: Partial<Record<Stage, number>>;
};

export type Card = {
  id: string; name: string; positionId: string | null; positionTitle: string; source: string; stage: Stage; outcome: Outcome | null;
  outcomeLabel: string; daysInStage: number | null; overSla: boolean; needsReply: boolean; hasEvidence: boolean; createdAt: string;
};

export type Pipeline = {
  stages: Record<Stage, string>;
  outcomes: Record<Outcome, string>;
  columns: Record<Stage, Card[]>;
  counters: { openPositions: number; thisWeek: number; overSla: number | null; slaDays: number | null; waitingReply: number; unanswered30: number };
  total: number;
  positions: Array<{ id: string; title: string; state: PositionState; counts: Partial<Record<Stage, number>> }>;
};

export type RecruitMeta = {
  stages: Record<Stage, string>; outcomes: Record<Outcome, string>; sources: Record<string, string>;
  positionStates: Record<PositionState, string>; templateKinds: Record<string, string>; templateStates: Record<string, string>;
  fields: Record<string, string>; messageStates: Record<string, string>; sendChannels: Record<string, string>;
  slaDays: number | null; fileMaxMb: number; modelVar: boolean;
  me: { username: string; display: string; can: { all: boolean; see: boolean; decide: boolean; positionOpen: boolean; positionApprove: boolean;
    letters: boolean; offerApprove: boolean; templates: boolean; export: boolean; kvkk: boolean } };
};

export type Message = {
  id: string; kind: string; kindLabel: string; templateId: string | null; templateVersion: number | null; body: string;
  status: 'taslak' | 'onayda' | 'onaylandi' | 'gonderildi' | 'iptal'; statusLabel: string; createdBy: string | null; createdAt: string;
  approvedBy: string | null; approvedAt: string | null; sentBy: string | null; sentAt: string | null; channel: string | null; note: string;
  missing?: string[]; softenNote?: string | null;
};

export type Candidate = {
  id: string; fullName: string; email: string | null; phone: string | null; source: string; sourceLabel: string; stage: Stage;
  stageLabel: string; outcome: Outcome | null; outcomeLabel: string; stageSince: string; daysInStage: number | null; overSla: boolean;
  createdAt: string; employeeId: string | null;
  position: { id: string; title: string; competencies: string[]; interviewKit: Position['interviewKit'] } | null;
  retention: { class: string | null; label: string | null; until: string | null; forced: string | null };
  files: Array<{ id: string; filename: string; size: number; createdAt: string; maskCounts: Record<string, number>; modelChecked: boolean;
    maskedText: string; originalText: string | null }>;
  evidence: Array<{ competency: string; verdict: 'kanit_var' | 'kanit_yok'; quotes: Array<{ line: number; text: string }> }>;
  evidenceAt: string | null;
  interviews: Array<{ id: string; startsAt: string; location: string; roomBookingId: string | null; interviewers: string[]; iAmInterviewer: boolean;
    hiddenOthers: boolean; notes: Array<{ id: string; author: string; scores: Record<string, number>; note: string; submittedAt: string | null; mine: boolean }> }>;
  messages: Message[];
  stageLog: Array<{ at: string; actor: string; from: Stage | null; to: Stage; outcome: Outcome | null; reason: string }>;
  consents?: Consent[];
  can: { decide: boolean; edit: boolean; files: boolean; downloadOriginal: boolean; letters: boolean; approveOffer: boolean; export: boolean;
    delete: boolean; consents: boolean };
};

export type Template = {
  id: string; kind: string; kindLabel: string; name: string; body: string; version: number; state: 'taslak' | 'yururlukte' | 'arsiv';
  stateLabel: string; placeholders: string[]; unknown: string[]; updatedBy: string | null; updatedAt: string;
};

const R = '/recruit';

export const recruitApi = {
  meta: () => hrSend<RecruitMeta>('GET', `${R}/meta`),
  pipeline: (position = '') => hrSend<Pipeline>('GET', `${R}/pipeline${qs({ position })}`),
  positions: (state = '') => hrSend<{ items: Position[] }>('GET', `${R}/positions${qs({ state })}`),
  position: (id: string) => hrSend<Position>('GET', `${R}/positions/${enc(id)}`),
  createPosition: (b: Partial<Position>) => hrSend<Position>('POST', `${R}/positions`, b),
  updatePosition: (id: string, b: Partial<Position>) => hrSend<Position>('PATCH', `${R}/positions/${enc(id)}`, b),
  positionAction: (id: string, action: 'submit' | 'withdraw' | 'approve' | 'reject' | 'hold' | 'resume' | 'close', note = '') =>
    hrSend<Position>('POST', `${R}/positions/${enc(id)}/${action}`, { note }),
  postingDraft: (id: string) => hrSend<{ text: string; warnings: Warning[] }>('POST', `${R}/positions/${enc(id)}/posting-draft`, {}, 300_000),
  postingCheck: (id: string, text: string) => hrSend<{ warnings: Warning[] }>('POST', `${R}/positions/${enc(id)}/posting-check`, { text }, 180_000),
  interviewKit: (id: string) => hrSend<{ items: Position['interviewKit'] }>('POST', `${R}/positions/${enc(id)}/interview-kit`, {}, 300_000),
  createCandidate: (b: { fullName: string; email?: string; phone?: string; positionId?: string | null; source?: string }) =>
    hrSend<{ id: string; ackDraft: string | null }>('POST', `${R}/candidates`, b),
  candidate: (id: string) => hrSend<Candidate>('GET', `${R}/candidates/${enc(id)}`),
  updateCandidate: (id: string, b: { fullName?: string; email?: string; phone?: string; positionId?: string | null; source?: string }) =>
    hrSend<{ changed: string[] }>('PATCH', `${R}/candidates/${enc(id)}`, b),
  stage: (id: string, b: { stage: Stage; outcome?: Outcome; reason?: string; startDate?: string }) =>
    hrSend<{ from: Stage; to: Stage; outcome: Outcome | null; employeeId: string | null }>('POST', `${R}/candidates/${enc(id)}/stage`, b),
  addFile: (id: string, file: File) => upload<{ id: string; filename: string; size: number; maskCounts: Record<string, number>; okuma?: { ocrSayfa: string[]; enDusukGuven: number | null } }>(`${R}/candidates/${enc(id)}/files`, file),
  deleteFile: (id: string, fid: string) => hrSend<{ ok: boolean }>('DELETE', `${R}/candidates/${enc(id)}/files/${enc(fid)}`),
  downloadFile: (id: string, fid: string, name: string) => hrDownload(`${R}/candidates/${enc(id)}/files/${enc(fid)}`, name),
  evidence: (id: string) => hrSend<Job>('POST', `${R}/candidates/${enc(id)}/evidence`, {}),
  exportCandidate: (id: string) => hrDownload(`${R}/candidates/${enc(id)}/export`, 'aday.json'),
  deleteCandidate: (id: string, reason: string) => hrSend<{ ok: boolean; purged: number }>('DELETE', `${R}/candidates/${enc(id)}${qs({ reason })}`),
  createInterview: (b: { candidateId: string; startsAt: string; location?: string; roomBookingId?: string; interviewers: string[] }) =>
    hrSend<{ id: string }>('POST', `${R}/interviews`, b),
  saveNote: (iid: string, b: { scores: Record<string, number>; note: string; submit: boolean }) =>
    hrSend<{ id: string; submitted: boolean }>('POST', `${R}/interviews/${enc(iid)}/notes`, b),
  templates: (kind = '') => hrSend<{ items: Template[]; kinds: Record<string, string>; fields: Record<string, string> }>('GET', `${R}/templates${qs({ kind })}`),
  starters: () => hrSend<{ items: Record<string, string> }>('GET', `${R}/templates/starters`),
  createTemplate: (b: { kind: string; name: string; body: string; state: string }) => hrSend<Template>('POST', `${R}/templates`, b),
  updateTemplate: (id: string, b: Partial<{ kind: string; name: string; body: string; state: string }>) => hrSend<Template>('PATCH', `${R}/templates/${enc(id)}`, b),
  letter: (cid: string, kind: string, b: { templateId?: string; soften?: boolean; fields?: Record<string, string> }) =>
    hrSend<Message>('POST', `${R}/candidates/${enc(cid)}/letters/${enc(kind)}`, b, 180_000),
  messageAction: (mid: string, action: 'edit' | 'submit' | 'approve' | 'reject' | 'sent' | 'cancel', b: Record<string, unknown> = {}) =>
    hrSend<Message>('POST', `${R}/messages/${enc(mid)}/${action}`, b),
  downloadMessage: (mid: string) => hrDownload(`${R}/messages/${enc(mid)}/document.docx`, 'mektup.docx'),
};

/* ------------------------------------------------------------------ biçim */

const dtf = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' });
const dttf = new Intl.DateTimeFormat('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
export const fmtDay = (iso: string | null | undefined) => (iso ? dtf.format(new Date(iso)) : '—');
export const fmtDateTime = (iso: string | null | undefined) => (iso ? dttf.format(new Date(iso)) : '—');
export const fmtSize = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1).replace('.', ',')} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
export const daysText = (d: number | null | undefined) => (d === null || d === undefined ? '—' : d === 0 ? 'bugün' : `${d} gün`);

export const STAGE_ORDER: Stage[] = ['basvurdu', 'on_eleme', 'mulakat', 'teklif', 'sonuc'];
export const POSITION_TONE: Record<PositionState, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted', onayda: 'warn', acik: 'ok', beklemede: 'violet', kapandi: 'muted',
};

/** Arka plan işini bitene kadar izler (1,5 sn arayla). */
export async function waitJob(id: string, onTick?: (j: Job) => void): Promise<Job> {
  for (;;) {
    const j = await hrApi.job(id);
    onTick?.(j);
    if (j.state !== 'calisiyor') return j;
    await new Promise((r) => setTimeout(r, 1500));
  }
}
