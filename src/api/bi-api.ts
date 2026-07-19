import type {
  BiAlertRule,
  BiBrandingSettings,
  BiBudgetEnvelope,
  BiBudgetImportResult,
  BiBudgetSummary,
  BiChatResponse,
  BiChatSession,
  BiConnectionProfile,
  BiConnectionUpsert,
  BiSourcesList,
  BiGlossaryEntry,
  BiQueryTemplate,
  BiReport,
  BiSavedQuery,
  BiSchedule,
  BiSchema,
  BiSchemaGraph,
  BiShareLink,
  BiStatus,
  BiWidgetData,
} from './types';
import { apiBase, buildRunnerHeaders, parseApiError, request, type ApiConfig } from './http';

export type SemanticTemplateCandidate = {
  candidate_id: string;
  status?: string;
  gate?: string;
  question?: string;
  template?: { template_id?: string; allowed_measures?: string[]; utterances?: Record<string, string[]> };
  quality?: {
    ready_for_approval?: boolean;
    checks?: Record<string, boolean>;
    errors?: Array<{ code: string; detail: string }>;
    confidence?: number;
    repeat_count?: number;
  };
  preview?: {
    normalized_question?: string;
    logical_template?: { template_id?: string; allowed_measures?: string[] };
    bound?: {
      entities?: Record<string, { table?: string; key?: string }>;
      measures?: Record<string, { entity?: string; field?: string; aggregation?: string }>;
    };
    compiled_sql?: string | null;
    sample_result?: {
      ok?: boolean;
      columns?: string[];
      rows?: Array<Record<string, unknown>>;
      row_count?: number;
      error?: string;
    };
    date_filter?: unknown;
    binding_fingerprint?: string;
    schema_fingerprint?: string | null;
    similar_templates?: Array<{ template_id?: string; score?: number }>;
  };
};

