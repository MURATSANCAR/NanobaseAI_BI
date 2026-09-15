"""Planlı rapor maili: özetli HTML + düz metin yedeği, rakamlar tüm satırlardan, ilk 5 satır örnek."""

from __future__ import annotations

from datetime import datetime, timezone

from semantic_bridge import reports as R

COLS = [
    {"name": "Müşteri", "type": "nvarchar", "format": "auto"},
    {"name": "Net Ciro", "type": "float", "format": "money"},
    {"name": "Pay", "type": "float", "format": "percent"},
]
ROWS = [{"Müşteri": f"Cari {i} <A&B>", "Net Ciro": 1_000_000.5 * i, "Pay": 1.25 * i} for i in range(1, 8)]
REP = {"title": "Müşteri Net Ciro", "question": "2026 müşteri bazlı net ciro", "when": "Tek sefer",
       "recipients": ["a@example.com"]}
NOW = datetime(2026, 9, 16, 7, 30, tzinfo=timezone.utc)


def test_values_use_turkish_notation():
    assert R.mail_value(COLS[1], 1234567.5) == "1.234.567,50 ₺"
    assert R.mail_value(COLS[2], 42.7) == "%42,7"
    assert R.mail_value({"name": "x", "type": "int"}, 73660) == "73.660"
    assert R.mail_value(COLS[0], None) == "—"
    assert R.compact_money(848_100_000) == "848,1 Mn ₺"


def test_total_is_over_all_rows_not_the_sample():
    s = R.mail_summary(COLS, ROWS)
    assert s["rows"] == 7
    assert s["totalLabel"] == "Net Ciro"
    assert abs(s["total"] - sum(r["Net Ciro"] for r in ROWS)) < 1e-6
    assert R.mail_summary([COLS[0]], ROWS)["total"] is None


def test_message_has_html_and_text_with_escaped_sample(tmp_path):
    path = tmp_path / "rapor.xlsx"
    path.write_bytes(b"x")
    msg = R.compose_mail(REP, path, COLS, ROWS, NOW, link="https://portal.example/timas/planli-raporlar")
    assert msg["Subject"] == "ZEKİ Rapor · Müşteri Net Ciro · 16.09.2026"
    text = msg.get_body(("plain",)).get_content()
    html = msg.get_body(("html",)).get_content()
    assert "İlk 5 satır" in text and "tamamı ekteki dosyada (7 satır)" in text
    assert "Cari 1 &lt;A&amp;B&gt;" in html and "<A&B>" not in html
    assert "Cari 5" in html and "Cari 6" not in html
    assert "28,0 Mn ₺" in html
    assert "Raporu ekranda aç" in html and "10:30" in html  # yerel saat (+3)


def test_send_attaches_file(monkeypatch, tmp_path):
    path = tmp_path / "rapor.xlsx"
    path.write_bytes(b"PK")
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, m): sent.append(m)

    monkeypatch.setattr(R.alerts_mod, "smtp_settings", lambda: {
        "host": "h", "port": 587, "user": "", "password": "", "sender": "zeki@example.com", "ssl": False, "starttls": True})
    monkeypatch.setattr(R.smtplib, "SMTP", FakeSMTP)
    assert R.send_file(REP, path, COLS, ROWS, NOW) == "sent"
    names = [p.get_filename() for p in sent[0].iter_attachments()]
    assert names == ["rapor.xlsx"]
    assert sent[0].get_body(("html",)) is not None
