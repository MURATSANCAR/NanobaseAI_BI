import { t } from '@/i18n';
import { brandText } from '@/utils/brand';
import { readinessCheckLabel } from '@/utils/suiteReadinessUi';

/** Resolve a machine code from the API to a localized operator label. */
export function mapBackendLabel(
  namespace: string,
  code: string | null | undefined,
  fallback?: string,
): string {
  const raw = String(code ?? '').trim();
  if (!raw) return fallback ?? '';
  const candidates = [
    `${namespace}.${raw}`,
    `${namespace}.${raw.toLowerCase()}`,
    `${namespace}.${raw.toLowerCase().replace(/[^a-z0-9._-]+/g, '_')}`,
  ];
  for (const key of candidates) {
    const label = t(key);
    if (label !== key) return label;
  }
  return fallback ?? brandText(raw);
}

export function formatStatus(code: string | null | undefined): string {
  return mapBackendLabel('status', code, code ? brandText(code) : t('common.noData'));
}

export function formatAuditAction(action: string | null | undefined): string {
  return mapBackendLabel('enterprise.audit.action', action);
}

export function formatApprovalStage(stage: string | null | undefined): string {
  return mapBackendLabel('enterprise.approval.stage', stage);
}

export function formatResourceType(type: string | null | undefined): string {
  return mapBackendLabel('enterprise.resourceType', type);
}

export function formatFarmType(type: string | null | undefined): string {
  return mapBackendLabel('enterprise.farm', type);
}

export function formatAnalyticsTrend(trend: string | null | undefined): string {
  return mapBackendLabel('enterprise.analytics.trendValue', trend);
}

export function formatTdmSeedType(type: string | null | undefined): string {
  return mapBackendLabel('enterprise.tdm.seedType', type);
}

export function formatVaultProvider(provider: string | null | undefined): string {
  return mapBackendLabel('enterprise.vaultProvider', provider);
}

export function formatRegistryPriority(priority: string | null | undefined): string {
  const raw = String(priority ?? '').trim();
  if (!raw) return '';
  return mapBackendLabel('registry.priority', raw.toLowerCase());
}

export function formatBiCode(code: string | null | undefined): string {
  return mapBackendLabel('bi.code', code);
}

export function formatImportError(raw: string | null | undefined): string {
  const text = String(raw ?? '').trim();
  if (!text) return '';
  const code = text.includes(':') ? text.split(':').pop()!.trim() : text;
  return mapBackendLabel('analysis.importError', code, brandText(text));
}

export function formatEnvironmentVerifyError(error: string | null | undefined): string {
  const text = String(error ?? '').trim();
  if (!text) return t('environment.verifyFailed');
  if (text === 'web_base_url is not configured') {
    return t('environment.verifyError.webBaseUrlMissing');
  }
  return mapBackendLabel('environment.verifyError', text, brandText(text));
}

export function formatBackendErrorText(text: string | null | undefined): string {
  const raw = String(text ?? '').trim();
  if (!raw) return '';
  const byMessage = API_ERROR_MESSAGES[raw];
  if (byMessage) return t(byMessage);
  const fromCode = localizeMachineCode(raw);
  if (fromCode) return fromCode;
  const patternKey = matchEnglishBackendPattern(raw);
  if (patternKey) return t(patternKey);
  if (raw.startsWith('upstream_fetch_failed')) return t('analysis.importError.upstream_fetch_failed');
  if (raw.startsWith('branch_checkout_failed')) return t('api.error.branch_checkout_failed');
  return brandText(raw);
}

