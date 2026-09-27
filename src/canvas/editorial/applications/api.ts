import { ENGINE_BASE, putFile, send } from '../../engine';

/** M1 başvuru ve yayın kurulu: köprünün `/api/v1/editorial/applications` ve `/board-sessions` uçları. */

export type Opt = { value: string; label: string };
export type AppStatus = 'yeni' | 'degerlendirmede' | 'revizyon' | 'kurul_bekliyor' | 'kurulda' | 'kabul' | 'red' | 'geri_cekildi';
export type AppView = 'kuyruk' | 'kabul' | 'arsiv' | 'hepsi';
export type VoteChoice = 'kabul' | 'revizyon' | 'red' | 'cekimser';
export type BoardDecision = 'kabul' | 'revizyon' | 'red' | 'ertele' | 'ertelendi';

export type AppMeta = {
  statuses: Opt[];
  channels: Opt[];
  audiences: Opt[];
  fileKinds: Opt[];
  recommendations: Opt[];
  redlines: Opt[];
  votes: Opt[];
  decisions: Opt[];
  letterKinds: Opt[];
  sendChannels: Opt[];
  thresholds: { accept: number; revise: number };
  fileMaxMb: number;
  me: { username: string; display: string; canWrite: boolean; canManage: boolean; canRunBoard: boolean; canSeeNames: boolean };
};

export type AppInput = Partial<{
  title: string;
  authorName: string;
  authorEmail: string;
  authorPhone: string;
  authorBio: string;
  authorExpertise: string;
  authorHistory: string;
  agencyName: string;
  agencyContact: string;
  crmContactId: string | null;
  summary: string;
  audience: string;
  ageFrom: number | string | null;
  ageTo: number | string | null;
  pageEstimate: number | string;
  genre: string;
  categoryId: string | null;
  categoryName: string | null;
  series: string;
  publisherNote: string;
  channel: string;
  receivedOn: string;
}>;

export type AppListItem = {
  id: string;
  no: string;
  status: AppStatus;
  statusLabel: string;
  title: string;
  authorName: string;
  agencyName: string | null;
  categoryName: string | null;
  channelLabel: string;
  receivedOn: string;
  pageEstimate: number;
  evaluator: string | null;
  evaluatorName: string | null;
  mine: boolean;
  files: number;
  evaluation: { submitted: boolean; contentScore: number | null; recommendation: string | null } | null;
  session: { id: string; title: string; date: string } | null;
  waitingDays: number | null;
  decidedAt: string | null;
  decisionNote: string | null;
};

export type AppFile = { id: string; kind: string; kindLabel: string; round: number; filename: string; mime: string; bytes: number; uploadedBy: string; uploadedAt: string };

export type Evaluation = {
  id: string;
  round: number;
  evaluator: string;
  evaluatorName: string;
  contentScore: number | null;
  mission: number | null;
  publishing: number | null;
  commercial: number | null;
  total: number | null;
  recommendation: string | null;
  recommendationLabel: string | null;
  topic: string | null;
  genre: string | null;
  ageGroup: string | null;
  overlapNote: string | null;
  redline: string | null;
  redlineLabel: string | null;
  redlineNote: string | null;
  report: string | null;
  submitted: boolean;
  submittedAt: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
};

export type Letter = {
  id: string;
  kind: 'kabul' | 'red' | 'revizyon';
  kindLabel: string;
  state: 'taslak' | 'onaylandi' | 'gonderildi';
  stateLabel: string;
  subject: string;
  body: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string | null;
  approvedBy: string | null;
  approvedName: string | null;
  approvedAt: string | null;
  sentOn: string | null;
  sentChannel: string | null;
  sentChannelLabel: string | null;
};

export type Tally = {
  voted: number;
  members: number;
  hidden?: boolean;
  counts?: Record<VoteChoice, number>;
  axes?: { mission: number | null; publishing: number | null; commercial: number | null };
  total?: number | null;
  majority?: string | null;
  majorityLabel?: string | null;
  tie?: boolean;
  byScore?: string | null;
  byScoreLabel?: string | null;
  thresholds?: { accept: number; revise: number };
};

export type Vote = {
  member: string;
  memberName: string;
  mission: number | null;
  publishing: number | null;
  commercial: number | null;
  vote: VoteChoice;
  voteLabel: string;
  note: string | null;
  updatedAt: string;
};

export type BoardHistory = {
  sessionId: string;
  title: string;
  date: string;
  state: 'planli' | 'kapandi';
  decision: BoardDecision | null;
  decisionLabel: string | null;
  note: string | null;
  printRun: number | null;
  price: number | null;
  royalty: number | null;
  publishOn: string | null;
  decidedByName: string | null;
  decidedAt: string | null;
  tally: Tally;
  votes: Vote[] | null;
};

export type ReportState = { id: string; status: 'hazirlaniyor' | 'hazir' | 'hata'; createdAt: string; finishedAt: string | null; error: string | null } | null;

