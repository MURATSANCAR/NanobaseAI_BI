from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "artifacts" / "final-release-gate"
DOCS = REPO_ROOT / "docs" / "architecture" / "final-release-gate"

GATE_STATUSES = (
    "NOT_STARTED",
    "PREPARING",
    "RELEASE_CANDIDATE_FROZEN",
    "VERIFYING",
    "SECURITY_REVIEW",
    "PERFORMANCE_REVIEW",
    "DR_REVIEW",
    "CUSTOMER_ACCEPTANCE",
    "BLOCKED",
    "REJECTED",
    "CONDITIONAL_GO",
    "GO",
    "DEPLOYED",
    "POST_RELEASE_VERIFIED",
)

# Areas where CONDITIONAL_GO is forbidden
HARD_NO_GO_AREAS = frozenset(
    {
        "tenant_isolation",
        "sql_security",
        "secret_security",
        "financial_accuracy",
        "sap_functional",
        "backup_restore",
        "rollback",
        "critical_high_security",
        "audit_integrity",
    }
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_artifacts() -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_tree(root: Path, patterns: tuple[str, ...] = ("*",)) -> str:
    """Stable hash of files under root (relative paths sorted)."""
    h = hashlib.sha256()
    files: list[Path] = []
    if not root.exists():
        return h.hexdigest()
    for pat in patterns:
        files.extend(p for p in root.rglob(pat) if p.is_file())
    for path in sorted(set(files), key=lambda p: str(p.relative_to(root))):
        rel = str(path.relative_to(root)).replace("\\", "/")
        h.update(rel.encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def write_json(path: Path, data: Any) -> None:
    ensure_artifacts()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_gate_status() -> dict[str, Any]:
    path = ARTIFACTS / "gate-status.json"
    if not path.exists():
        return {
            "status": "NOT_STARTED",
            "release": None,
            "updatedAt": None,
            "history": [],
        }
    return read_json(path)


def set_gate_status(status: str, release: str | None = None, note: str = "") -> dict[str, Any]:
    if status not in GATE_STATUSES:
        raise ValueError(f"invalid gate status: {status}")
    cur = load_gate_status()
    cur["history"].append(
        {
            "from": cur.get("status"),
            "to": status,
            "at": utc_now(),
            "note": note,
        }
    )
    cur["status"] = status
    if release:
        cur["release"] = release
    cur["updatedAt"] = utc_now()
    write_json(ARTIFACTS / "gate-status.json", cur)
    return cur


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")
