import { hrDownload, hrSend, qs } from '../hrApi';
import type { Kaynaklar } from '../../components/sqlInfo';

/** M56 Performans yönetimi uçları (/api/v1/hr/performance/*). Kapsam köprüde: kendi kaydım, ekip zincirim, İK/GM. */

const P = '/performance';
const enc = encodeURIComponent;

export type Level = 'sirket' | 'birim' | 'kisi';
export type GoalState = 'taslak' | 'onayda' | 'yururlukte' | 'kapandi';
export type Checkin = { id?: string; at: string; author: string; progressPct: number | null; value: number | null; note: string };
export type Revision = {
  id: string; goalId: string; requestedBy: string; requestedAt: string; changes: Record<string, unknown>; reason: string;
  decidedBy: string | null; decidedAt: string | null; decision: 'onay' | 'ret' | null; decisionNote: string;
};
export type Goal = {
  id: string; level: Level; levelLabel: string; ownerEmployeeId: string | null; ownerName: string | null; unitId: string | null;
  unitName: string | null; parentGoalId: string | null; parentTitle: string | null; title: string; description: string;
  measureKind: 'beyan' | 'sistem'; systemMeasure: string | null; measureRef: string | null; targetValue: number | null;
  unitLabel: string; weight: number | null; period: string; state: GoalState; stateLabel: string; submittedBy: string | null;
  submittedAt: string | null; approvedBy: string | null; approvedAt: string | null; reviewNote: string; createdBy: string | null;
  updatedAt: string | null; aligned: boolean; lastCheckin: Checkin | null; openRevision: Revision | null;
};
export type GoalDetail = Goal & {
  checkins: Checkin[]; revisions: Revision[];
  children: { id: string; title: string; level: Level; ownerName: string | null; unitName: string | null; state: GoalState }[];
  can: { edit: boolean; submit: boolean; withdraw: boolean; approve: boolean; checkin: boolean; revise: boolean; close: boolean };
 kaynaklar?: Kaynaklar; };
export type Section = { key: string; title: string; kind: 'yetkinlik' | 'hedef' | 'acik'; items: { key: string; label: string }[]; help?: string };
export type Form = { id: string; name: string; version: number; sections: Section[]; overallLabels: string[]; state: 'taslak' | 'yururlukte' | 'arsiv'; stateLabel: string; updatedBy: string | null; updatedAt: string | null };
export type CycleState = 'hazirlik' | 'acik' | 'kalibrasyon' | 'kapandi';
export type Cycle = {
  id: string; name: string; periodStart: string; periodEnd: string; startsOn: string; endsOn: string; selfDue: string | null;
  managerDue: string | null; formTemplateId: string | null; form: Form | null; audience: { units?: string[] }; state: CycleState;
  stateLabel: string; createdBy: string | null; updatedAt: string | null; closedAt: string | null;
};
export type ReviewState = 'oz_degerlendirme' | 'yonetici' | 'gorusme' | 'calisan_yorumu' | 'ik_onayi' | 'onaylandi';
export type Answers = { ratings: Record<string, number>; notes: Record<string, string>; overall?: number };
export type WorkSummary = {
  id: string; periodStart: string; periodEnd: string; generatedAt: string; generatedBy: string; text: string;
  facts: Record<string, unknown>; shownToEmployeeAt: string | null;
};
export type Review = {
  id: string; cycle: Cycle; employeeId: string; employeeName: string | null; unitName: string | null; title: string;
  managerId: string | null; managerName: string | null; role: 'self' | 'manager' | 'chain' | 'hr'; state: ReviewState; stateLabel: string;
  self: Answers; selfSubmittedAt: string | null; manager: Answers | null; managerSubmittedAt: string | null; sharedAt: string | null;
  meetingAt: string | null; employeeComment: string; objection: boolean; commentedAt: string | null; hrApprovedBy: string | null;
  hrApprovedAt: string | null; hrNote: string; goals: Goal[]; workSummaries: WorkSummary[];
  can: { editSelf: boolean; editManager: boolean; share: boolean; comment: boolean; approve: boolean; reassign: boolean; workSummary: boolean; rewrite: boolean };
 kaynaklar?: Kaynaklar; };
export type Task = { kind: 'oz' | 'yorum' | 'checkin'; reviewId?: string; goalId?: string; label: string; due: string | null; daysLeft: number | null };
export type Me = {
  employee: { id: string; displayName: string; unitName: string | null; managerName: string | null; title: string } | null;
  goals: Goal[]; reviews: { id: string; cycleName: string; cycleState: CycleState; state: ReviewState; stateLabel: string; selfDue: string | null; sharedAt: string | null }[];
  workSummaries: WorkSummary[]; tasks: Task[];
 kaynaklar?: Kaynaklar; };
