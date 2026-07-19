# Faz 6 trust boundaries

| Boundary | Rule |
|----------|------|
| User question | Untrusted; wrapped in `<user_question>` |
| Schema context | Authorized retrieve only (`tenant_id` + `datasource_id`) |
| DB comments | `<untrusted_database_comment>` — never instructions |
| SQL execute | Query Gateway only; never DB-GPT Chat Data |
| Repair | Allowlisted Gateway error codes; max 2; no scope expansion |
| Explanation | Numbers must appear in result/summary or Turkish fallback |

Assert: `scripts/server/assert-no-chat-data-execute.sh`
