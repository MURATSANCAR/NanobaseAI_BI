import { ENGINE_BASE, ENGINE_ENABLED, EngineAuthError, EngineForbiddenError, freshHeaders } from '../engine';
import { httpErrorText } from '../httpError';

/** H1 Kategori ağacı ekranının köprü uçları: /api/v1/categories/*. Portal CRM'e ve T-soft'a yazmaz. */

export type ProfileStatus = 'yok' | 'taslak' | 'kismi' | 'onayli' | 'red';
export type TreeStatus = 'taslak' | 'onay-bekliyor' | 'yururlukte' | 'arsiv';
export type Level = 'yayinevi' | 'ana' | 'alt' | 'altalt';
export type FieldKey = 'kategori' | 'tur' | 'hedef_kitle' | 'yas' | 'tema' | 'etiket';
export type FieldState = 'yok' | 'oneri' | 'kabul' | 'duzeltme' | 'ret';
export type FieldValue = string | string[] | null;

export type Me = {
  username: string;
  display: string;
  crmId: string | null;
  canPropose: boolean;
  canEditTree: boolean;
  canApproveTree: boolean;
  canDecide: boolean;
  everyone: boolean;
  canExport: boolean;
};

export type Job = { running: boolean; step: string | null; startedAt: string | null; finishedAt: string | null; error: string | null };

export type Meta = {
  levels: Record<Level, string>;
  systems: Record<string, string>;
  fields: Record<FieldKey, { label: string; kind: 'node' | 'one' | 'many' }>;
  profileStatus: Record<ProfileStatus, string>;
  treeStatus: Record<TreeStatus, string>;
  rules: Record<string, { label: string; help: string; field: FieldKey | null }>;
  thresholds: Record<string, number>;
  job: Job;
  me: Me;
};

export type TreeInfo = {
  id: string;
  version: number;
  status: TreeStatus;
  statusLabel: string;
  note: string | null;
  createdBy: string;
  createdAt: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
  submittedBy: string | null;
  submittedAt: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  decisionNote: string | null;
};

export type Ref = { id: string; name: string | null };

export type TreeNode = {
  id: string;
  parentId: string | null;
  level: Level;
  name: string;
  code: string | null;
  sort: number;
  status: 'aktif' | 'pasif';
  path: string;
  depth: number;
  mappings: Record<string, Ref[]>;
  books?: number;
  approved?: number;
  sales?: number;
};

export type TreeState = {
  inForce: (TreeInfo & { nodes: TreeNode[] }) | null;
  draft: (TreeInfo & { nodes: TreeNode[] }) | null;
  versions: TreeInfo[];
  levels: Record<Level, string>;
  systems: Record<string, string>;
  suggestion?: { books: number; placed: number; skipped: Record<string, number>; nodes: number; mappings: number; minBooks: number };
};

export type Impact = {
  added: Array<{ nodeId: string; path: string }>;
  removed: Array<{ nodeId: string; path: string }>;
  renamed: Array<{ nodeId: string; from: string; to: string }>;
  moved: Array<{ nodeId: string; fromPath: string; toPath: string }>;
  mappingChanges: Array<{ nodeId: string; path: string; added: [string, string][]; removed: [string, string][] }>;
  bookMoves: Array<{ from: string | null; fromPath: string | null; to: string | null; toPath: string | null; books: number }>;
  books: { total: number; moved: number; newlyPlaced: number; lost: number };
  orphanedApproved: Array<{ bookId: string; name: string; path: string; priority: number }>;
  m2: Array<{ kind: string; id: string; name: string; before: string[]; after: string[] }>;
  withoutTsoft: Array<{ nodeId: string; path: string }>;
};

export type Overview = {
  activeBooks: number;
  status: Record<ProfileStatus, number>;
  statusLabels: Record<ProfileStatus, string>;
  fill: Array<{ key: string; label: string; filled: number; total: number }>;
  links: Record<string, number>;
  selling: number;
  sellingApproved: number;
  placed: number;
  findings: { open: number; byRule: Record<string, number>; labels: Record<string, string> };
  tree: { inForce: TreeInfo | null; draft: TreeInfo | null };
  sync: { at?: string; previousAt?: string; crm?: { books: number }; logo?: { start?: string; end?: string; months?: number; error?: string };
    tsoft?: { products?: number; categories?: number; syncedAt?: string | null; error?: string } };
  priority: { start?: string; end?: string; months?: number };
  tsoft: { syncedAt: string | null; products: number | null; categories: number };
  mine: { pending: number; books: number };
  crmDiff: { rows: number; stale: number; books: number };
  job: Job;
};

export type BookRow = {
  bookId: string;
  stockCode: string | null;
  isbn?: string | null;
  name: string | null;
  author: string | null;
  brand: string | null;
  kitaplik: string | null;
  status: ProfileStatus;
  statusLabel: string;
  priority: number;
  findings: number;
  nodeId: string | null;
  resolvedNodeId: string | null;
  nodePath?: string | null;
  proposedPath?: string | null;
  pending: number;
  lowConfidence: number;
  updatedAt: string | null;
  updatedBy: string | null;
};

