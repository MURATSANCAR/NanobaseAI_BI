# Canlı kapasite ölçümü

- Zaman: `2026-08-10T21:49:32.475325+00:00`
- MODEL_MAX_CONCURRENCY: `2`

| Eşzamanlı | İstek | Başarı | p50 | p95 | TTFT p50 | Kuyruk | req/dk |
|-----------|-------|--------|-----|-----|----------|--------|--------|
| 1 | 2 | 2 | 0.12s | 122.61s | 0.11s | 0 | 0.98 |
| 2 | 4 | 4 | 141.29s | 184.89s | 126.27s | 0 | 1.3 |
| 4 | 8 | 8 | 0.41s | 327.03s | 0.3s | 220 | 1.47 |

**Değerlendirme:** p95 grows 2.7× from concurrency 1 → 4 (pure serialization would be ~4×). Parallel slots are absorbing load.
