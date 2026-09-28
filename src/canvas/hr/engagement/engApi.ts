import { hrDownload, hrSend, qs } from '../hrApi';

/** M58 Çalışan deneyimi ve bağlılık uçları (/api/v1/hr/engagement/*) ve oturumsuz anket formu (/api/v1/hr/survey-public/*). */

const E = '/engagement';
const PUB = '/survey-public';
const enc = encodeURIComponent;

export type QType = 'enps' | 'likert5' | 'secim' | 'acik';
export type Question = { key: string; text: string; type: QType; options?: string[] };
export type Template = {
  id: string; kind: string; kindLabel: string; title: string; questions: Question[]; version: number;
  state: 'taslak' | 'onayda' | 'yururlukte' | 'arsiv'; stateLabel: string; submittedBy: string | null; approvedBy: string | null;
  approvedAt: string | null; updatedBy: string | null; updatedAt: string | null;
};
export type SurveyState = 'taslak' | 'planli' | 'acik' | 'kapandi';
export type Survey = {
  id: string; templateId: string | null; templateVersion: number | null; kind: string; kindLabel: string; title: string; questions: Question[];
  opensAt: string; closesAt: string; audience: { units?: string[] }; audienceNames: string[] | null; unitBreakdown: boolean; minGroup: number | null;
  state: SurveyState; stateLabel: string; invited: number; responded: number; paperIssued: number; paperUsed: number;
  resultsSharedAt: string | null; createdBy: string | null; openedAt: string | null; closedAt: string | null; updatedAt: string | null;
};
export type Item =
  | { key: string; text: string; type: 'enps'; n: number; enps: number | null; dist: number[] }
  | { key: string; text: string; type: 'likert5'; n: number; mean: number | null; favorable: number | null; dist: number[] }
  | { key: string; text: string; type: 'secim'; n: number; counts: Record<string, number> };
export type UnitRow = { unitId: string; unitName: string | null; n: number | null; shown: boolean; mergedInto: string | null };
export type Result = {
  survey: Survey; scope: string; suppressed: boolean; reason?: string; message?: string; mergedInto?: string; unitName?: string;
  n?: number; enps?: number | null; index?: number | null; items?: Item[]; units?: UnitRow[] | null; minGroup?: number;
};
export type Themes = {
  suppressed: boolean; message?: string; total?: number; unclassified?: number;
  themes: { theme: string; count: number; summary: string | null; note: string | null }[];
  comments: { questionKey: string; text: string; theme: string | null; probability: number | null }[] | null;
};
export type Progress = {
  state: SurveyState; invited: number; responded: number; paperIssued: number; paperUsed: number; responses: number; rate: number | null;
  audienceActive: number; noAccount: number; note: string;
};
export type TrendRow = { surveyId: string; title: string; kind: string; closesAt: string; n: number | null; enps: number | null; index: number | null; suppressed: boolean; rate: number | null };
export type Suggestion = {
  id: string; createdDay: string; anonymous: boolean; author: string | null; text: string; topic: string | null; topicProb: number | null;
  topicSource: 'zeki' | 'ik' | null; personal: boolean; routedUnitId: string | null; routedUnitName: string | null; routedAt: string | null;
  state: 'yeni' | 'yonlendirildi' | 'cevaplandi' | 'kapandi'; stateLabel: string; answer: string; answeredBy: string | null; answeredAt: string | null;
};
export type Action = {
  id: string; surveyId: string | null; unitId: string | null; unitName: string | null; questionKey: string | null; title: string;
  ownerEmployeeId: string | null; ownerName: string | null; dueOn: string | null; state: 'acik' | 'devam' | 'tamam' | 'iptal'; stateLabel: string;
  note: string; createdBy: string | null; updatedAt: string | null; closedAt: string | null; canEdit: boolean;
};
export type EngMeta = {
  kinds: Record<string, string>; qtypes: Record<QType, string>; surveyStates: Record<SurveyState, string>; suggestionStates: Record<string, string>;
  actionStates: Record<string, string>; themes: string[]; topics: string[]; personalTopic: string; anonymity: string; modelVar: boolean;
  units: { id: string; name: string; parentId: string | null }[];
  me: { username: string; display: string; employeeId: string | null; managedUnits: string[];
    can: { dashboard: boolean; surveys: boolean; unitResult: boolean; comments: boolean; suggestionAdmin: boolean; suggestionAnswer: boolean; actions: boolean; export: boolean } };
};
export type PublicForm = { title: string; kindLabel: string; closesAt: string; open: boolean; alreadyResponded: boolean; questions: Question[]; anonymity: string };

