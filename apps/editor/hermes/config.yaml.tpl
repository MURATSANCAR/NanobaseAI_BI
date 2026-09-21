# Hermes Agent v2026.9.14 — Book Director (editor module).
# Rendered by `editorctl install` into $EDITOR_ROOT/hermes/config.yaml
# (${EDITOR_GATEWAY_KEY} is filled in there; MCP headers read the env at runtime).

model:
  provider: custom
  default: book-director
  base_url: http://editor-gateway:8000/v1
  api_key: "${EDITOR_GATEWAY_KEY}"
  context_length: 131072

# Every auxiliary task goes to the same gateway alias; Hermes never sees a real model.
auxiliary:
  compression: {provider: custom, model: book-director, base_url: http://editor-gateway:8000/v1, api_key: "${EDITOR_GATEWAY_KEY}"}
  title_generation: {provider: custom, model: book-director, base_url: http://editor-gateway:8000/v1, api_key: "${EDITOR_GATEWAY_KEY}"}
  approval: {provider: custom, model: book-director, base_url: http://editor-gateway:8000/v1, api_key: "${EDITOR_GATEWAY_KEY}"}
  mcp: {provider: custom, model: book-director, base_url: http://editor-gateway:8000/v1, api_key: "${EDITOR_GATEWAY_KEY}"}
  background_review: {provider: custom, model: book-director, base_url: http://editor-gateway:8000/v1, api_key: "${EDITOR_GATEWAY_KEY}"}
  memory_query_rewrite: {provider: custom, model: book-director, base_url: http://editor-gateway:8000/v1, api_key: "${EDITOR_GATEWAY_KEY}"}

# Conversational clients receive only bounded current-revision read tools.
# Analysis producers remain in Temporal and the operator MCP endpoints.
mcp_servers:
  book_chat_mcp:
    url: http://editor-mcp:8000/chat/mcp
    headers: {Authorization: "Bearer ${EDITOR_MCP_KEY}"}
    timeout: 300
    connect_timeout: 30
    trust: full

# API has no producer, delegation, cron, memory or filesystem tools.
platform_toolsets:
  cli: [skills, todo, clarify]
  api_server: [skills, todo]
  cron: []
agent:
  max_turns: 16
  disabled_toolsets: [delegation, cronjob, memory, terminal, file, code_execution, web, search, browser, vision, image_gen,
                      video_gen, video, tts, computer_use, homeassistant, connections, kanban,
                      x_search, session_search, spotify, discord, discord_admin, yuanbao]

# Hermes' own memory: user preferences, publisher rules, age rubrics, analysis
# profiles, project settings, approved way of working. Book facts: never
# (SOUL.md).
memory:
  memory_enabled: false
  user_profile_enabled: false
  write_approval: false

approvals:
  mode: manual
  cron_mode: deny
  single_query_mode: deny
  unattended_mode: deny

cron:
  allow_agent_scheduling: false

curator:
  enabled: false

# Only the book skills (hermes/skills/book). The image seeds one builtin skill; keep it off.
skills:
  disabled: [hermes-agent, evidence_quality_check, publisher_decision_support, universe_canon_analysis, book_recommendation, book_question_answering, book_summary, event_timeline, report_generation, visual_character_continuity, character_analysis, age_group_assessment, visual_scene_analysis, book_intake, book_full_analysis, editor_review_queue, emotion_analysis]

telemetry:
  shared_metrics: {enabled: false, send: false}

updates:
  check: false