export type AppDetail = Omit<AppListItem, 'evaluation' | 'session' | 'files' | 'waitingDays' | 'channelLabel'> & {
  round: number;
  authorEmail: string | null;
  authorPhone: string | null;
  authorBio: string | null;
  authorExpertise: string | null;
  authorHistory: string | null;
  agencyContact: string | null;
  crmContactId: string | null;
  summary: string;
  audience: string | null;
  audienceLabel: string | null;
  ageFrom: number | null;
  ageTo: number | null;
  genre: string | null;
  categoryId: string | null;
  series: string | null;
  publisherNote: string | null;
  channel: string;
  channelLabel: string;
  decidedBy: string | null;
  crmProjectId: string | null;
  crmProjectName: string | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string | null;
  files: AppFile[];
  evaluations: Evaluation[];
  evaluation: Evaluation | null;
  log: Array<{ at: string; actor: string; actorName: string; action: string; detail: Record<string, unknown> | null }>;
  letters: Letter[];
  board: BoardHistory[];
  report: ReportState;
};

export type MarketBook = { id: string | null; title: string | null; author: string | null; series: string | null; code: string; firstPublish: string; firstYear: number; sold: boolean };
export type Market = {
  categoryId: string;
  categoryName: string;
  window: { from: string; to: string };
  cohortMonths: number;
  firstYearMonths: number;
  books: number;
  withSales: number;
  withoutSales: number;
  firstYear: { p25: number | null; p50: number | null; p75: number | null; mean: number | null; min: number | null; max: number | null };
  scenarios: { kotumser: number | null; baz: number | null; iyimser: number | null };
  printRun: { suggested: number | null; step: number; basis: string };
  series: { name: string; count: number; of: number } | null;
  curve: number[];
  channels: Array<{ name: string; qty: number; share: number | null }>;
  last36: number;
  list: MarketBook[];
  missingYears: number[];
  computedAt: string;
  source: string;
};
export type OverlapItem = { id: string | null; title: string | null; author: string | null; category: string | null; firstPublish: string | null; matches: number; ownWork: boolean };

export type BoardReport = {
  generatedAt: string;
  generatedBy: string;
  author: {
    name: string;
    bio: string | null;
    expertise: string | null;
    history: string | null;
    agency: string | null;
    crm: {
      contactId: string;
      name: string | null;
      bio: string | null;
      works: Array<{ bookId: string | null; title: string | null; role: string | null; on: string | null }>;
      roles: Array<{ role: string; count: number }>;
      contracts: number;
      projects: number;
    } | null;
  };
  book: { no: string; title: string; summary: string; audience: string | null; ageFrom: number | null; ageTo: number | null; pages: number; genre: string | null; series: string | null; publisherNote: string | null; channel: string; receivedOn: string };
  category: { id: string | null; name: string | null; seriesSuggestion: Market['series'] | null; applicantSeries: string | null; printRun: Market['printRun'] | null };
  market: Market | null;
  overlap: OverlapItem[] | null;
  evaluation: Evaluation | null;
  problems: string[];
};

export type ReportResponse = { id?: string; status: 'hazirlaniyor' | 'hazir' | 'hata' | null; error?: string | null; createdBy?: string; createdAt?: string; finishedAt?: string | null; content?: BoardReport | null };

export type Member = { username: string; display: string };
export type SessionHead = {
  id: string;
  title: string;
  date: string;
  time: string | null;
  place: string | null;
  chair: string;
  chairName: string;
  members: Member[];
  note: string | null;
  state: 'planli' | 'kapandi';
  stateLabel: string;
  createdBy: string;
  createdAt: string;
  closedAt: string | null;
  agenda?: { items: number; decided: number };
  isMember?: boolean;
  myVotes?: number;
};
export type AgendaItem = {
  appId: string;
  no: string;
  title: string;
  authorName: string;
  categoryName: string | null;
  evaluatorName: string | null;
  pageEstimate: number;
  appStatus: AppStatus;
  position: number;
  decision: BoardDecision | null;
  decisionLabel: string | null;
  decisionNote: string | null;
  printRun: number | null;
  price: number | null;
  royalty: number | null;
  publishOn: string | null;
  decidedByName: string | null;
  decidedAt: string | null;
  editor: { contentScore: number | null; mission: number | null; publishing: number | null; commercial: number | null; recommendation: string | null; recommendationLabel: string | null; redline: string | null; redlineLabel: string | null } | null;
  report: 'hazirlaniyor' | 'hazir' | 'hata' | null | undefined;
  myVote: Vote | null;
  tally: Tally;
  votes: Vote[] | null;
};
export type SessionDetail = SessionHead & { isMember: boolean; canRun: boolean; canSeeNames: boolean; items: AgendaItem[]; thresholds: { accept: number; revise: number } };
export type SessionInput = Partial<{ title: string; date: string; time: string; place: string; chair: string; chairName: string; members: Member[]; note: string }>;

