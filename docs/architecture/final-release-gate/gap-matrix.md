# Final Gate gap matrix

| Area | Target | Automation status | Remaining for production GO |
|------|--------|-------------------|-----------------------------|
| SQL security corpus | 2800 | **2820** (+500 cross-layer) | `--run-pytest` in CI with live policy |
| AI adversarial | 1000 | **1000** corpus + detector | Live LLM tool-escape eval |
| Quality benchmark | 1100 | **1100** corpora + runner | Live execution equivalence |
| E2E scenarios | 500 | **500** synthetic pack | Wire live curls per area |
| Phase evidence | 1–9 | Verifier + LEGACY/PARTIAL map | Live Oracle/SAP GO |
| Supply chain | Manifest+SBOM+sign | Generators + stubs | Real digests, cosign, SLSA |
| Tenant / honeytenant | Full stack | Suite + honeytenant tests | Live RLS/VPD/SAP |
| Backup / DR | Restore proven | Offline backup/restore + DR tabletop | Live pg_dump + multi-cluster drill |
| K8s PSS / NetworkPolicy | Restricted | Manifests + Helm scaffold | Pre-prod cluster + egress probes |
| Pen-test / UAT / Go board | Signed | Templates; decision BLOCKED until signed | Org signatures |

Run: `./scripts/server/verify-final-gate.sh 1.0.0-rc.1`

See [production-readiness-plan.md](production-readiness-plan.md).
