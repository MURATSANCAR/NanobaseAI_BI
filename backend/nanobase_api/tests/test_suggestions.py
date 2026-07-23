"""Unit tests for datasource-scoped chat suggestions."""

from __future__ import annotations

from nanobase_api.suggestions import (
    alert_defaults_for,
    build_alert_suggestions,
    build_suggestions,
    defaults_for,
)


class _FakeRepo:
    def __init__(self, rows=None):
        self._rows = rows or []

    def top_user_questions(self, **_kwargs):
        return list(self._rows)


def test_defaults_per_datasource():
    assert any("hasar" in q.lower() for q in defaults_for("sigorta"))
    assert any("müşteri" in q.lower() or "musteri" in q.lower() for q in defaults_for("erp"))
    assert defaults_for("unknown-db")


def test_build_suggestions_defaults_without_history():
    out = build_suggestions(
        tenant_id="default",
        datasource_id="sigorta",
        limit=3,
        question_repo=_FakeRepo([]),
    )
    assert out["datasource_id"] == "sigorta"
    assert len(out["suggestions"]) == 3
    assert out["learned_count"] == 0
    assert all(s["source"] in ("default", "scenario") for s in out["suggestions"])


def test_build_suggestions_includes_learned_when_no_prepared(monkeypatch):
    monkeypatch.setattr(
        "nanobase_api.suggestions.resolve_prepared_sql",
        lambda *_a, **_k: None,
    )
    out = build_suggestions(
        tenant_id="default",
        datasource_id="sigorta",
        limit=4,
        question_repo=_FakeRepo(
            [
                {"question": "Kaç poliçe var?", "count": 12},
                {"question": "Hasar durumu nedir?", "count": 5},
            ]
        ),
    )
    texts = [s["text"] for s in out["suggestions"]]
    assert "Kaç poliçe var?" in texts
    assert out["learned_count"] >= 1


def test_build_suggestions_prefers_prepared_sql(monkeypatch):
    monkeypatch.setattr(
        "nanobase_api.suggestions.resolve_prepared_sql",
        lambda question, **_k: (
            {
                "sql_hint": "SELECT 1",
                "bind_params": {},
                "scenarioCode": "demo.count",
            }
            if "müşteri" in question.lower() or "musteri" in question.lower() or "poliçe" in question.lower()
            else None
        ),
    )
    out = build_suggestions(
        tenant_id="default",
        datasource_id="erp",
        limit=3,
        question_repo=_FakeRepo(
            [
                {"question": "Uzun ve hazır olmayan karmaşık sorgu metni burada", "count": 99},
            ]
        ),
    )
    assert out["prepared_count"] >= 1
    assert all(s.get("sql_hint") for s in out["suggestions"][: out["prepared_count"]])


def test_alert_defaults_per_datasource():
    sigorta = alert_defaults_for("sigorta")
    erp = alert_defaults_for("erp")
    assert any("hasar" in q.lower() for q in sigorta)
    assert any("fatura" in q.lower() or "stok" in q.lower() or "sipariş" in q.lower() for q in erp)
    assert "satış" not in " ".join(sigorta).lower() or "poliçe" in " ".join(sigorta).lower()


def test_build_alert_suggestions(monkeypatch):
    monkeypatch.setattr(
        "nanobase_api.infrastructure.active_source.prefer_datasource_id",
        lambda x: (x or "sigorta").strip() or "sigorta",
    )
    out = build_alert_suggestions(datasource_id="sigorta", limit=3)
    assert out["datasource_id"] == "sigorta"
    assert len(out["suggestions"]) == 3
    assert out["ask_prompt"]
    assert "hasar" in out["ask_prompt"].lower() or "poliçe" in out["ask_prompt"].lower()