export function createBiApi() {
  const bi = {
    status: (c: ApiConfig) => request<BiStatus>(c, '/api/v1/bi/status'),
    health: (c: ApiConfig) => request<Record<string, unknown>>(c, '/api/v1/bi/health'),
    schema: (c: ApiConfig, datasourceId?: string) =>
      request<BiSchema>(
        c,
        datasourceId
          ? `/api/v1/bi/schema?datasource_id=${encodeURIComponent(datasourceId)}`
          : '/api/v1/bi/schema',
      ),
    schemaGraph: (c: ApiConfig, datasourceId?: string) =>
      request<BiSchemaGraph>(
        c,
        datasourceId
          ? `/api/v1/bi/schema/graph?datasource_id=${encodeURIComponent(datasourceId)}`
          : '/api/v1/bi/schema/graph',
      ),
    refreshSchema: (c: ApiConfig, datasourceId?: string) =>
      request<BiSchema>(c, '/api/v1/bi/schema/refresh', {
        method: 'POST',
        body: JSON.stringify(datasourceId ? { datasource_id: datasourceId } : {}),
      }),
    briefing: (c: ApiConfig, dashboardId: string, locale = 'en') =>
      request<{
        dashboard_id: string;
        anomalies: Array<{
          key?: string;
          metric: string;
          delta_pct: number;
          tone?: string;
          widget_id?: string;
          ask_prompt: string;
          status?: string;
        }>;
        alerts: Array<{
          id?: string;
          title?: string;
          last_value?: number;
          threshold?: number;
          condition?: string;
          ask_prompt?: string;
        }>;
        insights: Array<{ title: string; body: string; tone?: string }>;
        attention?: Array<{
          id: string;
          kind: string;
          tone?: string;
          title?: string;
          title_key?: string;
          body?: string | null;
          body_key?: string;
          body_vars?: Record<string, string | number>;
          delta_pct?: number | null;
          ask_prompt?: string;
          href?: string | null;
        }>;
        deltas?: Array<{
          widget_id?: string;
          title: string;
          today?: number;
          delta_day_pct?: number | null;
          delta_week_pct?: number | null;
        }>;
        delta_summary?: { up: number; down: number; flat: number };
        data_pulse?: {
          db_ready?: boolean;
          table_count?: number;
          source_label?: string | null;
          schema_age_hours?: number | null;
          top_tables?: string[];
        };
        actions: Array<{
          id: string;
          kind: string;
          label_key?: string;
          label?: string;
          ask_prompt?: string;
          href?: string | null;
        }>;
        anomaly_count: number;
        alert_count: number;
        action_count?: number;
      }>(c, `/api/v1/bi/briefing?dashboard_id=${encodeURIComponent(dashboardId)}&locale=${encodeURIComponent(locale)}`),
    opsHealth: (c: ApiConfig, dashboardId = 'default') =>
      request<{
        dashboard_id: string;
        anomaly_count: number;
        alert_count: number;
        action_count: number;
        db_ready: boolean;
        data_pulse?: {
          db_ready?: boolean;
          table_count?: number;
          source_label?: string | null;
        };
        delta_summary: Array<{
          title: string;
          today: number;
          delta_day_pct?: number | null;
          delta_week_pct?: number | null;
        }>;
        actions: Array<{ id: string; kind: string; label_key?: string; label?: string }>;
      }>(c, `/api/v1/bi/ops-health?dashboard_id=${encodeURIComponent(dashboardId)}`),
    anomalies: {
      list: (c: ApiConfig, status = 'open') =>
        request<{ items: Array<Record<string, unknown>> }>(
          c,
          `/api/v1/bi/anomalies?status=${encodeURIComponent(status)}`,
        ),
      get: (c: ApiConfig, key: string) =>
        request<Record<string, unknown>>(c, `/api/v1/bi/anomalies/${encodeURIComponent(key)}`),
      ack: (c: ApiConfig, key: string, body?: { status?: string; note?: string }) =>
        request<Record<string, unknown>>(c, `/api/v1/bi/anomalies/${encodeURIComponent(key)}/ack`, {
          method: 'POST',
          body: JSON.stringify(body || { status: 'ack' }),
        }),
      resolve: (c: ApiConfig, key: string, body?: { note?: string }) =>
        request<Record<string, unknown>>(
          c,
          `/api/v1/bi/anomalies/${encodeURIComponent(key)}/resolve`,
          { method: 'POST', body: JSON.stringify(body || {}) },
        ),
      promoteAlert: (
        c: ApiConfig,
        key: string,
        body?: {
          title?: string;
          sql?: string;
          column?: string;
          threshold?: number;
          condition?: string;
          recipient?: string;
        },
      ) =>
        request<BiAlertRule>(c, `/api/v1/bi/anomalies/${encodeURIComponent(key)}/promote-alert`, {
          method: 'POST',
          body: JSON.stringify(body || {}),
        }),
    },
    kpiSuggestions: (c: ApiConfig, limit = 8) =>
      request<{
        suggestions: Array<{
          id: string;
          kind: string;
          table?: string;
          table_name?: string;
          measure?: string | null;
          category?: string | null;
          date_column?: string | null;
          title?: string;
          sql_hint?: string;
          prompt?: string;
          reason?: string;
        }>;
      }>(c, `/api/v1/bi/kpi/suggestions?limit=${limit}`),
    languagePacks: (c: ApiConfig, locale = 'en') =>
      request<{ packs: Array<{ id: string; label: string; chips: string[]; template_ids: string[] }> }>(
        c,
        `/api/v1/bi/language-packs?locale=${encodeURIComponent(locale)}`,
      ),
    chat: (c: ApiConfig, body: { message: string; session_id?: string; recipient?: string; dashboard_id?: string }) =>
      request<BiChatResponse>(c, '/api/v1/bi/chat', { method: 'POST', body: JSON.stringify(body) }),
    chatSessions: (c: ApiConfig) => request<{ sessions: BiChatSession[] }>(c, '/api/v1/bi/chat/sessions'),
    chatHistory: (c: ApiConfig, sessionId: string) =>
      request<{
        session_id: string;
        messages: unknown[];
        title?: string;
        pending?: boolean;
        queue_depth?: number;
      }>(
        c,
        `/api/v1/bi/chat/${sessionId}`,
      ),
    chatPending: (c: ApiConfig, sessionId: string) =>
      request<{ session_id: string; pending: boolean; queue_depth?: number }>(
        c,
        `/api/v1/bi/chat/${sessionId}/pending`,
      ),
    deleteChatSession: (c: ApiConfig, sessionId: string) =>
      request<void>(c, `/api/v1/bi/chat/${sessionId}`, { method: 'DELETE' }),
    renameChatSession: (c: ApiConfig, sessionId: string, title: string) =>
      request<{ session_id: string; title: string }>(c, `/api/v1/bi/chat/${sessionId}`, {
        method: 'PATCH',
        body: JSON.stringify({ title }),
      }),
    exportQuery: async (c: ApiConfig, sql: string, format: 'csv' | 'xlsx' | 'pdf') => {
      await bi.download(c, `/api/v1/bi/query/export?format=${format}`, `query.${format}`, sql);
    },
    chatSuggestions: (
      c: ApiConfig,
      opts?: { datasourceId?: string; limit?: number },
    ) => {
      const qs = new URLSearchParams();
      if (opts?.datasourceId) qs.set('datasource_id', opts.datasourceId);
      if (opts?.limit != null) qs.set('limit', String(opts.limit));
      const suffix = qs.toString() ? `?${qs.toString()}` : '';
      return request<{
        datasource_id: string;
        suggestions: Array<{ text: string; source: 'learned' | 'default' | string; count: number }>;
        learned_count?: number;
        default_count?: number;
      }>(c, `/api/v1/bi/suggestions${suffix}`);
    },
    templates: (c: ApiConfig, opts?: { refresh?: boolean }) =>
      request<{
        templates: BiQueryTemplate[];
        meta?: {
          source_id?: string;
          source_label?: string;
          fingerprint?: string;
          generated_at?: string;
          origin?: string;
          cached?: boolean;
        };
      }>(
        c,
        `/api/v1/bi/templates${opts?.refresh ? '?refresh=true' : ''}`,
      ),
    refreshTemplates: (c: ApiConfig) =>
      request<{
        templates: BiQueryTemplate[];
        meta?: Record<string, unknown>;
      }>(c, '/api/v1/bi/templates/refresh', { method: 'POST' }),
    warmTemplates: (
      c: ApiConfig,
      body?: { template_ids?: string[]; limit?: number },
    ) =>
      request<{
        results: Array<{
          template_id: string;
          ok?: boolean;
          sql?: string;
          result?: BiWidgetData;
          duration_ms?: number;
          error?: string;
        }>;
        warmed?: number;
        ttl_sec?: number;
      }>(c, '/api/v1/bi/templates/warm', {
        method: 'POST',
        body: JSON.stringify(body || {}),
      }),
    createTemplate: (
      c: ApiConfig,
      body: {
        title: string;
        prompt: string;
        locale?: string;
        sql_hint?: string;
        category?: string;
        widget_type?: string;
      },
    ) =>
      request<BiQueryTemplate>(c, '/api/v1/bi/templates', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    deleteTemplate: (c: ApiConfig, id: string) =>
      request<void>(c, `/api/v1/bi/templates/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    seedTemplates: (
      c: ApiConfig,
      body: { template_ids: string[]; dashboard_id?: number; title?: string; locale?: string },
    ) =>
      request<{
        dashboard_id: number;
        title: string;
        widget_count: number;
        embed_uuid?: string;
      }>(c, '/api/v1/bi/templates/seed', { method: 'POST', body: JSON.stringify(body) }),
    departmentBoards: {
      create: (c: ApiConfig, department: 'ceo' | 'cfo' | 'sales_ops' | 'sales' | 'operations' | 'finance', locale?: string) => {
        const q = locale ? `?locale=${encodeURIComponent(locale)}` : '';
        return request<{
          department: string;
          dashboard_id: number;
          title: string;
          embed_uuid?: string;
          guest?: Record<string, unknown>;
          widget_count: number;
          matched_tables?: string[];
          fallback?: boolean;
        }>(c, `/api/v1/bi/department-boards/${encodeURIComponent(department)}${q}`, { method: 'POST' });
      },
    },
    queries: {
      list: (c: ApiConfig) => request<{ queries: BiSavedQuery[] }>(c, '/api/v1/bi/queries'),
      save: (c: ApiConfig, body: Partial<BiSavedQuery> & { title: string; sql: string }) =>
        request<BiSavedQuery>(c, '/api/v1/bi/queries', { method: 'POST', body: JSON.stringify(body) }),
      run: (c: ApiConfig, id: string) =>
        request<Record<string, unknown>>(c, `/api/v1/bi/queries/${id}/run`, { method: 'POST' }),
      delete: (c: ApiConfig, id: string) =>
        request<void>(c, `/api/v1/bi/queries/${id}`, { method: 'DELETE' }),
    },
    glossary: {
      list: (c: ApiConfig, locale?: string) => {
        const qs = locale ? `?locale=${encodeURIComponent(locale)}` : '';
        return request<{ entries: BiGlossaryEntry[] }>(c, `/api/v1/bi/glossary${qs}`);
      },
      save: (c: ApiConfig, entries: BiGlossaryEntry[]) =>
        request<{ entries: BiGlossaryEntry[] }>(c, '/api/v1/bi/glossary', {
          method: 'PUT',
          body: JSON.stringify({ entries }),
        }),
      suggest: (c: ApiConfig, locale?: string) => {
        const qs = locale ? `?locale=${encodeURIComponent(locale)}` : '';
        return request<{
          suggestions: BiGlossaryEntry[];
          meta?: { locale?: string; origin?: string; count?: number };
        }>(c, `/api/v1/bi/glossary/suggest${qs}`, { method: 'POST' });
      },
      delete: (c: ApiConfig, entryId: string) =>
        request<void>(c, `/api/v1/bi/glossary/${entryId}`, { method: 'DELETE' }),
    },
    alerts: {
      list: (c: ApiConfig) => request<{ alerts: BiAlertRule[] }>(c, '/api/v1/bi/alerts'),
      save: (c: ApiConfig, body: Partial<BiAlertRule> & { title: string; sql: string; column: string; threshold: number }) =>
        request<BiAlertRule>(c, '/api/v1/bi/alerts', { method: 'POST', body: JSON.stringify(body) }),
      delete: (c: ApiConfig, id: string) =>
        request<void>(c, `/api/v1/bi/alerts/${id}`, { method: 'DELETE' }),
      runDue: (c: ApiConfig) =>
        request<{ checked?: number; triggered?: number; errors?: string[] }>(c, '/api/v1/bi/alerts/check-now', {
          method: 'POST',
        }),
    },
    semantic: {
      metrics: {
        list: (c: ApiConfig, status?: string) => {
          const qs = status ? `?status=${encodeURIComponent(status)}` : '';
          return request<{
            metrics: Array<{
              metric_id: string;
              label?: string;
              expression?: string;
              source_table?: string;
              grain?: string;
              status?: string;
              [key: string]: unknown;
            }>;
          }>(c, `/api/v1/bi/semantic/metrics${qs}`);
        },
        upsert: (
          c: ApiConfig,
          body: {
            metric_id: string;
            expression: string;
            label?: string;
            source_table?: string;
            grain?: string;
            time_dimension?: string;
            mandatory_filters?: string[];
            allowed_dimensions?: string[];
            owner?: string;
            status?: string;
            golden_sql?: string;
            stale_after_hours?: number;
          },
        ) =>
          request<Record<string, unknown>>(c, '/api/v1/bi/semantic/metrics', {
            method: 'POST',
            body: JSON.stringify(body),
          }),
        certify: (c: ApiConfig, metricId: string, body?: { golden_sql?: string }) =>
          request<Record<string, unknown>>(
            c,
            `/api/v1/bi/semantic/metrics/${encodeURIComponent(metricId)}/certify`,
            { method: 'POST', body: JSON.stringify(body || {}) },
          ),
        deprecate: (c: ApiConfig, metricId: string) =>
          request<Record<string, unknown>>(
            c,
            `/api/v1/bi/semantic/metrics/${encodeURIComponent(metricId)}/deprecate`,
            { method: 'POST' },
          ),
        versions: (c: ApiConfig, metricId: string) =>
          request<{ versions: Array<Record<string, unknown>> }>(
            c,
            `/api/v1/bi/semantic/metrics/${encodeURIComponent(metricId)}/versions`,
          ),
        goldenTest: (c: ApiConfig, metricId: string, body?: { golden_sql?: string }) =>
          request<Record<string, unknown>>(
            c,
            `/api/v1/bi/semantic/metrics/${encodeURIComponent(metricId)}/golden-test`,
            { method: 'POST', body: JSON.stringify(body || {}) },
          ),
      },
      joins: {
        list: (c: ApiConfig) =>
          request<{
            joins: Array<{
              join_id: string;
              left_table: string;
              right_table: string;
              left_key: string;
              right_key: string;
              cardinality?: string;
              bridge_flag?: boolean;
              causes_fanout?: boolean;
            }>;
          }>(c, '/api/v1/bi/semantic/joins'),
        upsert: (
          c: ApiConfig,
          body: {
            join_id?: string;
            left_table: string;
            right_table: string;
            left_key: string;
            right_key: string;
            cardinality?: string;
            bridge_flag?: boolean;
            causes_fanout?: boolean;
          },
        ) =>
          request<Record<string, unknown>>(c, '/api/v1/bi/semantic/joins', {
            method: 'POST',
            body: JSON.stringify(body),
          }),
      },
      binding: {
        status: (c: ApiConfig) =>
          request<{
            enabled?: boolean;
            active_source_id?: string;
            binding_status?: string | null;
            binding_error?: string | null;
            versions?: Record<string, string>;
            end_user_note?: string;
          }>(c, '/api/v1/bi/semantic/status'),
        get: (c: ApiConfig) => request<Record<string, unknown>>(c, '/api/v1/bi/semantic/binding'),
        approvalViews: (c: ApiConfig) =>
          request<{
            project_id: string;
            status: string;
            instruction?: string;
            auto_enriched?: boolean;
            views: Array<{
              project_id: string;
              logical_concept: string;
              physical_table: string;
              physical_field: string;
              description?: string;
              comment?: string | null;
              sample_values?: unknown[];
              null_ratio?: number | null;
              min_value?: number | string | null;
              max_value?: number | string | null;
              aggregation_example?: string;
              alternative_candidates?: Array<{
                field: string;
                reason?: string;
                profile?: { sample_values?: unknown[]; comment?: string | null };
              }>;
            }>;
          }>(c, '/api/v1/bi/semantic/binding/approval-views'),
        approve: (c: ApiConfig, body: { approved_by: string; notes?: string }) =>
          request<{
            ok: boolean;
            project_id?: string;
            status?: string;
            fingerprint?: string;
            auto_enriched?: boolean;
          }>(c, '/api/v1/bi/semantic/binding/approve', {
            method: 'POST',
            body: JSON.stringify(body),
          }),
        enrich: (c: ApiConfig) =>
          request<{
            ok: boolean;
            project_id?: string;
            status?: string;
            measures_with_profiles?: string[];
            measures_with_alternatives?: string[];
          }>(c, '/api/v1/bi/semantic/binding/enrich', { method: 'POST', body: '{}' }),
        installFixture: (c: ApiConfig, body?: { fixture_name?: string; as_project_id?: string }) =>
          request<{ ok: boolean; project_id?: string; fingerprint?: string }>(
            c,
            '/api/v1/bi/semantic/binding/install-fixture',
            { method: 'POST', body: JSON.stringify(body || {}) },
          ),
      },
      graph: {
        list: (c: ApiConfig) =>
          request<{
            business_graph_version?: string;
            edges: Array<{
              from: string;
              to: string;
              role: string;
              cardinality?: string;
              status?: string;
              steward?: string | null;
            }>;
          }>(c, '/api/v1/bi/semantic/graph'),
        promote: (
          c: ApiConfig,
          body: {
            from_entity: string;
            to_entity: string;
            role: string;
            decision: 'approved' | 'rejected';
            steward?: string;
          },
        ) =>
          request<{ ok: boolean; edge?: Record<string, unknown> }>(c, '/api/v1/bi/semantic/graph/promote', {
            method: 'POST',
            body: JSON.stringify(body),
          }),
      },
      templates: {
        list: (c: ApiConfig) =>
          request<{
            project_id: string;
            template_version?: string;
            active?: Array<{ template_id: string; status?: string }>;
            invalidated?: Array<{ template_id: string; status?: string }>;
            metrics?: {
              ready_approved?: number;
              ready_rejected?: number;
              steward_rejection_rate?: number | null;
            };
            candidates: SemanticTemplateCandidate[];
            ready_for_approval?: SemanticTemplateCandidate[];
            rejected?: Array<{ candidate_id: string }>;
          }>(c, '/api/v1/bi/semantic/templates'),
        propose: (c: ApiConfig, body: { question: string; enrich_qwen?: boolean }) =>
          request<{
            ok: boolean;
            code?: string;
            candidate?: {
              candidate_id: string;
              question?: string;
              template?: { template_id?: string };
              preview?: Record<string, unknown>;
            };
          }>(c, '/api/v1/bi/semantic/templates/propose', {
            method: 'POST',
            body: JSON.stringify(body),
          }),
        promote: (
          c: ApiConfig,
          body: {
            candidate_id: string;
            decision: 'approved' | 'rejected';
            steward?: string;
            rejection_reason?: string;
          },
        ) =>
          request<{ ok: boolean; status?: string; template_id?: string; code?: string; audit?: Record<string, unknown> }>(
            c,
            '/api/v1/bi/semantic/templates/promote',
            { method: 'POST', body: JSON.stringify(body) },
          ),
      },
    },
    /** Faz 7 governance catalog (/api/v1/semantic/*) — dual-review, versions, compile */
    catalogGov: {
      status: (c: ApiConfig) =>
        request<{
          ok?: boolean;
          enabled?: boolean;
          contractVersion?: string;
          metrics?: number;
          candidates?: number;
          promotions?: number;
          versions?: number;
        }>(c, '/api/v1/semantic/status'),
      bootstrapSlice: (c: ApiConfig, body?: { datasourceId?: string; published?: boolean }) =>
        request<{ ok: boolean; metric_id?: string; filter_id?: string; term_id?: string }>(
          c,
          '/api/v1/semantic/bootstrap/unpaid-invoice-slice',
          { method: 'POST', body: JSON.stringify(body || {}) },
        ),
      metrics: (c: ApiConfig, datasourceId = 'default') =>
        request<{ metrics: Array<Record<string, unknown>> }>(
          c,
          `/api/v1/semantic/metrics?datasource_id=${encodeURIComponent(datasourceId)}`,
        ),
      businessTerms: (c: ApiConfig, datasourceId = 'default') =>
        request<{ businessTerms: Array<Record<string, unknown>> }>(
          c,
          `/api/v1/semantic/business-terms?datasource_id=${encodeURIComponent(datasourceId)}`,
        ),
      filterRules: (c: ApiConfig, datasourceId = 'default') =>
        request<{ filterRules: Array<Record<string, unknown>> }>(
          c,
          `/api/v1/semantic/filter-rules?datasource_id=${encodeURIComponent(datasourceId)}`,
        ),
      promotions: (c: ApiConfig) =>
        request<{ promotionRequests: Array<Record<string, unknown>> }>(
          c,
          '/api/v1/semantic/promotion-requests',
        ),
      versions: (c: ApiConfig, datasourceId = 'default') =>
        request<{ versions: Array<Record<string, unknown>>; active: Record<string, unknown> | null }>(
          c,
          `/api/v1/semantic/versions?datasource_id=${encodeURIComponent(datasourceId)}`,
        ),
      validateMetric: (c: ApiConfig, metricId: string) =>
        request<Record<string, unknown>>(c, `/api/v1/semantic/metrics/${encodeURIComponent(metricId)}/validate`, {
          method: 'POST',
        }),
      submitReview: (c: ApiConfig, metricId: string) =>
        request<{ ok: boolean; promotionRequest?: Record<string, unknown> }>(
          c,
          `/api/v1/semantic/metrics/${encodeURIComponent(metricId)}/submit-review`,
          { method: 'POST' },
        ),
      review: (
        c: ApiConfig,
        promotionId: string,
        body: { decision: string; role: string; comment?: string },
      ) =>
        request<Record<string, unknown>>(
          c,
          `/api/v1/semantic/promotion-requests/${encodeURIComponent(promotionId)}/reviews`,
          { method: 'POST', body: JSON.stringify(body) },
        ),
      publish: (c: ApiConfig, promotionId: string, body?: { semanticVersion?: string; schemaVersion?: string }) =>
        request<Record<string, unknown>>(
          c,
          `/api/v1/semantic/promotion-requests/${encodeURIComponent(promotionId)}/publish`,
          { method: 'POST', body: JSON.stringify(body || {}) },
        ),
      rollback: (c: ApiConfig, versionId: string) =>
        request<Record<string, unknown>>(
          c,
          `/api/v1/semantic/versions/${encodeURIComponent(versionId)}/rollback`,
          { method: 'POST' },
        ),
      compile: (
        c: ApiConfig,
        body: { metric?: string; datasourceId?: string; period?: { from?: string; to?: string } },
      ) =>
        request<{ ok: boolean; sql?: string; logicalPlan?: Record<string, unknown>; astFingerprint?: string }>(
          c,
          '/api/v1/semantic/compile',
          { method: 'POST', body: JSON.stringify(body) },
        ),
    },
    artifacts: {
      create: (
        c: ApiConfig,
        body: {
          kind?: string;
          answer_md?: string;
          sql?: string;
          sql_fingerprint?: string;
          chart_spec?: Record<string, unknown>;
          provenance?: Record<string, unknown>;
          locale?: string;
          masked_columns?: string[];
        },
      ) =>
        request<{ artifact_id: string }>(c, '/api/v1/bi/artifacts', {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      get: (c: ApiConfig, id: string) =>
        request<Record<string, unknown>>(c, `/api/v1/bi/artifacts/${encodeURIComponent(id)}`),
    },
    narrative: (c: ApiConfig, dashboardId = 'default', locale = 'en') =>
      request<{
        headline: string;
        bullets: string[];
        drivers: Array<{ anomaly_key?: string; label?: string; tone?: string; delta_pct?: number }>;
        generated_at?: string;
        locale?: string;
      }>(
        c,
        `/api/v1/bi/narrative?dashboard_id=${encodeURIComponent(dashboardId)}&locale=${encodeURIComponent(locale)}`,
      ),
    scenario: {
      simulate: (
        c: ApiConfig,
        body: {
          base_metric_id?: string;
          base_value?: number;
          drivers: Array<{ target?: string; op?: string; value: number }>;
        },
      ) =>
        request<{
          base: number;
          simulated: number;
          delta_pct: number;
          drivers: Array<Record<string, unknown>>;
          widget?: Record<string, unknown>;
        }>(c, '/api/v1/bi/scenario/simulate', { method: 'POST', body: JSON.stringify(body) }),
    },
    domainPacks: {
      list: (c: ApiConfig) =>
        request<{ packs: Array<{ id: string; label_key?: string; score?: number }> }>(
          c,
          '/api/v1/bi/domain-packs',
        ),
      preview: (c: ApiConfig, packId: string) =>
        request<Record<string, unknown>>(
          c,
          `/api/v1/bi/domain-packs/${encodeURIComponent(packId)}/preview`,
          { method: 'POST', body: '{}' },
        ),
      apply: (c: ApiConfig, packId: string, mapping?: Record<string, unknown>) =>
        request<Record<string, unknown>>(
          c,
          `/api/v1/bi/domain-packs/${encodeURIComponent(packId)}/apply`,
          { method: 'POST', body: JSON.stringify({ mapping: mapping || {} }) },
        ),
    },
    comments: {
      list: (c: ApiConfig, targetType: string, targetId: string) =>
        request<{ items: Array<Record<string, unknown>> }>(
          c,
          `/api/v1/bi/comments?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}`,
        ),
      create: (
        c: ApiConfig,
        body: { target_type: string; target_id: string; body: string; parent_id?: string },
      ) =>
        request<Record<string, unknown>>(c, '/api/v1/bi/comments', {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      delete: (c: ApiConfig, id: string) =>
        request<{ ok: boolean }>(c, `/api/v1/bi/comments/${encodeURIComponent(id)}`, {
          method: 'DELETE',
        }),
    },
    lineage: {
      metric: (c: ApiConfig, metricId: string) =>
        request<Record<string, unknown>>(
          c,
          `/api/v1/bi/lineage/metric/${encodeURIComponent(metricId)}`,
        ),
    },
    sensitivity: {
      list: (c: ApiConfig) =>
        request<{ items: Array<Record<string, unknown>> }>(c, '/api/v1/bi/schema/sensitivity'),
      put: (
        c: ApiConfig,
        body: { table_name: string; column_name: string; sensitivity: string },
      ) =>
        request<Record<string, unknown>>(c, '/api/v1/bi/schema/sensitivity', {
          method: 'PUT',
          body: JSON.stringify(body),
        }),
    },
    tenantSecurity: {
      get: (c: ApiConfig) => request<Record<string, unknown>>(c, '/api/v1/bi/tenant/security'),
      put: (c: ApiConfig, body: Record<string, unknown>) =>
        request<Record<string, unknown>>(c, '/api/v1/bi/tenant/security', {
          method: 'PUT',
          body: JSON.stringify(body),
        }),
    },
    actions: {
      confirm: (
        c: ApiConfig,
        body: {
          action: string;
          payload?: Record<string, unknown>;
          confirm?: boolean;
          idempotency_key?: string;
        },
      ) =>
        request<Record<string, unknown>>(c, '/api/v1/bi/actions/confirm', {
          method: 'POST',
          body: JSON.stringify(body),
        }),
    },
    budgets: {
      list: (c: ApiConfig, q?: { fiscal_year?: number; kind?: string; status?: string; scenario?: string }) => {
        const params = new URLSearchParams();
        if (q?.fiscal_year != null) params.set('fiscal_year', String(q.fiscal_year));
        if (q?.kind) params.set('kind', q.kind);
        if (q?.status) params.set('status', q.status);
        if (q?.scenario) params.set('scenario', q.scenario);
        const qs = params.toString();
        return request<{ budgets: BiBudgetEnvelope[] }>(c, `/api/v1/bi/budgets${qs ? `?${qs}` : ''}`);
      },
      summary: (c: ApiConfig, fiscalYear?: number, opts?: { scenario?: string; reporting_currency?: string }) => {
        const params = new URLSearchParams();
        if (fiscalYear != null) params.set('fiscal_year', String(fiscalYear));
        if (opts?.scenario) params.set('scenario', opts.scenario);
        if (opts?.reporting_currency) params.set('reporting_currency', opts.reporting_currency);
        const qs = params.toString();
        return request<BiBudgetSummary>(c, `/api/v1/bi/budgets/summary${qs ? `?${qs}` : ''}`);
      },
      actualsTemplates: (c: ApiConfig) =>
        request<{
          templates: Array<{
            id: string;
            kind?: string;
            label_key?: string;
            table?: string;
            table_name?: string;
            measure?: string;
            sql: string;
            demo?: boolean;
          }>;
        }>(c, '/api/v1/bi/budgets/actuals-templates'),
      relatedTables: (c: ApiConfig, limit = 24) =>
        request<{
          tables: Array<{
            table: string;
            table_name: string;
            score: number;
            money_columns: string[];
            date_columns: string[];
            suggested_measure?: string | null;
            suggested_sql?: string;
            column_count?: number;
          }>;
        }>(c, `/api/v1/bi/budgets/related-tables?limit=${Math.min(Math.max(limit, 1), 48)}`),
      matchPreview: (c: ApiConfig, fiscalYear?: number) => {
        const params = new URLSearchParams();
        if (fiscalYear != null) params.set('fiscal_year', String(fiscalYear));
        const qs = params.toString();
        return request<{
          fiscal_year: number;
          plan_source?: Record<string, unknown> | null;
          spend_source?: Record<string, unknown> | null;
          matches: Array<{
            name: string;
            kind: string;
            allocated: number;
            cost_center?: string;
            budget_code?: string;
            match_confidence?: string;
            invoice_count?: number | null;
            invoice_total?: number | null;
            projected_remaining?: number | null;
            actuals_sql?: string;
          }>;
          warnings?: string[];
        }>(c, `/api/v1/bi/budgets/match-preview${qs ? `?${qs}` : ''}`);
      },
      syncFromSource: (
        c: ApiConfig,
        body?: { fiscal_year?: number; refresh?: boolean; scenario?: string },
      ) =>
        request<{
          fiscal_year: number;
          created: number;
          updated: number;
          skipped: number;
          match_count: number;
          warnings?: string[];
          refresh?: { refreshed: number; errors: number } | null;
        }>(c, '/api/v1/bi/budgets/sync-from-source', {
          method: 'POST',
          body: JSON.stringify(body || {}),
        }),
      validateSql: (c: ApiConfig, sql: string) =>
        request<{ ok: boolean; sample: number; sql: string; source: string }>(c, '/api/v1/bi/budgets/validate-sql', {
          method: 'POST',
          body: JSON.stringify({ sql }),
        }),
      approve: (c: ApiConfig, id: string) =>
        request<BiBudgetEnvelope>(c, `/api/v1/bi/budgets/${id}/approve`, { method: 'POST' }),
      lock: (c: ApiConfig, id: string) =>
        request<BiBudgetEnvelope>(c, `/api/v1/bi/budgets/${id}/lock`, { method: 'POST' }),
      unlock: (c: ApiConfig, id: string) =>
        request<BiBudgetEnvelope>(c, `/api/v1/bi/budgets/${id}/unlock`, { method: 'POST' }),
      changeLog: (c: ApiConfig, id: string) =>
        request<{
          entries: Array<{
            action: string;
            actor: string;
            field?: string | null;
            old_value?: string | null;
            new_value?: string | null;
            created_at?: string | null;
          }>;
        }>(c, `/api/v1/bi/budgets/${id}/change-log`),
      history: (c: ApiConfig, id: string) =>
        request<{ points: Array<{ actual: number | null; recorded_at?: string; source?: string }> }>(
          c,
          `/api/v1/bi/budgets/${id}/history`,
        ),
      breakdown: (c: ApiConfig, id: string) =>
        request<{
          budget_id?: string;
          columns: string[];
          rows: Array<Record<string, unknown> | unknown[]>;
          row_count: number;
          truncated?: boolean;
        }>(c, `/api/v1/bi/budgets/${id}/breakdown`),
      sharePack: (
        c: ApiConfig,
        body: {
          fiscal_year: number;
          scenario?: string;
          reporting_currency?: string;
          locale?: string;
          ttl_hours?: number;
          password?: string;
        },
      ) =>
        request<{ token?: string; expires_at?: string; resource_type?: string }>(c, '/api/v1/bi/budgets/share-pack', {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      periods: (c: ApiConfig, id: string) =>
        request<{ periods: Array<{ period_index: number; allocated: number; actual: number | null }> }>(
          c,
          `/api/v1/bi/budgets/${id}/periods`,
        ),
      savePeriods: (
        c: ApiConfig,
        id: string,
        periods: Array<{ period_index: number; allocated: number; actual?: number | null }>,
      ) =>
        request<{ periods: Array<{ period_index: number; allocated: number; actual: number | null }> }>(
          c,
          `/api/v1/bi/budgets/${id}/periods`,
          { method: 'PUT', body: JSON.stringify({ periods }) },
        ),
      commitments: (c: ApiConfig, id: string) =>
        request<{
          commitments: Array<{
            id: string;
            description: string;
            amount: number;
            currency: string;
            status: string;
            due_date?: string | null;
          }>;
        }>(c, `/api/v1/bi/budgets/${id}/commitments`),
      saveCommitment: (
        c: ApiConfig,
        budgetId: string,
        body: { id?: string; description?: string; amount: number; currency?: string; status?: string; due_date?: string },
      ) =>
        request<Record<string, unknown>>(c, `/api/v1/bi/budgets/${budgetId}/commitments`, {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      deleteCommitment: (c: ApiConfig, budgetId: string, commitmentId: string) =>
        request<void>(c, `/api/v1/bi/budgets/${budgetId}/commitments/${commitmentId}`, { method: 'DELETE' }),
      transfer: (c: ApiConfig, body: { from_budget_id: string; to_budget_id: string; amount: number }) =>
        request<{ amount: number; from: BiBudgetEnvelope; to: BiBudgetEnvelope }>(c, '/api/v1/bi/budgets/transfer', {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      fxRates: (c: ApiConfig) =>
        request<{
          rates: Array<{ id?: number; from_currency: string; to_currency: string; rate: number; as_of?: string }>;
        }>(c, '/api/v1/bi/fx-rates'),
      upsertFxRate: (
        c: ApiConfig,
        body: { from_currency: string; to_currency: string; rate: number; as_of?: string },
      ) => request<Record<string, unknown>>(c, '/api/v1/bi/fx-rates', { method: 'POST', body: JSON.stringify(body) }),
      costCenters: (c: ApiConfig) =>
        request<{
          cost_centers: Array<{ id: string; code: string; name: string; parent_id?: string | null; active?: boolean }>;
          tree: Array<Record<string, unknown>>;
        }>(c, '/api/v1/bi/cost-centers'),
      saveCostCenter: (
        c: ApiConfig,
        body: { id?: string; code: string; name: string; parent_id?: string | null; active?: boolean },
      ) => request<Record<string, unknown>>(c, '/api/v1/bi/cost-centers', { method: 'POST', body: JSON.stringify(body) }),
      deleteCostCenter: (c: ApiConfig, id: string) =>
        request<void>(c, `/api/v1/bi/cost-centers/${id}`, { method: 'DELETE' }),
      costCenterRollup: (
        c: ApiConfig,
        fiscalYear: number,
        opts?: { scenario?: string; reporting_currency?: string },
      ) => {
        const params = new URLSearchParams({ fiscal_year: String(fiscalYear) });
        if (opts?.scenario) params.set('scenario', opts.scenario);
        if (opts?.reporting_currency) params.set('reporting_currency', opts.reporting_currency);
        return request<{
          tree: Array<Record<string, unknown>>;
          flat: Array<Record<string, unknown> & { depth?: number }>;
          unassigned: Record<string, number>;
          unassigned_count: number;
          reporting_currency?: string | null;
          fx_missing?: Array<{ id?: string; name?: string; currency?: string }>;
        }>(c, `/api/v1/bi/cost-centers/rollup?${params}`);
      },
      save: (c: ApiConfig, body: Partial<BiBudgetEnvelope> & { name: string; allocated: number }) =>
        request<BiBudgetEnvelope>(c, '/api/v1/bi/budgets', { method: 'POST', body: JSON.stringify(body) }),
      delete: (c: ApiConfig, id: string) =>
        request<void>(c, `/api/v1/bi/budgets/${id}`, { method: 'DELETE' }),
      refreshAll: (c: ApiConfig, fiscalYear?: number) => {
        const qs = fiscalYear != null ? `?fiscal_year=${fiscalYear}` : '';
        return request<{ refreshed: number; errors: number }>(c, `/api/v1/bi/budgets/refresh-actuals${qs}`, {
          method: 'POST',
        });
      },
      refreshOne: (c: ApiConfig, id: string) =>
        request<BiBudgetEnvelope>(c, `/api/v1/bi/budgets/${id}/refresh-actuals`, { method: 'POST' }),
      downloadTemplate: async (c: ApiConfig, fiscalYear?: number) => {
        const qs = fiscalYear != null ? `?fiscal_year=${fiscalYear}` : '';
        const res = await fetch(`${apiBase(c)}/api/v1/bi/budgets/import-template${qs}`, {
          method: 'GET',
          headers: buildRunnerHeaders(c),
          credentials: 'include',
        });
        if (!res.ok) {
          throw new Error(parseApiError(await res.text(), res.status));
        }
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `butce-sablon-${fiscalYear ?? 'template'}.xlsx`;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      importFile: async (c: ApiConfig, file: File, fiscalYear?: number) => {
        const fd = new FormData();
        fd.append('file', file);
        const qs = fiscalYear != null ? `?fiscal_year=${fiscalYear}` : '';
        const res = await fetch(`${apiBase(c)}/api/v1/bi/budgets/import${qs}`, {
          method: 'POST',
          headers: buildRunnerHeaders(c),
          body: fd,
          credentials: 'include',
        });
        if (!res.ok) {
          throw new Error(parseApiError(await res.text(), res.status));
        }
        return res.json() as Promise<BiBudgetImportResult>;
      },
      exportReport: async (
        c: ApiConfig,
        opts: {
          format: 'pdf' | 'xlsx';
          fiscalYear: number;
          locale: string;
          scenario?: string;
          reportingCurrency?: string;
        },
      ) => {
        const params = new URLSearchParams({
          format: opts.format,
          fiscal_year: String(opts.fiscalYear),
          locale: opts.locale.split('-')[0] || 'en',
        });
        if (opts.scenario) params.set('scenario', opts.scenario);
        if (opts.reportingCurrency) params.set('reporting_currency', opts.reportingCurrency);
        const res = await fetch(`${apiBase(c)}/api/v1/bi/budgets/export?${params}`, {
          method: 'GET',
          headers: buildRunnerHeaders(c),
          credentials: 'include',
        });
        if (!res.ok) {
          throw new Error(parseApiError(await res.text(), res.status));
        }
        const blob = await res.blob();
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `butce-raporu-${opts.fiscalYear}.${opts.format === 'xlsx' ? 'xlsx' : 'pdf'}`;
        a.click();
        URL.revokeObjectURL(a.href);
      },
      narrative: (
        c: ApiConfig,
        fiscalYear: number,
        locale: string,
        opts?: { scenario?: string; reportingCurrency?: string },
      ) => {
        const params = new URLSearchParams({
          fiscal_year: String(fiscalYear),
          locale: locale.split('-')[0] || 'en',
        });
        if (opts?.scenario) params.set('scenario', opts.scenario);
        if (opts?.reportingCurrency) params.set('reporting_currency', opts.reportingCurrency);
        return request<{
          text: string;
          watch_count: number;
          over_count: number;
          source: string;
          scenario?: string;
          fiscal_year?: number;
          totals?: {
            allocated?: number | null;
            actual?: number | null;
            remaining?: number | null;
            count?: number;
          };
          top?: Array<{
            id?: string;
            name?: string;
            used_pct?: number | null;
            health?: string | null;
          }>;
        }>(c, `/api/v1/bi/budgets/narrative?${params}`);
      },
      cloneYear: (
        c: ApiConfig,
        body: { from_year: number; to_year: number; copy_actuals_sql?: boolean; scenario?: string },
      ) =>
        request<{ created: number; skipped: number; errors: unknown[]; scenario?: string | null }>(
          c,
          '/api/v1/bi/budgets/clone-year',
          {
            method: 'POST',
            body: JSON.stringify(body),
          },
        ),
      createAlert: (
        c: ApiConfig,
        id: string,
        body?: { threshold_pct?: number; condition?: string; recipient?: string },
      ) =>
        request<Record<string, unknown>>(c, `/api/v1/bi/budgets/${id}/create-alert`, {
          method: 'POST',
          body: JSON.stringify(body || {}),
        }),
    },
    shares: {
      list: (c: ApiConfig) => request<{ shares: BiShareLink[] }>(c, '/api/v1/bi/shares'),
      create: (
        c: ApiConfig,
        body: { resource_type: string; resource_id: string; ttl_hours?: number | null; password?: string },
      ) => request<BiShareLink>(c, '/api/v1/bi/shares', { method: 'POST', body: JSON.stringify(body) }),
      delete: (c: ApiConfig, token: string) =>
        request<void>(c, `/api/v1/bi/shares/${token}`, { method: 'DELETE' }),
      views: (c: ApiConfig, token: string) =>
        request<{ token: string; view_count: number; views: Array<{ at: string; ip?: string; user_agent?: string }> }>(
          c,
          `/api/v1/bi/shares/${token}/views`,
        ),
    },
    audit: (c: ApiConfig, limit = 100, action?: string) => {
      const q = new URLSearchParams({ limit: String(limit) });
      if (action) q.set('action', action);
      return request<{ entries: unknown[] }>(c, `/api/v1/bi/audit?${q}`);
    },
    publicShare: (baseUrl: string, token: string, opts?: { live?: boolean }) => {
      const q = opts?.live ? '?live=1' : '';
      return fetch(`${baseUrl.replace(/\/$/, '')}/api/v1/bi/public/${token}${q}`).then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      });
    },
    unlockPublicShare: (baseUrl: string, token: string, password: string, opts?: { live?: boolean }) =>
      fetch(`${baseUrl.replace(/\/$/, '')}/api/v1/bi/public/${token}/unlock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password, live: Boolean(opts?.live) }),
      }).then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      }),
    reports: (c: ApiConfig) => request<{ reports: BiReport[] }>(c, '/api/v1/bi/reports'),
    getReport: (c: ApiConfig, id: string) => request<BiReport>(c, `/api/v1/bi/reports/${id}`),
    refreshReport: (c: ApiConfig, id: string) =>
      request<BiReport>(c, `/api/v1/bi/reports/${id}/refresh`, { method: 'POST' }),
    deleteReport: (c: ApiConfig, id: string) =>
      request<void>(c, `/api/v1/bi/reports/${id}`, { method: 'DELETE' }),
    schedules: (c: ApiConfig) => request<{ schedules: BiSchedule[] }>(c, '/api/v1/bi/schedules'),
    updateSchedule: (c: ApiConfig, id: string, body: Partial<BiSchedule>) =>
      request<BiSchedule>(c, `/api/v1/bi/schedules/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
    deleteSchedule: (c: ApiConfig, id: string) =>
      request<void>(c, `/api/v1/bi/schedules/${id}`, { method: 'DELETE' }),
    settings: {
      get: (c: ApiConfig) => request<BiBrandingSettings>(c, '/api/v1/bi/settings'),
      save: (c: ApiConfig, body: Partial<BiBrandingSettings>) =>
        request<BiBrandingSettings>(c, '/api/v1/bi/settings', { method: 'PUT', body: JSON.stringify(body) }),
      uploadLogo: async (c: ApiConfig, file: File) => {
        const fd = new FormData();
        fd.append('file', file);
        const res = await fetch(`${apiBase(c)}/api/v1/bi/settings/logo`, {
          method: 'POST',
          headers: buildRunnerHeaders(c),
          body: fd,
          credentials: 'include',
        });
        if (!res.ok) {
          throw new Error(parseApiError(await res.text(), res.status));
        }
        return res.json() as Promise<BiBrandingSettings>;
      },
    },
    analytics: {
      status: (c: ApiConfig) =>
        request<{
          enabled: boolean;
          url?: string;
          health?: { ok: boolean; message?: string; dashboard_count?: number };
        }>(c, '/api/v1/bi/analytics/status'),
      dashboards: (c: ApiConfig) =>
        request<{
          dashboards: Array<{
            id: number;
            title?: string;
            chart_count?: number;
            changed_on?: string;
            changed_on_delta?: string;
          }>;
        }>(c, '/api/v1/bi/analytics/dashboards'),
      createDashboard: (c: ApiConfig, body?: { title?: string }) =>
        request<{
          id: number;
          title?: string;
          embed_uuid?: string;
          guest?: {
            token?: string;
            dashboard_id?: number;
            embed_uuid?: string;
            analytics_url?: string;
          };
        }>(c, '/api/v1/bi/analytics/dashboards', {
          method: 'POST',
          body: JSON.stringify({ title: body?.title || 'NanobaseAI Panel' }),
        }),
      charts: (c: ApiConfig) =>
        request<{ charts: Array<{ id: number; title?: string; viz_type?: string }> }>(c, '/api/v1/bi/analytics/charts'),
      sourceWidgets: (c: ApiConfig, datasourceId?: string) =>
        request<{
          datasource_id: string;
          widgets: import('@/api/types').BiWidget[];
          count: number;
          errors?: Array<{ id: string; message: string }>;
        }>(
          c,
          `/api/v1/bi/analytics/source-widgets${
            datasourceId ? `?datasource_id=${encodeURIComponent(datasourceId)}` : ''
          }`,
        ),
      datasets: (c: ApiConfig) =>
        request<{ datasets: Array<{ id: number; table_name?: string }> }>(c, '/api/v1/bi/analytics/datasets'),
      guestToken: (c: ApiConfig, dashboardId: number) =>
        request<{ token: string; dashboard_id: number; embed_uuid: string; analytics_url: string }>(
          c,
          `/api/v1/bi/analytics/guest-token/${dashboardId}`,
          { method: 'POST' },
        ),
      dashboardCharts: (c: ApiConfig, dashboardId: number) =>
        request<{ charts: Array<{ id: number; title?: string; viz_type?: string }> }>(
          c,
          `/api/v1/bi/analytics/dashboards/${dashboardId}/charts`,
        ),
      pin: (
        c: ApiConfig,
        dashboardId: number,
        body: {
          sql: string;
          title?: string;
          viz_type?: string;
          widgets?: Array<Record<string, unknown>>;
        },
      ) =>
        request<{
          action?: string;
          dashboard_id?: number;
          charts?: Array<{ id?: number; title?: string }>;
          guest?: {
            token?: string;
            dashboard_id?: number;
            embed_uuid?: string;
            analytics_url?: string;
          };
          embed_uuid?: string;
          count?: number;
        }>(c, `/api/v1/bi/analytics/dashboards/${dashboardId}/pin`, {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      removeChart: (c: ApiConfig, dashboardId: number, chartId: number) =>
        request<{ dashboard_id: number; chart_ids: number[]; embed_uuid?: string }>(
          c,
          `/api/v1/bi/analytics/dashboards/${dashboardId}/charts/${chartId}`,
          { method: 'DELETE' },
        ),
      reorderLayout: (c: ApiConfig, dashboardId: number, chartIds: number[]) =>
        request<{ dashboard_id: number; chart_ids: number[]; embed_uuid?: string }>(
          c,
          `/api/v1/bi/analytics/dashboards/${dashboardId}/layout`,
          {
            method: 'PUT',
            body: JSON.stringify({ chart_ids: chartIds }),
          },
        ),
    },
    reportExportUrl: (c: ApiConfig, id: string, format: 'pdf' | 'csv' | 'xlsx') =>
      `${apiBase(c)}/api/v1/bi/reports/${id}/export?format=${format}`,
    connection: {
      get: (c: ApiConfig) => request<BiConnectionProfile>(c, '/api/v1/bi/connection'),
      test: (c: ApiConfig, body: BiConnectionUpsert) =>
        request<{ ok: boolean; message?: string; dialect?: string }>(c, '/api/v1/bi/connection/test', {
          method: 'POST',
          body: JSON.stringify(body),
        }),
      save: (c: ApiConfig, body: BiConnectionUpsert) =>
        request<{ connection: BiConnectionProfile; test: Record<string, unknown> }>(c, '/api/v1/bi/connection', {
          method: 'PUT',
          body: JSON.stringify(body),
        }),
    },
    sources: {
      list: (c: ApiConfig) => request<BiSourcesList>(c, '/api/v1/bi/sources'),
      upsert: (c: ApiConfig, sourceId: string, body: BiConnectionUpsert, skipTest = false) =>
        request<{ source: BiConnectionProfile; test: Record<string, unknown> } & BiSourcesList>(
          c,
          `/api/v1/bi/sources/${encodeURIComponent(sourceId)}${skipTest ? '?skip_test=true' : ''}`,
          { method: 'PUT', body: JSON.stringify(body) },
        ),
      activate: (c: ApiConfig, sourceId: string) =>
        request<BiSourcesList>(c, `/api/v1/bi/sources/${encodeURIComponent(sourceId)}/activate`, {
          method: 'POST',
        }),
      delete: (c: ApiConfig, sourceId: string) =>
        request<{ ok: boolean }>(c, `/api/v1/bi/sources/${encodeURIComponent(sourceId)}`, {
          method: 'DELETE',
        }),
      test: (c: ApiConfig, sourceId: string) =>
        request<{
          success?: boolean;
          ok?: boolean;
          databaseType?: string;
          databaseVersion?: string;
          latencyMs?: number;
          message?: string;
          via?: string;
        }>(c, `/api/v1/bi/sources/${encodeURIComponent(sourceId)}/test`, {
          method: 'POST',
          body: '{}',
        }),
      scan: (c: ApiConfig, sourceId: string) =>
        request<{ scanId: string; status: string }>(
          c,
          `/api/v1/bi/sources/${encodeURIComponent(sourceId)}/scan`,
          { method: 'POST', body: '{}' },
        ),
    },
    schemaScans: {
      get: (c: ApiConfig, scanId: string) =>
        request<{
          scanId: string;
          status: string;
          datasourceId?: string;
          schemaCount?: number | null;
          tableCount?: number | null;
          columnCount?: number | null;
          relationshipCount?: number | null;
          indexedDocumentCount?: number | null;
          skippedDocumentCount?: number | null;
          error?: string | null;
          startedAt?: string | null;
          completedAt?: string | null;
        }>(c, `/api/v1/bi/schema-scans/${encodeURIComponent(scanId)}`),
    },
    queryFeedback: (
      c: ApiConfig,
      body: {
        question: string;
        rating: -1 | 0 | 1;
        sql?: string;
        session_id?: string;
        comment?: string;
        datasource_id?: string;
        promote_verified?: boolean;
      },
    ) =>
      request<{ ok?: boolean }>(c, '/api/v1/bi/query/feedback', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    download: async (c: ApiConfig, path: string, filename: string, sqlBody?: string) => {
      const url = `${apiBase(c)}${path}`;
      const headers: Record<string, string> = { Authorization: `Bearer ${c.apiKey}` };
      if (c.sessionToken) headers['X-Portal-Session'] = c.sessionToken;
      if (c.role) headers['X-Nanobase-Role'] = c.role;
      const init: RequestInit = { headers, method: sqlBody ? 'POST' : 'GET' };
      if (sqlBody) {
        headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify({ sql: sqlBody });
      }
      const resp = await fetch(url, init);
      if (!resp.ok) throw new Error(await resp.text());
      const blob = await resp.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    },
  };
  return bi;
}
