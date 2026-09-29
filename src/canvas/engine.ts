/**
 * Semantic bridge istemcisi (:8795). Kokpitin kullandığı servis budur; Logo
 * veritabanına bağlı olan da odur. Portal API'si (:8790) iş verisi taşımıyor.
 *
 * Tarayıcıdan erişim nginx üzerinden `/timas/api/...` yoluna gider ve oturum
 * ister (auth_request). Oturum yoksa 401 döner; kartlar bunu "oturum gerekli"
 * diye gösterir, sahte sayı üretmez.
 */
import type { DbTiming } from './DbTiming';
import type { Kaynaklar } from './components/sqlInfo';
import { httpErrorText } from './httpError';

const RAW_BASE = (import.meta.env.VITE_ENGINE_BASE as string | undefined) ?? '';
export const ENGINE_BASE = RAW_BASE.replace(/\/$/, '');
export const ENGINE_ENABLED = ENGINE_BASE.length > 0;

/** Motor 401 dedikten sonra tekrar tekrar denemek konsolu kirletiyor ve
 *  sunucuyu boşuna yoruyor. Giriş yapılana kadar yoklama durur. */
let authBlocked = false;
export const isAuthBlocked = (): boolean => authBlocked;
export const clearAuthBlock = (): void => {
  authBlocked = false;
};

/** Üst şeritteki "Verileri yenile" düğmesi basıldıktan sonraki kısa pencerede başlayan okumalar
 *  `X-Data-Refresh: 1` taşır; köprü o istekte beş dakikalık önbelleği atlayıp kaynağı okur.
 *  Otomatik (5 dk) yenilemeler başlığı taşımaz, önbellekten gelir. */
let freshUntil = 0;
export const requestFreshData = (ms = 3000): void => {
  freshUntil = Date.now() + ms;
};
export const freshHeaders = (): Record<string, string> => (Date.now() < freshUntil ? { 'X-Data-Refresh': '1' } : {});

export class EngineAuthError extends Error {
  constructor(message = 'ZEKİ AI oturumu gerekli') {
    super(message);
    this.name = 'EngineAuthError';
  }
}

/** Oturum var ama bu sayfa/işlem kişinin rolünde yok (köprünün sayfa kapısı, 403 FORBIDDEN). Oturum
 *  düşmediği için yoklamalar durdurulmaz; EngineAuthError'dan türediği için eski denetimler aynı davranır. */
export class EngineForbiddenError extends EngineAuthError {
  constructor(message = 'Bu sayfaya yetkiniz yok.') {
    super(message);
    this.name = 'EngineForbiddenError';
  }
}

/** Uç cevabına eklenen sorgu bilgisi (her rakamın SQL'i ve hesabı). */
export type WithK<T> = T & { kaynaklar?: Kaynaklar };

export type SqlResult<T> = DbTiming & {
  columns: Array<{ name: string; type: string }>;
  records: T[];
  totalRows?: number;
  truncated?: boolean;
  /** Köprünün veritabanında gerçekten koşturduğu metin (dönem ve yıl kopyaları çözülmüş). */
  physicalSql?: string;
  /** Sorgu bilgisi: gösterilen ve kopyalanan SQL fiziksel metindir. */
  kaynaklar?: Kaynaklar;
};

async function post<T>(path: string, body: unknown, timeoutMs = 45_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...freshHeaders() },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) throw new Error(httpErrorText(res.status));
  return (await res.json()) as T;
}

/** Kataloğa doğrulatılmış SQL çalıştırır. Motor katalog dışı tabloyu reddeder. */
/** limit 0: motorun kendi üst sınırı. İstemci ayrıca kesmez; kesilirse `truncated` gelir. */
export function runSql<T>(sql: string, limit = 0): Promise<SqlResult<T>> {
  return post<SqlResult<T>>('/api/v1/run_sql', { sql, limit });
}

export type EngineInfo = {
  dataSource?: string;
  models?: number;
  relationships?: number;
  certified?: number;
  catalogVersion?: number;
  project?: string;
  deployed?: boolean;
};

export async function engineInfo(): Promise<EngineInfo> {
  const res = await fetch(`${ENGINE_BASE}/api/v1/engine`, {
    credentials: 'include',
    headers: freshHeaders(),
    signal: AbortSignal.timeout(15_000),
  });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) throw new Error(httpErrorText(res.status));
  return (await res.json()) as EngineInfo;
}

export type AskAnswer = DbTiming & {
  id?: string;
  /** Soru kaydının kimliği (sl_query_log): cevabın altındaki «Doğru / Kısmen / Yanlış» bununla yazılır (M50). */
  queryId?: string;
  type?: string;
  /** Mantıksal SQL (katalog adları); panoya kart eklerken saklanır, kullanıcıya gösterilmez. */
  sql?: string;
  /** Köprünün Logo/CRM'de koşturduğu fiziksel SQL; ekranda gösterilen ve kopyalanan budur. */
  physicalSql?: string;
  /** Sorgu bilgisi (cevaptaki her rakamın SQL'i). */
  kaynaklar?: Kaynaklar;
  summary?: string;
  explanation?: string;
  columns?: Array<{ name: string; type: string }>;
  records?: Array<Record<string, unknown>>;
  rowCount?: number;
  latency_ms?: number;
  /** Belirsiz kelimelerin nasıl yorumlandığı ("bakiye" → Cari bakiyesi). Yoksa ya da boşsa hiçbir şey gösterilmez. */
  interpretations?: AnswerInterpretation[];
  /** Boş cevapta dönem verinin bittiği günden sonra kaldıysa: son gün ve sorunun o döneme kurulmuş hâli. */
  dataEnd?: { lastDay: string | null; note: string; suggestion: { question: string; start: string; end: string } | null } | null;
  /** «Neden?»: ölçü katalogda toplanabilir bir satış satırı ölçüsü ve soruda dönem varsa `ok`; değilse nedeni. */
  neden?: { ok: boolean; neden?: string; olcu?: string; birim?: string; bas?: string; bit?: string } | null;
};

/** Belirsiz bir kelimenin seçilen anlamı. */
export type InterpretationChoice = { label: string; conceptId?: string };
/** Seçilmeyen anlam; `rephrase` sorudaki kelimenin yerine konup soru yeniden sorulur. */
export type InterpretationAlternative = InterpretationChoice & { rephrase: string };
export type AnswerInterpretation = {
  term: string;
  chosen: InterpretationChoice;
  /** En fazla 3. */
  alternatives: InterpretationAlternative[];
  /** context: bağlamdan çıkarıldı; default: bağlam yoktu, en olası anlam alındı. */
  basis: 'context' | 'default';
};

/** Doğal dil sorusu. Motor SQL üretir, çalıştırır ve özetler. */
export function ask(question: string): Promise<AskAnswer> {
  return post<AskAnswer>('/api/v1/ask', { question, language: 'TR', execute: true, sampleSize: 50 }, 180_000);
}

/** Tablonun ait olduğu iş sistemi: Logo ERP ya da CRM. Motor şemadan belirler. */
export type DataSource = 'logo' | 'crm';

export type ConceptMapping = {
  id?: string;
  source?: DataSource | null;
  entity?: string;
  table_pattern?: string;
  column?: string | null;
  operator?: string | null;
  values?: string[];
  /** Metriğin hesabı: SUM(STLINE.AMOUNT) gibi. */
  formula?: string | null;
  time_primitive?: string | null;
  extra?: { func?: string; aliases?: string[]; conditions?: string[] };
};

export type Concept = {
  id: string;
  term: string;
  normalized_term?: string;
  semantic_type: string;
  status: string;
  domain?: string;
  confidence?: number;
  version?: number;
  synonyms?: string[];
  created_at?: string;
  updated_at?: string;
  explain?: {
    score?: number;
    human_reason?: string;
    schema_drift?: string;
    support?: { doc?: number; llm?: number; human?: number; validated_queries?: number };
    breakdown?: Record<string, number>;
    gate?: { passed?: boolean; reasons?: string[]; mode?: string; min_support?: number };
    human_certified_by?: string;
  };
};

export type ConceptRow = { concept: Concept; mappings?: ConceptMapping[] };

export type TableRow = {
  tableName: string;
  tablePattern?: string;
  entity?: string;
  schema?: string;
  description?: string;
  rowCount?: number;
  columnCount?: number;
  certifiedColumns?: number;
  primaryKey?: string[];
  scannedAt?: string;
  columns?: Array<{ name: string; type?: string; nullable?: boolean; isPrimaryKey?: boolean; sensitive?: boolean }>;
};

export type ReviewItem = {
  id: string;
  term: string;
  /** Kök terimin okunur hâli: "malzem" → "malzeme". Motor dağıtımın kendi kelimelerinden üretir. */
  label?: string;
  type: string;
  confidence?: number;
  source?: DataSource | null;
  mapping?: {
    entity?: string;
    column?: string | null;
    table_pattern?: string;
    operator?: string | null;
    values?: string[];
    formula?: string | null;
    extra?: { conditions?: string[]; ref_entity?: string; ref_column?: string; func?: string };
  };
  /** Motorun düz Türkçe cümlesi: bu terim neye karşılık geliyor. */
  plain?: string;
  /** Kolonun iş anlamı (varsa değer kodlarıyla birlikte). */
  columnMeaning?: string | null;
  /** Kolonda gerçekten görülen değerler ve satır sayıları. */
  observed?: Array<{ value: string; rows: number; label?: string }>;
  /** Gözlenen değerlerin okunduğu şema taraması. */
  scannedAt?: string | null;
  evidence?: Record<string, number>;
  counterEvidence?: number;
};

async function get<T>(path: string, timeoutMs = 20_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, { credentials: 'include', headers: freshHeaders(), signal: AbortSignal.timeout(timeoutMs) });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) throw new Error(httpErrorText(res.status));
  return (await res.json()) as T;
}

/** Veri sözlüğü: sertifikalı kavramlar. */
export function concepts(status = 'CERTIFIED', limit = 200) {
  return get<{ items: ConceptRow[] }>(`/api/v1/semantic/concepts?status=${status}&limit=${limit}`);
}

/** Şema envanteri: tablolar, açıklamaları, satır sayıları ve kolonları. */
export function inventory() {
  return get<{ tables: TableRow[]; tableCount?: number; columnCount?: number }>('/api/v1/schema/inventory', 60_000);
}

export type GapItem = {
  tablePattern: string;
  example: string;
  source?: DataSource;
  copies: number;
  description: string | null;
  tableMissing: boolean;
  rows: number;
  columns: number;
  missing: number;
  suggestions: number;
};

export type GapSuggestion = { id: string; text: string; confidence: number; model?: string };

export type GapColumn = {
  name: string;
  type?: string;
  status: 'UNDEFINED' | 'DESCRIBED' | 'CANDIDATE' | 'CERTIFIED';
  isPrimaryKey?: boolean;
  ref?: string | null;
  sensitive?: boolean;
  distinct?: number | null;
  topValues: Array<[string, number]>;
  unit?: string | null;
  derived: string[];
  description: string | null;
  annotationId: string | null;
  suggestion: GapSuggestion | null;
};

export type GapDetail = {
  tablePattern: string;
  example: string;
  source?: DataSource;
  tables: Array<{ name: string; rows: number }>;
  description: string | null;
  tableAnnotationId: string | null;
  rows: number;
  /** Satır sayısı ve örnek değerler şema taramasında okundu (canlı sorgu değil). */
  scannedAt?: string | null;
  primaryKey?: string[];
  missing: GapColumn[];
  described: GapColumn[];
};

export type GapSummary = {
  patterns: number;
  patternsWithGaps: number;
  tablesWithoutDescription: number;
  columns: number;
  missingColumns: number;
  suggestions: number;
  bySource?: Record<DataSource, number>;
};

/** Veri sözlüğü: tablo kalıpları (yıl/firma kopyaları tek satır), eksik açıklamalar ve yazma uçları. */
export const gapsApi = {
  list: () => get<{ summary: GapSummary; items: GapItem[] }>('/api/v1/schema/gaps', 120_000),
  detail: (tablePattern: string) =>
    get<GapDetail>(`/api/v1/schema/gaps/detail?tablePattern=${encodeURIComponent(tablePattern)}`, 60_000),
  describe: (tablePattern: string, column: string | null, text: string) =>
    send<unknown>('POST', '/api/v1/schema/gaps/describe', { tablePattern, column, text }, 60_000),
  accept: (id: string) => send<unknown>('POST', `/api/v1/schema/gaps/suggestions/${encodeURIComponent(id)}/accept`, {}, 60_000),
  dismiss: (id: string) => send<unknown>('POST', `/api/v1/schema/gaps/suggestions/${encodeURIComponent(id)}/dismiss`, {}, 30_000),
};

export type Decision = 'APPROVE' | 'REJECT' | 'CORRECT';

/** Bir terim hakkında insanın kararı. CORRECT için açıklama zorunlu. */
export function decide(
  conceptId: string,
  body: { decision: Decision; note?: string; column?: string; entity?: string; term?: string; by?: string },
) {
  return post<{ ok?: boolean; status?: string; concept_id?: string }>(
    `/api/v1/semantic/concepts/${encodeURIComponent(conceptId)}/review`,
    body,
    60_000,
  );
}

/** Onay kuyruğu: insana sorulmayı bekleyen terimler. */
export function review(limit = 50) {
  return get<{ waiting: number; used: number; total: number; items: ReviewItem[] }>(
    `/api/v1/semantic/review?limit=${limit}`,
  );
}

/* ------------------------------------------------------------------ */
/* Eş anlamlılar — alan açıklamasından üretilir, insan onayıyla sözlüğe girer */
/* ------------------------------------------------------------------ */

export type VocabItem = {
  id: string;
  entity: string;
  column: string | null;
  term: string;
  role: 'COLUMN' | 'ENTITY' | 'METRIC';
  examples: string[];
  source: 'generated' | 'human';
  status: 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'DROPPED';
  reason?: string | null;
  conceptId?: string | null;
  decidedBy?: string | null;
  decidedAt?: string | null;
  createdAt?: string | null;
};
export type VocabGroup = { entity: string; column: string | null; source?: DataSource | null; items: VocabItem[] };
export type VocabCounts = Record<VocabItem['status'], number>;

export function vocabulary(status: 'PROPOSED' | 'APPROVED' | 'REJECTED' | 'DROPPED' | 'ALL' = 'PROPOSED') {
  return get<{ groups: VocabGroup[]; counts: VocabCounts }>(`/api/v1/semantic/vocabulary?status=${status}&limit=5000`, 60_000);
}
export function vocabularyGaps() {
  return get<{ items: Array<{ entity: string; tablePattern: string; column: string; type: string; source?: DataSource | null }> }>('/api/v1/semantic/vocabulary/gaps', 60_000);
}
export function vocabularyDecide(id: string, decision: 'APPROVE' | 'REJECT', note?: string) {
  return post<{ id: string; status: string; conceptId?: string | null }>(`/api/v1/semantic/vocabulary/${encodeURIComponent(id)}/decide`, { decision, note }, 60_000);
}
export function vocabularyAdd(entity: string, column: string | null, term: string) {
  return post<{ id: string; status: string; conceptId?: string | null }>('/api/v1/semantic/vocabulary', { entity, column, term }, 60_000);
}
export function vocabularyGenerate(entity: string, column?: string | null) {
  return post<{ started: boolean }>('/api/v1/semantic/vocabulary/generate', { entity, column }, 60_000);
}
/** Bir alan için kullanıcının cümlesi; motor ondan hem kavram adayı hem eş anlamlı üretir. */
export function annotate(tablePattern: string, column: string | null, text: string) {
  return post<{ annotation: { id: string } }>('/api/v1/schema/annotations', { tablePattern, column, text }, 60_000);
}

/* ------------------------------------------------------------------ */
/* Uyarılar — kural bir sorudur, kontrolü sunucu yapar                  */
/* ------------------------------------------------------------------ */

/** `olagandisi`: eşik yerine beklenen aralık (geçmiş 24 ayın aynı penceresi); eşik kolonu hassasiyettir (k). */
export type AlertCondition = 'gt' | 'gte' | 'lt' | 'lte' | 'olagandisi';

/** Beklenen aralık (kurala göre; model yok). `ok: false` ise nedeni yazılıdır, aralık uydurulmaz. */
export type AlertRange = {
  ok: boolean;
  neden?: string;
  alt?: number;
  merkez?: number;
  ust?: number;
  yontem?: 'mevsimsel' | 'medyan';
  nokta?: number;
  deger?: number;
  disinda?: boolean;
  donem?: string;
  gun?: string;
};

export type AlertSuggestion = AlertRange & {
  oneri?: { esik: number; gerekce: string; alt: number; ust: number; etiket: string } | null;
  kaynak?: { sql?: Array<{ ad: string; sql: string }> };
  /** Sorgu bilgisi: aralığın geçmiş okumalarının fiziksel SQL'i. */
  kaynaklar?: Kaynaklar;
};

export type AlertRule = {
  id: string;
  title: string;
  question: string;
  sql: string;
  column: string | null;
  condition: AlertCondition;
  threshold: number;
  recipients: string[];
  status: 'active' | 'paused';
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  last_value: number | null;
  last_checked_at: string | null;
  last_triggered_at: string | null;
  state: 'unknown' | 'ok' | 'triggered' | 'error';
  last_error: string | null;
  last_notified_at: string | null;
  last_notify: 'sent' | 'failed' | 'no_smtp' | 'no_recipient' | null;
  /** Son ölçümde değerin veritabanından gelme süresi. */
  last_db?: DbTiming | null;
  /** Günde bir hesaplanan beklenen aralık. */
  expected?: AlertRange | null;
};

export type AlertEmail = { configured: boolean; sender: string | null };

export type AlertInput = {
  title: string;
  question: string;
  condition: AlertCondition;
  threshold: number;
  recipients: string[];
  column?: string | null;
};

/** GET dışı istekler; motorun düz Türkçe hata mesajını olduğu gibi taşır. */
export async function send<T>(method: string, path: string, body?: unknown, timeoutMs = 180_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: { ...(method === 'GET' ? freshHeaders() : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 403) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } } | null;
    if (j?.detail?.code === 'FORBIDDEN') throw new EngineForbiddenError(j.detail.message);
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (res.status === 401) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

