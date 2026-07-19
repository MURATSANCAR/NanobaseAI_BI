# Faz 9 — SAP HANA / S/4HANA Production Entegrasyonu (index)

Önceki connector özeti [phase-9.md](../phase-9.md) içinde kaldı.
Bu klasör production sertifikasyon mimarisini ve kanıtlarını tutar.

| Doküman | İçerik |
|---------|--------|
| [architecture.md](architecture.md) | Hardened Gateway SAP path (OData + HANA) |
| [sap-source-policy.md](sap-source-policy.md) | CDS/VDM kaynak önceliği ve yasaklar |
| [sap-authorization-model.md](sap-authorization-model.md) | Min privilege, company/client izolasyonu |
| [s4-odata-design.md](s4-odata-design.md) | Logical plan, safe builder, pagination |
| [hana-connector-design.md](hana-connector-design.md) | hdbcli, policy, workload, plan guard |
| [sap-semantic-model.md](sap-semantic-model.md) | Ledger, fiscal, currency, unit, reversal |
| [sap-functional-governance.md](sap-functional-governance.md) | Functional validation + approvals |
| [fi-rule-pack.md](fi-rule-pack.md) | İlk vertical slice — SAP FI |
| [verification-plan.md](verification-plan.md) | Unit / corpus / functional / chaos |
| [rollback-plan.md](rollback-plan.md) | PLAN_ONLY / feature flags |
| [acceptance.md](acceptance.md) | Go / No-Go |
| [known-risks.md](known-risks.md) | Açık riskler |
| [implementation-report.md](implementation-report.md) | Kod haritası |
| [quality-results.md](quality-results.md) | Kalite özeti |
| [security-results.md](security-results.md) | Güvenlik özeti |
| [performance-results.md](performance-results.md) | Performans özeti |
| [chaos-results.md](chaos-results.md) | Chaos özeti |

Artefaktlar: `artifacts/phase-9/`.

## Destek matrisi

| SAP sistemi | Yöntem | Durum |
|-------------|--------|--------|
| S/4HANA Cloud Public | Released/custom CDS + OData | Birincil |
| S/4HANA Private Edition | CDS/OData | Birincil |
| S/4HANA On-Premise | CDS/OData | Birincil |
| S/4HANA On-Premise | Approved HANA view | Kontrollü |
| SAP HANA Platform / Cloud | Approved calculation/SQL view | Desteklenecek |
| SAP Business One on HANA | Ayrı sertifikasyon | Opsiyonel |
| SAP BW/4HANA | Ayrı faz | Faz 9 dışı |
| SAP ECC on AnyDB | Ayrı entegrasyon | Faz 9 dışı |
| Ham S/4HANA tabloları | Doğrudan SQL | Yasak |