const API_ERROR_CODES: Record<string, string> = {
  suite_readiness_blocked: 'error.suiteReadinessBlocked',
  reconciliation_required: 'error.reconciliationRequired',
  development_rejected: 'error.developmentRejected',
  decision_required: 'error.decisionRequired',
  github_connection_failed: 'api.message.github_connection_failed',
  github_token_invalid: 'api.message.github_token_invalid',
  github_token_missing: 'api.message.github_token_missing',
  quality_gate_failed: 'api.error.quality_gate_failed',
  tdm_suite_lock_held: 'error.tdmSuiteLockHeld',
  parity_blocked: 'error.parityBlocked',
  clone_url_required: 'api.error.clone_url_required',
  invalid_request: 'api.error.invalid_request',
  suite_login_failed: 'error.suiteLoginFailed',
  suite_not_login_blocked: 'api.error.suite_not_login_blocked',
  discovery_login_failed: 'api.error.discovery_login_failed',
  auth_config_incomplete: 'api.error.auth_config_incomplete',
  suite_login_resumed: 'api.message.suite_login_resumed',
  analytics_not_configured: 'api.error.analytics_not_configured',
  analytics_failed: 'api.error.analytics_failed',
  analytics_guest_token_failed: 'api.error.analytics_guest_token_failed',
  analytics_list_charts_failed: 'api.error.analytics_list_charts_failed',
  analytics_pin_failed: 'api.error.analytics_pin_failed',
  analytics_remove_chart_failed: 'api.error.analytics_remove_chart_failed',
  analytics_reorder_failed: 'api.error.analytics_reorder_failed',
  analytics_create_dashboard_failed: 'api.error.analytics_create_dashboard_failed',
  dashboard_title_exists: 'api.error.dashboard_title_exists',
  'NanobaseAI analytics engine not configured': 'api.error.analytics_not_configured',
  schema_required: 'api.error.schema_required',
  anomaly_not_found: 'api.error.anomaly_not_found',
  evidence_sql_required: 'api.error.evidence_sql_required',
  metric_not_found: 'api.error.metric_not_found',
  share_disabled: 'api.error.share_disabled',
  share_artifact_blocked_sensitivity: 'api.error.share_artifact_blocked_sensitivity',
  artifact_not_found: 'api.error.artifact_not_found',
  domain_pack_not_found: 'api.error.domain_pack_not_found',
  glossary_suggest_failed: 'api.error.glossary_suggest_failed',
  scenario_metric_not_certified: 'api.error.scenario_metric_not_certified',
  scenario_driver_invalid: 'api.error.scenario_driver_invalid',
  embed_origin_denied: 'api.error.embed_origin_denied',
  embed_disabled: 'api.error.embed_disabled',
  golden_sql_failed: 'api.error.golden_sql_failed',
  comment_body_required: 'api.error.comment_body_required',
  comment_not_found: 'api.error.comment_not_found',
  text2sql_disabled: 'api.error.text2sql_disabled',
  arctic_unavailable: 'api.error.arctic_unavailable',
  sql_invalid: 'api.error.sql_invalid',
  explain_failed: 'api.error.explain_failed',
  brief_invalid: 'api.error.brief_invalid',
  brief_allowlist: 'api.error.brief_allowlist',
  brief_forbidden_key: 'api.error.brief_forbidden_key',
  brief_replan_required: 'api.error.brief_replan_required',
  join_plan_impossible: 'api.error.join_plan_impossible',
  planner_unavailable: 'api.error.planner_unavailable',
  ratio_requires_derived_metric: 'api.error.ratio_requires_derived_metric',
  derived_measure_step_missing: 'api.error.derived_measure_step_missing',
  atomic_measure_binding_missing: 'api.error.atomic_measure_binding_missing',
  grain_incompatible: 'api.error.grain_incompatible',
  dimension_resolution_missing: 'api.error.dimension_resolution_missing',
  dimension_not_in_ontology: 'api.error.dimension_not_in_ontology',
  dimension_not_in_binding: 'api.error.dimension_not_in_binding',
  business_graph_path_missing: 'api.error.business_graph_path_missing',
  template_does_not_allow_dimension: 'api.error.template_does_not_allow_dimension',
  compiler_grain_not_applied: 'api.error.compiler_grain_not_applied',
  semantic_underfit: 'api.error.semantic_underfit',
  concept_definition_missing: 'api.error.concept_definition_missing',
  forbidden_extra_tables: 'api.error.forbidden_extra_tables',
  bi_share_password_invalid: 'api.error.bi_share_password_invalid',
  bi_logo_invalid_type: 'api.error.bi_logo_invalid_type',
  bi_logo_too_large: 'api.error.bi_logo_too_large',
  bi_logo_not_found: 'api.error.bi_logo_not_found',
  public_share_disabled: 'api.error.public_share_disabled',
  demo_seed_disabled: 'api.error.demo_seed_disabled',
  clarification_required: 'api.error.clarification_required',
  ssrf_blocked: 'api.error.ssrf_blocked',
  superset_tenant_denied: 'api.error.superset_tenant_denied',
  tenant_id_required: 'api.error.tenant_id_required',
  worker_token_required: 'api.error.worker_token_required',
  lease_not_found: 'api.error.lease_not_found',
  llm_not_busy: 'api.error.llm_not_busy',
  llm_cancel_failed: 'api.error.llm_cancel_failed',
  qa_llm_disabled: 'api.error.qa_llm_disabled',
  llm_cancel_slot_only: 'api.message.llm_cancel_slot_only',
  llm_cancel_stopping: 'api.message.llm_cancel_stopping',
  llm_cancelled: 'api.message.llm_cancelled',
  bi_table_not_allowed: 'api.error.bi_table_not_allowed',
  bi_department_unknown: 'api.error.bi_department_unknown',
  department_board_failed: 'api.error.department_board_failed',
  schema_db_auth_failed: 'api.error.schema_db_auth_failed',
  schema_introspect_failed: 'api.error.schema_introspect_failed',
  schema_refresh_failed: 'api.error.schema_refresh_failed',
  schema_db_not_configured: 'api.error.schema_db_not_configured',
  template_title_required: 'api.error.template_title_required',
  template_prompt_required: 'api.error.template_prompt_required',
  template_not_found: 'api.error.template_not_found',
  template_not_custom: 'api.error.template_not_custom',
  bi_starter_templates_empty: 'api.error.bi_starter_templates_empty',
  no_widgets_for_department: 'api.error.no_widgets_for_department',
  schema_empty: 'api.error.schema_empty',
  bi_anomaly_status_invalid: 'api.error.bi_anomaly_status_invalid',
  bi_meeting_recipients_required: 'api.error.bi_meeting_recipients_required',
  bi_source_admin_required: 'api.error.bi_source_admin_required',
  bi_source_id_invalid: 'api.error.bi_source_id_invalid',
  bi_source_not_found: 'api.error.bi_source_not_found',
  bi_supabase_credentials_required: 'api.error.bi_supabase_credentials_required',
  bi_sqlite_path_required: 'api.error.bi_sqlite_path_required',
  bi_connection_incomplete: 'api.error.bi_connection_incomplete',
  bi_connection_test_failed: 'api.error.bi_connection_test_failed',
  bi_budget_kind_invalid: 'api.error.bi_budget_kind_invalid',
  bi_budget_status_invalid: 'api.error.bi_budget_status_invalid',
  bi_budget_name_required: 'api.error.bi_budget_name_required',
  bi_budget_allocated_invalid: 'api.error.bi_budget_allocated_invalid',
  bi_budget_sql_required: 'api.error.bi_budget_sql_required',
  bi_budget_actual_empty: 'api.error.bi_budget_actual_empty',
  bi_budget_not_found: 'api.error.bi_budget_not_found',
  bi_budget_import_empty: 'api.error.bi_budget_import_empty',
  bi_budget_import_invalid_file: 'api.error.bi_budget_import_invalid_file',
  bi_budget_import_row_invalid: 'api.error.bi_budget_import_row_invalid',
  bi_budget_locked: 'api.error.bi_budget_locked',
  bi_budget_export_failed: 'api.error.bi_budget_export_failed',
  bi_budget_export_format_invalid: 'api.error.bi_budget_export_format_invalid',
  bi_budget_clone_same_year: 'api.error.bi_budget_clone_same_year',
  bi_budget_clone_year_invalid: 'api.error.bi_budget_clone_year_invalid',
  bi_budget_clone_row_failed: 'api.error.bi_budget_clone_row_failed',
  bi_budget_sql_invalid: 'api.error.bi_budget_sql_invalid',
  bi_budget_breakdown_sql_required: 'api.error.bi_budget_breakdown_sql_required',
  bi_fx_rate_invalid: 'api.error.bi_fx_rate_invalid',
  bi_commitment_amount_invalid: 'api.error.bi_commitment_amount_invalid',
  bi_commitment_not_found: 'api.error.bi_commitment_not_found',
  bi_budget_transfer_amount_invalid: 'api.error.bi_budget_transfer_amount_invalid',
  bi_budget_transfer_same: 'api.error.bi_budget_transfer_same',
  bi_budget_transfer_insufficient: 'api.error.bi_budget_transfer_insufficient',
  bi_budget_transfer_requires_postgres: 'api.error.bi_budget_transfer_requires_postgres',
  bi_budget_match_invalid_ident: 'api.error.bi_budget_match_invalid_ident',
  bi_budget_match_no_plan_table: 'api.message.bi_budget_match_no_plan_table',
  bi_budget_match_no_spend_table: 'api.message.bi_budget_match_no_spend_table',
  bi_budget_match_plan_query_failed: 'api.message.bi_budget_match_plan_query_failed',
  bi_budget_match_no_common_key: 'api.message.bi_budget_match_no_common_key',
  bi_cost_center_code_required: 'api.error.bi_cost_center_code_required',
  bi_cost_center_name_required: 'api.error.bi_cost_center_name_required',
  bi_cost_center_parent_invalid: 'api.error.bi_cost_center_parent_invalid',
  bi_cost_center_cycle: 'api.error.bi_cost_center_cycle',
  bi_cost_center_code_exists: 'api.error.bi_cost_center_code_exists',
  bi_cost_center_has_children: 'api.error.bi_cost_center_has_children',
  bi_cost_center_not_found: 'api.error.bi_cost_center_not_found',
  share_view_limit: 'api.error.share_view_limit',
  unsupported_export_format: 'api.error.unsupported_export_format',
  bad_gateway: 'api.error.bad_gateway',
  not_found: 'api.error.not_found',
  suite_not_found: 'api.error.suite_not_found',
  repo_not_found: 'api.error.repo_not_found',
  job_not_found: 'api.error.job_not_found',
  event_not_found: 'api.error.event_not_found',
  dlq_not_found: 'api.error.dlq_not_found',
  vault_secret_not_found: 'api.message.vault_secret_not_found',
  reconciliation_not_found: 'api.error.reconciliation_not_found',
  demo_catalog_not_found: 'api.error.demo_catalog_not_found',
  developer_smoke_only: 'api.error.developer_smoke_only',
  gate_waiver_admin_only: 'api.error.gate_waiver_admin_only',
  role_access_denied: 'api.error.role_access_denied',
  suite_not_resumable: 'api.message.suite_not_resumable',
  suite_body_snapshot_not_resumable: 'api.message.suite_snapshot_missing',
  suite_timeout: 'api.message.suite_timeout',
  suite_report_not_ready: 'api.message.suite_report_not_ready',
  orchestration_resume_started: 'api.message.orchestration_resume_started',
  suite_cancelled: 'api.message.suite_cancelled',
  healing_auto_commit_blocked_in_prod: 'api.error.healing_auto_commit_blocked_in_prod',
  analysis_no_versions: 'api.error.analysis_no_versions',
  analysis_version_not_found: 'api.error.analysis_version_not_found',
  analysis_diff_invalid_range: 'api.error.analysis_diff_invalid_range',
  base_url_required: 'api.message.base_url_required',
  failure_not_found: 'api.error.failure_not_found',
  invalid_failure_status: 'api.error.invalid_failure_status',
  note_text_required: 'api.error.note_text_required',
  k6_not_installed: 'api.error.k6_not_installed',
  zap_not_installed: 'api.error.zap_not_installed',
  analysis_not_cached: 'api.message.analysis_not_cached',
  analysis_stale_missing_base_url: 'api.message.analysis_stale_missing_base_url',
  project_id_required: 'api.message.project_id_required',
  project_id_entity_key_required: 'api.message.project_id_entity_key_required',
  unknown_project: 'api.error.unknown_project',
  screen_api_link_fields_required: 'api.message.screen_api_link_fields_required',
  analysis_document_missing_after_reconcile: 'api.message.analysis_document_missing_gate',
  portal_runtime_config_unavailable: 'api.error.portal_runtime_config_unavailable',
  runner_api_key_not_configured: 'api.error.runner_api_key_not_configured',
  invalid_api_key: 'auth.invalidApiKey',
  'DOC-001': 'api.error.DOC-001',
  'DOC-002': 'api.error.DOC-002',
  'DOC-003': 'api.error.DOC-003',
  'DOC-005': 'api.error.DOC-005',
  'DOC-006': 'api.error.DOC-006',
  'RET-001': 'api.error.RET-001',
  'AI-005': 'api.error.AI-005',
  documents_not_ready: 'api.error.documents_not_ready',
  format_md_only: 'api.error.format_md_only',
  page_preview_failed: 'api.error.page_preview_failed',
  unauthorized: 'api.error.unauthorized',
  portal_session_required: 'api.message.portal_session_required',
  module_access_denied: 'api.error.module_access_denied',
  api_key_required: 'api.error.api_key_required',
  tenant_access_denied: 'api.error.tenant_access_denied',
  project_access_denied: 'api.error.project_access_denied',
  user_admin_required: 'api.error.user_admin_required',
  suite_gate_failed: 'api.error.suite_gate_failed',
  contracts_module_required: 'api.error.contracts_module_required',
  tenant_required: 'api.error.tenant_required',
  tenant_not_found: 'api.error.tenant_not_found',
  portal_auth_misconfigured: 'api.error.portal_auth_misconfigured',
  project_not_found: 'api.error.project_not_found',
  document_not_found: 'api.error.document_not_found',
  requirements_must_be_list: 'api.error.requirements_must_be_list',
  slack_webhook_not_configured: 'api.message.slack_webhook_missing',
  test_case_not_found: 'api.message.test_case_not_found',
  entity_not_found: 'api.message.entity_not_found',
  sync_failed: 'api.message.sync_failed',
  db_sync_ok: 'api.message.db_sync_ok',
  db_sync_partial: 'api.message.db_sync_partial',
  db_sync_all_failed: 'api.message.db_sync_all_failed',
  db_sync_no_projects: 'api.message.db_sync_no_projects',
  db_sync_auto_disabled: 'api.message.db_sync_auto_disabled',
  validation_matrix_unavailable: 'api.message.validation_matrix_unavailable',
  test_matrix_unavailable: 'api.message.test_matrix_unavailable',
  api_matrix_unavailable: 'api.message.api_matrix_unavailable',
  api_matrix_high_orphan_ratio: 'api.message.api_matrix_high_orphan_ratio',
  artifact_export_blocked: 'api.message.artifact_export_blocked',
  mermaid_cli_unavailable: 'api.message.mermaid_cli_unavailable',
  module_spec_missing_apis: 'api.message.module_spec_missing_apis',
  module_spec_quality_low: 'api.message.module_spec_quality_low',
  module_spec_release_not_ready: 'api.message.module_spec_release_not_ready',
  module_spec_boilerplate: 'api.message.module_spec_boilerplate',
  module_spec_boilerplate_workflow: 'api.message.module_spec_boilerplate_workflow',
  module_spec_boilerplate_purpose: 'api.message.module_spec_boilerplate_purpose',
  module_spec_boilerplate_rules: 'api.message.module_spec_boilerplate_rules',
  module_spec_empty_error_table: 'api.message.module_spec_empty_error_table',
  module_spec_wrong_locale: 'api.message.module_spec_wrong_locale',
  business_analysis_release_not_ready: 'api.message.business_analysis_release_not_ready',
  ba_ac_tbd: 'api.message.ba_ac_tbd',
  document_stale: 'api.message.document_stale',
  graph_document_fp_mismatch: 'api.message.graph_document_fp_mismatch',
  entity_scenario_parity_gap: 'api.message.entity_scenario_parity_gap',
  spec_drift: 'api.message.spec_drift',
  architecture_unavailable: 'api.message.architecture_unavailable',
  process_unavailable: 'api.message.process_unavailable',
  permissions_unavailable: 'api.message.permissions_unavailable',
  notifications_unavailable: 'api.message.notifications_unavailable',
  data_dictionary_unavailable: 'api.message.data_dictionary_unavailable',
  module_spec_seed_too_short: 'api.message.module_spec_seed_too_short',
  invalid_base64: 'api.message.invalid_base64',
  module_seed_unmapped: 'api.message.module_seed_unmapped',
  stub_cases_not_approvable: 'api.message.stub_cases_not_approvable',
  jira_not_configured: 'api.message.jira_not_configured',
  jira_connection_failed: 'api.message.jira_connection_failed',
  jira_api_error: 'api.message.jira_api_error',
  jira_bug_failed: 'api.message.jira_bug_failed',
  jira_issue_create_failed: 'api.message.jira_issue_create_failed',
  xray_not_configured: 'api.message.xray_not_configured',
  xray_plan_key_required: 'api.message.xray_plan_key_required',
  xray_import_failed: 'api.message.xray_import_failed',
  suite_id_missing: 'api.message.suite_id_missing',
  job_id_missing: 'api.message.job_id_missing',
  vault_configured: 'api.message.vault_configured',
  vault_dev_only: 'api.message.vault_dev_only',
  vault_unknown: 'api.message.vault_unknown',
  vault_write_local_only: 'api.message.vault_write_local_only',
  vault_secret_saved: 'api.message.vault_secret_saved',
  vault_remote_write_failed: 'api.message.vault_remote_write_failed',
  vault_secret_deleted: 'api.message.vault_secret_deleted',
  vault_remote_delete_failed: 'api.message.vault_remote_delete_failed',
  quarantine_ok: 'api.message.quarantine_ok',
};

