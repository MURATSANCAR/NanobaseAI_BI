# Faz 9 Verification Plan

| Suite | Target |
|-------|--------|
| Unit (OData builder / HANA policy / SAP semantic) | ≥95% branch; security-critical 100% |
| OData adversarial corpus | 600/600 REJECT |
| HANA SQL security corpus | 600/600 REJECT |
| Functional benchmark | 400 Q (FI≥150 first) |
| Cross-profile equivalence | 100 (when HANA enabled) |
| Integration | Sandbox OData + HANA TLS |
| Perf / soak / chaos | §43–44 targets |
| Scanners | Semgrep, Bandit, pip-audit, Gitleaks, Trivy — Crit/High = 0 |

Offline verify: `./scripts/server/verify-sap.sh` (SKIP without secrets).
