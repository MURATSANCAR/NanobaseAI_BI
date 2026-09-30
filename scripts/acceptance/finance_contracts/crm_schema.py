"""Remote-only published CRM metadata evidence for the closed CRM query module.

No legacy catalog reads and no source writes. This establishes field/relationship
identity, not API answer acceptance; the latter belongs to composable_live.py.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from schema import collect


REQUIRED = {
    "new_kitapBase": ["new_kitapId", "new_stokkodu", "new_name", "new_yazartext", "new_isbn13", "new_yayineviid", "CreatedOn", "ModifiedOn", "statecode", "statuscode"],
    "new_markaBase": ["new_markaId", "new_name", "statecode", "statuscode"],
    "ContactBase": ["ContactId", "FullName", "new_yazarmi", "CreatedOn", "ModifiedOn", "statecode", "statuscode"],
    "AccountBase": ["AccountId", "Name", "CreatedOn", "ModifiedOn", "statecode", "statuscode"],
}


def main():
    if sys.platform != "linux" or not Path("/proc").is_dir():
        raise SystemExit("Run only on the real test server")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    evidence = collect(("crm",))
    source = evidence["sources"]["crm"]
    physical = {(r["TABLE_NAME"].lower(), r["COLUMN_NAME"].lower()) for r in source["columns"]}
    missing = [t + "." + c for t, cols in REQUIRED.items() for c in cols if (t.lower(), c.lower()) not in physical]
    labels = sorted({str(r["Label"]) for r in source["fieldLabels"] if str(r["attribute"]).lower() == "new_isbn13" and r["LanguageId"] == 1055 and r["Label"]})
    relationships = [r for r in source["relationships"] if r["sourceEntity"] == "new_kitap" and r["sourceAttribute"].lower() == "new_yayineviid" and r["targetEntity"] == "new_marka" and r["targetAttribute"].lower() == "new_markaid"]
    checks = {"requiredPhysicalColumns": not missing, "currentIsbnLabel": any("ISBN" in label for label in labels),
              "publisherRelationship": bool(relationships)}
    evidence.update(checks=checks, missingColumns=missing, currentIsbnLabels=labels,
                    relationshipEvidence=relationships, sourceWrites=0, apiAcceptance=False)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, ensure_ascii=False, default=str, indent=2))
    print(json.dumps({"checks": checks, "missingColumns": missing, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                      "apiAcceptance": False}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
