"""Personal-data detection for profiling.

A column is treated as sensitive when its *name shape* or its *value shape* matches personal data. The
rule set is generic (identity numbers, e-mail, phone, IBAN, card, address, birth date, credentials) and
extensible through SEMANTIC_PII_PATTERNS; it never encodes one customer's column names.

A sensitive column is never value-sampled, never carries observed values into the catalog, is masked in
the portal inventory and is excluded from LLM prompt context. Its existence is still visible — analysts
need to know the column is there — but its contents never leave the database.

Name matching is deliberately not a bare substring search. ERP columns are run-together capitals, so a
short fragment like "tel" or "cell" turns up inside words that have nothing to do with a telephone
(DUEDATELIMIT, CANCELLED); every fragment therefore has to be followed by something that continues the
personal-data word — a number/code suffix, or the end of the name. A false positive here is not a
harmless extra precaution: the column is dropped from prompts and its values are never read, so an
iptal flag mistaken for a fax number takes the "CANCELLED = 0" filter out of every generated query.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Optional

#: Suffixes that continue a phone/fax word: TELNRS1, FAXNR, TELCODES2, FAXEXTNUM, TELEFON.
_PHONE_TAIL = r"(efon|no|nr|nrs|num|nums|number|code|codes|ext\w*)?\d*\b"

# Name fragments used for personal data across languages/ERPs (Turkish + English), each with the label
# the sentinel carries. Order matters: the first match names the reason, so EMAILADDR reads as e-posta.
_NAME_PATTERNS: list[tuple[str, str]] = [
    ("TC kimlik / vergi no", r"tckn|tc_?kimlik|kimlik_?no|vergi_?no|vkn|ssn_?(no|nr)?\b|social_?security|national_?id"),
    ("pasaport no", r"passport|pasaport"),
    ("e-posta", r"e_?mail|eposta|email_?addr|mail_?addr"),
    ("telefon/faks", r"(tel|fax|faks)" + _PHONE_TAIL + r"|phone|gsm\w*|mobile\b|cep_?tel\w*"),
    ("IBAN", r"iban|bank_?acc(t|ount)?s?(no|nr|nrs|num)?\d*\b|hesap_?no|card_?no|kart_?no|credit_?card|ccnum"),
    ("adres", r"adres|address|street|posta_?kodu|zip_?code|postcode"),
    ("doğum tarihi", r"dogum|birth_?date|birthday|dob\b"),
    ("kimlik bilgisi", r"password|parola|sifre|secret|token|api_?key"),
]
# Value shapes that betray personal data even when the column is named opaquely.
_VALUE_PATTERNS = [
    (re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]+$"), "e-posta biçimi"),
    (re.compile(r"^\+?\d[\d ()\-]{8,}$"), "telefon biçimi"),
    (re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$"), "IBAN biçimi"),
    (re.compile(r"^\d{11}$"), "11 haneli kimlik numarası biçimi"),
]

#: Types too narrow to hold any of the shapes above. A boolean or a two-byte integer cannot carry a
#: phone number, an IBAN, an e-mail, an address or an 11-digit identity number — it holds a flag or a
#: code. Logo writes its iptal flags as `Byte`, SQL Server reports them as `bit`/`tinyint`/`smallint`.
_FLAG_TYPES = re.compile(r"^(bit|bool(ean)?|tinyint|smallint|int2|byte|logical)\b", re.I)

#: A code set: a handful of short integers. Real personal data never looks like this.
_CODE_MAX_DIGITS = 4
_CODE_MAX_DISTINCT = 8


def _compiled() -> list[tuple[str, re.Pattern[str]]]:
    extra = [("özel kalıp", p) for p in os.environ.get("SEMANTIC_PII_PATTERNS", "").split(",") if p.strip()]
    return [(label, re.compile(p, re.I)) for label, p in _NAME_PATTERNS + extra]


def holds_codes_not_personal_data(data_type: str = "", values: Iterable[str] = ()) -> bool:
    """Whether the column physically cannot hold personal data, whatever its name suggests.

    Two independent reads, either of which settles it: the declared type is too narrow for any personal
    shape, or every value observed is a short integer out of a handful of distinct ones — a flag or an
    enum. This is what keeps a name-pattern near-miss from masking an operational column.
    """
    if _FLAG_TYPES.match((data_type or "").strip()):
        return True
    sample = [str(v).strip() for v in values if str(v).strip()]
    if not sample:
        return False
    if not all(v.lstrip("-").isdigit() and len(v.lstrip("-")) <= _CODE_MAX_DIGITS for v in sample):
        return False
    return len(set(sample)) <= _CODE_MAX_DISTINCT


def name_is_sensitive(column: str) -> Optional[str]:
    for label, pattern in _compiled():
        if pattern.search(column or ""):
            return f"{label} — kolon adı kişisel veri kalıbına uyuyor"
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


def classify(column: str, values: Iterable[str] = (), data_type: str = "") -> Optional[str]:
    """Return the reason a column is personal data, or None."""
    values = list(values)
    if holds_codes_not_personal_data(data_type, values):
        return None
    return name_is_sensitive(column) or values_are_sensitive(values)


MASK = "•••"
