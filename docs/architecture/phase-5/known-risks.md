# Known risks (Faz 5)

- Legacy `/api/v1/query/*` still unauthenticated at gateway loopback (mitigated by bind 127.0.0.1 + portal principal on nanobase proxies). Prefer internal API with JWT/HMAC.
- `QG_REQUIRE_QUALIFIED_TABLES` default false for chat compatibility; enable per strict tenant.
- Full Testcontainers RLS soak / 4h Locust / mTLS NetworkPolicy deferred to staging gates.
- Oracle/SAP not on internal execute path yet.