export type Evidence = { kind: string; text: string; term?: string; probability?: number };

export type ProfileField = {
  state: FieldState;
  current?: FieldValue;
  currentPath?: string | null;
  proposed?: FieldValue;
  proposedPath?: string | null;
  value?: FieldValue;
  valuePath?: string | null;
  source?: string;
  method?: string;
  confident?: boolean;
  probability?: number | null;
  margin?: number | null;
  evidence?: Evidence[];
  alternatives?: Array<{ nodeId: string; label: string; probability: number; path?: string | null }>;
  weak?: Array<{ term: string; probability: number; kind: string; text: string }>;
  added?: string[];
  by?: string;
  at?: string;
  note?: string | null;
};

export type CrmSnapshot = {
  id: string;
  stok: string | null;
  ad: string | null;
  isbn: string | null;
  ean: string | null;
  yazar: string | null;
  yayincilikStatusu: string | null;
  kitaplik: Ref | null;
  dizi: Ref | null;
  marka: Ref | null;
  hedefKitle: { code: number; label: string | null } | null;
  yas: { bas: number | null; bit: number | null } | null;
  yasMetni: string | null;
  turMetni: string | null;
  rafTuru: string | null;
  web: string | null;
  editor: Ref | null;
  yonetmen: Ref | null;
  tsoftAktif: boolean;
  ozetVar: boolean;
  urunkategorisi: Ref[];
  raf: Ref[];
  sergilenecek: Ref[];
  tema: Ref[];
  anahtarkelime: Ref[];
  tur: Ref[];
  tsoft?: { categoryId: string | null; categoryName: string | null; categoryPath: string | null } | null;
};

export type Finding = {
  id: string;
  bookId: string;
  rule: string;
  ruleLabel: string;
  field: FieldKey | null;
  detail: Record<string, unknown>;
  status: 'acik' | 'duzeltildi' | 'yoksay';
  firstSeen: string | null;
  lastSeen: string | null;
  decidedBy: string | null;
  note: string | null;
  name?: string | null;
  stockCode?: string | null;
  brand?: string | null;
  kitaplik?: string | null;
  priority?: number;
  profileStatus?: ProfileStatus;
};

export type BookDetail = BookRow & {
  fields: Partial<Record<FieldKey, ProfileField>>;
  fieldDefs: Meta['fields'];
  crm: CrmSnapshot;
  resolution: { nodeId: string | null; path: string | null; reason: string; candidatePaths: string[]; hits: Array<{ systemLabel: string; value: string }> };
  events: Array<{ field: string; old: unknown; new: unknown; action: string; user: string; at: string | null }>;
  findingsList: Finding[];
  tree: TreeInfo | null;
  canDecide: boolean;
  modelCalls?: number;
};

export type BookText = { ozet: string | null; spot: string | null; anahtarMetin: string | null; tanitim: string | null; oneCikan: string | null; sayfa: number | null; ilkYayin: string | null };

export type Rule = { key: string; label: string; help: string; field: FieldKey | null; enabled: boolean; params: Record<string, number>; updatedBy: string | null; updatedAt: string | null };

export type DiffRow = {
  bookId: string;
  stockCode: string | null;
  name: string | null;
  brand: string | null;
  priority: number;
  field: FieldKey;
  fieldLabel: string;
  crmField: string;
  crmValue: string | null;
  portalValue: string | null;
  action: 'ekle' | 'cikar' | 'degistir' | 'bilgi';
  note?: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  ageDays: number | null;
  stale: boolean;
};

export type Options = Record<string, Array<{ id: string; name: string; active?: boolean; products?: number }>> & { etiket: string[] };

export type Tag = { tag: string; source: string; status: string; mergedInto: string | null; books: number; createdBy: string | null; createdAt: string | null };

export type Paged<T> = { items: T[]; total: number; page: number; pageSize: number; note?: string };

const B = '/api/v1/categories';

