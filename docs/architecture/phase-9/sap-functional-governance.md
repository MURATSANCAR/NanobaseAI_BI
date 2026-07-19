# SAP Functional Governance

Every metric requires a Functional Validation Record:

```json
{
  "metric": "open_receivable_amount",
  "domain": "FI",
  "validatedByRole": "SAP_FI_CONSULTANT",
  "status": "APPROVED"
}
```

## Dual approval

SAP Functional Reviewer + Nanobase Technical Reviewer.
Critical financial metrics also need Data Owner approval.

Technical tests alone do not close Phase 9.
