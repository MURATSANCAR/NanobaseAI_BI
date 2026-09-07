export type BiWidgetData = {
  columns: string[];
  rows: Array<Record<string, unknown>>;
  row_count?: number;
};

export type BiWidgetType =
  | 'card'
  | 'metric'
  | 'kpi'
  | 'gauge'
  | 'multi_card'
  | 'period_compare'
  | 'bar'
  | 'column'
  | 'stacked_bar'
  | 'stacked_column'
  | 'line'
  | 'area'
  | 'combo'
  | 'pie'
  | 'donut'
  | 'table'
  | 'matrix'
  | 'scatter'
  | 'bubble'
  | 'waterfall'
  | 'funnel'
  | 'treemap'
  | string;

export type BiWidget = {
  id: string;
  type: BiWidgetType;
  title: string;
  /** Template id used for seed / i18n title lookup. */
  template_id?: string;
  /** Localized titles keyed by locale (en/tr/ru/uz). */
  titles?: Partial<Record<'en' | 'tr' | 'ru' | 'uz', string>>;
  description?: string;
  x_key?: string;
  y_key?: string;
  y2_key?: string;
  value_key?: string;
  label_key?: string;
  series_key?: string;
  row_key?: string;
  col_key?: string;
  trend_key?: string;
  format?: 'number' | 'percent' | 'currency';
  max_value?: number;
  sql?: string;
  drill_sql?: string;
  target_value?: number;
  refreshed_at?: string;
  data?: BiWidgetData & { delta_pct?: number | null };
  current_label?: string;
  prior_label?: string;
};

export type BiBrandingSettings = {
  brand_name: string;
  logo_url: string;
  primary_color: string;
  accent_color: string;
  footer_text: string;
  allowed_tables?: string[];
};

export type BiAuditEntry = {
  at: string;
  action: string;
  sql?: string;
  session_id?: string;
  duration_ms?: number;
  row_count?: number;
  ok: boolean;
  error?: string;
  source?: string;
};

export type BiForecastBlockData = {
  metric: string;
  unit?: string | null;
  frequency: string;
  engine?: string;
  history: Array<{ period: string; value: number }>;
  forecast: Array<{ period: string; p10: number; p50: number; p90: number }>;
};

export type BiAnswerBlock = {
  type: 'text' | 'metric' | 'table' | 'list' | 'highlight' | 'decision' | 'forecast' | string;
  title?: string;
  content?: string;
  metrics?: Array<{ label: string; value: string; tone?: 'positive' | 'negative' | 'neutral' }>;
  columns?: string[];
  rows?: unknown[][];
  items?: string[];
  /** Forecast block: history + p10/p50/p90 series (rendered as a chart with a band). */
  forecast?: BiForecastBlockData;
};

export type BiChatResponse = {
  session_id: string;
  reply: string;
  intent: string;
  /** Final executed (or attempted) SQL — always present for query intents after honesty fixes. */
  sql?: string | null;
  sql_error?: string | null;
  widgets: BiWidget[];
  answer_blocks: BiAnswerBlock[];
  query_result?: BiWidgetData;
  dashboard?: { widgets: BiWidget[]; updated_at?: string };
  schedule?: BiSchedule;
  report?: BiReport;
  saved_query?: BiSavedQuery;
  alert?: BiAlertRule;
  analytics?: BiAnalyticsResult;
  provenance?: {
    type?: string;
    metric?: string;
    grain?: string;
    assumptions?: string[];
    ambiguities?: string[];
    confidence?: number;
    selected_tables?: string[];
    columns?: string[];
    warnings?: string[];
    dialect?: string;
    executed?: boolean;
    execution_mode?: string;
    sql_fingerprint?: string;
    mandatory_filters?: string[];
  };
  workflows?: {
    plan?: {
      dialect?: string;
      tables?: string[];
      columns?: string[];
      assumptions?: string[];
      warnings?: string[];
      ambiguities?: string[];
      confidence?: number;
      sql?: string;
      [key: string]: unknown;
    };
    explain?: unknown;
  };
  execution_mode?: string;
  warnings?: string[];
  action_preview?: {
    status?: string;
    message?: string;
    confirmed?: boolean;
    result?: Record<string, unknown>;
    preview?: {
      action?: string;
      kind?: string;
      payload?: Record<string, unknown>;
      tenant_id?: string;
      idempotency_key?: string;
      requires_confirm?: boolean;
    };
    alert?: BiAlertRule;
    schedule?: BiSchedule;
    report?: BiReport;
    saved_query?: BiSavedQuery;
    analytics?: BiAnalyticsResult;
    [key: string]: unknown;
  };
  needs_clarification?: boolean;
};