/** Legacy keys kept for backward compatibility with older portal copy. */
const API_MESSAGE_ALIASES: Record<string, string> = {
  base_url_required: 'repos.analysisDocNeedBaseUrl',
  analysis_not_cached: 'repos.analysisDocNotCached',
};

const API_ERROR_MESSAGES: Record<string, string> = {
  'Missing Bearer token': 'error.missingBearer',
  'Invalid API key': 'auth.invalidApiKey',
  'Invalid username or password': 'auth.loginFailed',
  'Suite not found': 'api.error.suite_not_found',
  'Repo not found': 'api.error.repo_not_found',
  'Repo not found — register first via POST /api/v1/repos': 'api.error.repo_not_found',
  'Reconciliation report not found': 'api.error.reconciliation_not_found',
  'No analysis document versions stored for this source': 'api.error.analysis_versions_missing',
  'DLQ entry not found': 'api.error.dlq_not_found',
  'event not found': 'api.error.event_not_found',
  'job not found': 'api.error.job_not_found',
  'Job not found': 'api.error.job_not_found',
  'web_base_url is not configured': 'environment.verifyError.webBaseUrlMissing',
  'project_id and repo_id required': 'api.error.project_repo_required',
  'project_id required': 'api.message.project_id_required',
  'Suite is not resumable': 'api.message.suite_not_resumable',
  'Suite body snapshot missing or not resumable': 'api.message.suite_snapshot_missing',
  'Suite did not complete within timeout': 'api.message.suite_timeout',
  'Analysis document not available — run code scan first': 'api.message.analysis_document_unavailable',
  pdf_export_failed: 'api.message.pdf_export_failed',
  module_spec_unavailable: 'api.message.module_spec_unavailable',
  module_not_found: 'api.message.module_not_found',
  module_spec_seed_invalid: 'api.message.module_spec_seed_invalid',
  module_spec_seed_no_numbered_sections: 'api.message.module_spec_seed_no_numbered_sections',
  module_spec_seed_too_short: 'api.message.module_spec_seed_too_short',
  invalid_base64: 'api.message.invalid_base64',
  module_seed_unmapped: 'api.message.module_seed_unmapped',
  validation_matrix_unavailable: 'api.message.validation_matrix_unavailable',
  test_matrix_unavailable: 'api.message.test_matrix_unavailable',
  api_matrix_unavailable: 'api.message.api_matrix_unavailable',
  api_matrix_high_orphan_ratio: 'api.message.api_matrix_high_orphan_ratio',
  artifact_export_blocked: 'api.message.artifact_export_blocked',
  mermaid_cli_unavailable: 'api.message.mermaid_cli_unavailable',
  module_spec_missing_apis: 'api.message.module_spec_missing_apis',
  module_spec_quality_low: 'api.message.module_spec_quality_low',
  module_spec_release_not_ready: 'api.message.module_spec_release_not_ready',
  module_spec_boilerplate: 'api.message.module_spec_boilerplate',
  module_spec_boilerplate_workflow: 'api.message.module_spec_boilerplate_workflow',
  module_spec_boilerplate_purpose: 'api.message.module_spec_boilerplate_purpose',
  module_spec_boilerplate_rules: 'api.message.module_spec_boilerplate_rules',
  module_spec_empty_error_table: 'api.message.module_spec_empty_error_table',
  module_spec_wrong_locale: 'api.message.module_spec_wrong_locale',
  business_analysis_release_not_ready: 'api.message.business_analysis_release_not_ready',
  ba_ac_tbd: 'api.message.ba_ac_tbd',
  document_stale: 'api.message.document_stale',
  graph_document_fp_mismatch: 'api.message.graph_document_fp_mismatch',
  entity_scenario_parity_gap: 'api.message.entity_scenario_parity_gap',
  spec_drift: 'api.message.spec_drift',
  architecture_unavailable: 'api.message.architecture_unavailable',
  process_unavailable: 'api.message.process_unavailable',
  permissions_unavailable: 'api.message.permissions_unavailable',
  notifications_unavailable: 'api.message.notifications_unavailable',
  data_dictionary_unavailable: 'api.message.data_dictionary_unavailable',
  analysis_enrichment_pending: 'api.message.analysis_enrichment_pending',
  'Knowledge scan job not found': 'api.message.knowledge_scan_not_found',
  'Crawl job not found': 'api.message.crawl_job_not_found',
  'No cached schema — run POST /db-schema/refresh first': 'api.message.schema_cache_missing',
  'No schema reconciliation report': 'api.message.schema_reconciliation_missing',
  'Portal session required': 'api.message.portal_session_required',
  'User administration permission required': 'api.message.portal_admin_required',
  'Slack webhook URL not configured': 'api.message.slack_webhook_missing',
  'Provide flow_yaml, spec_path, or generate_from_prompt': 'api.message.flow_missing',
  'Provide flow_yaml or user_story': 'api.message.flow_missing',
  'Artifact not found': 'api.message.artifact_not_found',
  'Job artifacts not found': 'api.message.job_artifacts_missing',
  'Flow not found': 'api.message.flow_file_missing',
  'Flow file missing': 'api.message.flow_file_missing',
  'Log not found': 'api.message.log_not_found',
  'Log file missing': 'api.message.log_not_found',
  'Test case not found': 'api.message.test_case_not_found',
  'no active sign-off for project/repo': 'api.message.signoff_not_found',
  'no visual diff': 'api.message.no_visual_diff',
  'analysis_document missing after reconciliation gate': 'api.message.analysis_document_missing_gate',
  'Resolve readiness blockers before starting the suite.': 'api.message.resolve_readiness_blockers',
  'Spec–code reconciliation required before starting tests from project.': 'api.message.reconciliation_required_before_suite',
  'Orchestration interrupted — partial progress saved. Resume the suite or re-run with force_regenerate=false.':
    'api.message.orchestration_interrupted_partial',
  'Orchestration interrupted (stale suite recovered on API startup). Re-run the suite from Run pipeline.':
    'api.message.orchestration_interrupted_empty',
  'Orchestration resume started': 'api.message.orchestration_resume_started',
  'Suite cancelled': 'api.message.suite_cancelled',
  'Another suite holds test data lock for this project': 'error.tdmSuiteLockHeld',
  'User analysis differs from code baseline. Review feedback and submit reconcile_decision.':
    'error.reconciliationRequired',
  'Test generation blocked. Share the following fixes with developers.': 'error.developmentRejected',
  'Set reconcile_decision to continue_test or reject_development': 'error.decisionRequired',
  'Runner API key not configured on server': 'api.message.runner_key_missing',
  'Portal runtime config unavailable': 'api.message.portal_config_missing',
  'requirements must be a list': 'api.message.requirements_invalid',
  'source_id and scenario_id required for baseline': 'api.message.source_scenario_required',
  'value required': 'api.message.value_required',
};