export const alertsApi = {
  list: () => send<{ user: string; alerts: AlertRule[]; email: AlertEmail; kaynaklar?: Kaynaklar }>('GET', '/api/v1/alerts'),
  create: (b: AlertInput) => send<AlertRule>('POST', '/api/v1/alerts', b),
  update: (id: string, b: Partial<AlertInput> & { status?: 'active' | 'paused' }) =>
    send<AlertRule>('PATCH', `/api/v1/alerts/${encodeURIComponent(id)}`, b),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/alerts/${encodeURIComponent(id)}`),
  check: (id?: string) =>
    send<{
      checked: number;
      triggered: number;
      notified: number;
      errors: Array<{ id: string; error: string }>;
      kaynaklar?: Kaynaklar;
    }>(
      'POST',
      `/api/v1/alerts/check${id ? `?id=${encodeURIComponent(id)}` : ''}`,
      {},
    ),
  /** Sorunun geçmişinden beklenen aralık ve koşula göre eşik önerisi (kurala göre). */
  suggest: (question: string, condition: AlertCondition) =>
    send<AlertSuggestion>('POST', '/api/v1/alerts/suggest', { question, condition }, 300_000),
};

/* ------------------------------------------------------------------ pano */

export type BoardRefresh = 'manual' | 'hourly' | 'daily';

export type BoardCardResult = SqlResult<Record<string, unknown>> & { at: number };

/** Sunucudaki kart: kişiye özel, son sonucuyla birlikte gelir. */
export type BoardCardDto = {
  id: string;
  title: string;
  note: string;
  question: string;
  sql: string;
  chart: string;
  depth: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
  sqlOpen: boolean;
  refresh: BoardRefresh;
  refreshAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  lastAutoAt: string | null;
  lastError: string | null;
  result: BoardCardResult | null;
};

/** Kolon başlıklarının Türkçe yazımı için sözcük haritası (bkz. board/Chart.tsx `humanize`). */
export const displayWordsApi = {
  get: () => get<{ words: Record<string, string>; version: string }>('/api/v1/semantic/display-words', 30_000),
};

/** CRM varlık/alan adı → CRM'in kendi Türkçe etiketi (başlık çevirici bunu kuraldan önce kullanır). */
export const crmNamesApi = {
  get: () =>
    get<{ entities: Record<string, string>; attributes: Record<string, string>; version: string }>('/api/v1/semantic/crm-names', 60_000),
};

export const boardApi = {
  load: () => send<{ user: string; cards: BoardCardDto[]; kaynaklar?: Kaynaklar }>('GET', '/api/v1/board', undefined, 30_000),
  save: (cards: unknown[]) => send<{ user: string; cards: BoardCardDto[] }>('PUT', '/api/v1/board', { cards }, 30_000),
  run: (id: string) => send<BoardCardResult>('POST', `/api/v1/board/cards/${encodeURIComponent(id)}/run`, {}),
  /** Sunucuda üretilen Excel kitabı: özet + kart başına sayfa, tam veri, Excel grafiği. Boş liste = bütün kartlar. */
  exportXlsx: async (ids: string[] = []): Promise<{ blob: Blob; name: string }> => {
    const q = ids.length ? `?ids=${encodeURIComponent(ids.join(','))}` : '';
    const res = await fetch(`${ENGINE_BASE}/api/v1/board/export.xlsx${q}`, {
      credentials: 'include',
      signal: AbortSignal.timeout(600_000),
    });
    if (res.status === 401 || res.status === 403) {
      authBlocked = true;
      throw new EngineAuthError();
    }
    if (!res.ok) {
      const j = (await res.json().catch(() => null)) as { detail?: { message?: string } | string } | null;
      const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
      throw new Error(msg || `Excel üretilemedi (${res.status})`);
    }
    const m = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '');
    return { blob: await res.blob(), name: m?.[1] ?? 'pano.xlsx' };
  },
};

/* ------------------------------------------------------------------ planlı raporlar */

export type ReportRecurrence = 'daily' | 'weekly' | 'monthly' | 'once';
export type ReportFormat = 'xlsx' | 'csv';
export type ReportStatus = 'active' | 'paused' | 'done';
export type ReportLastStatus = 'sent' | 'no_smtp' | 'no_recipient' | 'failed' | null;
export type ColumnFormat = 'auto' | 'text' | 'number' | 'money' | 'percent' | 'date';
/** Kişinin ekranda kurduğu kolon düzeni; `key` motorun verdiği kaynak kolon adıdır. Sıra dizinin sırasıdır. */
export type ReportColumn = { key: string; label: string; hidden: boolean; format: ColumnFormat };

export type ReportDto = {
  id: string;
  title: string;
  prompt: string;
  question: string;
  sql: string;
  fmt: ReportFormat;
  recurrence: ReportRecurrence;
  at: string;
  weekday: number | null;
  monthday: number | null;
  onceAt: string | null;
  recipients: string[];
  status: ReportStatus;
  createdAt: string | null;
  updatedAt: string | null;
  nextRunAt: string | null;
  lastRunAt: string | null;
  lastStatus: ReportLastStatus;
  lastError: string | null;
  lastRows: number | null;
  /** Son çalışmada verinin veritabanından gelme süresi; hiç çalışmadıysa null. `physicalSql`: o çalışmada
   *  veritabanında koşan metin (Son kullanılan SQL bu). */
  lastDb: (DbTiming & { physicalSql?: string | null; rows?: number | null }) | null;
  hasFile: boolean;
  /** Tek plan cevabında (çalıştır) sorgu bilgisi. */
  kaynaklar?: Kaynaklar;
  columns: ReportColumn[];
  /** "Her gün 08:00" gibi okunur plan. */
  when: string;
};

export type ReportDraft = DbTiming & {
  question: string;
  title: string;
  recurrence: ReportRecurrence;
  at: string;
  weekday: number | null;
  monthday: number | null;
  /** Tek seferlikte ayrıştırıcının bulduğu an ("bugün/yarın"), İstanbul saatli ISO. */
  onceAt?: string | null;
  recipients: string[];
  fmt: ReportFormat;
  sql: string;
  /** Önizlemede koşan fiziksel SQL (gösterilen ve kopyalanan). */
  physicalSql?: string;
  columns: Array<{ name: string; type: string }>;
  records: Array<Record<string, unknown>>;
  rowCount?: number | null;
  summary?: string;
  layout: ReportColumn[];
  kaynaklar?: Kaynaklar;
};

/** Önizlemede düzeltme sonucu. `requery` ise veri yeniden çekildi ve sql/columns/records geldi. */
export type ReportRefinement = DbTiming & {
  question: string;
  requery: boolean;
  via: 'rules' | 'model';
  changes: string[];
  layout: ReportColumn[];
  added: string[];
  dropped: string[];
  sql?: string;
  physicalSql?: string;
  columns?: Array<{ name: string; type: string }>;
  records?: Array<Record<string, unknown>>;
  rowCount?: number | null;
  summary?: string;
  kaynaklar?: Kaynaklar;
};

export type ReportInput = {
  title: string;
  prompt?: string;
  question: string;
  sql?: string;
  fmt: ReportFormat;
  recurrence: ReportRecurrence;
  at: string;
  weekday?: number | null;
  monthday?: number | null;
  onceAt?: string | null;
  recipients: string[];
  status?: ReportStatus;
  columns?: ReportColumn[];
};

export const reportsApi = {
  list: () =>
    send<{ user: string; reports: ReportDto[]; email: AlertEmail; kaynaklar?: Kaynaklar }>('GET', '/api/v1/reports', undefined, 30_000),
  parse: (text: string) => send<ReportDraft>('POST', '/api/v1/reports/parse', { text }, 600_000),
  refine: (b: { question: string; instruction: string; columns: ReportColumn[] }) =>
    send<ReportRefinement>('POST', '/api/v1/reports/refine', b, 600_000),
  preview: (b: { question: string; columns: ReportColumn[] }) =>
    send<Omit<ReportRefinement, 'requery' | 'via' | 'changes'>>('POST', '/api/v1/reports/preview', b, 600_000),
  create: (b: ReportInput) => send<ReportDto>('POST', '/api/v1/reports', b, 30_000),
  update: (id: string, b: Partial<ReportInput>) => send<ReportDto>('PATCH', `/api/v1/reports/${encodeURIComponent(id)}`, b, 30_000),
  remove: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/reports/${encodeURIComponent(id)}`, undefined, 30_000),
  run: (id: string) => send<ReportDto>('POST', `/api/v1/reports/${encodeURIComponent(id)}/run`, {}, 600_000),
  fileUrl: (id: string) => `${ENGINE_BASE}/api/v1/reports/${encodeURIComponent(id)}/file`,
};

/* ------------------------------------------------------------------ yönetim */

export type AdminSettingType = 'text' | 'int' | 'bool' | 'secret' | 'email' | 'users' | 'time';

export type AdminSetting = {
  key: string;
  group: string;
  label: string;
  type: AdminSettingType;
  help: string;
  /** Gizli alanlarda her zaman null; yalnız `hasValue` söylenir. */
  value: string | null;
  hasValue: boolean;
  /** screen: yönetim ekranında kaydedildi · env: servis ortam dosyası · file: giriş servisi dosyası · default: varsayılan */
  source: 'screen' | 'env' | 'file' | 'default';
  updatedBy: string | null;
  updatedAt: string | null;
};

export type AdminSettings = {
  /** Ayar grupları; `category` Yönetim › Ayarlar ekranındaki kategoridir (yoksa «Diğer»). */
  groups: Array<{ id: string; label: string; help: string; category?: string }>;
  /** Kategoriler ekrandaki sırayla; eski köprüde yoksa bütün gruplar «Diğer» altında görünür. */
  categories?: Array<{ id: string; label: string }>;
  items: AdminSetting[];
};

export type AdminUnit = {
  unit: string;
  label: string;
  every?: string;
  state: string;
  sub?: string | null;
  last?: string | null;
  next?: string | null;
  result?: string | null;
};

export type AuditItem = {
  id: number;
  at: string;
  actor: string;
  action: string;
  kind: string;
  kindLabel: string;
  objectId: string | null;
  title: string | null;
  detail: Record<string, unknown> | null;
};

export type AdminOverview = {
  counts: {
    reports: number;
    reportsActive: number;
    reportsFailed: number;
    alerts: number;
    alertsActive: number;
    alertsTriggered: number;
    cards: number;
    cardsFailed: number;
    users: number;
    admins: number;
  };
  email: AlertEmail;
  engine: { model: string; llm: boolean; db: boolean; catalog: Record<string, number>; profiles: number };
  services: AdminUnit[];
  timers: AdminUnit[];
  recent: AuditItem[];
};

/** Bağlantı denemesinin sonucu: ne denendi, ne zaman, ne kadar sürdü. */
export type AdminCheck = {
  id: string;
  group: string | null;
  label: string;
  ok: boolean;
  message: string;
  ms: number;
  at: string;
  /** Birden çok anahtarı olan gruplarda her bağlantının ayrı sonucu; off = girilmemiş. */
  parts?: { label: string; state: 'ok' | 'err' | 'off'; message: string; ms: number }[];
};

export type AdminSystem = {
  items: Array<{ label: string; value: string }>;
  checks: Array<{ id: string; group: string | null; label: string }>;
};

export type AdminReport = ReportDto & { owner: string };

export type AdminCard = {
  id: string;
  owner: string;
  title: string;
  question: string;
  chart: string;
  refresh: string;
  refreshAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
  resultAt: string | null;
  lastAutoAt: string | null;
  lastError: string | null;
};

export type AdminUser = { username: string; cards: number; reports: number; actions: number; lastSeen: string | null; admin: boolean };

export type AuditQuery = { kind?: string; action?: string; actor?: string; q?: string; before?: number };

/* --------------------------------------------------------------- promt izleyici */

/** Promt izleyicide liste satırı (hafif: tam sonuç/çözümleme yok). */
export type PromptRow = {
  id: string;
  question: string;
  username: string | null;
  threadId: string | null;
  sql: string | null;
  compiler: string | null;
  answerType: string | null;
  answerSummary: string | null;
  executed: boolean;
  rowCount: number | null;
  latencyMs: number | null;
  error: string | null;
  validated: boolean | null;
  catalogVersion: number | null;
  reviewFlag: 'todo' | 'fixed' | 'ignored' | null;
  reviewNote: string | null;
  reviewedBy: string | null;
  reviewedAt: string | null;
  createdAt: string | null;
};

/** Tek promtun her şeyi: SQL, tam sonuç satırları, semantik çözümleme, kapı kararları. */
export type PromptDetail = PromptRow & {
  resolved: Record<string, unknown>;
  result: {
    columns: Array<{ name: string }>;
    records: Array<Record<string, unknown>>;
    totalRows?: number;
    truncated?: boolean;
    _truncated_store?: boolean;
    /** Soru koşarken veritabanında koşan metin (kayıttaki `sql` çözülmemiş, katalog adlı metindir). */
    physicalSql?: string | null;
    dbMs?: number | null;
  } | null;
  gate: Record<string, unknown> | null;
};

export type PromptOverview = {
  sinceDays: number;
  total: number;
  answered: number;
  failed: number;
  todo: number;
  byType: Record<string, number>;
  byCompiler: Record<string, number>;
  unresolvedTerms: Array<[string, number]>;
  topFailing: Array<{ question: string; count: number }>;
};

export type PromptQuery = { limit?: number; offset?: number; only?: string; q?: string; user?: string; days?: number };

const qs = (o: Record<string, string | number | undefined>) => {
  const p = new URLSearchParams();
  Object.entries(o).forEach(([k, v]) => {
    if (v !== undefined && v !== '') p.set(k, String(v));
  });
  const s = p.toString();
  return s ? `?${s}` : '';
};

export const adminApi = {
  /** Oturumdaki kişinin rolü. `isEditor`: yönetim ekranındaki «Editör AD grubu» üyesi (ayar boşsa false);
   *  eski köprü göndermez, o zaman editör sayılmaz. */
  me: () => send<{ user: string; isAdmin: boolean; isEditor?: boolean }>('GET', '/api/v1/admin/me', undefined, 15_000),
  overview: () => send<WithK<AdminOverview>>('GET', '/api/v1/admin/overview', undefined, 30_000),
  settings: () => send<AdminSettings>('GET', '/api/v1/admin/settings', undefined, 15_000),
  saveSettings: (values: Record<string, string>) =>
    send<AdminSettings & { changed: string[]; applied: string[]; applyError: string | null }>(
      'PUT',
      '/api/v1/admin/settings',
      { values },
      60_000,
    ),
  resetSetting: (key: string) => send<AdminSettings>('DELETE', `/api/v1/admin/settings/${encodeURIComponent(key)}`, undefined, 15_000),
  testEmail: (to: string) => send<{ ok: boolean; message: string }>('POST', '/api/v1/admin/email/test', { to }, 60_000),
  testDirectory: (username: string) =>
    send<{ ok: boolean; message: string }>('POST', '/api/v1/admin/directory/test', { username }, 30_000),
  /** Tek bağlantı denemesi: database · crm · llm · directory · email · store. */
  test: (id: string) => send<AdminCheck>('POST', `/api/v1/admin/tests/${encodeURIComponent(id)}`, undefined, 120_000),
  testAll: () => send<{ items: AdminCheck[]; ok: boolean; at: string }>('POST', '/api/v1/admin/tests', undefined, 180_000),
  system: () => send<AdminSystem>('GET', '/api/v1/admin/system', undefined, 15_000),
  reports: () => send<WithK<{ items: AdminReport[] }>>('GET', '/api/v1/admin/reports', undefined, 30_000),
  updateReport: (id: string, b: Partial<ReportInput>) =>
    send<ReportDto>('PATCH', `/api/v1/admin/reports/${encodeURIComponent(id)}`, b, 30_000),
  deleteReport: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/admin/reports/${encodeURIComponent(id)}`, undefined, 30_000),
  alerts: () => send<WithK<{ items: AlertRule[] }>>('GET', '/api/v1/admin/alerts', undefined, 30_000),
  updateAlert: (id: string, b: Partial<AlertInput> & { status?: 'active' | 'paused' }) =>
    send<AlertRule>('PATCH', `/api/v1/admin/alerts/${encodeURIComponent(id)}`, b, 30_000),
  deleteAlert: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/admin/alerts/${encodeURIComponent(id)}`, undefined, 30_000),
  cards: () => send<{ items: AdminCard[] }>('GET', '/api/v1/admin/cards', undefined, 30_000),
  deleteCard: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/admin/cards/${encodeURIComponent(id)}`, undefined, 30_000),
  users: () => send<WithK<{ items: AdminUser[] }>>('GET', '/api/v1/admin/users', undefined, 30_000),
  audit: (q: AuditQuery) => send<{ items: AuditItem[]; next: number | null }>('GET', `/api/v1/admin/audit${qs(q)}`, undefined, 30_000),
  prompts: (q: PromptQuery) =>
    send<WithK<{ items: PromptRow[]; hasMore: boolean; nextOffset: number | null }>>('GET', `/api/v1/admin/prompts${qs(q)}`, undefined, 30_000),
  promptsOverview: (days = 30) => send<WithK<PromptOverview>>('GET', `/api/v1/admin/prompts/overview${qs({ days })}`, undefined, 30_000),
  prompt: (id: string) => send<WithK<PromptDetail>>('GET', `/api/v1/admin/prompts/${encodeURIComponent(id)}`, undefined, 30_000),
  markPrompt: (id: string, b: { flag?: string; note?: string }) =>
    send<PromptDetail>('PATCH', `/api/v1/admin/prompts/${encodeURIComponent(id)}`, b, 30_000),
  /** CSV indirme adresi (aynı köken, oturum çerezi taşınır). */
  promptsExportUrl: (q: PromptQuery) => `${ENGINE_BASE}/api/v1/admin/prompts/export.csv${qs(q)}`,
};

/* ------------------------------------------------------------------ yetki */

/** Bağ türü: AD grubu, AD birimi (OU), CRM güvenlik rolü ya da tek kişi. */
export type AccessSubjectType = 'ad_group' | 'ou' | 'crm_role' | 'user';

/** Oturumdaki kişinin görebildiği sayfalar ve işlemler (`perms`: `sayfa:*` + `ozellik:*`). `all` yalnız yöneticide
 *  doğrudur; «bütün» rolü açıkça verilen işlemleri kapsamadığı için liste her zaman `perms`ten okunur. */
export type AccessMe = {
  user: string;
  isAdmin: boolean;
  isEditor?: boolean;
  all: boolean;
  allRoles?: boolean;
  perms: string[];
  roles: Array<{ id: string; name: string; via: string[] }>;
};

/** `explicit`: «Bütün sayfalar» ile gelmez (İK ekranları); `sensitive`: kişisel veri, yöneticiye de rolüyle verilir. */
export type AccessPage = { key: string; area: string; label: string; explicit?: boolean; sensitive?: boolean };
/** Sayfa içindeki işlem. `explicit`: «Bütün sayfalar ve işlemler» ile gelmez, role tek tek verilir. */
export type AccessFeature = { key: string; area: string; page?: string; label: string; hint: string; explicit?: boolean; sensitive?: boolean };
/** ZEKİ AI veri alanı (yetki Aşama C). `always`: herkese açık ortak başvuru, rolle kapatılmaz. */
export type AccessDataDomain = { id: string; key: string; label: string; hint: string; always?: boolean };
export type AccessCatalog = {
  version: number;
  areas: Array<{ id: string; label: string }>;
  pages: AccessPage[];
  features: AccessFeature[];
  data: AccessDataDomain[];
  subjectTypes: Record<AccessSubjectType, string>;
};

export type AccessBinding = {
  id: string;
  type: AccessSubjectType;
  typeLabel: string;
  subject: string;
  label: string;
  /** Görüntüdeki üye sayısı; henüz okunmadıysa null. Kişi bağında 1. */
  members: number | null;
  updatedAt: string | null;
  error: string | null;
  createdBy: string | null;
  createdAt: string | null;
};

export type AccessRole = {
  id: string;
  name: string;
  description: string;
  allPerms: boolean;
  system: boolean;
  perms: string[];
  bindings: AccessBinding[];
  updatedBy: string | null;
  updatedAt: string | null;
};

export type AccessRoleInput = { name: string; description: string; allPerms: boolean; perms: string[] };

/** Bağlanabilecek aday: AD grubu, OU, CRM rolü ya da kişi. `count`: üye sayısı (kişide yok). */
export type AccessCandidate = { subject: string; label: string; hint?: string; detail?: string; count?: number };

export type AccessExplain = AccessMe & {
  adGroups: string[];
  crmRoles: string[];
  pages: Array<AccessPage & { allowed: boolean }>;
  features: Array<AccessFeature & { allowed: boolean }>;
  data: Array<AccessDataDomain & { allowed: boolean }>;
  notes: string[];
};

export type AccessDataEntity = {
  entity: string;
  source: 'logo' | 'crm';
  description: string;
  rows: number;
  tables: number;
  domain: string;
  manual: boolean;
};

export const accessApi = {
  me: () => send<AccessMe>('GET', '/api/v1/access/me', undefined, 15_000),
  catalog: () => send<AccessCatalog>('GET', '/api/v1/access/catalog', undefined, 15_000),
  roles: () => send<WithK<{ items: AccessRole[] }>>('GET', '/api/v1/access/roles', undefined, 30_000),
  createRole: (b: AccessRoleInput) => send<{ id: string }>('POST', '/api/v1/access/roles', b, 30_000),
  updateRole: (id: string, b: AccessRoleInput) =>
    send<{ id: string }>('PUT', `/api/v1/access/roles/${encodeURIComponent(id)}`, b, 30_000),
  deleteRole: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/access/roles/${encodeURIComponent(id)}`, undefined, 30_000),
  /** Bağı ekler; köprü üyeleri hemen okur (AD/CRM), bu yüzden süre uzun tutuldu. */
  addBinding: (roleId: string, b: { type: AccessSubjectType; subject: string; label: string }) =>
    send<{ id: string; refresh?: { ok: boolean; failed: Array<{ error: string }> } }>(
      'POST',
      `/api/v1/access/roles/${encodeURIComponent(roleId)}/bindings`,
      b,
      120_000,
    ),
  deleteBinding: (id: string) => send<{ ok: boolean }>('DELETE', `/api/v1/access/bindings/${encodeURIComponent(id)}`, undefined, 30_000),
  subjects: (type: AccessSubjectType) =>
    send<WithK<{ type: AccessSubjectType; items: AccessCandidate[] }>>('GET', `/api/v1/access/subjects${qs({ type })}`, undefined, 120_000),
  /** CRM'de departmana atanmamış etkin kullanıcılar, AD birimleriyle (Excel indirme). */
  crmUnassignedUrl: `${ENGINE_BASE}/api/v1/access/crm-unassigned.xlsx`,
  /** Bağın bugünkü etkin üyeleri (grupta iç içe gruplar, birimde alt birimler dahil). */
  members: (type: AccessSubjectType, subject: string) =>
    send<WithK<{ type: AccessSubjectType; subject: string; count: number; items: AccessCandidate[] }>>(
      'GET', `/api/v1/access/subjects/members${qs({ type, subject })}`, undefined, 120_000),
  explain: (user: string) => send<WithK<AccessExplain>>('GET', `/api/v1/access/explain${qs({ user })}`, undefined, 120_000),
  /** Kataloğun her varlığı ve veri alanı; `manual`: alanı yönetici atadı (kural değil). */
  dataEntities: () =>
    send<WithK<{ items: AccessDataEntity[]; counts: Record<string, number> }>>('GET', '/api/v1/access/data-entities', undefined, 60_000),
  setEntityDomain: (entity: string, domain: string | null) =>
    send<{ ok: boolean }>('PUT', `/api/v1/access/data-entities/${encodeURIComponent(entity)}`, { domain }, 30_000),
  refresh: () =>
    send<{ ok: boolean; refreshed: number; failed: Array<{ type: string; subject: string; error: string }> }>(
      'POST',
      '/api/v1/access/refresh',
      undefined,
      300_000,
    ),
};

/* ------------------------------------------------------------------ kişi tercihleri */

