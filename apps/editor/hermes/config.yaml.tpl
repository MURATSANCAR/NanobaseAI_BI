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

# Sub-agents (Critic Agent, Editor Review Agent, parallel sub-analyses).
delegation:
  model: book-director
  base_url: http://editor-gateway:8000/v1
  api_key: "${EDITOR_GATEWAY_KEY}"
  max_concurrent_children: 6
  max_spawn_depth: 2
  inherit_mcp_toolsets: true
  subagent_auto_approve: false

mcp_servers:
  book_document_mcp:
    url: http://editor-mcp:8000/document/mcp
    headers: {Authorization: "Bearer ${EDITOR_MCP_KEY}"}
    timeout: 1800
    connect_timeout: 60
    trust: full
  book_vision_mcp:
    url: http://editor-mcp:8000/vision/mcp
    headers: {Authorization: "Bearer ${EDITOR_MCP_KEY}"}
    timeout: 3600
    connect_timeout: 60
    trust: full
  book_knowledge_mcp:
    url: http://editor-mcp:8000/knowledge/mcp
    headers: {Authorization: "Bearer ${EDITOR_MCP_KEY}"}
    timeout: 3600
    connect_timeout: 60
    trust: full
  book_retrieval_mcp:
    url: http://editor-mcp:8000/retrieval/mcp
    headers: {Authorization: "Bearer ${EDITOR_MCP_KEY}"}
    timeout: 1800
    connect_timeout: 60
    trust: full
  book_quality_mcp:
    url: http://editor-mcp:8000/quality/mcp
    headers: {Authorization: "Bearer ${EDITOR_MCP_KEY}"}
    timeout: 1800
    connect_timeout: 60
    trust: full
  book_jobs_mcp:
    url: http://editor-mcp:8000/jobs/mcp
    headers: {Authorization: "Bearer ${EDITOR_MCP_KEY}"}
    timeout: 600
    connect_timeout: 60
    trust: full

# No terminal, no file system, no code execution, no web: only MCP tools
# + memory + skills + delegation + cron + todo/clarify (NIHAI-KARAR.md §4).
platform_toolsets:
  cli: [memory, skills, delegation, cronjob, todo, clarify]
  api_server: [memory, skills, delegation, cronjob, todo]
  cron: [memory, skills, delegation, todo]
agent:
  disabled_toolsets: [terminal, file, code_execution, web, search, browser, vision, image_gen,
                      video_gen, video, tts, computer_use, homeassistant, connections, kanban,
                      x_search, session_search, spotify, discord, discord_admin, yuanbao]

# Hermes' own memory: user preferences, publisher rules, age rubrics, analysis
# profiles, project settings, approved way of working. Book facts: never
# (SOUL.md).
memory:
  memory_enabled: true
  user_profile_enabled: true
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
  disabled: [hermes-agent]

telemetry:
  shared_metrics: {enabled: false, send: false}

updates:
  check: false
