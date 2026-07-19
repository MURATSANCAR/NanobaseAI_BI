# Network forbidden-flow tests (§10.3)

YAML NetworkPolicies are insufficient. For each forbidden path, run a real connect test.

## Forbidden examples

| From | To | Expect |
|------|-----|--------|
| DB-GPT pod | customer PostgreSQL :5432 | connection fail |
| AWEL / DB-GPT | customer Oracle | fail |
| Frontend | Query Gateway | fail (no public route) |
| Public Internet | DB-GPT / QG / meta PG | fail |

## Host equivalent (current deploy)

Until K8s pre-prod exists, verify with:

```bash
# From DB-GPT host namespace / process network
nc -zv <customer-pg-host> 5432   # must fail if firewall correct
```

Record results in `artifacts/final-release-gate/network-egress-results.json`.
