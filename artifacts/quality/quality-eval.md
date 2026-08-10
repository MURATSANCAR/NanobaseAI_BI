# Text2SQL execution accuracy

- Zaman: `2026-08-10T21:38:42.015216+00:00`
- Datasource: `bi_reporting`
- Korpus: `quality-corpus.yaml` (30 vaka)
- **Execution accuracy: 56.7%** (17/30, eşik 80%) → FAIL
- Pipeline hata oranı: 6.7% · repair'li vaka: 1
- Gecikme: p50 166.58s · p95 330.2s · ilk token p50 130.87s

## Etiket kırılımı

| Etiket | Geçen |
|--------|-------|
| aggregate | 2/5 |
| ambiguous | 1/1 |
| anti_join | 1/1 |
| count | 3/4 |
| date_filter | 1/2 |
| date_trunc | 0/1 |
| filter | 4/5 |
| group_by | 5/9 |
| having | 0/1 |
| invoices | 2/4 |
| join | 1/8 |
| master_data | 1/2 |
| numeric | 1/1 |
| order_by | 1/1 |
| out_of_schema | 1/1 |
| payments | 1/1 |
| returns | 1/1 |
| revenue | 1/4 |
| single_table | 4/5 |
| top_n | 1/3 |

## Vakalar

| ID | Sonuç | Süre | Repair | Not |
|----|-------|------|--------|-----|
| `qa-001` | PASS | 123.8s | 0 | result set matches reference |
| `qa-002` | FAIL | 119.33s | 0 | result set differs from reference |
| `qa-003` | PASS | 127.11s | 0 | result set matches reference |
| `qa-004` | PASS | 128.12s | 0 | result set matches reference |
| `qa-005` | PASS | 203.29s | 0 | result set matches reference |
| `qa-006` | PASS | 0.33s | 0 | result set matches reference |
| `qa-007` | FAIL | 303.27s | 0 | pipeline error: TimeoutError: timed out |
| `qa-008` | PASS | 330.2s | 0 | result set matches reference |
| `qa-009` | PASS | 186.65s | 0 | result set matches reference |
| `qa-010` | PASS | 139.15s | 0 | result set matches reference |
| `qa-011` | FAIL | 161.7s | 0 | result set differs from reference |
| `qa-012` | FAIL | 147.52s | 0 | result set differs from reference |
| `qa-013` | FAIL | 177.81s | 0 | result set differs from reference |
| `qa-014` | FAIL | 140.74s | 0 | result set differs from reference |
| `qa-015` | FAIL | 156.83s | 0 | result set differs from reference |
| `qa-016` | FAIL | 177.09s | 0 | result set differs from reference |
| `qa-017` | PASS | 158.27s | 0 | result set matches reference |
| `qa-018` | FAIL | 170.34s | 0 | result set differs from reference |
| `qa-019` | PASS | 148.5s | 0 | result set matches reference |
| `qa-020` | FAIL | 174.48s | 0 | result set differs from reference |
| `qa-021` | FAIL | 144.05s | 0 | result set differs from reference |
| `qa-022` | PASS | 211.31s | 0 | result set matches reference |
| `qa-023` | PASS | 213.19s | 0 | result set matches reference |
| `qa-024` | PASS | 134.17s | 0 | result set matches reference |
| `qa-025` | FAIL | 374.08s | 1 | result set differs from reference |
| `qa-026` | FAIL | 166.58s | 0 | result set differs from reference |
| `qa-027` | PASS | 211.18s | 0 | result set matches reference |
| `qa-028` | PASS | 198.24s | 0 | result set matches reference |
| `qa-029` | PASS | 303.55s | 0 | no fabricated execution |
| `qa-030` | PASS | 208.09s | 0 | clarification requested |