export const engApi = {
  meta: () => hrSend<EngMeta>('GET', `${E}/meta`),
  mySurveys: () => hrSend<{ items: { id: string; title: string; kindLabel: string; closesAt: string; questions: number; responded: boolean }[] }>('GET', `${E}/me/surveys`),
  link: (sid: string) => hrSend<{ token: string }>('POST', `${E}/me/surveys/${enc(sid)}/link`),
  publicForm: (token: string) => hrSend<PublicForm>('GET', `${PUB}/${enc(token)}`),
  submit: (token: string, answers: Record<string, unknown>) => hrSend<{ ok: boolean; message: string }>('POST', `${PUB}/${enc(token)}`, { answers }),
  templates: () => hrSend<{ items: Template[]; starters: Record<string, { title: string; questions: Question[] }> }>('GET', `${E}/templates`),
  createTemplate: (b: Record<string, unknown>) => hrSend<Template>('POST', `${E}/templates`, b),
  updateTemplate: (id: string, b: Record<string, unknown>) => hrSend<Template>('PATCH', `${E}/templates/${enc(id)}`, b),
  templateAction: (id: string, a: 'submit' | 'approve' | 'reject' | 'archive') => hrSend<Template>('POST', `${E}/templates/${enc(id)}/${a}`),
  surveys: () => hrSend<{ items: Survey[] }>('GET', `${E}/surveys`),
  createSurvey: (b: Record<string, unknown>) => hrSend<Survey>('POST', `${E}/surveys`, b),
  updateSurvey: (id: string, b: Record<string, unknown>) => hrSend<Survey>('PATCH', `${E}/surveys/${enc(id)}`, b),
  open: (id: string) => hrSend<Survey>('POST', `${E}/surveys/${enc(id)}/open`),
  close: (id: string) => hrSend<Survey>('POST', `${E}/surveys/${enc(id)}/close`),
  paperCodes: (id: string, n: number, unit?: string) => hrSend<{ codes: string[] }>('POST', `${E}/surveys/${enc(id)}/paper-codes${qs({ n, unit })}`),
  progress: (id: string) => hrSend<Progress>('GET', `${E}/surveys/${enc(id)}/progress`),
  results: (id: string, scope = 'sirket') => hrSend<Result>('GET', `${E}/surveys/${enc(id)}/results${qs({ scope })}`),
  themes: (id: string, raw = false) => hrSend<Themes>('GET', `${E}/surveys/${enc(id)}/themes${qs({ raw: raw ? 1 : undefined })}`),
  refreshThemes: (id: string) => hrSend<{ classified: number; themes: number }>('POST', `${E}/surveys/${enc(id)}/themes/refresh`, undefined, 600_000),
  share: (id: string) => hrSend<Survey>('POST', `${E}/surveys/${enc(id)}/share`),
  exportCsv: (id: string) => hrDownload(`${E}/surveys/${enc(id)}/export.csv`, 'anket.csv'),
  trend: () => hrSend<{ items: TrendRow[]; suggestions: { total: number; answered: number; open: number; avgDays: number | null } }>('GET', `${E}/trend`),
  myUnits: () => hrSend<{ units: { id: string; name: string | null }[]; results: Result[] }>('GET', `${E}/my-units`),
  createSuggestion: (text: string, anonymous: boolean) => hrSend<{ id: string; anonymous: boolean; followCode: string | null }>('POST', `${E}/suggestions`, { text, anonymous }),
  suggestions: (state = '') => hrSend<{ items: Suggestion[]; topics: string[] }>('GET', `${E}/suggestions${qs({ state })}`),
  mySuggestions: () => hrSend<{ items: Suggestion[] }>('GET', `${E}/suggestions/mine`),
  track: (code: string) => hrSend<Suggestion>('GET', `${E}/suggestions/track/${enc(code)}`),
  suggestionAction: (id: string, a: 'route' | 'topic' | 'answer' | 'close', b: Record<string, unknown>) => hrSend<Suggestion>('POST', `${E}/suggestions/${enc(id)}/${a}`, b),
  actions: (survey = '') => hrSend<{ items: Action[]; canCreate: boolean }>('GET', `${E}/actions${qs({ survey })}`),
  createAction: (b: Record<string, unknown>) => hrSend<Action>('POST', `${E}/actions`, b),
  updateAction: (id: string, b: Record<string, unknown>) => hrSend<Action>('PATCH', `${E}/actions/${enc(id)}`, b),
};

export const SURVEY_TONE: Record<SurveyState, 'ok' | 'warn' | 'muted' | 'violet'> = { taslak: 'muted', planli: 'warn', acik: 'ok', kapandi: 'violet' };
export const fmtNum = (v: number | null | undefined, digits = 1) =>
  v === null || v === undefined ? '—' : new Intl.NumberFormat('tr-TR', { maximumFractionDigits: digits }).format(v);