const ENGLISH_BACKEND_PATTERNS: Array<{ test: RegExp; key: string }> = [
  { test: /another suite holds test data lock/i, key: 'error.tdmSuiteLockHeld' },
  { test: /coverage parity blocked/i, key: 'error.parityBlocked' },
  { test: /spec.?code reconciliation required/i, key: 'error.reconciliationRequired' },
  { test: /reconcile_decision/i, key: 'error.decisionRequired' },
  { test: /test generation blocked/i, key: 'error.developmentRejected' },
  { test: /user analysis differs from code baseline/i, key: 'error.reconciliationRequired' },
  { test: /resolve readiness blockers/i, key: 'api.message.resolve_readiness_blockers' },
  { test: /suite_readiness_blocked/i, key: 'error.suiteReadinessBlocked' },
];

function matchEnglishBackendPattern(text: string): string | null {
  for (const { test, key } of ENGLISH_BACKEND_PATTERNS) {
    if (test.test(text)) return key;
  }
  return null;
}

function localizeMachineCode(code: string): string | null {
  const raw = String(code ?? '').trim();
  if (!raw) return null;
  if (API_MESSAGE_ALIASES[raw]) return t(API_MESSAGE_ALIASES[raw]);
  if (API_ERROR_CODES[raw]) return t(API_ERROR_CODES[raw]);
  if (API_ERROR_MESSAGES[raw]) return t(API_ERROR_MESSAGES[raw]);
  if (/^[a-z][a-z0-9_]*$/.test(raw)) {
    const fromApi = formatApiMessage(raw);
    if (fromApi !== raw && !fromApi.startsWith('api.message.') && !fromApi.startsWith('api.error.')) {
      return fromApi;
    }
    const msgKey = `api.message.${raw}`;
    const msgLabel = t(msgKey);
    if (msgLabel !== msgKey) return msgLabel;
    const errKey = `api.error.${raw}`;
    const errLabel = t(errKey);
    if (errLabel !== errKey) return errLabel;
  }
  return null;
}