export type BiAnalyticsResult = {
  action?: string;
  items?: Array<Record<string, unknown>>;
  count?: number;
  dashboard?: { id: number; title?: string; embed_uuid?: string };
  chart?: { id: number; title?: string; viz_type?: string };
  dataset?: { id: number; table_name?: string };
  dashboard_id?: number;
  embed_uuid?: string;
  guest?: {
    token: string;
    dashboard_id: number;
    embed_uuid: string;
    analytics_url: string;
  };
  error?: string;
};

export type BiStatus = {
  database_configured: boolean;
  connection: { ok: boolean; dialect?: string; message?: string; code?: string };
  schema_cached: boolean;
  schema_ready?: boolean;
  table_count?: number;
  introspected_at?: string;
  warnings?: Array<{ code: string; message: string }>;
  sql_mode?: string;
  engine_mode?: 'superset';
  capabilities?: Record<string, boolean>;
  analytics?: {
    enabled?: boolean;
    url?: string;
    health?: { ok: boolean; message?: string };
  };
};

export type BiChatSession = {
  session_id: string;
  title?: string;
  updated_at?: string;
  message_count?: number;
  preview?: string;
};

export type BiQueryTemplate = {
  id: string;
  title?: string;
  prompt_tr?: string;
  prompt_en?: string;
  prompt_ru?: string;
  prompt_uz?: string;
  sql_hint?: string | null;
  bind_params?: Record<string, unknown> | null;
  scenarioCode?: string | null;
  category?: string;
  widget_type?: string;
  source?: string;
  kind?: string;
  table_name?: string;
  measure?: string | null;
  category_col?: string | null;
};

export type BiSavedQuery = {
  id: string;
  title: string;
  description?: string;
  sql: string;
  tags?: string[];
  last_run_at?: string;
  created_at?: string;
  updated_at?: string;
};

export type BiGlossaryEntry = {
  id: string;
  table: string;
  column?: string;
  business_name: string;
  definition: string;
  synonyms?: string[];
  source?: string;
};

export type BiShareLink = {
  token?: string;
  token_hash?: string;
  resource_type: string;
  resource_id: string;
  expires_at?: string | null;
  view_count?: number;
  password_protected?: boolean;
  created_at?: string;
  view_log?: Array<{ at: string; ip?: string; user_agent?: string }>;
};

/** Visual table/field rule compiled to alert SQL (stored in payload). */
export type BiAlertStructuredRule = {
  table: string;
  schema?: string;
  tableName?: string;
  aggregate: 'count' | 'count_distinct' | 'sum' | 'avg' | 'min' | 'max' | string;
  measureColumn?: string;
  filters: Array<{
    id?: string;
    column: string;
    op: string;
    value?: string;
  }>;
};

export type BiAlertRule = {
  id: string;
  title: string;
  sql: string;
  column: string;
  condition: string;
  threshold: number;
  recipient?: string;
  status: string;
  last_value?: number;
  last_checked_at?: string;
  last_triggered_at?: string;
  created_at?: string;
  updated_at?: string;
  channels?: Array<{ type: string; to?: string; secret_ref?: string; url?: string }>;
  slack_secret_ref?: string;
  teams_secret_ref?: string;
  /** Optional structured builder definition; when present, UI can re-edit without SQL. */
  rule?: BiAlertStructuredRule | null;
};

