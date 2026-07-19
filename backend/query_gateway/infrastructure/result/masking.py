"""Sensitive value masking."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def mask_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    s = str(value)
    k = (kind or "FULL").upper()
    if k == "NULLIFY":
        return None
    if k == "FULL":
        return "***"
    if k == "HASH":
        return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
    if k == "LAST_FOUR":
        return ("*" * max(0, len(s) - 4)) + s[-4:] if len(s) >= 4 else "****"
    if k == "EMAIL":
        if "@" not in s:
            return "***"
        local, _, domain = s.partition("@")
        keep = local[:1] if local else ""
        return f"{keep}***@{domain}"
    if k == "PHONE":
        digits = re.sub(r"\D", "", s)
        if len(digits) < 7:
            return "***"
        return digits[:4] + "***" + digits[-4:]
    if k == "IBAN":
        compact = s.replace(" ", "")
        if len(compact) < 8:
            return "****"
        return compact[:4] + ("*" * (len(compact) - 8)) + compact[-4:]
    if k == "IDENTITY_NUMBER":
        if len(s) < 2:
            return "**"
        return ("*" * (len(s) - 2)) + s[-2:]
    if k == "PARTIAL":
        if len(s) <= 2:
            return "**"
        return s[:1] + ("*" * (len(s) - 2)) + s[-1:]
    return "***"


def column_mask_kind(column_name: str, policies: dict[str, str]) -> str | None:
    """Return mask kind if column is MASKED; DENIED should be blocked earlier."""
    key = column_name.lower()
    mode = policies.get(key)
    if mode and mode.upper().startswith("MASK"):
        # MASKED or MASKED:EMAIL
        if ":" in mode:
            return mode.split(":", 1)[1].upper()
        return "PARTIAL"
    # also match suffix .email etc.
    for pk, pv in policies.items():
        if pk.endswith(f".{key}") or pk == key:
            if str(pv).upper().startswith("MASK"):
                if ":" in str(pv):
                    return str(pv).split(":", 1)[1].upper()
                # infer from column name
                if "email" in pk:
                    return "EMAIL"
                if "phone" in pk or "tel" in pk:
                    return "PHONE"
                if "iban" in pk:
                    return "IBAN"
                if "identity" in pk or "tc" in pk:
                    return "IDENTITY_NUMBER"
                return "PARTIAL"
    return None