function localizeTdmLockMessage(detailObj: Record<string, unknown> | null): string {
  const holder = detailObj?.holder_suite_id;
  if (holder) {
    return t('error.tdmSuiteLockHeldWithHolder', { holder: String(holder) });
  }
  return t('error.tdmSuiteLockHeld');
}

/** Map backend `message` machine codes to localized operator text. */
export function formatApiMessage(code: string | null | undefined): string {
  const raw = String(code ?? '').trim();
  if (!raw) return '';
  if (API_MESSAGE_ALIASES[raw]) return t(API_MESSAGE_ALIASES[raw]);
  const key = `api.message.${raw}`;
  const label = t(key);
  if (label !== key) return label;
  if (API_ERROR_CODES[raw]) return t(API_ERROR_CODES[raw]);
  if (API_ERROR_MESSAGES[raw]) return t(API_ERROR_MESSAGES[raw]);
  return formatBackendErrorText(raw);
}

/** Any user-visible backend string → localized text in the active portal locale. */
export function localizeUserMessage(text: string | null | undefined): string {
  const raw = String(text ?? '').trim();
  if (!raw) return '';
  const fromCode = localizeMachineCode(raw);
  if (fromCode) return fromCode;
  if (raw.startsWith('upstream_fetch_failed')) return t('analysis.importError.upstream_fetch_failed');
  if (raw.startsWith('branch_checkout_failed')) return t('api.error.branch_checkout_failed');
  if (/^(error|api)\.[a-z0-9_.]+$/.test(raw)) {
    const label = t(raw);
    if (label !== raw) return label;
  }
  return formatBackendErrorText(raw);
}