export type TeamPerson = {
  id: string; name: string; title: string; unitName: string | null; direct: boolean; managerName: string | null; goals: number;
  pendingApproval: number; openRevisions: number; noCheckin: number; avgProgress: number | null;
  reviews: { id: string; cycleName: string; state: ReviewState; stateLabel: string; mine: boolean }[];
};
export type Team = { me: { id: string | null; name: string | null } | null; people: TeamPerson[]; gaps: { id: string; name: string; unitName: string | null }[] | null; kaynaklar?: Kaynaklar };
export type Status = {
  cycle: Cycle; total: number; selfDone: number; managerDone: number; selfRate: number | null; managerRate: number | null; shared: number;
  approved: number; objections: number; noManager: number;
  units: { unitId: string | null; unitName: string; total: number; self: number; manager: number; approved: number }[];
  people: { reviewId: string; employeeId: string; name: string | null; unitName: string | null; managerId: string | null; managerName: string | null; state: ReviewState; stateLabel: string; objection: boolean }[];
 kaynaklar?: Kaynaklar; };
export type Calibration = {
  cycle: Cycle; labels: string[]; overall: number[]; n: number; mean: number | null;
  units: { unitId: string | null; unitName: string; counts: number[]; n: number; mean: number | null; people: { reviewId: string; name: string | null; score: number; managerName: string | null }[] }[];
 kaynaklar?: Kaynaklar; };
export type PerfMeta = {
  levels: Record<Level, string>; goalStates: Record<GoalState, string>; measureKinds: Record<string, string>;
  systemMeasures: Record<string, { label: string; unit: string; hint: string }>; sectionKinds: Record<string, string>;
  cycleStates: Record<CycleState, string>; reviewStates: Record<ReviewState, string>; defaultOverall: string[];
  settings: { logoSales: boolean; remindDays: number | null }; modelVar: boolean; units: { id: string; name: string; parentId: string | null }[];
  me: { username: string; display: string; employeeId: string | null; teamSize: number; managedUnits: string[];
    can: { goalWrite: boolean; goalApprove: boolean; cycle: boolean; reviewWrite: boolean; reviewApprove: boolean; calibration: boolean; workSummary: boolean; export: boolean } };
};
export type Progress = {
  kind: 'beyan' | 'sistem'; periodStart: string; periodEnd: string; target: number | null; value: number | null; progressPct: number | null;
  invoices?: number; lastDate?: string | null; code?: string; note?: string;
 kaynaklar?: Kaynaklar; };