/** Kişinin kendi ekran alanları (AD hesabına bağlı, sunucuda). */
export const prefsApi = {
  get: <T,>(key: string) =>
    send<{ user: string; key: string; value: T | null; updatedAt: string | null }>('GET', `/api/v1/me/prefs/${encodeURIComponent(key)}`, undefined, 15_000),
  put: <T,>(key: string, value: T) =>
    send<{ user: string; key: string; value: T; updatedAt: string }>('PUT', `/api/v1/me/prefs/${encodeURIComponent(key)}`, { value }, 15_000),
  remove: (key: string) => send<{ ok: boolean }>('DELETE', `/api/v1/me/prefs/${encodeURIComponent(key)}`, undefined, 15_000),
};

/* ------------------------------------------------------------------ toplantı odaları */

export type Room = { id: string; name: string; location: string; capacity: number | null; active: boolean };
export type RoomBooking = {
  id: string;
  roomId: string;
  roomName?: string;
  start: string;
  end: string;
  /** İstanbul günü, YYYY-AA-GG. */
  date: string;
  startLocal: string;
  endLocal: string;
  username: string;
  displayName: string;
  title: string;
  mine: boolean;
  canCancel: boolean;
};
export type RoomGrid = { start: string; end: string; slotMinutes: number; startMin: number; endMin: number };
export type RoomsMe = { username: string; displayName: string; admin: boolean };
export type RoomsDay = { date: string; today: string; grid: RoomGrid; rooms: Room[]; bookings: RoomBooking[]; me: RoomsMe };
export type RoomNow = Room & { current: RoomBooking | null; next: RoomBooking | null };
export type RoomsNow = { now: string; today: string; rooms: RoomNow[]; me: RoomsMe };

/** Oda servisinin düz Türkçe hatası. 409'da saati kimin aldığı `booking` içinde gelir. */
export class RoomsError extends Error {
  constructor(message: string, readonly status: number, readonly booking?: RoomBooking) {
    super(message);
    this.name = 'RoomsError';
  }
}

/** `send` 403'ü oturum düşmesi sayar; burada 403 "bu işi yapamazsın" demektir, oturum yerinde kalır. */
async function roomsSend<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30_000),
  });
  if (res.status === 401) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string; booking?: RoomBooking } | string } | null;
    const d = j?.detail;
    const msg = typeof d === 'string' ? d : d?.message;
    throw new RoomsError(msg || httpErrorText(res.status), res.status, typeof d === 'object' ? d?.booking : undefined);
  }
  return (await res.json()) as T;
}

export type Greeting = { id: string; from: string; to: string; occasion: string | null; at: string; seen: boolean };

/** Kampüs kutlamaları: `sent` bugün kutladıklarım, `inbox` bana gelen ve henüz görmediklerim,
 *  `received` son 30 günde bana gelenlerin hepsi (zil), `wall` herkesin son 30 günü (alkış duvarı). */
export const greetingsApi = {
  state: () => roomsSend<{ sent: string[]; inbox: Greeting[]; received: Greeting[]; wall: Greeting[] }>('GET', '/api/v1/greetings'),
  send: (to: string, occasion?: string) => roomsSend<Greeting & { created: boolean }>('POST', '/api/v1/greetings', { to, occasion }),
  seen: (ids: string[]) => roomsSend<{ marked: number }>('POST', '/api/v1/greetings/seen', { ids }),
};

/* ------------------------------------------------------------------ kampüs sesli bülteni */

export type BulletinStatus = 'taslak' | 'yayinda';
export type Bulletin = {
  id: string;
  title: string;
  summary: string | null;
  episode: number | null;
  voice: string | null;
  durationSec: number | null;
  mime: string;
  size: number;
  source: 'yükleme' | 'sunucu';
  status: BulletinStatus;
  originalName: string | null;
  createdBy: string;
  createdAt: string;
  publishedAt: string | null;
  updatedAt: string;
  /** Köprü yolu, sürüm parçasıyla; `bulletinAudioUrl` tam adrese çevirir. */
  audioPath: string;
};
export type BulletinPatch = Partial<Pick<Bulletin, 'title' | 'summary' | 'episode' | 'voice' | 'durationSec' | 'status'>>;

export const bulletinAudioUrl = (b: Pick<Bulletin, 'audioPath'>) => `${ENGINE_BASE}${b.audioPath}`;

/** Metinden üretim işi: ZEKİ AI seslendirir (GPU sırası); bitince ses taslak bülten olur (`bulletinId`). */
export type BulletinJob = {
  id: string;
  title: string | null;
  voice: string | null;
  chars: number;
  status: 'queued' | 'running' | 'done' | 'fail';
  error: string | null;
  bulletinId: string | null;
  createdBy: string;
  createdAt: string | null;
};
export type BulletinVoice = { id: string; label: string; note: string; group: string; recommended?: boolean };

/** Kampüs'te en son yayınlanan bülten çalar; Yönetim → Sesli bülten taslakları da görür, ekler, yayınlar. */
export const bulletinsApi = {
  current: () => roomsSend<{ item: Bulletin | null }>('GET', '/api/v1/bulletins/current'),
  adminList: () => roomsSend<WithK<{ items: Bulletin[]; maxMb: number }>>('GET', '/api/v1/admin/bulletins'),
  update: (id: string, patch: BulletinPatch) => roomsSend<Bulletin>('PATCH', `/api/v1/admin/bulletins/${encodeURIComponent(id)}`, patch),
  remove: (id: string) => roomsSend<{ ok: boolean }>('DELETE', `/api/v1/admin/bulletins/${encodeURIComponent(id)}`),
  voices: () => roomsSend<{ voices: BulletinVoice[]; groups: Record<string, string>; error?: string }>('GET', '/api/v1/admin/bulletins/voices'),
  jobs: () => roomsSend<WithK<{ items: BulletinJob[] }>>('GET', '/api/v1/admin/bulletins/jobs'),
  generate: (b: { text: string; voice: string | null; title: string | null }) =>
    roomsSend<BulletinJob>('POST', '/api/v1/admin/bulletins/generate', b),
  /** Ham gövdeyle yükleme; süre tarayıcıda ölçülüp gönderilir (sunucuda ses çözümleyici yok). */
  upload: (file: File, durationSec: number | null, onProgress: (sent: number, total: number) => void) =>
    new Promise<Bulletin>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const q = `filename=${encodeURIComponent(file.name)}${durationSec ? `&duration=${durationSec.toFixed(1)}` : ''}`;
      xhr.open('POST', `${ENGINE_BASE}/api/v1/admin/bulletins?${q}`);
      xhr.withCredentials = true;
      xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
      xhr.upload.onprogress = (e) => onProgress(e.loaded, e.lengthComputable ? e.total : file.size);
      xhr.onload = () => {
        if (xhr.status === 401) { authBlocked = true; reject(new EngineAuthError()); return; }
        let j: Record<string, unknown> | null = null;
        try { j = JSON.parse(xhr.responseText) as Record<string, unknown>; } catch { /* gövdesiz (ör. nginx 413) */ }
        if (xhr.status >= 200 && xhr.status < 300 && j) { resolve(j as unknown as Bulletin); return; }
        const d = j?.detail as { message?: string } | string | undefined;
        reject(new RoomsError((typeof d === 'string' ? d : d?.message) || httpErrorText(xhr.status), xhr.status));
      };
      xhr.onerror = () => reject(new RoomsError('Bağlantı koptu; yükleme tamamlanmadı.', 0));
      xhr.ontimeout = () => reject(new RoomsError('Yükleme zaman aşımına uğradı.', 0));
      xhr.timeout = 15 * 60_000;
      xhr.send(file);
    }),
};

/* ------------------------------------------------------------------ kişi rehberi ve profil */

/** CRM'deki gerçek, etkin kullanıcı. Boş alan "". dahili/kat CRM'de yoksa kişinin profilinden gelir. */
export type Person = {
  id: string;
  username: string;
  name: string;
  title: string;
  unit: string;
  email: string;
  mobile: string;
  phone: string;
  extension: string;
  floor: string;
  desk?: string;
  about?: string;
  photoVersion: number | null;
};
export type PeopleList = { items: Person[]; total: number; truncated: boolean; source: 'crm'; adChecked: boolean; at: string; db?: DbTiming | null };
export type ProfileFields = { extension: string; floor: string; desk: string; mobile: string; about: string };
export type MyProfile = {
  username: string;
  displayName: string;
  inCrm: boolean;
  crm: Person | null;
  fields: ProfileFields;
  photoVersion: number | null;
  updatedAt: string | null;
  /** CRM kaydının veritabanından gelme süresi; CRM okunamadıysa null. */
  db?: DbTiming | null;
};

export const photoUrl = (username: string, version: number | null) =>
  version ? `${ENGINE_BASE}/api/v1/people/${encodeURIComponent(username)}/photo?v=${version}` : null;

export const peopleApi = {
  list: () => roomsSend<PeopleList>('GET', '/api/v1/people'),
  me: () => roomsSend<MyProfile>('GET', '/api/v1/me/profile'),
  save: (fields: ProfileFields) => roomsSend<MyProfile>('PUT', '/api/v1/me/profile', { fields }),
  savePhoto: (dataUrl: string) => roomsSend<{ photoVersion: number }>('PUT', '/api/v1/me/profile/photo', { dataUrl }),
  deletePhoto: () => roomsSend<{ ok: boolean }>('DELETE', '/api/v1/me/profile/photo'),
};

export const roomsApi = {
  day: (date: string) => roomsSend<RoomsDay>('GET', `/api/v1/rooms?date=${encodeURIComponent(date)}`),
  now: () => roomsSend<RoomsNow>('GET', '/api/v1/rooms/now'),
  book: (roomId: string, b: { date: string; start: string; end: string; title: string }) =>
    roomsSend<RoomBooking>('POST', `/api/v1/rooms/${encodeURIComponent(roomId)}/bookings`, b),
  cancel: (id: string) => roomsSend<{ ok: boolean; booking: RoomBooking }>('DELETE', `/api/v1/rooms/bookings/${encodeURIComponent(id)}`),
  addRoom: (b: { name: string; location: string; capacity: number | null }) => roomsSend<Room>('POST', '/api/v1/admin/rooms', b),
  removeRoom: (id: string) =>
    roomsSend<Room & { cancelledBookings: number }>('DELETE', `/api/v1/admin/rooms/${encodeURIComponent(id)}`),
};

// ---------------------------------------------------------------------------- editoryal süreç (M1–M8)

// ------------------------------------------------------------ yazar giriş süreci (9 adım, CRM'den)

export type IntakeCard = {
  id: string;
  name: string | null;
  author: string | null;
  editor: string | null;
  bookId: string | null;
  /** Bulunulan adım (1–9); tamamlanmış ya da kapanmış projede null. */
  step: number | null;
  phase: number | null;
  done: number;
  progress: boolean[];
  line: string;
  since: string | null;
  waitingDays: number | null;
  late: boolean;
  outcome: 'red' | 'iptal' | null;
  complete: boolean;
  boardOn: string | null;
  modifiedOn: string | null;
  createdOn: string | null;
  mine: boolean;
  /** CRM projesindeki «Yayınevi» (marka); girilmemişse null. */
  brand?: string | null;
  /** CRM proje türü etiketi (Editoryal, Pazarlama, Satış). */
  projectType?: string | null;
};
export type IntakeStepDef = { no: number; title: string; waiting: string; owner: string; markable: string | null };
export type IntakePhase = { no: number; title: string; lead: string; steps: Array<{ no: number; title: string }>; count: number; late: number };
export type IntakeBoard = {
  since: string | null;
  at: string | null;
  audit: boolean;
  lateDays: number;
  phases: IntakePhase[];
  items: IntakeCard[];
  completed: IntakeCard[];
  closed: IntakeCard[];
  todo: IntakeCard[];
  /** 'all': yönetici, bütün editörlerin bekleyen işi; 'mine': yalnız oturumdaki editörün. */
  todoScope: 'all' | 'mine';
  lastBoard: string | null;
  steps: IntakeStepDef[];
  loading: boolean;
  updatedAt: number | null;
  error: string | null;
  refreshIntervalSeconds: number;
};
export type IntakeStep = {
  no: number;
  title: string;
  owner: string;
  waiting: string;
  done: boolean;
  on: string | null;
  source: 'crm' | 'portal' | 'cikarim' | null;
  markable: string | null;
  marked: boolean;
  markedBy: string | null;
};
export type IntakeBoardRecord = {
  id: string | null;
  date: string | null;
  decisionCode: number | null;
  decision: string | null;
  note: string | null;
  printRun: string | null;
  price: string | null;
  royalty: string | null;
  publishOn: string | null;
};
export type IntakeOpinion = { by: string | null; verdict: string | null; text: string | null; on: string | null };
export type IntakeProject = IntakeCard & {
  canMark: boolean;
  steps: IntakeStep[];
  phases: Array<{ no: number; title: string; steps: number[] }>;
  channel: string | null;
  status: string | null;
  idea: string | null;
  book: string | null;
  publishOn: string | null;
  contracts: number;
  participations: number;
  boards: IntakeBoardRecord[];
  opinions: IntakeOpinion[] | null;
  opinionsVisible: boolean;
};
export type IntakeMeeting = { date: string; total: number; accepted: number; rejected: number; revisit: number; pending: number };
export type IntakeAgendaItem = {
  id: string | null;
  projectId: string | null;
  project: string | null;
  author: string | null;
  editor: string | null;
  report: boolean;
  decisionCode: number | null;
  decision: string | null;
  note: string | null;
  printRun: string | null;
  price: string | null;
  royalty: string | null;
  advance: string | null;
  publishOn: string | null;
  opinions: IntakeOpinion[] | null;
  opinionCount: number | null;
};

export const intakeApi = {
  board: () => send<IntakeBoard>('GET', '/api/v1/editorial/intake', undefined, 60_000),
  project: (id: string) => send<IntakeProject>('GET', `/api/v1/editorial/intake/${encodeURIComponent(id)}`, undefined, 60_000),
  mark: (id: string, step: number) => send<{ ok: boolean }>('PUT', `/api/v1/editorial/intake/${encodeURIComponent(id)}/marks/${step}`, undefined, 30_000),
  unmark: (id: string, step: number) => send<{ ok: boolean }>('DELETE', `/api/v1/editorial/intake/${encodeURIComponent(id)}/marks/${step}`, undefined, 30_000),
  meetings: () => send<{ items: IntakeMeeting[] }>('GET', '/api/v1/editorial/intake/meetings', undefined, 60_000),
  agenda: (day: string) =>
    send<{ date: string; items: IntakeAgendaItem[]; opinionsVisible: boolean }>('GET', `/api/v1/editorial/intake/meetings/${encodeURIComponent(day)}`, undefined, 60_000),
};

// ------------------------------------------------------------ basın ve web (açık RSS + Wikidata)

export type WebTone = Partial<Record<'olumlu' | 'olumsuz' | 'notr', number>>;
export type WebMention = {
  contactId: string;
  author: string;
  books: Array<{ id: string; title: string }>;
  label: 'olumlu' | 'olumsuz' | 'notr';
  source: string;
  kind: 'haber' | 'sozluk' | 'forum';
  url: string;
  title: string;
  summary: string | null;
  on: string | null;
};
export type WebFacts = {
  description: string | null;
  born: number | null;
  died: number | null;
  occupations: string[];
  awards: string[];
  works: string[];
  wikipedia: string | null;
  wikidata: string;
};
export type WebChannel = {
  key: string;
  label: string;
  kind: string;
  url: string | null;
  status: 'açık' | 'kapalı' | 'hata' | 'engelli';
  note: string | null;
  read: number;
  matched: number;
  relevant: number;
  lastAt: string | null;
};
export type WebOverview = {
  /** Bu ortamda tarama açık mı (WEB_WATCH_ENABLED); müşteri ortamında kapalı. */
  enabled: boolean;
  channels: WebChannel[];
  items: WebMention[];
  total: number;
  page: number;
  pageSize: number;
  tone: WebTone;
  authors: Array<{ contactId: string; author: string; total: number; tone: WebTone }>;
  counts: { items: number; pending: number; authorsChecked: number; authorsFound: number };
  lastRun: { at: string | null; report: Record<string, unknown> } | null;
  sources: Array<{ key: string; label: string }>;
};
export type WebSubject = { items: WebMention[]; total: number; tone: WebTone; facts?: WebFacts | null; checkedAt?: string | null };

export const webApi = {
  status: () => send<{ enabled: boolean }>('GET', '/api/v1/editorial/web/status', undefined, 30_000),
  overview: (p: { page?: number; label?: string }) => send<WebOverview>('GET', `/api/v1/editorial/web${qs({ page: p.page, label: p.label })}`, undefined, 60_000),
  person: (id: string) => send<WebSubject>('GET', `/api/v1/editorial/web/people/${encodeURIComponent(id)}`, undefined, 60_000),
  book: (id: string) => send<WebSubject>('GET', `/api/v1/editorial/web/books/${encodeURIComponent(id)}`, undefined, 60_000),
};

/** CRM sözleşme hakkı: var (true), yok (false), CRM'de girilmemiş (null). */
export type CrmRight = { key: string; label: string; granted: boolean | null };
/** CRM lisans şartları; `terms` yalnız dolu alanları taşır (anahtarlar crm_rights.TERMS). */
export type CrmLicense = {
  flags: Array<{ key: string; label: string }>;
  terms: Record<string, string | number>;
  rightsNote: string | null;
  royaltyNote: string | null;
  countries: string[];
  languages: string[];
};
export type CrmRightsFields = { rights?: CrmRight[]; license?: CrmLicense; purchase?: boolean; inForce?: boolean };
/** Kitabın hakları: yürürlükteki Telif Alış sözleşmelerinin birleşimi. */
export type BookRights = {
  basis: number;
  items: Array<{ key: string; label: string; state: 'var' | 'kismi' | 'yok' | 'girilmemis'; yes: number; of: number; missing: string[] }>;
  notes: Array<{ no: string | null; text: string }>;
  countries: string[];
  languages: string[];
};
export type ContractRate = { format: string; percent: number };
export type ContractParty = { name: string; share: number | null; scope: string | null; viaAgent: boolean };
export type Contract = {
  id: string;
  no: string | null;
  code: string | null;
  kind: string | null;
  payment: string | null;
  basis: string | null;
  rates: ContractRate[];
  currency: string | null;
  advance: number | null;
  start: string | null;
  end: string | null;
  years: number | null;
  openEnded: boolean;
  status: string | null;
  stage: string | null;
  daysLeft: number | null;
  modifiedOn: string | null;
  books: Array<{ id: string | null; title: string }>;
  parties: ContractParty[];
  /** Portalda düzenlenmişse portal kaydının durumu ve CRM'e işlenmemiş fark sayısı. */
  portal?: { id: string; status: string; statusLabel: string; updatedAt: string; diff: number } | null;
} & CrmRightsFields;
export type ContractPage = { items: Contract[]; total: number; page: number; pageSize: number; db?: DbTiming | null };
export type ContractFacet = { code: number; label: string | null; count: number };
export type ContractSummary = {
  total: number;
  active: number;
  renewal: number;
  expiring: number;
  warnDays: number;
  avgRoyalty: number | null;
  avgRoyaltyOver: number;
  statuses: ContractFacet[];
  kinds: ContractFacet[];
  db?: DbTiming | null;
};
export type ContractQuery = { q?: string; status?: number; kind?: number; expiring?: boolean; order?: string; page?: number };

/** M6 Telif & Sözleşme: CRM'deki sözleşme portföyü (salt okunur). */
export const contractsApi = {
  summary: () => send<ContractSummary>('GET', '/api/v1/editorial/contracts/summary', undefined, 60_000),
  list: (p: ContractQuery) =>
    send<ContractPage>(
      'GET',
      `/api/v1/editorial/contracts${qs({ q: p.q, status: p.status, kind: p.kind, expiring: p.expiring ? 'true' : undefined, order: p.order, page: p.page })}`,
      undefined,
      60_000,
    ),
};

export type Contributor = { id: string; name: string | null; works: number; recentWorks: number; last: string | null; roles: Array<{ role: string; works: number }> };
export type ContributorPage = {
  items: Contributor[];
  total: number;
  activePeople: number;
  contributions: number;
  page: number;
  pageSize: number;
  db?: DbTiming | null;
  kaynaklar?: Kaynaklar;
};
export type RoleFacet = { role: string; records: number; people: number };
export type PersonDetail = {
  id: string;
  name: string | null;
  bio: string | null;
  works: Array<{ bookId: string | null; title: string | null; role: string | null; on: string | null }>;
  contracts: Array<{ id: string; no: string | null; status: string | null; kind: string | null; start: string | null; end: string | null; royalty: number | null; share: number | null } & CrmRightsFields>;
  projects: Array<{ id: string; name: string | null; status: string | null; text: string | null; on: string | null; editor: string | null }>;
  truncated: boolean;
  db?: DbTiming | null;
  kaynaklar?: Kaynaklar;
};

/** M7 / M8 / M4: esere katkı verenler (yazar, çizer, çevirmen…), CRM eser katılım kayıtlarından. */
export const contributorsApi = {
  roles: () => send<{ items: RoleFacet[]; db?: DbTiming | null; kaynaklar?: Kaynaklar }>('GET', '/api/v1/editorial/contributors/roles', undefined, 60_000),
  list: (p: { roles: string[]; q?: string; order?: string; page?: number }) =>
    send<ContributorPage>('GET', `/api/v1/editorial/contributors${qs({ roles: p.roles.join('|'), q: p.q, order: p.order, page: p.page })}`, undefined, 60_000),
  person: (id: string) => send<PersonDetail>('GET', `/api/v1/editorial/contributors/${encodeURIComponent(id)}`, undefined, 60_000),
};

