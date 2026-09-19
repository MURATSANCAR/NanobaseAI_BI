# Regression

`run_regression_suite` (book_quality_mcp) runs after every analysis
(NIHAI-KARAR.md §7). It always checks the quality-rule invariants; per-book
golden expectations live in `books/<sha256[:16]>.yaml`:

```yaml
characters: [Defne, Max]          # must exist as canonical name or alias
events:
  - contains: "tablet"            # substring of an event summary
    modality: PLAN                # expected modality
```

Golden files are written by the editor after reviewing a run, never by a model.