/** Parse runner API error payloads into localized operator messages. */
export function parseApiErrorBody(text: string, status: number): string {
  try {
    const data = JSON.parse(text) as { detail?: string | Record<string, unknown> };
    const detailRaw = data.detail;
    const detailObj =
      detailRaw && typeof detailRaw === 'object' ? (detailRaw as Record<string, unknown>) : null;
    const detailStr =
      typeof detailRaw === 'string'
        ? detailRaw
        : detailObj
          ? String(detailObj.message || detailObj.status || detailObj.code || '')
          : '';
    const detailCode = detailObj ? String(detailObj.code || '') : '';
    const detailStatus = detailObj ? String(detailObj.status || '') : '';

    if (detailCode === 'tdm_suite_lock_held') {
      return localizeTdmLockMessage(detailObj);
    }
    if (detailCode && API_ERROR_CODES[detailCode]) {
      return t(API_ERROR_CODES[detailCode]);
    }
    if (typeof detailRaw === 'string') {
      const plain = detailRaw.trim();
      const fromPlain = localizeMachineCode(plain);
      if (fromPlain) return fromPlain;
      const patternKey = matchEnglishBackendPattern(plain);
      if (patternKey) return t(patternKey);
    }
    if (detailStatus && API_ERROR_CODES[detailStatus]) {
      const base = t(API_ERROR_CODES[detailStatus]);
      if (detailStatus === 'suite_readiness_blocked') {
        const blockers = (detailObj?.blockers as string[] | undefined) || [];
        if (blockers.length) {
          const labels = blockers.slice(0, 3).map((code) => readinessCheckLabel(code, false)).join(', ');
          return `${base} (${labels})`;
        }
      }
      return base;
    }

    if (detailStr && API_ERROR_MESSAGES[detailStr]) {
      return t(API_ERROR_MESSAGES[detailStr]);
    }

    if (detailStatus === 'suite_readiness_blocked' || detailStr.includes('suite_readiness_blocked')) {
      const blockers = (detailObj?.blockers as string[] | undefined) || [];
      if (blockers.length) {
        const labels = blockers.slice(0, 3).map((code) => readinessCheckLabel(code, false)).join(', ');
        return `${t('error.suiteReadinessBlocked')} (${labels})`;
      }
      return t('error.suiteReadinessBlocked');
    }
    if (detailStatus === 'reconciliation_required' || detailStr.includes('reconciliation_required')) {
      return t('error.reconciliationRequired');
    }
    if (detailStatus === 'development_rejected' || detailStr.includes('development_rejected')) {
      return t('error.developmentRejected');
    }
    if (detailStatus === 'decision_required' || detailStr.includes('decision_required')) {
      return t('error.decisionRequired');
    }
    if (detailStr.includes('tdm_suite_lock') || /test data lock/i.test(detailStr)) {
      return localizeTdmLockMessage(detailObj);
    }
    if (detailStr.includes('Coverage parity blocked')) {
      return t('error.parityBlocked');
    }
    if (detailStr) return localizeUserMessage(detailStr);
  } catch {
    /* plain text */
  }

  if (status === 401) return t('error.unauthorized');
  if (status === 403) return t('error.forbidden');
  if (status === 404) return t('api.error.not_found');
  if (status === 409) return t('error.suiteConflict');
  if (status === 422) {
    try {
      const data = JSON.parse(text) as { detail?: { status?: string } | string };
      if (typeof data.detail === 'object' && data.detail?.status === 'development_rejected') {
        return t('error.developmentRejected');
      }
    } catch {
      /* ignore */
    }
    return t('error.parityBlocked');
  }
  if (status === 502) return t('api.error.bad_gateway');
  return localizeUserMessage(text) || t('api.error.http', { status: String(status) });
}