// ------------------------------------------------------------ M7 yazar ilişkileri (kendi kayıtlarımız + CRM okuma)

export type Choice = { key: string; label: string };
export type AuthorsMeta = {
  stages: Choice[];
  poolStages: string[];
  sources: Choice[];
  channels: Choice[];
  tones: Choice[];
  statuses: Choice[];
  heat: { recencyMax: number; recencyDays: number; frequencyMax: number; frequencyEach: number; toneMax: number; months: number };
  me: { username: string; display: string; admin: boolean };
  poolSince: string;
};
export type HeatBand = 'yok' | 'soguk' | 'ilik' | 'sicak';
export type AuthorHeat = {
  score: number;
  band: HeatBand;
  parts: { recency: number; frequency: number; tone: number };
  lastContact: string | null;
  daysSince: number | null;
  contactsYear: number;
  months: number[];
  next: string | null;
  /** Yakınlık payının kaynağı: son görüşme ya da CRM'deki son iz (yeni eser kaydı, sözleşme başlangıcı). */
  recencyFrom: 'gorusme' | 'eser' | 'sozlesme' | null;
  lastTrace: string | null;
  traceKind: 'eser' | 'sozlesme' | null;
  traceDays: number | null;
};
export type AuthorCard = {
  id: string;
  crmContactId: string | null;
  name: string;
  stage: string;
  stageLabel: string;
  genre: string | null;
  source: string | null;
  sourceLabel: string | null;
  sourceNote: string | null;
  email: string | null;
  phone: string | null;
  city: string | null;
  links: string[];
  bio: string | null;
  tags: string[];
  owner: string | null;
  ownerDisplay: string | null;
  createdBy: string;
  createdAt: string;
  updatedBy: string | null;
  updatedAt: string | null;
  archived: boolean;
  archivedAt: string | null;
};
export type AuthorCardSummary = AuthorCard & { heat: AuthorHeat; meetings: number; openSteps: number };
export type AuthorMeeting = {
  id: string;
  cardId: string;
  status: 'planlandi' | 'yapildi' | 'iptal';
  statusLabel: string;
  startsAt: string;
  date: string;
  time: string;
  minutes: number | null;
  channel: string;
  channelLabel: string;
  location: string | null;
  topic: string;
  notes: string | null;
  tone: string | null;
  toneLabel: string | null;
  nextStep: string | null;
  nextDue: string | null;
  nextDone: boolean;
  private: boolean;
  hidden: boolean;
  participants: Array<{ username: string; display: string }>;
  roomBookingId: string | null;
  roomName: string | null;
  createdBy: string;
  createdDisplay: string | null;
  createdAt: string;
  updatedAt: string | null;
  canEdit: boolean;
  overdue: boolean;
  cardName?: string | null;
  cardStage?: string | null;
  crmContactId?: string | null;
  stepLate?: boolean;
};
export type AuthorCardDetail = AuthorCard & { heat: AuthorHeat; timeline: AuthorMeeting[]; kaynaklar?: Kaynaklar };
export type AuthorByCrm = { card: AuthorCard | null; heat: AuthorHeat; timeline: AuthorMeeting[]; kaynaklar?: Kaynaklar };
export type AuthorCardInput = Partial<{
  name: string;
  stage: string;
  genre: string;
  source: string;
  sourceNote: string;
  email: string;
  phone: string;
  city: string;
  links: string[];
  bio: string;
  tags: string[];
  owner: string;
  ownerDisplay: string;
  crmContactId: string | null;
  archived: boolean;
}>;
export type AuthorMeetingInput = Partial<{
  cardId: string;
  crmContactId: string;
  name: string;
  status: string;
  date: string;
  time: string;
  minutes: number | null;
  channel: string;
  location: string;
  topic: string;
  notes: string;
  tone: string | null;
  nextStep: string;
  nextDue: string;
  nextDone: boolean;
  private: boolean;
  participants: Array<{ username: string; display: string }>;
  roomId: string;
}>;
export type AuthorPoolCrm = {
  items: Array<{
    crmContactId: string;
    name: string | null;
    projects: number;
    last: string | null;
    latest: { id: string; name: string | null; status: string | null; on: string | null; editor: string | null } | null;
    cardId: string | null;
    cardStage: string | null;
  }>;
  total: number;
  page: number;
  pageSize: number;
  since: string;
  db?: DbTiming | null;
  kaynaklar?: Kaynaklar;
};
export type AuthorHeatRow = {
  key: string;
  name: string;
  cardId: string | null;
  crmContactId: string | null;
  stage: string | null;
  stageLabel: string | null;
  owner: string | null;
  ownerDisplay: string | null;
  contracts: number;
  contractEnds: string | null;
  heat: AuthorHeat;
  crm: number[];
  crmBooks: number;
  crmContracts: number;
  /** «İlgi bekleyen» nedenleri (sözleşme bitiyor + görüşme yok, notu girilmemiş randevu, geçmiş adım). */
  attention: string[];
  /** Sadakat puanı (yalnız CRM'deki yazar için; CRM okunamadıysa null). */
  loyalty: AuthorLoyalty | null;
};
export type LoyaltyBand = 'bagli' | 'duzenli' | 'zayif';
export type AuthorLoyalty = {
  score: number;
  band: LoyaltyBand;
  parts: { years: number; books: number; recent: number; active: number; returning: number };
  since: string | null;
  last: string | null;
  years?: number;
  books: number;
  contracts: number;
  activeContracts: number;
};
export type SalesTotals = { qty: number; net: number; retQty: number };
export type AuthorGrowth = {
  contactId: string;
  books: Array<{ id: string; title: string | null; stockCode: string | null; hasCode: boolean; firstPublished: string | null } & SalesTotals>;
  booksTotal: number;
  booksWithCode: number;
  newBooksByYear: Array<{ year: number; count: number }>;
  sales: {
    last12: SalesTotals;
    prev12: SalesTotals;
    changePct: number | null;
    direction: 'artis' | 'dusus' | 'yatay' | null;
    series: Array<{ month: string } & SalesTotals>;
    years: Array<{ year: number } & SalesTotals>;
    window: { from: string; to: string; prevFrom: string; prevTo: string };
  };
  dataEnd: string | null;
  royalty: {
    contracts: number;
    statements: Array<{ contractNo: string; periodStart: string; periodEnd: string; status: string; gross: number; net: number; currency: string; approved: boolean }>;
  };
  readers: {
    site: { available: boolean; comments: number; rated: number; average: number | null; stars: Record<string, number>; books: Array<{ title: string | null; comments: number; rated: number; average: number | null }> };
    web: Record<string, number> | null;
  };
  loyalty: AuthorLoyalty;
  loyaltyRules?: Record<string, number>;
  notes: string[];
  computedAt: string;
  cached?: boolean;
  preparedAt?: string;
  snapshot?: AuthorSnapshot;
  kaynaklar?: Kaynaklar;
};
/** Önceden hazırlanan M7 verisinin durumu (CRM + Logo parçaları, 5 dk'da bir ve «Yenile» ile). */
export type AuthorSnapshot = {
  intervalSeconds: number;
  refreshing: boolean;
  crm: { updatedAt: string; error: string | null; seconds: number | null } | null;
  sales: { updatedAt: string; error: string | null; seconds: number | null } | null;
};
export type AuthorAdvice = {
  id: string;
  summary: string;
  recommendations: Array<{ title: string; why: string; when: string }>;
  risks: string[];
  createdBy: string;
  createdAt: string;
  input?: Record<string, unknown>;
  /** Sayı denetimi: olgularla tutmayan cümle sayısı; boşalan özet/öneri yerine kural metni konduysa işaret. */
  guard?: { dropped: number; ruleSummary: boolean; ruleRecommendations: boolean };
  kaynaklar?: Kaynaklar;
};
export type AuthorHeatmap = {
  months: string[];
  items: AuthorHeatRow[];
  total: number;
  page: number;
  pageSize: number;
  bands: Record<HeatBand, number>;
  attention: number;
  warnDays: number;
  crmOk: boolean;
  crmError: string | null;
  kaynaklar?: Kaynaklar;
};
export type AuthorAgenda = { upcoming: AuthorMeeting[]; missingNotes: AuthorMeeting[]; openSteps: AuthorMeeting[]; days: number; today: string; kaynaklar?: Kaynaklar };
/** Çapraz yazar önerisi: e-ticarette aynı siparişte birlikte alınan yazarlar (müşteri bilgisi yok). */
export type AuthorRelated = {
  items: Array<{
    contactId: string;
    name: string | null;
    orders: number;
    theirOrders: number;
    lift: number;
    /** Beklenenden fazla ortak sipariş (sıralama buna göre). */
    excess: number;
    share: number | null;
    books: Array<{ a: string | null; b: string | null; orders: number }>;
  }>;
  total: number;
  page: number;
  pageSize: number;
  authorOrders: number | null;
  minOrders: number;
  minLift: number;
  run: { at: string | null; orders: number; linesMatched: number; lines: number; pairs: number } | null;
  kaynaklar?: Kaynaklar;
};
/** Pazarda bu yazar: Başarı Dağıtım kataloğundaki kitapları (barkodla doğrulanan + ad eşleşmesi; ad eşleşmesi bağlanmaz). */
export type AuthorPazarBook = {
  barkod: string;
  ad: string | null;
  yayinevi: string | null;
  ustKategori: string | null;
  durum: string | null;
  baskiNo: number | null;
  fiyat: number | null;
  basimYili: number | null;
  timas: boolean;
  dogrulandi: boolean;
  drde: boolean;
  cikis: number | null;
};
export type AuthorPazarGroup = { kitap: number; satista: number; baskisiYok: number; diger: number; dogrulanan: number };
export type AuthorPazar = {
  kaynak: string;
  tarih: string | null;
  kaynakZamani: string | null;
  ad: string;
  not: string;
  okundu: boolean;
  kitaplar: AuthorPazarBook[];
  adlar: string[];
  belirsiz: boolean;
  nedenler: string[];
  dogrulanan?: number;
  kitapListesi?: boolean;
  timas?: AuthorPazarGroup;
  diger?: AuthorPazarGroup;
  yayinevleri?: Array<{ yayinevi: string; kitap: number; satista: number; timas: boolean }>;
  enYuksekBaski?: { baski: number; ad: string | null; yayinevi: string | null } | null;
  fiyat?: { enDusuk: number; orta: number; enYuksek: number; kitap: number } | null;
  drdeOlan?: number;
  cikis?: { bas: string; son: string; timas: number; diger: number } | null;
  cikisNot?: string | null;
  kaynaklar?: Kaynaklar;
};
export type AuthorSimilar = {
  cards: Array<{ id: string; name: string; stage: string; stageLabel: string | null; archived: boolean; crmContactId: string | null }>;
  crm: Array<{ crmContactId: string; name: string | null; author: boolean; cardId: string | null }>;
  crmTotal: number;
  crmError?: string | null;
  kaynaklar?: Kaynaklar;
};

const A = '/api/v1/editorial/authors';
export const authorsApi = {
  meta: () => send<AuthorsMeta>('GET', `${A}/meta`, undefined, 30_000),
  cards: (p: { stage?: string; q?: string; scope?: string; archived?: boolean } = {}) =>
    send<{ items: AuthorCardSummary[]; total: number; stages: Record<string, number>; kaynaklar?: Kaynaklar }>(
      'GET',
      `${A}/cards${qs({ stage: p.stage, q: p.q, scope: p.scope, archived: p.archived ? 'true' : undefined })}`,
      undefined,
      30_000,
    ),
  card: (id: string) => send<AuthorCardDetail>('GET', `${A}/cards/${encodeURIComponent(id)}`, undefined, 30_000),
  createCard: (b: AuthorCardInput) => send<AuthorCard>('POST', `${A}/cards`, b, 30_000),
  updateCard: (id: string, b: AuthorCardInput) => send<AuthorCard>('PATCH', `${A}/cards/${encodeURIComponent(id)}`, b, 30_000),
  byCrm: (contactId: string) => send<AuthorByCrm>('GET', `${A}/by-crm/${encodeURIComponent(contactId)}`, undefined, 30_000),
  crmCard: (contactId: string, name: string, stage: string) =>
    send<AuthorCardDetail>('POST', `${A}/by-crm/${encodeURIComponent(contactId)}/card`, { name, stage }, 30_000),
  similar: (name: string) => send<AuthorSimilar>('GET', `${A}/similar${qs({ name })}`, undefined, 60_000),
  poolCrm: (p: { q?: string; page?: number; closed?: boolean }) =>
    send<AuthorPoolCrm>('GET', `${A}/pool/crm${qs({ q: p.q, page: p.page, closed: p.closed ? 'true' : undefined })}`, undefined, 120_000),
  heatmap: (p: { scope?: string; q?: string; order?: string; page?: number }) =>
    send<AuthorHeatmap>('GET', `${A}/heatmap${qs({ scope: p.scope, q: p.q, order: p.order, page: p.page })}`, undefined, 180_000),
  related: (contactId: string, page = 0) =>
    send<AuthorRelated>('GET', `${A}/related/${encodeURIComponent(contactId)}${qs({ page })}`, undefined, 30_000),
  pazar: (p: { contactId?: string | null; name?: string | null }) =>
    send<AuthorPazar>('GET', `${A}/pazar${qs({ kisi: p.contactId || undefined, ad: p.name || undefined })}`, undefined, 60_000),
  agenda: (scope: string, days = 30) => send<AuthorAgenda>('GET', `${A}/agenda${qs({ scope, days })}`, undefined, 30_000),
  createMeeting: (b: AuthorMeetingInput) => send<AuthorMeeting>('POST', `${A}/meetings`, b, 30_000),
  updateMeeting: (id: string, b: AuthorMeetingInput) => send<AuthorMeeting>('PATCH', `${A}/meetings/${encodeURIComponent(id)}`, b, 30_000),
  growth: (contactId: string, refresh = false) =>
    send<AuthorGrowth>('GET', `${A}/growth/${encodeURIComponent(contactId)}${refresh ? '?refresh=true' : ''}`, undefined, 600_000),
  advice: (contactId: string) =>
    send<{ advice: AuthorAdvice | null; modelReady: boolean; kaynaklar?: Kaynaklar }>('GET', `${A}/advice/${encodeURIComponent(contactId)}`, undefined, 30_000),
  makeAdvice: (contactId: string) => send<AuthorAdvice>('POST', `${A}/advice/${encodeURIComponent(contactId)}`, undefined, 600_000),
  snapshot: () => send<AuthorSnapshot>('GET', `${A}/snapshot`, undefined, 30_000),
  refresh: () => send<AuthorSnapshot>('POST', `${A}/refresh`, undefined, 30_000),
  remindersMe: () =>
    send<{ enabled: boolean; smtp: boolean; today: { randevu: number; not: number; adim: number }; kaynaklar?: Kaynaklar }>('GET', `${A}/reminders/me`, undefined, 30_000),
  setReminders: (enabled: boolean) => send<{ enabled: boolean }>('PUT', `${A}/reminders/me`, { enabled }, 30_000),
  deleteMeeting: (id: string) => send<{ ok: boolean }>('DELETE', `${A}/meetings/${encodeURIComponent(id)}`, undefined, 30_000),
};

export type EditorLoad = { id: string; name: string | null; total: number; last: string | null; disabled: boolean; byStatus: ContractFacet[] };
export type EditorsOverview = { items: EditorLoad[]; sinceYear: number; statuses: ContractFacet[]; unassigned: ContractFacet[]; truncated: boolean; db?: DbTiming | null };
export type EditorialProject = {
  id: string;
  name: string | null;
  status: string | null;
  text: string | null;
  stage: string | null;
  textDue: string | null;
  createdOn: string | null;
  modifiedOn: string | null;
  author: string | null;
  editor: string | null;
  projectEditor: string | null;
};

/** M2: editörler ve projeleri (CRM proje kartındaki "Editörü" alanı). */
export const editorsApi = {
  overview: (since?: number) => send<EditorsOverview>('GET', `/api/v1/editorial/editors${qs({ since })}`, undefined, 60_000),
  projects: (p: { q?: string; editor?: string; status?: number; since?: number; page?: number }) =>
    send<{ items: EditorialProject[]; total: number; page: number; pageSize: number; db?: DbTiming | null }>(
      'GET',
      `/api/v1/editorial/projects${qs({ q: p.q, editor: p.editor, status: p.status, since: p.since, page: p.page })}`,
      undefined,
      60_000,
    ),
};

// -------------------------------------------------------- M2 editör atama (yalnız CRM'den okunur) ve Masam › Görevlerim
// Kim hangi projenin editörü CRM'dedir; portal atama yapmaz. Görevlerim'deki durum, termin ve not editörün kendi
// takibidir (köprünün tablosunda; CRM'e yazılmaz).

export type AssignRef = { id: string; name: string | null };
export type AssignProject = {
  id: string;
  name: string | null;
  status: string | null;
  statusCode: number;
  kitaplik: AssignRef | null;
  marka: AssignRef | null;
  crmEditorId: string | null;
  crmEditor: string | null;
  pages: number | null;
  boardApproved: string | null;
  targetPrint: string | null;
  createdOn: string | null;
  modifiedOn: string | null;
  author: string | null;
};
export type TaskStatus = 'sirada' | 'calisiyor' | 'beklemede' | 'tamamlandi' | 'iptal';
/** Görevlerim satırı: CRM projesi + kişinin takip kaydı. Kaydı henüz yoksa `id` boştur, durum «sırada». */
export type EditorTask = {
  id: string | null;
  projectId: string;
  projectName: string | null;
  category: string | null;
  editorId: string | null;
  editorName: string | null;
  role: 'editor' | 'destek';
  roleLabel: string;
  status: TaskStatus;
  statusLabel: string;
  source: 'atama' | 'crm';
  start: string | null;
  due: string | null;
  pages: number | null;
  note: string | null;
  crmEditorId: string | null;
  overdue: boolean;
  createdBy: string | null;
  createdAt: string | null;
  updatedBy: string | null;
  updatedAt: string | null;
  doneAt: string | null;
  project?: AssignProject;
};
export type TaskLogEntry = { at: string; actor: string; action: string; detail: Record<string, unknown> | null };
export type CrmMe = { id: string; name: string | null; disabled: boolean };
export type TaskPatch = Partial<{ status: TaskStatus; start: string | null; due: string | null; pages: number | null; note: string | null; reason: string }>;

export const assignApi = {
  /** status: '100000019|100000020' gibi kodlar, 'hepsi' ya da boş (ilk açılış süzgeci). */
  pending: (p: { q?: string; status?: string; category?: string; page?: number }) =>
    send<{
      items: AssignProject[];
      total: number;
      page: number;
      pageSize: number;
      sinceYear: number;
      statuses: number[];
      defaultStatuses: number[];
      statusFacets: ContractFacet[];
      db?: DbTiming | null;
    }>('GET', `/api/v1/editorial/assignments/pending${qs({ q: p.q, status: p.status, category: p.category, page: p.page })}`, undefined, 60_000),
  history: (id: string) => send<{ items: TaskLogEntry[] }>('GET', `/api/v1/editorial/assignments/tasks/${encodeURIComponent(id)}/history`, undefined, 30_000),
  mine: () =>
    send<{ me: CrmMe | null; user: string; tasks: EditorTask[]; sinceYear?: number; db?: DbTiming | null }>(
      'GET',
      '/api/v1/editorial/tasks/mine',
      undefined,
      60_000,
    ),
  /** Görevlerim: projenin takibini değiştirir; kayıt yoksa köprü açar. */
  updateMine: (projectId: string, b: TaskPatch) => send<EditorTask>('PATCH', `/api/v1/editorial/tasks/mine/${encodeURIComponent(projectId)}`, b, 30_000),
};

// -------------------------------------------------------- editoryal masa (M3 redaksiyon, M5 son okuma)