export type BiBudgetEnvelope = {
  id: string;
  fiscal_year: number;
  cost_center?: string;
  kind: 'opex' | 'capex' | 'other' | string;
  name: string;
  allocated: number;
  currency?: string;
  committed?: number;
  actuals_sql?: string;
  breakdown_sql?: string;
  owner?: string;
  status: 'draft' | 'approved' | 'closed' | string;
  notes?: string;
  actual?: number | null;
  actual_error?: string | null;
  actuals_at?: string | null;
  remaining?: number | null;
  used_pct?: number | null;
  health?: 'ok' | 'watch' | 'over' | null;
  ask_prompt?: string;
  burn_rate_daily?: number | null;
  runway_days?: number | null;
  projected_year_end?: number | null;
  scenario?: string;
  locked?: boolean;
  approved_at?: string | null;
  approved_by?: string | null;
  version?: number;
  match_source?: string;
  match_key?: string | null;
  match_value?: string | null;
  match_confidence?: string | null;
  budget_code?: string;
  created_at?: string;
  updated_at?: string;
};

export type BiBudgetImportResult = {
  created: number;
  updated: number;
  skipped: number;
  periods_updated?: number;
  commitments_upserted?: number;
  errors: Array<{ row: number; code: string; detail?: string; sheet?: string }>;
};

export type BiBudgetSummary = {
  fiscal_year: number;
  suggested_fiscal_year?: number;
  available_fiscal_years?: number[];
  by_kind: Record<string, { allocated: number; actual: number; committed: number; remaining: number; count: number }>;
  by_currency?: Record<string, { allocated: number; actual: number; committed: number; remaining: number; count: number }>;
  totals: {
    allocated: number | null;
    actual: number | null;
    committed: number | null;
    remaining: number | null;
    count: number;
  };
  watch_count: number;
  over_count: number;
  budget_watch_count: number;
  mixed_currency?: boolean;
  reporting_currency?: string | null;
  currencies?: string[];
  fx_missing?: Array<{ id?: string; name?: string; currency?: string }>;
};

export type BiSchemaColumn = {
  name: string;
  type: string;
  /** Pretty type with length/precision, e.g. varchar(50), numeric(18,2). */
  type_display?: string;
  udt_name?: string | null;
  nullable?: boolean;
  max_length?: number | null;
  character_maximum_length?: number | null;
  precision?: number | null;
  numeric_precision?: number | null;
  scale?: number | null;
  numeric_scale?: number | null;
  datetime_precision?: number | null;
};
export type BiSchemaTable = {
  schema?: string;
  name: string;
  full_name: string;
  columns: BiSchemaColumn[];
  primary_key?: string[];
  foreign_keys?: Array<Record<string, unknown>>;
};

export type BiSchema = {
  dialect: string;
  table_count: number;
  tables: BiSchemaTable[];
  introspected_at?: string;
};

export type BiSchemaGraphColumn = BiSchemaColumn;

export type BiSchemaGraphNode = {
  id: string;
  label: string;
  schema: string;
  full_name: string;
  columns: BiSchemaGraphColumn[];
  primary_key: string[];
  fk_columns: string[];
};

export type BiSchemaGraphEdge = {
  id: string;
  from: string;
  to: string;
  source_columns: string[];
  target_columns: string[];
  label?: string;
};

export type BiSchemaGraph = {
  nodes: BiSchemaGraphNode[];
  edges: BiSchemaGraphEdge[];
  stats: { tables: number; relations: number };
};

export type BiReport = {
  id: string;
  title: string;
  description?: string;
  widgets?: BiWidget[];
  sql?: string;
  created_at?: string;
  updated_at?: string;
};

export type BiSchedule = {
  id: string;
  subject: string;
  run_at: string;
  recipient?: string;
  prompt_summary?: string;
  status: string;
  created_at?: string;
  sent_at?: string;
  error?: string;
  recurrence?: 'none' | 'daily' | 'weekly' | string;
  local_time?: string;
  timezone?: string;
  include_alerts?: boolean;
  include_narrative?: boolean;
  kind?: string;
};

export type BiConnectionProfile = {
  configured: boolean;
  id?: string;
  active_id?: string | null;
  label: string;
  deployment: 'local' | 'cloud' | 'onprem';
  driver: 'postgresql' | 'mysql' | 'oracle' | 'sqlite' | 'supabase' | 'hana' | 'odata';
  host: string;
  port: number;
  database: string;
  username: string;
  password_configured: boolean;
  password_masked: string;
  ssl: boolean;
  sqlite_path: string;
  supabase_url: string;
  supabase_api_key_configured: boolean;
  supabase_api_key_masked: string;
  connection_url_configured?: boolean;
  last_test_at?: string | null;
  last_test_ok?: boolean | null;
  last_test_message?: string | null;
  active?: boolean;
  /** Gateway/secrets-map managed — not user-deletable */
  managed?: boolean;
  protected?: boolean;
};

