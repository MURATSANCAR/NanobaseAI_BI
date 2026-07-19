from __future__ import annotations

import re


def test_email_mask():
    email = "user@example.com"
    masked = re.sub(r"(^.).*(@.*$)", r"\1***\2", email)
    assert masked != email
    assert "@example.com" in masked


def test_iban_mask():
    iban = "TR330006100519786457841326"
    masked = iban[:4] + "*" * (len(iban) - 8) + iban[-4:]
    assert iban not in masked
    assert masked.startswith("TR33")