export type DeskFile = {
  id: string;
  version: number;
  filename: string;
  bytes: number;
  sha256: string;
  uploadedBy: string;
  uploadedAt: string;
  report: {
    chapters?: number;
    words?: number;
    atesman?: number | null;
    pages?: number;
    sizes?: Record<string, number>;
    fonts?: string[];
    unembeddedFonts?: string[];
    images?: number;
    rgbImages?: number;
    isbnsInText?: string[];
    signatures16?: number;
    fullSignatures?: boolean;
    trimBoxMissing?: number;
    versus?: { version: number; pageDelta: number; changedPages: number[] };
  };
};
export type Work = {
  id: string;
  title: string;
  author: string | null;
  projectId: string | null;
  projectName: string | null;
  isbn: string | null;
  createdBy: string;
  createdAt: string;
  members: string[];
  manuscript: DeskFile | null;
  proof: DeskFile | null;
  chapters: { total: number; approved: number; inProgress: number };
  signatures: { total: number; signed: number };
};
export type ChapterRow = {
  id: string;
  no: number;
  title: string;
  status: 'bekliyor' | 'islemde' | 'onaylandi';
  reviewState: 'yok' | 'calisiyor' | 'bitti' | 'hata';
  reviewNote: string | null;
  words: number;
  atesman: number | null;
  pending: number;
  accepted: number;
  rejected: number;
  changed: boolean;
};
export type Suggestion = {
  id: string;
  kind: 'yazim' | 'uslup';
  original: string;
  suggestion: string;
  reason: string | null;
  status: 'bekliyor' | 'kabul' | 'red';
  appliedText: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
};
export type TextMetrics = {
  words: number;
  sentences: number;
  paragraphs: number;
  atesman: number | null;
  band?: string | null;
  syllablesPerWord: number | null;
  wordsPerSentence: number | null;
  longLimit?: number;
  longSentences: Array<{ words: number; text: string }>;
};
export type ChapterDetail = {
  id: string;
  workId: string;
  no: number;
  title: string;
  status: ChapterRow['status'];
  text: string;
  reviewState: ChapterRow['reviewState'];
  reviewNote: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  metrics: TextMetrics;
  originalMetrics: TextMetrics;
  diff: Array<{ op: 'eq' | 'del' | 'ins'; text: string }>;
  suggestions: Suggestion[];
};
export type DeskCheck = { id: string; key: string; label: string; auto: boolean; passed: boolean | null; evidence: string | null; checkedBy: string | null; checkedAt: string | null };
export type DeskSignature = { id: string; role: string; username: string; display: string | null; signedAt: string | null; sha256: string | null; mine: boolean };
export type ProofState = {
  work: Work;
  versions: DeskFile[];
  checks: DeskCheck[];
  signatures: DeskSignature[];
  approved: boolean;
  blocking: { failed: number; open: number; unsigned: number };
};

