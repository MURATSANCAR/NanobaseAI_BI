# Faz 8 — Oracle Production Entegrasyonu (index)

Önceki ADB SSB connector özeti [phase-8.md](../phase-8.md) içinde kaldı.
Bu klasör production sertifikasyon mimarisini ve kanıtlarını tutar.

| Doküman | İçerik |
|---------|--------|
| [architecture.md](architecture.md) | Hardened Gateway Oracle path |
| [oracle-support-matrix.md](oracle-support-matrix.md) | 19c / 23ai / RAC / CDB-PDB |
| [oracle-security-model.md](oracle-security-model.md) | Değiştirilemez güvenlik kuralları |
| [oracle-privilege-model.md](oracle-privilege-model.md) | METADATA / PLAN / QUERY hesapları |
| [oracle-metadata-model.md](oracle-metadata-model.md) | ALL_* scanner + synonym |
| [oracle-dialect-policy.md](oracle-dialect-policy.md) | SQLGlot + function/statement policy |
| [oracle-ha-design.md](oracle-ha-design.md) | Thin pool, RAC, retry |
| [oracle-vpd-design.md](oracle-vpd-design.md) | Application context |
| [verification-plan.md](verification-plan.md) | Unit / corpus / integration |
| [rollback-plan.md](rollback-plan.md) | PLAN_ONLY / feature flag |
| [acceptance.md](acceptance.md) | Go / No-Go |
| [known-risks.md](known-risks.md) | Açık riskler |
| [implementation-report.md](implementation-report.md) | Kod haritası |

Artefaktlar: `artifacts/phase-8/`.
