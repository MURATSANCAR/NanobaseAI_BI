# Data classification

Classes: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED, PII, FINANCIAL, SECRET.

Per column: class, view authz, masking, export, LLM visibility, log visibility, audit visibility, retention.

Acceptance: unmasked RESTRICTED = 0; forbidden raw values to LLM/logs = 0.