const upload = async (path: string, file: File) => {
  const res = await fetch(`${ENGINE_BASE}${path}${path.includes('?') ? '&' : '?'}filename=${encodeURIComponent(file.name)}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
    signal: AbortSignal.timeout(600_000),
  });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } } | null;
    throw new Error(j?.detail?.message || httpErrorText(res.status));
  }
  return (await res.json()) as { fileId: string; version: number };
};

/** M3 ve M5: eser dosyaları, metin/prova sürümleri, öneriler, kontroller, imzalar. */
export const deskApi = {
  works: () => send<{ items: Work[]; user: string }>('GET', '/api/v1/editorial/works', undefined, 60_000),
  createWork: (b: { title: string; author?: string }) => send<{ id: string; title: string }>('POST', '/api/v1/editorial/works', b, 30_000),
  updateWork: (id: string, b: Record<string, unknown>) => send<{ ok: boolean }>('PATCH', `/api/v1/editorial/works/${encodeURIComponent(id)}`, b, 30_000),
  uploadManuscript: (id: string, file: File) => upload(`/api/v1/editorial/works/${encodeURIComponent(id)}/manuscript`, file),
  uploadProof: (id: string, file: File) => upload(`/api/v1/editorial/works/${encodeURIComponent(id)}/proof`, file),
  /** Dosyadan yeni eser: ad dosya adından, tek istekte eser + ilk metin/prova sürümü (liste boşken yükleme alanı). */
  createFromFile: (kind: 'manuscript' | 'proof', file: File) =>
    upload(`/api/v1/editorial/works-from-file?kind=${kind}`, file) as Promise<{ fileId: string; version: number; workId: string; title: string }>,
  chapters: (id: string) => send<{ work: Work; chapters: ChapterRow[]; versions: DeskFile[] }>('GET', `/api/v1/editorial/works/${encodeURIComponent(id)}/chapters`, undefined, 60_000),
  chapter: (id: string) => send<ChapterDetail>('GET', `/api/v1/editorial/chapters/${encodeURIComponent(id)}`, undefined, 60_000),
  review: (id: string) => send<{ ok: boolean }>('POST', `/api/v1/editorial/chapters/${encodeURIComponent(id)}/review`, {}, 60_000),
  approve: (id: string, approve: boolean) => send<{ ok: boolean }>('POST', `/api/v1/editorial/chapters/${encodeURIComponent(id)}/approval`, { approve }, 30_000),
  decide: (id: string, decision: 'kabul' | 'red', text?: string) =>
    send<{ ok: boolean }>('POST', `/api/v1/editorial/suggestions/${encodeURIComponent(id)}/decision`, { decision, text }, 30_000),
  proof: (id: string) => send<ProofState>('GET', `/api/v1/editorial/works/${encodeURIComponent(id)}/proof`, undefined, 60_000),
  setCheck: (id: string, passed: boolean | null, note?: string) => send<{ ok: boolean }>('POST', `/api/v1/editorial/checks/${encodeURIComponent(id)}`, { passed, note }, 30_000),
  setSigners: (id: string, signers: Array<{ role: string; username: string; display?: string }>) =>
    send<{ ok: boolean }>('PUT', `/api/v1/editorial/works/${encodeURIComponent(id)}/signers`, { signers }, 30_000),
  sign: (id: string) => send<{ sha256: string; version: number }>('POST', `/api/v1/editorial/works/${encodeURIComponent(id)}/sign`, {}, 30_000),
  fileUrl: (id: string) => `${ENGINE_BASE}/api/v1/editorial/files/${encodeURIComponent(id)}`,
};

// -------------------------------------------------------------------- M4 çeviri

export type SegmentStatus = 'bos' | 'taslak' | 'cevrildi' | 'onaylandi';
export type JobStage = 'kaynak' | 'ceviri' | 'inceleme' | 'tamamlandi';
export type QaIssue = { code: string; text: string };
export type TranslationPace = {
  wordsLast14: number;
  activeDays: number;
  windowDays: number;
  perDay: number;
  finish: string | null;
  daysLeft: number | null;
  needPerDay: number | null;
  late: boolean;
  overdue: boolean;
};
export type TranslationJob = {
  id: string;
  title: string;
  author: string | null;
  sourceLang: string;
  targetLang: string;
  translator: string | null;
  translatorName: string | null;
  reviewer: string | null;
  reviewerName: string | null;
  dueDate: string | null;
  note: string | null;
  createdBy: string;
  createdAt: string;
  completedAt: string | null;
  workId: string | null;
  source: { version: number; filename: string | null; bytes: number; sha256: string | null } | null;
  draft: { state: 'yok' | 'calisiyor' | 'bitti' | 'hata'; note: string | null; done: number; total: number };
  stage: JobStage;
  segments: { total: number } & Record<SegmentStatus, number>;
  words: { total: number; done: number; approved: number };
  pace: TranslationPace;
  roles: { translate: boolean; review: boolean; manage: boolean };
};
export type TranslationChapter = { no: number; title: string; segments: number; words: number; wordsDone: number } & Record<SegmentStatus, number>;
export type TranslationJobDetail = TranslationJob & { chapters: TranslationChapter[]; languages: { source: string | null; target: string | null } };
export type SegmentRow = {
  id: string;
  no: number;
  para: number;
  chapter: number;
  heading: boolean;
  source: string;
  target: string;
  status: SegmentStatus;
  words: number;
  hasDraft: boolean;
  issues: QaIssue[];
  errors: number;
  note: string | null;
  edited: boolean;
  updatedBy: string | null;
  updatedAt: string | null;
};
export type SegmentTerm = { id: string; source: string; target: string; forbidden: string[]; note: string | null; status: 'onayli' | 'aday'; jobOnly: boolean; at: [number, number]; ok: boolean };
export type MemoryMatch = { source: string; target: string; score: number; status: SegmentStatus; job: string; sameJob: boolean };
export type SegmentError = { id: string; category: string; severity: 'kucuk' | 'buyuk' | 'kritik'; note: string | null; by: string; at: string };
export type SegmentDetail = SegmentRow & {
  chapterTitle: string;
  draft: string | null;
  submitted: string | null;
  translatedBy: string | null;
  translatedAt: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  diff: Array<{ op: 'eq' | 'del' | 'ins'; text: string }>;
  terms: SegmentTerm[];
  memory: MemoryMatch[];
  context: Array<{ no: number; source: string; target: string }>;
  errorList: SegmentError[];
  roles: TranslationJob['roles'];
  jobId: string;
};
export type Term = {
  id: string;
  sourceLang: string;
  targetLang: string;
  source: string;
  target: string;
  forbidden: string[];
  note: string | null;
  jobId: string | null;
  jobTitle?: string | null;
  status: 'onayli' | 'aday';
  createdBy: string;
  createdAt: string;
  updatedBy: string | null;
  updatedAt: string | null;
};
export type TermCandidate = { term: string; count: number; example: string };
export type TranslatorCard = {
  username: string;
  name: string | null;
  jobs: number;
  active: number;
  completed: number;
  onTime: number;
  late: number;
  words: number;
  wordsDone: number;
  reviewedWords: number;
  penalty: number;
  mqm: number | null;
  pairs: string[];
};
export type QualityReport = TranslationJob & {
  mqm: { score: number | null; penalty: number; reviewedWords: number; weights: Record<string, number>; categories: Record<string, Record<string, number>>; errors: number };
  edits: { segments: number; reviewed: number; rate: number | null };
  checks: { byCode: Record<string, number>; segments: number; labels: Record<string, string>; items: Array<{ id: string; no: number; chapter: number; source: string; target: string; status: SegmentStatus; issues: QaIssue[] }> };
  terms: { uses: number; ok: number; items: Array<{ source: string; target: string; uses: number; ok: number }> };
  chapters: Array<{ no: number; title: string; words: number; done: number; approved: number; issues: number; errors: number; penalty: number; reviewedWords: number; mqm: number | null }>;
  daily: Array<{ date: string; cevrildi: number; onaylandi: number; geri: number }>;
  people: Array<{ username: string; cevrildi: number; onaylandi: number; geri: number }>;
  errorList: Array<{ id: string; segmentNo: number | null; segmentId: string; category: string; severity: string; note: string | null; by: string; at: string; source: string; target: string }>;
  categoryLabels: Record<string, string>;
  severityLabels: Record<string, string>;
};

export async function putFile<T>(path: string, file: File): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}${path.includes('?') ? '&' : '?'}filename=${encodeURIComponent(file.name)}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
    signal: AbortSignal.timeout(600_000),
  });
  if (res.status === 403) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } } | null;
    if (j?.detail?.code === 'FORBIDDEN') throw new EngineForbiddenError(j.detail.message);
    if (j?.detail?.message) throw new Error(j.detail.message);
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (res.status === 401) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { message?: string } } | null;
    throw new Error(j?.detail?.message || httpErrorText(res.status));
  }
  return (await res.json()) as T;
}

const TR = '/api/v1/editorial/translation';
const enc = encodeURIComponent;

export const translationApi = {
  jobs: (mine = false) =>
    send<{ items: TranslationJob[]; user: string; languages: Record<string, string>; seeAll: boolean }>('GET', `${TR}/jobs${mine ? '?mine=1' : ''}`, undefined, 60_000),
  job: (id: string) => send<TranslationJobDetail>('GET', `${TR}/jobs/${enc(id)}`, undefined, 60_000),
  createJob: (b: Record<string, unknown>) => send<{ id: string; title: string }>('POST', `${TR}/jobs`, b, 30_000),
  updateJob: (id: string, b: Record<string, unknown>) => send<{ ok: boolean }>('PATCH', `${TR}/jobs/${enc(id)}`, b, 30_000),
  deleteJob: (id: string) => send<{ ok: boolean }>('DELETE', `${TR}/jobs/${enc(id)}`, undefined, 60_000),
  uploadSource: (id: string, file: File) =>
    putFile<{ version: number; segments: number; chapters: number; words: number; carried: number }>(`${TR}/jobs/${enc(id)}/source`, file),
  sourceUrl: (id: string) => `${ENGINE_BASE}${TR}/jobs/${enc(id)}/source`,
  /** Dosyadan yeni çeviri işi: ad dosya adından, dil çifti yükleme alanından; iş + kaynak v1 tek istekte. */
  createFromFile: (file: File, sourceLang: string, targetLang: string) =>
    putFile<{ jobId: string; title: string; version: number; segments: number; chapters: number; words: number; carried: number }>(
      `${TR}/jobs-from-file${qs({ sourceLang, targetLang })}`,
      file,
    ),
  segments: (id: string, p: { chapter?: number | null; filter?: string; q?: string }) =>
    send<{ items: SegmentRow[]; total: number; roles: TranslationJob['roles'] }>(
      'GET',
      `${TR}/jobs/${enc(id)}/segments${qs({ chapter: p.chapter ?? undefined, filter: p.filter, q: p.q || undefined })}`,
      undefined,
      60_000,
    ),
  segment: (id: string) => send<SegmentDetail>('GET', `${TR}/segments/${enc(id)}`, undefined, 30_000),
  save: (id: string, b: { target: string; status: 'taslak' | 'cevrildi'; updatedAt?: string | null; note?: string }) =>
    send<{ status: SegmentStatus; updatedAt: string; repeatsFilled: number }>('PUT', `${TR}/segments/${enc(id)}`, b, 30_000),
  review: (id: string, b: { action: 'onayla' | 'geri'; target?: string; toTranslator?: boolean; note?: string }) =>
    send<{ updatedAt: string }>('POST', `${TR}/segments/${enc(id)}/review`, b, 30_000),
  /** İşteki bir sonraki segment (süzgeçten bağımsız) ve birleştirilebilir mi; birleştir/böl: çevirmen ya da işi yöneten. */
  segmentNext: (id: string) =>
    send<{ next: { id: string; no: number; para: number; source: string; target: string; status: SegmentStatus; updatedAt: string | null } | null; mergeable: boolean; reason: string | null }>('GET', `${TR}/segments/${enc(id)}/next`, undefined, 30_000),
  mergeNext: (id: string, b: { nextId: string; updatedAt?: string | null; nextUpdatedAt?: string | null }) =>
    send<{ id: string; removed: string; source: string; target: string; status: SegmentStatus; words: number; demoted: boolean; updatedAt: string }>('POST', `${TR}/segments/${enc(id)}/merge`, b, 30_000),
  split: (id: string, b: { at: number; source: string; updatedAt?: string | null }) =>
    send<{ id: string; newId: string; source: string; newSource: string; status: SegmentStatus; words: number; demoted: boolean; updatedAt: string }>('POST', `${TR}/segments/${enc(id)}/split`, b, 30_000),
  addError: (id: string, b: { category: string; severity: string; note?: string }) => send<{ id: string }>('POST', `${TR}/segments/${enc(id)}/errors`, b, 30_000),
  deleteError: (id: string) => send<{ ok: boolean }>('DELETE', `${TR}/errors/${enc(id)}`, undefined, 30_000),
  approveMany: (id: string, chapter: number | null) => send<{ approved: number }>('POST', `${TR}/jobs/${enc(id)}/approve`, { chapter }, 60_000),
  useDraft: (id: string, chapter: number | null) => send<{ filled: number }>('POST', `${TR}/jobs/${enc(id)}/use-draft`, { chapter }, 60_000),
  draft: (id: string, chapter: number | null) => send<{ segments: number }>('POST', `${TR}/jobs/${enc(id)}/draft`, { chapter }, 60_000),
  candidates: (id: string) => send<{ items: TermCandidate[] }>('GET', `${TR}/jobs/${enc(id)}/candidates`, undefined, 60_000),
  quality: (id: string) => send<QualityReport>('GET', `${TR}/jobs/${enc(id)}/quality`, undefined, 120_000),
  qualityCsvUrl: (id: string) => `${ENGINE_BASE}${TR}/jobs/${enc(id)}/quality.csv`,
  docxUrl: (id: string) => `${ENGINE_BASE}${TR}/jobs/${enc(id)}/export.docx`,
  xliffUrl: (id: string) => `${ENGINE_BASE}${TR}/jobs/${enc(id)}/export.xlf`,
  importXliff: (id: string, file: File) =>
    putFile<{ updated: number; confirmed: number; locked: number; unknown: number; unchanged: number }>(`${TR}/jobs/${enc(id)}/xliff`, file),
  toRedaction: (id: string) => send<{ workId: string; version: number; chapters: number }>('POST', `${TR}/jobs/${enc(id)}/to-redaction`, {}, 120_000),
  translators: () => send<{ items: TranslatorCard[] }>('GET', `${TR}/translators`, undefined, 60_000),
  terms: (p: { src?: string; tgt?: string; q?: string; status?: string; job?: string }) =>
    send<{ items: Term[]; languages: Record<string, string> }>('GET', `${TR}/terms${qs({ src: p.src || undefined, tgt: p.tgt || undefined, q: p.q || undefined, status: p.status || undefined, job: p.job || undefined })}`, undefined, 60_000),
  createTerm: (b: Record<string, unknown>) => send<{ id: string }>('POST', `${TR}/terms`, b, 30_000),
  proposeTerm: (b: Record<string, unknown>) => send<{ id: string }>('POST', `${TR}/terms/propose`, b, 30_000),
  updateTerm: (id: string, b: Record<string, unknown>) => send<{ ok: boolean }>('PATCH', `${TR}/terms/${enc(id)}`, b, 30_000),
  deleteTerm: (id: string) => send<{ ok: boolean }>('DELETE', `${TR}/terms/${enc(id)}`, undefined, 30_000),
  importTerms: (src: string, tgt: string, file: File) =>
    putFile<{ added: number; updated: number; skipped: number }>(`${TR}/terms/import?src=${enc(src)}&tgt=${enc(tgt)}`, file),
  termsCsvUrl: (src?: string, tgt?: string) => `${ENGINE_BASE}${TR}/terms/export.csv${qs({ src: src || undefined, tgt: tgt || undefined })}`,
};

// ------------------------------------------------------ çeviri işi → serbest çalışan işi ve hakediş (M4 → M8)

export type PayoutBasis = 'onaylanan' | 'cevrilen';
export type TranslationPayout = {
  jobId: string;
  words: { total: number; approved: number; translated: number };
  bases: Record<PayoutBasis, string>;
  unit: string;
  wordsPerPage: number;
  /** M8'de çeviri rolündeki aktif kişiler; kartında kelime ücreti yazılıysa `rate`. */
  people: Array<{ id: string; name: string; city: string | null; email: string | null; rate: number | null }>;
  link: {
    personId: string;
    personName: string | null;
    personActive: boolean;
    rate: number;
    basis: PayoutBasis;
    basisWords: number;
    transferred: number;
    pending: number;
    pendingAmount: number;
    transferredAmount: number;
    ahead: number;
    updatedBy: string;
    updatedAt: string | null;
  } | null;
  task: { id: string; title: string; status: string; units: number; unitPrice: number; due: string | null; open: boolean } | null;
  package: { id: string; title: string; status: 'acik' | 'kapandi' | 'iptal' } | null;
  moves: Array<{
    id: string;
    taskId: string;
    words: number;
    basis: PayoutBasis;
    rate: number;
    amount: number;
    by: string;
    at: string;
    payout: { id: string; no: number; status: string } | null;
  }>;
};

export const translationPayoutApi = {
  get: (jobId: string) => send<TranslationPayout>('GET', `${TR}/jobs/${enc(jobId)}/payout`, undefined, 30_000),
  save: (jobId: string, b: { personId: string; rate: string; basis: PayoutBasis }) =>
    send<{ personId: string; personName: string; rate: number; basis: PayoutBasis }>('PUT', `${TR}/jobs/${enc(jobId)}/payout`, b, 30_000),
  openPackage: (jobId: string) =>
    send<{ packageId: string; taskId: string; created: boolean; units: number }>('POST', `${TR}/jobs/${enc(jobId)}/payout/package`, {}, 60_000),
  transfer: (jobId: string) =>
    send<{ moved: number; transferred: number; amount: number; taskId: string | null }>('POST', `${TR}/jobs/${enc(jobId)}/payout/transfer`, {}, 60_000),
};

// ------------------------------------------------------ editoryal arama ve kitap 360 (ana ekran)

export type SearchHit = { kind: 'kitap' | 'proje' | 'kisi'; id: string; title: string | null; note: string | null; extra: string | null; status: string | null; date: string | null };
export type SearchKind = 'kitap' | 'proje' | 'kisi';
/** Her türün ilk sayfası (ya da `kind` ile istenen sayfası) ve o türde eşleşen bütün kayıtların sayısı. */
export type EditorialSearch = {
  books: SearchHit[];
  projects: SearchHit[];
  people: SearchHit[];
  totals: Partial<Record<'books' | 'projects' | 'people', number>>;
  query: string;
  page: number;
  pageSize: number;
  db?: DbTiming | null;
};
export type BookDetail = {
  id: string;
  title: string | null;
  isbn: string | null;
  ebookIsbn: string | null;
  pages: number | null;
  size: string | null;
  price: number | null;
  printNo: number | null;
  printTotal: number | null;
  firstPrint: number | null;
  firstPublished: string | null;
  lastPublished: string | null;
  lastPrint: string | null;
  genres: string | null;
  shelf: string | null;
  originalLanguage: string | null;
  royaltyState: string | null;
  printState: string | null;
  status: string | null;
  editorNote: string | null;
  illustratorsText: string | null;
  translatorsText: string | null;
  authorsText: string | null;
  /** Kitabın konusu (CRM tanıtım metni, yoksa projenin fikri); HTML'den düz metne çevrilmiş. */
  summary: string | null;
  summaryFrom: string | null;
  roles: Array<{ role: string; people: Array<{ id: string | null; name: string | null }> }>;
  contracts: Array<{ id: string; no: string | null; kind: string | null; status: string | null; stage: string | null; start: string | null; end: string | null; royalty: number | null; daysLeft: number | null } & CrmRightsFields>;
  rights?: BookRights;
  projects: Array<{ id: string; name: string | null; status: string | null; text: string | null; stage: string | null; on: string | null; editor: string | null; idea: string | null }>;
  board: Array<{ id: string; date: string | null; decision: string | null; note: string | null; royalty: number | null; printRun: string | null; project: string | null }>;
  production: Array<{ id: string; on: string | null; delivery: string | null; editorial: string | null; firstText: string | null; status: string | null; editor: string | null; designer: string | null }>;
  desk: Work[];
  /** Kitap editöre yüklenmişse: editördeki kimliği ve bekleyen inceleme sayısı. */
  editorBook?: { id: string; title: string | null; generationId: string | null; codeVersion: string | null; open: number } | null;
  db?: DbTiming | null;
};

/** İnceleme kaydının ekranda gösterilen hâli. Motorun kendi notu, güven puanı ve İngilizce etiketler
 *  sunucuda kalır; buraya yalnız editörün okuyacağı Türkçe gelir. */
export type BookReviewAction = { key: 'yes' | 'no' | 'fix'; label: string; tone: 'primary' | 'ghost' };
export type BookReviewItem = {
  id: string;
  type: string;
  priority: number;
  pages: number[];
  subject: string;
  question: string;
  statement: string;
  quote: { text: string; page: number } | null;
  figures: string[];
  actions: BookReviewAction[];
  link: 'proofing' | null;
  /** Kitabın türüne uymayan okumanın sorusu (ör. kişisel gelişim kitabında «kim yaptı»): cevaplanabilir,
   *  ama kabulü engellemez ve `open` sayısına girmez. Eski kart servisi göndermez. */
  advisory?: boolean;
};
export type BookReviewGroup = { type: string; title: string; bulk: boolean; items: BookReviewItem[] };
export type BookReviewQueue = {
  book_id: string;
  title: string;
  generation_id: string;
  groups: BookReviewGroup[];
  open: number;
  /** Açık öneriler (advisory); kabulü engellemez. */
  advice?: number;
  decided: number;
};

export type BookPageContext = {
  page_no: number;
  texts: Array<{ source: string; text: string }>;
  regions: Array<{ id: string; label: string; kind: string; bbox: number[] | null; description: string | null }>;
};

/** Analizin emin olamayıp insana sorduğu kayıtlar. Karar veren kişi oturumdan gelir; istemci ad göndermez.
 *  `choice` kaydın kendi sorusunun cevabıdır: yes / no / fix (fix bir not ister). */
export const bookReviewApi = {
  queue: (bookId: string) =>
    send<BookReviewQueue>('GET', `/api/v1/editorial/books/${encodeURIComponent(bookId)}/review`, undefined, 60_000),
  decide: (bookId: string, items: string[], choice: BookReviewAction['key'], note?: string) =>
    send<{ decided: number; failed: Array<{ item: string; error: string }> }>(
      'POST', `/api/v1/editorial/books/${encodeURIComponent(bookId)}/review/decide`,
      { items, choice, ...(note ? { note } : {}) }, 120_000),
  pageContext: (bookId: string, page: number) =>
    send<BookPageContext>('GET', `/api/v1/editorial/books/${encodeURIComponent(bookId)}/pages/${page}/context`, undefined, 60_000),
  /** Sohbetteki sayfa rozetiyle aynı uç: küçültülmüş WebP, köprü bir saat önbellekler. */
  pageUrl: (bookId: string, page: number, width = 480) =>
    `${ENGINE_BASE}/api/v1/editorial/ask/pages/${encodeURIComponent(bookId)}/${Math.max(1, Math.floor(page))}?w=${Math.max(1, Math.floor(width))}`,
  figureUrl: (bookId: string, regionId: string) =>
    `${ENGINE_BASE}/api/v1/editorial/books/${encodeURIComponent(bookId)}/figures/${encodeURIComponent(regionId)}`,
};

/** Editoryal ana ekranın arama kutusu ve kitabın bütün süreçlerini toplayan sayfa. */
export const editorialSearchApi = {
  search: (q: string, kind?: SearchKind, page?: number) => send<EditorialSearch>('GET', `/api/v1/editorial/search${qs({ q, kind, page })}`, undefined, 60_000),
  book: (id: string) => send<BookDetail>('GET', `/api/v1/editorial/books/${encodeURIComponent(id)}`, undefined, 60_000),
  personBooks: (id: string, page?: number) =>
    send<{ items: SearchHit[]; total: number; page: number; pageSize: number; db?: DbTiming | null }>('GET', `/api/v1/editorial/people/${encodeURIComponent(id)}/books${qs({ page })}`, undefined, 60_000),
};

// ------------------------------------------------ kitabın içeriğine soru (editör motoru, Hermes)

export type BookCard = {
  id: string;
  title: string;
  authors: string[];
  summary: Array<{ text: string; pages: number[] }>;
  cover: { source: string; page: number | null } | null;
  contentAvailable: boolean;
  generationId: string;
  revision: number | null;
  semanticAcceptance: boolean;
  /** Yazar kitaptan mı doğrulandı, yoksa yayınevinin CRM kaydından mı geliyor. */
  authorsSource?: 'BOOK' | 'CRM' | null;
  /** Yayınevinin CRM kaydı; kitabın metninden doğrulanmış değildir. */
  publisher?: {
    source: 'CRM';
    title: string;
    matchedBy: string;
    authors: string[];
    illustrators: string[];
    summary: string | null;
    isbn: string | null;
    firstPublishDate: string | null;
  } | null;
  /** Kitabın hangi türden okunduğu (motorun book_type'ı). `source`: CRM türü belirledi, ya da CRM'de tür
   *  yok/iki türe işaret ediyor ve ZEKİ AI kitabın metninden belirledi (MODEL); NONE ise belirlenemedi. */
  profile?: {
    form: BookForm;
    source: 'CRM' | 'MODEL' | 'EDITOR' | 'NONE';
    audience: 'CHILD' | 'YOUNG' | 'ADULT' | 'UNKNOWN';
    crmGenres: string[];
    probability: number | null;
  } | null;
};

export type BookForm = 'FICTION' | 'NARRATIVE_NONFICTION' | 'EXPOSITORY' | 'ACTIVITY' | 'POETRY' | 'UNKNOWN';
export const BOOK_FORM_TR: Record<BookForm, string> = {
  FICTION: 'Kurgu',
  NARRATIVE_NONFICTION: 'Gerçek kişi ve olay anlatısı',
  EXPOSITORY: 'Fikir, bilgi ya da rehber',
  ACTIVITY: 'Etkinlik ya da ders kitabı',
  POETRY: 'Şiir',
  UNKNOWN: 'Belirlenemedi',
};

export type BookQuestion = {
  id: string;
  bookKey: string;
  bookTitle: string | null;
  /** Kart kimliği: kitap adı kataloğa tam eşleşince köprü ekler; sayfa rozetlerinin görsel önizlemesi buna bağlıdır.
   *  Yoksa rozet düz metin kalır (önizleme yok). */
  bookId?: string | null;
  cards?: BookCard[];
  cardError?: string | null;
  cardMatch?: string | null;
  question: string;
  status: 'bekliyor' | 'calisiyor' | 'bitti' | 'hata';
  answer: string | null;
  /** Karakter sorusunda köprünün eklediği ağ verisi (graf aracından): düğüm = karakter, kenar = ortak olay.
   *  Yoksa ekranda yalnız metin gösterilir. */
  graph?: { nodes: { name: string; count: number; role?: 'lead' | 'family' | 'other' }[];
            edges: { a: string; b: string; weight: number }[] } | null;
  /** Cevap «Kitapta bulunamadı.» ile başlıyorsa true; ekran bunu sakin bir kart olarak gösterir. */
  notFound: boolean;
  error: string | null;
  elapsedMs: number | null;
  username: string;
  createdAt: string;
  finishedAt: string | null;
};

/** Kapak görselinin adresi (oturum çerezi tarayıcıdan gider). Kart `cover` null ise 404 döner; ekran `onError` ile gizler. */
export const bookCoverUrl = (bookId: string) => `${ENGINE_BASE}/api/v1/editorial/ask/covers/${encodeURIComponent(bookId)}`;

/** Motorun kitap kataloğu (kart özeti): sohbet çipleri ve kitap detayı, kitap adını burada eşleyip kapağı bulur. */
export const bookCatalogApi = {
  list: () => send<{ items: BookCard[] }>('GET', '/api/v1/editorial/ask/catalog', undefined, 30_000),
};

/** Kitap adının katalogdaki kartı: motor adı (`title`) ya da yayınevinin CRM adı (`publisher.title`) ile
 *  büyük/küçük harf farksız tam eşleşme. Eşleşme yoksa null (yer tutucu gösterilmez). */
export function findCatalogCard(cards: BookCard[] | undefined, title: string | null | undefined): BookCard | null {
  const key = (title ?? '').trim().toLocaleLowerCase('tr');
  if (!key || !cards) return null;
  return cards.find((c) => c.title.trim().toLocaleLowerCase('tr') === key || (c.publisher?.title ?? '').trim().toLocaleLowerCase('tr') === key) ?? null;
}

/** Soru bir iştir: motor modeli istendiğinde açar ve GPU kitap analiziyle paylaşılır. */
export const bookAskApi = {
  list: (bookKey?: string) => send<{ items: BookQuestion[]; running: number; configured: boolean }>('GET', `/api/v1/editorial/ask${qs({ book: bookKey })}`, undefined, 30_000),
  ask: (b: { question: string; bookKey?: string; bookTitle?: string; parentId?: string }) => send<{ id: string; status: string }>('POST', '/api/v1/editorial/ask', b, 30_000),
  one: (id: string) => send<BookQuestion>('GET', `/api/v1/editorial/ask/${encodeURIComponent(id)}`, undefined, 30_000),
  /** Sayfa rozeti önizlemesi: kitabın son neslinde o sayfanın render'ı. Oturum çerezi tarayıcıdan gider;
   *  köprü bir saat önbelleklettiği için aynı sayfa ikinci kez anında açılır. */
  pageImageUrl: (bookId: string, pageNo: number, width = 480) =>
    `${ENGINE_BASE}/api/v1/editorial/ask/pages/${encodeURIComponent(bookId)}/${Math.max(1, Math.floor(pageNo))}?w=${Math.max(1, Math.floor(width))}`,
  /** Ekrandaki sohbetin PDF'i (sunucuda üretilir): `ids` bu açılışta gösterilen soruların kimlikleri, ekran sırasıyla.
   *  Oturum çerezi tarayıcıdan gider; başkasının sorusu 403 döner. `book` başlıktaki kitap adı (isteğe bağlı). */
  exportUrl: (ids: string[], book?: string) => `${ENGINE_BASE}/api/v1/editorial/ask/export.pdf${qs({ ids: ids.join(','), book })}`,
};

// ------------------------------------------------------ M5: motorun otomatik son okuma denetimleri

export type ProofingSeverity = 'INFO' | 'WARN' | 'ERROR';
/** Motordaki tek bir denetimin (ör. yazım, tutarlılık) son koşusu. FAILED ise `error` dolu gelir. */
export type ProofingCheck = {
  name: string;
  label: string;
  version: string;
  status: 'SUCCEEDED' | 'FAILED';
  startedAt: string | null;
  finishedAt: string | null;
  findings: number;
  /** WARN + ERROR sayısı. */
  serious: number;
  error: string | null;
  /** Kuralın (ad+sürüm) isabeti: bütün kitaplardaki geçerli editör kararlarından; hiç karar yoksa null. */
  precision: ProofingPrecision | null;
  /** Önceki okumada «yanlış alarm» denip taşındığı için `findings`/`serious` sayılarına girmeyen bulgular. */
  hidden?: number;
};
export type ProofingPrecision = { accepted: number; rejected: number; rate: number };
export type ProofVerdict = 'ACCEPT' | 'REJECT';
/** Yanlış alarm gerekçesi (kapalı küme; kart servisiyle aynı). */
export type ProofReasonCode = 'TEXT_CORRECT' | 'INTENDED_STYLE' | 'DICTIONARY_GAP' | 'WRONG_PAGE' | 'EXPLAINED_IN_TEXT' | 'NOT_AN_ISSUE' | 'OTHER';
/** Taşınan kararın kaynağı: aynı kitabın önceki okumasında (ya da aynı okumanın önceki koşusunda) verilen karar. */
export type ProofDecisionSource = {
  decisionId: string;
  findingId: string;
  generationId: string;
  /** Kaynak aynı okumanın (nesil) eski bir koşusu mu. */
  sameReading: boolean;
  page: number | null;
  /** Kararın verildiği kural sürümü (bugünkü sürümden farklı olabilir). */
  checkVersion: string | null;
  /** Kaynak okumanın (denetim koşusunun) zamanı. */
  readAt: string | null;
};
/** Editörün bulguya geçerli (en yeni) kararı; salt eklemedir, yeni karar eskisini geçersiz kılar.
 *  `inherited`: bu bulgunun kendi kararı yok, aynı kitabın önceki okumasındaki aynı bulgunun kararı gösteriliyor
 *  (veritabanına yazılmamıştır; editör onaylar/değiştirir/geri alırsa `carriedFrom` ile yazılır). */
export type ProofDecision = {
  verdict: ProofVerdict;
  reasonCode: ProofReasonCode | null;
  note: string | null;
  decidedBy: string;
  at: string | null;
  inherited?: boolean;
  source?: ProofDecisionSource;
};
export type ProofingFinding = {
  /** proof_finding kimliği; karar bu kimliğe iliştirilir. Eski kart servisi göndermezse null. */
  id: string | null;
  decision: ProofDecision | null;
  check: string;
  label: string;
  page: number | null;
  severity: ProofingSeverity;
  /** Sade bulgu metni: ne sorun, nerede, neden önemli (kart servisi kayıtlı alanlardan üretir; Word'deki yorumla aynı). */
  message: string;
  quote: string | null;
  /** Ne yapılabilir: somut öneri cümlesi. */
  suggestion: string | null;
  /** Sayısal ayrıntı, sade dille («Okunurluk oranı 2,4; en az 4,5 olmalı.»); ekranda katlanır. Eski servis göndermez. */
  detail?: string | null;
  bbox: [number, number, number, number] | null;
  /** Denetimin varsayımı bu tür kitapta geçerli değilse (ör. kişisel gelişim kitabında eşya sürekliliği)
   *  bulgu öneri olarak gelir: seviye INFO, burada nedeni. Eski kart servisi göndermez. */
  advisory?: string | null;
  /** Birlikte karar verilebilecek bulguların ortak anahtarı (ör. kelime tekrarında «kök · anlam»). */
  group?: string | null;
  /** Modelin bulguya güveni (0..1); gruplu görünümde sıralama için. */
  confidence?: number | null;
  /** Aynı sayfada işaretlenecek öbür yerler (0..1000); ör. tekrarın bütün geçişleri. */
  marks?: Array<[number, number, number, number]> | null;
};
/** Eşleşme köprüde kitap adıyla yapılır; `bookId` null ise eser motorda okunmamıştır. */
export type ProofingReport = {
  configured: boolean;
  bookId: string | null;
  bookTitle: string | null;
  generationId: string | null;
  checks: ProofingCheck[];
  findings: ProofingFinding[];
};

/** Kelime haritasında bir kökün bir anlamı (model gruplaması; deyimse `idiom` mastar hâliyle). */
export type WordSense = { label: string; idiom: string; count: number; pages: number[]; example: string };
/** Kitabın tekil kelime haritasında bir kök: biçimler ve sayfalar; ≥2 geçen içerik kökünde anlamlar. */
export type WordMapEntry = {
  lemma: string;
  pos: string | null;
  count: number;
  forms: Record<string, number>;
  pages: number[];
  ambiguous: boolean;
  senses: WordSense[];
};
export type WordMapSummary = {
  wordTokens: number | null;
  contentTokens: number | null;
  distinctLemmas: number | null;
  distinctContentLemmas: number | null;
  hapaxContentLemmas: number | null;
  polysemousLemmas: number | null;
  idiomSenses: number | null;
  mtldLemma: number | null;
  mtldForm: number | null;
  candidates: number | null;
  kept: number | null;
  droppedAsIntentional: number | null;
  nearDifferentSense: number | null;
  senseUnassigned: number | null;
};
/** Son okuma `word_variety` denetiminin haritası; denetim koşmadıysa `ready: false`. */
export type WordMap = {
  bookId: string;
  generationId: string | null;
  ready: boolean;
  version: string | null;
  finishedAt: string | null;
  summary: WordMapSummary | null;
  words: WordMapEntry[];
  /** Yakın geçen ama anlamı farklı geçişler (tekrar sayılmadı); `passage`ta geçişler [[ ]] içinde. */
  nearDifferentSense: Array<{ lemma: string; pages: number[]; senses: string[]; passage: string }>;
  unknownForms: Array<{ form: string; count: number; pages: number[] }>;
};

export const proofingApi = {
  get: (bookTitle: string) => send<ProofingReport>('GET', `/api/v1/editorial/proofing${qs({ book: bookTitle })}`, undefined, 30_000),
  /** Editörün bulguya kararı; kararı veren oturumdaki kullanıcıdır, gövdede gönderilmez. `CLEAR` = «geri al»
   *  (bulgunun kararı yok; önceki okumadan taşınan karar bu bulguya uygulanmaz). `carriedFrom`: editör önceki
   *  okumadan taşınan kararı görürken karar verdiyse o kararın kimliği (isabet ikinci kez saymaz). */
  decide: (b: { bookId: string; findingId: string; verdict: ProofVerdict | 'CLEAR'; reasonCode?: ProofReasonCode; note?: string; carriedFrom?: string }) =>
    send<{ finding_id: string; decision: ProofDecision | null }>('POST', '/api/v1/editorial/proofing/decision', b, 30_000),
  /** Bulgular kitabın metnine Word yorumu olarak işlenmiş .docx (yanlış alarm denenler hariç). */
  exportDocx: async (bookId: string): Promise<{ blob: Blob; name: string }> => {
    const res = await fetch(`${ENGINE_BASE}/api/v1/editorial/proofing/export.docx${qs({ bookId })}`, {
      credentials: 'include',
      signal: AbortSignal.timeout(300_000),
    });
    if (res.status === 401 || res.status === 403) {
      authBlocked = true;
      throw new EngineAuthError();
    }
    if (!res.ok) {
      const j = (await res.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(j?.detail || `Word dosyası üretilemedi (${res.status})`);
    }
    const star = /filename\*=UTF-8''([^;]+)/.exec(res.headers.get('Content-Disposition') ?? '');
    const plain = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '');
    return { blob: await res.blob(), name: star ? decodeURIComponent(star[1]) : plain?.[1] ?? 'son-okuma.docx' };
  },
  /** Kelime haritası (kök, biçim, sayfa, anlam, deyim); motordaki kitap kimliğiyle. */
  wordMap: (bookId: string) => send<WordMap>('GET', `/api/v1/editorial/proofing/word-map${qs({ bookId })}`, undefined, 30_000),
};

/** Belge incelemesi: Son Okuma ekranından yüklenen belge (doc, docx, pdf, odt, rtf, txt, md) üstünde metin denetimleri. */
export type DocumentStatus = 'QUEUED' | 'RUNNING' | 'DONE' | 'FAILED';
export type DocumentItem = {
  id: string;
  title: string;
  file_name: string;
  format: string;
  /** PRINTED: PDF'in basılı sayfaları; APPROXIMATE: sayfasız belge ~250 sözcüklük sayfalara bölündü. */
  page_kind: 'PRINTED' | 'APPROXIMATE';
  words: number;
  status: DocumentStatus;
  error: string | null;
  uploaded_by: string;
  created_at: string;
  finished_at: string | null;
  serious: number;
};
export type DocumentReport = {
  document: DocumentItem & { audience: string | null; age_from: number | null; age_to: number | null; pages: number };
  checks: ProofingCheck[];
  findings: ProofingFinding[];
};
export const DOCUMENT_ACCEPT = '.doc,.docx,.pdf,.odt,.rtf,.txt,.md';

export const documentApi = {
  list: () => send<{ items: DocumentItem[] }>('GET', '/api/v1/editorial/documents', undefined, 30_000),
  get: (id: string) => send<DocumentReport>('GET', `/api/v1/editorial/documents/${encodeURIComponent(id)}`, undefined, 30_000),
  wordMap: (id: string) => send<WordMap>('GET', `/api/v1/editorial/documents/${encodeURIComponent(id)}/word-map`, undefined, 30_000),
  /** Ham dosya gövdesi (müsvedde yüklemesiyle aynı yol); başlık, okur kitlesi ve yaş isteğe bağlı. */
  upload: async (file: File, o: { title?: string; audience?: string; ageFrom?: string; ageTo?: string } = {}) => {
    const q = qs({ filename: file.name, title: o.title || undefined, audience: o.audience || undefined, ageFrom: o.ageFrom || undefined, ageTo: o.ageTo || undefined });
    const res = await fetch(`${ENGINE_BASE}/api/v1/editorial/documents${q}`, {
      method: 'PUT',
      credentials: 'include',
      headers: { 'Content-Type': 'application/octet-stream' },
      body: file,
      signal: AbortSignal.timeout(600_000),
    });
    if (res.status === 401 || res.status === 403) {
      authBlocked = true;
      throw new EngineAuthError();
    }
    if (!res.ok) {
      const j = (await res.json().catch(() => null)) as { detail?: string | { message?: string } } | null;
      const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
      throw new Error(msg || httpErrorText(res.status));
    }
    return (await res.json()) as DocumentItem;
  },
  exportDocx: async (id: string): Promise<{ blob: Blob; name: string }> => {
    const res = await fetch(`${ENGINE_BASE}/api/v1/editorial/documents/${encodeURIComponent(id)}/export.docx`, {
      credentials: 'include',
      signal: AbortSignal.timeout(300_000),
    });
    if (res.status === 401 || res.status === 403) {
      authBlocked = true;
      throw new EngineAuthError();
    }
    if (!res.ok) {
      const j = (await res.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(j?.detail || `Word dosyası üretilemedi (${res.status})`);
    }
    const star = /filename\*=UTF-8''([^;]+)/.exec(res.headers.get('Content-Disposition') ?? '');
    return { blob: await res.blob(), name: star ? decodeURIComponent(star[1]) : 'inceleme.docx' };
  },
};

/** Soru sorulabilen (okunmuş) kitaplar; motordan gelir, köprüde kısa süre önbellekte tutulur. */
export const readableBooksApi = {
  list: () => send<{ items: string[]; at: number | null; configured: boolean; loading: boolean }>('GET', '/api/v1/editorial/ask/books', undefined, 30_000),
};


export type EditorialHomeSnapshot = {
  parts: {
    readableBooks: EditorialSnapshotPart<{ items: string[]; at: number | null; configured: boolean; loading: boolean }>;
    contracts: EditorialSnapshotPart<ContractSummary>;
    board: EditorialSnapshotPart<{ years: Array<{ year: number; total: number; sessions: number; last: string | null; decisions: ContractFacet[] }> }>;
    editors: EditorialSnapshotPart<EditorsOverview>;
    roles: EditorialSnapshotPart<{ items: RoleFacet[] }>;
    expiring: EditorialSnapshotPart<ContractPage>;
  };
  works: { items: Work[]; user: string };
  refreshIntervalSeconds: number;
  loading: boolean;
  stale: boolean;
  revision: string;
};
export type EditorialSnapshotPart<T> = { data?: T; updatedAt?: number; error?: string | null };
export const editorialHomeApi = {
  get: () => send<EditorialHomeSnapshot>('GET', '/api/v1/editorial/home', undefined, 30_000),
};

// ---------------------------------------------------------------- Kitap Tasarım Stüdyosu
/** Basıma hazırlık işi: GPU'daki stüdyo servisi yürütür, köprü oturumla aracılık eder. Düzenleyen kişi
 *  oturumdan gelir; istemci ad göndermez. */
export type StudioStepStatus = 'waiting' | 'running' | 'done' | 'warn' | 'fail' | 'skipped';
export type StudioStep = {
  key: string;
  label: string;
  status: StudioStepStatus;
  seconds: number | null;
  summary: string;
  progress?: [number, number];
  reasons?: string[];
  names?: string[];
  palette?: string[];
};
export type StudioArtVersion = { v: number; mode: string; prompt: string; by: string; at: number; dpi: number; base: number | null };
export type StudioArt = { selected: number | null; approved: boolean; approved_by: string | null; versions: StudioArtVersion[] } | null;
export type StudioPage = {
  no: number;
  kind: 'front' | 'flow' | 'full';
  key: string | null;
  chapter: number | null;
  excerpt: string;
  art: StudioArt;
  scene: { moment: string; quote: string; characters: string[]; grounded: boolean } | null;
};
export type StudioCheck = { name: string; status: 'OK' | 'WARN' | 'FAIL'; detail: string };
export type StudioBusy = { key: string; mode: string; since: number; queued?: boolean; error?: string } | null;
/** Başlangıçta resim seçimi: otomatik (önerilen) | her sayfa | yalnız bölüm başları | resimsiz. */
export type StudioArtMode = 'auto' | 'every_page' | 'chapter' | 'none';
export type StudioJob = {
  job: { id: string; source: { generation_id?: string; book_id?: string; docx?: string; file_name?: string }; created_by: string; created_at: number;
         art_mode?: StudioArtMode };
  state: { title: string; status: 'running' | 'done' | 'fail'; error: string | null; started: number; finished: number | null; steps: StudioStep[] };
  busy: StudioBusy;
  book: { title: string; author: string | null; meta: Record<string, string | number | null>; chapters: (string | null)[]; words: number } | null;
  profile: { age_min: number; age_max: number; age_source: string; genre: string; illustration: string; illustration_source?: string | null; tone: string[];
             reading: Record<string, number>; disagreement: string | null; reasons: { claim: string; quote: string }[];
             /** Resim kararının kaynağı (editör seçimi ya da otomatik) ve gerekçesi. */
             art_source?: 'editor' | 'auto'; art_reason?: string | null } | null;
  spec: { trim_w: number; trim_h: number; bleed: number; body_font: string; body_size: number; leading: number; paper: string;
          hyphenate: boolean; reasons: string[] } | null;
  layout: { art_ratio: number; body_size: number; accent: string } | null;
  style: { medium: string; palette: string[]; accent: string; why: string } | null;
  characters: { i: number; name: string; species: string; look: string; from_text: string[]; role: string; has_ref: boolean }[];
  pages: StudioPage[];
  cover: { art: StudioArt; info: { size_mm: [number, number]; binding: string; spine_mm: number } | null };
  preflight: { status: 'OK' | 'WARN' | 'FAIL'; checks: StudioCheck[] } | null;
  front: { rows: StudioKunyeRow[]; bios: { name: string; text: string }[] } | null;
  files: { ic: boolean; kapak: boolean; 'baski-ic': boolean; 'baski-kapak': boolean };
  /** Dizginin son yenilenme zamanı (sn); eski servis göndermez. */
  built?: number;
};
/** Künye satırı. `field` varsa satır kitap adı / yazardır: kaydı künye alanı değil el yazmasının kendisini düzeltir
 *  (kapak, iç kapak, künye, dizgi yeniden kurulur). `edited`: editörün düzeltmesi (kim, ne zaman, eski değer).
 *  `none`: yazarsız kitap (künyede basılmıyor, panelde düzenlenir). Eski servis `field`/`edited` göndermez. */
export type StudioKunyeRow = {
  label: string; value: string; missing: boolean; editable: boolean; source: string | null;
  field?: 'title' | 'author'; edited?: { by: string | null; at: number | null; was: string | null } | null; none?: boolean;
};
export type StudioBookEdit = { title?: string; author?: string };
export type StudioKunyeResult = {
  kunye: [string, string][]; book?: { title: string; author: string | null }; changed?: string[];
  crm?: { match: string; filled: string[]; linked?: boolean } | null;
};
export type StudioJobRow = { id: string; title: string | null; created_by: string; created_at: number;
  source: StudioJob['job']['source']; steps: { key: string; label: string; status: StudioStepStatus }[]; busy: StudioBusy };

const studioBase = (job: string) => `/api/v1/editorial/studio/jobs/${encodeURIComponent(job)}`;
export const studioApi = {
  list: () => send<{ jobs: StudioJobRow[] }>('GET', '/api/v1/editorial/studio/jobs', undefined, 30_000),
  create: (bookId: string, artMode: StudioArtMode = 'auto') =>
    send<{ id: string }>('POST', '/api/v1/editorial/studio/jobs', { book_id: bookId, art_mode: artMode }, 60_000),
  /** Word dosyası ham gövdeyle gider; ad başlıkta (URL kodlu). */
  upload: async (file: File, artMode: StudioArtMode = 'auto'): Promise<{ id: string }> => {
    const res = await fetch(`${ENGINE_BASE}/api/v1/editorial/studio/jobs/docx?art_mode=${artMode}`, {
      method: 'POST', credentials: 'include', body: file,
      headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                 'X-File-Name': encodeURIComponent(file.name) },
      signal: AbortSignal.timeout(180_000),
    });
    if (res.status === 401 || res.status === 403) throw new EngineAuthError();
    if (!res.ok) {
      const j = (await res.json().catch(() => null)) as { detail?: string } | null;
      throw new Error(typeof j?.detail === 'string' ? j.detail : `Yükleme başarısız (${res.status})`);
    }
    return (await res.json()) as { id: string };
  },
  get: (job: string) => send<StudioJob>('GET', studioBase(job), undefined, 30_000),
  restart: (job: string) => send<{ id: string }>('POST', `${studioBase(job)}/restart`, {}, 60_000),
  resume: (job: string) => send<{ id: string }>('POST', `${studioBase(job)}/resume`, {}, 60_000),
  /** Resim seçimini sonradan değiştirir: yerleşim yeniden kurulur, resimler silinmez. */
  setArtMode: (job: string, artMode: StudioArtMode) =>
    send<{ id?: string; ok?: boolean }>('POST', `${studioBase(job)}/art-mode`, { art_mode: artMode }, 120_000),
  /** Künye alanları ve kitap adı/yazar düzeltmesi; servis kapağı ve sayfaları yeniden dizince döner. */
  kunye: (job: string, fields: Record<string, string>, book?: StudioBookEdit) =>
    send<StudioKunyeResult>('POST', `${studioBase(job)}/kunye`,
      book && Object.keys(book).length ? { fields, book } : { fields }, 300_000),
  regenerate: (job: string, key: string, mode: 'fix' | 'new', prompt: string, variants = 1) =>
    send<{ accepted: boolean }>('POST', `${studioBase(job)}/art/${encodeURIComponent(key)}/regenerate`, { mode, prompt, variants }, 60_000),
  select: (job: string, key: string, v: number) =>
    send<{ ok: boolean }>('POST', `${studioBase(job)}/art/${encodeURIComponent(key)}/select`, { v }, 120_000),
  approve: (job: string, key: string, ok: boolean) =>
    send<{ ok: boolean }>('POST', `${studioBase(job)}/art/${encodeURIComponent(key)}/approve`, { ok }, 120_000),
  pageUrl: (job: string, page: number, width = 600, rev = '') => `${ENGINE_BASE}${studioBase(job)}/pages/${page}/preview?w=${width}${rev ? `&r=${rev}` : ''}`,
  coverUrl: (job: string, width = 1400, rev = '') => `${ENGINE_BASE}${studioBase(job)}/cover/preview?w=${width}${rev ? `&r=${rev}` : ''}`,
  artUrl: (job: string, key: string, v: number, width = 800) => `${ENGINE_BASE}${studioBase(job)}/art/${encodeURIComponent(key)}/${v}?w=${width}`,
  characterUrl: (job: string, i: number, width = 160) => `${ENGINE_BASE}${studioBase(job)}/characters/${i}?w=${width}`,
  pdfUrl: (job: string, kind: 'ic' | 'kapak' | 'baski-ic' | 'baski-kapak') => `${ENGINE_BASE}${studioBase(job)}/pdf/${kind}`,
};

// ------------------------------------------------ Stüdyo sayfa planı (docs/analiz/studyo-sayfa-plani-sozlesme.md)
/** Ölçüler mm; köken taşma paylı sayfanın sol üstü. */
export type PlanBox = { x: number; y: number; w: number; h: number };
export type PlanRun = { text: string; color?: string | null; weight?: number | null; size?: number | null;
  font?: 'body' | 'heading' | null; source?: 'auto' | 'editor' | null };
export type PlanBlock = { id: string; kind: 'para' | 'sound' | 'heading' | string; runs: PlanRun[] };
export type PlanLayout = 'art-top' | 'art-bottom' | 'art-full' | 'art-left' | 'art-right' | 'text-over-art' | 'text-only' | 'blank' | 'custom';
export type PlanBubbleShape = 'oval' | 'thought' | 'shout' | 'box';
export type PlanBubble = { id: string; speaker: string | null; text: string; shape: PlanBubbleShape; box: PlanBox;
  tail: { x: number; y: number } | null; color: string | null; source: 'auto' | 'editor' | string };
export type PlanFigure = { id: string; asset: string; box: PlanBox; rotate: number; flip: boolean; z: number };
/** Efekt yazı (sözleşme «Efekt yazılar ve süs/şekiller»); çizimi dizgide, panel E hattında. */
/** Şekil ve efekt yazının tek tip kaynağı burasıdır; `studio/elements/types.ts` bunları yeniden adlandırarak verir.
 *  Renk alanı "#RRGGBB(AA)", palet rolü (`PlanColorRole`, dizgi kitabın paletinden çözer) ya da "none" (boya yok). */
export type PlanColorRole = 'accent' | 'accent2' | 'ink' | 'pop' | 'pop2' | 'sun' | 'rose' | 'soft' | 'soft2' | 'paper'
  | 'wood' | 'bark' | 'deep' | 'white';
export type PlanEffectStyle = 'burst' | 'wave' | 'arc' | 'shadow' | 'outline' | 'stacked' | 'bounce' | 'rainbow';
/** Stilin kullanmadığı alan etkisizdir; dış çizgi ve gölge her stilde çalışır. null renk = yok. */
export type PlanEffectParams = {
  /** arc/wave: -1..1 kavis */ curve?: number; /** wave: dalga sayısı */ waves?: number;
  outline?: string | null; /** mm */ outline_w?: number; shadow?: string | null; /** mm */ shadow_dx?: number; /** mm */ shadow_dy?: number;
  /** stacked: derinlik (harf boyuna oran) */ depth?: number;
  /** rainbow/bounce: harf harf dönen renkler; boş → kitabın paletinden */ colors?: string[] | null;
  burst_fill?: string | null; burst_stroke?: string | null; /** derece */ angle?: number;
  /** burst: uç sayısı ve tohum (aynı tohum → aynı çizim) */ spikes?: number; seed?: number;
  [k: string]: unknown;
};
export type PlanEffect = { style: PlanEffectStyle; params: PlanEffectParams };
/** `size` null → yazı kutuya sığacak kadar büyür/küçülür; sayı verilirse sabittir, sığmazsa dizgi `overflow` yazar. */
export type PlanFreeText = { id: string; box: PlanBox; align: 'left' | 'justify' | 'center' | 'right'; size: number | null;
  background: string | null; runs: PlanRun[]; z: number; effect?: PlanEffect | null; overflow?: boolean };
/** Süs/şekil katmanı (çerçeve, tabela, not kâğıdı, yıldız …); z kuralı figürlerle aynı (≥ 3). Boş renk → türün
 *  varsayılan rolü; `text_size` null → yazı şekle sığdırılır; `flip` şekli aynalar, yazıyı aynalamaz. */
export type PlanShapeKind = 'frame' | 'corner' | 'scatter' | 'arrow' | 'sign' | 'note' | 'envelope' | 'scroll' | 'badge'
  | 'ribbon' | 'star' | 'heart' | 'cloud' | 'burst' | 'line';
export type PlanShape = { id: string; kind: PlanShapeKind | (string & {}); box: PlanBox; rotate: number; flip: boolean; z: number;
  fill?: string | null; stroke?: string | null; stroke_w?: number | null; opacity?: number | null;
  params?: Record<string, unknown>; runs?: PlanRun[]; text_size?: number | null;
  /** Salt okunur (dizgi yazar): sabit puntolu yazı şekle sığmadı. */
  overflow?: boolean };
/** `id`: çizilen resim (a_…); `asset`: sayfa resmi yapılan yüklenmiş fotoğraf (g_…). İkisinden biri dolu olur. */
export type PlanArt = { id: string | null; asset?: string | null; box: PlanBox; fit: 'cover' | 'contain'; focus: { x: number; y: number };
  /** Salt okunur: çizilen resmin seçili sürümü (tarayıcı taslağında resmi göstermek için; sözleşmeye önerildi). */
  selected?: number | null };
export type PlanText = { box: PlanBox; align: 'left' | 'justify' | 'center'; size: number | null; background: string | null; blocks: PlanBlock[] };
export type PlanPage = { id: string; chapter: number | null; layout: PlanLayout; art: PlanArt | null; text: PlanText | null;
  bubbles: PlanBubble[]; figures: PlanFigure[]; texts: PlanFreeText[];
  /** Eski planlarda yok; ekran boş liste sayar. */
  shapes?: PlanShape[]; overflow: boolean };
export type PlanColor = { name: string; hex: string; source: 'resim' | 'timas' | 'editor' | string };
/** `accent` isteğe bağlı (B teslim notu): verilirse vurgu rolü odur. */
export type PlanPalette = { colors: PlanColor[]; text: string; characters: Record<string, string>; accent?: string | null };
export type PlanAsset = { kind: 'figure' | 'photo' | string; prompt?: string; name?: string; path: string; w_px: number; h_px: number;
  alpha: boolean; by: string; at: string; characters?: string[];
  /** Arka planı kaldırılmış ya da kalitesi artırılmış kopyanın özgünü. */
  derived_from?: string | null; upscale?: number | null; cutout?: boolean;
  /** Sunucunun sonuç notu (ör. «yalnız büyütüldü, keskinleştirilemedi»). */
  note?: string | null };
export type Plan = {
  version: number; rev: number; frozen_at: string; frozen_by: string;
  page: { w: number; h: number; bleed: number; safe: number; gutter: number };
  palette: PlanPalette; pages: PlanPage[]; assets: Record<string, PlanAsset>; warnings: string[];
};
export type PlanHistoryItem = { rev: number; at: string; by: string; what: string };
/** `plan/jobs` satırı. Sözleşme alan adlarını sabitlemiyor; ekran bilinmeyen alanı yok sayar. */
export type PlanJob = { workflow?: string; id?: string; kind?: string; status?: string; page?: string | null; prompt?: string;
  error?: string | null; progress?: [number, number] | number | null; asset?: string | null; since?: number | string;
  item?: string | null; source?: string | null; note?: string | null };
export type PhotoUpload = { asset: string; w_px: number; h_px: number; dpi_hint?: number | null };

/** Plan uçlarının hatası: durum kodu ve gövdedeki `code` (STALE, NO_PLAN …) kaybolmaz. */
export class StudioPlanError extends Error {
  constructor(public status: number, public code: string | null, message: string, public body: unknown) {
    super(message);
    this.name = 'StudioPlanError';
  }
}

async function planSend<T>(method: string, path: string, body?: unknown, timeoutMs = 180_000): Promise<T> {
  const res = await fetch(`${ENGINE_BASE}${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (res.status === 401 || res.status === 403) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as Record<string, unknown> | null;
    // Servis `{"code": …}` ya da FastAPI kalıbıyla `{"detail": {"code": …}}` / `{"detail": "…"}` dönebilir.
    const detail = j?.detail as Record<string, unknown> | string | undefined;
    const inner = (typeof detail === 'object' && detail) ? detail : j ?? {};
    const code = typeof inner.code === 'string' ? inner.code : null;
    const msg = typeof detail === 'string' ? detail
      : typeof inner.message === 'string' ? inner.message
      : typeof inner.detail === 'string' ? inner.detail : httpErrorText(res.status);
    throw new StudioPlanError(res.status, code, msg, j);
  }
  return (await res.json()) as T;
}

const planBase = (job: string) => `${studioBase(job)}/plan`;
const pid = (id: string) => encodeURIComponent(id);
export const studioPlanApi = {
  get: (job: string) => planSend<Plan>('GET', planBase(job), undefined, 30_000),
  freeze: (job: string) => planSend<Plan>('POST', `${planBase(job)}/freeze`, {}, 300_000),
  /** Sayfa düzeni ekranının açılışı: plan yoksa sunucu kendiliğinden kurar. Hazırsa `{status: 'ready'}`; kurulurken
   *  409 PREPARING (`body.state`: preparing | waiting), düştüyse 409 PLAN_FAILED (`retry` ile yeniden), kitap
   *  yerleşmediyse 404 NO_PLAN — hepsi `StudioPlanError`. */
  prepare: (job: string, retry = false) =>
    planSend<{ status: 'ready' }>('POST', `${planBase(job)}/prepare${retry ? '?retry=1' : ''}`, {}, 60_000),
  putPage: (job: string, rev: number, page: PlanPage) =>
    planSend<{ page: PlanPage; rev: number; warnings?: string[] }>('PUT', `${planBase(job)}/pages/${pid(page.id)}`, { rev, page }, 180_000),
  addPage: (job: string, rev: number, after: string | null, layout: PlanLayout) =>
    planSend<Partial<Plan> & { page?: PlanPage; rev: number }>('POST', `${planBase(job)}/pages`, { rev, after, layout }, 180_000),
  deletePage: (job: string, rev: number, id: string) =>
    planSend<{ ok: boolean; rev: number; warnings?: string[] }>('DELETE', `${planBase(job)}/pages/${pid(id)}?rev=${rev}`, undefined, 180_000),
  order: (job: string, rev: number, ids: string[]) => planSend<Plan>('POST', `${planBase(job)}/order`, { rev, ids }, 180_000),
  split: (job: string, rev: number, id: string, block: string, at: number) =>
    planSend<Partial<Plan> & { rev: number }>('POST', `${planBase(job)}/pages/${pid(id)}/split`, { rev, block, at }, 180_000),
  palette: (job: string, rev: number, palette: PlanPalette) => planSend<Plan>('PUT', `${planBase(job)}/palette`, { rev, palette }, 180_000),
  suggestBubbles: (job: string, id: string) =>
    planSend<{ bubbles: PlanBubble[] } | PlanBubble[]>('POST', `${planBase(job)}/pages/${pid(id)}/bubbles/suggest`, {}, 180_000),
  unusedArt: (job: string) => planSend<{ ids?: string[]; art?: string[] } | string[]>('GET', `${planBase(job)}/unused-art`, undefined, 30_000),
  figure: (job: string, prompt: string, characters: string[], page: string | null) =>
    planSend<{ workflow: string }>('POST', `${planBase(job)}/figures`, { prompt, characters, page }, 60_000),
  deleteAsset: (job: string, rev: number, gid: string) =>
    planSend<{ ok: boolean; rev: number }>('DELETE', `${planBase(job)}/assets/${pid(gid)}?rev=${rev}`, undefined, 60_000),
  history: (job: string) => planSend<PlanHistoryItem[] | { history: PlanHistoryItem[] }>('GET', `${planBase(job)}/history`, undefined, 30_000),
  restore: (job: string, rev: number) => planSend<Plan>('POST', `${planBase(job)}/restore`, { rev }, 300_000),
  jobs: (job: string) => planSend<PlanJob[] | { jobs: PlanJob[] }>('GET', `${planBase(job)}/jobs`, undefined, 30_000),
  cutout: (job: string, gid: string) => planSend<{ workflow: string }>('POST', `${planBase(job)}/assets/${pid(gid)}/cutout`, {}, 60_000),
  upscale: (job: string, gid: string, page: string | null, item: string | null) =>
    planSend<{ workflow: string }>('POST', `${planBase(job)}/assets/${pid(gid)}/upscale`, { page, item }, 60_000),
  /** Stüdyo ayarları (yönetim ekranı): fotoğraf başına en büyük boyut. */
  settings: () => planSend<{ upload_mb: number }>('GET', '/api/v1/editorial/studio/settings', undefined, 30_000),
  /** Ham gövdeyle fotoğraf yükleme; ilerleme için XHR (fetch yükleme ilerlemesi vermez). */
  uploadPhoto: (job: string, file: Blob, filename: string, page: string | null, onProgress: (sent: number, total: number) => void,
    signal?: AbortSignal) => new Promise<PhotoUpload>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const q = `filename=${encodeURIComponent(filename)}${page ? `&page=${pid(page)}` : ''}`;
    xhr.open('PUT', `${ENGINE_BASE}${planBase(job)}/photos?${q}`);
    xhr.withCredentials = true;
    xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
    xhr.upload.onprogress = (e) => onProgress(e.loaded, e.lengthComputable ? e.total : file.size);
    xhr.onload = () => {
      if (xhr.status === 401 || xhr.status === 403) { authBlocked = true; reject(new EngineAuthError()); return; }
      let j: Record<string, unknown> | null = null;
      try { j = JSON.parse(xhr.responseText) as Record<string, unknown>; } catch { /* gövdesiz */ }
      if (xhr.status >= 200 && xhr.status < 300 && j) { resolve(j as unknown as PhotoUpload); return; }
      const detail = j?.detail as Record<string, unknown> | string | undefined;
      const inner = (typeof detail === 'object' && detail) ? detail : j ?? {};
      const msg = typeof detail === 'string' ? detail : typeof inner.message === 'string' ? inner.message : `Yükleme kabul edilmedi (${xhr.status})`;
      reject(new StudioPlanError(xhr.status, typeof inner.code === 'string' ? inner.code : null, msg, j));
    };
    xhr.onerror = () => reject(new TypeError('ağ'));
    xhr.ontimeout = () => reject(new TypeError('zaman aşımı'));
    xhr.onabort = () => reject(new DOMException('iptal', 'AbortError'));
    xhr.timeout = 15 * 60_000;
    signal?.addEventListener('abort', () => xhr.abort());
    xhr.send(file);
  }),
  /** `v` önbellek anahtarıdır: sayfanın sunucudaki hâli değişince değişir. */
  previewUrl: (job: string, id: string, width: number, v: string) => `${ENGINE_BASE}${planBase(job)}/pages/${pid(id)}/preview?w=${width}&v=${v}`,
  assetUrl: (job: string, gid: string, width = 400) => `${ENGINE_BASE}${planBase(job)}/assets/${pid(gid)}?w=${width}`,
};

