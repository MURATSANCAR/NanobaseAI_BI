# Modifier evidence

The resolver records `GRAMMATICAL`, `SEMANTIC`, `ABSENCE` or `UNKNOWN` in
`query.modifiers`. Position and light-verb roots are hints, never certification.
Certified phrase mappings are resolved by the existing catalog lookup. Unknown
modifiers block SQL generation and return `type: CLARIFICATION` with
`needs_clarification: true`; their trace remains in the query log.

History evidence is deliberately conservative. Imported YAML pairs or SQL
document front matter must explicitly contain `human_verified: true`. A
successful execution, `runtime_validated` source, or missing SQL predicate does
not constitute human approval. Do not bulk-mark existing pairs as approved.

For grammatical equivalence, both the complete question and the question with
the single modifier removed must have independently approved pairs with equal
SQL syntax trees. Conflicting SQL, another datasource, or an absent control
invalidates the evidence. Matching is by complete token sequence; evidence is
not generalised to other entities, directions, dates or verb inflections. SQL is
parsed once when the resolver is built; no database shadow query is executed.
Reload the knowledge pack after adding reviewed pairs.

`modifierTelemetry` reports decisions, recovered candidates, catalog/history
confirmation and silent drops among detected modifiers. This is detector-scoped
telemetry, not a claim that all possible Turkish modifiers are recognised.

The regression matrix covers 24 phrases plus catalog, history, scope and API
guards. Run the offline suite with:

```sh
rtk proxy env PYTHONPATH=backend SEMANTIC_TABLE_SELECTOR=off uv run --python 3.11 --with-requirements backend/requirements-semantic.txt -- python -m pytest backend/semantic_layer/tests -q
```

The production golden recall and the referenced 10-question daily baseline
require their deployment catalog and question set. Unit-test success must not be
reported as an improvement over that 7/10 baseline.
