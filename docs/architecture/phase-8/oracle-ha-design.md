# Oracle HA Design

- Connect via SERVICE_NAME / SCAN descriptor — never single RAC instance host as sole endpoint.
- Pool: min=max=5, increment=0 (reduce connection storms).
- Retry only when execution never started and outcome known; otherwise `EXECUTION_OUTCOME_UNKNOWN`.
- Thick Mode HA extras require separate process image `query-gateway-oracle-thick`.

See `infrastructure/oracle/rac.py` for descriptor helpers and retry policy stubs.