// ------------------------------------------------------ serbest çalışanlar (M8)

export type FlRole = { key: string; label: string; unit: string; hoursPerUnit: number };
export type FlRate = { role: string; unit: string; price: number };
export type FlAway = { from: string; to: string; note?: string | null };
export type FlStats = { active: number; waiting: number; done: number; late: number; onTimeRate: number | null; avgRevisions: number | null; payable: number };
export type FlPerson = {
  id: string;
  name: string;
  roles: string[];
  email: string | null;
  phone: string | null;
  city: string | null;
  website: string | null;
  crmContactId: string | null;
  logoCard: string | null;
  styles: string[];
  note: string | null;
  weeklyHours: number;
  rates: FlRate[];
  away: FlAway[];
  status: 'aktif' | 'pasif';
  createdBy: string;
  createdAt: string;
  updatedBy: string | null;
  updatedAt: string | null;
  stats: FlStats;
  preview?: string[];
};
export type FlPortfolioItem = { id: string; title: string | null; tags: string[]; book: string | null; filename: string; mime: string; bytes: number; uploadedBy: string; uploadedAt: string };
export type FlTaskStatus = 'atanmadi' | 'atandi' | 'calisiyor' | 'teslim' | 'revizyon' | 'onaylandi' | 'iptal';
export type FlDelivery = {
  id: string;
  taskId: string;
  version: number;
  note: string | null;
  link: string | null;
  filename: string | null;
  bytes: number | null;
  uploadedBy: string;
  uploadedAt: string;
  decision: 'bekliyor' | 'kabul' | 'revizyon';
  decisionNote: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
};
export type FlTask = {
  id: string;
  packageId: string;
  personId: string | null;
  personName?: string | null;
  personEmail?: string | null;
  title: string;
  role: string;
  units: number;
  unit: string;
  unitPrice: number;
  amount: number;
  effortHours: number;
  start: string | null;
  due: string | null;
  status: FlTaskStatus;
  revisions: number;
  assignedAt: string | null;
  firstDeliveredAt: string | null;
  acceptedAt: string | null;
  payoutId: string | null;
  late: boolean;
  packageTitle?: string;
  bookTitle?: string | null;
  deliveries?: FlDelivery[];
};
export type FlPayoutHead = {
  id: string;
  no: number;
  personId: string;
  personName: string | null;
  status: 'taslak' | 'onay' | 'onaylandi' | 'odendi' | 'silindi';
  total: number;
  note: string | null;
  returnNote: string | null;
  createdBy: string;
  createdAt: string;
  submittedBy: string | null;
  submittedAt: string | null;
  approvedBy: string | null;
  approvedAt: string | null;
  paidOn: string | null;
  paidRef: string | null;
  paidBy: string | null;
};
export type FlPersonDetail = FlPerson & { portfolio: FlPortfolioItem[]; tasks: FlTask[]; payouts: FlPayoutHead[]; kaynaklar?: Kaynaklar };
export type FlPackageRow = {
  id: string;
  title: string;
  bookTitle: string | null;
  role: string;
  due: string | null;
  status: 'acik' | 'kapandi' | 'iptal';
  owner: string;
  createdAt: string;
  tasks: number;
  counts: Record<FlTaskStatus, number>;
  people: string[];
  amount: number;
  late: number;
  unread: number;
};
export type FlPackage = {
  id: string;
  title: string;
  bookTitle: string | null;
  bookId: string | null;
  role: string;
  brief: string | null;
  due: string | null;
  status: 'acik' | 'kapandi' | 'iptal';
  owner: string;
  createdBy: string;
  createdAt: string;
  tasks: FlTask[];
  kaynaklar?: Kaynaklar;
};
export type FlTaskInput = { title: string; units: number | string; unit?: string; unitPrice?: number | string; effortHours?: number | string; start?: string; due?: string; role?: string };
export type FlCapacityCell = { week: string; capacity: number; load: number; ratio: number | null; away: boolean };
export type FlCapacity = {
  weeks: string[];
  today: string;
  unassigned: { tasks: number; hours: number };
  people: Array<{
    id: string;
    name: string;
    roles: string[];
    weeklyHours: number;
    weeks: FlCapacityCell[];
    active: number;
    late: number;
    tasks: Array<{ id: string; title: string; packageId: string; packageTitle: string; start: string | null; due: string | null; effortHours: number; status: FlTaskStatus; late: boolean }>;
  }>;
  kaynaklar?: Kaynaklar;
};
export type FlSuggestion = {
  taskId: string;
  title?: string;
  role?: string;
  suggested: string | null;
  note: string | null;
  candidates: Array<{ personId: string; name: string; freeHours: number; fits: boolean; onTimeRate: number | null; reason: string }>;
};
export type FlPayable = { personId: string; personName: string; total: number; tasks: FlTask[] };
export type FlPayout = FlPayoutHead & {
  person: { id: string; name: string; logoCard: string | null; email: string | null };
  lines: Array<{ id: string; taskId: string; description: string; units: number; unit: string; unitPrice: number; amount: number }>;
  kaynaklar?: Kaynaklar;
};
export type FlMessageKind = 'ic' | 'giden' | 'gelen' | 'sistem';
export type FlMessage = {
  id: string;
  thread: string;
  taskId: string | null;
  kind: FlMessageKind;
  author: string;
  authorDisplay: string | null;
  mine: boolean;
  body: string;
  emailTo: string | null;
  emailStatus: 'gonderildi' | 'gonderilemedi' | 'ayar-yok' | 'adres-yok' | null;
  createdAt: string;
};
export type FlThread = { thread: string; title: string; kind: 'paket' | 'kisi'; recipients: Array<{ id: string; name: string; email: string | null }>; messages: FlMessage[] };
export type FlInboxItem = { thread: string; kind: 'paket' | 'kisi'; title: string; subtitle: string | null; count: number; unread: number; at: string | null; last: { kind: FlMessageKind; body: string; author: string } | null };
export type FlOverview = {
  people: { active: number; passive: number };
  tasks: { unassigned: number; active: number; late: number; review: number };
  payable: number;
  payouts: Partial<Record<Exclude<FlPayoutHead['status'], 'silindi'>, { count: number; total: number }>>;
  unread: number;
  roles: FlRole[];
  units: string[];
  email: { configured: boolean; sender: string | null };
  me: { username: string; canManage: boolean; canApprove: boolean };
  kaynaklar?: Kaynaklar;
};
export type FlLogoCard = { code: string | null; name: string | null; specode: string | null; city: string | null; freelance: boolean };
export type FlLogoMovements = {
  found: boolean;
  code: string | null;
  name?: string | null;
  specode?: string | null;
  year: number;
  lines: Array<{ day: string | null; type: string; trcode: number; side: 'alacak' | 'borc'; amount: number; no: string | null; doc: string | null; text: string | null }>;
  credit?: number;
  debit?: number;
  balance?: number;
  last?: string | null;
  db?: DbTiming | null;
  kaynaklar?: Kaynaklar;
};

