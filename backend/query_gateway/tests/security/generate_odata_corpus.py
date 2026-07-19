"""Generate ≥600 malicious OData plan fixtures (all must REJECT)."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).parent / "corpus" / "odata_malicious.jsonl"


def _plans() -> list[dict]:
    cases: list[dict] = []

    def add(category: str, plan: dict) -> None:
        cases.append({"category": category, "plan": plan, "expect": "REJECT"})

    # Host/path escape (60)
    for i in range(60):
        entity = [
            f"../evil{i}",
            f"http://evil{i}",
            f"https://evil/{i}",
            f"evil;{i}",
            f"//evil{i}",
            f"..%2fevil{i}",
        ][i % 6]
        add(
            "host_path_escape",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": entity,
                "select": ["CompanyCode"],
                "top": 10,
            },
        )

    # Entity escape (60) — not allowlisted
    for i in range(60):
        add(
            "entity_escape",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": f"EvilEntity{i}",
                "select": ["CompanyCode"],
                "top": 10,
            },
        )

    # Filter injection (80) — bad field, op, or URL value
    for i in range(80):
        add(
            "filter_injection",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": "JournalEntryItem",
                "select": ["CompanyCode"],
                "filters": [
                    {
                        "field": ["1eq1", "evil()", f"F{i}DROP", "CompanyCode;"][i % 4],
                        "operator": ["OR", "EXEC", "LIKE", "BETWEEN"][i % 4],
                        "value": "1000",
                    }
                ],
                "top": 10,
            },
        )

    # Encoding/Unicode (60) — invalid select or entity
    for i in range(60):
        bad_select = ["*", f"Col-{i}", f"Col {i}", "Col\x00x"][i % 4]
        add(
            "encoding_unicode",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": "JournalEntryItem",
                "select": [bad_select],
                "top": 10,
            },
        )

    # Navigation abuse (50)
    for i in range(50):
        add(
            "navigation_abuse",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": f"JournalEntryItem/../Evil{i}",
                "select": ["CompanyCode"],
                "top": 10,
            },
        )

    # Expand abuse (50) — depth > 1 or too many
    for i in range(50):
        add(
            "expand_abuse",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": "JournalEntryItem",
                "select": ["CompanyCode"],
                "expand": [f"to_A/to_B{i}", f"to_C/to_D{i}", f"to_E{i}"][: 2 + (i % 2)],
                "top": 10,
            },
        )

    # Action/function (60)
    for i in range(60):
        add(
            "action_function",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": f"JournalEntryItem_Action{i}",
                "select": ["CompanyCode"],
                "top": 10,
            },
        )

    # Write operation (60) — missing select
    for i in range(60):
        add(
            "write_operation",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": "JournalEntryItem",
                "select": [],
                "top": 10,
            },
        )

    # Pagination / next-link style (50) — URL in filter value
    for i in range(50):
        add(
            "pagination_nextlink",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": "JournalEntryItem",
                "select": ["CompanyCode"],
                "top": 10,
                "filters": [
                    {
                        "field": "CompanyCode",
                        "operator": "EQ",
                        "value": f"https://evil{i}.example/next",
                    }
                ],
            },
        )

    # Query option duplication / wildcard (40)
    for i in range(40):
        add(
            "query_duplication",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": "JournalEntryItem",
                "select": ["*"] if i % 2 == 0 else [f"bad-field-{i}"],
                "top": 10,
            },
        )

    # Oversized query (30)
    for i in range(30):
        add(
            "oversized_query",
            {
                "sourceType": "SAP_ODATA",
                "service": "API_JOURNALENTRYITEM_SRV",
                "entitySet": "JournalEntryItem",
                "select": [f"Col{j}" for j in range(120)],
                "top": 5000 + i,
            },
        )

    return cases


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    cases = _plans()
    assert len(cases) >= 600, len(cases)
    with OUT.open("w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    print(f"wrote {len(cases)} -> {OUT}")


if __name__ == "__main__":
    main()