async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 120_000): Promise<T> {
  if (!ENGINE_ENABLED) throw new Error('Bu kurulumda veri bağlantısı tanımlı değil.');
  const res = await fetch(`${ENGINE_BASE}${B}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401) throw new EngineAuthError();
  if (res.status === 403) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new EngineForbiddenError(msg || 'Bu işleme yetkiniz yok.');
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

const qs = (o: Record<string, string | number | boolean | undefined | null>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};
const enc = encodeURIComponent;

export type BookFilter = { q?: string; owner?: string; status?: string; brand?: string; kitaplik?: string; selling?: string; finding?: string; node?: string; order?: string; page?: number };

export const categoriesApi = {
  meta: () => send<Meta>('GET', '/meta'),
  overview: () => send<Overview>('GET', '/overview'),
  status: () => send<Job>('GET', '/status'),
  mine: () => send<{ pending: number; books: number }>('GET', '/mine'),
  refresh: () => send<Job & { started: boolean }>('POST', '/refresh', {}),
  options: () => send<Options>('GET', '/options'),
  tree: () => send<TreeState>('GET', '/tree'),
  version: (id: string) => send<TreeInfo & { nodes: TreeNode[] }>('GET', `/tree/versions/${enc(id)}`),
  saveTree: (body: { nodes: Array<Pick<TreeNode, 'id' | 'parentId' | 'level' | 'name' | 'code' | 'sort' | 'status'>>; note?: string | null; version?: number }) =>
    send<TreeState>('PUT', '/tree', body),
  openDraft: () => send<TreeState>('POST', '/tree/open', {}),
  discardDraft: () => send<TreeState>('DELETE', '/tree/draft'),
  suggest: (replace: boolean) => send<TreeState>('POST', '/tree/suggest', { replace }, 300_000),
  submit: () => send<TreeState>('POST', '/tree/submit', {}),
  withdraw: () => send<TreeState>('POST', '/tree/withdraw', {}),
  approve: (version: number, note?: string) => send<TreeState>('POST', '/tree/approve', { version, note }, 300_000),
  reject: (version: number, note: string) => send<TreeState>('POST', '/tree/reject', { version, note }),
  impact: () => send<Impact>('GET', '/tree/impact', undefined, 300_000),
  setMappings: (nodeId: string, system: string, items: Array<{ externalId: string; externalName?: string | null }>) =>
    send<{ nodeId: string; system: string; items: unknown[] }>('PUT', '/mappings', { nodeId, system, items }),
  books: (f: BookFilter) => send<Paged<BookRow>>('GET', `/books${qs(f)}`),
  book: (id: string) => send<BookDetail>('GET', `/books/${enc(id)}`),
  bookText: (id: string) => send<BookText>('GET', `/books/${enc(id)}/text`),
  propose: (id: string, body: { reset?: boolean; fields?: FieldKey[] } = {}) => send<BookDetail>('POST', `/books/${enc(id)}/propose`, body, 600_000),
  decide: (id: string, body: { fields?: Partial<Record<FieldKey, { action: 'kabul' | 'duzeltme' | 'ret'; value?: FieldValue; note?: string }>>; all?: 'kabul' }) =>
    send<BookDetail & { changed: Record<string, unknown>; newTags: string[] }>('POST', `/books/${enc(id)}/decision`, body),
  findings: (f: { rule?: string; status?: string; owner?: string; q?: string; page?: number }) =>
    send<Paged<Finding> & { openByRule: Record<string, number>; rules: Rule[] }>('GET', `/findings${qs(f)}`),
  findingStatus: (id: string, status: 'acik' | 'yoksay', note?: string) => send<Finding>('POST', `/findings/${enc(id)}/status`, { status, note }),
  applyFindings: (ids: string[]) => send<{ applied: Array<{ id: string }>; skipped: Array<{ id: string; reason: string }> }>('POST', '/findings/apply', { ids }, 300_000),
  updateRule: (key: string, body: { enabled?: boolean; params?: Record<string, number> }) => send<Rule>('PUT', `/rules/${enc(key)}`, body, 300_000),
  crmDiff: (f: { owner?: string; q?: string }) =>
    send<{ items: DiffRow[]; total: number; books: number; stale: number; staleDays: number; byField: Record<string, number> }>('GET', `/crm-diff${qs(f)}`),
  crmDiffUrl: (owner?: string) => `${ENGINE_BASE}${B}/crm-diff/export.xlsx${qs({ owner })}`,
  tags: (f: { status?: string; q?: string; page?: number }) => send<Paged<Tag> & { counts: Record<string, number> }>('GET', `/tags${qs(f)}`),
  decideTag: (tag: string, status: 'aktif' | 'red' | 'birlesti', mergedInto?: string) => send<Tag>('POST', '/tags/decision', { tag, status, mergedInto }),
};

/* ------------------------------------------------------------------ biçim */

const int0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
export const fmtInt = (v: number | null | undefined) => (v === null || v === undefined ? '—' : int0.format(v));
export const fmtPct = (part: number, total: number) => (total ? `%${Math.round((part / total) * 100)}` : '—');
export const fmtProb = (p: number | null | undefined) => (p === null || p === undefined ? null : `%${Math.round(p * 100)}`);

const dayFmt = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Europe/Istanbul' });
export const fmtDay = (iso: string | null | undefined) => (iso ? dayFmt.format(new Date(iso)) : '—');

export const STATUS_TONE: Record<ProfileStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  yok: 'muted',
  taslak: 'violet',
  kismi: 'warn',
  onayli: 'ok',
  red: 'err',
};

export const TREE_TONE: Record<TreeStatus, 'ok' | 'warn' | 'err' | 'muted' | 'violet'> = {
  taslak: 'muted',
  'onay-bekliyor': 'warn',
  yururlukte: 'ok',
  arsiv: 'muted',
};

export const ACTION_TEXT: Record<DiffRow['action'], string> = { ekle: 'Ekle', cikar: 'Çıkar', degistir: 'Değiştir', bilgi: 'Bilgi' };

export function showValue(v: FieldValue | undefined, path?: string | null): string {
  if (path) return path;
  if (v === null || v === undefined || v === '') return '—';
  if (Array.isArray(v)) return v.length ? v.join(', ') : '—';
  return v;
}
