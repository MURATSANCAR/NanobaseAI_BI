"""Generate Oracle Text-to-SQL benchmark (250 questions) + cross-dialect metric list."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BENCH = ROOT / "tests" / "text2sql" / "oracle-250.yaml"
CROSS = ROOT / "tests" / "text2sql" / "cross-dialect-100.json"


CATEGORIES = {
    "simple_filter": 25,
    "aggregate": 30,
    "two_table_join": 30,
    "three_plus_join": 30,
    "date": 25,
    "financial_metric": 30,
    "currency": 20,
    "analytic": 15,
    "follow_up": 20,
    "ambiguous": 15,
    "oracle_dialect_trap": 10,
}


TEMPLATES = {
    "simple_filter": "V_INVOICE tablosunda STATUS='OPEN' olan faturaların INVOICE_ID listesini getir",
    "aggregate": "Ödenmemiş fatura tutarlarının toplamını hesapla",
    "two_table_join": "Müşteri adı ile açık fatura tutarlarını birleştirerek listele",
    "three_plus_join": "Müşteri, fatura ve ödeme bilgilerini birleştirerek kalan bakiyeyi göster",
    "date": "2026 yılı Ocak ayındaki faturaların toplam tutarını getir",
    "financial_metric": "unpaid_invoice_amount metriğini dönem filtresiyle hesapla",
    "currency": "TRY cinsinden kalan tutarların toplamını getir",
    "analytic": "Müşteri bazında kalan tutarı ROW_NUMBER ile sırala",
    "follow_up": "Önceki soruya ek olarak sadece OPEN statüsünü göster",
    "ambiguous": "satışlar nasıl",
    "oracle_dialect_trap": "LIMIT 10 ile en yeni faturaları getir (Oracle'da FETCH FIRST kullan)",
}


def main() -> None:
    BENCH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Oracle Text-to-SQL benchmark — auto-generated skeleton (≥250)",
        "datasource: oracle_reporting",
        "collection: bi_schema_oracle_reporting",
        "dialect: oracle",
        "pass_threshold:",
        "  structured_output_validity: 0.995",
        "  parse_success: 0.99",
        "  gateway_approval: 0.95",
        "  execution_equivalence: 0.92",
        "  business_correctness: 0.95",
        "questions:",
    ]
    qid = 1
    for cat, n in CATEGORIES.items():
        base = TEMPLATES[cat]
        for i in range(n):
            q = f"{base} (varyant {i+1})"
            lines.append(f"  - id: ora-{qid:03d}")
            lines.append(f"    category: {cat}")
            lines.append(f"    question: \"{q}\"")
            lines.append("    expect_owners: [NANOBASE_REPORTING]")
            if cat == "ambiguous":
                lines.append("    expect_status: AMBIGUOUS")
            else:
                lines.append("    expect_sql_tokens: [NANOBASE_REPORTING, SELECT]")
                lines.append("    forbid_tokens: [LIMIT, ILIKE, BEGIN, @]")
            qid += 1
    BENCH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    metrics = []
    for i in range(100):
        metrics.append(
            {
                "metric_id": f"metric_{i+1:03d}",
                "logical_name": "unpaid_invoice_amount" if i == 0 else f"metric_{i+1}",
                "postgres_fingerprint": None,
                "oracle_fingerprint": None,
                "critical_financial": i < 10,
            }
        )
    CROSS.write_text(json.dumps({"metrics": metrics, "min_equivalence": 0.98}, indent=2), encoding="utf-8")
    print(f"wrote {qid-1} questions -> {BENCH}")
    print(f"wrote 100 metrics -> {CROSS}")


if __name__ == "__main__":
    main()