export type BiSourcesList = {
  active_id: string | null;
  sources: BiConnectionProfile[];
  updated_at?: string;
};

export type BiConnectionUpsert = {
  label?: string;
  deployment?: 'local' | 'cloud' | 'onprem';
  driver?: 'postgresql' | 'mysql' | 'oracle' | 'sqlite' | 'supabase' | 'hana' | 'odata';
  host?: string;
  port?: number;
  database?: string;
  username?: string;
  password?: string;
  ssl?: boolean;
  sqlite_path?: string;
  supabase_url?: string;
  supabase_api_key?: string;
  connection_url?: string;
};


// ---------------------------------------------------------------- Semantic Layer V1 (portal layer)
export type BiSlConceptRef = {
  id: string;
  term: string;
  type: string;
  status: string;
  operator?: string;
  values?: string[];
  formula?: string;
  confidence?: number;
};
export type BiSlAnnotation = { id: string; text: string; author: string; createdAt: string };
export type BiSlColumn = {
  name: string;
  type: string;
  nullable?: boolean;
  isPrimaryKey?: boolean;
  ref?: string | null;
  distinct?: number | null;
  topValues?: Array<[string, number]>;
  /** What the source itself says — a database comment or model export. The customer's own words. */
  description?: string | null;
  /** What this system concluded, tagged by where it came from. Kept beside the source's words,
   *  never merged into them. `freshness` entries measure the data rather than define the column. */
  derived?: Array<{ source: string; text: string }>;
  unit?: string | null;
  annotations: BiSlAnnotation[];
  concepts: BiSlConceptRef[];
  status: 'CERTIFIED' | 'CANDIDATE' | 'DESCRIBED' | 'UNDEFINED' | (string & {});
};
export type BiSlTable = {
  entity: string;
  tableName: string;
  tablePattern: string;
  schema: string;
  description?: string | null;
  rowCount?: number | null;
  primaryKey: string[];
  relationships: Array<{ column: string; ref_entity: string; ref_column: string }>;
  annotations: BiSlAnnotation[];
  columns: BiSlColumn[];
  undefinedColumns: number;
  scannedAt: string;
};
export type BiSemanticLayerInventory = {
  datasourceId: string;
  tables: BiSlTable[];
  tableCount: number;
  columnCount: number;
  undefinedColumns: number;
  catalog: Record<string, number>;
  version?: { version: number; certified_count: number; created_at: string; note?: string } | null;
};
export type BiSemanticLayerStatus = {
  ok: boolean;
  datasourceId: string;
  status: Record<string, number>;
  certifiedByType: Record<string, number>;
  version?: { version: number; certified_count: number; created_at: string } | null;
  profiles: number;
  queries: { total: number; validated: number; deterministic: number };
  unresolved: Record<string, number>;
};
export type BiSlConcept = {
  concept: {
    id: string;
    term: string;
    normalized_term: string;
    semantic_type: string;
    status: string;
    confidence: number;
    version: number;
    sense_id: number;
    synonyms: string[];
    explain: Record<string, unknown>;
  };
  mappings: Array<{ entity: string; table_pattern: string; column?: string | null; operator?: string | null; values: string[]; formula?: string | null; extra?: Record<string, unknown> }>;
};


/** Terms real users asked for that the catalog could not place — the queue behind the annotation page.
 *  `undefined` is a word nobody has defined; `qualifier` narrows a question in a way nothing covers. */
export type BiSemanticLayerGap = {
  kind: 'undefined' | 'qualifier';
  term: string;
  count: number;
  questions: string[];
  lastAsked?: string | null;
};

export type BiSemanticLayerGaps = {
  ok: boolean;
  days: number;
  gaps: BiSemanticLayerGap[];
  /** Entities whose data window was never measured: scope checks are off for them. */
  unmeasuredWindows: string[];
};
