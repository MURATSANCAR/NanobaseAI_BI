"""Personal-data detection for profiling.

A column is treated as sensitive when its *name shape* or its *value shape* matches personal data. The
rule set is generic (identity numbers, e-mail, phone, IBAN, card, address, birth date, credentials) and
extensible through SEMANTIC_PII_PATTERNS; it never encodes one customer's column names.

A sensitive column is never value-sampled, never carries observed values into the catalog, is masked in
the portal inventory and is excluded from LLM prompt context. Its existence is still visible — analysts
need to know the column is there — but its contents never leave the database.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Optional

# Name fragments used for personal data across languages/ERPs (Turkish + English).
_NAME_PATTERNS = [
    r"tckn|tc_?kimlik|kimlik_?no|vergi_?no|vkn|ssn|social_?security|national_?id|passport|pasaport",
    r"e_?mail|eposta|email_?addr|mail_?addr",
    r"tel(no|nrs|efon)?\d*|phone|gsm|mobile|cep_?tel|faks|fax",
    r"iban|bank_?acc|hesap_?no|card_?no|kart_?no|credit_?card|ccnum",
    r"adres|address|street|posta_?kodu|zip_?code|postcode",
    r"dogum|birth_?date|birthday|dob\b",
    r"password|parola|sifre|secret|token|api_?key",
]
# Value shapes that betray personal data even when the column is named opaquely.
_VALUE_PATTERNS = [
    (re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]+$"), "e-posta biçimi"),
    (re.compile(r"^\+?\d[\d ()\-]{8,}$"), "telefon biçimi"),
    (re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$"), "IBAN biçimi"),
    (re.compile(r"^\d{11}$"), "11 haneli kimlik numarası biçimi"),
]


def _compiled() -> list[re.Pattern[str]]:
    extra = [p for p in os.environ.get("SEMANTIC_PII_PATTERNS", "").split(",") if p.strip()]
    return [re.compile(p, re.I) for p in _NAME_PATTERNS + extra]


def name_is_sensitive(column: str) -> Optional[str]:
    for pattern in _compiled():
        if pattern.search(column or ""):
            return f"kolon adı kişisel veri kalıbına uyuyor ({pattern.pattern.split('|')[0]})"
    return None


def values_are_sensitive(values: Iterable[str], *, threshold: float = 0.6) -> Optional[str]:
    sample = [str(v) for v in values if str(v).strip()]
    if len(sample) < 3:
        return None
    for rx, why in _VALUE_PATTERNS:
        hits = sum(1 for v in sample if rx.match(v))
        if hits / len(sample) >= threshold:
            return why
    return None


def classify(column: str, values: Iterable[str] = ()) -> Optional[str]:
    """Return the reason a column is personal data, or None."""
    return name_is_sensitive(column) or values_are_sensitive(values)


MASK = "•••"
