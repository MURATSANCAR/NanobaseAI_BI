# Semantic versioning

Format: `MAJOR.MINOR.PATCH`

- MAJOR: metric meaning, calculation, mandatory filter, currency, join meaning
- MINOR: new metric/dimension/synonym/verified query
- PATCH: metadata / description only

Each publish produces an immutable manifest (`manifestSha256`).
Rollback switches the active pointer to a prior sealed version.
Executions pin the active semantic version at start.
