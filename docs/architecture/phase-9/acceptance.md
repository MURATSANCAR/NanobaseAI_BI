# Faz 9 Acceptance / Go-No-Go

## Vertical slice GO (code complete offline)

- [x] SAP hardened package under `infrastructure/sap/`
- [x] OData logical plan + safe builder + policy
- [x] OData adversarial corpus ≥600 all REJECT
- [x] HANA policy + security corpus ≥600 all REJECT
- [x] FI semantic pack + open_receivable binding
- [x] AWEL S/4 OData + HANA prompts
- [x] Feature flags + PLAN_ONLY rollback
- [x] Docs + artifacts skeleton

## Production GO (requires live SAP sandbox)

- [ ] Communication arrangement + RO identity
- [ ] Live verify-sap.sh PASS
- [ ] Cross-company / cross-client 0 rows
- [ ] FI functional reviewer approval
- [ ] 400-Q functional thresholds
- [ ] Soak / chaos / credential rotation
- [ ] Basis + Security + Data Owner approval

## Immediate NO_GO

Raw S/4 table access, SAP_ALL/SYSTEM, OData write, action/function bypass,
cross-client/company leak, wrong ledger/currency/reversal, analytic privilege bypass,
workload skip, missing functional validation, unmasked sensitive data,
Critical/High findings, rollback failure, OData→raw HANA table fallback.