type I18nParams = Record<string, string | number>;

function formatWithParams(key: string, params?: I18nParams, fallback?: string): string {
  const label = t(key, params);
  if (label !== key) return label;
  return fallback ?? '';
}

export function formatReconciliationSummary(
  code: string | null | undefined,
  params?: I18nParams,
  fallback?: string,
): string {
  const raw = String(code ?? 'alignment_summary').trim() || 'alignment_summary';
  const key = `reconciliation.summary.${raw}`;
  const label = t(key, params);
  if (label !== key) return label;
  return fallback ? localizeUserMessage(fallback) : label;
}

export function formatReconciliationLoginGap(
  item: { code?: string; params?: I18nParams } | string,
): string {
  if (typeof item === 'string') return localizeUserMessage(item);
  const code = String(item.code ?? '').trim();
  if (!code) return '';
  return formatWithParams(`reconciliation.loginGap.${code}`, item.params, localizeUserMessage(code));
}

export function formatDeveloperAction(
  item: { code?: string; params?: I18nParams } | string,
): string {
  if (typeof item === 'string') return localizeUserMessage(item);
  const code = String(item.code ?? '').trim();
  if (!code) return '';
  return formatWithParams(`reconciliation.developerAction.${code}`, item.params, localizeUserMessage(code));
}