const A = '/api/v1/editorial/applications';
const S = '/api/v1/editorial/board-sessions';
const enc = encodeURIComponent;
const qs = (o: Record<string, string | number | boolean | undefined>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== '' && v !== false) p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const applicationsApi = {
  meta: () => send<AppMeta>('GET', `${A}/meta`, undefined, 30_000),
  categories: () => send<{ items: Array<{ id: string; name: string; books: number }> }>('GET', `${A}/categories`, undefined, 60_000),
  list: (p: { view: AppView; q?: string; status?: string; mine?: boolean }) =>
    send<{ items: AppListItem[]; counts: Record<AppStatus, number>; totals: Record<AppView, number>; view: AppView }>(
      'GET',
      `${A}${qs({ view: p.view, q: p.q, status: p.status, mine: p.mine })}`,
      undefined,
      60_000,
    ),
  create: (b: AppInput) => send<AppDetail>('POST', A, b, 30_000),
  get: (id: string) => send<AppDetail>('GET', `${A}/${enc(id)}`, undefined, 60_000),
  update: (id: string, b: AppInput) => send<AppDetail>('PATCH', `${A}/${enc(id)}`, b, 30_000),
  upload: (id: string, kind: string, file: File) => putFile<AppFile>(`${A}/${enc(id)}/files?kind=${enc(kind)}`, file),
  fileUrl: (fileId: string) => `${ENGINE_BASE}${A}/files/${enc(fileId)}`,
  deleteFile: (fileId: string) => send<{ ok: boolean }>('DELETE', `${A}/files/${enc(fileId)}`, undefined, 30_000),
  assign: (id: string, evaluator: string, evaluatorName: string) =>
    send<AppDetail>('POST', `${A}/${enc(id)}/assign`, { evaluator, evaluatorName }, 30_000),
  saveEvaluation: (id: string, b: Record<string, unknown>) => send<Evaluation>('PUT', `${A}/${enc(id)}/evaluation`, b, 30_000),
  decide: (id: string, action: 'kurula' | 'revizyon' | 'red' | 'geri_cekildi', note: string) =>
    send<AppDetail>('POST', `${A}/${enc(id)}/decision`, { action, note }, 30_000),
  reopen: (id: string, note: string) => send<AppDetail>('POST', `${A}/${enc(id)}/reopen`, { note }, 30_000),
  overlap: (id: string) => send<{ items: OverlapItem[]; words: string[] }>('GET', `${A}/${enc(id)}/overlap`, undefined, 120_000),
  linkCrm: (id: string, projectId: string) => send<AppDetail>('POST', `${A}/${enc(id)}/crm-project`, { projectId }, 60_000),
  startReport: (id: string, refresh = false) => send<{ status: string }>('POST', `${A}/${enc(id)}/report`, { refresh }, 30_000),
  report: (id: string) => send<ReportResponse>('GET', `${A}/${enc(id)}/report`, undefined, 30_000),
  createLetter: (id: string, kind?: string) => send<Letter>('POST', `${A}/${enc(id)}/letters`, { kind }, 30_000),
  updateLetter: (letterId: string, b: { subject?: string; body?: string }) => send<Letter>('PATCH', `${A}/letters/${enc(letterId)}`, b, 30_000),
  letterAction: (letterId: string, action: 'approve' | 'unapprove' | 'sent' | 'delete', b: { on?: string; channel?: string } = {}) =>
    send<Letter>('POST', `${A}/letters/${enc(letterId)}/${action}`, b, 30_000),
};

export const boardApi = {
  list: (state?: 'planli' | 'kapandi') => send<{ items: SessionHead[] }>('GET', `${S}${qs({ state })}`, undefined, 30_000),
  create: (b: SessionInput) => send<SessionHead>('POST', S, b, 30_000),
  get: (id: string) => send<SessionDetail>('GET', `${S}/${enc(id)}`, undefined, 30_000),
  update: (id: string, b: SessionInput) => send<SessionHead>('PATCH', `${S}/${enc(id)}`, b, 30_000),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `${S}/${enc(id)}`, undefined, 30_000),
  addAgenda: (id: string, applicationId: string) => send<{ ok: boolean }>('POST', `${S}/${enc(id)}/agenda`, { applicationId }, 30_000),
  removeAgenda: (id: string, appId: string) => send<{ ok: boolean }>('DELETE', `${S}/${enc(id)}/agenda/${enc(appId)}`, undefined, 30_000),
  vote: (id: string, appId: string, b: { vote: VoteChoice; mission: number | null; publishing: number | null; commercial: number | null; note: string }) =>
    send<Vote>('PUT', `${S}/${enc(id)}/votes/${enc(appId)}`, b, 30_000),
  decide: (id: string, appId: string, b: { decision: string; note?: string; printRun?: string; price?: string; royalty?: string; publishOn?: string }) =>
    send<{ ok: boolean; decision: string | null; status?: string }>('POST', `${S}/${enc(id)}/decisions/${enc(appId)}`, b, 30_000),
  close: (id: string) => send<{ ok: boolean; postponed: number }>('POST', `${S}/${enc(id)}/close`, {}, 30_000),
};