const FL = '/api/v1/editorial/freelance';

/** Ham gövdeyle dosya yükleme; sayfa kapısının 403'ü (yetki) oturum düşmesinden ayrılır. */
const flUpload = async <T,>(path: string, file: File, extra: Record<string, string> = {}): Promise<T> => {
  const res = await fetch(`${ENGINE_BASE}${path}${qs({ filename: file.name, ...extra })}`, {
    method: 'PUT',
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
    signal: AbortSignal.timeout(900_000),
  });
  if (res.status === 401) {
    authBlocked = true;
    throw new EngineAuthError();
  }
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { detail?: { code?: string; message?: string } | string } | null;
    const msg = typeof j?.detail === 'string' ? j.detail : j?.detail?.message;
    if (res.status === 403) throw new EngineForbiddenError(msg || 'Bu işlem rolünüzde yok.');
    throw new Error(msg || httpErrorText(res.status));
  }
  return (await res.json()) as T;
};

export const freelanceApi = {
  overview: () => send<FlOverview>('GET', `${FL}/overview`, undefined, 30_000),
  people: (p: { q?: string; role?: string; status?: string } = {}) =>
    send<{ items: FlPerson[]; total: number; roles: FlRole[]; units: string[]; kaynaklar?: Kaynaklar }>('GET', `${FL}/people${qs(p)}`, undefined, 30_000),
  person: (id: string) => send<FlPersonDetail>('GET', `${FL}/people/${enc(id)}`, undefined, 30_000),
  createPerson: (b: Record<string, unknown>) => send<FlPersonDetail>('POST', `${FL}/people`, b, 30_000),
  updatePerson: (id: string, b: Record<string, unknown>) => send<FlPersonDetail>('PATCH', `${FL}/people/${enc(id)}`, b, 30_000),
  lookup: (crmIds: string[]) => send<{ items: Record<string, string> }>('GET', `${FL}/lookup${qs({ crm: crmIds.join('|') })}`, undefined, 30_000),
  addPortfolio: (personId: string, file: File, meta: { title?: string; tags?: string; book?: string } = {}) =>
    flUpload<FlPortfolioItem>(`${FL}/people/${enc(personId)}/portfolio`, file, Object.fromEntries(Object.entries(meta).filter(([, v]) => v)) as Record<string, string>),
  updatePortfolio: (id: string, b: { title?: string; tags?: string[]; book?: string }) => send<{ ok: boolean }>('PATCH', `${FL}/portfolio/${enc(id)}`, b, 30_000),
  deletePortfolio: (id: string) => send<{ ok: boolean }>('DELETE', `${FL}/portfolio/${enc(id)}`, undefined, 30_000),
  portfolioUrl: (id: string) => `${ENGINE_BASE}${FL}/portfolio/${enc(id)}`,
  packages: (p: { q?: string; status?: string } = {}) => send<{ items: FlPackageRow[]; total: number; kaynaklar?: Kaynaklar }>('GET', `${FL}/packages${qs(p)}`, undefined, 30_000),
  package: (id: string) => send<FlPackage>('GET', `${FL}/packages/${enc(id)}`, undefined, 30_000),
  createPackage: (b: { title: string; role: string; due?: string; bookTitle?: string; bookId?: string; brief?: string; tasks: FlTaskInput[] }) =>
    send<{ id: string; title: string }>('POST', `${FL}/packages`, b, 30_000),
  updatePackage: (id: string, b: Record<string, unknown>) => send<{ ok: boolean }>('PATCH', `${FL}/packages/${enc(id)}`, b, 30_000),
  addTasks: (id: string, tasks: FlTaskInput[]) => send<{ added: number }>('POST', `${FL}/packages/${enc(id)}/tasks`, { tasks }, 30_000),
  updateTask: (id: string, b: Record<string, unknown>) => send<{ ok: boolean }>('PATCH', `${FL}/tasks/${enc(id)}`, b, 30_000),
  deleteTask: (id: string) => send<{ ok: boolean }>('DELETE', `${FL}/tasks/${enc(id)}`, undefined, 30_000),
  assign: (items: Array<{ taskId: string; personId: string | null }>, notify: boolean) =>
    send<{ assigned: number; mail: { gonderildi: number; diger: number } | null }>('POST', `${FL}/assign`, { items, notify }, 120_000),
  suggest: (taskIds: string[]) => send<{ items: FlSuggestion[]; kaynaklar?: Kaynaklar }>('POST', `${FL}/suggest`, { taskIds }, 30_000),
  capacity: (p: { weeks?: number; role?: string; start?: string } = {}) => send<FlCapacity>('GET', `${FL}/capacity${qs(p)}`, undefined, 30_000),
  deliverFile: (taskId: string, file: File, note?: string) =>
    flUpload<{ id: string; version: number }>(`${FL}/tasks/${enc(taskId)}/delivery`, file, note ? { note } : {}),
  deliverLink: (taskId: string, link: string, note?: string) =>
    send<{ id: string; version: number }>('POST', `${FL}/tasks/${enc(taskId)}/delivery-link`, { link, note }, 30_000),
  decide: (deliveryId: string, decision: 'kabul' | 'revizyon', note: string, notify: boolean) =>
    send<{ ok: boolean; mail: FlMessage['emailStatus'] }>('POST', `${FL}/deliveries/${enc(deliveryId)}/decision`, { decision, note, notify }, 60_000),
  deliveryUrl: (id: string) => `${ENGINE_BASE}${FL}/deliveries/${enc(id)}/file`,
  payable: () => send<{ items: FlPayable[]; kaynaklar?: Kaynaklar }>('GET', `${FL}/payable`, undefined, 30_000),
  payouts: (p: { status?: string; person?: string } = {}) =>
    send<{ items: FlPayoutHead[]; totals: Record<Exclude<FlPayoutHead['status'], 'silindi'>, number>; kaynaklar?: Kaynaklar }>('GET', `${FL}/payouts${qs(p)}`, undefined, 30_000),
  payout: (id: string) => send<FlPayout>('GET', `${FL}/payouts/${enc(id)}`, undefined, 30_000),
  createPayout: (b: { personId: string; taskIds?: string[]; note?: string }) =>
    send<{ id: string; no: number; total: number; personName: string }>('POST', `${FL}/payouts`, b, 30_000),
  payoutAction: (id: string, action: 'submit' | 'return' | 'approve' | 'pay' | 'delete', b: { note?: string; paidOn?: string; paidRef?: string } = {}) =>
    send<{ id: string; no: number; action: string }>('POST', `${FL}/payouts/${enc(id)}/${action}`, b, 30_000),
  payoutCsvUrl: (id: string) => `${ENGINE_BASE}${FL}/payouts/${enc(id)}/export.csv`,
  inbox: () => send<{ items: FlInboxItem[]; unread: number; kaynaklar?: Kaynaklar }>('GET', `${FL}/inbox`, undefined, 30_000),
  thread: (id: string) => send<FlThread>('GET', `${FL}/threads/${enc(id)}`, undefined, 30_000),
  post: (id: string, b: { kind: 'ic' | 'giden' | 'gelen'; body: string; personId?: string; taskId?: string }) =>
    send<{ id: string; emailStatus: FlMessage['emailStatus'] }>('POST', `${FL}/threads/${enc(id)}/messages`, b, 60_000),
  logoCards: (q: string) => send<{ items: FlLogoCard[]; year: number; db?: DbTiming | null; truncated?: boolean }>('GET', `${FL}/logo/cards${qs({ q })}`, undefined, 60_000),
  logo: (personId: string) => send<FlLogoMovements>('GET', `${FL}/people/${enc(personId)}/logo`, undefined, 60_000),
};

// ------------------------------------------------------------------ kapak arşivi (stüdyo)
export type LibraryAudience = 'CHILD' | 'YOUNG' | 'ADULT';
export type LibraryCategory = { name: string; path: string; count: number; children: LibraryCategory[] };
export type LibraryTree = {
  categories: LibraryCategory[];
  uncategorized: number;
  total: number;
  audiences: Record<LibraryAudience, number>;
};
export type LibraryCover = {
  id: string; title: string; authors: string[]; illustrators: string[]; isbn: string | null; brand: string | null;
  category: string[]; audience: LibraryAudience | null; ageFrom: number | null; ageTo: number | null; genres: string[];
  onSale: boolean; pageUrl: string | null; w: number | null; h: number | null;
};
export type LibraryPage = { total: number; page: number; size: number; pages: number; items: LibraryCover[] };
export type LibraryStats = {
  total: number; ok: number; pending: number; failed: number; none: number; lastFeed: string | null;
  fetch: { running: boolean; done: number; failed: number };
  feed: { running: boolean; sent: number; error: string | null; result: Record<string, number | string> | null };
};
/** `cat`: null = bütün kapaklar, '' = kategorisiz, «Kök > Alt» = o kategori ve altı. */
export type LibraryQuery = { cat: string | null; q: string; audience: LibraryAudience | null; sort: 'sales' | 'title'; page: number; size: number };

const libraryBase = '/api/v1/editorial/studio/library';
export const coverLibraryApi = {
  stats: () => send<LibraryStats>('GET', libraryBase, undefined, 30_000),
  categories: (audience: LibraryAudience | null) =>
    send<LibraryTree>('GET', `${libraryBase}/categories${audience ? `?audience=${audience}` : ''}`, undefined, 30_000),
  covers: (x: LibraryQuery) => {
    const p = new URLSearchParams({ sort: x.sort, page: String(x.page), size: String(x.size) });
    if (x.cat !== null) p.set('cat', x.cat);
    if (x.q.trim()) p.set('q', x.q.trim());
    if (x.audience) p.set('audience', x.audience);
    return send<LibraryPage>('GET', `${libraryBase}/covers?${p}`, undefined, 30_000);
  },
  /** Beslemeyi elle başlatır (yalnız yönetici); görseller arka planda iner. */
  refresh: () => send<{ started: boolean }>('POST', `${libraryBase}/refresh`, {}, 30_000),
  imageUrl: (id: string, width = 360) => `${ENGINE_BASE}${libraryBase}/covers/${encodeURIComponent(id)}/image?w=${width}`,
};
