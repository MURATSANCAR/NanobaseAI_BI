# Text2SQL execution accuracy

- Zaman: `2026-08-11T07:26:48.206837+00:00`
- Datasource: `bi_reporting`
- Korpus: `quality-corpus.yaml` (30 vaka)
- **Execution accuracy: 70.0%** (21/30, eşik 80%) → FAIL
- Pipeline hata oranı: 0.0% · repair'li vaka: 0
- Gecikme: p50 152.08s · p95 238.45s · ilk token p50 124.87s

## Etiket kırılımı

| Etiket | Geçen |
|--------|-------|
| aggregate | 4/5 |
| ambiguous | 1/1 |
| anti_join | 1/1 |
| count | 4/4 |
| date_filter | 2/2 |
| date_trunc | 0/1 |
| filter | 4/5 |
| group_by | 6/9 |
| having | 1/1 |
| invoices | 2/4 |
| join | 2/8 |
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
| `qa-001` | PASS | 130.91s | 0 | result set matches reference |
| `qa-002` | FAIL | 0.11s | 0 | result set differs from reference |
| `qa-003` | PASS | 0.09s | 0 | result set matches reference |
| `qa-004` | PASS | 144.79s | 0 | result set matches reference |
| `qa-005` | PASS | 184.36s | 0 | result set matches reference |
| `qa-006` | PASS | 135.71s | 0 | result set matches reference |
| `qa-007` | PASS | 207.64s | 0 | result set matches reference |
| `qa-008` | PASS | 130.67s | 0 | result set matches reference |
| `qa-009` | PASS | 167.73s | 0 | result set matches reference |
| `qa-010` | PASS | 136.82s | 0 | result set matches reference |
| `qa-011` | PASS | 197.21s | 0 | result set matches reference |
| `qa-012` | PASS | 152.08s | 0 | result set matches reference |
| `qa-013` | FAIL | 200.31s | 0 | result set differs from reference |
| `qa-014` | PASS | 76.49s | 0 | result set matches reference |
| `qa-015` | FAIL | 173.01s | 0 | result set differs from reference |
| `qa-016` | FAIL | 0.29s | 0 | result set differs from reference |
| `qa-017` | FAIL | 0.16s | 0 | result set differs from reference |
| `qa-018` | PASS | 238.45s | 0 | result set matches reference |
| `qa-019` | PASS | 158.94s | 0 | result set matches reference |
| `qa-020` | FAIL | 0.19s | 0 | result set differs from reference |
| `qa-021` | FAIL | 158.02s | 0 | result set differs from reference |
| `qa-022` | PASS | 222.51s | 0 | result set matches reference |
| `qa-023` | PASS | 243.55s | 0 | result set matches reference |
| `qa-024` | PASS | 0.16s | 0 | result set matches reference |
| `qa-025` | FAIL | 0.16s | 0 | result set differs from reference |
| `qa-026` | FAIL | 163.59s | 0 | result set differs from reference |
| `qa-027` | PASS | 181.54s | 0 | result set matches reference |
| `qa-028` | PASS | 142.21s | 0 | result set matches reference |
| `qa-029` | PASS | 194.38s | 0 | clarification requested |
| `qa-030` | PASS | 201.38s | 0 | clarification requested |