export function formatReconciliationField(field: string | null | undefined): string {
  return mapBackendLabel('reconciliation.field', field, brandText(String(field ?? '')));
}

export function formatSchemaGapType(type: string | null | undefined): string {
  return mapBackendLabel('dbAlignment.gapType', type, brandText(String(type ?? '')));
}

export function formatSchemaGapStatus(status: string | null | undefined): string {
  return mapBackendLabel('dbAlignment.gapStatus', status, brandText(String(status ?? '')));
}

export function formatSchemaGapSeverity(severity: string | null | undefined): string {
  const fromRegistry = formatRegistryPriority(severity);
  if (fromRegistry) return fromRegistry;
  return mapBackendLabel('dbAlignment.severity', severity, String(severity ?? ''));
}

export function formatSchemaGapDetail(gap: {
  detail?: string;
  detail_code?: string;
  detail_params?: I18nParams;
  type?: string;
  table?: string;
}): string {
  const code = String(gap.detail_code ?? '').trim();
  if (code) {
    const label = formatWithParams(`dbAlignment.gapDetail.${code}`, gap.detail_params, '');
    if (label) return label;
  }
  if (gap.type) {
    const fromType = formatWithParams(`dbAlignment.gapDetail.${gap.type}`, {
      table: gap.table ?? '',
      ...(gap.detail_params || {}),
    }, '');
    if (fromType) return fromType;
  }
  return localizeUserMessage(gap.detail);
}

export function formatNonMobileGapDetail(
  code: string | null | undefined,
  detail?: string | null,
): string {
  const raw = String(code ?? '').trim();
  if (raw) {
    const label = mapBackendLabel('repos.nonMobile.detail', raw);
    if (label !== `repos.nonMobile.detail.${raw}`) return label;
  }
  return localizeUserMessage(detail);
}