export const perfApi = {
  meta: () => hrSend<PerfMeta>('GET', `${P}/meta`),
  me: () => hrSend<Me>('GET', `${P}/me`),
  team: (direct = false) => hrSend<Team>('GET', `${P}/team${qs({ direct: direct || undefined })}`),
  person: (id: string) => hrSend<{ employee: { id: string; name: string; title: string; unitName: string | null; managerName: string | null }; goals: Goal[];
    reviews: { id: string; cycleName: string; state: ReviewState; stateLabel: string; mine: boolean }[]; workSummaries: WorkSummary[] | null }>('GET', `${P}/team/${enc(id)}`),
  goals: (f: { period?: string; year?: string; owner?: string; level?: string } = {}) => hrSend<{ items: Goal[] }>('GET', `${P}/goals${qs(f)}`),
  goal: (id: string) => hrSend<GoalDetail>('GET', `${P}/goals/${enc(id)}`),
  createGoal: (b: Record<string, unknown>) => hrSend<GoalDetail>('POST', `${P}/goals`, b),
  updateGoal: (id: string, b: Record<string, unknown>) => hrSend<GoalDetail>('PATCH', `${P}/goals/${enc(id)}`, b),
  goalAction: (id: string, action: 'submit' | 'withdraw' | 'approve' | 'reject' | 'close', note = '') => hrSend<GoalDetail>('POST', `${P}/goals/${enc(id)}/${action}`, { note }),
  checkin: (id: string, b: { progressPct?: number | null; value?: number | null; note?: string }) => hrSend<GoalDetail>('POST', `${P}/goals/${enc(id)}/checkins`, b),
  revise: (id: string, b: { changes: Record<string, unknown>; reason: string }) => hrSend<GoalDetail>('POST', `${P}/goals/${enc(id)}/revisions`, b),
  decide: (rid: string, decision: 'onay' | 'ret', note = '') => hrSend<GoalDetail>('POST', `${P}/revisions/${enc(rid)}/decide`, { decision, note }),
  progress: (id: string) => hrSend<Progress>('GET', `${P}/goals/${enc(id)}/progress`),
  draft: (b: { parentGoalId?: string; ownerEmployeeId?: string; unitId?: string; hint?: string }) =>
    hrSend<{ items: { title: string; measure: string; target: string }[] }>('POST', `${P}/goals/draft`, b, 180_000),
  align: (id: string) => hrSend<{ candidates: { id: string; title: string; level: Level; unitName: string | null }[];
    suggestion: { id: string; title: string; probability: number | null } | null; note?: string }>('POST', `${P}/goals/${enc(id)}/align-suggest`, {}, 180_000),
  salesmanFill: (year: number) => hrSend<{ year: number; invoices: number; withSalesman: number; rate: number | null }>('GET', `${P}/logo-salesman-fill${qs({ year })}`, undefined, 300_000),
  forms: () => hrSend<{ items: Form[]; starter: { name: string; sections: Section[] } }>('GET', `${P}/forms`),
  createForm: (b: Record<string, unknown>) => hrSend<Form>('POST', `${P}/forms`, b),
  updateForm: (id: string, b: Record<string, unknown>) => hrSend<Form>('PATCH', `${P}/forms/${enc(id)}`, b),
  cycles: () => hrSend<{ items: Cycle[] }>('GET', `${P}/cycles`),
  createCycle: (b: Record<string, unknown>) => hrSend<Cycle>('POST', `${P}/cycles`, b),
  updateCycle: (id: string, b: Record<string, unknown>) => hrSend<Cycle>('PATCH', `${P}/cycles/${enc(id)}`, b),
  cycleAction: (id: string, action: 'open' | 'calibrate' | 'reopen' | 'close') => hrSend<Cycle & { added?: number }>('POST', `${P}/cycles/${enc(id)}/${action}`),
  sync: (id: string) => hrSend<{ added: number }>('POST', `${P}/cycles/${enc(id)}/sync`),
  status: (id: string) => hrSend<Status>('GET', `${P}/cycles/${enc(id)}/status`),
  remind: (id: string, which: 'self' | 'manager') => hrSend<{ people: number; sent: number; noMail: number; failed: number; adRead: boolean }>('POST', `${P}/cycles/${enc(id)}/remind`, { which }, 180_000),
  calibration: (id: string) => hrSend<Calibration>('GET', `${P}/cycles/${enc(id)}/calibration`),
  exportCycle: (id: string) => hrDownload(`${P}/cycles/${enc(id)}/export.csv`, 'degerlendirme.csv'),
  review: (id: string) => hrSend<Review>('GET', `${P}/reviews/${enc(id)}`),
  saveReview: (id: string, b: { self?: Answers; manager?: Answers }) => hrSend<Review>('PATCH', `${P}/reviews/${enc(id)}`, b),
  submitSelf: (id: string, self: Answers) => hrSend<Review>('POST', `${P}/reviews/${enc(id)}/submit-self`, { self }),
  submitManager: (id: string, manager: Answers) => hrSend<Review>('POST', `${P}/reviews/${enc(id)}/submit-manager`, { manager }),
  reviewAction: (id: string, action: 'share' | 'comment' | 'approve' | 'reassign', b: Record<string, unknown>) => hrSend<Review>('POST', `${P}/reviews/${enc(id)}/${action}`, b),
  rewrite: (id: string, text: string) => hrSend<{ text: string; masked: Record<string, number> }>('POST', `${P}/reviews/${enc(id)}/rewrite`, { text }, 180_000),
  workSummary: (id: string) => hrSend<WorkSummary>('POST', `${P}/reviews/${enc(id)}/work-summary`, undefined, 300_000),
};

export const STATE_TONE: Record<GoalState, 'ok' | 'warn' | 'muted' | 'violet'> = { taslak: 'muted', onayda: 'warn', yururlukte: 'ok', kapandi: 'violet' };
export const REVIEW_TONE: Record<ReviewState, 'ok' | 'warn' | 'muted' | 'violet' | 'err'> = {
  oz_degerlendirme: 'muted', yonetici: 'warn', gorusme: 'warn', calisan_yorumu: 'violet', ik_onayi: 'violet', onaylandi: 'ok',
};
export const pct = (v: number | null | undefined) => (v === null || v === undefined ? '—' : `%${Math.round(v * 100)}`);
export const thisYear = () => String(new Date().getFullYear());
