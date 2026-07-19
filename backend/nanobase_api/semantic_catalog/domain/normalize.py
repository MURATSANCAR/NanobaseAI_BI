"""Normalization helpers for business terms / synonyms."""

from __future__ import annotations

import re
import unicodedata


_TR_MAP = str.maketrans(
    {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "c",
        "Ğ": "g",
        "İ": "i",
        "Ö": "o",
        "Ş": "s",
        "Ü": "u",
    }
)


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/Turkish chars, collapse to snake-ish token."""
    s = (name or "").strip().translate(_TR_MAP)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s\-]+", "_", s).strip("_")
    return s


def normalize_synonym(syn: str) -> str:
    return normalize_name(syn)
